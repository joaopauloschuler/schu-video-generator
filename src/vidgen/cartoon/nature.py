"""Nature that moves by itself on a stage (DESIGN.md §69.55): the maths, without manim.

A ``tree`` with ``fruit: true`` carries a few fruits (:data:`FRUIT_SPOTS`); the ``drop_fruit``
action lets one fall (:func:`drop_timing`, :func:`drop_point`): it falls faster and faster, hits
the ground (or a character's head) and bounces once before it lies still. A flock of birds
crosses the sky (:class:`FlockPlan`, :func:`flock_birds`, :func:`bird_place`), each bird flapping
its wings (:func:`wing_lift`, :func:`bird_outline`) with a glide now and then. Every number comes
from a seed, so every render is the same.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# ----- fruit ------------------------------------------------------------------------------------------

#: Where a tree's fruits hang (prop units of the tree as drawn facing right: x, y of the middle),
#: in the order they fall when nothing chooses; their radius (prop units).
FRUIT_SPOTS: tuple[tuple[float, float], ...] = ((-0.27, 0.5), (0.28, 0.52), (-0.1, 0.73), (0.13, 0.84))
FRUIT_RADIUS = 0.034
#: A fruit's colours: its skin, the shine on it and its stalk (fixed: no theme token is an apple
#: red in every theme).
FRUIT_COLOR = "#D9473B"
FRUIT_SHINE = "#F6B3A8"
FRUIT_STALK = "#6B4A2B"
#: How fast a dropped fruit falls (frame heights per second squared: a cartoon's gravity), how high
#: it bounces off the ground and off a head (frame heights), how far a head sends it aside (in the
#: heights of that character) and how far it rolls on after a bounce on the ground (frame heights).
FRUIT_GRAVITY = 3.2
GROUND_BOUNCE = 0.05
HEAD_BOUNCE = 0.12
HEAD_ASIDE = 0.4
GROUND_ASIDE = 0.04
#: How many degrees it turns while it bounces (per bounce).
BOUNCE_TURN = 100.0
#: How long the stars circle a head a fruit fell on (s).
HIT_STARS_SECONDS = 1.6


@dataclass(frozen=True)
class DropTiming:
    """How a fruit's drop is timed: its whole ``seconds``, and the share of them at which it hits
    (``impact``: the ground or a head)."""

    seconds: float
    impact: float


def bounce_seconds(height: float, gravity: float = FRUIT_GRAVITY) -> float:
    """Seconds a bounce ``height`` high takes (up and down again) under ``gravity``."""
    return 2.0 * math.sqrt(2.0 * max(height, 0.0) / gravity)


def drop_timing(fall: float, bounce: float, gravity: float = FRUIT_GRAVITY) -> DropTiming:
    """The timing of a drop that falls ``fall`` (frame heights) and bounces ``bounce`` high."""
    falling = math.sqrt(2.0 * max(fall, 1e-6) / gravity)
    total = falling + bounce_seconds(bounce, gravity)
    return DropTiming(total, falling / total)


def drop_point(share: float, start: tuple[float, float], impact: tuple[float, float], end: tuple[float, float], *,
               hit_share: float, bounce: float) -> tuple[float, float, float]:
    """Where a dropped fruit's middle is at ``share`` (0..1) of its drop, and how far it has turned
    (degrees, counterclockwise): from ``start`` it falls with gravity (y ∝ the time squared, x
    straight) to ``impact`` at ``hit_share``, then bounces on a parabola ``bounce`` high (in the
    units of the points) to ``end``, turning :data:`BOUNCE_TURN` degrees the way it goes."""
    u = min(max(share, 0.0), 1.0)
    if u <= hit_share and hit_share > 0:
        s = u / hit_share
        return start[0] + (impact[0] - start[0]) * s, start[1] + (impact[1] - start[1]) * s * s, 0.0
    s = 1.0 if hit_share >= 1.0 else (u - hit_share) / (1.0 - hit_share)
    x = impact[0] + (end[0] - impact[0]) * s
    y = impact[1] + (end[1] - impact[1]) * s + 4.0 * bounce * s * (1.0 - s)
    way = -1.0 if end[0] >= impact[0] else 1.0
    return x, y, way * BOUNCE_TURN * s


def fruit_to_drop(left: list[int], *, near_x: float | None = None, xs: list[float] | None = None) -> int:
    """Which of the fruits ``left`` (indices of :data:`FRUIT_SPOTS`, still on the tree) falls: the
    first, or, with ``near_x``, the one whose x on screen (``xs``, per spot) is nearest it."""
    if not left:
        raise ValueError("no fruit left on the tree")
    if near_x is None or xs is None:
        return left[0]
    return min(left, key=lambda k: (abs(xs[k] - near_x), k))


# ----- birds ------------------------------------------------------------------------------------------

#: A flock: how many birds, how wide a bird is (wing tip to wing tip, frame heights), how fast it
#: flies (frame widths per second), how high it flies (a share of the frame height above the
#: bottom edge), and how often its wings beat (Hz, each bird a little different).
FLOCK_COUNT = 5
BIRD_SPAN = 0.04
FLOCK_SPEED = 0.2
FLOCK_HEIGHT = 0.8
WING_BEATS = (3.0, 4.2)
#: A bird glides (wings held a little up) for this share of each glide cycle of this many seconds.
GLIDE_SHARE = 0.3
GLIDE_SECONDS = 2.6
#: The flock's spacing: how far behind (spans) and above or below (spans) each rank flies, how much
#: each bird is moved off its place by its seed (spans) and how far it bobs up and down (spans).
RANK_BEHIND = 1.3
RANK_ASIDE = 0.55
PLACE_JITTER = 0.35
BOB = 0.25
#: The most birds in one flock.
MAX_BIRDS = 20


def _unit(seed: int, *keys: object) -> float:
    """A number in [0, 1) fixed by ``seed`` and ``keys`` (the same in every run)."""
    return random.Random(":".join(str(k) for k in (seed, *keys))).random()


@dataclass(frozen=True)
class FlockBird:
    """One bird of a flock: its place in the flock relative to the leader (``dx`` behind it,
    ``dy`` up, in bird spans), its wing beat (``rate`` Hz, ``phase`` in turns), its size (a share
    of :data:`BIRD_SPAN`) and when its glides come (``glide_phase``, turns of the glide cycle)."""

    dx: float
    dy: float
    rate: float
    phase: float
    size: float
    glide_phase: float


def flock_birds(count: int, seed: int) -> list[FlockBird]:
    """The birds of a flock of ``count`` in a loose V: the leader first, then one on each side per
    rank, each moved off its place, sized and timed by ``seed``."""
    birds: list[FlockBird] = []
    for k in range(count):
        rank, side = (k + 1) // 2, (1.0 if k % 2 else -1.0)
        dx = rank * RANK_BEHIND + PLACE_JITTER * (2 * _unit(seed, "dx", k) - 1)
        dy = side * rank * RANK_ASIDE + PLACE_JITTER * (2 * _unit(seed, "dy", k) - 1)
        rate = WING_BEATS[0] + (WING_BEATS[1] - WING_BEATS[0]) * _unit(seed, "rate", k)
        size = 0.85 + 0.3 * _unit(seed, "size", k)
        birds.append(FlockBird(dx if k else 0.0, dy if k else 0.0, rate, _unit(seed, "phase", k), size, _unit(seed, "glide", k)))
    return birds


def wing_lift(seconds: float, bird: FlockBird) -> float:
    """How far a bird's wings are up (1) or down (−1) ``seconds`` into its flight: a beat at its
    rate, easing into a glide (wings held at 0.3) for :data:`GLIDE_SHARE` of each glide cycle."""
    beat = math.sin(2.0 * math.pi * (bird.rate * seconds + bird.phase))
    cycle = (seconds / GLIDE_SECONDS + bird.glide_phase) % 1.0
    glide = math.sin(math.pi * cycle / GLIDE_SHARE) if cycle < GLIDE_SHARE else 0.0
    return beat * (1.0 - glide) + 0.3 * glide


def bird_outline(lift: float, span: float = 1.0) -> list[tuple[float, float]]:
    """A bird seen from afar, as the five corners of a stroke from one wing tip over the body to
    the other (``span`` wide, the body at the origin): a V with the wings up (``lift`` 1), an
    upturned V with them down (−1)."""
    half = span / 2.0
    elbow = (0.1 + 0.22 * lift) * half
    tip = (0.55 * lift - 0.05) * half
    return [(-half, tip), (-0.45 * half, elbow), (0.0, -0.06 * half), (0.45 * half, elbow), (half, tip)]


@dataclass(frozen=True)
class FlockPlan:
    """A flock crossing a stage: from scene time ``start`` for ``seconds``, flying ``direction``
    (+1 to the right, −1 to the left) from beyond one edge (``left`` .. ``right``, Manim units) to
    beyond the other at height ``y`` (Manim units), its birds ``span`` wide (Manim units)."""

    start: float
    seconds: float
    direction: float
    left: float
    right: float
    y: float
    span: float
    birds: tuple[FlockBird, ...]

    @property
    def end(self) -> float:
        """When the last bird has left the stage (scene seconds)."""
        return self.start + self.seconds

    def margin(self) -> float:
        """How far beyond the edges the flock starts and ends: its whole length past the edge."""
        behind = max((b.dx for b in self.birds), default=0.0)
        return (behind + 1.0) * self.span

    def flying(self, start: float, end: float) -> bool:
        """Whether the flock is in the air at some time between ``start`` and ``end``."""
        return start <= self.end and end >= self.start


def flock_plan(start: float, *, seconds: float | None, direction: float, left: float, right: float, y: float, span: float,
               count: int, seed: int, frame_width: float) -> FlockPlan:
    """A :class:`FlockPlan` of ``count`` birds (:func:`flock_birds`); ``seconds``: how long it
    takes, default at :data:`FLOCK_SPEED` frame widths a second over the stage and both margins."""
    birds = tuple(flock_birds(count, seed))
    plan = FlockPlan(start, 1.0, 1.0 if direction >= 0 else -1.0, left, right, y, span, birds)
    if seconds is None:
        seconds = (right - left + 2.0 * plan.margin()) / (FLOCK_SPEED * frame_width)
    return FlockPlan(start, float(seconds), plan.direction, left, right, y, span, birds)


def bird_place(plan: FlockPlan, k: int, now: float) -> tuple[float, float, float] | None:
    """Where bird ``k`` of ``plan`` is at scene time ``now`` and how high its wings are: (x, y,
    wing lift), Manim units; ``None`` before the flock sets off and after it has gone."""
    if not plan.start <= now <= plan.end:
        return None
    bird = plan.birds[k]
    share = (now - plan.start) / max(plan.seconds, 1e-9)
    margin = plan.margin()
    lead = plan.left - margin + share * (plan.right - plan.left + 2.0 * margin)
    if plan.direction < 0:
        lead = plan.right + margin - share * (plan.right - plan.left + 2.0 * margin)
    seconds = now - plan.start
    x = lead - plan.direction * bird.dx * plan.span
    y = plan.y + (bird.dy + BOB * math.sin(2.0 * math.pi * (0.5 * seconds + bird.phase))) * plan.span
    return x, y, wing_lift(seconds, bird)


def flock_box(plan: FlockPlan, start: float, end: float, samples: int = 24) -> tuple[float, float, float, float] | None:
    """The box (left, bottom, right, top; Manim units) the flock's birds cover between scene
    times ``start`` and ``end`` (``None``: not flying then), from ``samples`` moments and a bird's
    span around each."""
    a, b = max(start, plan.start), min(end, plan.end)
    if a > b:
        return None
    times = [a + (b - a) * k / max(samples - 1, 1) for k in range(samples)] if b > a else [a]
    places = [p for t in times for k in range(len(plan.birds)) if (p := bird_place(plan, k, t)) is not None]
    reach = plan.span * 1.3
    xs, ys = [p[0] for p in places], [p[1] for p in places]
    return min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach


__all__ = [
    "BIRD_SPAN",
    "FLOCK_COUNT",
    "FLOCK_HEIGHT",
    "FLOCK_SPEED",
    "FRUIT_COLOR",
    "FRUIT_GRAVITY",
    "FRUIT_RADIUS",
    "FRUIT_SHINE",
    "FRUIT_SPOTS",
    "FRUIT_STALK",
    "GROUND_ASIDE",
    "GROUND_BOUNCE",
    "HEAD_ASIDE",
    "HEAD_BOUNCE",
    "HIT_STARS_SECONDS",
    "MAX_BIRDS",
    "DropTiming",
    "FlockBird",
    "FlockPlan",
    "bird_outline",
    "bird_place",
    "bounce_seconds",
    "drop_point",
    "drop_timing",
    "flock_birds",
    "flock_box",
    "flock_plan",
    "fruit_to_drop",
    "wing_lift",
]
