"""Flat shapes of the cell world, in µm (DESIGN.md §95.3): ellipses (cells, nuclei, round
organelles), capsules (mitochondria) and arc bands (ER sheets, Golgi cisternae, ER tubules).
Each tells whether a point is inside, its outline, an inset copy (the next membrane in), its
surface points with outward normals (for things bound to a membrane) and its bounds. A cell
world is a cross-section, as in a thin-section micrograph. No manim."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]


class Shape(Protocol):
    """What every shape offers."""

    def contains(self, p: Point, pad: float = 0.0) -> bool: ...
    def outline(self, n: int = 64) -> list[Point]: ...
    def inset(self, d: float) -> "Shape": ...
    def bounds(self) -> Bounds: ...
    def center(self) -> Point: ...


def _rot(x: float, y: float, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return (x * c - y * s, x * s + y * c)


@dataclass(frozen=True)
class Ellipse:
    """An ellipse: centre, half-axes ``a`` (along ``angle``, radians) and ``b``."""

    cx: float
    cy: float
    a: float
    b: float
    angle: float = 0.0

    def center(self) -> Point:
        return (self.cx, self.cy)

    def local(self, p: Point) -> Point:
        return _rot(p[0] - self.cx, p[1] - self.cy, -self.angle)

    def contains(self, p: Point, pad: float = 0.0) -> bool:
        a, b = self.a + pad, self.b + pad
        if a <= 0 or b <= 0:
            return False
        x, y = self.local(p)
        return (x / a) ** 2 + (y / b) ** 2 <= 1.0

    def point(self, t: float) -> Point:
        """The outline at parameter ``t`` (0..1, counter-clockwise from the ``a`` axis)."""
        x, y = _rot(self.a * math.cos(2 * math.pi * t), self.b * math.sin(2 * math.pi * t), self.angle)
        return (self.cx + x, self.cy + y)

    def normal(self, t: float) -> Point:
        """The outward unit normal at parameter ``t``."""
        nx, ny = _rot(self.b * math.cos(2 * math.pi * t), self.a * math.sin(2 * math.pi * t), self.angle)
        length = math.hypot(nx, ny) or 1.0
        return (nx / length, ny / length)

    def outline(self, n: int = 64) -> list[Point]:
        return [self.point(k / n) for k in range(n)]

    def inset(self, d: float) -> "Ellipse":
        return replace(self, a=self.a - d, b=self.b - d)

    def perimeter(self) -> float:
        """Ramanujan's approximation."""
        a, b = self.a, self.b
        h = ((a - b) / (a + b)) ** 2
        return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))

    def bounds(self) -> Bounds:
        c, s = math.cos(self.angle), math.sin(self.angle)
        hx = math.hypot(self.a * c, self.b * s)
        hy = math.hypot(self.a * s, self.b * c)
        return (self.cx - hx, self.cy - hy, self.cx + hx, self.cy + hy)

    def surface(self, spacing: float, offset: float = 0.0) -> list[tuple[Point, Point]]:
        """Points every ``spacing`` µm along the outline (starting ``offset`` of a step in), each
        with its outward normal."""
        count = max(1, round(self.perimeter() / spacing))
        return [(self.point((k + offset) / count), self.normal((k + offset) / count)) for k in range(count)]


