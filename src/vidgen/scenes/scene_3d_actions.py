"""The actions of the ``3d`` scene type: the camera actions (Phase AI, Step 299, DESIGN §114.8)
``camera_orbit``, ``camera_dolly``, ``camera_fly_to``, ``camera_look_at`` and ``camera_move``, and
the object actions (Step 300, §114.11) ``object_move``, ``object_path``, ``object_rotate``,
``object_spin``, ``object_scale``, ``object_show``, ``object_hide``, ``object_highlight``,
``object_walk`` and ``object_face`` (the ``camera_`` / ``object_`` prefixes keep them apart from
the stage's ``look_at``, ``turn``, ``walk_to``... and the 2D ``highlight``).

They are beat actions, so ``at`` (a fraction of the beat or a word it says, ``"@tower"``) and
``run_time`` time them like any action; but the 3D frames are drawn before the scene plays, so
they draw nothing when they fall due: the scene reads their times (``action_times``) and turns
them into camera moves of its scene description. A move lasts ``run_time`` seconds (default: to
the end of its beat) and may run on into the next beats; the next camera action stops it.
Object actions likewise become changes of the objects (``ObjectChange``); the next action of the
same kind of change on the same object stops one still running. Their ``target`` is an object id
of the scene (not a Manim target), checked with did-you-mean.
"""

from typing import Any, ClassVar, Literal

from vidgen.api import *

Point = tuple[float, float, float]


class _EasedOptions(ActionOptions):
    easing: Literal["smooth", "linear"] = "smooth"
    """How the move starts and ends: smooth (eases in and out) or linear (constant speed)."""


