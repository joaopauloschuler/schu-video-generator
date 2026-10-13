"""Props that move by themselves (DESIGN.md §69.54, §69.55): the maths, without manim.

A wall ``clock`` that runs turns its hands from the scene clock (:func:`clock_seconds`,
:func:`hand_angles`); a ``tv`` that is on shows a picture that changes every second or two and
flickers (:func:`tv_picture`); a ``lamp`` that is on glows (:data:`GLOWS`, :func:`glow_rings`); a
``fireplace`` that is on burns, its flames flickering and leaning with the wind
(:func:`flame_shapes`, :func:`fire_flicker`); a ``kettle`` that is on steams (:func:`steam_puffs`).
These are on or off from the start and the ``switch_on`` / ``switch_off`` actions change them
(:func:`switched_on`, :func:`on_spans`). Only what changes is redrawn on each frame: the moving
parts and what is drawn over them (:func:`redrawn_members`); the rest of the set stays in Manim's
static image (§69.20).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

#: The props a ``switch_on`` / ``switch_off`` action and the stage key ``on`` act on.
SWITCHED_PROPS: tuple[str, ...] = ("fireplace", "kettle", "lamp", "tv")
#: The props that can move by themselves: a running clock and the switched ones.
LIVING_KINDS: tuple[str, ...] = ("clock", *SWITCHED_PROPS)
#: The attribute naming a living part of a prop's drawing (``hour``, ``minute``, ``second``,
#: ``picture``, ``lantern``, ``flame``).
LIVING_PART = "living_part"
#: The time the clock's drawing shows (10:10), seconds after midnight: a running clock starts there
#: unless it has a ``time``.
DRAWN_CLOCK_SECONDS = 10 * 3600 + 10 * 60
#: The fastest a clock may run (clock seconds per scene second: an hour a second).
MAX_CLOCK_SPEED = 3600.0
#: Up to this speed a running clock shows a second hand (faster, it would only blur).
SECOND_HAND_MAX_SPEED = 10.0
#: A television's picture: how often its brightness flickers (s), how dark the darkest flicker is
#: (a share taken off), and the shortest and longest time one picture lasts (s).
FLICKER_STEP = 1.0 / 12.0
FLICKER_DEPTH = 0.22
TV_SHOT_SECONDS = 1.8
TV_SHOT_JITTER = 0.8
#: A television picture's colours, (sky, ground, left shape, right shape) per picture: simple
#: screen colours, none of them a programme or channel of any kind.
TV_PALETTES: tuple[tuple[str, str, str, str], ...] = (
    ("#7EC8F0", "#6FBF73", "#F6D55C", "#ED553B"),
    ("#2E4A7D", "#3B6E8F", "#F2E8C9", "#9AD1D4"),
    ("#F7B267", "#F4845F", "#5D2E46", "#F25C54"),
    ("#B8E0D2", "#95B8D1", "#EAC4D5", "#809BCE"),
    ("#E9F5DB", "#97A97C", "#FFB4A2", "#6D6875"),
    ("#FFD6A5", "#CAFFBF", "#9BF6FF", "#FFADAD"),
)
#: How many rings make a glow (more: smoother).
GLOW_RINGS = 12

#: A box on screen: left, bottom, right, top (Manim units).
Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class GlowSpec:
    """A glow around a prop: its middle (``x``, ``y``) and ``radius`` in prop units as drawn
    facing right, its ``color`` and its ``opacity`` at the middle."""

    x: float
    y: float
    radius: float
    color: str
    opacity: float


#: The glow of each prop that glows when on: a lamp's warm light around its lantern, a
#: television's cool light around its screen, a fireplace's orange light around its fire.
GLOWS: dict[str, GlowSpec] = {
    "lamp": GlowSpec(0.0, 0.86, 0.42, "#FFD67A", 0.55),
    "tv": GlowSpec(0.0, 0.7, 0.8, "#A8D8FF", 0.3),
    "fireplace": GlowSpec(0.0, 0.32, 1.05, "#FFA94D", 0.5),
}

#: A fireplace's flames (prop units, as drawn facing right): the middle of each outer tongue's
#: foot, its half width and its height at rest; the inner (yellow) tongues are
#: :data:`INNER_FLAME_SHARE` of the outer ones they stand in.
FLAME_FEET: tuple[float, ...] = (-0.27, -0.13, 0.0, 0.13, 0.27)
FLAME_HALF_WIDTH = 0.1
FLAME_HEIGHTS: tuple[float, ...] = (0.2, 0.3, 0.38, 0.29, 0.21)
FLAME_BASE = 0.12
INNER_FLAME_SHARE = 0.55
#: How much a tongue's height flickers (a share either way), how far its tip wavers sideways
#: (prop units) and the corners of each tongue's outline per side.
FLAME_FLICKER = 0.28
FLAME_WAVER = 0.035
FLAME_CORNERS = 9
#: How far the flames' tips lean at felt wind force 1 (prop units; :func:`flame_lean`), at most.
FLAME_LEAN = 0.22
FLAME_LEAN_MAX = 0.3
#: A fire's glow: its strength flickers between ``1 − FIRE_GLOW_FLICKER`` and 1.
FIRE_GLOW_FLICKER = 0.25
#: A kettle's steam (prop units, as drawn facing right): where it leaves the spout, how many
#: puffs rise at a time, how long one takes to rise (s), how high it rises, the puffs' radius as
#: they leave and as they fade, their opacity at the most, and how far it drifts at felt wind
#: force 1 (at the top).
STEAM_SPOUT = (0.66, 0.68)
STEAM_PUFFS = 6
STEAM_SECONDS = 2.2
STEAM_RISE = 2.0
STEAM_RADIUS = (0.08, 0.3)
STEAM_OPACITY = 0.85
STEAM_LEAN = 0.9
STEAM_LEAN_MAX = 1.2


@lru_cache(maxsize=256)
def _noise_terms(seed: int, keys: tuple[object, ...]) -> tuple[tuple[float, float, float], ...]:
    """(weight, rate in Hz, phase in turns) of the three sines of :func:`_noise`."""
    return tuple((weight, 1.3 + 3.7 * _unit(seed, *keys, "rate", k), _unit(seed, *keys, "phase", k)) for k, weight in enumerate((0.5, 0.3, 0.2)))


def _noise(now: float, seed: int, *keys: object) -> float:
    """A smooth wobble in [-1, 1] at scene time ``now``: three sines whose rates (1.3 to 5 Hz) and
    phases are fixed by ``seed`` and ``keys``."""
    return sum(weight * math.sin(2.0 * math.pi * (rate * now + phase)) for weight, rate, phase in _noise_terms(seed, keys))


# ----- clocks -----------------------------------------------------------------------------------


def parse_clock_time(text: str) -> float:
    """``H:MM`` or ``H:MM:SS`` (0:00 to 23:59:59) as seconds after midnight; :class:`ValueError`
    for anything else."""
    parts = str(text).strip().split(":")
    message = f"time {text!r} is not a clock time: write H:MM or H:MM:SS, e.g. 10:10 or 21:45:30"
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts) or any(len(p) != 2 for p in parts[1:]):
        raise ValueError(message)
    hours, minutes, seconds = (int(p) for p in [*parts, "0"][:3])
    if hours > 23 or minutes > 59 or seconds > 59:
        raise ValueError(message)
    return float(hours * 3600 + minutes * 60 + seconds)


def clock_seconds(start: float, speed: float, scene_time: float) -> float:
    """The time a clock shows (seconds after midnight) ``scene_time`` seconds into its scene, when
    it showed ``start`` at the scene's start and runs ``speed`` times as fast as real time."""
    return start + speed * scene_time


