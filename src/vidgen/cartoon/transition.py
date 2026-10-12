"""Eased part-by-part changes between two character states (DESIGN.md §69.3).

:class:`PoseChange` animates a :class:`~vidgen.cartoon.character.Character` from its state when the
animation starts to a target state (a pose, an expression, or any :class:`CharacterState`). Each
part that changes eases on its own: angles, scales and shifts are blended and the character is
redrawn from its rest shapes, so an arm swings along an arc about its pivot (``.animate`` would
move its points along straight lines), and parts start one after another from the body out.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from manim import Animation, linear, smooth

from vidgen.cartoon.character import PART_NAMES, Character, CharacterState, PartPose


def blend_poses(start: PartPose, end: PartPose, progress: float) -> PartPose:
    """The pose ``progress`` (0..1) of the way from ``start`` to ``end``: angle, scale and shift
    blended linearly; the shape switches to ``end``'s at the halfway point."""
    def mix(a: float, b: float) -> float:
        return a + (b - a) * progress

    return PartPose(
        angle=mix(start.angle, end.angle),
        scale=(mix(start.scale[0], end.scale[0]), mix(start.scale[1], end.scale[1])),
        shift=(mix(start.shift[0], end.shift[0]), mix(start.shift[1], end.shift[1])),
        shape=end.shape if progress >= 0.5 else start.shape,
    )


def part_windows(parts: Sequence[str], lag_ratio: float) -> dict[str, tuple[float, float]]:
    """When each of ``parts`` moves, as (start, end) fractions of the animation: each starts
    ``lag_ratio`` of a part's duration after the previous one (0: all together), the last ends at 1."""
    if not parts:
        return {}
    total = 1.0 + (len(parts) - 1) * lag_ratio
    return {part: (k * lag_ratio / total, (k * lag_ratio + 1.0) / total) for k, part in enumerate(parts)}


class PoseChange(Animation):
    """Animate ``character`` to pose ``pose`` and / or expression ``expression`` (names of
    :meth:`Character.names`), or to ``state``; ``facing`` turns it too (the mirror switches
    halfway). Every changing part eases with ``part_rate_func`` in its own window; parts start
    ``lag_ratio`` apart, body first, then legs, arms, head and face (:data:`PART_NAMES` order).
    The target is resolved when the animation is created; the start when it begins, which also
    ends a running blink (the idle clock stops while it plays, §69.5).

    ``self.play(PoseChange(pip, pose="waving", expression="happy"), run_time=0.8)``
    """

    def __init__(
        self,
        character: Character,
        *,
        pose: str | None = None,
        expression: str | None = None,
        state: CharacterState | None = None,
        facing: str | None = None,
        lag_ratio: float = 0.15,
        part_rate_func: Callable[[float], float] = smooth,
        **kwargs,
    ) -> None:
        if state is not None and (pose is not None or expression is not None):
            raise TypeError("PoseChange: give state, or pose / expression, not both")
        target = state if state is not None else character.posed_state(pose=pose, expression=expression)
        if facing is not None:
            target = CharacterState(facing, dict(target.parts))
        self.target = target
        self.part_rate_func = part_rate_func
        self._start = character.state()
        self._windows: dict[str, tuple[float, float]] = {}
        kwargs.setdefault("rate_func", linear)
        super().__init__(character, lag_ratio=lag_ratio, **kwargs)

    def begin(self) -> None:
        self.mobject.end_blink()
        self._start = self.mobject.state()
        changing = [
            part for part in PART_NAMES
            if part in self._start.parts and self.target.parts.get(part, self._start.parts[part]) != self._start.parts[part]
        ]
        self._windows = part_windows(changing, self.lag_ratio)
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        progress = self.rate_func(alpha)
        parts = {}
        for part, (begin, end) in self._windows.items():
            local = min(max((progress - begin) / (end - begin), 0.0), 1.0)
            parts[part] = blend_poses(self._start.parts[part], self.target.parts[part], self.part_rate_func(local))
        facing = self.target.facing if progress >= 0.5 else self._start.facing
        self.mobject.set_state(CharacterState(facing, parts))


__all__ = ["PoseChange", "blend_poses", "part_windows"]