class _ThreeDAction(Action):
    """An action of a ``3d`` scene, planned by the scene before it plays (its target: an object id)."""

    Options: ClassVar[type[ActionOptions]] = _EasedOptions
    animates = False
    needs_visible = False
    scene_targets = False
    needs_target = False
    run_time = 2.0
    #: The change's kind (the name without its prefix).
    kind: ClassVar[str] = ""
    #: The name's prefix: ``camera_`` or ``object_``.
    prefix: ClassVar[str] = "camera_"
    #: What the action does, for the message on another scene type.
    does: ClassVar[str] = "moves the camera"
    #: Whether the action takes an object id as its target: "no", "may" or "must".
    takes_target: ClassVar[str] = "no"

    @property
    def name(self) -> str:
        return f"{self.prefix}{self.kind}"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "three_d_actions", False):
            return [("action", f"{self.name} {self.does} of a 3D scene (type: 3d)")]
        targets = self.config.targets()
        if self.takes_target == "no" and targets:
            return [("target", f"{self.name} takes no target (write `- action: {self.name}` with its options)")]
        if self.takes_target == "must" and not targets:
            return [("target", f"{self.name} needs the id of an object ({self.name}: <id>)")]
        if len(targets) > 1:
            return [("target", f"{self.name} takes one object, got {len(targets)}")]
        ids = params.object_ids()
        refs = [("target", t) for t in targets] + [(key, v) for key, v in self.id_options() if isinstance(v, str)]
        unknown = [(key, f"no object {ref!r}{did_you_mean(ref, ids)} (objects: {', '.join(ids) or 'none'})") for key, ref in refs if ref not in ids]
        return unknown or self.object_problems(params)

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        """Problems with the objects named (they exist): a walk of a box..."""
        return []

    def id_options(self) -> list[tuple[str, Any]]:
        """Options that may name an object (checked against the scene's ids)."""
        return []

    @property
    def target(self) -> str | None:
        targets = self.config.targets()
        return targets[0] if targets else None

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Nothing at the cue: the scene drew its frames with this move before it played."""


class _CameraAction(_ThreeDAction):
    """A camera move of a ``3d`` scene."""

    def move(self, start: float, end: float) -> CameraMove:
        """This use as a camera move from ``start`` to ``end`` (seconds of the scene's clock)."""
        return CameraMove(self.kind, start, end, self.options.easing, target=self.target, **self.move_fields())

    def move_fields(self) -> dict[str, Any]:
        return {}


@action("camera_orbit")
class CameraOrbit(_CameraAction):
    """Circle the camera around an object (``camera_orbit: tower``), a point (``around``) or the
    point it looks at: ``degrees`` around the vertical axis (positive: counter-clockwise seen
    from above, the camera moving to its right), rising by ``up``."""

    kind = "orbit"
    takes_target = "may"

    class Options(_EasedOptions):
        degrees: float = 90.0
        """How far around, in degrees (negative: the other way; 360: a full circle)."""
        up: float = 0.0
        """Scene units the camera rises during the orbit (negative: sinks)."""
        around: Point | None = None
        """[x, y, z] to circle instead of an object or the point looked at."""

        @field_validator("degrees")
        @classmethod
        def _turns(cls, v: float) -> float:
            if v == 0:
                raise ValueError("degrees: 0 does not move the camera")
            return v

    def problems(self) -> list[tuple[str, str]]:
        if self.config.targets() and self.options.around is not None:
            return [("around", "give an object (the target) or around, not both")]
        return []

    def move_fields(self) -> dict[str, Any]:
        o = self.options
        return {"degrees": o.degrees, "up": o.up, "point": o.around}


@action("camera_dolly")
class CameraDolly(_CameraAction):
    """Push the camera in towards the point it looks at by ``by`` scene units (negative: pull
    back): a push-in / dolly."""

    kind = "dolly"

    class Options(_EasedOptions):
        by: float
        """Scene units towards the point looked at (negative: away from it)."""

        @field_validator("by")
        @classmethod
        def _moves(cls, v: float) -> float:
            if v == 0:
                raise ValueError("by: 0 does not move the camera")
            return v

    def move_fields(self) -> dict[str, Any]:
        return {"by": self.options.by}


@action("camera_fly_to")
class CameraFlyTo(_CameraAction):
    """Fly the camera to an object (``camera_fly_to: tower``): it ends looking at its centre from
    the direction it looked before, close enough that the object fills about 60 % of the frame's
    shorter side (or at ``distance``)."""

    kind = "fly_to"
    takes_target = "must"

    class Options(_EasedOptions):
        distance: float | None = Field(None, gt=0)
        """Scene units from the object's centre (default: the object fills about 60 % of the frame)."""

    def move_fields(self) -> dict[str, Any]:
        return {"distance": self.options.distance}


@action("camera_look_at")
class CameraLookAt(_CameraAction):
    """Turn the camera (standing still) to look at an object (``camera_look_at: tower``) or a
    ``point``."""

    kind = "look_at"
    takes_target = "may"

    class Options(_EasedOptions):
        point: Point | None = None
        """[x, y, z] to look at instead of an object."""

    def problems(self) -> list[tuple[str, str]]:
        if bool(self.config.targets()) == (self.options.point is not None):
            return [("point", "give an object (camera_look_at: <id>) or point: [x, y, z], one of them")]
        return []

    def move_fields(self) -> dict[str, Any]:
        return {"point": self.options.point}


@action("camera_move")
class CameraMoveTo(_CameraAction):
    """Move the camera to stand at ``to``, looking at ``look_at`` (an object id or a point;
    default: what it looks at now)."""

    kind = "move"

    class Options(_EasedOptions):
        to: Point
        """[x, y, z] where the camera ends."""
        look_at: Point | str | None = None
        """What it looks at when it gets there: an object id or [x, y, z] (default: what it looks at now)."""

    def id_options(self) -> list[tuple[str, Any]]:
        return [("look_at", self.options.look_at)]

    def move_fields(self) -> dict[str, Any]:
        return {"point": self.options.to, "look_at": self.options.look_at}


# ----- object actions (Step 300) ------------------------------------------------------------------


class _ObjectAction(_ThreeDAction):
    """A change of one object of a ``3d`` scene (``object_move: ball``)."""

    prefix = "object_"
    does = "changes an object"
    takes_target = "must"
    #: Seconds it lasts without ``run_time``; ``None``: until the end of its beat.
    seconds: ClassVar[float | None] = None

    def end(self, due: float, beat_end: float, fps: float) -> float | None:
        """When this use ends: after ``run_time``, else after :attr:`seconds` or at the end of
        its beat (at least one frame)."""
        if self.config.run_time is not None:
            return due + self.config.run_time
        if self.seconds is not None:
            return due + self.seconds
        return max(beat_end, due + 1 / fps)

    def change(self, start: float, end: float | None, theme: Any = None) -> ObjectChange:
        """This use as an object change from ``start`` to ``end`` (seconds of the scene's clock;
        colours resolved with ``theme``)."""
        return ObjectChange(self.kind, self.target or "", start, end, self.options.easing, **self.change_fields(theme))

    def change_fields(self, theme: Any) -> dict[str, Any]:
        return {}

    def _target_object(self, params: Any) -> Any:
        return params.object(self.target) if self.target else None

    def _not_an_arrow_with_to(self, params: Any) -> list[tuple[str, str]]:
        obj = self._target_object(params)
        if obj is not None and obj.to is not None:
            return [("target", f"{self.name}: the arrow '{obj.id}' points at its `to`; it cannot be turned (move its tail with object_move)")]
        return []


def _one_of(to: Any, by: Any, name: str) -> list[tuple[str, str]]:
    if (to is None) == (by is None):
        return [("to", f"{name}: give to or by, one of them")]
    return []


@action("object_move")
class ObjectMove(_ObjectAction):
    """Move an object (``object_move: ball``) to ``to: [x, y, z]`` or by ``by: [dx, dy, dz]`` (in
    its parent's frame), by default until the end of the beat; its children move with it."""

    kind = "move"

    class Options(_EasedOptions):
        to: Point | None = None
        """[x, y, z] where its centre ends (in its parent's frame)."""
        by: Point | None = None
        """[dx, dy, dz] to move by instead."""

    def problems(self) -> list[tuple[str, str]]:
        return _one_of(self.options.to, self.options.by, self.name)

    def change_fields(self, theme: Any) -> dict[str, Any]:
        return {"point": self.options.to, "by": self.options.by}


@action("object_path")
class ObjectPath(_ObjectAction):
    """Move an object along a path through ``points`` (a smooth curve from where it is; straight
    lines with ``smooth: false``), at an even speed; ``turn: true`` turns it to face along the path."""

    kind = "path"

    class Options(_EasedOptions):
        points: list[Point] = Field(min_length=1)
        """[[x, y, z], ...] it passes through in order (in its parent's frame)."""
        smooth: bool = True
        """true: a smooth curve through the points; false: straight lines between them."""
        turn: bool = False
        """true: it turns about the vertical to face the way it goes (a stand-in's nose leads)."""

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        return self._not_an_arrow_with_to(params) if self.options.turn else []

    def change_fields(self, theme: Any) -> dict[str, Any]:
        o = self.options
        return {"points": tuple(tuple(p) for p in o.points), "smooth": o.smooth, "turn": o.turn}


@action("object_rotate")
class ObjectRotate(_ObjectAction):
    """Turn an object to ``to: [x, y, z]`` degrees or by ``by: [x, y, z]`` (XYZ order, like
    ``rotation``), by default until the end of the beat; its children turn with it."""

    kind = "rotate"

    class Options(_EasedOptions):
        to: Point | None = None
        """[x, y, z] rotation in degrees it ends at."""
        by: Point | None = None
        """[x, y, z] degrees to turn by instead."""

    def problems(self) -> list[tuple[str, str]]:
        return _one_of(self.options.to, self.options.by, self.name)

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        return self._not_an_arrow_with_to(params)

    def change_fields(self, theme: Any) -> dict[str, Any]:
        return {"angles": self.options.to, "by": self.options.by}


@action("object_spin")
class ObjectSpin(_ObjectAction):
    """Spin an object ``turns`` full turns about its ``axis`` (x, y or z; default y, the
    vertical), by default until the end of the beat (``spin:`` in its params keeps it turning
    all the time instead)."""

    kind = "spin"

    class Options(_EasedOptions):
        turns: float = 1.0
        """Full turns (negative: the other way; 0.5: half a turn)."""
        axis: Literal["x", "y", "z"] = "y"
        """The axis it turns about (its own x, y or z rotation)."""

        @field_validator("turns")
        @classmethod
        def _turns(cls, v: float) -> float:
            if v == 0:
                raise ValueError("turns: 0 does not turn it")
            return v

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        return self._not_an_arrow_with_to(params)

    def change_fields(self, theme: Any) -> dict[str, Any]:
        return {"turns": self.options.turns, "axis": self.options.axis}


@action("object_scale")
class ObjectScale(_ObjectAction):
    """Grow or shrink an object to ``to`` times its size (one number, or [x, y, z]), by default
    until the end of the beat; its children scale with it."""

    kind = "scale"

    class Options(_EasedOptions):
        to: float | Point
        """Times its size it ends at: 2 (twice), 0.5 (half), [1, 2, 1] (twice as tall)."""

        @field_validator("to")
        @classmethod
        def _positive(cls, v: float | Point) -> float | Point:
            if min(v if isinstance(v, tuple) else (v,)) <= 0:
                raise ValueError("to: a scale must be positive (object_hide takes it away)")
            return v

    def change_fields(self, theme: Any) -> dict[str, Any]:
        to = self.options.to
        return {"factor": tuple(to) if isinstance(to, tuple) else (float(to),) * 3}


class _AppearOptions(_EasedOptions):
    style: Literal["fade", "grow"] = "fade"
    """fade (its opacity) or grow (its size, from nothing / to nothing)."""


@action("object_show")
class ObjectShow(_ObjectAction):
    """Bring in an object hidden with ``visible: false`` (or by ``object_hide``): fading in, or
    growing from nothing (``style: grow``), in 0.6 s (``run_time``); its children come with it."""

    kind = "show"
    seconds = 0.6
    Options = _AppearOptions

    def change_fields(self, theme: Any) -> dict[str, Any]:
        return {"style": self.options.style}


@action("object_hide")
class ObjectHide(_ObjectAction):
    """Take an object away: fading out, or shrinking to nothing (``style: grow``), in 0.6 s
    (``run_time``); its children go with it."""

    kind = "hide"
    seconds = 0.6
    Options = _AppearOptions

    def change_fields(self, theme: Any) -> dict[str, Any]:
        return {"style": self.options.style}


@action("object_highlight")
class ObjectHighlight(_ObjectAction):
    """Make an object glow in ``color`` (default the theme's highlight) until the end of the
    beat (or for ``run_time`` seconds, into later beats); a group glows with all its children."""

    kind = "highlight"

    class Options(_EasedOptions):
        color: ThemeColor = "highlight"
        """The glow's colour (theme token or #hex)."""
        strength: float = Field(0.6, gt=0, le=1)
        """How strong the glow is (0..1; 1 is the colour itself)."""

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        obj = self._target_object(params)
        if obj is not None and obj.shape == "label":
            return [("target", f"{self.name}: a label does not glow; highlight the object it names")]
        return []

    def change_fields(self, theme: Any) -> dict[str, Any]:
        color = theme.color(self.options.color) if theme is not None else "#ffcc00"
        return {"color": hex6(color), "strength": self.options.strength}


@action("object_walk")
class ObjectWalk(_ObjectAction):
    """A stand-in turns towards ``to`` and walks there (``[x, z]`` on the ground: it keeps its
    height, or an object's id: it stops in front of it) at ``speed`` units per second (or in
    ``run_time`` seconds), bobbing a little with its steps."""

    kind = "walk"

    class Options(_EasedOptions):
        to: tuple[float, float] | str
        """[x, z] where it walks to, or the id of an object it walks up to."""
        speed: float = Field(1.4, gt=0)
        """Scene units per second (when there is no run_time)."""
        easing: Literal["smooth", "linear"] = "linear"
        """linear (an even pace; default) or smooth (it speeds up and slows down)."""

    def end(self, due: float, beat_end: float, fps: float) -> float | None:
        return due + self.config.run_time if self.config.run_time is not None else None

    def id_options(self) -> list[tuple[str, Any]]:
        return [("to", self.options.to)]

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        obj = self._target_object(params)
        if obj is None or obj.shape != "standin":
            return [("target", f"{self.name}: only a stand-in walks (shape: standin); move other objects with object_move or object_path")]
        if self.options.to == self.target:
            return [("to", f"{self.name}: '{self.target}' cannot walk to itself")]
        return []

    def change_fields(self, theme: Any) -> dict[str, Any]:
        to = self.options.to
        return {"toward": to if isinstance(to, str) else None, "point": None if isinstance(to, str) else tuple(to), "speed": self.options.speed}


@action("object_face")
class ObjectFace(_ObjectAction):
    """Turn an object (a stand-in: its nose) about the vertical to face ``to`` (an object's id,
    or [x, z] / [x, y, z]) in 0.6 s (``run_time``), the shorter way round."""

    kind = "face"
    seconds = 0.6

    class Options(_EasedOptions):
        to: tuple[float, float] | Point | str
        """The id of an object, or the point to face: [x, z] or [x, y, z]."""

    def id_options(self) -> list[tuple[str, Any]]:
        return [("to", self.options.to)]

    def object_problems(self, params: Any) -> list[tuple[str, str]]:
        if self.options.to == self.target:
            return [("to", f"{self.name}: '{self.target}' cannot face itself")]
        return self._not_an_arrow_with_to(params)

    def change_fields(self, theme: Any) -> dict[str, Any]:
        to = self.options.to
        return {"toward": to} if isinstance(to, str) else {"point": tuple(to)}
