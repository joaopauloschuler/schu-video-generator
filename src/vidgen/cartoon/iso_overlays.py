"""Things drawn over an iso place's pictures that move by themselves (DESIGN.md §100.7, §100.11,
§102.2, §102.3): the steel shutters over a room's windows, the blinking lights of its lab objects
and towers, a city's crawling info screens and its hover pods on their lanes. Each is a
*living thing* of the stage (``update_to``, ``changing``, ``done``, ``movers``, ``region``), drawn
right after the place's pictures (behind the characters).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from manim import Circle, VGroup, VMobject

from vidgen.cartoon.alarm import shutter_level, shutters_changing
from vidgen.cartoon.iso_drawing import ISO_OUTLINE
from vidgen.config import CHARACTER_INK
from vidgen.cartoon.iso_city import SCREEN_LINES, SCREEN_TEXT, lane_pods, pod_hidden, screen_lines
from vidgen.cartoon.living import _unit
from vidgen.world.iso_view import Box3

#: Shutters: the steel's colour, its slats' colour and how many slats a window has.
SHUTTER_STEEL = "#8E96A3"
SHUTTER_SLAT = "#5D6573"
SHUTTER_SLATS = 7

Box = tuple[float, float, float, float]
Point = tuple[float, float]


def _box(points: Sequence[Point]) -> Box:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class IsoShutters(VGroup):
    """Steel shutters over ``windows`` (each four points on screen: bottom left, bottom right,
    top right, top left), down at the start when ``closed``; :meth:`move` closes or opens them
    at a scene time (:func:`~vidgen.cartoon.alarm.shutter_level`). ``stroke``: the slats' width."""

    def __init__(self, windows: Sequence[Sequence[Point]], *, closed: bool = False, stroke: float = 1.0) -> None:
        super().__init__()
        self.name = "shutters"
        self.windows = [tuple((float(x), float(y)) for x, y in w) for w in windows]
        self.closed = closed
        self.moves: list[tuple[float, bool]] = []
        self.plates: list[VMobject] = []
        self.slats: list[list[VMobject]] = []
        for _ in self.windows:
            plate = VMobject().set_fill(SHUTTER_STEEL, opacity=1.0).set_stroke(SHUTTER_SLAT, width=stroke, opacity=1.0)
            slats = [VMobject().set_fill(opacity=0.0).set_stroke(SHUTTER_SLAT, width=stroke, opacity=1.0) for _ in range(SHUTTER_SLATS)]
            self.plates.append(plate)
            self.slats.append(slats)
            self.add(plate, *slats)
        self.update_to(0.0)

    def move(self, close: bool, time: float) -> None:
        """Close (or open) the shutters from scene ``time``."""
        self.moves.append((float(time), bool(close)))

    def update_to(self, now: float) -> None:
        """Draw them as they are at scene time ``now``: each plate from its window's top down to
        its level, the slats on it."""
        level = shutter_level(self.closed, self.moves, now)
        for window, plate, slats in zip(self.windows, self.plates, self.slats):
            bl, br, tr, tl = (np.array([x, y, 0.0]) for x, y in window)
            if level <= 1e-4:
                plate.points = np.zeros((0, 3))
                for slat in slats:
                    slat.points = np.zeros((0, 3))
                continue
            low_l, low_r = tl + (bl - tl) * level, tr + (br - tr) * level
            plate.set_points_as_corners([tl, tr, low_r, low_l, tl])
            for k, slat in enumerate(slats):
                share = (k + 1) / (len(slats) + 1)
                if share < level:
                    left, right = tl + (low_l - tl) * (share / level), tr + (low_r - tr) * (share / level)
                    slat.set_points_as_corners([left, right])
                else:
                    slat.points = np.zeros((0, 3))

    def changing(self, start: float, end: float) -> bool:
        """Whether they move between scene times ``start`` and ``end``."""
        return shutters_changing(self.moves, start, end)

    def done(self, now: float) -> bool:
        """Whether every move is over at scene time ``now``."""
        return not shutters_changing(self.moves, now, math.inf)

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        """The box of every window (Manim units)."""
        boxes = [_box(w) for w in self.windows] or [(0.0, 0.0, 0.0, 0.0)]
        return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


