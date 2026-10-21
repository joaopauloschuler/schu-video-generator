"""Weather on an iso place (DESIGN.md §90): what keeps the rain off, where puddles lie and how
their ripples look, and how much settling snow shows. No manim.

The *top surface* of a place (:class:`TopSurface`, :func:`top_surface`) is the height of the
highest thing facing up over each point of the map, sampled :data:`SURFACE_SAMPLES` times per
tile: the ground, a block's top, a roof's slope, a tree's crown (a ball around each puff), a
bridge's deck, a post's top. It is made from the shapes the place is drawn with, so what keeps
the rain off is what settling snow lies on (:func:`~vidgen.cartoon.iso_drawing.upward`). A drop
that would land on the ground under something higher lands on that thing's top instead
(:func:`lift_floors`): rain splashes on a roof or a crown and never under it, or under a bridge.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from vidgen.cartoon.iso_drawing import Blobs, Disc, Poly, Shape, Upright, upward
from vidgen.cartoon.iso_scenery import WATER_DEPTH
from vidgen.world.iso import FLOOR, PATH, VOID, WATER, IsoPlace
from vidgen.world.iso_view import ISO_RISE, Box3, in_front

#: Samples of the top surface per tile, each way.
SURFACE_SAMPLES = 8
#: A round puff of a crown or a bush drawn as a circle of radius ``r`` on the picture is a ball
#: of radius ``r`` times this in the world (the view is a parallel view scaled by 1/√2).
BALL_RADIUS = math.sqrt(2.0)
#: Something this much (tile units) over the ground keeps the rain off it (a roof, a crown); less
#: is the ground's own relief (a stone on a path, a flower bed's leaves).
SHELTER_CLEARANCE = 0.3

#: Heights (tile units; ``-inf`` where nothing) over sample grids ``x``, ``y`` (world points)
#: that are the part ``(i0, j0, i1, j1)`` of the surface's samples.
Heights = Callable[[np.ndarray, np.ndarray, tuple[int, int, int, int]], np.ndarray]


@dataclass(frozen=True, eq=False)
class TopSurface:
    """The heights (tile units) over a place of ``columns`` x ``rows`` cells, sampled ``samples``
    times per tile: ``tops`` the highest surface facing up, ``grounds`` each cell's top (water's
    surface, a little under the banks; rows of samples, ``y`` first); ``-inf`` outside the place."""

    samples: int
    columns: int
    rows: int
    tops: np.ndarray
    grounds: np.ndarray

    def _index(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        i = np.floor(np.asarray(x, dtype=float) * self.samples).astype(int)
        j = np.floor(np.asarray(y, dtype=float) * self.samples).astype(int)
        inside = (i >= 0) & (j >= 0) & (i < self.columns * self.samples) & (j < self.rows * self.samples)
        return np.clip(i, 0, self.columns * self.samples - 1), np.clip(j, 0, self.rows * self.samples - 1), inside

    def top_z(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """The top surface's height over each world point (``-inf`` outside the place)."""
        i, j, inside = self._index(x, y)
        return np.where(inside, self.tops[j, i], -np.inf)

    def ground_z(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """The height of the cell top under each world point (``-inf`` outside the place)."""
        i, j, inside = self._index(x, y)
        return np.where(inside, self.grounds[j, i], -np.inf)

    def sheltered(self, x: np.ndarray, y: np.ndarray, z: np.ndarray | float) -> np.ndarray:
        """Whether something at least :data:`SHELTER_CLEARANCE` over the height ``z`` keeps the
        rain off each world point (a roof, a crown, a bridge over water)."""
        return self.top_z(x, y) > np.asarray(z, dtype=float) + SHELTER_CLEARANCE


def _raise(tops: np.ndarray, samples: int, bounds: tuple[float, float, float, float], heights: Heights) -> None:
    """Raise ``tops`` to ``heights`` within the world ``bounds`` (x0, y0, x1, y1)."""
    rows, columns = tops.shape
    i0, j0 = max(math.floor(bounds[0] * samples), 0), max(math.floor(bounds[1] * samples), 0)
    i1, j1 = min(math.ceil(bounds[2] * samples), columns), min(math.ceil(bounds[3] * samples), rows)
    if i1 <= i0 or j1 <= j0:
        return
    x, y = np.meshgrid((np.arange(i0, i1) + 0.5) / samples, (np.arange(j0, j1) + 0.5) / samples)
    found = heights(x, y, (i0, j0, i1, j1))
    np.maximum(tops[j0:j1, i0:i1], found, out=tops[j0:j1, i0:i1])


def _poly_heights(shape: Poly, normal: tuple[float, float, float], samples: int) -> Heights:
    """The heights of an upward polygon over the samples its outline on the map covers."""
    p0 = shape.points[0]

    def heights(x: np.ndarray, y: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
        i0, j0, i1, j1 = box
        mask = Image.new("L", (i1 - i0, j1 - j0), 0)
        ImageDraw.Draw(mask).polygon([(p[0] * samples - i0 - 0.5, p[1] * samples - j0 - 0.5) for p in shape.points], fill=1, outline=1)
        z = p0[2] - (normal[0] * (x - p0[0]) + normal[1] * (y - p0[1])) / normal[2]
        return np.where(np.asarray(mask, dtype=bool), z, -np.inf)

    return heights


def _ball_heights(cx: float, cy: float, cz: float, radius: float) -> Heights:
    """A ball's upper half."""
    def heights(x: np.ndarray, y: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        return np.where(d2 <= radius * radius, cz + np.sqrt(np.maximum(radius * radius - d2, 0.0)), -np.inf)

    return heights


def _disc_heights(cx: float, cy: float, z: float, radius: float) -> Heights:
    """A flat disc."""
    def heights(x: np.ndarray, y: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
        return np.where((x - cx) ** 2 + (y - cy) ** 2 <= radius * radius, z, -np.inf)

    return heights


def top_surface(place: IsoPlace, shapes: Sequence[Shape], samples: int = SURFACE_SAMPLES) -> TopSurface:
    """The :class:`TopSurface` of ``place`` drawn with ``shapes`` (its ground and its pieces as
    they are now): every polygon facing up (a top, a roof's slope), round puffs as balls, flat
    discs and the tops of upright cylinders; shadows and pools of light (tints) do not count."""
    columns, rows = place.columns, place.rows
    grounds = np.full((rows * samples, columns * samples), -np.inf)
    for r in range(rows):
        for c in range(columns):
            ground = place.ground(c, r)
            if ground != VOID:
                grounds[r * samples:(r + 1) * samples, c * samples:(c + 1) * samples] = -WATER_DEPTH if ground == WATER else place.floor_z(c, r)
    tops = grounds.copy()
    for shape in shapes:
        if isinstance(shape, Poly):
            normal = upward(shape)
            if normal is None:
                continue
            xs, ys = [p[0] for p in shape.points], [p[1] for p in shape.points]
            _raise(tops, samples, (min(xs), min(ys), max(xs), max(ys)), _poly_heights(shape, normal, samples))
        elif isinstance(shape, Blobs):
            for (cx, cy, cz), r in zip(shape.centres, shape.radii):
                radius = r * BALL_RADIUS
                _raise(tops, samples, (cx - radius, cy - radius, cx + radius, cy + radius), _ball_heights(cx, cy, cz, radius))
        elif isinstance(shape, Disc) and shape.opacity >= 1.0:
            cx, cy, cz = shape.centre
            _raise(tops, samples, (cx - shape.radius, cy - shape.radius, cx + shape.radius, cy + shape.radius),
                   _disc_heights(cx, cy, cz, shape.radius))
        elif isinstance(shape, Upright):
            _raise(tops, samples, (shape.x - shape.radius, shape.y - shape.radius, shape.x + shape.radius, shape.y + shape.radius),
                   _disc_heights(shape.x, shape.y, shape.z1, shape.radius))
    tops = np.where(np.isfinite(grounds), tops, -np.inf)   # nothing counts beyond the place's cells
    return TopSurface(samples, columns, rows, tops, grounds)


def world_at(u: np.ndarray, v: np.ndarray, z: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
    """The world point at height ``z`` seen at picture point (``u``, ``v``) (tile widths)."""
    depth = 2.0 * (np.asarray(v, dtype=float) + np.asarray(z, dtype=float) * ISO_RISE)
    return u + depth, depth - u


def lift_floors(u: np.ndarray, v: np.ndarray, surface: TopSurface) -> np.ndarray:
    """How far up the picture (tile widths) a drop that would land on the ground seen at picture
    point (``u``, ``v``) lands instead: on the top surface over that ground point when something
    is :data:`SHELTER_CLEARANCE` or more over it (a roof, a crown, a bridge's deck over water),
    else 0. The ground point is found by stepping to the cell top's height (three times: a
    raised block moves it)."""
    z = np.zeros_like(np.asarray(u, dtype=float))
    for _ in range(3):
        x, y = world_at(u, v, z)
        ground = surface.ground_z(x, y)
        z = np.where(np.isfinite(ground), ground, 0.0)
    x, y = world_at(u, v, z)
    top = surface.top_z(x, y)
    lift = np.where(np.isfinite(top) & (top > z + SHELTER_CLEARANCE), top - z, 0.0)
    return lift * ISO_RISE


# ----- puddles (DESIGN.md §90.2) --------------------------------------------------------------------

#: One puddle per this many cells where one may lie, at least :data:`MIN_PUDDLES` and at most
#: :data:`MAX_PUDDLES`; their radius (tile units: a circle on the ground, drawn as the view sees it).
CELLS_PER_PUDDLE = 10
MIN_PUDDLES = 2
MAX_PUDDLES = 12
PUDDLE_RADIUS = (0.3, 0.44)
#: The grounds a puddle lies on: grass (``.`` outdoors) and paths.
PUDDLE_GROUNDS = (FLOOR, PATH)


@dataclass(frozen=True)
class IsoPuddle:
    """A puddle on the place: its middle (``x``, ``y``, ``z``; tile units) and ``radius``; ``seed``
    times its ripples."""

    x: float
    y: float
    z: float
    radius: float
    seed: int


def puddle_cells(place: IsoPlace, surface: TopSurface, pieces: Sequence[Box3]) -> list[tuple[int, int]]:
    """The cells a puddle may lie in, in map order: grass or a path with nothing on it, no door,
    not sheltered (:meth:`TopSurface.sheltered`), and no piece of the place (``pieces``: their
    boxes) in front of it on the picture: the puddle is drawn over the place's picture, under
    the characters, so it must not cover a piece in front of it."""
    found = []
    for r in range(place.rows):
        for c in range(place.columns):
            if place.ground(c, r) not in PUDDLE_GROUNDS or place.object_at(c, r) is not None:
                continue
            z = place.floor_z(c, r)
            if bool(surface.sheltered(np.array([c + 0.5]), np.array([r + 0.5]), z)[0]):
                continue
            flat = Box3(c, r, z, c + 1, r + 1, z + 0.02)
            if any(in_front(box, flat) is True for box in pieces):
                continue
            found.append((c, r))
    return found


def iso_puddles(place: IsoPlace, surface: TopSurface, pieces: Sequence[Box3], seed: int) -> list[IsoPuddle]:
    """Seeded puddles on the place (:func:`puddle_cells`): one per :data:`CELLS_PER_PUDDLE`
    cells, each inside its own cell, back to front."""
    cells = puddle_cells(place, surface, pieces)
    if not cells:
        return []
    count = min(max(round(len(cells) / CELLS_PER_PUDDLE), MIN_PUDDLES), MAX_PUDDLES, len(cells))
    rng = random.Random(f"puddles:{seed}")
    found = []
    for c, r in rng.sample(cells, count):
        radius = rng.uniform(*PUDDLE_RADIUS)
        room = 0.5 - radius
        found.append(IsoPuddle(c + 0.5 + rng.uniform(-room, room), r + 0.5 + rng.uniform(-room, room), place.floor_z(c, r), radius,
                               rng.randrange(1 << 30)))
    return sorted(found, key=lambda p: (p.x + p.y, p.x))


#: Ripples while it rains: rings per puddle, seconds each takes to spread, how far it spreads (a
#: share of the puddle's radius), its ring's width (a share of its radius) and opacity at the start.
RIPPLES = 2
RIPPLE_SECONDS = 0.9
RIPPLE_REACH = 0.75
RIPPLE_WIDTH = 0.16
RIPPLE_OPACITY = 0.7
#: How far from the puddle's middle a ripple starts (a share of its radius): at most the room
#: its ring leaves, so a ring never spreads past the puddle onto the grass.
RIPPLE_OFFSET = 1.0 - RIPPLE_REACH - 0.05


@dataclass(frozen=True)
class Ripple:
    """A ripple ring on a puddle: its middle (``dx``, ``dy``, tile units from the puddle's),
    ``radius`` (tile units) and ``opacity``."""

    dx: float
    dy: float
    radius: float
    opacity: float


def ripples(puddle: IsoPuddle, seconds: float, size: float = 1.0) -> list[Ripple]:
    """The ripples on ``puddle`` ``seconds`` into the rain (``size``: how grown it is, 0..1):
    :data:`RIPPLES` rings, each spreading from a seeded point and fading over
    :data:`RIPPLE_SECONDS`, then starting again elsewhere."""
    found = []
    radius = puddle.radius * size
    for k in range(RIPPLES):
        rng = random.Random(f"{puddle.seed}:{k}")
        phase = rng.random()
        cycle = seconds / RIPPLE_SECONDS + phase
        turn = math.floor(cycle)
        spread = cycle - turn
        where = random.Random(f"{puddle.seed}:{k}:{turn}")
        angle, reach = where.uniform(0.0, 2 * math.pi), where.uniform(0.0, RIPPLE_OFFSET)
        found.append(Ripple(math.cos(angle) * reach * radius, math.sin(angle) * reach * radius,
                            max(spread * RIPPLE_REACH * radius, 1e-6), RIPPLE_OPACITY * (1.0 - spread) * size))
    return found


__all__ = [
    "BALL_RADIUS",
    "CELLS_PER_PUDDLE",
    "IsoPuddle",
    "PUDDLE_GROUNDS",
    "PUDDLE_RADIUS",
    "RIPPLES",
    "RIPPLE_OFFSET",
    "RIPPLE_OPACITY",
    "RIPPLE_SECONDS",
    "RIPPLE_WIDTH",
    "Ripple",
    "SHELTER_CLEARANCE",
    "SURFACE_SAMPLES",
    "TopSurface",
    "iso_puddles",
    "lift_floors",
    "puddle_cells",
    "ripples",
    "top_surface",
    "world_at",
]
