"""``stage``: a cartoon set (a picture, a generated picture or a colour / gradient) with a ground
line, named marks and the video's characters standing on them (DESIGN.md §69.6), parallax
layers that move by their factor when the camera moves (§69.7), props (§69.8), particles
(§69.9), its light and shadows (§69.31), its wind (§69.32) or a room instead of the sky (§69.42),
props that move by themselves (§69.54), snow that settles and fog (§69.60), lightning, rainbows
and the sun and moon moving across the sky (§69.61)."""

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
#: How far around a moving part of a prop that moves by itself another member counts as drawn
#: over it (frame heights: outlines and anti-aliasing reach past the points), and the level of
#: the click of a switch (dB).
REDRAW_MARGIN = 0.006
SWITCH_CLICK_GAIN = -4.0
#: A fireplace lighting: a short burner whoosh, its level (dB) and length (s).
FIRE_LIGHT_GAIN = -10.0
FIRE_LIGHT_SECONDS = 0.8
#: The level of a ringing phone's ``phone`` sound (dB), one per burst of rings.
PHONE_RING_GAIN = -6.0
#: The level of a ``knock`` on a door (dB).
KNOCK_GAIN = -3.0
#: Lightning (DESIGN.md §69.61): a bolt's core width (Manim stroke width) and how far it zigzags
#: (frame heights); the band left free above the sky's path for the sun and moon (frame heights).
BOLT_WIDTH = 4.0
BOLT_SPREAD = 0.12
SKY_TOP_ROOM = 0.14

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
    """The expression it starts with (neutral, happy, sad, angry, surprised, worried, thinking, laughing, blushing, tongue_out, crying, dizzy, frightened, or its own); none: at rest."""

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
    """A built-in prop: table, chair, tree, bush, house, door, lamp, sign, box, ball, cloud, sun, moon, rock, plant, laptop, cup, basket, umbrella, napkin, kettle; small things: cake, muffin, book, phone, letter, gift, balloons, vase, watering_can; furniture: sofa, armchair, bed, bookshelf, counter, fridge, picture, rug, houseplant, clock, tv, desk, fireplace; vehicles: bicycle, car, bus, boat (on the stage's water), hot_air_balloon, toy_rocket."""
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
    """An umbrella, a door, a book, a letter or a gift: true starts it open (the open / close actions change it later)."""
    against: Literal["wall"] | None = None
    """wall: it stands with its back to the room's wall, at the wall's depth unless depth is given (a room only); a picture or a clock in a room hangs on the wall without it."""
    on: bool = False
    """A tv, a lamp, a fireplace, a kettle or a phone: true starts it switched on (a tv's picture changes and flickers, a lamp glows, a fireplace burns and crackles, a kettle steams, a phone rings and shakes; the switch_on / switch_off actions change it)."""
    time: str | None = None
    """A clock: the time it shows at the scene's start, H:MM or H:MM:SS (default 10:10, as drawn); with time or speed the clock runs, its hands turning."""
    speed: float | None = Field(None, gt=0.0, le=MAX_CLOCK_SPEED)
    """A clock: how fast it runs, clock seconds per second (1 real time, the default; 60 a minute a second; up to 3600); with time or speed the clock runs."""
    fruit: bool = False
    """A tree: true hangs a few fruits on it (the drop_fruit action lets one fall)."""

    @model_validator(mode="before")
    @classmethod
    def _kind_only(cls, data: Any) -> Any:
        if isinstance(data, dict) and True in data and "on" not in data:   # YAML 1.1 reads the bare key `on` as true
            data = {("on" if key is True else key): value for key, value in data.items()}
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
        if self.on and self.prop not in SWITCHED_PROPS:
            raise ValueError(f"on is for props that switch on ({', '.join(SWITCHED_PROPS)}), not {self.prop or 'an svg prop'}")
        if (self.time is not None or self.speed is not None) and self.prop != "clock":
            raise ValueError(f"time and speed are for a clock, not {self.prop or 'an svg prop'}")
        if self.time is not None:
            parse_clock_time(self.time)
        if self.fruit and self.prop != "tree":
            raise ValueError(f"fruit is for a tree, not {self.prop or 'an svg prop'}")
        return self

    def runs(self) -> bool:
        """Whether it is a clock that runs (it has a ``time`` or a ``speed``)."""
        return self.prop == "clock" and (self.time is not None or self.speed is not None)

    def clock_start(self) -> float:
        """The time a running clock shows at the scene's start, seconds after midnight."""
        return DRAWN_CLOCK_SECONDS if self.time is None else parse_clock_time(self.time)

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
        for problem in (settle_problem(self.kind, self), storm_problem(self.kind, self)):
            if problem is not None:
                raise ValueError(problem[1])
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A kind alone is also a particle setting (JSON Schema ``anyOf`` kind | object)."""
        return {"anyOf": [{"enum": list(PARTICLE_KINDS)}, handler(core_schema)]}


class FlockSettings(SceneParams):
    """A flock of birds crossing the sky (DESIGN.md §69.55): how many, which way, how high, how
    fast and its seed."""

    count: int = Field(FLOCK_COUNT, ge=1, le=MAX_BIRDS)
    """How many birds (in a loose V)."""
    direction: Literal["right", "left"] = "right"
    """Which way they fly across the stage."""
    height: float = Field(FLOCK_HEIGHT, ge=0.5, le=0.97)
    """How high they fly: their height above the frame's bottom edge, as a fraction of the frame height."""
    seconds: float | None = Field(None, gt=0.0, le=120.0)
    """How long they take to cross the stage (from beyond one edge to beyond the other); default about 5 s per frame width of the stage."""
    seed: int | None = None
    """Varies the flock (their places, sizes and wing beats); default: one from the scene."""


