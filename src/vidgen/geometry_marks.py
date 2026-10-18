"""Geometry marks in frame coordinates: a brace along a segment, an angle arc (a square at 90°)
and a dimension line, each with an optional label placed outside it (exported by ``vidgen.api``).

``function_plot`` draws them on its plane (data points mapped to the frame first) and a project's
own scene can draw the same marks on anything (DESIGN §87.7). The builders take Manim points and
a label mobject (already made, e.g. with ``T``), and return a :class:`GeometryMark` whose label
has been moved into place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from manim import Arc, BraceBetweenPoints, Line, Mobject, VGroup, VMobject

from vidgen.helpers import resolve_color

#: Gap (units) between a mark and its label.
LABEL_GAP = 0.12
#: Default radius (units) of an angle arc; it shrinks on short rays.
ANGLE_RADIUS = 0.55
#: An angle within this many degrees of 90 is drawn as a right-angle square.
RIGHT_ANGLE_TOLERANCE = 0.5
#: How far (units) a dimension line sits beside its segment, and the length of its end bars.
DIMENSION_OFFSET, DIMENSION_BAR = 0.35, 0.2


@dataclass
class GeometryMark:
    """A mark: ``shape`` (the brace, arc or line) and ``label`` (placed, or ``None``);
    ``group`` holds both."""

    shape: VMobject
    label: Mobject | None = None
    group: VGroup = field(default_factory=VGroup)


def _xy(point: Sequence[float] | np.ndarray) -> np.ndarray:
    p = np.asarray(point, dtype=float)
    return np.array([p[0], p[1], 0.0])


def segment_normal(start: Sequence[float], end: Sequence[float], away_from: Sequence[float] | None = None) -> np.ndarray:
    """A unit normal of the segment ``start`` -> ``end``: the one pointing away from
    ``away_from`` (e.g. the middle of a figure, so a brace goes outside it); without it, or when
    the segment runs through that point, the one pointing down (left on a vertical segment)."""
    a, b = _xy(start), _xy(end)
    d = b - a
    length = float(np.linalg.norm(d[:2]))
    if length < 1e-9:
        return np.array([0.0, -1.0, 0.0])
    normal = np.array([-d[1], d[0], 0.0]) / length
    if away_from is not None:
        side = float(np.dot(normal[:2], ((a + b) / 2 - _xy(away_from))[:2]))
        if abs(side) > 1e-6:
            return normal if side > 0 else -normal
    if normal[1] > 1e-9 or (abs(normal[1]) <= 1e-9 and normal[0] > 0):
        normal = -normal
    return normal


def _put_label(label: Mobject, anchor: np.ndarray, direction: np.ndarray, gap: float = LABEL_GAP) -> None:
    """Move ``label`` beside ``anchor``, its nearest edge ``gap`` away along ``direction``."""
    d = direction / (np.linalg.norm(direction) or 1.0)
    reach = gap + 0.5 * (abs(d[0]) * label.width + abs(d[1]) * label.height)
    label.move_to(anchor + d * reach)


def _group(shape: VMobject, label: Mobject | None) -> GeometryMark:
    return GeometryMark(shape, label, VGroup(shape, *([label] if label is not None else [])))


def brace_mark(
    start: Sequence[float], end: Sequence[float], *, label: Mobject | None = None, normal: Sequence[float] | None = None,
    color: str = "text", buff: float = 0.1,
) -> GeometryMark:
    """A curly brace beside the segment ``start`` -> ``end`` on the side of ``normal`` (default:
    :func:`segment_normal`), its ``label`` beyond its tip."""
    a, b = _xy(start), _xy(end)
    n = _xy(normal) if normal is not None else segment_normal(a, b)
    n = n / (np.linalg.norm(n) or 1.0)
    brace = BraceBetweenPoints(a, b, direction=n, buff=buff, color=resolve_color(color))
    if label is not None:
        _put_label(label, brace.get_tip(), n)
    return _group(brace, label)


def angle_between(vertex: Sequence[float], start: Sequence[float], end: Sequence[float]) -> tuple[float, float]:
    """``(start angle, sweep)`` in radians of the angle at ``vertex`` from the ray to ``start``
    to the ray to ``end``: the smaller one (sweep in ``(-pi, pi]``, positive counter-clockwise)."""
    v, a, b = _xy(vertex), _xy(start), _xy(end)
    first = float(np.arctan2(a[1] - v[1], a[0] - v[0]))
    second = float(np.arctan2(b[1] - v[1], b[0] - v[0]))
    sweep = (second - first + np.pi) % (2 * np.pi) - np.pi
    if sweep <= -np.pi + 1e-12:
        sweep = np.pi
    return first, sweep


def angle_mark(
    vertex: Sequence[float], start: Sequence[float], end: Sequence[float], *, label: Mobject | None = None,
    radius: float = ANGLE_RADIUS, color: str = "text", right_angle: bool | None = None, stroke_width: float = 4.0,
) -> GeometryMark:
    """The angle at ``vertex`` between the rays to ``start`` and ``end`` (the smaller one): an
    arc of ``radius`` (at most 40 % of the shorter ray), or a small square when it is a right angle
    (``right_angle``; default: within :data:`RIGHT_ANGLE_TOLERANCE` degrees of 90); its ``label``
    outside it on the bisector."""
    v = _xy(vertex)
    rays = [_xy(start) - v, _xy(end) - v]
    shortest = min(float(np.linalg.norm(r[:2])) for r in rays)
    r = max(0.12, min(radius, 0.4 * shortest)) if shortest > 1e-9 else radius
    first, sweep = angle_between(v, start, end)
    is_right = right_angle if right_angle is not None else abs(abs(np.degrees(sweep)) - 90) <= RIGHT_ANGLE_TOLERANCE
    ink = resolve_color(color)
    u1 = np.array([np.cos(first), np.sin(first), 0.0])
    u2 = np.array([np.cos(first + sweep), np.sin(first + sweep), 0.0])
    if is_right:
        side = r * 0.7
        shape = VMobject(stroke_color=ink, stroke_width=stroke_width).set_points_as_corners([v + u1 * side, v + (u1 + u2) * side, v + u2 * side])
        reach = side * np.sqrt(2)
    else:
        shape = Arc(radius=r, start_angle=first, angle=sweep, arc_center=v, color=ink, stroke_width=stroke_width)
        reach = r
    if label is not None:
        bisector = np.array([np.cos(first + sweep / 2), np.sin(first + sweep / 2), 0.0])
        _put_label(label, v + bisector * reach, bisector)
    return _group(shape, label)


def dimension_mark(
    start: Sequence[float], end: Sequence[float], *, label: Mobject | None = None, normal: Sequence[float] | None = None,
    offset: float = DIMENSION_OFFSET, color: str = "dim", stroke_width: float = 2.5,
) -> GeometryMark:
    """A dimension line: the segment ``start`` -> ``end`` drawn ``offset`` beside it on the side of
    ``normal`` (default: :func:`segment_normal`), with end bars across it and thin extension lines
    back to the ends; its ``label`` beside its middle, outside."""
    a, b = _xy(start), _xy(end)
    n = _xy(normal) if normal is not None else segment_normal(a, b)
    n = n / (np.linalg.norm(n) or 1.0)
    ink = resolve_color(color)
    p, q = a + n * offset, b + n * offset
    half = n * DIMENSION_BAR / 2
    shape = VGroup(
        Line(p, q, color=ink, stroke_width=stroke_width),
        Line(p - half, p + half, color=ink, stroke_width=stroke_width),
        Line(q - half, q + half, color=ink, stroke_width=stroke_width),
        Line(a + n * 0.06, p + half, color=ink, stroke_width=stroke_width * 0.5, stroke_opacity=0.6),
        Line(b + n * 0.06, q + half, color=ink, stroke_width=stroke_width * 0.5, stroke_opacity=0.6),
    )
    if label is not None:
        _put_label(label, (p + q) / 2 + half, n, gap=0.08)
    return _group(shape, label)
