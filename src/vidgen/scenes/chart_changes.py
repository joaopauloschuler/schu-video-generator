"""Charts that change between beats (``changes:`` on ``bar_chart`` and ``line_chart``; DESIGN
§87.9): the ``change<N>`` targets and steps, the rule for when a y axis rescales, and the
animation that swaps parts of a group (an axis' ticks) when a change ends."""

from collections.abc import Callable, Sequence
from fnmatch import fnmatchcase
from typing import Any

from vidgen.api import *

#: A change rescales the y axis when its values leave the axis or span less than this share of it.
RESCALE_SHARE = 0.5
#: Seconds a ``reveal`` action takes to play a change (without its own ``run_time``).
CHANGE_TIME = 1.2


def needs_rescale(axis: ChartAxis, values: Sequence[float]) -> bool:
    """Whether ``values`` call for another y axis than ``axis``: some lie outside it, or they
    span less than :data:`RESCALE_SHARE` of it (the change would look flat)."""
    lo, hi = min(values), max(values)
    if lo < axis.lo - 1e-9 or hi > axis.hi + 1e-9:
        return True
    return hi - lo < RESCALE_SHARE * (axis.hi - axis.lo)


def state_axes(states: Sequence[Sequence[float]], make: Callable[[list[float]], ChartAxis], rescale: bool) -> list[ChartAxis]:
    """One y axis per state of a chart (``states``: each state's values): with ``rescale`` the
    first state's axis, kept (the same object) until a state :func:`needs_rescale`, which gets
    ``make(its values)``; without, one axis over every state."""
    if not rescale:
        one = make([v for state in states for v in state])
        return [one] * len(states)
    axes = [make(list(states[0]))]
    for values in states[1:]:
        current = axes[-1]
        new = make(list(values)) if needs_rescale(current, values) else current
        axes.append(current if new == current else new)
    return axes


def lerp(a: Any, b: Any, t: float) -> Any:
    """``a`` to ``b`` at ``t`` (numbers or numpy arrays)."""
    return a + (b - a) * t


def keep_opacity(new: Mobject, old: Mobject) -> Mobject:
    """``new`` (a label about to replace ``old`` by ``become``) at the opacity ``old`` shows, e.g.
    dimmed. Not ``match_style``: after a ``become`` from a longer text, ``old`` holds pointless
    padding glyphs, and copying their style glyph by glyph hides digits."""
    shown = old.family_members_with_points()
    if shown:
        new.set_fill(opacity=max(float(m.get_fill_opacity()) for m in shown))
    return new


class ChangingChart:
    """Mixin for a chart scene with ``changes``: registers ``change<N>`` targets (shown once the
    chart has changed to state N; the first state is 0), the steps that play them and the
    bookkeeping of the state shown. The scene defines :meth:`play_change`."""

    def setup_changes(self, count: int, chart: Mobject) -> None:
        """Register ``change1`` .. ``change<count>`` on ``chart`` (what ``dim`` / ``highlight``
        act on); a change a ``reveal`` action plays is left out of :meth:`change_steps`."""
        self._state = 0
        self._change_of: dict[int, int] = {}
        for k in range(1, count + 1):
            target = self.target(f"change{k}", chart, entrance=lambda k=k: self.go_to_state(k))  # type: ignore[attr-defined]
            self._change_of[id(target)] = k
        names = [f"change{k}" for k in range(1, count + 1)]
        patterns = [p for action in self.action_uses("reveal") for p in action.config.targets()]  # type: ignore[attr-defined]
        self._waiting = {int(n[len("change"):]) for n in names if any(fnmatchcase(n, p) for p in patterns)}

    def change_steps(self) -> list[Callable[[], list[Animation]]]:
        """One step per change (empty for a change a ``reveal`` action plays)."""
        return [(lambda k=k: [] if k in self._waiting else self.go_to_state(k)) for k in range(1, len(self._change_of) + 1)]

    def go_to_state(self, k: int) -> list[Animation]:
        """The animations from the state shown to state ``k``; nothing when it (or a later one)
        shows already."""
        if k <= self._state:
            return []
        old, self._state = self._state, k
        return self.play_change(old, k)

    def play_change(self, old: int, new: int) -> list[Animation]:
        """The animations from state ``old`` to ``new``; parts not on screen change at once."""
        raise NotImplementedError

    def is_shown(self, target: Target | str) -> bool:
        """A ``change<N>`` target is shown once the chart has changed to state N."""
        found = self.find_targets(target) if isinstance(target, str) else [target]  # type: ignore[attr-defined]
        changes = getattr(self, "_change_of", {})
        if found and all(id(t) in changes for t in found):
            return any(changes[id(t)] <= self._state for t in found)
        return super().is_shown(target)  # type: ignore[misc]

    def entrance_time(self, target: Target) -> float | None:
        """A ``reveal`` action plays a change for :data:`CHANGE_TIME` seconds."""
        if id(target) in getattr(self, "_change_of", {}):
            return CHANGE_TIME
        return super().entrance_time(target)  # type: ignore[misc]


def swap_parts(scene: NarratedScene, holder: VGroup, drop: list[Mobject], add: list[Mobject], animations: list[Animation]) -> list[Animation]:
    """Replace ``drop`` by ``add`` inside ``holder`` (e.g. an axis' ticks in the ``axes``
    target): at once when ``holder`` is not on screen, else when ``animations`` (which fade
    ``drop`` out and bring ``add`` in) end, so ``holder`` stays one group on screen."""
    if not scene.on_screen_parts(holder):
        holder.remove(*drop)
        holder.add(*add)
        return animations
    return [*animations, _SwapAtEnd(holder, drop, add)]


class _SwapAtEnd(Animation):
    """Changes nothing while it plays (but has Manim redraw ``holder``); when it ends, ``drop``
    leaves ``holder`` and the scene, and ``add`` joins ``holder`` instead of standing in the
    scene on its own. Not an ``AnimationGroup``: playing one dissolves a group on screen whose
    parts it animates (Manim adds the animation's group to the scene)."""

    def __init__(self, holder: VGroup, drop: list[Mobject], add: list[Mobject], **kwargs: Any) -> None:
        super().__init__(holder, **kwargs)
        self._drop, self._add = drop, add

    def interpolate_mobject(self, alpha: float) -> None:
        pass

    def clean_up_from_scene(self, scene: Scene) -> None:
        super().clean_up_from_scene(scene)
        holder = self.mobject
        holder.remove(*self._drop)   # first: removing a part of a group on screen dissolves the group
        scene.remove(*self._drop)
        if holder in scene.mobjects:
            scene.remove(*self._add)
        holder.add(*self._add)