#: Blinking lights: the radius of a light's halo (a share more than its own), the halo's opacity,
#: the seconds a light's blink takes (from .. to, seeded) and its share lit (from .. to).
LIGHT_HALO = 1.8
LIGHT_HALO_OPACITY = 0.22
BLINK_SECONDS = (0.35, 2.4)
BLINK_DUTY = (0.25, 0.8)


def blink_on(index: int, now: float, seed: int = 0) -> bool:
    """Whether light ``index`` is lit at scene time ``now``: each blinks at its own seeded
    period and share lit; one in four flickers fast, like a disk at work."""
    period = BLINK_SECONDS[0] + (BLINK_SECONDS[1] - BLINK_SECONDS[0]) * _unit(seed, "blink", index)
    if index % 4 == 3:
        period *= 0.25
    duty = BLINK_DUTY[0] + (BLINK_DUTY[1] - BLINK_DUTY[0]) * _unit(seed, "duty", index)
    phase = _unit(seed, "phase", index)
    return ((now / period + phase) % 1.0) < duty


class IsoBlinkers(VGroup):
    """Small lights at ``points`` (on screen) of ``radius``, in ``colors`` (one per light), each
    blinking by :func:`blink_on` with a soft halo; never graded by the stage's light. ``hidden``:
    whether light ``k`` is behind something now (a character standing in front of its object,
    DESIGN.md §102.19): it is not drawn then."""

    def __init__(self, points: Sequence[Point], colors: Sequence[str], radius: float, *, seed: int = 0,
                 hidden: Callable[[int], bool] | None = None) -> None:
        super().__init__()
        self.name = "lab_lights"
        self.points_xy = [(float(x), float(y)) for x, y in points]
        self.radius = radius
        self.seed = seed
        self.hidden = hidden
        unit = Circle(radius=1.0).points
        self.lights: list[tuple[VMobject, VMobject]] = []
        for (x, y), color in zip(self.points_xy, colors):
            halo = VMobject().set_fill(color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
            halo.points = unit * (radius * LIGHT_HALO) + np.array([x, y, 0.0])
            dot = VMobject().set_fill(color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
            dot.points = unit * radius + np.array([x, y, 0.0])
            self.lights.append((halo, dot))
            self.add(halo, dot)
        self.update_to(0.0)

    def update_to(self, now: float) -> None:
        """Light each one as it is at scene time ``now``."""
        for k, (halo, dot) in enumerate(self.lights):
            lit = blink_on(k, now, self.seed) and not (self.hidden is not None and self.hidden(k))
            dot.set_fill(opacity=1.0 if lit else 0.0)
            halo.set_fill(opacity=LIGHT_HALO_OPACITY if lit else 0.0)

    def changing(self, start: float, end: float) -> bool:
        return bool(self.lights)

    def done(self, now: float) -> bool:
        return not self.lights

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        pad = self.radius * LIGHT_HALO
        xs = [p[0] for p in self.points_xy] or [0.0]
        ys = [p[1] for p in self.points_xy] or [0.0]
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


#: A tower's screen (DESIGN.md §102.2): its lines' thickness (a share of the screen's height).
SCREEN_LINE_THICKNESS = 0.07


def _quad_point(quad: Sequence[np.ndarray], across: float, up: float) -> np.ndarray:
    """A point of the quad ``(bottom left, bottom right, top right, top left)``: ``across`` and
    ``up`` shares of it."""
    bl, br, tr, tl = quad
    bottom = bl + (br - bl) * across
    top = tl + (tr - tl) * across
    return bottom + (top - bottom) * up


class IsoScreens(VGroup):
    """The info screens of a city's towers (DESIGN.md §102.2): over each screen (four points on
    screen: bottom left, bottom right, top right, top left) its glowing plate in ``colors`` and
    lines of text crawling up it (:func:`~vidgen.cartoon.iso_city.screen_lines`); never graded by
    the stage's light."""

    def __init__(self, screens: Sequence[Sequence[Point]], colors: Sequence[str], *, seeds: Sequence[int]) -> None:
        super().__init__()
        self.name = "tower_screens"
        self.quads = [[np.array([float(x), float(y), 0.0]) for x, y in quad] for quad in screens]
        self.seeds = list(seeds)
        self.lines: list[list[VMobject]] = []
        for quad, color in zip(self.quads, colors):
            plate = VMobject().set_fill(color, opacity=1.0).set_stroke(width=0.0, opacity=0.0)
            plate.set_points_as_corners([*quad, quad[0]])
            rows = [VMobject().set_fill(SCREEN_TEXT, opacity=0.95).set_stroke(width=0.0, opacity=0.0) for _ in range(SCREEN_LINES)]
            self.lines.append(rows)
            self.add(plate, *rows)
        self.update_to(0.0)

    def update_to(self, now: float) -> None:
        """Put each screen's lines where they are at scene time ``now``."""
        half = SCREEN_LINE_THICKNESS / 2
        for quad, rows, seed in zip(self.quads, self.lines, self.seeds):
            for row, (up, length) in zip(rows, screen_lines(now, seed)):
                low, high = max(up - half, 0.04), min(up + half, 0.96)
                if high <= low:
                    row.points = np.zeros((0, 3))
                    continue
                a0, a1 = 0.06, 0.06 + 0.88 * length
                row.set_points_as_corners([_quad_point(quad, a0, low), _quad_point(quad, a1, low), _quad_point(quad, a1, high),
                                           _quad_point(quad, a0, high), _quad_point(quad, a0, low)])

    def changing(self, start: float, end: float) -> bool:
        return bool(self.quads)

    def done(self, now: float) -> bool:
        return not self.quads

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        points = [(float(p[0]), float(p[1])) for quad in self.quads for p in quad] or [(0.0, 0.0)]
        return _box(points)


@dataclass(frozen=True)
class PodLane:
    """A traffic lane over an iso place on screen (DESIGN.md §102.3): its ``start`` and ``end``
    (Manim units), how long a pod takes along it (``seconds``), how many pods (``count``), their
    ``color``, crossing once from scene time ``at`` (``None``: looping) and the pods' ``length``
    (Manim units)."""

    start: Point
    end: Point
    seconds: float
    count: int
    color: str
    length: float
    at: float | None = None
    #: the lane's ends in the world (tile units), for what hides its pods (``None``: nothing does)
    world: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None


#: A pod's parts (DESIGN.md §102.3): its height as a share of its length, its trail's length (a
#: share of its length), the glow under it, the canopy's and the hull's colours.
POD_HEIGHT = 0.36
POD_TRAIL = 2.4
POD_GLOW_OPACITY = 0.28
POD_CANOPY = "#CFF6FF"
POD_HULL = "#262C44"


def _ellipse(cx: float, cy: float, rx: float, ry: float, steps: int = 20) -> list[np.ndarray]:
    return [np.array([cx + rx * math.cos(a), cy + ry * math.sin(a), 0.0]) for a in np.linspace(0.0, 2 * math.pi, steps + 1)]


class IsoTraffic(VGroup):
    """Hover pods gliding along traffic lanes over an iso place (DESIGN.md §102.3): each pod a
    small capsule (a dark hull with a glowing rim in its lane's colour, a light canopy with a
    rider's head, a headlight), a soft glow under it and a fading light trail behind it, facing
    the way it goes; :func:`~vidgen.cartoon.iso_city.lane_pods` says where they are. A pod behind
    one of ``occluders`` (the boxes of the place's tall objects, with their outlines on the
    picture: :func:`~vidgen.cartoon.iso_city.pod_hidden`) is not drawn. Never graded by the
    stage's light."""

    def __init__(self, lanes: Sequence[PodLane], occluders: Sequence[tuple[Box3, list[tuple[float, float]]]] = ()) -> None:
        super().__init__()
        self.name = "traffic"
        self.lanes = list(lanes)
        self.occluders = list(occluders)
        #: each lane's pods: (trail, glow, hull, canopy, head, light)
        self.pods: list[list[tuple[VMobject, ...]]] = []
        for lane in self.lanes:
            pods = []
            for _ in range(lane.count):
                trail = VMobject().set_fill(lane.color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                glow = VMobject().set_fill(lane.color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                hull = VMobject().set_fill(POD_HULL, opacity=0.0).set_stroke(lane.color, width=2.0, opacity=0.0)
                canopy = VMobject().set_fill(POD_CANOPY, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                head = VMobject().set_fill("#141826", opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                light = VMobject().set_fill("#FFFFFF", opacity=0.0).set_stroke(width=0.0, opacity=0.0)
                parts = (trail, glow, hull, canopy, head, light)
                pods.append(parts)
                self.add(*parts)
            self.pods.append(pods)
        self.update_to(0.0)

    def update_to(self, now: float) -> None:
        """Place every pod where it is at scene time ``now``."""
        for lane, pods in zip(self.lanes, self.pods):
            spots = lane_pods(now, lane.seconds, lane.count, lane.at)
            (x0, y0), (x1, y1) = lane.start, lane.end
            dx, dy = x1 - x0, y1 - y0
            norm = math.hypot(dx, dy) or 1.0
            ux, uy = dx / norm, dy / norm
            facing = 1.0 if dx >= 0 else -1.0
            for k, parts in enumerate(pods):
                spot = spots[k] if k < len(spots) else None
                if spot is not None and lane.world is not None and self.occluders:
                    (a, b) = lane.world
                    point = tuple(a[i] + (b[i] - a[i]) * spot.share for i in range(3))
                    if pod_hidden(point, self.occluders):   # type: ignore[arg-type]
                        spot = None
                if spot is None:
                    for part in parts:
                        part.points = np.zeros((0, 3))
                    continue
                self._draw(parts, x0 + dx * spot.share, y0 + dy * spot.share, ux, uy, facing, lane.length, spot.shown)

    @staticmethod
    def _draw(parts: tuple[VMobject, ...], x: float, y: float, ux: float, uy: float, facing: float, length: float, shown: float) -> None:
        trail, glow, hull, canopy, head, light = parts
        half, tall = length / 2, length * POD_HEIGHT / 2
        back = np.array([x - ux * half * 0.8, y - uy * half * 0.8, 0.0])
        tail = np.array([x - ux * length * POD_TRAIL, y - uy * length * POD_TRAIL, 0.0])
        side = np.array([-uy, ux, 0.0]) * tall * 0.7
        trail.set_points_as_corners([back + side, tail, back - side, back + side])
        trail.set_fill(opacity=0.32 * shown)
        glow.set_points_as_corners(_ellipse(x, y - tall * 1.6, half * 1.25, tall * 0.7))
        glow.set_fill(opacity=POD_GLOW_OPACITY * shown)
        hull.set_points_as_corners(_ellipse(x, y, half, tall))
        hull.set_fill(opacity=shown).set_stroke(opacity=shown)
        dome = [np.array([x + facing * half * 0.15 + half * 0.5 * math.cos(a), y + tall * 0.2 + tall * 1.1 * math.sin(a), 0.0])
                for a in np.linspace(0.0, math.pi, 13)]
        canopy.set_points_as_corners([*dome, dome[0]])
        canopy.set_fill(opacity=0.85 * shown)
        head.set_points_as_corners(_ellipse(x + facing * half * 0.05, y + tall * 0.75, tall * 0.42, tall * 0.48, 12))
        head.set_fill(opacity=0.9 * shown)
        light.set_points_as_corners(_ellipse(x + facing * half * 0.9, y - tall * 0.1, tall * 0.22, tall * 0.18, 10))
        light.set_fill(opacity=shown)

    def changing(self, start: float, end: float) -> bool:
        return bool(self.lanes)

    def done(self, now: float) -> bool:
        return not self.lanes

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        points = [p for lane in self.lanes for p in (lane.start, lane.end)] or [(0.0, 0.0)]
        x0, y0, x1, y1 = _box(points)
        pad = max((lane.length * (POD_TRAIL + 1) for lane in self.lanes), default=0.0)
        return x0 - pad, y0 - pad, x1 + pad, y1 + pad


#: Manim units per unit of a stroke's width (Cairo's line width multiple).
CAIRO_LINE_UNIT = 0.01


@dataclass(frozen=True)
class Gadget:
    """A working object of an iso place for :class:`IsoGadgets` (DESIGN.md §103): its moving
    ``parts`` at a scene time (:func:`~vidgen.cartoon.iso_objects.object_motion`; the same number
    at any time), whether it works at a scene time (``working``) and whether it works at any time
    between two (``busy``)."""

    parts: Callable[[float], Sequence[Any]]
    working: Callable[[float], bool]
    busy: Callable[[float, float], bool]


class IsoGadgets(VGroup):
    """The moving parts of an iso place's working objects (DESIGN.md §103), drawn over the
    place's pictures while each works: a robot arm swinging, a centrifuge's rotor spinning, a
    quantum core pulsing, steam over a coffee mug. ``project`` puts a world point on screen;
    ``unit``: a tile's width on screen (Manim units), for the outline as the place's
    (``outline``: the drawing style's factor); ``region``: the box (on screen) they stay in. The
    parts that are lights (:attr:`glowing`) are left out of the stage's light grade by the stage."""

    def __init__(self, gadgets: Sequence[Gadget], project: Callable[[Any], Point], *, unit: float, region: Box, outline: float = 1.0,
                 pool_strength: Callable[[], float] = lambda: 1.0) -> None:
        super().__init__()
        #: how strong the parts that are light thrown on things (``pool``) show now (§104)
        self.pool_strength = pool_strength
        ink = CHARACTER_INK
        stroke = ISO_OUTLINE * unit * outline / CAIRO_LINE_UNIT
        self.name = "gadgets"
        self.gadgets = list(gadgets)
        self.project = project
        self.box = region
        #: each gadget's pieces, one per part, and the pieces of the parts that are lights
        self.pieces: list[list[VMobject]] = []
        self.glowing: list[VMobject] = []
        for gadget in self.gadgets:
            pieces = []
            for part in gadget.parts(0.0):
                piece = VMobject().set_fill(part.fill, opacity=0.0).set_stroke(ink, width=stroke if part.ink else 0.0, opacity=0.0)
                pieces.append(piece)
                if part.glow:
                    self.glowing.append(piece)
            self.pieces.append(pieces)
            self.add(*pieces)
        self.update_to(0.0)

    def update_to(self, now: float) -> None:
        """Draw every working object's parts as they are at scene time ``now`` (none while it
        does not work)."""
        strength = None
        for gadget, pieces in zip(self.gadgets, self.pieces):
            parts = gadget.parts(now) if gadget.working(now) else []
            for k, piece in enumerate(pieces):
                part = parts[k] if k < len(parts) else None
                opacity = 0.0 if part is None else part.opacity
                if part is not None and getattr(part, "pool", False):   # light on things: faint by day (§104)
                    strength = self.pool_strength() if strength is None else strength
                    opacity *= strength
                if part is None or opacity <= 0.0:
                    piece.points = np.zeros((0, 3))
                    continue
                corners = [np.array([*self.project(p), 0.0]) for p in part.points]
                piece.set_points_as_corners([*corners, corners[0]])
                piece.set_fill(part.fill, opacity=opacity).set_stroke(opacity=opacity if part.ink else 0.0)

    def changing(self, start: float, end: float) -> bool:
        return any(gadget.busy(start, end) for gadget in self.gadgets)

    def done(self, now: float) -> bool:
        return not any(gadget.busy(now, math.inf) for gadget in self.gadgets)

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        return self.box


@dataclass(frozen=True)
class HazeSpot:
    """A haze on screen (DESIGN.md §102.12): its ``foot`` and ``top`` (Manim units), its
    ``width`` (Manim units), ``color``, ``strength`` (0..1) and the scene time it fades in
    from (``start``)."""

    foot: Point
    top: Point
    width: float
    color: str
    strength: float
    start: float = 0.0


#: A haze's ribbons, glow and sparkles at full strength: their opacities.
HAZE_RIBBON_OPACITY = 0.2
HAZE_GLOW_OPACITY = 0.16
HAZE_SPARK_OPACITY = 0.85


class IsoHaze(VGroup):
    """Shimmering air over spots of an iso place (DESIGN.md §102.12): for each :class:`HazeSpot`
    a soft glow on the floor, faint ribbons of light wavering up
    (:func:`~vidgen.cartoon.haze.haze_ribbons`) and small sparkles rising through them
    (:func:`~vidgen.cartoon.haze.haze_sparks`); never graded by the stage's light."""

    def __init__(self, spots: Sequence[HazeSpot], *, seed: int = 0) -> None:
        from vidgen.cartoon.haze import HAZE_RIBBONS, HAZE_SPARKS

        super().__init__()
        self.name = "haze"
        self.spots = list(spots)
        self.seed = seed
        self.parts: list[tuple[VMobject, list[VMobject], list[VMobject]]] = []
        for spot in self.spots:
            glow = VMobject().set_fill(spot.color, opacity=0.0).set_stroke(width=0.0, opacity=0.0)
            ribbons = [VMobject().set_fill(spot.color, opacity=0.0).set_stroke(width=0.0, opacity=0.0) for _ in range(HAZE_RIBBONS)]
            sparks = [VMobject().set_fill("#FFFFFF", opacity=0.0).set_stroke(spot.color, width=1.0, opacity=0.0) for _ in range(HAZE_SPARKS)]
            self.parts.append((glow, ribbons, sparks))
            self.add(glow, *ribbons, *sparks)
        self.update_to(0.0)

    def update_to(self, now: float) -> None:
        """Draw every haze as it is at scene time ``now``."""
        from vidgen.cartoon.haze import haze_level, haze_ribbons, haze_sparks

        for k, (spot, (glow, ribbons, sparks)) in enumerate(zip(self.spots, self.parts)):
            level = haze_level(now, spot.start) * spot.strength
            (fx, fy), (tx, ty) = spot.foot, spot.top

            def at(u: float, v: float) -> np.ndarray:
                return np.array([fx + (tx - fx) * v + u * spot.width, fy + (ty - fy) * v, 0.0])

            if level <= 1e-3:
                for member in (glow, *ribbons, *sparks):
                    member.points = np.zeros((0, 3))
                continue
            glow.set_points_as_corners(_ellipse(fx, fy, spot.width * 0.6, spot.width * 0.22))
            glow.set_fill(opacity=HAZE_GLOW_OPACITY * level)
            for ribbon, (outline, share) in zip(ribbons, haze_ribbons(now, self.seed + k)):
                ribbon.set_points_as_corners([at(u, v) for u, v in (*outline, outline[0])])
                ribbon.set_fill(opacity=HAZE_RIBBON_OPACITY * share * level)
            for member, (u, v, size, shown) in zip(sparks, haze_sparks(now, self.seed + k)):
                cx, cy = at(u, v)[:2]
                r = size * spot.width
                member.set_points_as_corners([np.array([cx + r * math.cos(a) * (1.0 if j % 2 == 0 else 0.3), cy + r * math.sin(a) * (1.0 if j % 2 == 0 else 0.3), 0.0])
                                              for j, a in enumerate(np.linspace(0.0, 2.0 * math.pi, 9))])
                member.set_fill(opacity=HAZE_SPARK_OPACITY * shown * level).set_stroke(opacity=0.6 * shown * level)

    def changing(self, start: float, end: float) -> bool:
        return bool(self.spots)

    def done(self, now: float) -> bool:
        return not self.spots

    def movers(self) -> list[VMobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> Box:
        boxes = []
        for spot in self.spots:
            (fx, fy), (tx, ty) = spot.foot, spot.top
            pad = spot.width * 0.75
            boxes.append((min(fx, tx) - pad, min(fy, ty) - pad, max(fx, tx) + pad, max(fy, ty) + pad))
        boxes = boxes or [(0.0, 0.0, 0.0, 0.0)]
        return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


__all__ = ["BLINK_DUTY", "BLINK_SECONDS", "POD_HEIGHT", "SCREEN_LINE_THICKNESS", "SHUTTER_SLATS", "Gadget", "HazeSpot", "IsoBlinkers", "IsoGadgets", "IsoHaze",
           "IsoScreens", "IsoShutters", "IsoTraffic", "PodLane", "blink_on"]