@dataclass(frozen=True)
class HandAngles:
    """Where a clock's hands point: degrees clockwise from twelve o'clock."""

    hour: float
    minute: float
    second: float


def hand_angles(seconds: float) -> HandAngles:
    """The hands of a clock showing ``seconds`` after midnight (the hour hand goes round twice a
    day, moving on between the hours)."""
    return HandAngles((seconds / 43200.0 * 360.0) % 360.0, (seconds / 3600.0 * 360.0) % 360.0, (seconds / 60.0 * 360.0) % 360.0)


def hand_tip(x: float, y: float, length: float, degrees: float) -> tuple[float, float]:
    """The tip of a hand ``length`` long from (``x``, ``y``) pointing ``degrees`` clockwise from
    straight up (y up, as on screen)."""
    angle = math.radians(degrees)
    return x + length * math.sin(angle), y + length * math.cos(angle)


def shows_second_hand(speed: float) -> bool:
    """Whether a clock running at ``speed`` shows a second hand."""
    return 0.0 < speed <= SECOND_HAND_MAX_SPEED


# ----- switching on and off ---------------------------------------------------------------------


def switched_on(on_at_start: bool, switches: Sequence[tuple[float, bool]], now: float) -> bool:
    """Whether a prop is on at scene time ``now``: on or off from the start, then each switch
    (scene time, on) from its time on; the last switch at or before ``now`` wins (in the order
    given when two fall at once)."""
    state = on_at_start
    for _, on in sorted((s for s in switches if s[0] <= now), key=lambda s: s[0]):
        state = on
    return state


