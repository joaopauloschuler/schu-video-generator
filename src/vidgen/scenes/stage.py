"""``stage``: a cartoon set (a picture, a generated picture or a colour / gradient) with a ground
line, named marks and the video's characters standing on them (DESIGN.md §69.6), parallax
layers that move by their factor when the camera moves (§69.7), props (§69.8) and particles
(§69.9)."""

import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
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
    """A built-in prop: table, chair, tree, bush, house, door, lamp, sign, box, ball, cloud, sun, moon, rock, plant, laptop, cup."""
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
        return self

    def default_name(self) -> str:
        """The prop's name (``tree``), or the SVG's file name made an identifier (``old_well``)."""
        if self.prop is not None:
            return self.prop
        stem = re.sub(r"[^A-Za-z0-9_]+", "_", PurePosixPath(self.svg or "").stem).strip("_")
        return stem or "prop"

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
    """rain, snow, sparkles, dust, confetti, smoke or bubbles."""

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
    ``particles`` (rain, snow, confetti...) move over the whole scene.

    A beat is spoken by the characters whose voice says it (their mouths move with it), or by
    the ones its ``say`` action names; the acting actions (``say``, ``look_at``, ``turn``,
    ``emote``, ``pose``, ``react``) change the characters during the beats, and the moving ones
    (``walk_to``, ``enter``, ``exit``, ``gesture``, ``jump``) move them. A character with an
    ``enter`` action waits off stage until it enters. Walks, entrances, exits, jumps and a
    surprised face make their own sounds (foley; ``foley: false`` turns them off). With
    ``auto_direct``, listeners look at whoever speaks and react after lines on their own.

    The ``keyframes`` and ``move_along`` actions move a character, a prop or a character's part
    by keys or along a path.

    Action targets: each character and each prop by its name; each part of a character as
    ``<character>.<part>`` (``kit.arm_left``).
    """

    outro = 0.5
    target_patterns = ("<character>", "<prop>", "<character>.<part>")
    uses_cartoon_style = True
    #: Storyboard stills also show these actions half-way through (DESIGN.md §69.16).
    mid_still_actions = frozenset({"walk_to", "enter", "exit", "gesture", "jump", "keyframes", "move_along"})

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
        """Automatic directing in this scene: listeners look at whoever speaks and react after lines (true, false or {looks, reactions, gestures, closeups}); a beat's own setting wins; default: the video's (off). Actions written in a beat always win."""
        cartoon_motion: MotionSetting | None = None
        """Animation principles for the characters in this scene (anticipation, squash and stretch, overshoot and settle, follow-through): lively, calm or none; a character's own setting wins; default: the video's (lively)."""
        width: float = Field(1.0, ge=1.0, le=4.0)
        """Width of the stage in frame widths (marks and x positions are fractions of it); wider than 1: the camera pans across it (pan, follow)."""
        camera_at: str | Annotated[float, Field(ge=0.0, le=1.0)] = "centre"
        """Where the camera looks at the start, on a stage wider than the frame: a mark or an x from 0 to 1 of the stage."""
        layers: list[StageLayer] = []
        """Parallax layers: {place: background | middle | foreground, factor, image | shapes}."""
        props: list[StageProp] = []
        """Props: a built-in prop's name, or {prop | svg, name, at, depth, scale, lift, facing, color, detail, recolor}."""
        particles: list[StageParticles] = []
        """Particles over the whole scene, in front of everything: a kind (rain, snow, sparkles, dust, confetti, smoke, bubbles) or {kind, density, area, color, seed}; for one beat use the particles action."""

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
            names: list[str] = []
            count: dict[str, int] = {}
            for prop in self.props:
                if prop.name is not None:
                    names.append(prop.name)
                    continue
                base = prop.default_name()
                count[base] = count.get(base, 0) + 1
                names.append(base + (f"_{count[base]}" if count[base] > 1 else ""))
            return names

        def layer_names(self) -> list[str]:
            """Each layer's name: its own, else ``<place>_layer`` numbered from the second
            unnamed layer of a place on (``middle_layer``, ``middle_layer_2``)."""
            names: list[str] = []
            count: dict[str, int] = {}
            for layer in self.layers:
                if layer.name is not None:
                    names.append(layer.name)
                    continue
                count[layer.place] = count.get(layer.place, 0) + 1
                n = count[layer.place]
                names.append(f"{layer.place}_layer" + (f"_{n}" if n > 1 else ""))
            return names

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
        speaks, the speaker at the one it talks to, and listeners react after lines
        (:func:`stage_directions`, DESIGN.md §69.23)."""
        return stage_directions(project, spec, [c.name for c in params.characters], params.auto_direct)

    @contextmanager
    def narrate(self, beat: Any) -> Iterator[float]:
        """Narrate a beat; the characters on the stage whose voice says it speak (lip sync from
        the beat's start to its end), unless the beat has a ``say`` action, which picks who
        speaks (DESIGN.md §69.11)."""
        b = self.beat(beat)
        voiced = [] if "say" in self.beat_action_names(b) else speaking_characters(self.project.config, beat_voice(self.spec, b), self.cast)
        speakers: list[tuple[Character, Any]] = []
        with super().narrate(b) as d:
            for name in voiced:
                self.speak(self.cast[name])
                speakers.append((self.cast[name], self.cast[name].lip_sync_track))
            yield d
        for figure, track in speakers:
            if figure.lip_sync_track is track:  # not taken over by a later lip sync
                figure.stop_lip_sync()

    def action_foley(self, action: str, options: Any, animations: Any, start: float, seconds: float) -> None:
        """The sounds of a character's action as it plays (DESIGN.md §69.19): footsteps on
        walks, a whoosh on enter / exit, a boing on jump, a pop on a surprised face
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
            else:
                played = PlayedAction(action, start, seconds, expression=expression)
            for cue in foley_cues(played):
                params = {} if self.sounds.file(cue.sound) is not None else cue.params
                self.sfx(cue.sound, max(cue.time, 0.0), gain=cue.gain, align=cue.align, **params)

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
        """The stage's width in Manim units."""
        return self.params.width * self.frame_width

    def construct(self) -> None:
        p = self.params
        frame = self.camera.frame
        start_x = (mark_x(p.camera_at, p.marks) - 0.5) * self.stage_width
        frame.move_to([*view_center_within(self.camera_bounds(), (start_x, 0.0), frame.width, frame.height), 0.0])
        layers = self._layers()
        #: the layers by name, in the order given (DESIGN.md §69.7)
        self.layers: dict[str, Mobject] = dict(zip(p.layer_names(), layers))
        behind = [m for layer, m in zip(p.layers, layers) if layer.place != "foreground"]
        in_front = [m for layer, m in zip(p.layers, layers) if layer.place == "foreground"]
        backdrop = self._backdrop(behind)
        placements = stage_layout(
            p.items(),
            marks=p.marks,
            ground=p.ground,
            size=p.size,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            stage_width=self.stage_width,
        )
        members = {m.name: m for m in p.characters}
        props = dict(zip(p.prop_names(), p.props))
        # the characters and the props on the stage by name, back to front (DESIGN.md §69.6, §69.8)
        self.cast: dict[str, Character] = {}
        self.props: dict[str, Prop] = {}
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
        # register back to front, so the fade-ins add them (and draw them) in that order
        targets = [self.target(name, mob) for name, mob in on_stage]
        for whole in targets:  # parts come on screen with their character (§69.14)
            if isinstance(whole.mobject, Character):
                for part in whole.mobject.parts:
                    self.target(f"{whole.name}.{part}", whole.mobject.parts[part], entrance=lambda t=whole: self.entrance(t))

        def entrance() -> list:
            return [FadeIn(part) for part in backdrop] + [a for t in targets for a in self.entrance(t)] + [FadeIn(m) for m in in_front]

        #: the particle fields over the stage, in the order given (DESIGN.md §69.9)
        self.particles: list[ParticleField] = [particle_field(self, item.kind, item) for item in p.particles]
        self.add(*self.particles)
        self.reveal([entrance], fraction=0.6, cap=1.0)
        self.finish()

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
            facing=prop.facing, character_height=height / prop.height_factor(),
        )

    def _backdrop(self, layers: list[Mobject]) -> list[Mobject]:
        """The set behind the characters, back to front: the picture (cover) or the colour /
        gradient (named ``background``), the background and middle ``layers``, then the ground
        band (``ground``). Empty when the stage shows the theme's background, no layers and no
        ground band."""
        p = self.params
        fw, fh = self.stage_width, self.frame_height
        parts: list[Mobject] = []
        if p.has_picture():
            parts.append(self._picture())
        elif p.background is not None:
            colors = p.background if isinstance(p.background, list) else [p.background]
            sky = Rectangle(width=fw, height=fh, stroke_width=0)
            sky.set_fill([resolve_color(c, self.theme) for c in colors], opacity=1.0)
            sky.set_sheen_direction(DOWN)  # a gradient runs from the first colour at the top
            sky.name = "background"
            parts.append(sky)
        parts += layers
        ground_color = p.ground_color
        if ground_color is None and not p.has_picture():
            ground_color = DEFAULT_GROUND_COLOR
        top = ground_top(p.ground, p.items())  # up to the deepest thing standing on it (§69.6)
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
