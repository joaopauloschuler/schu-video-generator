"""Regions made of shapes by union and difference (DESIGN.md §95.9): a membrane whose outline
is not one simple shape — a mitochondrion's inner membrane folded into cristae, the ER's sheets
joined to the nuclear envelope, a smooth-ER network, a nuclear envelope opened by its pores.
Backed by Skia's path operations (``skia-pathops``, which Manim needs too) in local
coordinates near the region and in nanometres, so float precision stays far below a nanometre
and features are the size Skia's tolerances are made for (in µm, two 10 nm thylakoid pieces
overlapping at their ends lost one of them in a union). No manim."""

from __future__ import annotations

import math
from collections.abc import Iterable

import pathops

from .curves import Cubic, flatten, shape_curves
from .geometry import Bounds, Point

#: Skia paths are in nanometres (the region's points are µm).
NM = 1000.0


def _path(curves: Iterable[Cubic], origin: Point) -> pathops.Path:
    """A Skia path of closed outlines (pieces end to end; a gap starts a new outline), in nm
    from ``origin``."""
    path = pathops.Path()
    ox, oy = origin
    last: Point | None = None
    first: Point | None = None
    for p0, p1, p2, p3 in curves:
        if last is None or math.dist(last, p0) > 1e-9:
            if last is not None:
                path.close()
            path.moveTo((p0[0] - ox) * NM, (p0[1] - oy) * NM)
            first = p0
        path.cubicTo((p1[0] - ox) * NM, (p1[1] - oy) * NM, (p2[0] - ox) * NM, (p2[1] - oy) * NM, (p3[0] - ox) * NM, (p3[1] - oy) * NM)
        last = p3
    if first is not None:
        path.close()
    return path


def _nudged(shape: object, origin: Point) -> pathops.Path:
    if isinstance(shape, Region):
        return _path(shape.curves(), (origin[0] + 1e-4, origin[1] + 1e-4))
    return _path(shape_curves(shape, 1e-4), origin)


