"""The camera actions of the ``3d`` scene type (Phase AI, Step 299, DESIGN §114.8):
``camera_orbit``, ``camera_dolly``, ``camera_fly_to``, ``camera_look_at`` and ``camera_move``.

They are beat actions, so ``at`` (a fraction of the beat or a word it says, ``"@tower"``) and
``run_time`` time them like any action; but the 3D frames are drawn before the scene plays, so
they draw nothing when they fall due: the scene reads their times (``action_times``) and turns
them into camera moves of its scene description. A move lasts ``run_time`` seconds (default: to
the end of its beat) and may run on into the next beats; the next camera action stops it.
Their ``target`` is an object id of the scene (not a Manim target), checked with did-you-mean.
"""

from typing import Any, ClassVar, Literal

from vidgen.api import *

Point = tuple[float, float, float]


class _CameraOptions(ActionOptions):
    easing: Literal["smooth", "linear"] = "smooth"
    """How the move starts and ends: smooth (eases in and out) or linear (constant speed)."""


class _CameraAction(Action):
    """A camera move of a ``3d`` scene, planned by the scene before it plays."""

    Options: ClassVar[type[ActionOptions]] = _CameraOptions
    animates = False
    needs_visible = False
    scene_targets = False
    needs_target = False
    run_time = 2.0
    #: The :class:`CameraMove` kind.
    kind: ClassVar[str] = ""
    #: Whether the action takes an object id as its target: "no", "may" or "must".
    takes_target: ClassVar[str] = "no"

    @property
    def name(self) -> str:
        return f"camera_{self.kind}"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not getattr(scene_cls, "three_d_actions", False):
            return [("action", f"{self.name} moves the camera of a 3D scene (type: 3d)")]
        targets = self.config.targets()
        if self.takes_target == "no" and targets:
            return [("target", f"{self.name} takes no target (write `- action: {self.name}` with its options)")]
        if self.takes_target == "must" and not targets:
            return [("target", f"{self.name} needs the id of an object ({self.name}: <id>)")]
        if len(targets) > 1:
            return [("target", f"{self.name} takes one object, got {len(targets)}")]
        ids = params.object_ids()
        refs = [("target", t) for t in targets] + [(key, v) for key, v in self.id_options() if isinstance(v, str)]
        return [(key, f"no object {ref!r}{did_you_mean(ref, ids)} (objects: {', '.join(ids) or 'none'})") for key, ref in refs if ref not in ids]

    def id_options(self) -> list[tuple[str, Any]]:
        """Options that may name an object (checked against the scene's ids)."""
        return []

    @property
    def target(self) -> str | None:
        targets = self.config.targets()
        return targets[0] if targets else None

    def move(self, start: float, end: float) -> CameraMove:
        """This use as a camera move from ``start`` to ``end`` (seconds of the scene's clock)."""
        return CameraMove(self.kind, start, end, self.options.easing, target=self.target, **self.move_fields())

    def move_fields(self) -> dict[str, Any]:
        return {}

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Nothing at the cue: the scene drew its frames with this move before it played."""


@action("camera_orbit")
class CameraOrbit(_CameraAction):
    """Circle the camera around an object (``camera_orbit: tower``), a point (``around``) or the
    point it looks at: ``degrees`` around the vertical axis (positive: counter-clockwise seen
    from above, the camera moving to its right), rising by ``up``."""

    kind = "orbit"
    takes_target = "may"

    class Options(_CameraOptions):
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

    class Options(_CameraOptions):
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

    class Options(_CameraOptions):
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

    class Options(_CameraOptions):
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

    class Options(_CameraOptions):
        to: Point
        """[x, y, z] where the camera ends."""
        look_at: Point | str | None = None
        """What it looks at when it gets there: an object id or [x, y, z] (default: what it looks at now)."""

    def id_options(self) -> list[tuple[str, Any]]:
        return [("look_at", self.options.look_at)]

    def move_fields(self) -> dict[str, Any]:
        return {"point": self.options.to, "look_at": self.options.look_at}
