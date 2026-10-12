"""Keyframe and motion path beat actions (DESIGN.md §69.14): ``keyframes`` and ``move_along`` on
the characters, props and character parts (``kit.arm_left``) of a ``stage``. Written against
``vidgen.api`` only, like project actions.

The values are worked out without manim in :mod:`vidgen.cartoon.keyframes` (keys, eases, paths)
and played with :class:`KeyedMotion`. Units: a character or prop's ``x`` is a mark or an x from 0
to 1 of the stage and its ``y`` the height of its feet above its ground line in frame heights; a
part's ``x`` / ``y`` is its shift in character heights.
"""

from fnmatch import fnmatchcase
from typing import Annotated, Any, Literal

from vidgen.api import *

from .acting import is_part_target
from .moving import _place_x

#: A point of a path: [x, y] (see the module's units).
PathPoint = tuple[str | float, Annotated[float, Field(ge=-2.0, le=2.0)]]
#: Largest |y| of a character or prop (frame heights), and largest |x| / |y| shift of a part
#: (character heights).
WHOLE_Y_LIMIT = 1.0
PART_SHIFT_LIMIT = 1.0


def _subject(scene: NarratedScene, target: Target) -> tuple[Mobject, str | None]:
    """What moves for ``target``: the mobject itself, or a part's character and the part's name."""
    if is_part_target(target.name):
        owner, part = target.name.split(".", 1)
        return scene.find_targets(owner)[0].mobject, part
    return target.mobject, None


def _value_problems(scene_cls: type[NarratedScene], params: Any, name: str, where: str, x: Any, y: Any) -> list[tuple[str, str]]:
    """Problems of an ``x`` / ``y`` for target ``name`` (``where``: the option's location)."""
    problems: list[tuple[str, str]] = []
    if is_part_target(name):
        if isinstance(x, str):
            problems.append((where, f"{name}: a part's x is its shift right in character heights (a number), not {x!r}"))
        for axis, value in (("x", x), ("y", y)):
            if isinstance(value, (int, float)) and abs(value) > PART_SHIFT_LIMIT:
                problems.append((where, f"{name}: a part's {axis} shift is at most {PART_SHIFT_LIMIT} character heights either way, not {value}"))
        return problems
    if x is not None:
        try:
            scene_cls.camera_place(params, x)
        except ValueError as exc:
            problems.append((where, f"{name}: x: {exc}"))
    if y is not None and abs(y) > WHOLE_Y_LIMIT:
        problems.append((where, f"{name}: y is the feet's height above the ground in frame heights, at most {WHOLE_Y_LIMIT} either way, not {y}"))
    return problems