class Region:
    """An area of the plane (µm) with any number of outlines and holes: ``Region.of(*shapes)``
    is their union; ``plus`` and ``minus`` combine regions or shapes. It offers what the
    shapes offer (``contains``, ``outline``, ``bounds``, ``center``) and its exact outlines as
    Bézier pieces (``contours``) for drawing."""

    def __init__(self, path: pathops.Path, origin: Point) -> None:
        self.path, self.origin = path, origin

    @classmethod
    def of(cls, *shapes: object, origin: Point | None = None) -> "Region":
        """The union of ``shapes`` (shapes of the geometry or regions)."""
        if origin is None:
            boxes = [s.bounds() for s in shapes]  # type: ignore[attr-defined]
            origin = ((min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2, (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2) if boxes else (0.0, 0.0)
        return cls(pathops.Path(), origin).plus(*shapes)

    def _local(self, shape: object) -> pathops.Path:
        if isinstance(shape, Region):
            return _path(shape.curves(), self.origin)
        return _path(shape_curves(shape), self.origin)

    def _combine(self, shapes: tuple[object, ...], op: pathops.PathOp) -> "Region":
        builder = pathops.OpBuilder(fix_winding=True, keep_starting_points=False)
        builder.add(self.path, pathops.PathOp.UNION)
        locals_ = [self._local(shape) for shape in shapes]
        for path in locals_:
            builder.add(path, op)
        try:
            return Region(builder.resolve(), self.origin)
        except pathops.PathOpsError:
            pass
        # Skia gives up on some many-shape problems (outlines touching along a stretch): one
        # shape at a time, nudging a shape that still fails by a hair (0.1 nm)
        path = self.path
        for shape, local in zip(shapes, locals_):
            for candidate in (local, _nudged(shape, self.origin)):
                try:
                    path = pathops.op(path, candidate, op, fix_winding=True, keep_starting_points=False)
                    break
                except pathops.PathOpsError:
                    continue
        return Region(path, self.origin)

    def plus(self, *shapes: object) -> "Region":
        """The union with ``shapes``."""
        return self._combine(shapes, pathops.PathOp.UNION) if shapes else self

    def minus(self, *shapes: object) -> "Region":
        """This region without ``shapes``."""
        return self._combine(shapes, pathops.PathOp.DIFFERENCE) if shapes else self

    def times(self, *shapes: object) -> "Region":
        """The part of this region inside every one of ``shapes``."""
        region = self
        for shape in shapes:
            region = region._combine((shape,), pathops.PathOp.INTERSECTION)
        return region

    @property
    def empty(self) -> bool:
        return not list(self.path.contours)

    def contours(self) -> list[list[Cubic]]:
        """Each outline as Bézier pieces in µm (holes run the other way round)."""
        ox, oy = self.origin
        out: list[list[Cubic]] = []
        current: list[Cubic] = []
        pen: Point | None = None
        start: Point | None = None

        def world(p: tuple[float, float]) -> Point:
            return (p[0] / NM + ox, p[1] / NM + oy)

        def straight(a: Point, b: Point) -> Cubic:
            return (a, (a[0] + (b[0] - a[0]) / 3, a[1] + (b[1] - a[1]) / 3), (a[0] + 2 * (b[0] - a[0]) / 3, a[1] + 2 * (b[1] - a[1]) / 3), b)

        for verb, pts in self.path.segments:
            if verb == "moveTo":
                if current:
                    out.append(current)
                current = []
                pen = start = world(pts[0])
            elif verb == "lineTo" and pen is not None:
                q = world(pts[0])
                current.append(straight(pen, q))
                pen = q
            elif verb == "curveTo" and pen is not None:
                a, b, q = (world(p) for p in pts)
                current.append((pen, a, b, q))
                pen = q
            elif verb == "qCurveTo" and pen is not None:
                # quadratic pieces (possibly several, TrueType style) as cubics
                controls = [world(p) for p in pts]
                end = controls[-1]
                ctrls = controls[:-1]
                mids = [((ctrls[i][0] + ctrls[i + 1][0]) / 2, (ctrls[i][1] + ctrls[i + 1][1]) / 2) for i in range(len(ctrls) - 1)]
                ends = [*mids, end]
                for c, e in zip(ctrls, ends):
                    current.append((pen, (pen[0] + 2 / 3 * (c[0] - pen[0]), pen[1] + 2 / 3 * (c[1] - pen[1])),
                                    (e[0] + 2 / 3 * (c[0] - e[0]), e[1] + 2 / 3 * (c[1] - e[1])), e))
                    pen = e
            elif verb in ("closePath", "endPath"):
                if pen is not None and start is not None and math.dist(pen, start) > 1e-12:
                    current.append(straight(pen, start))
                if current:
                    out.append(current)
                current, pen = [], start
        if current:
            out.append(current)
        return out

    def curves(self) -> list[Cubic]:
        return [c for contour in self.contours() for c in contour]

    def contains(self, p: Point, pad: float = 0.0) -> bool:
        inside = self.path.contains(((p[0] - self.origin[0]) * NM, (p[1] - self.origin[1]) * NM))
        if pad == 0.0:
            return bool(inside)
        near = self.distance(p) <= abs(pad)
        return bool(inside or near) if pad > 0 else bool(inside and not near)

    def distance(self, p: Point) -> float:
        """Distance from ``p`` to the nearest outline (sampled)."""
        pts = self.outline(256)
        return min((math.dist(p, q) for q in pts), default=math.inf)

    def outline(self, n: int = 64) -> list[Point]:
        """Points along every outline, about ``n`` in all."""
        contours = self.contours()
        pieces = sum(len(c) for c in contours)
        steps = max(1, math.ceil(n / max(pieces, 1)))
        return [p for contour in contours for p in flatten(contour, steps)]

    def bounds(self) -> Bounds:
        x0, y0, x1, y1 = self.path.bounds
        ox, oy = self.origin
        return (x0 / NM + ox, y0 / NM + oy, x1 / NM + ox, y1 / NM + oy)

    def center(self) -> Point:
        x0, y0, x1, y1 = self.bounds()
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    def area(self) -> float:
        return abs(self.path.area) / NM / NM

    def inset(self, d: float) -> "Region":
        raise NotImplementedError("a region is not inset; build the inner region from inset shapes")