@dataclass(frozen=True)
class Capsule:
    """A stadium (a mitochondrion's section): centre, total ``length`` along ``angle``
    (radians) and ``width``."""

    cx: float
    cy: float
    length: float
    width: float
    angle: float = 0.0

    def center(self) -> Point:
        return (self.cx, self.cy)

    @property
    def radius(self) -> float:
        return self.width / 2

    @property
    def half(self) -> float:
        """Half the straight part's length."""
        return max(0.0, (self.length - self.width) / 2)

    def contains(self, p: Point, pad: float = 0.0) -> bool:
        x, y = _rot(p[0] - self.cx, p[1] - self.cy, -self.angle)
        dx = max(abs(x) - self.half, 0.0)
        return math.hypot(dx, y) <= self.radius + pad

    def _local_outline(self, n: int) -> list[tuple[Point, Point]]:
        h, r = self.half, self.radius
        straight, arc = 2 * h, math.pi * r
        total = 2 * straight + 2 * arc
        out = []
        for k in range(n):
            s = total * k / n
            if s < straight:                       # bottom, left to right
                out.append(((-h + s, -r), (0.0, -1.0)))
            elif s < straight + arc:               # right end
                phi = -math.pi / 2 + (s - straight) / r
                out.append(((h + r * math.cos(phi), r * math.sin(phi)), (math.cos(phi), math.sin(phi))))
            elif s < 2 * straight + arc:           # top, right to left
                out.append(((h - (s - straight - arc), r), (0.0, 1.0)))
            else:                                  # left end
                phi = math.pi / 2 + (s - 2 * straight - arc) / r
                out.append(((-h + r * math.cos(phi), r * math.sin(phi)), (math.cos(phi), math.sin(phi))))
        return out

    def _placed(self, local: list[tuple[Point, Point]]) -> list[tuple[Point, Point]]:
        result = []
        for (x, y), (nx, ny) in local:
            px, py = _rot(x, y, self.angle)
            result.append(((self.cx + px, self.cy + py), _rot(nx, ny, self.angle)))
        return result

    def outline(self, n: int = 64) -> list[Point]:
        return [p for p, _ in self._placed(self._local_outline(n))]

    def perimeter(self) -> float:
        return 4 * self.half + 2 * math.pi * self.radius

    def surface(self, spacing: float, offset: float = 0.0) -> list[tuple[Point, Point]]:
        count = max(1, round(self.perimeter() / spacing))
        return self._placed(self._local_outline(count))

    def inset(self, d: float) -> "Capsule":
        return replace(self, length=self.length - 2 * d, width=self.width - 2 * d)

    def bounds(self) -> Bounds:
        xs, ys = zip(*self.outline(48))
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(frozen=True)
class ArcBand:
    """A curved band with round ends (an ER sheet, a Golgi cisterna, an ER tubule): the arc of
    ``radius`` round ``(cx, cy)`` from angle ``start`` to ``end`` (radians, counter-clockwise),
    ``thickness`` across."""

    cx: float
    cy: float
    radius: float
    thickness: float
    start: float
    end: float

    def center(self) -> Point:
        mid = (self.start + self.end) / 2
        return (self.cx + self.radius * math.cos(mid), self.cy + self.radius * math.sin(mid))

    def _within(self, phi: float) -> bool:
        span = self.end - self.start
        return (phi - self.start) % (2 * math.pi) <= span

    def contains(self, p: Point, pad: float = 0.0) -> bool:
        half = self.thickness / 2 + pad
        if half <= 0:
            return False
        dx, dy = p[0] - self.cx, p[1] - self.cy
        if self._within(math.atan2(dy, dx)) and abs(math.hypot(dx, dy) - self.radius) <= half:
            return True
        return any(math.hypot(p[0] - ex, p[1] - ey) <= half for ex, ey in self.ends())

    def ends(self) -> tuple[Point, Point]:
        """The middles of its two round ends."""
        return tuple((self.cx + self.radius * math.cos(a), self.cy + self.radius * math.sin(a)) for a in (self.start, self.end))  # type: ignore[return-value]

    @property
    def length(self) -> float:
        return self.radius * (self.end - self.start)

    def outline(self, n: int = 64) -> list[Point]:
        r_out, r_in, half = self.radius + self.thickness / 2, self.radius - self.thickness / 2, self.thickness / 2
        side = max(2, (n - 8) // 2)
        out = [(self.cx + r_out * math.cos(a), self.cy + r_out * math.sin(a))
               for a in (self.start + (self.end - self.start) * k / (side - 1) for k in range(side))]
        ex, ey = self.ends()[1]
        out += [(ex + half * math.cos(self.end + math.pi * k / 4), ey + half * math.sin(self.end + math.pi * k / 4)) for k in range(1, 4)]
        out += [(self.cx + r_in * math.cos(a), self.cy + r_in * math.sin(a))
                for a in (self.end - (self.end - self.start) * k / (side - 1) for k in range(side))]
        sx, sy = self.ends()[0]
        out += [(sx + half * math.cos(self.start + math.pi + math.pi * k / 4), sy + half * math.sin(self.start + math.pi + math.pi * k / 4))
                for k in range(1, 4)]
        return out

    def inset(self, d: float) -> "ArcBand":
        return replace(self, thickness=self.thickness - 2 * d)

    def bounds(self) -> Bounds:
        xs, ys = zip(*self.outline(64))
        return (min(xs), min(ys), max(xs), max(ys))

    def faces(self, spacing: float, offset: float = 0.5) -> list[tuple[Point, Point]]:
        """Points every ``spacing`` µm along both long faces (outer, then inner), each with its
        outward normal (away from the lumen)."""
        count = max(1, int(self.length / spacing))
        out = []
        for sign in (1.0, -1.0):
            r = self.radius + sign * self.thickness / 2
            for k in range(count):
                a = self.start + (self.end - self.start) * (k + offset) / count
                out.append(((self.cx + r * math.cos(a), self.cy + r * math.sin(a)), (sign * math.cos(a), sign * math.sin(a))))
        return out


def inside(shape: Shape, host: Shape, margin: float = 0.0) -> bool:
    """Whether ``shape``'s outline lies within ``host`` at least ``margin`` from its edge."""
    return all(host.contains(p, -margin) for p in shape.outline(64))


def overlap(a: Shape, b: Shape, margin: float = 0.0) -> bool:
    """Whether two shapes overlap or come within ``margin`` of each other (outline samples:
    good for the convex and thin shapes here)."""
    ax0, ay0, ax1, ay1 = a.bounds()
    bx0, by0, bx1, by1 = b.bounds()
    if ax1 + margin < bx0 or bx1 + margin < ax0 or ay1 + margin < by0 or by1 + margin < ay0:
        return False
    if a.contains(b.center(), margin) or b.contains(a.center(), margin):
        return True
    return any(b.contains(p, margin) for p in a.outline(96)) or any(a.contains(p, margin) for p in b.outline(96))
