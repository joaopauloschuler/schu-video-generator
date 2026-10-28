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


@dataclass(frozen=True)
class Orbiter:
    """A body on a Kepler orbit (``elements``, at the epoch t = 0) around ``parent``: ``None``
    for the central body, else another orbiter's name."""

    name: str
    body: Body
    elements: Elements
    parent: str | None = None


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
        return sum((o.elements.positions(t) for o in self.chain(name)), start=np.zeros(3) if np.ndim(t) == 0 else np.zeros((len(t), 3)))

    def state(self, name: str, t: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        """Position and velocity relative to the central body at time ``t``."""
        r, v = np.zeros(3), np.zeros(3)
        for o in self.chain(name):
            ro, vo = o.elements.states(t)
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
    start the clock reads 0, after the end ``span``."""

    start: float
    seconds: float
    span: float

    def __post_init__(self) -> None:
        if self.seconds <= 0 or self.span <= 0:
            raise VidgenError("a playback needs positive video seconds and a positive simulated span")

    @property
    def speedup(self) -> float:
        return self.span / self.seconds

    def sim_time(self, video_seconds: float) -> float:
        f = (video_seconds - self.start) / self.seconds
        return self.span * min(1.0, max(0.0, f))


def swept_area(points: np.ndarray, focus: Any = (0.0, 0.0, 0.0)) -> float:
    """The area swept by the line from ``focus`` to a body passing through ``points`` (in
    order): the sum of the triangles focus–pᵢ–pᵢ₊₁ (exact as the points get dense)."""
    rel = np.asarray(points, dtype=float) - np.asarray(focus, dtype=float)
    return float(np.linalg.norm(np.cross(rel[:-1], rel[1:]), axis=-1).sum() / 2)


__all__ = ["Orbiter", "Playback", "System", "swept_area"]