class StageBirds(FlockSettings):
    """The stage's ``birds``: a flock crossing the sky from ``start``. ``true`` is a flock with the
    defaults, a number is how many birds."""

    also_accepts: ClassVar[tuple[type, ...]] = (bool, int)

    start: float = Field(0.5, ge=0.0)
    """When it sets off, seconds into the scene."""

    @model_validator(mode="before")
    @classmethod
    def _plain(cls, data: Any) -> Any:
        if data is False:
            raise ValueError("birds: false is the default; leave birds out")
        if data is True:
            return {}
        return {"count": data} if isinstance(data, int) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``true`` or a count is also a flock (JSON Schema ``anyOf`` true | count | object)."""
        return {"anyOf": [{"const": True}, {"type": "integer", "minimum": 1, "maximum": MAX_BIRDS}, handler(core_schema)]}


class StageFogSetting(SceneParams):
    """Fog over the stage (DESIGN.md §69.60): translucent bands lying between the things by depth,
    thicker further back, drifting. ``true`` is fog with the defaults, a number its density."""

    also_accepts: ClassVar[tuple[type, ...]] = (bool, float)

    density: float = Field(FOG_DENSITY, gt=0.0, le=1.0)
    """How thick: 0.5 hides about a third of a character at depth 0.5 and over half of the sky low down; 1 is a thick fog."""
    color: ThemeColor | None = None
    """Its colour (a theme token or #hex); default a pale grey blue."""
    drift: float = Field(1.0, ge=0.0, le=5.0)
    """How fast its waves drift sideways (1 slowly; 0 still, unless the wind blows: it is then drawn once per animation, not on every frame)."""
    seed: int | None = None
    """Varies its waves; default: one from the scene."""

    @model_validator(mode="before")
    @classmethod
    def _plain(cls, data: Any) -> Any:
        if data is False:
            raise ValueError("fog: false is the default; leave fog out")
        if data is True:
            return {}
        return {"density": data} if isinstance(data, (int, float)) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``true`` or a density is also fog (JSON Schema ``anyOf`` true | density | object)."""
        return {"anyOf": [{"const": True}, {"type": "number", "exclusiveMinimum": 0, "maximum": 1}, handler(core_schema)]}


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


class WaterStrip(SceneParams):
    """A strip of water at the front of the stage, with waves: a boat floats on it (DESIGN.md
    §69.53). ``true`` is water across the whole stage."""

    also_accepts: ClassVar[tuple[type, ...]] = (bool,)

    left: str | Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    """Where it starts: a mark or an x from 0 (left edge) to 1 (right edge) of the stage."""
    right: str | Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    """Where it ends: a mark or an x from 0 to 1, right of left."""
    color: ThemeColor | None = None
    """The water's colour (a theme token or #hex); default a clear blue."""

    @model_validator(mode="before")
    @classmethod
    def _plain(cls, data: Any) -> Any:
        return {} if data is True else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """``true`` is also water (JSON Schema ``anyOf`` true | object)."""
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
    A clock with a ``time`` or a ``speed`` runs; a tv ``on`` shows a flickering picture, a
    lamp ``on`` glows, a fireplace ``on`` burns and crackles, a kettle ``on`` steams, a phone
    ``on`` rings (``switch_on`` / ``switch_off`` change them). Small things to hold: a cake, a
    muffin, a book and a letter and a gift (they ``open`` and ``close``), balloons (``let_go``
    floats them away), a vase of flowers and a watering can (``pour``). A tree with ``fruit`` carries fruits that
    ``drop_fruit`` lets fall (on a character's head too); ``birds`` (or the ``birds`` action) send
    a flock across the sky. Snow with ``settle: true`` lies on the ground and the props in a
    growing white layer; ``fog`` lies in bands between the things by depth, thicker further back.
    ``lightning`` flashes the set with a bolt, its thunder following by the strike's distance
    (rain with ``lightning: true`` strikes on its own); ``rainbow`` fades a rainbow into the sky;
    a ``light`` change with ``move_sun: true`` moves the sun and the moon along their arc across
    the sky, the shadows lengthening and turning away from the sun.

    A beat is spoken by the characters whose voice says it (their mouths move with it), or by
    the ones its ``say`` action names; the acting actions (``say``, ``look_at``, ``turn``,
    ``emote``, ``pose``, ``react``) change the characters during the beats, and the moving ones
    (``walk_to``, ``run_to``, ``enter``, ``exit``, ``gesture``, ``jump``) move them; ``effect``
    puts a symbol over a head (an idea bulb, a sweat drop, a question mark...). A character with an
    ``enter`` action waits off stage until it enters. Walks, entrances, exits, jumps, a
    surprised face and most symbols make their own sounds, doors creak (``knock`` knocks on one),
    and the set plays a quiet bed: birdsong outdoors by day, a room tone indoors, or ``ambience:
    city`` (foley; ``foley: false`` turns them off);
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
    ``stand_up``. They ``get_in`` a car or a bus (or on a bicycle), ``ride_to`` a place in it with
    its wheels turning (pedalling on a bicycle) and ``get_out``. ``water`` puts a strip of water
    with waves at the front, where a boat bobs and rides; a hot-air balloon rises, drifts with the
    wind and lands; a toy rocket launches with smoke and floats down under its parachute (or flies
    off, ``land: false``).

    Action targets: each character and each prop by its name; each part of a character as
    ``<character>.<part>`` (``kit.arm_left``).
    """

    outro = 0.5
    takes_host = False   # its characters are on the set already (DESIGN.md §71)
    target_patterns = ("<character>", "<prop>", "<character>.<part>")
    uses_cartoon_style = True
    #: Storyboard stills also show these actions half-way through (DESIGN.md §69.16).
    mid_still_actions = frozenset({
        "walk_to", "run_to", "enter", "exit", "gesture", "jump", "keyframes", "move_along", "pick_up", "put_down", "give", "throw",
        "sit_on", "lean_on", "stand_up", "blow_away", "get_in", "ride_to", "get_out", "let_go", "pour",
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
        """Sounds for the characters' actions (footsteps, whoosh on enter / exit, boing on jump, pop on a surprised face, a sound with most effect symbols), and the ambience: false for none in this scene; default: the video's foley (on)."""
        ambience: bool | Literal["auto", "birdsong", "city", "room_tone"] | list[Literal["birdsong", "city", "room_tone"]] | None = None
        """A sound bed under the whole scene while foley is on: birdsong, city (street sounds), room_tone, or a list of them; auto (or true): chosen from the set: room_tone in a room, birdsong outdoors while the light is day or morning and it does not rain; false: none; default: the video's ambience (auto). Rain and a burning fire play their own beds whatever this says."""
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
        """Props: a built-in prop's name, or {prop | svg, name, at, depth, scale, lift, facing, color, detail, recolor, open, against, on, time, speed, fruit}."""
        particles: list[StageParticles] = []
        """Particles over the whole scene, in front of everything: a kind (rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves, streaks) or {kind, density, area, color, seed, puddles, lightning, settle, settled}; rain ends on the ground with splashes, not under an open umbrella or a tree, and plays a rain sound with foley; rain with lightning: true flashes lightning with thunder at seeded times; snow with settle: true lands on the ground and the props, where a white layer grows; for one beat use the particles action."""
        light: LightSetting = "day"
        """The light on the set: day (as drawn), morning, sunset, night (dark blue, with stars on a colour background) or indoor, or {tint, strength}: a colour grade of the background, layers, props and characters (never of speech bubbles, captions or other text); the light action changes it during the scene."""
        shadows: bool = True
        """Soft shadows on the ground under the characters and the props standing on it (smaller when they jump, none under a held prop); false: none."""
        wind: WindSetting = 0.0
        """Wind from the start, in gusts: 0 calm (nothing moves) .. 1 a gale blowing to the right (negative: to the left), or calm, breeze (0.3), windy (0.6), gale (1); trees, bushes, plants, signs and lamps sway, scarves, long hair, floppy or pointy ears and hats trail (clearly from windy on), particles drift (add leaves or streaks to show it more); the wind action changes it during the scene, blow_away blows a light prop away."""
        room: StageRoom | None = None
        """An indoor set instead of the sky and the ground: true, or {wall, wallpaper (plain, stripes, dots), floor, flooring (boards, tiles, plain), skirting, ceiling, depth, windows, doors}; windows show the sky of the stage's light, doors are door props whose names are marks (enter / exit through them); no wind, rain, snow, leaves or streaks inside."""
        water: WaterStrip | None = None
        """A strip of water with waves at the front of the stage, for a boat to float on: true (the whole width) or {left, right, color} (marks or x from 0 to 1); outdoors only."""
        birds: StageBirds | None = None
        """A flock of birds crossing the sky, flapping: true, a number of birds, or {count, direction, height, start, seconds, seed}; outdoors only (the birds action sends one later)."""
        fog: StageFogSetting | None = None
        """Fog in translucent bands lying between the characters and props by depth, thicker further back (the sky most), drifting slowly and with the wind: true, a density from 0 to 1 (true: 0.5), or {density, color, drift, seed}; outdoors only."""

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
            self._check_water_and_air(marks)
            if self.room is not None:
                self._check_room()
            return self

        def water_span(self) -> tuple[float, float] | None:
            """The water's left and right x (0..1 of the stage; ``None``: no water)."""
            if self.water is None:
                return None
            marks = self.stage_marks()
            return mark_x(self.water.left, marks), mark_x(self.water.right, marks)

        def _check_water_and_air(self, marks: dict[str, float]) -> None:
            """Water and air vehicles stay outdoors; a boat floats on the stage's water, at the
            front (DESIGN.md §69.53)."""
            if self.water is not None:
                if self.room is not None:
                    raise ValueError("a room has no water: remove water (or the room)")
                try:
                    left, right = self.water_span() or (0.0, 1.0)
                except ValueError as exc:
                    raise ValueError(f"water: {exc}") from None
                if left >= right:
                    raise ValueError(f"water: left ({left:g}) must be left of right ({right:g})")
            for k, (prop, name) in enumerate(zip(self.props, self.prop_names())):
                if prop.prop not in VEHICLES or VEHICLES[prop.prop].medium == "ground":
                    continue
                if self.room is not None:
                    raise ValueError(f"props[{k}]: a {prop.prop.replace('_', ' ')} stays outdoors; remove it (or the room)")
                if VEHICLES[prop.prop].medium != "water":
                    continue
                span = self.water_span()
                if span is None:
                    raise ValueError(f"props[{k}]: '{name}' floats on water: give the stage water: true (or {{left, right}})")
                x = mark_x(prop.at, marks)
                if not span[0] <= x <= span[1]:
                    raise ValueError(f"props[{k}]: '{name}' at {x:.2f} is not on the water (from {span[0]:.2f} to {span[1]:.2f}); put it at an x there")
                if prop.depth != 0.0:
                    raise ValueError(f"props[{k}]: '{name}' floats at the front (depth 0), where the water is; remove its depth")

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
            if self.birds is not None:
                raise ValueError("birds fly outdoors: remove birds (or the room)")
            if self.fog is not None:
                raise ValueError("there is no fog in a room: remove fog (or the room)")
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
        seat taken, a walk of a character that sits, leans or rides, a full vehicle or one too far
        to get in (§69.52). Needs the active project (the video's frame); none without one."""
        fruit = cls._fruit_count_problems(params, uses)
        try:
            project = current_project()
        except VidgenError:
            return fruit
        if not any(u.config.action in HANDLING_ACTIONS | POSTURE_ACTIONS | RIDING_ACTIONS for u in uses):
            return fruit
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
            vehicles={name: (kind, height) for name, (kind, height, _) in frame.vehicles.items()},
            water=frame.water,
            kinds={name: p.prop for name, p in zip(params.prop_names(), params.stage_props())},
        )
        return fruit + problems + cls._calm_blow_problems(params, ordered)

    @staticmethod
    def _fruit_count_problems(params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """A ``drop_fruit`` of a tree whose fruits have all fallen (DESIGN.md §69.55)."""
        dropped: dict[str, int] = {}
        problems: list[tuple[str, str]] = []
        for use in uses:
            if use.config.action != "drop_fruit":
                continue
            for name in [n for n in params.prop_names() if any(fnmatchcase(n, p) for p in use.config.targets())]:
                dropped[name] = dropped.get(name, 0) + 1
                if dropped[name] == len(FRUIT_SPOTS) + 1:
                    problems.append((f"{use.location}.target", f"'{name}' has {len(FRUIT_SPOTS)} fruits; they have all fallen by then"))
        return problems

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
        on a surprised face, a sound for an effect symbol (unless its ``sound: false``), a door's
        creak, a splash of water (:func:`foley_cues`), splashing steps once puddles lie on the
        ground (:func:`wet_steps`); none with ``foley: false`` (the stage's, else the video's). A
        project file with a sound's name plays as it is (without the cue's params)."""
        if not self._foley_on():
            return
        wet_from = min(getattr(self, "_puddles_from", []), default=None)
        for anim in animations:
            for cue in wet_steps(foley_cues(_played(action, options, anim, start, seconds)), wet_from):
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
        over. None in a draft (§74)."""
        on = self.params.motion_effects if self.params.motion_effects is not None else self.project.config.motion_effects
        if not on or self.is_draft:
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
                self._add_motion_effect(effect, mover, behind=cue.kind in ("speed_lines", "smoke"))

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

    def ride_in_depth(self, vehicle: Prop, ride: Ride) -> None:
        """``vehicle`` rides in depth with ``ride``: its place in the draw order, with its riders,
        follows its depth on every frame (:meth:`_keep_depth_order`, DESIGN.md §69.52), and the
        ground line under it is its new depth's once it stops."""
        self.grounds[vehicle.name] = self.feet_y_at(ride.to_depth)
        for seat in ride.seats:
            self.grounds[seat.rider.name] = self.grounds[vehicle.name]
        self._depth_walks.append((vehicle, ride))
        self._watch_draw_order()

    def _start_depth_order(self) -> None:
        """Watch the draw order from the start when a walk in depth or a turn to the front may
        change it (a character facing front, or a turn to it, :meth:`_watch_draw_order`)."""
        #: the walks and rides in depth under way: (character or vehicle, walk or ride)
        self._depth_walks: list[tuple[Mobject, Walk | Ride]] = []
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
        if self._depth_walks:
            changed |= self._sort_fog()   # a walker may pass a fog band's depth (§69.60)
        self._depth_walks = [(c, w) for c, w in self._depth_walks if abs(c.stage_depth - w.to_depth) > SAME_DEPTH]
        for name, figure in self.cast.items():
            if self._part_orders.get(name) != figure.order_changes:
                self._part_orders[name] = figure.order_changes
                changed = True
        if changed and getattr(self, "animations", None):
            self.moving_mobjects = self._moving_in_order()

    def _moving_in_order(self) -> list[Mobject]:
        """What Manim draws on each frame of the animation playing now, in the current draw order:
        what it drew so far plus what moves now. Manim drew everything else once, when the
        animation began, into its static image; a thing dropped from this list mid-play (a prop at
        the depth the walker has left behind, so no longer one it passes) would be drawn in neither
        and vanish until the next animation (§69.44)."""
        now = self.get_moving_and_static_mobjects(self.animations)[0]
        kept = {id(m) for m in self.moving_mobjects} | {id(m) for m in now}
        ordered = self.get_mobject_family_members()
        known = {id(m) for m in ordered}
        return [m for m in [*ordered, *(m for m in now if id(m) not in known)] if id(m) in kept]

    def _keep_depth_order(self, walker: Mobject) -> bool:
        """Move ``walker`` (with the props it holds; a vehicle with its riders) to its place among
        the characters and props for its depth now (:func:`depth_slot`), the moving shadows before
        the first thing whose shadow they draw; whether it moved."""
        block = _moving_block(self, walker)
        if not block:
            return False
        ids = {id(m) for m in block}
        things = {id(m) for m in [*self.cast.values(), *self.props.values()] if getattr(m, "held_by", None) is None} - ids
        block_at = next(k for k, m in enumerate(self.mobjects) if id(m) in ids)
        rest = [m for m in self.mobjects if id(m) not in ids]
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
            if not isinstance(anim, (Walk, Ride)) or anim.to_depth is None:
                continue
            low, high = sorted((float(anim.mobject.stage_depth), anim.to_depth))
            riders = [seat.rider for seat in anim.seats] if isinstance(anim, Ride) else []
            for thing in [anim.mobject, *riders, *(t for t in things if low - SAME_DEPTH <= float(getattr(t, "stage_depth", 0.0)) <= high + SAME_DEPTH)]:
                found |= {id(m) for m in thing.get_family()}
            fog = getattr(self, "fog", None)   # the fog bands it passes (§69.60)
            for band in fog.bands if fog is not None else []:
                if low - SAME_DEPTH <= band.stage_depth <= high + SAME_DEPTH:
                    found |= {id(m) for m in band.get_family()}
        return found

    # ----- rain on the ground (DESIGN.md §69.39) --------------------------------------------------

    def rain_ground(self) -> RainGround:
        """Where rain ends now: the landing band from the ground line up to the top of the ground
        area, and the shelters (open umbrellas, held or standing, and trees) where they are."""
        shelters = [s for s in (self._shelter_of(prop) for prop in self.props.values()) if s is not None]
        top = ground_top(self.params.ground, self.params.items())
        return rain_ground(self.params.ground, top, self.frame_height, shelters)

    def _shelter_of(self, prop: Prop) -> ShelterBox | None:
        """The box ``prop`` keeps rain off now (an open umbrella, a tree; ``None``: none): its drawn
        bounds, on its feet or its holder's."""
        if prop.kind not in SHELTER_PROPS:
            return None
        holder = self.cast.get(prop.held_by) if prop.held_by is not None else None
        feet = float((holder.feet() if holder is not None else prop.feet())[1])
        box = (float(prop.get_left()[0]), float(prop.get_right()[0]), float(prop.get_top()[1]))
        return prop_shelter(prop.kind, prop.shape, box, feet)

    def particles_started(self, field: Any, settings: Any) -> None:
        """A rain field: its sound bed plays while it lasts (with foley), and, with ``puddles:
        true``, puddles grow on the ground under it (drawn over the ground band, under the
        shadows, characters and props). A snow field with ``settle: true``: its layer grows
        (:meth:`_settle_snow`)."""
        if field.seeds.kind == "snow" and settings.settle and not self.is_draft:
            self._settle_snow(field, settings)
        if field.seeds.kind != "rain":
            return
        every = storm_every(settings)
        if every is not None:   # lightning while it rains (§69.61); a draft hears its thunder only (§74)
            storm = RainStorm(field.start, every, motion_seed(self.spec.id, "storm", settings.seed, len(self._storms)), lambda: field.ended)
            self._storms.append(storm)
            if not self.is_draft:
                self._lit().storms.append(storm)
                self._watch_light()
        if self._foley_on():
            self._rain_fields.append(field)
        if not settings.puddles:
            return
        self._puddles_from.append(field.start)   # steps splash from then on, also in a draft without puddles (§74)
        if self.is_draft:
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

    # ----- snow that settles (DESIGN.md §69.60) -----------------------------------------------------

    def snow_ground(self) -> RainGround:
        """Where settling snow ends now: rain's landing band, open umbrellas (held or standing) and
        the top line of every prop that catches snow (:meth:`_snow_tops`)."""
        tops = self._snow_tops()
        shelters: list[Any] = []
        for name, prop in self.props.items():
            if prop.kind == "umbrella":
                shelters += [s for s in [self._shelter_of(prop)] if s is not None]
            elif name in tops:
                shelters.append(tops[name])
        top = ground_top(self.params.ground, self.params.items())
        return rain_ground(self.params.ground, top, self.frame_height, shelters)

    def _snow_tops(self) -> dict[str, TopLine]:
        """The top lines of the props that catch snow, by name, taken once (they stay put): every
        prop on the ground that no action moves, but flat ones (a rug), floating ones and
        umbrellas (sheltering boxes)."""
        if getattr(self, "_tops", None) is None:
            hanging = {item.name for item in self.params.items() if item.lift + item.hang > 0}
            fixed = set(self.props) - self._movable_props() - hanging
            self._tops: dict[str, TopLine] | None = {}
            for name in sorted(fixed):
                prop = self.props[name]
                if prop.kind in (*FLAT_PROPS, *WATER_VEHICLES, *AIR_VEHICLES, "umbrella") or prop.held_by is not None:
                    continue
                line = prop_top_line(prop)
                if line is not None:
                    self._tops[name] = TopLine(line[0], line[1], float(prop.feet()[1]))
        return self._tops

    def _settle_snow(self, field: Any, settings: Any) -> None:
        """The layer a settling snow ``field`` leaves (:class:`SettledSnow`): a blanket on the
        ground area (thin under trees and standing open umbrellas), laid like puddles, and a cap
        right after each prop that catches snow and does not sway, all lit; it grows in steps."""
        ground = self.rain_ground()
        left, right = self.camera_bounds()[:2]
        movable = self._movable_props()
        bare = [s for s in (self._shelter_of(p) for n, p in self.props.items() if p.held_by is None and n not in movable) if s is not None]
        token = settings.color[0] if isinstance(settings.color, list) else settings.color
        color = SNOW_COLOR if token is None else resolve_color(token, self.theme)
        swaying = set(SWAYS) if getattr(self, "blowing", None) is not None else set()
        short = min(self.frame_width, self.frame_height)
        caps = []
        for name, line in self._snow_tops().items():
            prop = self.props[name]
            if prop.kind in swaying:
                continue   # its cap would not sway with it
            full = cap_full_thickness(short, float(getattr(prop, "stage_depth", 0.0)), float(prop.height))
            caps.append(SnowCap(line.xs, line.ys, full, color, cap_of=name))
        layer = SettledSnow(
            SnowBlanket(color), caps, area=(left, right, -self.frame_height / 2, ground.back), frame_height=self.frame_height,
            bare=bare_patches(bare), start=field.start, ended=lambda: field.ended, density=settings.density,
            settled=settings.settled, seed=settings.seed,
        )
        mark_lit(layer.blanket, *caps)
        self.snow_layers.append(layer)
        self._lay_on_ground(layer.blanket, under_water=True)
        for cap in caps:
            self._put_after_prop(cap.cap_of, cap)
        self._watch_living()

    def _put_after_prop(self, name: str, mobject: Mobject) -> None:
        """Draw ``mobject`` right after the prop ``name``: now, when the prop is on screen, else
        when it comes in (:meth:`construct`'s entrance)."""
        prop = self.props[name]
        at = next((k for k, m in enumerate(self.mobjects) if m is prop), None)
        if at is None:
            self._after_props.setdefault(name, []).append(mobject)
        else:
            self.mobjects.insert(at + 1, mobject)

    # ----- fog (DESIGN.md §69.60) -------------------------------------------------------------------

    def _fog(self) -> StageFog | None:
        """The stage's ``fog`` (``None``: none): its bands lit by the light, drifting with the
        stage's wind when it may blow, and the scene updater when its waves move. None in a draft (§74)."""
        setting = self.params.fog
        if setting is None or self.is_draft:
            return None
        left, right = self.camera_bounds()[:2]
        color = resolve_color(setting.color, self.theme) if setting.color is not None else FOG_COLOR
        wind = getattr(self, "particle_wind", None)
        fog = StageFog(
            density=setting.density, color=color, ground=self.params.ground, left=left, right=right, frame_height=self.frame_height,
            drift=setting.drift, seed=setting.seed if setting.seed is not None else motion_seed(self.spec.id, "fog"),
            blown=(lambda now: wind(0.0, now)[0]) if wind is not None else None,
        )
        mark_lit(*fog.bands)
        if fog.moves:
            self._watch_living()
        return fog

    def _sort_fog(self) -> bool:
        """Put each fog band right before the first character or prop (in draw order) standing
        at its depth or nearer (before the props that one holds in front of it), else before the
        foreground: everything deeper is seen through it. Whether the draw order changed."""
        fog = getattr(self, "fog", None)
        if fog is None:
            return False
        before = [id(m) for m in self.mobjects]
        bands = {id(b) for b in fog.bands}
        self.mobjects[:] = [m for m in self.mobjects if id(m) not in bands]
        depths = {id(m): float(getattr(m, "stage_depth", 0.0)) for m in [*self.cast.values(), *self.props.values()] if getattr(m, "held_by", None) is None}
        front = {id(m) for m in self._in_front}
        after = 0
        for band in fog.bands:   # back to front
            at = next((k for k, m in enumerate(self.mobjects) if k >= after and id(m) in depths and depths[id(m)] <= band.stage_depth), None)
            if at is None:
                at = next((k for k, m in enumerate(self.mobjects) if k >= after and (id(m) in front or isinstance(m, ParticleField))), len(self.mobjects))
            else:
                name = getattr(self.mobjects[at], "name", None)
                while at > after and getattr(self.mobjects[at - 1], "held_by", None) == name:
                    at -= 1
            self.mobjects.insert(at, band)
            after = at + 1
        return [id(m) for m in self.mobjects] != before

    def _watch_living(self) -> None:
        """Install the scene updater of the things that move by themselves (once)."""
        if not any(f is self._living_updater for f in self.updaters):
            self.add_updater(self._living_updater)

    def _lay_on_ground(self, mobject: Mobject, *, under_water: bool = False) -> None:
        """Put ``mobject`` right in front of the set behind the characters (before the shadows):
        into the backdrop while it has not come on screen yet (it fades in with it), else into
        the scene. ``under_water``: right before the stage's water instead, when it has some."""
        water = getattr(self, "water", None)
        if under_water and water is not None:
            for drawn in (self.mobjects, self._backdrop):
                at = next((k for k, m in enumerate(drawn) if m is water.back), None)
                if at is not None:
                    drawn.insert(at, mobject)
                    return
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
        to its end (the scene's end while it lasts, DESIGN.md §69.39), the fire's crackle while
        each fireplace burns (§69.55) and the set's beds (:meth:`set_beds`, §69.62), with foley;
        scene seconds."""
        data = super().timings()
        end = float(self.renderer.time)
        spans = [(f.start, end if f.ended is None else min(f.ended, end)) for f in getattr(self, "_rain_fields", [])]
        beds = [{"bed": "rain", "start": round(a, 6), "end": round(b, 6)} for a, b in spans if b > a]
        fires = [live for live in getattr(self, "living", {}).values() if live.kind == "fireplace"] if self._foley_on() else []
        beds += [{"bed": "fire", "start": round(a, 6), "end": round(b, 6)} for live in fires for a, b in on_spans(live.on, live.switches, end)]
        beds += [{"bed": bed, "start": round(a, 6), "end": round(b, 6)} for bed, a, b in self.set_beds([s for s in spans if s[1] > s[0]], end)]
        if beds:
            data["ambience"] = beds
        return data

    def set_beds(self, rain: list[tuple[float, float]], end: float) -> list[tuple[str, float, float]]:
        """The set's ambience beds of a scene of ``end`` seconds with ``rain`` spans
        (:func:`set_ambience`): the stage's ``ambience``, else the video's; none without foley."""
        if not self._foley_on():
            return []
        given = self.params.ambience
        setting: bool | list[str]
        if given is None:
            setting = self.project.config.ambience
        elif isinstance(given, bool):
            setting = given
        else:
            setting = True if given == "auto" else [given] if isinstance(given, str) else list(given)
        lights = getattr(self, "light_marks", [(0.0, None)])
        return set_ambience(setting, room=self.params.room is not None, lights=lights, rain=rain, end=end)

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
        living = self._living_names()
        left, right = self.camera_bounds()[:2]
        on_stage: list[tuple[str, Mobject]] = []
        for place_at in placements:
            self.grounds[place_at.name] = feet_point(
                place_at.x_fraction, place_at.depth, p.ground, self.frame_width, self.frame_height,
            )[1]
            if place_at.kind == "prop":
                item = self._prop(place_at.name, props[place_at.name], place_at.height, living=place_at.name in living)
                item.height_factor = props[place_at.name].height_factor()
                item.shift(np.array([*place_at.feet, 0.0]) - item.feet())
                item.stage_depth = place_at.depth   # its place in the draw order (walks in depth, §69.44)
                item.raised = props[place_at.name].resolved_lift() + props[place_at.name].resolved_hang() > 0
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
            if not p.idle or self.is_draft:   # a draft: no breathing, swaying or blinking (§74)
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
            # the holder stands a hand and the prop further out, so the prop in its hand stays out of view
            outward = 1.0 if figure.feet()[0] > (left + right) / 2 else -1.0
            figure.shift([outward * (figure.width / 2 + item.width), 0.0, 0.0])
            item.shift([float(figure.feet()[0] - item.feet()[0]), 0.0, 0.0])
        #: the stage's water (``None``: none): its band over the ground, its front strip in front of
        #: everything, the boats bobbing on it (DESIGN.md §69.53)
        self.water = self._water()
        if self.water is not None:
            backdrop.append(self.water.back)
            in_front.insert(0, self.water.front)
            for prop in self.props.values():
                if prop.is_vehicle and VEHICLES[prop.kind].medium == "water":
                    self.water.float_boat(prop)
        # the light grades the set, not the stars, shadows, bubbles or text (DESIGN.md §69.31)
        mark_lit(*[m for m in backdrop if not isinstance(m, (StarField, WindowViews))], *in_front, *(mob for _, mob in on_stage))
        self._start_living(living)
        still, moving = self._shadows(placements)
        backdrop += [still] if still is not None else []
        self._start_sky_path()
        # register back to front, so the fade-ins add them (and draw them) in that order
        targets = [self.target(name, mob) for name, mob in on_stage]
        for whole in targets:  # parts come on screen with their character (§69.14)
            if isinstance(whole.mobject, Character):
                for part in whole.mobject.parts:
                    self.target(f"{whole.name}.{part}", whole.mobject.parts[part], entrance=lambda t=whole: self.entrance(t))
        cast_by = {id(c.mobject) for c in (moving.casters if moving is not None else [])}
        first_moving = next((k for k, t in enumerate(targets) if id(t.mobject) in cast_by), None)

        def entrance() -> list:
            """The set comes in as one picture: everything is added at once, back to front, under
            a cover of the background colour that fades out (a fade-in per thing would show the
            things behind through each one while they fade, §69.51)."""
            shown: list[Mobject] = [*backdrop]
            items: list = []
            for k, t in enumerate(targets):  # moving things' shadows: drawn just before the first of them
                shown += [moving] if k == first_moving else []
                if self.is_shown(t):
                    continue
                carried = self._claim_carried(t) if self._carried else None   # a copy from the scene before moves in (§50)
                if carried is not None:
                    items.append(carried)
                else:
                    live = self.living.get(t.name)   # a glow right behind it, steam right in front (§69.54, §69.55)
                    shown += [m for m in (live.glow if live else None, t.mobject, live.steam if live else None) if m is not None]
                    shown += self._after_props.pop(t.name, [])   # its snow cap (§69.60)
            self.add(*shown, *in_front)
            for body in self.sky_bodies:   # a moving sun or moon goes behind everything (§69.61)
                self.mobjects.remove(body.prop)
                self._put_in_sky(body.prop)
            self._sort_fog()
            return [FadeOut(self._cover()), *items]

        self._start_wind(placements)
        self._start_water()
        self._start_depth_order()
        #: the set behind the characters (puddles go in it, DESIGN.md §69.39)
        self._backdrop = backdrop
        #: the flocks of birds in the sky (DESIGN.md §69.55), drawn right after the sky
        self.flocks: list[Flock] = []
        if p.birds is not None:
            self.add_flock(p.birds, p.birds.start)
        if p.room is None and self._lightning_used() and not self.is_draft:
            self.bolt = LightningBolt()
            self._put_in_sky(self.bolt)
        #: the rain fields whose sound bed plays (foley on)
        self._rain_fields: list[ParticleField] = []
        #: the puddles under the rain fields with ``puddles: true``
        self.puddles: list[Puddles] = []
        #: the scene times the rain fields with ``puddles: true`` started (wet steps follow them)
        self._puddles_from: list[float] = []
        #: the layers of the snow fields with ``settle: true``, what waits to be drawn right after
        #: a prop when it comes in (its snow cap), and the stage's fog (DESIGN.md §69.60)
        self.snow_layers: list[SettledSnow] = []
        self._after_props: dict[str, list[Mobject]] = {}
        self._in_front = in_front
        self.fog = self._fog()
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
        self._ring_sounds()
        self._storm_thunder()

    def _cover(self) -> Rectangle:
        """A rectangle of the background colour over everything, larger than the view and kept
        on it, for the set to fade in under as one picture (:meth:`construct`'s entrance) or out
        (:meth:`finish`)."""
        frame = self.camera.frame
        cover = Rectangle(width=frame.width * 1.5, height=frame.height * 1.5, stroke_width=0)
        cover.set_fill(self.camera.background_color, opacity=1.0)
        cover.add_updater(lambda m: m.move_to(frame.get_center()))
        self.add(cover.move_to(frame.get_center()))
        return cover

    def finish(self) -> None:
        """The scene's outro: the set fades out as one picture, under a cover of the background
        colour fading in over everything (also the particles, bubbles and symbols drawn above it),
        then everything leaves the scene (as after a fade out); fading each thing on its own
        showed what stands behind a house through it. As
        :meth:`NarratedScene.finish` when there is no outro, a transition takes the picture away or
        the next scene carries something on (DESIGN.md §49, §50)."""
        if self.outro <= 0 or (self.transition_out is not None and not self.transition_out.cut) or self._carried_parts():
            super().finish()
            return
        top = max((m.z_index for m in self.get_mobject_family_members()), default=0)
        self.play(FadeIn(self._cover().set_z_index(top + 1)), run_time=self.outro)
        self.remove(*self.mobjects)   # gone, as a fade out leaves the scene

    # ----- light and shadows (DESIGN.md §69.31) ---------------------------------------------------

    def _start_light(self) -> None:
        """The light at the start (``light``) and, when it grades anything or a ``light`` action
        changes it, the :class:`StageLight` that grades the set as the camera draws it."""
        #: the light from the start, and whether any light of the scene has stars
        self.base_light = resolve_light(self.params.light, self.theme)
        #: (scene time, light preset or ``None`` for a tint) from the start: where the light
        #: counts as changed for the ambience (half-way through each change, DESIGN.md §69.62)
        self.light_marks: list[tuple[float, str | None]] = [(0.0, self.params.light if isinstance(self.params.light, str) else None)]
        changes = [resolve_light(use.setting(), self.theme) for use in self.action_uses("light")]
        self._starry = max([self.base_light.stars, *(g.stars for g in changes)]) > 0
        flashes = self._lightning_used()
        #: the stage's light (``None``: the set as drawn, nothing changes it)
        #: (a draft's is flat: nothing graded, no flashes, the changes at their times, §74)
        self.light: StageLight | None = (
            StageLight(self.renderer.camera, self.base_light, flat=self.is_draft) if self.base_light.changes_colors or changes or flashes else None
        )
        if self.light is not None and self.params.room is not None:
            self.light.flash_share *= ROOM_FLASH   # only what comes in through the windows (§69.61)
        #: the lightning bolt in the sky, the rainbows, the suns and moons moving along the sky's
        #: path and the rain fields' storms (DESIGN.md §69.61)
        self.bolt: LightningBolt | None = None
        self.rainbows: list[StageRainbow] = []
        self.sky_bodies: list[SkyBody] = []
        self._storms: list[RainStorm] = []
        self._bolt_paths: dict[int, list[np.ndarray]] = {}
        self.stars: StarField | None = None
        self.window_views: WindowViews | None = None
        self.shadows: list[StageShadows] = []
        #: the scene updater while the light changes, kept: Manim removes an updater by identity,
        #: and each ``self._light_step`` is a new bound method
        self._light_updater = self._light_step

    def change_light(self, setting: str | CustomLight, start: float, seconds: float, *, move_sun: bool = False) -> None:
        """Fade the light to ``setting`` (a preset or a tint) from scene time ``start`` over
        ``seconds`` (the ``light`` action); everything is redrawn on every frame meanwhile.
        ``move_sun``: the suns and moons move along the sky's path to their places for the preset
        meanwhile (DESIGN.md §69.61)."""
        self.light_marks.append((float(start) + max(float(seconds), 0.0) / 2, setting if isinstance(setting, str) else None))
        if self.window_views is not None:   # the sky outside fades with it (§69.42)
            self._sky_changes.append(SkyChange(float(start), max(float(seconds), 0.0), window_sky(self._light_key(setting))))
        if move_sun and isinstance(setting, str):
            for body in self.sky_bodies:
                body.moves.append(PathMove(float(start), max(float(seconds), 0.0), place_for(body.kind, setting)))
        self._lit().change(resolve_light(setting, self.theme), start, seconds)
        self._watch_light()

    def _lit(self) -> StageLight:
        """The stage's light, made now when it has none yet."""
        if self.light is None:
            self.light = StageLight(self.renderer.camera, self.base_light, flat=self.is_draft)
            self.light.on_change(self._show_light)
        return self.light

    def _watch_light(self) -> None:
        """Install the scene updater of the light (once)."""
        if not any(f is self._light_updater for f in self.updaters):
            self.add_updater(self._light_updater)

    def _light_step(self, dt: float) -> None:
        """Scene updater while the light changes or lightning may flash: the sky (§69.61) and the
        grade for the scene time now; it removes itself once every change and flash is over (a
        scene updater makes Manim redraw every frame)."""
        now = float(self.renderer.time)
        self._sky_step(now)
        if self.light is not None:
            self.light.update(now)
        if self.light is None or self.light.settled(now):
            self.remove_updater(self._light_updater)

    def _show_light(self, grade: LightGrade) -> None:
        """The stars' brightness and the shadows' darkness for ``grade``, and the sky outside a
        room's windows for the light now (lit by lightning, §69.61)."""
        if self.stars is not None:
            self.stars.set_level(grade.stars)
        if self.window_views is not None:
            sky = sky_at(self._sky_base, self._sky_changes, float(self.renderer.time))
            self.window_views.show(flash_sky(sky, self.light.flash) if self.light is not None else sky)
        for group in self.shadows:
            group.set_strength(grade.shadow)

    # ----- lightning, rainbows, the sun and moon moving (DESIGN.md §69.61) --------------------------

    def _lightning_used(self) -> bool:
        """Whether lightning may flash in this scene: a ``lightning`` action, or rain with
        ``lightning`` (the stage's or a ``particles`` action's)."""
        rain = [p for p in self.params.particles if p.kind == "rain"] + [u.options for u in self.action_uses("particles") if u.kind() == "rain"]
        return bool(self.action_uses("lightning")) or any(r.lightning is not False for r in rain)

    def _horizon_y(self) -> float:
        """The y of the horizon: the back edge of the ground area (Manim units)."""
        return (ground_top(self.params.ground, self.params.items()) - 0.5) * self.frame_height

    def strike_lightning(self, at: str | float | None, time: float, *, distance: float = THUNDER_DISTANCE, bolt: bool = True, seed: int | None = None) -> Strike:
        """Lightning strikes at scene ``time`` (the ``lightning`` action): the set flashes (a room
        less, through its windows), a bolt strikes at ``at`` (a mark or an x; ``None``: a seeded
        place; none in a room or with ``bolt`` false) and its thunder follows ``distance`` km
        later (foley)."""
        seed = seed if seed is not None else motion_seed(self.spec.id, "lightning", round(float(time), 3))
        x = mark_x(at, self.params.stage_marks()) if at is not None else 0.15 + 0.7 * (seed % 1000) / 999
        strike = Strike(float(time), x, float(distance), seed, bolt and self.params.room is None)
        if not self.is_draft:   # a draft: no flash, no bolt, the thunder at its time (§74)
            self._lit().strikes.append(strike)
            self._watch_light()
        self._thunder(strike)
        return strike

    def _thunder(self, strike: Strike) -> None:
        """The thunder of ``strike`` (foley; heard where it struck)."""
        if not self._foley_on():
            return
        cue = strike.thunder
        params = {} if self.sounds.file("thunder") is not None else {"duration": cue.duration, "intensity": cue.intensity, "pitch": cue.pitch}
        self.sfx("thunder", strike.time + cue.delay, gain=cue.gain, pan=thunder_pan(strike.x), **params)

    def _storm_thunder(self) -> None:
        """The thunder of the strikes of the rain fields' storms, once the scene has played: of
        those whose thunder starts before the scene's end (the others' would only begin in the
        next scene)."""
        end = float(self.renderer.time)
        for storm in self._storms:
            for strike in storm.strikes(end):
                if strike.time + strike.thunder.delay < end:
                    self._thunder(strike)

    def _show_bolt(self, now: float) -> None:
        """The bolt of the brightest strike with one at scene time ``now`` (none: hidden)."""
        if self.bolt is None or self.light is None:
            return
        lit = [(s.level(now), s) for s in self.light.strikes_until(now) if s.bolt]
        level, strike = max(lit, key=lambda ls: ls[0], default=(0.0, None))
        if strike is None or level <= 0:
            self.bolt.hide()
            return
        if strike.seed not in self._bolt_paths:
            left = -self.stage_width / 2
            self._bolt_paths[strike.seed] = bolt_paths(
                strike.seed, left + strike.x * self.stage_width, self.frame_height / 2, self._horizon_y(), BOLT_SPREAD * self.frame_height,
            )
        width = BOLT_WIDTH * min(max(1.2 - 0.1 * strike.distance, 0.4), 1.2)
        self.bolt.show(self._bolt_paths[strike.seed], width, min(level / flash_strength(strike.distance), 1.0))

    def show_rainbow(self, at: str | float | None, time: float, seconds: float, *, width: float = RAINBOW_WIDTH, opacity: float = RAINBOW_OPACITY) -> StageRainbow:
        """A rainbow fading in from scene ``time`` over ``seconds`` (the ``rainbow`` action): a
        half ring standing on the horizon with its middle at ``at`` (a mark or an x; ``None``: the
        middle), ``width`` frame widths across, drawn right after the sky (behind the layers, the
        ground and everything on it) and graded by the light."""
        x = mark_x(at if at is not None else "centre", self.params.stage_marks())
        radius = width * self.frame_width / 2
        rainbow = Rainbow((x - 0.5) * self.stage_width, self._horizon_y(), radius, opacity, name="rainbow" if not self.rainbows else f"rainbow_{len(self.rainbows) + 1}")
        mark_lit(rainbow)
        stage_rainbow = StageRainbow(rainbow)
        stage_rainbow.fade(1.0, time, seconds)
        stage_rainbow.update(float(self.renderer.time))
        self.rainbows.append(stage_rainbow)
        self._put_in_sky(rainbow)
        self._watch_living()
        return stage_rainbow

    def hide_rainbows(self, time: float, seconds: float) -> None:
        """Every rainbow fades out from scene ``time`` over ``seconds`` (``rainbow`` with ``hide``)."""
        for rainbow in self.rainbows:
            rainbow.fade(0.0, time, seconds)
        if self.rainbows:
            self._watch_living()

    def _start_sky_path(self) -> None:
        """With a ``light`` action that has ``move_sun`` (outdoors), every ``sun`` and ``moon``
        prop is a :class:`SkyBody`: placed on the sky's path where the light at the start puts it
        (a tint: as by day), moved by the light changes, and the shadows cast away from it."""
        if self.params.room is not None or not any(use.options.move_sun for use in self.action_uses("light")):
            return
        start = self.params.light if isinstance(self.params.light, str) else "day"
        for prop in self.props.values():
            if prop.kind in SKY_BODIES and prop.held_by is None:
                body = SkyBody(prop, prop.kind, place_for(prop.kind, start), self._sky_place)
                prop.stage_depth = 1.0   # it moves into the sky, behind everything (entrance)
                self.sky_bodies.append(body)
        self._sky_step(float(self.renderer.time))

    def _sky_place(self, x_share: float, height: float) -> tuple[float, float]:
        """Where a sky body's middle is for an x share of the stage and a height on the sky's path
        (0 on the horizon, 1 at the top of the arc, :func:`path_point`)."""
        horizon = self._horizon_y()
        room = self.frame_height / 2 - horizon - SKY_TOP_ROOM * self.frame_height
        return -self.stage_width / 2 + x_share * self.stage_width, horizon + height * room

    def _sky_step(self, now: float) -> None:
        """The sky for scene time ``now``: the suns and moons on their path, the shadows they cast
        (from the one that shows most, the sun on a tie), and the lightning bolt."""
        if self.sky_bodies:
            for body in self.sky_bodies:
                body.update(now)
            body = max(self.sky_bodies, key=lambda b: (b.shown, b.kind == "sun"))
            stretch, side = shadow_cast(body.share if body.shown > 0 else None)
            for group in self.shadows:
                group.set_cast(stretch * body.shown, side)
        self._show_bolt(now)

    def get_moving_mobjects(self, *animations: Animation) -> list[Mobject]:
        """Manim's moving mobjects, or every mobject while the light changes during this
        animation (the grade then changes on every frame, so nothing can stay in the static
        image), or, while the wind may move something, everything from the first swaying prop or
        trailing character on (DESIGN.md §69.32; the set behind it stays in the static image),
        while a character walks in depth, everything from the first thing whose depth it passes
        on (its place in the draw order changes, §69.44), on a stage with water everything from
        the first boat on (the waves and the bobbing move every frame, §69.53), and the parts of the
        props that move by themselves with what is drawn over them (§69.54)."""
        moving = super().get_moving_mobjects(*animations)
        now = float(self.renderer.time)
        duration = getattr(self, "duration", None)
        end = now + (math.inf if duration is None else float(duration))
        light = getattr(self, "light", None)
        if light is not None:
            self._sky_step(now)
            light.update(now)
            if light.changing(now, end):   # (a part of a character is in its family already: not again, on top)
                known = {id(m) for m in self.get_mobject_family_members()}
                return [*self.mobjects, *(m for m in moving if id(m) not in known)]
        redrawn = self._depth_crossers(animations) if hasattr(self, "_depth_walks") else set()
        redrawn |= self._water_movers()
        blowing = getattr(self, "blowing", None)
        if blowing is not None:
            blowing.update(now)
            if blowing.moving(now, end):
                redrawn |= {id(m) for mob in blowing.mobjects() for m in mob.get_family()}
            elif not blowing.moving(now, math.inf):
                self.remove_updater(self._wind_updater)
        if redrawn:
            family = self.get_mobject_family_members()
            first = next((k for k, m in enumerate(family) if id(m) in redrawn), len(family))
            moving = list_update(family[first:], moving)
        return self._living_redrawn(moving, now, end)

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
        left = -self.stage_width / 2
        if self.is_draft:   # nothing sways or trails; balloons and blown props still drift with it (§74)
            self.blowing = StageWind(wind, [], {}, lambda x: (x - left) / self.stage_width)
            self._wind_updater = self._wind_step
            return
        lifts = {item.name: item.lift for item in self.params.items()}
        still = set(self.props) - self._movable_props() - self._posture_props()
        swaying = [
            SwayingProp(self.props[place.name], self.props[place.name].kind, place.x_fraction)
            for place in placements
            if place.kind == "prop" and place.name in still and lifts[place.name] == 0 and self.props[place.name].kind in SWAYS
        ]
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
        if not self.is_draft and not any(f is self._wind_updater for f in self.updaters):
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

    # ----- water (DESIGN.md §69.53) ----------------------------------------------------------------

    def _water(self) -> StageWater | None:
        """The stage's ``water`` (``None``: none), its waves drifting with the wind's way."""
        p = self.params
        span = p.water_span()
        if span is None or p.water is None:
            return None
        left = -self.stage_width / 2
        unit = p.size * min(self.frame_width, self.frame_height)
        color = resolve_color(p.water.color, self.theme) if p.water.color is not None else WATER_COLOR
        sign = -1.0 if wind_level(p.wind) < 0 else 1.0
        return StageWater(left + span[0] * self.stage_width, left + span[1] * self.stage_width, self.feet_y_at(0.0),
                          -self.frame_height / 2, unit, color, sign=sign)

    def _start_water(self) -> None:
        """The scene updater that moves the waves and bobs the boats on every frame (kept: Manim
        removes an updater by identity)."""
        if self.water is None:
            return
        self._water_updater = self._water_step
        self.add_updater(self._water_updater)

    def _water_step(self, dt: float) -> None:
        """Scene updater: the waves and the boats (with their riders) for the scene time now."""
        if self.water is not None:
            self.water.update(float(self.renderer.time), self._riders_of)

    def _riders_of(self, vehicle: Prop) -> list[RiderSeat]:
        """The seats of the characters riding ``vehicle`` now."""
        return [seat for seat, _ in getattr(self, "_riders", {}).values() if seat.vehicle is vehicle]

    def _water_movers(self) -> set[int]:
        """The ids of the family members the water moves on every frame: its front strip, the boats
        and their riders."""
        water = getattr(self, "water", None)
        if water is None:
            return set()
        boats = [boat for boat, _ in water.boats]
        riders = [seat.rider for boat in boats for seat in self._riders_of(boat)]
        return {id(m) for mob in [water.front, *boats, *riders] for m in mob.get_family()}

    # ----- props that move by themselves (DESIGN.md §69.54) ----------------------------------------

    def _living_names(self) -> set[str]:
        """The props that move by themselves in this scene: running clocks, and the tvs and lamps
        that are on at the start or that a ``switch_on`` names. Every other prop is drawn as before."""
        p = self.params
        patterns = [pattern for use in self.action_uses("switch_on") for pattern in use.config.targets()]
        return {
            name for name, prop in zip(p.prop_names(), p.stage_props())
            if prop.runs() or (prop.prop in SWITCHED_PROPS and (prop.on or any(fnmatchcase(name, pat) for pat in patterns)))
        }

    def _start_living(self, names: set[str]) -> None:
        """A :class:`LivingProp` per prop of ``names`` (made after the light marks the props: its
        moving parts and glow are not graded; a fire's flames and a kettle's steam lean with the
        stage's wind when it may blow), and the scene updater that shows them for the scene time on
        every frame."""
        given = dict(zip(self.params.prop_names(), self.params.stage_props()))
        movable = self._movable_props() if names else set()
        blows = wind_level(self.params.wind) != 0.0 or any(use.level() for use in self.action_uses("wind"))
        wind = self._felt_wind if blows else None
        #: the props that move by themselves, by name (DESIGN.md §69.54)
        self.living: dict[str, LivingProp] = {}
        for name in sorted(names):
            prop = given[name]
            self.living[name] = LivingProp(
                self.props[name], start=prop.clock_start() if prop.runs() else None, speed=prop.speed or 1.0, on=prop.on,
                seed=motion_seed(self.spec.id, name), movable=name in movable, wind=wind if prop.prop in ("fireplace", "kettle") else None,
            )
        #: the scene updater, kept: Manim removes an updater by identity
        self._living_updater = self._living_step
        if self.living:
            self.add_updater(self._living_updater)

    def _felt_wind(self, now: float) -> float:
        """The stage's felt wind force at scene time ``now`` (0 while calm)."""
        blowing = getattr(self, "blowing", None)
        return felt_force(blowing.wind.force(now)) if blowing is not None else 0.0

    def _living_things(self) -> list[Any]:
        """The props that move by themselves, the flocks of birds, the layers of settling snow, the
        fog and the rainbows (DESIGN.md §69.54, §69.55, §69.60, §69.61)."""
        fog = getattr(self, "fog", None)
        return [
            *getattr(self, "living", {}).values(), *getattr(self, "flocks", []), *getattr(self, "snow_layers", []), *([fog] if fog is not None else []),
            *getattr(self, "rainbows", []),
        ]

    def _living_step(self, dt: float) -> None:
        """Scene updater: every prop that moves by itself, every flock, every layer of settling
        snow, the fog and every rainbow as they are at the scene time now; it removes itself once
        only flocks that have flown away, layers that grow no more and rainbows done fading are
        left."""
        now = float(self.renderer.time)
        for live in self.living.values():
            live.update(now)
        for flock in self.flocks:
            flock.update_to(now)
        for layer in self.snow_layers:
            layer.update(now)
        fog = getattr(self, "fog", None)
        if fog is not None and fog.moves:
            fog.update(now)
        for rainbow in self.rainbows:
            rainbow.update(now)
        settled = all(layer.done(now) for layer in [*self.snow_layers, *self.rainbows]) and (fog is None or not fog.moves)
        if not self.living and all(flock.done(now) for flock in self.flocks) and settled:
            self.remove_updater(self._living_updater)

    def switch_props(self, patterns: list[str], on: bool, time: float) -> None:
        """Switch the tvs, lamps, fireplaces, kettles and phones matching ``patterns`` on (or off)
        at scene ``time`` (the ``switch_on`` / ``switch_off`` actions), with a click (foley; a fire
        lights with a burner's whoosh and goes out quietly, a phone starts ringing without one:
        its rings are :meth:`_ring_sounds`)."""
        names = [name for name in getattr(self, "living", {}) if any(fnmatchcase(name, pat) for pat in patterns)]
        for name in names:
            self.living[name].switch(on, time)
        if not names or not self._foley_on():
            return
        if any(self.living[name].kind not in ("fireplace", *(("phone",) if on else ())) for name in names):
            self.sfx("click", max(float(time), 0.0), gain=SWITCH_CLICK_GAIN)
        if on and any(self.living[name].kind == "fireplace" for name in names):
            self.sfx("burner", max(float(time), 0.0), gain=FIRE_LIGHT_GAIN, duration=FIRE_LIGHT_SECONDS)

    def knock_on(self, patterns: list[str], time: float) -> None:
        """Someone knocks on the doors matching ``patterns`` at scene ``time`` (the ``knock``
        action): a ``knock`` sound (foley, DESIGN.md §69.62), once however many doors match."""
        names = [name for name, prop in self.props.items() if prop.kind == "door" and any(fnmatchcase(name, pat) for pat in patterns)]
        if names and self._foley_on():
            self.sfx("knock", max(float(time), 0.0), gain=KNOCK_GAIN)

    def _ring_sounds(self) -> None:
        """A ``phone`` sound at each burst of rings of each phone while it rings in the scene
        (foley; DESIGN.md §69.56), once the scene has played (its end ends a ring left on)."""
        if not self._foley_on():
            return
        end = float(self.renderer.time)
        for live in getattr(self, "living", {}).values():
            if live.kind == "phone":
                for time in ring_bursts(on_spans(live.on, live.switches, end)):
                    self.sfx("phone", time, gain=PHONE_RING_GAIN)

    def _living_redrawn(self, moving: list[Mobject], start: float, end: float) -> list[Mobject]:
        """``moving`` plus what props that move by themselves and flocks change between scene
        times ``start`` and ``end`` (the hands, a picture, flames, a glow, steam, the birds) and
        every member drawn after those that overlaps them (:func:`redrawn_members`); the rest of
        the set stays in Manim's static image. In draw order."""
        changing = [live for live in self._living_things() if live.changing(start, end)]
        if not changing:
            return moving
        family = self.get_mobject_family_members()
        movers = {id(m) for live in changing for mob in live.movers() for m in mob.get_family()}
        first = next((k for k, m in enumerate(family) if id(m) in movers), None)
        if first is None:
            return moving   # not on screen yet
        drawn = {id(m) for m in moving}
        after = [m for m in family[first:] if id(m) not in movers and id(m) not in drawn]
        boxes = [_box(m) for m in after]
        regions = [live.region(start, end) for live in changing]
        kept = movers | drawn | {id(after[k]) for k in redrawn_members(boxes, regions, REDRAW_MARGIN * self.frame_height)}
        known = {id(m) for m in family}
        return [m for m in family if id(m) in kept] + [m for m in moving if id(m) not in known]

    # ----- birds and fruit (DESIGN.md §69.55) ------------------------------------------------------

    def add_flock(self, settings: Any, start: float) -> Flock:
        """A flock of birds (``settings``: count, direction, height, seconds, seed) crossing the
        stage from scene time ``start`` (the ``birds`` param and action), drawn right after the sky
        (behind the layers, the ground, the props and the characters) and graded by the light."""
        left, right = self.camera_bounds()[:2]
        seed = settings.seed if settings.seed is not None else motion_seed(self.spec.id, "birds", len(self.flocks))
        plan = flock_plan(
            float(start), seconds=settings.seconds, direction=1.0 if settings.direction == "right" else -1.0, left=left, right=right,
            y=(settings.height - 0.5) * self.frame_height, span=BIRD_SPAN * self.frame_height, count=settings.count, seed=seed,
            frame_width=self.frame_width,
        )
        flock = Flock(plan, name="birds" if not self.flocks else f"birds_{len(self.flocks) + 1}")
        flock.update_to(float(self.renderer.time))
        mark_lit(flock)
        self.flocks.append(flock)
        self._put_in_sky(flock)
        if not any(f is self._living_updater for f in self.updaters):
            self.add_updater(self._living_updater)
        return flock

    def _put_in_sky(self, mobject: Mobject) -> None:
        """Put ``mobject`` right after the sky (the background and the stars): into the backdrop
        while it has not come on screen yet (it comes in with it), else into the scene."""
        sky_end = getattr(self, "_sky_end", 0)
        on_screen = any(m in self.mobjects for m in [*self._backdrop, *self.cast.values(), *self.props.values()])
        if not on_screen:
            self._backdrop.insert(sky_end, mobject)
            self._sky_end = sky_end + 1
            return
        sky = {id(m) for m in self._backdrop[:sky_end]}
        shown = [k for k, m in enumerate(self.mobjects) if id(m) in sky]
        self.mobjects.insert(max(shown) + 1 if shown else 0, mobject)

    def _fruit_left(self, tree: str) -> list[int]:
        """The fruits still on the tree ``tree`` (indices of :data:`FRUIT_SPOTS`)."""
        if not hasattr(self, "_fallen"):
            #: each tree's fallen fruits (DESIGN.md §69.55)
            self._fallen: dict[str, set[int]] = {}
        return [k for k in range(len(FRUIT_SPOTS)) if k not in self._fallen.get(tree, set())]

    def _fruit_members(self, tree: str, index: int) -> list[VMobject]:
        """The members of the tree ``tree``'s fruit ``index``, in drawing order."""
        return [m for m in self.props[tree].get_family() if getattr(m, FRUIT_INDEX, None) == index]

    def _fruit_drop(self, tree: str, onto: str | None) -> dict[str, Any] | None:
        """How a fruit of ``tree`` drops (``onto``: the character it falls on): which fruit, where
        it hits and ends (its middle), the bounce and the timing; ``None``: no fruit left. A fruit
        aimed at a character falls on its head when one hangs above it, else beside it."""
        left = self._fruit_left(tree)
        if not left:
            return None
        fh = self.frame_height
        figure = self.cast.get(onto) if onto is not None else None
        middles = {k: self._fruit_middle(tree, k) for k in left}
        xs = [middles[k][0] if k in middles else 0.0 for k in range(len(FRUIT_SPOTS))]
        head = head_box(figure) if figure is not None else None
        above = [k for k in left if head is not None and middles[k][1] > head[3] + middles[k][2]]
        if head is not None and above:
            x = (head[0] + head[2]) / 2
            index = fruit_to_drop(above, near_x=x, xs=xs)
            mx, my, radius = middles[index]
            side = 1.0 if mx >= float(figure.feet()[0]) else -1.0
            impact = (x, head[3] + radius)
            end = (float(figure.feet()[0]) + side * HEAD_ASIDE * figure.character_height, float(figure.feet()[1]) + radius)
            bounce = HEAD_BOUNCE * fh
        else:
            index = fruit_to_drop(left, near_x=float(figure.feet()[0]) if figure is not None else None, xs=xs)
            mx, my, radius = middles[index]
            ground = self.grounds.get(tree, float(self.props[tree].feet()[1]))
            side = 1.0 if mx >= float(self.props[tree].feet()[0]) else -1.0
            impact = (mx, ground + radius)
            end = (mx + side * GROUND_ASIDE * fh, ground + radius)
            bounce = GROUND_BOUNCE * fh
        timing = drop_timing(max(my - impact[1], 0.0) / fh, bounce / fh)
        return {"index": index, "impact": impact, "end": end, "bounce": bounce, "timing": timing, "hit": head is not None and bool(above)}

    def _fruit_middle(self, tree: str, index: int) -> tuple[float, float, float]:
        """Fruit ``index`` of ``tree`` on screen now: the middle of its skin (x, y; what a
        :class:`PropMove` moves of a :class:`FallenFruit`) and its radius."""
        skin = fruit_skin(self._fruit_members(tree, index))
        middle = skin.get_center()
        return float(middle[0]), float(middle[1]), float(skin.width) / 2

    def fruit_drop_seconds(self, tree: str, onto: str | None) -> float | None:
        """How long a ``drop_fruit`` of ``tree`` takes (``None``: no fruit left)."""
        plan = self._fruit_drop(tree, onto)
        return None if plan is None else plan["timing"].seconds

    def drop_fruit(self, tree: str, onto: str | None = None) -> list[Animation]:
        """A fruit of the tree ``tree`` falls (the ``drop_fruit`` action): the tree's fruit is
        hidden and a :class:`FallenFruit` copy of it falls, hits the ground (or ``onto``'s head,
        which then sees stars), bounces and lies still, drawn in front of the tree (and of the
        character). The thud is foley (its ``lands_at``)."""
        plan = self._fruit_drop(tree, onto)
        if plan is None:
            return []
        index = plan["index"]
        self._fallen.setdefault(tree, set()).add(index)
        members = self._fruit_members(tree, index)
        fruit = FallenFruit(members, fruit_of=tree, index=index, opacities=[(float(m.get_fill_opacity()), float(m.get_stroke_opacity())) for m in members])
        for member in members:
            member.set_fill(opacity=0.0)
            member.set_stroke(opacity=0.0)
        figure = self.cast.get(onto) if onto is not None else None
        behind = [m for m in (self.props[tree], figure if plan["hit"] else None) if m is not None and m in self.mobjects]
        at = max((self.mobjects.index(m) for m in behind), default=len(self.mobjects) - 1)
        self.mobjects.insert(at + 1, fruit)
        stars = None
        if plan["hit"] and figure is not None:
            stars = hit_stars(figure, color=self.theme.color("highlight"))
            self._add_motion_effect(stars, figure, behind=False)
        return [FruitDrop(fruit, impact=plan["impact"], end=plan["end"], timing=plan["timing"], bounce=plan["bounce"], stars=stars)]

    def _shadows(self, placements: list[StagePlacement]) -> tuple[StageShadows | None, StageShadows | None]:
        """The shadows (``shadows: true``): of the props on the ground that stay put (drawn
        with the backdrop, so they stay in Manim's static image), and of the characters and the
        props an action may move (placed under them on every frame). None in a draft (§74)."""
        if not self.params.shadows or self.is_draft:
            return None, None
        lifts = {item.name: item.lift + item.hang for item in self.params.items()}
        movable = self._movable_props()
        doors = set(self.params.door_names())
        still: list[ShadowCaster] = []
        moving: list[ShadowCaster] = []
        for place_at in placements:
            name = place_at.name
            if place_at.kind == "prop":
                if lifts[name] > 0 or name in doors or self.props[name].kind in (*FLAT_PROPS, *WATER_VEHICLES):
                    continue  # hangs in the sky or on a wall, is part of the room's wall, lies flat or floats
                prop = self.props[name]
                widths = {shape: prop.shape_width(shape) * PROP_SHADOW_WIDTH for shape in prop.shapes}
                caster = ShadowCaster(prop, self.grounds[name], prop.width * PROP_SHADOW_WIDTH, prop.height, widths, grows=prop.is_vehicle)
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
        thrown), moved by ``keyframes`` / ``move_along``, opened or closed, blown away; the
        vehicles of a scene with a ``ride_to`` (DESIGN.md §69.52)."""
        moved = {use.options.to for kind in ("pick_up", "hold") for use in self.action_uses(kind)}
        if self.action_uses("ride_to"):
            moved |= {name for name, prop in self.props.items() if prop.is_vehicle}
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

    def _prop(self, name: str, prop: StageProp, height: float, *, living: bool = False) -> Prop:
        """The prop ``name`` drawn ``height`` units tall, its feet at the origin; outlines as wide
        as a character's at its depth; ``living``: with the parts it moves by itself (§69.54)."""
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
            living=living, fruit=prop.fruit,
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
        #: how many of the backdrop's first members are its sky (a flock flies right after them)
        self._sky_end = 0
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
        self._sky_end = len(parts)
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


def _moving_block(scene: Any, mover: Mobject) -> list[Mobject]:
    """``mover`` with what moves with it in ``scene``'s draw order: a walker and the props right
    after it (or right before it: an open umbrella, balloons) that it holds; a vehicle, its riders
    and the props they hold (DESIGN.md §69.52)."""
    at = next((k for k, m in enumerate(scene.mobjects) if m is mover), None)
    if at is None:
        return []
    if isinstance(mover, Character):
        start, end = at, at + 1
        while start > 0 and getattr(scene.mobjects[start - 1], "held_by", None) == mover.name:
            start -= 1
        while end < len(scene.mobjects) and getattr(scene.mobjects[end], "held_by", None) == mover.name:
            end += 1
        return scene.mobjects[start:end]
    riders = {name for name, figure in scene.cast.items() if getattr(figure, "riding", None) == getattr(mover, "name", None)}
    return [m for m in scene.mobjects if m is mover or (isinstance(m, Character) and m.name in riders) or getattr(m, "held_by", None) in riders]


def _box(mob: Mobject) -> tuple[float, float, float, float] | None:
    """The box of ``mob``'s own points (left, bottom, right, top; ``None``: it has none)."""
    points = mob.points
    if len(points) == 0:
        return None
    return float(points[:, 0].min()), float(points[:, 1].min()), float(points[:, 0].max()), float(points[:, 1].max())


def _played(action: str, options: Any, anim: Animation, start: float, seconds: float) -> PlayedAction:
    """One animation of a built-in ``action`` (its ``options``) as it plays from scene time
    ``start`` for ``seconds``, for foley and motion effects."""
    if isinstance(anim, Walk):
        through_door = anim.fade_in > 0 or anim.fade_out > 0   # a fade in a doorway (§69.42)
        return PlayedAction(action, start, seconds, heights=anim.heights, phases=anim.phases, step_length=anim.step_length, rolls=anim.gait.rolls,
                            through_door=through_door, opens_door=anim.opens_door)
    if isinstance(anim, PropReshape):
        return PlayedAction(action, start, seconds, prop=getattr(anim.mobject, "kind", None))
    if isinstance(anim, WaterFlow):
        return PlayedAction(action, start, seconds, pours=True)
    if isinstance(anim, Ride):
        lands = 1.0 if anim.flies and anim.course.land else None   # a balloon or a toy rocket touching down (§69.53)
        return PlayedAction(action, start, seconds, heights=anim.heights, phases=anim.phases, vehicle=anim.kind, lands=lands)
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