def switch_between(switches: Sequence[tuple[float, bool]], start: float, end: float) -> bool:
    """Whether a switch falls between scene times ``start`` and ``end`` (both included)."""
    return any(start <= time <= end for time, _ in switches)


def on_between(on_at_start: bool, switches: Sequence[tuple[float, bool]], start: float, end: float) -> bool:
    """Whether a prop is on at any time between scene times ``start`` and ``end``."""
    return switched_on(on_at_start, switches, start) or any(on and start <= time <= end for time, on in switches)


def on_spans(on_at_start: bool, switches: Sequence[tuple[float, bool]], end: float) -> list[tuple[float, float]]:
    """The spans (start, end scene seconds) from 0 to ``end`` while a prop is on (a fireplace's
    crackle plays then)."""
    spans: list[tuple[float, float]] = []
    since = 0.0 if on_at_start else None
    for time, on in sorted(switches, key=lambda s: s[0]):
        time = min(max(float(time), 0.0), end)
        if on and since is None:
            since = time
        elif not on and since is not None:
            spans.append((since, time))
            since = None
    if since is not None:
        spans.append((since, end))
    return [(a, b) for a, b in spans if b > a]


# ----- a television's picture -------------------------------------------------------------------


def _unit(seed: int, *keys: object) -> float:
    """A number in [0, 1) fixed by ``seed`` and ``keys`` (the same in every run)."""
    return random.Random(":".join(str(k) for k in (seed, *keys))).random()


def _shot_start(seed: int, index: int) -> float:
    """When picture ``index`` begins (picture 0 at 0; each later one near ``index`` ×
    :data:`TV_SHOT_SECONDS`, moved by up to half the jitter either way, so they stay in order)."""
    if index <= 0:
        return 0.0
    return index * TV_SHOT_SECONDS + (_unit(seed, "shot", index) - 0.5) * TV_SHOT_JITTER


