"""Vehicles moving on an isometric place, drawn (DESIGN.md §105): a car driving, a boat sailing, a
train car rolling and a rocket lifting off, along the routes of the rules
(:mod:`vidgen.world.iso_vehicles`).

A vehicle the scene moves is not part of the place's pictures (its look is ``driven``): the stage
draws it as an :class:`IsoVehicle`, a small picture of it (a *sprite*: its shapes drawn as the
place's are, at the level of detail the camera's zoom needs) moved across the place. The place is
seen without perspective, so moving a thing in the world moves its picture on the screen and
nothing else: one sprite per way it heads, lit or not (and a few for a car's turning wheels, a
rocket's flickering flame) serves the whole drive. Like a character it stands in a box for the
draw order (:meth:`IsoVehicle.box`) and has a front picture of what stands in front of it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from manim import Animation, Group, ImageMobject, Mobject, linear

from vidgen.cartoon.iso_drawing import Blobs, Disc, IsoCanvas, Line, Poly, Shape, canvas_for, draw_shapes, mix, shape_bounds
from vidgen.cartoon.iso_objects import ObjectLook, _Frame, light_pool
from vidgen.cartoon.iso_pictures import GlowTile, PoolTile
from vidgen.cartoon.iso_seasons import BOB, BOB_SECONDS, FOAM, _boat_parts, launch_smoke, rocket_body, rocket_fire, train_body, train_track
from vidgen.cartoon.iso_scenery import WATER_DEPTH
from vidgen.cartoon.iso_stage import IsoView, canvas_center, detail_for
from vidgen.cartoon.iso_town import car_shapes
from vidgen.cartoon.shading import LIT
from vidgen.world.iso import OBJECT_KINDS, IsoObject, ObjectState
from vidgen.world.iso_vehicles import VEHICLE_SIZES, VehicleRoute, drive_share, lift_share
from vidgen.world.iso_view import Box3, iso_point

Cell = tuple[int, int]
Point3 = tuple[float, float, float]

#: A car's wheel radius (tile units): how far it rolls per turn of its wheels; its spokes look
#: the same every quarter turn, drawn at :data:`SPOKE_STEPS` angles in between.
WHEEL_RADIUS = 0.21
SPOKE_STEPS = 4
#: A rocket's flame: drawn at this many moments a second (its flicker), how much longer it roars
#: while it lifts off.
FLAME_FRAMES = 8
LIFT_FLAME = 2.2
#: The drives of a scene a vehicle has made or will make: (scene start, seconds).
Span = tuple[float, float]


def frame_item(kind: str, heading: Cell) -> IsoObject:
    """The vehicle ``kind`` standing with its middle at the world's origin, heading ``heading``
    (along the map's rows: facing left; along its columns: facing right)."""
    spec = OBJECT_KINDS[kind]
    length, width = max(spec.width, spec.depth), min(spec.width, spec.depth)
    if kind == "rocket":
        return IsoObject(kind, kind, -spec.width / 2, -spec.depth / 2, spec.width, spec.depth, spec.height)   # type: ignore[arg-type]
    if heading[1] == 0:
        return IsoObject(kind, kind, -length / 2, -width / 2, length, width, spec.height, "left")   # type: ignore[arg-type]
    return IsoObject(kind, kind, -width / 2, -length / 2, width, length, spec.height, "right")   # type: ignore[arg-type]


#: A sailing boat's wake: how far behind its stern it spreads (tile units) and how wide.
WAKE_LENGTH = 1.3
WAKE_SPREAD = 0.75


def boat_wake(f: _Frame, reverse: bool) -> list[Shape]:
    """A sailing boat's wake on the water behind its stern: two arms of foam spreading out in a V
    and a fainter trail between them (in its frame: its stern at ``a`` 0, or at its width when
    ``reverse``)."""
    wl = -WATER_DEPTH + 0.003

    def q(a: float, b: float) -> Point3:
        return f.p(f.width - a if reverse else a, b, wl)

    shapes: list[Shape] = []
    for side in (-1.0, 1.0):
        arm = [(0.2, 0.5 + side * 0.2), (-WAKE_LENGTH, 0.5 + side * WAKE_SPREAD), (-WAKE_LENGTH + 0.1, 0.5 + side * (WAKE_SPREAD - 0.12)),
               (0.15, 0.5 + side * 0.1)]
        shapes.append(Poly(tuple(q(a, b) for a, b in arm), FOAM, False, holds_snow=False))
    trail = [(0.1, 0.42), (-WAKE_LENGTH * 0.8, 0.45), (-WAKE_LENGTH * 0.8, 0.55), (0.1, 0.58)]
    shapes.append(Poly(tuple(q(a, b) for a, b in trail), mix(FOAM, "#9FD3F2", 0.45), False, holds_snow=False))
    return shapes


def _turned(shape: Shape, cos: float, sin: float) -> Shape:
    """``shape`` turned about the world's upright axis through the origin."""
    def p(q: Point3) -> Point3:
        return (q[0] * cos - q[1] * sin, q[0] * sin + q[1] * cos, q[2])
    if isinstance(shape, (Poly, Line)):
        return replace(shape, points=tuple(p(q) for q in shape.points))
    if isinstance(shape, Disc):
        return replace(shape, centre=p(shape.centre))
    if isinstance(shape, Blobs):
        return replace(shape, centres=tuple(p(q) for q in shape.centres))
    x, y, _ = p((shape.x, shape.y, 0.0))
    return replace(shape, x=x, y=y)


def turning_shapes(kind: str, look: ObjectLook, turn: tuple[Cell, Cell], **settings: Any) -> list[Shape]:
    """A car or a boat half-way round a corner (``turn``: the ways it heads before and after):
    the one heading along the map's row turned 45 degrees to the diagonal between them. Seen
    turned so, one of its faces drawn shows whole and the other edge-on (a box's faces drawn are
    those to the viewer), so the picture has no gaps (DESIGN.md §105.8)."""
    along_x = next(h for h in turn if h[1] == 0)
    along_y = next(h for h in turn if h[0] == 0)
    sign = along_x[0] * along_y[1]
    shapes = vehicle_shapes(kind, look, heading=along_x, **settings)
    c = math.sqrt(0.5)
    return [_turned(s, c, sign * c) for s in shapes]


def vehicle_shapes(kind: str, look: ObjectLook, *, heading: Cell, on: bool, spin: float | None = None, now: float = 0.0,
                   boost: float = 1.0, wake: bool = False, turn: tuple[Cell, Cell] | None = None) -> list[Shape]:
    """The shapes of a moving vehicle with its middle at the world's origin (on its base, ``z``
    0), heading ``heading``: a car side-on (driving away up the picture its tail shows, ``spin``
    its spokes), a boat (its bow the way it sails; ``wake``: its wake behind it), a train car's
    carriage (no track), a rocket without its pad (its flame at ``now``, ``boost`` times as long,
    while ``on``); ``turn``: a car or a boat half-way round a corner (:func:`turning_shapes`)."""
    if turn is not None:
        return turning_shapes(kind, look, turn, on=on, spin=spin, now=now, boost=boost, wake=wake)
    f = _Frame(frame_item(kind, heading), 0.0)
    plain = ObjectLook(look.main, look.detail)
    away = heading in ((-1, 0), (0, -1))
    if kind == "car":
        return car_shapes(f, plain, ObjectState(on=on), reverse=away, spin=spin)
    if kind == "boat":
        pool = light_pool(f.p(f.width - 0.25 if away else 0.25, 0.5, -WATER_DEPTH + 0.01), 0.8, 0.6) if on else []
        return [*pool, *(boat_wake(f, away) if wake else []), *_boat_parts(f, plain, on, 0.0, 0.0, 0.0, reverse=away)]
    if kind == "train_car":
        return train_body(f, plain)
    shapes = rocket_body(f, plain, on)
    return shapes + (rocket_fire(f, now, boost) if on else [])   # type: ignore[operator]


def track_shapes(cells: Sequence[Cell], base: float) -> list[Shape]:
    """A train car's track along ``cells`` (a straight line of cells), on the ground at ``base``."""
    columns, rows = [c for c, _ in cells], [r for _, r in cells]
    across = len(set(rows)) == 1
    item = IsoObject("track", "train_car", min(columns), min(rows), len(cells) if across else 1, 1 if across else len(cells), 0.1,
                     "left" if across else "right")
    return train_track(_Frame(item, base))


def rocket_smoke(item: IsoObject, base: float, now: float, strength: float) -> list[Any]:
    """The smoke billowing over the pad of the rocket ``item`` (standing at ``base``) at ``now``,
    ``strength`` (0..1) of it showing (:func:`~vidgen.cartoon.iso_seasons.launch_smoke`)."""
    return launch_smoke(_Frame(item, base), now, strength)


#: A sprite's three pictures, in the order drawn: the vehicle, its pools of light, its lights.
SPRITE_MODES = ("picture", "pool", "glow")
_NOTHING = np.zeros((1, 1, 4), dtype=np.uint8)


@dataclass
class Sprite:
    """A vehicle drawn once: the pixels of its picture, its pools of light and its lights
    (``None``: none; :data:`SPRITE_MODES`), and the canvas they were drawn on (picture point of
    its top left, with the vehicle's middle on the world's origin)."""

    canvas: IsoCanvas
    pixels: tuple[np.ndarray | None, ...]


def draw_sprite(shapes: Sequence[Shape], scale: float, *, outline: float) -> Sprite:
    """``shapes`` drawn at ``scale`` pixels per tile width: its picture, its pools of light and
    its lights (:data:`SPRITE_MODES`; ``None`` where it has none)."""
    bounds = [shape_bounds(s) for s in shapes]
    canvas = canvas_for((min(b[0] for b in bounds), min(b[1] for b in bounds), max(b[2] for b in bounds), max(b[3] for b in bounds)),
                        scale, margin=0.08)
    pixels: list[np.ndarray | None] = []
    for mode in SPRITE_MODES:
        if mode != "picture" and not any(getattr(s, mode, False) for s in shapes):
            pixels.append(None)
            continue
        pixels.append(np.array(draw_shapes(shapes, canvas, outline=outline, glow=mode == "glow", pool=mode == "pool")))
    return Sprite(canvas, tuple(pixels))


class IsoVehicle(Group):
    """A vehicle of an iso place the scene moves (DESIGN.md §105), named after its object: its
    sprite (:class:`Sprite`) where it is now. ``point``: its middle on its base (tile units),
    ``heading``: the way it heads (a rocket: ``(0, 0)``); :meth:`set_pose` moves it,
    :meth:`refresh` shows it as it is at a scene time (lit or not, its flame, a boat's bob) at the
    level of detail of the camera's ``zoom``. ``switches``: its ``on`` from scene times on.

    It is also one of the stage's things that move by themselves (``update_to``, ``changing``,
    ``done``, ``movers``, ``region``): a switch, a flame or a bob shows without an animation."""

    iso_vehicle = True

    def __init__(self, name: str, kind: str, look: ObjectLook, view: IsoView, *, point: Point3, heading: Cell, scale: float, density: float,
                 frame_width: float, outline: float = 1.0, on: bool = False) -> None:
        super().__init__()
        self.name, self.kind, self.look, self.view = name, kind, look, view
        self.point, self.heading = point, heading
        #: half-way round a corner: the ways it heads before and after (drawn turned)
        self.turn: tuple[Cell, Cell] | None = None
        #: how far it has driven (tile units): its wheels' turn
        self.rolled = 0.0
        #: its ``on`` from scene times on, in time order
        self.switches: list[tuple[float, bool]] = [(0.0, on)]
        #: its moves: (scene start, seconds); a rocket's lift-off (``None``: none) and when it is gone
        self.drives: list[Span] = []
        self.launch: Span | None = None
        self.scale, self.density, self.frame_width, self.outline = scale, density, frame_width, outline
        self.level = 0
        self.shown = True
        self._sprites: dict[tuple[Any, ...], Sprite] = {}
        self._now = 0.0
        #: where it reaches on screen over the scene (Manim units: left, bottom, right, top)
        self.reach: tuple[float, float, float, float] | None = None
        #: its three pictures (:data:`SPRITE_MODES`), always the same mobjects: Manim keeps the
        #: members of what moves when an animation starts, so a swapped one would stay drawn
        self.slots: tuple[ImageMobject, ...] = tuple(kind(_NOTHING.copy()) for kind in (ImageMobject, PoolTile, GlowTile))
        for slot in self.slots:
            slot.iso_tile = True   # drawn by the place's tile drawing (draw_tile)
            slot.scenery = True    # a thing of the place: the camera may cut it (lint off_frame)
            slot.name = name
        self.add(*self.slots)
        self.refresh(0.0)

    # ----- where it is ------------------------------------------------------------------------------

    @property
    def iso_feet(self) -> Point3:
        return self.point

    def set_pose(self, point: Point3, heading: Cell, rolled: float | None = None, turn: tuple[Cell, Cell] | None = None) -> None:
        """Put its middle at ``point`` (tile units), heading ``heading``; ``rolled``: how far it
        has driven (its wheels); ``turn``: half-way round a corner (drawn turned)."""
        self.point, self.heading, self.turn = point, heading, turn
        if rolled is not None:
            self.rolled = rolled

    def box(self) -> Box3:
        """The box it stands in now, for the draw order (tile units)."""
        length, width, height = VEHICLE_SIZES[self.kind]
        x, y, z = self.point
        along_x = self.heading[1] == 0
        hx, hy = (length / 2, width / 2) if along_x else (width / 2, length / 2)
        if self.kind == "rocket":
            hx = hy = length / 2
        return Box3(x - hx, y - hy, z, x + hx, y + hy, z + height)

    def on_at(self, now: float) -> bool:
        """Whether it is on at scene time ``now``."""
        found = self.switches[0][1]
        for time, on in self.switches:
            if time <= now + 1e-9:
                found = on
        return found

    def switch(self, time: float, on: bool) -> None:
        """Switch it on (or off) from scene ``time``."""
        self.switches.append((float(time), bool(on)))
        self.switches.sort(key=lambda entry: entry[0])

    # ----- drawn -------------------------------------------------------------------------------------

    def _variant(self, now: float) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """The sprite it shows at ``now``: its key and the shapes' settings."""
        on = self.on_at(now)
        settings: dict[str, Any] = {"heading": self.heading if self.kind != "rocket" else (0, 0), "on": on}
        key: tuple[Any, ...] = (settings["heading"], on)
        if self.turn is not None and self.kind in ("car", "boat"):
            settings["turn"] = self.turn
            key += (self.turn,)
        if self.kind == "car":
            step = round(self.rolled / WHEEL_RADIUS / (math.pi / 2) * SPOKE_STEPS) % SPOKE_STEPS
            settings["spin"] = step * (math.pi / 2) / SPOKE_STEPS
            key += (step,)
        if self.kind == "boat":   # its wake while it sails
            settings["wake"] = any(s <= now <= s + t for s, t in self.drives)
            key += (settings["wake"],)
        if self.kind == "rocket" and on:
            frame = math.floor(now * FLAME_FRAMES) % (FLAME_FRAMES * 2)
            settings["now"] = frame / FLAME_FRAMES
            settings["boost"] = LIFT_FLAME if self.launch is not None and self.launch[0] <= now else 1.0
            key += (frame, settings["boost"])
        return key, settings

    def _lift(self, now: float) -> float:
        """How far its picture rises over its base now (tile units): a boat bobs while on or sailing."""
        if self.kind != "boat" or not (self.on_at(now) or any(s <= now <= s + t for s, t in self.drives)):
            return 0.0
        return BOB[0] * math.sin(2 * math.pi * now / BOB_SECONDS)

    def show_view(self, frame: Mobject) -> None:
        """Draw it at the level of detail the camera's view ``frame`` needs."""
        level = detail_for(self.frame_width / max(float(frame.width), 1e-9), self.density)
        if level != self.level:
            self.level = level
            self.refresh(self._now)

    def refresh(self, now: float | None = None) -> None:
        """Show it as it is at scene time ``now`` (default: the last time shown) where it is now."""
        now = self._now if now is None else float(now)
        self._now = now
        key, settings = self._variant(now)
        key = (*key, self.level)
        if key not in self._sprites:
            shapes = vehicle_shapes(self.kind, self.look, **settings)
            self._sprites[key] = draw_sprite(shapes, self.scale * 2**self.level, outline=self.outline)
        sprite = self._sprites[key]
        x, y, z = self.point
        cx, cy = canvas_center(sprite.canvas, self.view)
        du, dv = iso_point(x, y, z + self._lift(now))
        centre = np.array([cx + du * self.view.unit, cy - dv * self.view.unit, 0.0])
        width = sprite.canvas.width / sprite.canvas.scale * self.view.unit
        height = sprite.canvas.height / sprite.canvas.scale * self.view.unit
        left, bottom = centre[0] - width / 2, centre[1] - height / 2
        for slot, pixels in zip(self.slots, sprite.pixels):
            shown = pixels is not None and self.shown
            slot.pixel_array = pixels if shown else _NOTHING
            slot.orig_alpha_pixel_array = slot.pixel_array[:, :, 3].copy() if shown else _NOTHING[:, :, 3].copy()
            slot.points = np.array([[left, bottom + height, 0.0], [left + width, bottom + height, 0.0], [left, bottom, 0.0], [left + width, bottom, 0.0]])
            slot.iso_pieces = ((self.name, (left, bottom, left + width, bottom + height)),)   # what it shows, where (lint hidden_speaker, §89.11)
        if getattr(self, LIT, False):
            setattr(self.slots[0], LIT, True)

    def screen_box(self, point: Point3) -> tuple[float, float, float, float]:
        """Where its picture lies on screen with its middle at ``point`` (Manim units: left,
        bottom, right, top), heading as it does now."""
        sprite = next(iter(self._sprites.values()))
        c = sprite.canvas
        (u0, v0), (u1, v1) = (c.left, c.top), (c.left + c.width / c.scale, c.top + c.height / c.scale)
        du, dv = iso_point(*point)
        xs = [(u + du - self.view.u0) * self.view.unit for u in (u0, u1)]
        ys = [-(v + dv - self.view.v0) * self.view.unit for v in (v0, v1)]
        return min(xs), min(ys), max(xs), max(ys)

    def reaches(self, points: Sequence[Point3]) -> None:
        """Count ``points`` (its middle) in :attr:`reach`, where it goes on screen."""
        boxes = [self.screen_box(p) for p in points] + ([self.reach] if self.reach is not None else [])
        pad = self.view.unit * 1.5
        self.reach = (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad, max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)

    # ----- a thing that moves by itself (the stage's living things) -----------------------------------------

    def _animated(self) -> bool:
        return self.kind in ("rocket", "boat")

    def update_to(self, now: float) -> None:
        self.refresh(now)

    def changing(self, start: float, end: float) -> bool:
        if any(start <= t <= end for t, _ in self.switches[1:]):
            return True
        if any(s <= end and s + t >= start for s, t in self.drives):
            return True
        return self._animated() and (self.on_at(start) or any(on for t, on in self.switches if t <= end))

    def done(self, now: float) -> bool:
        if any(t > now for t, _ in self.switches[1:]) or any(s + t > now for s, t in self.drives):
            return False
        return not (self._animated() and self.on_at(now) and self.shown)

    def movers(self) -> list[Mobject]:
        return [self]

    def region(self, start: float = 0.0, end: float = math.inf) -> tuple[float, float, float, float]:
        if self.reach is None:
            self.reaches([self.point])
        assert self.reach is not None
        return self.reach


class IsoDrive(Animation):
    """``vehicle`` (an :class:`IsoVehicle`) moving along ``route`` (a
    :class:`~vidgen.world.iso_vehicles.VehicleRoute`): speeding up, going steadily and slowing down
    to a stop (:func:`~vidgen.world.iso_vehicles.drive_share`), turning at corners, its wheels
    turning; a rocket rising faster and faster (:func:`~vidgen.world.iso_vehicles.lift_share`) and,
    once out of the view (``gone``: when its share of the way is past this), gone."""

    def __init__(self, vehicle: IsoVehicle, route: VehicleRoute, *, run_time: float, gone: float | None = None,
                 clock: Callable[[], float] | None = None, **kwargs: Any) -> None:
        super().__init__(vehicle, run_time=run_time, rate_func=linear, **kwargs)
        self.route, self.kind, self.gone, self.clock = route, vehicle.kind, gone, clock

    def create_starting_mobject(self) -> Mobject:
        return self.mobject   # nothing to interpolate from (a copy would copy every sprite drawn)

    def begin(self) -> None:
        self._rolled = self.mobject.rolled
        super().begin()

    def interpolate_mobject(self, alpha: float) -> None:
        vehicle: IsoVehicle = self.mobject   # type: ignore[assignment]
        share = lift_share(alpha) if self.kind == "rocket" else drive_share(alpha, max(float(self.run_time), 1e-6))
        distance = share * self.route.length
        point, heading = self.route.at(distance)
        vehicle.set_pose(point, heading, self._rolled + distance, self.route.turning(distance))
        if self.gone is not None and share >= self.gone:
            vehicle.shown = False
        vehicle.refresh(self.clock() if self.clock is not None else None)


__all__ = ["FLAME_FRAMES", "LIFT_FLAME", "SPOKE_STEPS", "WAKE_LENGTH", "WAKE_SPREAD", "WHEEL_RADIUS", "IsoDrive", "IsoVehicle", "Sprite",
           "boat_wake", "draw_sprite", "frame_item", "rocket_smoke", "track_shapes", "turning_shapes", "vehicle_shapes"]
