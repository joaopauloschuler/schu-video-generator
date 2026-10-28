"""A central body with bodies orbiting it (or one another: the Moon around the Earth around the
Sun), moved by Kepler's laws or by n-body integration, and the mapping of video time to
simulated time (Phase X, DESIGN §98). No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vidgen.errors import VidgenError

from .bodies import Body
from .elements import Elements
from .manoeuvres import Trajectory


@dataclass(frozen=True)
class Orbiter:
    """A body on a Kepler orbit (``elements``, at the epoch t = 0) around ``parent``: ``None``
    for the central body, else another orbiter's name. A body that burns (Step 231) has a
    ``trajectory``: its Kepler arcs between the burns, starting on ``elements``."""

    name: str
    body: Body
    elements: Elements
    parent: str | None = None
    trajectory: Trajectory | None = None

    def states(self, t: Any) -> tuple[np.ndarray, np.ndarray]:
        """Position and velocity relative to the parent at time(s) ``t`` (through the burns)."""
        return self.trajectory.states(t) if self.trajectory is not None else self.elements.states(t)

    def positions(self, t: Any) -> np.ndarray:
        return self.trajectory.positions(t) if self.trajectory is not None else self.elements.positions(t)

    def elements_at(self, t: float) -> Elements:
        """The orbit at time ``t`` (its epoch: t = 0, or the last burn's time before ``t``)."""
        return self.trajectory.elements_at(t) if self.trajectory is not None else self.elements


@dataclass(frozen=True)
class System:
    """The central body and its orbiters, in the order given (a parent before its satellites)."""

    central: Body
    orbiters: tuple[Orbiter, ...]
    _index: dict[str, Orbiter] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        index: dict[str, Orbiter] = {}
        for o in self.orbiters:
            if o.name in index or o.name == self.central.name:
                raise VidgenError(f"two bodies are called '{o.name}'; give each its own name")
            if o.parent is not None and o.parent not in index:
                raise VidgenError(f"'{o.name}' goes around '{o.parent}', which is not listed before it")
            index[o.name] = o
        object.__setattr__(self, "_index", index)

    def orbiter(self, name: str) -> Orbiter:
        try:
            return self._index[name]
        except KeyError:
            raise VidgenError(f"no body '{name}' (bodies: {', '.join(self._index)})") from None

    @property
    def names(self) -> list[str]:
        return [o.name for o in self.orbiters]

    def parent_body(self, o: Orbiter) -> Body:
        return self.central if o.parent is None else self.orbiter(o.parent).body

    def chain(self, name: str) -> list[Orbiter]:
        """The orbiter and its parents up to the central body (the orbiter first)."""
        out = [self.orbiter(name)]
        while out[-1].parent is not None:
            out.append(self.orbiter(out[-1].parent))
        return out

    def position(self, name: str, t: Any) -> np.ndarray:
        """Position (m) relative to the central body at time(s) ``t`` (s): Kepler orbits added
        up the chain of parents."""
        return sum((o.positions(t) for o in self.chain(name)), start=np.zeros(3) if np.ndim(t) == 0 else np.zeros((len(t), 3)))

    def state(self, name: str, t: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        """Position and velocity relative to the central body at time ``t``."""
        r, v = np.zeros(3), np.zeros(3)
        for o in self.chain(name):
            ro, vo = o.states(t)
            r, v = r + ro, v + vo
        return r, v

    def first_period(self) -> tuple[str, float | None]:
        """The first orbiter and its period (``None``: an open orbit)."""
        if not self.orbiters:
            raise VidgenError("the system has no orbiting body")
        o = self.orbiters[0]
        return o.name, o.elements.period


@dataclass(frozen=True)
class Playback:
    """Simulated time shown in video time: from video second ``start`` for ``seconds`` the
    clock runs from 0 to ``span`` (s) at the constant ``speedup`` = span / seconds (so equal
    video times are equal simulated times: Kepler's second law shows as it is). Before the
    start the clock reads 0, after the end ``span``.

    Step 231: inner ``knots`` (video s, simulated s) make it piecewise linear — a burn on its
    word, the clock held still (two knots at one simulated time). Each stretch then runs at its
    own speed-up (:meth:`rate`), shown by the scene; ``speedup`` stays the average."""

    start: float
    seconds: float
    span: float
    knots: tuple[tuple[float, float], ...] = ()

    def __post_init__(self) -> None:
        if self.seconds <= 0 or self.span <= 0:
            raise VidgenError("a playback needs positive video seconds and a positive simulated span")
        pts = self._points()
        for (v0, s0), (v1, s1) in zip(pts, pts[1:]):
            if not (v1 > v0 and s1 >= s0):
                raise VidgenError("a playback's knots must go forwards in video time and never back in simulated time")

    def _points(self) -> list[tuple[float, float]]:
        return [(self.start, 0.0), *self.knots, (self.start + self.seconds, self.span)]

    @property
    def speedup(self) -> float:
        return self.span / self.seconds

    def sim_time(self, video_seconds: float) -> float:
        if not self.knots:
            f = (video_seconds - self.start) / self.seconds
            return self.span * min(1.0, max(0.0, f))
        pts = self._points()
        if video_seconds <= pts[0][0]:
            return 0.0
        for (v0, s0), (v1, s1) in zip(pts, pts[1:]):
            if video_seconds <= v1:
                return s0 + (s1 - s0) * (video_seconds - v0) / (v1 - v0)
        return self.span

    def rate(self, video_seconds: float) -> float:
        """The speed-up of the stretch playing at ``video_seconds`` (0 while held still)."""
        pts = self._points()
        for (v0, s0), (v1, s1) in zip(pts, pts[1:]):
            if video_seconds < v1 or (v1, s1) == pts[-1]:
                return (s1 - s0) / (v1 - v0)
        return self.speedup

    def rates(self) -> list[float]:
        """The speed-up of every stretch, in order."""
        pts = self._points()
        return [(s1 - s0) / (v1 - v0) for (v0, s0), (v1, s1) in zip(pts, pts[1:])]

    @classmethod
    def timed(cls, start: float, seconds: float, span: float, events: list[tuple[float, float, str]], holds: list[tuple[float, float, str]]) -> "Playback":
        """A playback through ``events`` (video s, simulated s, what: a burn on its word) with
        the clock held still over ``holds`` (video from, to, what): between two events the clock
        runs at one speed-up over the time not held. Raises :class:`VidgenError` naming what
        does not fit (an event before the motion starts or after it ends, events out of order,
        a hold over an event, holds leaving no time to move)."""
        end = start + seconds
        fixed = [(start, 0.0, "the start of the motion")]
        for video, sim, what in sorted(events):
            if video <= start:
                raise VidgenError(f"{what}: its word falls before the motion starts (during the first beat's entrance); put it on a later word")
            if video >= end:
                raise VidgenError(f"{what}: its word falls after the motion ends")
            if not 0 <= sim < span:
                raise VidgenError(f"{what}: it happens at {sim:g} s of simulated time, outside the scene's span (0 to {span:g} s)")
            prev = fixed[-1]
            if sim < prev[1] or (sim == prev[1] and len(fixed) > 1):   # at 0, on a later word: the clock waits at 0 for it
                raise VidgenError(f"{what} comes before {prev[2]} in the simulation but after it in the narration; put the words in the same order")
            fixed.append((video, sim, what))
        fixed.append((end, span, "the end"))
        spans = sorted((max(a, start), min(b, end), what) for a, b, what in holds if min(b, end) > max(a, start))
        for (a0, b0, w0), (a1, _, w1) in zip(spans, spans[1:]):
            if a1 < b0:
                raise VidgenError(f"{w1} starts while {w0} still holds the clock")
        knots: list[tuple[float, float]] = []
        for (va, sa, wa), (vb, sb, wb) in zip(fixed, fixed[1:]):
            inside = [(a, b, w) for a, b, w in spans if va <= a < vb]
            for a, b, w in inside:
                if b > vb + 1e-9:
                    raise VidgenError(f"{w} holds the clock over the word of {wb}; end the pause before it")
            running = (vb - va) - sum(b - a for a, b, _ in inside)
            if running <= 1e-6:
                raise VidgenError(f"the pauses between {wa} and {wb} leave no time for the motion between them")
            rate = (sb - sa) / running
            sim, last = sa, va
            for a, b, _ in inside:
                sim += rate * (a - last)
                if a > va:
                    knots.append((a, sim))
                if b < vb:
                    knots.append((b, sim))
                last = b
            if vb != end:
                knots.append((vb, sb))
        knots = [k for k, nxt in zip(knots, [*knots[1:], (math.inf, math.inf)]) if nxt[0] > k[0]]
        return cls(start, seconds, span, tuple(knots))


def swept_area(points: np.ndarray, focus: Any = (0.0, 0.0, 0.0)) -> float:
    """The area swept by the line from ``focus`` to a body passing through ``points`` (in
    order): the sum of the triangles focus–pᵢ–pᵢ₊₁ (exact as the points get dense)."""
    rel = np.asarray(points, dtype=float) - np.asarray(focus, dtype=float)
    return float(np.linalg.norm(np.cross(rel[:-1], rel[1:]), axis=-1).sum() / 2)


__all__ = ["Orbiter", "Playback", "System", "swept_area"]