class _Keyed(Action):
    """Moves stage characters, props and parts by channel values; ``until`` (or undoing) moves
    them back to where they were before, in a straight smooth move."""

    run_time = 1.0
    reversible = True

    def __init__(self, options: ActionOptions, config: Any) -> None:
        super().__init__(options, config)
        #: (mobject, part or None, channel values before) per moved target, for :meth:`revert`
        self.saved: list[tuple[Mobject, str | None, dict[str, float]]] = []

    def _points(self) -> list[tuple[str, Any, Any]]:
        """(option location, x, y) of every place the options name, for the checks."""
        raise NotImplementedError

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """A stage's targets only; each x / y in range for each target kind."""
        if "<character>" not in scene_cls.target_patterns:
            return [("target", f"{self.config.action} moves the characters, props and character parts of a stage")]
        names = scene_cls.target_names(params)
        matched = [n for pattern in self.config.targets() for n in names if fnmatchcase(n, pattern)]
        problems: list[tuple[str, str]] = []
        for name in dict.fromkeys(matched):
            for where, x, y in self._points():
                problems += _value_problems(scene_cls, params, name, where, x, y)
        return list(dict.fromkeys(problems))

    @staticmethod
    def _start(mobject: Mobject, part: str | None, channels: set[str]) -> dict[str, float]:
        """The ``channels`` of ``mobject`` (or its ``part``) now, in :class:`KeyedMotion` units."""
        if part is not None:
            pose = mobject.pose_of(part)
            now = {"x": pose.shift[0], "y": pose.shift[1], "rotate": pose.angle, "scale": (abs(pose.scale[0]) + abs(pose.scale[1])) / 2}
        else:
            feet = feet_of(mobject)
            now = {"x": float(feet[0]), "y": float(feet[1]), "rotate": getattr(mobject, "keyed_rotate", 0.0), "scale": getattr(mobject, "keyed_scale", 1.0)}
        return {c: float(now[c]) for c in CHANNELS if c in channels}

    @staticmethod
    def _units(scene: NarratedScene, name: str, part: str | None, values: dict[str, Any]) -> dict[str, float]:
        """Option values in :class:`KeyedMotion` units: a whole target's x and y on screen."""
        out = {c: v for c, v in values.items() if c not in ("x", "y")}
        if part is not None:
            out.update({c: float(values[c]) for c in ("x", "y") if c in values})
            return out
        if "x" in values:
            out["x"] = _place_x(scene, values["x"])
        if "y" in values:
            ground = getattr(scene, "grounds", {}).get(name, -scene.frame_height / 2)
            out["y"] = ground + float(values["y"]) * scene.frame_height
        return {c: float(v) for c, v in out.items()}

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the channel values before."""
        anims: list[Animation] = []
        saved, self.saved = self.saved, []
        for mobject, part, before in saved:
            now = self._start(mobject, part, set(before))
            back = [Key(1.0, before, DEFAULT_EASE)]
            anims.append(KeyedMotion(mobject, lambda share, now=now, back=back: keyed_values(now, back, share), part=part))
        return anims


@action("keyframes")
class Keyframes(_Keyed):
    """The target (a character, a prop, or a character's part such as kit.arm_left) moves through
    `keys`: `[{t, x, y, rotate, scale, ease}, ...]`. `t` is seconds from the action's start (1.5)
    or a share of the beat's narration ('40%'), in time order. A character or prop: `x` a mark or
    0..1 of the stage, `y` its feet's height above its ground line (frame heights), `rotate`
    degrees about its feet, `scale` its size. A part: `x` / `y` its shift (character heights),
    `rotate` its angle about its pivot (as drawn facing right), `scale` its size. A value a key
    does not give holds; each key is reached with its `ease` (default the action's). It lasts until
    the last key and stays there (`until: <beat>`: back)."""

    class Options(ActionOptions):
        keys: list[KeyFrame] = Field(min_length=1)
        """The keys: {t, x, y, rotate, scale, ease}, in time order; t in seconds from the action's start or a share of the beat ('40%')."""
        ease: EaseName = DEFAULT_EASE  # type: ignore[valid-type]
        """How every key is reached unless it says otherwise: linear, smooth, ease_in_out_sine, ease_out_back, lively, calm, ... (Manim's rate function names)."""

    def problems(self) -> list[tuple[str, str]]:
        """Key times in order, all seconds or all shares, a share at most 100%."""
        return [("keys" if k is None else f"keys[{k}].t", message) for k, message in key_time_problems([k.t for k in self.options.keys])]

    def _points(self) -> list[tuple[str, Any, Any]]:
        return [(f"keys[{k}]", key.x, key.y) for k, key in enumerate(self.options.keys)]

    def _seconds(self, scene: NarratedScene) -> list[float]:
        beat = scene.current_beat
        beat_seconds = scene.beat_duration(beat) if beat is not None else 0.0
        return [key_seconds(key.t, beat_seconds) for key in self.options.keys]

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """Until the last key."""
        return self._seconds(scene)[-1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`KeyedMotion` through the keys for each target."""
        seconds = self._seconds(scene)
        total = seconds[-1]
        anims: list[Animation] = []
        for target in targets:
            mobject, part = _subject(scene, target)
            keys = [
                Key(t, self._units(scene, target.name, part, key.values()), key.ease or self.options.ease)
                for t, key in zip(seconds, self.options.keys)
            ]
            start = self._start(mobject, part, {c for key in keys for c in key.values})
            self.saved.append((mobject, part, dict(start)))
            anims.append(KeyedMotion(mobject, lambda share, start=start, keys=keys: keyed_values(start, keys, share * total), part=part))
        return anims


@action("move_along")
class MoveAlong(_Keyed):
    """The target (a character, a prop, or a character's part such as kit.head) moves from where
    it is through the points of `path`, [[x, y], ...], at an even speed eased by `ease`: a smooth
    curve through them (`curve: smooth`) or straight lines (`straight`). A character or prop: x a
    mark or 0..1 of the stage, y its feet's height above its ground line (frame heights); a part:
    its shift (character heights). It takes `speed` (units per second along the path) or
    `run_time` (default 2 s), and stays at the end (`until: <beat>`: back)."""

    class Options(ActionOptions):
        path: list[PathPoint] = Field(min_length=1)
        """The points it moves through after where it is: [[x, y], ...]."""
        curve: Literal["smooth", "straight"] = "smooth"
        """smooth: a curve through the points; straight: straight lines between them."""
        ease: EaseName = DEFAULT_EASE  # type: ignore[valid-type]
        """How it speeds up and slows down along the path: linear, smooth, ease_in_out_sine, ... (Manim's rate function names; past the ends it holds)."""
        speed: float | None = Field(None, gt=0.0, le=20.0)
        """Units per second along the path (the frame's shorter side is 8 units); default: run_time."""

    run_time = 2.0

    def _points(self) -> list[tuple[str, Any, Any]]:
        return [(f"path[{k}]", x, y) for k, (x, y) in enumerate(self.options.path)]

    def _path(self, scene: NarratedScene, target: Target) -> tuple[Mobject, str | None, MotionPath]:
        mobject, part = _subject(scene, target)
        start = self._start(mobject, part, {"x", "y"})
        points = [(start["x"], start["y"])]
        for x, y in self.options.path:
            moved = self._units(scene, target.name, part, {"x": x, "y": y})
            if abs(moved["x"] - points[-1][0]) > 1e-9 or abs(moved["y"] - points[-1][1]) > 1e-9:
                points.append((moved["x"], moved["y"]))
        return mobject, part, MotionPath(tuple(points), self.options.curve == "smooth")

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        """The longest path's length on screen over ``speed``; without a speed, ``run_time``."""
        if self.options.speed is None:
            return None
        lengths = []
        for target in targets:
            mobject, part, path = self._path(scene, target)
            lengths.append(path.length * (mobject.character_height if part is not None else 1.0))
        return max(lengths, default=0.0) / self.options.speed

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`KeyedMotion` along the path for each target."""
        anims: list[Animation] = []
        ease = self.options.ease
        for target in targets:
            mobject, part, path = self._path(scene, target)
            self.saved.append((mobject, part, {"x": path.points[0][0], "y": path.points[0][1]}))

            def along(share: float, path: MotionPath = path) -> dict[str, float]:
                x, y = path.at(ease_progress(ease, share))
                return {"x": x, "y": y}

            anims.append(KeyedMotion(mobject, along, part=part))
        return anims
