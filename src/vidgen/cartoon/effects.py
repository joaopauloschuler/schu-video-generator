"""Effect symbols over characters (DESIGN.md §69.40), worked out without manim: what each symbol
is made of, where it sits on a character's head and how it moves.

A symbol (:data:`EFFECT_KINDS`: a sweat drop, an anger mark, an idea bulb, a question or
exclamation mark, sleepy Zs, hearts, dizzy stars, a sparkle, a tear) is one or more *pieces*
(:func:`effect_pieces`), each a few outlined shapes drawn from primitives (circles, polygons, thick
paths) in *symbol units*: about 1 tall, centred on the symbol's spot. :func:`effect_spot` places
the symbol by the head's box on screen and which way the character faces (above the head, at its
front or back, on its top corner, round it, or under the eye); :func:`piece_pose` moves each piece
with the seconds since the symbol appeared (a drip, a pulse, rising Zs, orbiting stars...), and
:func:`pop_scale` / :func:`exit_scale` pop it in with a little bounce and shrink it away. Shapes are
never mirrored (a question mark reads the same either way); only where they sit and lean follows
the facing.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from vidgen.cartoon.motion import smoothstep
from vidgen.cartoon.spring import Spring

#: The effect symbols, in the order the docs list them.
EFFECT_KINDS: tuple[str, ...] = ("sweat", "anger", "idea", "question", "exclaim", "sleep", "hearts", "stars", "sparkle", "tear")

#: A box ``(left, bottom, right, top)`` in Manim units (``y`` up).
Box = tuple[float, float, float, float]
#: A point in symbol units.
Point = tuple[float, float]


@dataclass(frozen=True)
class EffectStyle:
    """Where a symbol sits (``spot``: :data:`SPOTS`), its height in head heights (``size``) and
    its colour (a theme token; ``vidgen`` themes all define it)."""

    spot: str
    size: float
    color: str


#: Where a symbol may sit on the head: ``above`` it, at its ``front`` (the way it faces) or
#: ``back`` near the top, on its front top ``corner``, in a ``ring`` round its top, or under its
#: ``eye``.
SPOTS: tuple[str, ...] = ("above", "front", "back", "corner", "ring", "eye")
#: Each symbol's style.
EFFECT_STYLES: dict[str, EffectStyle] = {
    "sweat": EffectStyle("back", 0.32, "primary"),
    "anger": EffectStyle("corner", 0.34, "accent"),
    "idea": EffectStyle("above", 0.55, "highlight"),
    "question": EffectStyle("above", 0.6, "secondary"),
    "exclaim": EffectStyle("above", 0.6, "accent"),
    "sleep": EffectStyle("front", 0.7, "primary"),
    "hearts": EffectStyle("above", 0.5, "accent"),
    "stars": EffectStyle("ring", 0.7, "highlight"),
    "sparkle": EffectStyle("front", 0.6, "highlight"),
    "tear": EffectStyle("eye", 0.2, "primary"),
}
#: Spots tried in turn when the symbol's own would overlap something to keep clear of (a speech
#: bubble); a spot not listed has no other.
ALTERNATE_SPOTS: dict[str, tuple[str, ...]] = {
    "above": ("front", "back"), "front": ("above", "back"), "back": ("above", "front"), "corner": ("front", "back"),
}
#: Gap between the head and a symbol above, in front of or behind it (head heights).
HEAD_GAP = 0.12
#: Where the eye is without an ``eyes`` part: this far forward of the head's middle (head widths)
#: and up from its bottom (head heights).
EYE_FORWARD = 0.25
EYE_UP = 0.55

#: A symbol pops in with a bounce: a spring's step response (``cartoon_motion`` strength 1), or an
#: eased grow over :data:`POP_SECONDS` (strength 0), blended by the strength.
POP_SPRING = Spring.tuned(3.0, 0.35)
POP_SECONDS = 0.25
#: Seconds a symbol takes to shrink away when its effect ends.
EXIT_SECONDS = 0.3
#: Run time (s) of the ``effect`` action: the pop's first swell (the bounce settles after it).
EFFECT_SECONDS = 0.4


@dataclass(frozen=True)
class EffectSpot:
    """Where a symbol is drawn: its middle ``x``, ``y`` and height ``size`` (Manim units), and the
    ``spot`` it took (:data:`SPOTS`)."""

    x: float
    y: float
    size: float
    spot: str

    def box(self) -> Box:
        """The square the symbol about fills."""
        half = self.size / 2
        return (self.x - half, self.y - half, self.x + half, self.y + half)


def _side(facing: str) -> float:
    return 1.0 if facing == "right" else -1.0


def spot_at(spot: str, kind: str, head: Box, facing: str, eye: Sequence[float] | None = None, crown: float | None = None) -> EffectSpot:
    """The ``kind`` symbol at ``spot`` of a head whose box on screen is ``head``, facing
    ``facing``; ``eye``: the eye's middle (``tear``; default: :data:`EYE_FORWARD` / :data:`EYE_UP`);
    ``crown``: the top of a hat, when higher than the head (``above`` and ``ring`` go by it; the
    size always goes by the head)."""
    if spot not in SPOTS:
        raise ValueError(f"unknown spot {spot!r} (spots: {', '.join(SPOTS)})")
    x0, y0, x1, y1 = head
    width, height = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    side, cx = _side(facing), (x0 + x1) / 2
    size = EFFECT_STYLES[kind].size * height
    front, back = (x1, x0) if side > 0 else (x0, x1)
    gap = HEAD_GAP * height
    top = y1 if crown is None else max(y1, crown)
    if spot == "above":
        x, y = cx + side * 0.1 * width, top + gap + size / 2
    elif spot == "front":
        x, y = front + side * (gap + size / 2), y1 - 0.1 * height
    elif spot == "back":
        x, y = back - side * (0.25 * size), y0 + 0.75 * height
    elif spot == "corner":
        x, y = cx + side * 0.3 * width, y1 - 0.08 * height
    elif spot == "ring":
        x, y = cx, top + 0.08 * height
    else:
        ex, ey = (cx + side * EYE_FORWARD * width, y0 + EYE_UP * height) if eye is None else (float(eye[0]), float(eye[1]))
        x, y = ex + side * 0.15 * size, ey - 0.75 * size
    return EffectSpot(x, y, size, spot)


def _overlaps(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def effect_spot(
    kind: str, head: Box, facing: str, *, eye: Sequence[float] | None = None, crown: float | None = None, avoid: Sequence[Box] = (),
) -> EffectSpot:
    """Where the ``kind`` symbol goes on a head with box ``head`` facing ``facing`` (``eye``,
    ``crown``: as :func:`spot_at`): its own spot (:data:`EFFECT_STYLES`), else the first of
    :data:`ALTERNATE_SPOTS` whose box overlaps none of ``avoid`` (a speech bubble), else its own
    spot anyway."""
    if kind not in EFFECT_STYLES:
        raise ValueError(f"unknown effect {kind!r} (effects: {', '.join(EFFECT_KINDS)})")
    own = EFFECT_STYLES[kind].spot
    for spot in (own, *ALTERNATE_SPOTS.get(own, ())):
        placed = spot_at(spot, kind, head, facing, eye, crown)
        if not any(_overlaps(placed.box(), box) for box in avoid):
            return placed
    return spot_at(own, kind, head, facing, eye, crown)


# ----- timing ------------------------------------------------------------------------------------


def pop_scale(seconds: float, strength: float = 1.0) -> float:
    """How big a symbol is (1: its size) ``seconds`` after it appeared: a spring that overshoots
    and settles at ``cartoon_motion`` ``strength`` 1, an eased grow at 0."""
    if seconds <= 0:
        return 0.0
    grow = smoothstep(min(seconds / POP_SECONDS, 1.0))
    return (1.0 - strength) * grow + strength * POP_SPRING.step_response(seconds)


def exit_scale(seconds: float) -> float:
    """How big a leaving symbol is ``seconds`` after its effect ended (1 down to 0)."""
    return 1.0 - smoothstep(min(max(seconds, 0.0) / EXIT_SECONDS, 1.0))


# ----- pieces and shapes ------------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectShape:
    """One closed outline (``points``, symbol units, counterclockwise) of a piece, its ``fill``
    (``main``: the symbol's colour, ``shine``: a white highlight, ``base``: a grey metal) and
    whether it gets the ink outline."""

    points: tuple[Point, ...]
    fill: str = "main"
    outline: bool = True


@dataclass(frozen=True)
class EffectPiece:
    """A part of a symbol that moves on its own: its middle (``x`` forward, ``y`` up) and height
    ``size`` in symbol units, and its shapes, drawn about 1 tall about the origin."""

    x: float
    y: float
    size: float
    shapes: tuple[EffectShape, ...]


@dataclass(frozen=True)
class PiecePose:
    """A piece's move at a moment: ``dx`` (forward), ``dy`` (symbol units), ``scale`` and a turn
    ``angle`` (degrees, counterclockwise as drawn facing right)."""

    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    angle: float = 0.0


def _circle(cx: float, cy: float, r: float, n: int = 36) -> tuple[Point, ...]:
    return tuple((cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n))


def _ellipse(cx: float, cy: float, rx: float, ry: float, angle: float = 0.0, n: int = 28) -> tuple[Point, ...]:
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    found = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        found.append((cx + x * c - y * s, cy + x * s + y * c))
    return tuple(found)


def _star(points: int, outer: float, inner: float, turn: float = 90.0) -> tuple[Point, ...]:
    found = []
    for k in range(2 * points):
        r = outer if k % 2 == 0 else inner
        a = math.radians(turn) + math.pi * k / points
        found.append((r * math.cos(a), r * math.sin(a)))
    return tuple(found)


def _arc(cx: float, cy: float, r: float, start: float, end: float, n: int = 24) -> list[Point]:
    """Points along a circle from angle ``start`` to ``end`` (degrees, either way)."""
    return [(cx + r * math.cos(math.radians(start + (end - start) * k / n)), cy + r * math.sin(math.radians(start + (end - start) * k / n)))
            for k in range(n + 1)]


def _signed_area(points: Sequence[Point]) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, [*points[1:], points[0]]))


def _counterclockwise(points: Sequence[Point]) -> tuple[Point, ...]:
    return tuple(points) if _signed_area(points) >= 0 else tuple(reversed(points))


def thick_path(points: Sequence[Point], width: float, *, miter_limit: float = 2.0) -> tuple[Point, ...]:
    """The outline of an open path ``points`` drawn ``width`` wide with square ends (the left
    side forward, the right side back; corners mitred up to ``miter_limit`` half widths):
    a stroke turned into a shape, so it fills and outlines like the others."""
    if len(points) < 2:
        raise ValueError("a path needs two points or more")
    half = width / 2
    normals = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = math.hypot(x1 - x0, y1 - y0) or 1e-9
        normals.append((-(y1 - y0) / length, (x1 - x0) / length))
    left, right = [], []
    for k, (x, y) in enumerate(points):
        a = normals[max(k - 1, 0)]
        b = normals[min(k, len(normals) - 1)]
        nx, ny = a[0] + b[0], a[1] + b[1]
        norm = math.hypot(nx, ny) or 1e-9
        nx, ny = nx / norm, ny / norm
        reach = min(half / max(nx * b[0] + ny * b[1], 1e-9), miter_limit * half)
        left.append((x + nx * reach, y + ny * reach))
        right.append((x - nx * reach, y - ny * reach))
    return _counterclockwise([*left, *reversed(right)])


def _drop() -> tuple[Point, ...]:
    """A drop, its point up: ``x = 0.42 sin t sin(t/2)``, ``y = 0.5 cos t``."""
    return _counterclockwise([(0.42 * math.sin(t) * math.sin(t / 2), 0.5 * math.cos(t)) for t in (2 * math.pi * k / 40 for k in range(40))])


def _heart() -> tuple[Point, ...]:
    raw = [(16 * math.sin(t) ** 3, 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
           for t in (2 * math.pi * k / 48 for k in range(48))]
    ys = [y for _, y in raw]
    scale, mid = 1.0 / (max(ys) - min(ys)), (max(ys) + min(ys)) / 2
    return _counterclockwise([(x * scale, (y - mid) * scale) for x, y in raw])


def _shine(cx: float, cy: float, rx: float, ry: float, angle: float = 0.0) -> EffectShape:
    return EffectShape(_counterclockwise(_ellipse(cx, cy, rx, ry, angle)), "shine", outline=False)


def _main(points: Sequence[Point]) -> EffectShape:
    return EffectShape(_counterclockwise(points))


def _piece(x: float, y: float, size: float, *shapes: EffectShape) -> EffectPiece:
    return EffectPiece(x, y, size, tuple(shapes))


def _anger_mark() -> tuple[EffectShape, ...]:
    """Four bands, each an arc bowing towards the middle, round a gap: a cross of curved ticks."""
    shapes = []
    for k in range(4):
        angle = 45.0 + 90.0 * k
        cx, cy = 0.62 * math.cos(math.radians(angle)), 0.62 * math.sin(math.radians(angle))
        facing_in = angle + 180.0
        outer = _arc(cx, cy, 0.42, facing_in - 40, facing_in + 40, 12)
        inner = _arc(cx, cy, 0.24, facing_in + 40, facing_in - 40, 12)
        shapes.append(_main([*outer, *inner]))
    return tuple(shapes)


def _bulb() -> tuple[EffectShape, ...]:
    glass = _main(_circle(0.0, 0.14, 0.3))
    neck = EffectShape(_counterclockwise([(-0.15, -0.1), (0.15, -0.1), (0.12, -0.34), (-0.12, -0.34)]), "base")
    return glass, neck, _shine(-0.1, 0.24, 0.07, 0.12, -30)


def _rays() -> tuple[EffectShape, ...]:
    shapes = []
    for angle in (30.0, 60.0, 90.0, 120.0, 150.0):
        a = math.radians(angle)
        start, end = (0.4 * math.cos(a), 0.14 + 0.4 * math.sin(a)), (0.55 * math.cos(a), 0.14 + 0.55 * math.sin(a))
        shapes.append(EffectShape(thick_path([start, end], 0.07)))
    return tuple(shapes)


def _question() -> tuple[EffectShape, ...]:
    hook = [*_arc(0.0, 0.2, 0.22, 165, -40, 20), (0.08, -0.02), (0.03, -0.09), (0.03, -0.18)]
    return _main(thick_path(hook, 0.13)), _main(_circle(0.03, -0.37, 0.08, 24))


def _exclaim() -> tuple[EffectShape, ...]:
    return _main([(-0.14, 0.5), (0.14, 0.5), (0.06, -0.16), (-0.06, -0.16)]), _main(_circle(0.0, -0.38, 0.1, 24))


def _zed() -> tuple[EffectShape, ...]:
    """A Z: a top bar, a diagonal down to the left and a bottom bar, as one outline."""
    return (_main([(-0.4, -0.5), (0.4, -0.5), (0.4, -0.29), (-0.06, -0.29), (0.4, 0.29), (0.4, 0.5), (-0.4, 0.5), (-0.4, 0.29),
                   (0.06, 0.29), (-0.4, -0.29)]),)


@lru_cache(maxsize=None)
def effect_pieces(kind: str) -> tuple[EffectPiece, ...]:
    """The pieces of the ``kind`` symbol, as drawn facing right."""
    heart = (_main(_heart()), _shine(-0.2, 0.18, 0.07, 0.11, 30))
    star = (_main(_star(5, 0.5, 0.22)),)
    sparkle = (_main(_star(4, 0.5, 0.14)),)
    pieces: dict[str, tuple[EffectPiece, ...]] = {
        "sweat": (_piece(0.0, 0.0, 1.0, _main(_drop()), _shine(-0.06, -0.18, 0.06, 0.1, 15)),),
        "anger": (_piece(0.0, 0.0, 1.0, *_anger_mark()),),
        "idea": (_piece(0.0, 0.0, 1.0, *_rays()), _piece(0.0, 0.0, 1.0, *_bulb())),
        "question": (_piece(0.0, 0.0, 1.0, *_question()),),
        "exclaim": (_piece(0.0, 0.0, 1.0, *_exclaim()),),
        "sleep": tuple(_piece(0.0, 0.0, 0.5, *_zed()) for _ in range(3)),
        "hearts": (_piece(-0.34, -0.08, 0.45, *heart), _piece(0.06, 0.22, 0.55, *heart), _piece(0.4, -0.12, 0.4, *heart)),
        "stars": tuple(_piece(0.0, 0.0, 0.42, *star) for _ in range(3)),
        "sparkle": (_piece(-0.1, 0.12, 0.8, *sparkle), _piece(0.35, -0.3, 0.5, *sparkle)),
        "tear": (_piece(0.0, 0.0, 1.0, _main(_drop()), _shine(-0.06, -0.18, 0.06, 0.1, 15)),),
    }
    if kind not in pieces:
        raise ValueError(f"unknown effect {kind!r} (effects: {', '.join(EFFECT_KINDS)})")
    return pieces[kind]


def _cycle(seconds: float, period: float, offset: float = 0.0) -> float:
    return (seconds / period + offset) % 1.0


def piece_pose(kind: str, index: int, seconds: float) -> PiecePose:
    """How piece ``index`` of the ``kind`` symbol has moved ``seconds`` after it appeared (as drawn
    facing right): a sweat drop slides down, an anger mark and an idea's rays pulse, a question
    mark rocks, an exclamation mark shakes and calms, Zs rise and fade in turn, hearts bob,
    stars circle the head, sparkles twinkle, a tear runs down the cheek and forms again."""
    t = max(seconds, 0.0)
    if kind == "sweat":
        return PiecePose(dy=-0.25 * smoothstep(min(t / 1.5, 1.0)), angle=15.0)
    if kind == "anger":
        return PiecePose(scale=1.0 + 0.12 * abs(math.sin(2 * math.pi * 1.4 * t)))
    if kind == "idea":
        return PiecePose(scale=0.85 + 0.15 * abs(math.sin(2 * math.pi * 1.2 * t))) if index == 0 else PiecePose()
    if kind == "question":
        return PiecePose(angle=10.0 * math.sin(2 * math.pi * t / 1.3))
    if kind == "exclaim":
        return PiecePose(angle=8.0 * math.exp(-t / 0.5) * math.sin(2 * math.pi * 5.0 * t))
    if kind == "sleep":
        u = _cycle(t, 2.4, index / 3)
        grow = min(1.0, 6.0 * u) * min(1.0, 4.0 * (1.0 - u))
        return PiecePose(dx=-0.3 + 0.6 * u, dy=-0.35 + 0.7 * u, scale=(0.5 + 0.6 * u) * grow, angle=-8.0)
    if kind == "hearts":
        phase = index / 3
        return PiecePose(dy=0.06 * math.sin(2 * math.pi * (t / 1.3 + phase)), scale=1.0 + 0.08 * math.sin(2 * math.pi * (t / 0.65 + phase)))
    if kind == "stars":
        theta = 2 * math.pi * _cycle(t, 1.6, index / 3)
        return PiecePose(dx=0.6 * math.cos(theta), dy=0.15 * math.sin(theta), scale=0.85 + 0.15 * math.sin(theta), angle=120.0 * t)
    if kind == "sparkle":
        return PiecePose(scale=0.55 + 0.45 * abs(math.cos(math.pi * (t / 0.8 + index / 2))), angle=30.0 * t)
    if kind == "tear":
        u = _cycle(t, 2.0)
        grow = smoothstep(min(5.0 * u, 1.0)) * (1.0 - smoothstep(max((u - 0.75) / 0.25, 0.0)))
        return PiecePose(dy=-1.2 * u ** 1.5, scale=grow)
    raise ValueError(f"unknown effect {kind!r} (effects: {', '.join(EFFECT_KINDS)})")


def piece_center(kind: str, index: int, seconds: float, facing: str) -> Point:
    """Where piece ``index``'s middle is (symbol units from the spot), its home moved by its
    pose, forward mirrored for ``facing``."""
    piece = effect_pieces(kind)[index]
    pose = piece_pose(kind, index, seconds)
    return (_side(facing) * (piece.x + pose.dx), piece.y + pose.dy)


#: The expression changes ``auto_direct`` marks with a symbol (DESIGN.md §69.40).
EXPRESSION_EFFECTS: dict[str, str] = {"surprised": "exclaim", "thinking": "question", "angry": "anger"}
