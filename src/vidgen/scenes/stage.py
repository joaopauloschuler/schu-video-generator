"""``stage``: a cartoon set (a picture, a generated picture or a colour / gradient) with a ground
line, named marks and the video's characters standing on them (DESIGN.md §69.6), parallax
layers that move by their factor when the camera moves (§69.7), props (§69.8), particles
(§69.9), its light and shadows (§69.31) and its wind (§69.32)."""

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
    facing: Literal["auto", "right", "left"] = "auto"
    """Which way it looks; auto: towards the middle of the stage (right on the left half, left on the right half)."""
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
    """A built-in prop: table, chair, tree, bush, house, door, lamp, sign, box, ball, cloud, sun, moon, rock, plant, laptop, cup, basket, umbrella, napkin."""
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
    """An umbrella: true starts it open (the open / close actions change it later)."""

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


class StageParticles(ParticleSettings, SceneParams):
    """Particles over the whole scene (rain, snow...). A plain string is the kind."""

    also_accepts: ClassVar[tuple[type, ...]] = (str,)

    kind: ParticleKindName
    """rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks (wind lines, seen only in wind)."""

    @model_validator(mode="before")
    @classmethod
    def _kind_only(cls, data: Any) -> Any:
        return {"kind": data} if isinstance(data, str) else data

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
    mark, out of a hand too.

    A beat is spoken by the characters whose voice says it (their mouths move with it), or by
    the ones its ``say`` action names; the acting actions (``say``, ``look_at``, ``turn``,
    ``emote``, ``pose``, ``react``) change the characters during the beats, and the moving ones
    (``walk_to``, ``enter``, ``exit``, ``gesture``, ``jump``) move them. A character with an
    ``enter`` action waits off stage until it enters. Walks, entrances, exits, jumps and a
    surprised face make their own sounds (foley; ``foley: false`` turns them off). With
    ``auto_direct``, listeners look at whoever speaks and react after lines on their own. A
    beat's ``shot:`` frames characters for that beat (``closeup kit``, ``two_shot``,
    ``over_shoulder kit pip``...): a cut, and back at the next beat without one. On a stage wider
    than the frame (a 9:16 variant crops the landscape stage) the camera keeps whoever speaks
    in view (``reframe``).

    The ``keyframes`` and ``move_along`` actions move a character, a prop or a character's part
    by keys or along a path. Characters handle props with ``pick_up``, ``hold``, ``put_down``,
    ``give`` and ``throw``: a held prop goes along with its holder's hand (they crouch for a low
    one). They sit on a chair, a rock or a box with ``sit_on``, lean on a tree, a door or a sign
    with ``lean_on``, and get up with ``stand_up``.

    Action targets: each character and each prop by its name; each part of a character as
    ``<character>.<part>`` (``kit.arm_left``).
    """

    outro = 0.5
    target_patterns = ("<character>", "<prop>", "<character>.<part>")
    uses_cartoon_style = True
    #: Storyboard stills also show these actions half-way through (DESIGN.md §69.16).
    mid_still_actions = frozenset({
        "walk_to", "enter", "exit", "gesture", "jump", "keyframes", "move_along", "pick_up", "put_down", "give", "throw",
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
        """Own marks: name -> x from 0 (left edge) to 1 (right edge), besides far_left 0.1, left 0.25, centre 0.5, right 0.75, far_right 0.9."""
        characters: list[StageCharacter] = []
        """The characters on the stage: a name, or {name, at, depth, scale, facing, pose, expression}."""
        size: float = Field(0.45, gt=0.0, le=1.0)
        """Height of a character at depth 0, as a fraction of the frame's shorter side."""
        idle: bool = True
        """false: the characters do not breathe, sway or blink in this scene."""
        foley: bool | None = None
        """Sounds for the characters' actions (footsteps, whoosh on enter / exit, boing on jump, pop on a surprised face): false for none in this scene; default: the video's foley (on)."""
        auto_direct: AutoDirectSetting | None = None
        """Automatic directing in this scene: listeners look at whoever speaks and react after lines, speakers gesture on stressed words, short punchy lines get a close-up (true, false or {looks, reactions, gestures, closeups}); a beat's own setting wins; default: the video's (off). Actions written in a beat always win."""
        cartoon_motion: MotionSetting | None = None
        """Animation principles for the characters in this scene (anticipation, squash and stretch, overshoot and settle, follow-through): lively, calm or none; a character's own setting wins; default: the video's (lively)."""
        width: float = Field(1.0, ge=1.0, le=4.0)
        """Width of the stage in frame widths (marks and x positions are fractions of it; while it reframes in a frame narrower than 16:9, in 16:9 frame widths); wider than 1: the camera pans across it (pan, follow)."""
        camera_at: str | Annotated[float, Field(ge=0.0, le=1.0)] = "centre"
        """Where the camera looks at the start, on a stage wider than the frame: a mark or an x from 0 to 1 of the stage."""
        reframe: ReframeSetting | None = None
        """On a stage wider than the frame: speaker moves the camera to whoever speaks (easing between speakers, holding during short replies; a 9:16 frame then crops the stage laid out as wide as the 16:9 one); none: only the beats' own pan / follow / zoom / shot move it; default: the video's, else speaker when the characters do not fit in one view."""
        layers: list[StageLayer] = []
        """Parallax layers: {place: background | middle | foreground, factor, image | shapes}."""
        props: list[StageProp] = []
        """Props: a built-in prop's name, or {prop | svg, name, at, depth, scale, lift, facing, color, detail, recolor, open}."""
        particles: list[StageParticles] = []
        """Particles over the whole scene, in front of everything: a kind (rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves, streaks) or {kind, density, area, color, seed}; for one beat use the particles action."""
        light: LightSetting = "day"
        """The light on the set: day (as drawn), morning, sunset, night (dark blue, with stars on a colour background) or indoor, or {tint, strength}: a colour grade of the background, layers, props and characters (never of speech bubbles, captions or other text); the light action changes it during the scene."""
        shadows: bool = True
        """Soft shadows on the ground under the characters and the props standing on it (smaller when they jump, none under a held prop); false: none."""
        wind: WindSetting = 0.0
        """Wind from the start, in gusts: 0 calm (nothing moves) .. 1 a gale blowing to the right (negative: to the left), or calm, breeze (0.3), windy (0.6), gale (1); trees, bushes, plants, signs and lamps sway, scarves, long hair, floppy or pointy ears and hats trail (clearly from windy on), particles drift (add leaves or streaks to show it more); the wind action changes it during the scene, blow_away blows a light prop away."""

        @model_validator(mode="after")
        def _check(self) -> SceneParams:
            if self.image is not None and self.generate is not None:
                raise ValueError("give either image (a file) or generate (a picture to generate), not both")
            if (self.image is not None or self.generate is not None) and self.background is not None:
                raise ValueError("background (a colour) is for stages without a picture; remove it or the image / generate")
            if isinstance(self.background, list) and len(self.background) < 2:
                raise ValueError("a background gradient needs at least two colours (or give one colour)")
            seen: set[str] = set()
            for k, member in enumerate(self.characters):
                if member.name in seen:
                    raise ValueError(f"character '{member.name}' is on the stage twice (characters[{k}])")
                seen.add(member.name)
                try:
                    mark_x(member.at, self.marks)
                except ValueError as exc:
                    raise ValueError(f"characters[{k}].at: {exc}") from None
            try:
                mark_x(self.camera_at, self.marks)
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
                    mark_x(prop.at, self.marks)
                except ValueError as exc:
                    raise ValueError(f"props[{k}].at: {exc}") from None
            return self

        def prop_names(self) -> list[str]:
            """Each prop's name: its own, else its default name numbered from the second prop of
            that name on (``tree``, ``tree_2``)."""
            return numbered_names([(prop.name, prop.default_name()) for prop in self.props])

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
            props = [
                StageItem(name, "prop", prop.at, prop.depth, prop.height_factor(), prop.resolved_lift())
                for prop, name in zip(self.props, self.prop_names())
            ]
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
        on a surprised face
        (:func:`foley_cues`); none with ``foley: false`` (the stage's, else the video's). A
        project file with a sound's name plays as it is (without the cue's params)."""
        on = self.params.foley if self.params.foley is not None else self.project.config.foley
        if not on:
            return
        expression = options.to if action == "emote" else getattr(options, "expression", None) if action == "react" else None
        for anim in animations:
            if isinstance(anim, Walk):
                played = PlayedAction(action, start, seconds, heights=anim.heights, phases=anim.phases)
            elif isinstance(anim, Jump):
                played = PlayedAction(action, start, seconds, phases=anim.phases)
            elif isinstance(anim, PropMove):
                played = PlayedAction(action, start, seconds, lands=anim.lands_at)
            else:
                played = PlayedAction(action, start, seconds, expression=expression)
            for cue in foley_cues(played):
                params = {} if self.sounds.file(cue.sound) is not None else cue.params
                self.sfx(cue.sound, max(cue.time, 0.0), gain=cue.gain, align=cue.align, **params)

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
        """A mark of the stage (its own too) or an x from 0 to 1."""
        return mark_x(place, params.marks)

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
        start_x = (mark_x(p.camera_at, p.marks) - 0.5) * self.stage_width
        frame.move_to([*view_center_within(self.camera_bounds(), (start_x, 0.0), frame.width, frame.height), 0.0])
        self._start_light()
        layers = self._layers()
        #: the layers by name, in the order given (DESIGN.md §69.7)
        self.layers: dict[str, Mobject] = dict(zip(p.layer_names(), layers))
        behind = [m for layer, m in zip(p.layers, layers) if layer.place != "foreground"]
        in_front = [m for layer, m in zip(p.layers, layers) if layer.place == "foreground"]
        placements = stage_layout(
            p.items(),
            marks=p.marks,
            ground=p.ground,
            size=p.size,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            stage_width=self.stage_width,
        )
        heads = [place.feet[1] + place.height for place in placements if place.kind == "character"]
        backdrop = self._backdrop(behind, max(heads, default=None))
        members = {m.name: m for m in p.characters}
        props = dict(zip(p.prop_names(), p.props))
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
                self.props[place_at.name] = item
                on_stage.append((place_at.name, item))
                continue
            member = members[place_at.name]
            facing = facing_towards_centre(place_at.x_fraction) if member.facing == "auto" else member.facing
            figure = character(member.name, height=place_at.height, facing=facing, motion=p.cartoon_motion)
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
        # the light grades the set, not the stars, shadows, bubbles or text (DESIGN.md §69.31)
        mark_lit(*[m for m in backdrop if not isinstance(m, StarField)], *in_front, *(mob for _, mob in on_stage))
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
        self.shadows: list[StageShadows] = []
        #: the scene updater while the light changes, kept: Manim removes an updater by identity,
        #: and each ``self._light_step`` is a new bound method
        self._light_updater = self._light_step

    def change_light(self, setting: str | CustomLight, start: float, seconds: float) -> None:
        """Fade the light to ``setting`` (a preset or a tint) from scene time ``start`` over
        ``seconds`` (the ``light`` action); everything is redrawn on every frame meanwhile."""
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
        """The stars' brightness and the shadows' darkness for ``grade``."""
        if self.stars is not None:
            self.stars.set_level(grade.stars)
        for group in self.shadows:
            group.set_strength(grade.shadow)

    def get_moving_mobjects(self, *animations: Animation) -> list[Mobject]:
        """Manim's moving mobjects, or every mobject while the light changes during this
        animation (the grade then changes on every frame, so nothing can stay in the static
        image), or, while the wind may move something, everything from the first swaying prop or
        trailing character on (DESIGN.md §69.32; the set behind it stays in the static image)."""
        moving = super().get_moving_mobjects(*animations)
        now = float(self.renderer.time)
        duration = getattr(self, "duration", None)
        end = now + (math.inf if duration is None else float(duration))
        light = getattr(self, "light", None)
        if light is not None:
            light.update(now)
            if light.changing(now, end):
                return [*self.mobjects, *(m for m in moving if m not in self.mobjects)]
        blowing = getattr(self, "blowing", None)
        if blowing is None:
            return moving
        blowing.update(now)
        if not blowing.moving(now, end):
            if not blowing.moving(now, math.inf):
                self.remove_updater(self._wind_updater)
            return moving
        family = self.get_mobject_family_members()
        blown = {id(m) for mob in blowing.mobjects() for m in mob.get_family()}
        first = next((k for k, m in enumerate(family) if id(m) in blown), len(family))
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
        lifts = {item.name: item.lift for item in self.params.items()}
        movable = self._movable_props()
        still: list[ShadowCaster] = []
        moving: list[ShadowCaster] = []
        for place_at in placements:
            name = place_at.name
            if place_at.kind == "prop":
                if lifts[name] > 0:
                    continue  # hangs in the sky
                prop = self.props[name]
                widths = {shape: prop.shape_width(shape) * PROP_SHADOW_WIDTH for shape in prop.shapes}
                caster = ShadowCaster(prop, self.grounds[name], prop.width * PROP_SHADOW_WIDTH, prop.height, widths)
                (moving if name in movable else still).append(caster)
            else:
                figure = self.cast[name]
                moving.append(ShadowCaster(figure, self.grounds[name], SHADOW_WIDTH * figure.standing_height, figure.standing_height))
        strength = self.base_light.shadow
        groups = [StageShadows(casters, strength) if casters else None for casters in (still, moving)]
        if groups[1] is not None:
            groups[1].add_updater(lambda m: m.follow())
        self.shadows = [g for g in groups if g is not None]
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