def tv_shot(now: float, seed: int) -> int:
    """Which picture a television that is on shows at scene time ``now`` (0, 1, 2, ...)."""
    if now <= 0:
        return 0
    index = int(now // TV_SHOT_SECONDS)
    while index > 0 and _shot_start(seed, index) > now:
        index -= 1
    while _shot_start(seed, index + 1) <= now:
        index += 1
    return index


def tv_flicker(now: float, seed: int) -> float:
    """How bright a television's picture is at scene time ``now``: 1 at full, down to
    1 − :data:`FLICKER_DEPTH`, changing every :data:`FLICKER_STEP` seconds."""
    step = math.floor(now / FLICKER_STEP)
    return 1.0 - FLICKER_DEPTH * _unit(seed, "flicker", step) ** 2


@dataclass(frozen=True)
class TvPicture:
    """A television's picture at one moment: which picture (``shot``), its four colours (sky,
    ground, left shape, right shape; #hex) and its ``brightness`` (0..1)."""

    shot: int
    colors: tuple[str, str, str, str]
    brightness: float


def tv_picture(now: float, seed: int) -> TvPicture:
    """The picture of a television that is on, at scene time ``now`` (``seed``: its own, so two
    televisions differ)."""
    shot = tv_shot(now, seed)
    palette = TV_PALETTES[int(_unit(seed, "palette", shot) * len(TV_PALETTES))]
    return TvPicture(shot, palette, tv_flicker(now, seed))


# ----- a fire's flames and a kettle's steam ------------------------------------------------------


def flame_lean(force: float) -> float:
    """How far (prop units, + to the right) the flames' tips lean under the signed felt wind
    ``force`` (:func:`~vidgen.cartoon.wind.felt_force`; 0 indoors)."""
    return min(max(FLAME_LEAN * force, -FLAME_LEAN_MAX), FLAME_LEAN_MAX)


@dataclass(frozen=True)
class FlameShape:
    """One tongue of a fire: its closed outline (prop units, as drawn facing right; from the left
    of its foot up to its tip and down to the right) and whether it is an ``inner`` (yellow) one."""

    points: tuple[tuple[float, float], ...]
    inner: bool


def _tongue(x: float, half: float, height: float, tip_shift: float, waver: float) -> tuple[tuple[float, float], ...]:
    """A tongue's outline: widest a fifth of the way up, pointed at the top, its middle bending to
    ``tip_shift`` at the tip (quadratically) with a ``waver`` that grows towards the tip."""
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for k in range(FLAME_CORNERS):
        v = k / (FLAME_CORNERS - 1)
        width = half * (1.0 - v) ** 0.85 * min(1.0, 0.55 + 2.25 * v)
        middle = x + tip_shift * v * v + waver * math.sin(math.pi * v) * v
        y = FLAME_BASE + height * v
        left.append((middle - width, y))
        right.append((middle + width, y))
    return (*left, *reversed(right[:-1]))


def flame_shapes(now: float, seed: int, lean: float = 0.0) -> list[FlameShape]:
    """A fire's tongues at scene time ``now`` (``seed``: its own, so two fires differ; ``lean``:
    :func:`flame_lean`), outer ones first, then the inner ones: each one's height flickers by up
    to :data:`FLAME_FLICKER` and its tip wavers by up to :data:`FLAME_WAVER`, smoothly."""
    shapes: list[FlameShape] = []
    for inner in (False, True):
        for k, (x, height) in enumerate(zip(FLAME_FEET, FLAME_HEIGHTS)):
            if inner and k in (0, len(FLAME_FEET) - 1):
                continue   # the yellow core burns in the middle three
            share = INNER_FLAME_SHARE if inner else 1.0
            tall = height * share * (1.0 + FLAME_FLICKER * _noise(now, seed, "flame", k))
            waver = FLAME_WAVER * _noise(now, seed, "waver", k)
            shapes.append(FlameShape(_tongue(x, FLAME_HALF_WIDTH * share, tall, lean * share, waver), inner))
    return shapes


def fire_flicker(now: float, seed: int) -> float:
    """How strong a fire's glow is at scene time ``now``: 1 − :data:`FIRE_GLOW_FLICKER` to 1,
    smoothly."""
    return 1.0 - FIRE_GLOW_FLICKER * 0.5 * (1.0 - _noise(now, seed, "glow"))


@dataclass(frozen=True)
class SteamPuff:
    """One puff of steam: its middle (``x``, ``y``) and ``radius`` (prop units, as drawn facing
    right) and its ``opacity``."""

    x: float
    y: float
    radius: float
    opacity: float


def steam_puffs(now: float, seed: int, lean: float = 0.0) -> list[SteamPuff]:
    """A kettle's steam at scene time ``now``: :data:`STEAM_PUFFS` puffs, each rising from the
    spout over :data:`STEAM_SECONDS` (one after another, a little jittered by ``seed``), growing,
    swaying and drifting up and away from the spout, fading in and out; ``lean``: the felt wind
    force (at most :data:`STEAM_LEAN_MAX` either way), blowing the puffs aside (more the higher
    they are). A puff that has faded is left out."""
    sx, sy = STEAM_SPOUT
    lean = min(max(lean, -STEAM_LEAN_MAX), STEAM_LEAN_MAX)
    puffs: list[SteamPuff] = []
    for k in range(STEAM_PUFFS):
        age = (now / STEAM_SECONDS + (k + 0.6 * _unit(seed, "steam", k)) / STEAM_PUFFS) % 1.0
        opacity = STEAM_OPACITY * min(1.0, 8.0 * age) * (1.0 - age) ** 1.3   # at once out of the spout, fading as it rises
        if opacity <= 0.0:
            continue
        sway = 0.15 * math.sin(2.0 * math.pi * (1.3 * age + _unit(seed, "sway", k)))
        x = sx + 0.3 * age + sway * age + STEAM_LEAN * lean * age * age
        y = sy + STEAM_RISE * age
        puffs.append(SteamPuff(x, y, STEAM_RADIUS[0] + (STEAM_RADIUS[1] - STEAM_RADIUS[0]) * age, opacity))
    return puffs


def steam_box(lean: float = 0.0) -> Box:
    """The box (prop units, as drawn facing right) a kettle's steam can fill with the felt wind
    force ``lean`` (left, bottom, right, top)."""
    sx, sy = STEAM_SPOUT
    reach = STEAM_RADIUS[1] + 0.15
    drift = STEAM_LEAN * min(max(lean, -STEAM_LEAN_MAX), STEAM_LEAN_MAX)
    return (sx - reach + min(drift, 0.0), sy - STEAM_RADIUS[0], sx + 0.3 + reach + max(drift, 0.0), sy + STEAM_RISE + reach)


# ----- glows ------------------------------------------------------------------------------------


def glow_rings(radius: float, opacity: float, rings: int = GLOW_RINGS) -> list[tuple[float, float]]:
    """The discs a soft glow is drawn with, from the outside in: (radius, opacity of the disc).
    Stacked, they are ``opacity`` opaque at the middle and fade out towards ``radius``."""
    each = 1.0 - (1.0 - min(max(opacity, 0.0), 1.0)) ** (1.0 / max(rings, 1))
    return [(radius * (rings - k) / rings, each) for k in range(rings)]


def glow_box(x: float, y: float, radius: float) -> Box:
    """The box a glow of ``radius`` about (``x``, ``y``) covers (Manim units)."""
    return (x - radius, y - radius, x + radius, y + radius)


def union_box(a: Box, b: Box) -> Box:
    """The smallest box holding ``a`` and ``b``."""
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def boxes_overlap(a: Box, b: Box, margin: float = 0.0) -> bool:
    """Whether boxes ``a`` and ``b`` overlap, ``b`` grown by ``margin`` on every side."""
    return a[0] <= b[2] + margin and b[0] - margin <= a[2] and a[1] <= b[3] + margin and b[1] - margin <= a[3]


def redrawn_members(boxes: Sequence[Box | None], regions: Sequence[Box], margin: float = 0.0) -> list[int]:
    """Which of ``boxes`` (the members drawn after the moving parts, in draw order; ``None``: draws
    nothing) Manim must redraw on every frame: each one overlapping a moving part's region
    (``regions``) or a member redrawn before it, since a moving part redrawn over the static image
    would otherwise cover it. Their indices, in order."""
    covered = list(regions)
    found: list[int] = []
    for k, box in enumerate(boxes):
        if box is not None and any(boxes_overlap(box, region, margin) for region in covered):
            found.append(k)
            covered.append(box)
    return found


__all__ = [
    "DRAWN_CLOCK_SECONDS",
    "FIRE_GLOW_FLICKER",
    "FLAME_BASE",
    "FLAME_FEET",
    "FLAME_FLICKER",
    "FLAME_HEIGHTS",
    "FLAME_LEAN_MAX",
    "FLICKER_DEPTH",
    "FLICKER_STEP",
    "GLOWS",
    "GLOW_RINGS",
    "LIVING_KINDS",
    "LIVING_PART",
    "MAX_CLOCK_SPEED",
    "SECOND_HAND_MAX_SPEED",
    "STEAM_LEAN_MAX",
    "STEAM_PUFFS",
    "STEAM_RISE",
    "STEAM_SPOUT",
    "SWITCHED_PROPS",
    "TV_PALETTES",
    "TV_SHOT_JITTER",
    "TV_SHOT_SECONDS",
    "Box",
    "FlameShape",
    "GlowSpec",
    "HandAngles",
    "SteamPuff",
    "TvPicture",
    "boxes_overlap",
    "clock_seconds",
    "fire_flicker",
    "flame_lean",
    "flame_shapes",
    "glow_box",
    "glow_rings",
    "hand_angles",
    "hand_tip",
    "on_between",
    "on_spans",
    "parse_clock_time",
    "redrawn_members",
    "shows_second_hand",
    "steam_box",
    "steam_puffs",
    "switch_between",
    "switched_on",
    "tv_flicker",
    "tv_picture",
    "tv_shot",
    "union_box",
]
