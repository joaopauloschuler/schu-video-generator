"""The vehicles' drawings (DESIGN.md §69.52, §69.53): a bicycle, a car, a bus, a boat, a hot-air
balloon and a toy rocket from primitives, in the two colours of a prop (``main``: the frame, the
body, the hull or the envelope; ``detail``: the saddle and grips, a stripe, the basket or the nose
and fins) plus shades, the characters' ink, dark tyres and see-through glass. Original simple
shapes, side on, the front on the right; the toy rocket is a toy (fins, a round window, a
parachute), not a copy of any real craft.

Each is drawn in a character's heights (the measures of :data:`~vidgen.cartoon.vehicles.VEHICLES`)
and scaled to prop units (top at 1). The parts that turn are returned apart: each wheel's spokes
(or a car's hub bolts) about its axle, and a bicycle's cranks and pedals about the crank axle.
The windows are drawn see-through (:data:`GLASS_OPACITY`) so riders sitting behind the side show
in them; a car's, a bus's and a boat's side and a balloon's basket hide the riders' lower bodies.
A toy rocket has two shapes (:data:`~vidgen.cartoon.props.PROP_SHAPES`): its parachute folded,
and open above it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from manim import ORIGIN, Circle, Line, VGroup, VMobject

from vidgen.cartoon.character import OUTLINE_WIDTH
from vidgen.cartoon.props import GLASS, PROP_SHAPES, TV_CASE, _arc, _circle, _handle, _line, _Paint, _poly, _rect
from vidgen.cartoon.vehicles import VEHICLES

#: How opaque a vehicle's window glass is (riders behind it show through).
GLASS_OPACITY = 0.3
#: A wheel's hub and spokes, a car's headlights (fixed light colours, as no theme token is light in
#: every theme).
HUB = "#D9DDE3"
SPOKE = "#9AA1AC"
HEADLIGHT = "#FFF4C2"


@dataclass
class VehicleDrawing:
    """A vehicle drawn in prop units: its ``members`` (back to front) and the ones that turn:
    each wheel's ``(group, axle)``, and a bicycle's ``crank`` ``(group, axle)``; ``shapes``: a
    vehicle drawn in several shapes (a toy rocket) gets them instead of members."""

    members: list[VMobject]
    wheels: list[tuple[VMobject, tuple[float, float]]] = field(default_factory=list)
    crank: tuple[VMobject, tuple[float, float]] | None = None
    shapes: dict[str, list[VMobject]] = field(default_factory=dict)


def _glass(points: list[tuple[float, float]], p: _Paint) -> VMobject:
    return _poly(points, GLASS, p).set_fill(GLASS, opacity=GLASS_OPACITY)


def _spokes(cx: float, cy: float, inner: float, outer: float, count: int, color: str, width: float) -> VGroup:
    """``count`` lines from ``inner`` to ``outer`` about (cx, cy), the first straight ahead."""
    angles = np.linspace(0.0, 2 * np.pi, count, endpoint=False)
    return VGroup(*(
        Line([cx + inner * np.cos(a), cy + inner * np.sin(a), 0.0], [cx + outer * np.cos(a), cy + outer * np.sin(a), 0.0], stroke_width=width, color=color)
        for a in angles
    ))


def _road_wheel(cx: float, cy: float, r: float, p: _Paint) -> tuple[list[VMobject], VMobject]:
    """A car's or a bus's wheel: a dark tyre, a light hub and bolts that show it turning."""
    bolts = VGroup(*(
        _circle(cx + 0.55 * r * np.cos(a), cy + 0.55 * r * np.sin(a), 0.07 * r, SPOKE, p, outline=False)
        for a in np.linspace(0.0, 2 * np.pi, 5, endpoint=False)
    ))
    turning = VGroup(_spokes(cx, cy, 0.12 * r, 0.42 * r, 5, SPOKE, 1.4 * OUTLINE_WIDTH), bolts)
    tyre = _circle(cx, cy, r, TV_CASE, p)
    hub = _circle(cx, cy, 0.55 * r * 1.35, HUB, p)
    cap = _circle(cx, cy, 0.12 * r, p.dark(p.main), p)
    return [tyre, hub, turning, cap], turning


def _arch(cx: float, cy: float, r: float, p: _Paint) -> VMobject:
    """The dark wheel arch over a wheel (its upper half)."""
    return _poly(_arc(cx, cy, r, 0, 180, 16), p.dark(p.main), p, outline=False)


def _bicycle(p: _Paint) -> VehicleDrawing:
    wheels: list[tuple[VMobject, tuple[float, float]]] = []
    members: list[VMobject] = []
    for x, y, r in _measures("bicycle"):
        tyre = Circle(radius=0.93 * r).move_to([x, y, 0.0]).set_fill(opacity=0).set_stroke(p.ink, width=2.2 * OUTLINE_WIDTH)
        rim = Circle(radius=0.8 * r).move_to([x, y, 0.0]).set_fill(opacity=0).set_stroke(HUB, width=1.0 * OUTLINE_WIDTH)
        spokes = _spokes(x, y, 0.1 * r, 0.78 * r, 8, SPOKE, 0.7 * OUTLINE_WIDTH)
        edge = Circle(radius=r).move_to([x, y, 0.0]).set_fill(opacity=0).set_stroke(p.ink, width=0)   # the wheel's box: its bottom on the ground
        members += [edge, rim, spokes, tyre, _circle(x, y, 0.13 * r, p.main, p)]
        wheels.append((spokes, (x, y)))
    height, crank_spec = VEHICLES["bicycle"].height, VEHICLES["bicycle"].crank
    assert crank_spec is not None
    (rx, ry, _), (fx, fy, _) = _measures("bicycle")
    cx, cy, r = (v * height for v in crank_spec)
    rear, crank, seat_top, head_top, head_low, front = (rx, ry), (cx, cy), (-0.075, 0.235), (0.12, 0.245), (0.13, 0.2), (fx, fy)
    tubes = [(crank, rear), (rear, seat_top), (crank, seat_top), (seat_top, head_top), (crank, head_low), (head_top, front)]
    for a, b in tubes:
        members += _handle([a, b], p.main, p, width=2.4)
    members += _handle([head_top, (0.125, 0.33), (0.122, 0.355)], p.dark(p.main), p, width=2.2)    # the stem
    members += _handle([(0.16, 0.355), (0.122, 0.355), (0.095, 0.352)], p.dark(p.main), p, width=2.2)  # the handlebar
    members.append(_rect(0.075, 0.345, 0.11, 0.38, p.detail, p, radius=0.01))         # the grip
    members.append(_rect(-0.086, 0.232, -0.072, 0.25, p.dark(p.main), p))           # the seat post
    members.append(_poly([(-0.13, 0.262), (-0.04, 0.258), (-0.03, 0.247), (-0.12, 0.243)], p.detail, p, round_by=0.005))
    members.append(_circle(cx, cy, 0.03, p.dark(p.detail), p))                        # the chainring
    arms = VGroup(*_handle([(cx - r, cy), (cx + r, cy)], p.dark(p.main), p, width=1.8))
    pedals = VGroup(*(_rect(x - 0.018, cy - 0.007, x + 0.018, cy + 0.007, TV_CASE, p) for x in (cx - r, cx + r)))
    turning = VGroup(arms, pedals)
    members.append(turning)
    return VehicleDrawing(members, wheels, (turning, crank))


def _measures(kind: str) -> list[tuple[float, float, float]]:
    """A vehicle's wheels (x, y, radius) in a character's heights (its spec is in prop units)."""
    height = VEHICLES[kind].height
    return [(x * height, y * height, r * height) for x, y, r in VEHICLES[kind].wheels]


def _road_wheels(kind: str, p: _Paint, members: list[VMobject]) -> list[tuple[VMobject, tuple[float, float]]]:
    """A car's or a bus's wheels under their arches, added to ``members``; the turning parts."""
    wheels: list[tuple[VMobject, tuple[float, float]]] = []
    for x, y, r in _measures(kind):
        members.append(_arch(x, y, 1.25 * r, p))
        drawn, turning = _road_wheel(x, y, r, p)
        members += drawn
        wheels.append((turning, (x, y)))
    return wheels


def _car(p: _Paint) -> VehicleDrawing:
    roof, belt, band = 1.12, 0.55, 1.05
    left, right, top_left, top_right = (-0.73, belt), (0.6, belt), (-0.62, roof), (0.25, roof)

    def x_at(edge_from: tuple[float, float], edge_to: tuple[float, float], y: float) -> float:
        share = (y - edge_from[1]) / (edge_to[1] - edge_from[1])
        return edge_from[0] + (edge_to[0] - edge_from[0]) * share

    xl, xr = x_at(left, top_left, band), x_at(right, top_right, band)
    members: list[VMobject] = [
        _glass([(-0.6, belt), (xl + 0.09, band), (-0.17, band), (-0.17, belt)], p),
        _glass([(-0.1, belt), (-0.1, band), (xr - 0.07, band), (0.5, belt)], p),
        _poly([left, (xl, band), (xl + 0.1, band), (-0.6, belt)], p.main, p),
        _rect(-0.17, belt, -0.1, band, p.main, p),
        _poly([right, (xr, band), (xr - 0.08, band), (0.5, belt)], p.main, p),
        _poly([(xl, band), top_left, top_right, (xr, band)], p.main, p),
        _rect(-0.98, 0.1, -0.9, 0.2, p.dark(p.detail), p, radius=0.03),
        _rect(0.9, 0.1, 0.98, 0.2, p.dark(p.detail), p, radius=0.03),
        _rect(-0.95, 0.07, 0.95, 0.58, p.main, p, radius=0.14),
        Line([-0.88, 0.48, 0.0], [0.88, 0.48, 0.0], stroke_width=1.5 * OUTLINE_WIDTH, color=p.light(p.main)),
        Line([-0.13, 0.14, 0.0], [-0.13, 0.56, 0.0], stroke_width=OUTLINE_WIDTH, color=p.ink),
        Line([0.55, 0.14, 0.0], [0.55, 0.56, 0.0], stroke_width=OUTLINE_WIDTH, color=p.ink),
        _rect(0.0, 0.43, 0.1, 0.46, p.dark(p.main), p, outline=False),
        _rect(-0.55, 0.43, -0.45, 0.46, p.dark(p.main), p, outline=False),
        _poly([(0.87, 0.38), (0.95, 0.38), (0.95, 0.47), (0.87, 0.47)], HEADLIGHT, p, round_by=0.02),
        _rect(-0.95, 0.36, -0.9, 0.46, p.detail, p, radius=0.015),
    ]
    return VehicleDrawing(members, _road_wheels("car", p, members))


def _bus(p: _Paint) -> VehicleDrawing:
    belt, top = 0.62, 1.27
    members: list[VMobject] = [_glass([(-1.52, belt), (-1.52, top), (1.52, top), (1.52, belt)], p)]
    for x0, x1 in ((-1.6, -1.46), (-0.78, -0.7), (0.0, 0.08), (0.64, 0.72), (1.02, 1.08), (1.5, 1.6)):
        members.append(_rect(x0, belt - 0.02, x1, top + 0.02, p.main, p))
    members += [
        _rect(1.12, 1.15, 1.46, 1.24, TV_CASE, p, radius=0.02),
        _rect(1.15, 1.17, 1.43, 1.22, p.light(p.detail), p, outline=False),
        _rect(-1.6, top - 0.02, 1.6, 1.45, p.main, p, radius=0.1),
        _rect(-1.63, 0.1, -1.53, 0.24, p.dark(p.detail), p, radius=0.03),
        _rect(1.53, 0.1, 1.63, 0.24, p.dark(p.detail), p, radius=0.03),
        _rect(-1.6, 0.1, 1.6, belt + 0.02, p.main, p, radius=0.12),
        _rect(-1.58, 0.46, 1.58, 0.54, p.detail, p, outline=False),
    ]
    for x0, x1 in ((0.72, 0.87), (0.87, 1.02)):   # the folding door, glass above, a panel below
        members += [_rect(x0, 0.14, x1, top - 0.02, p.dark(p.main), p), _glass([(x0 + 0.025, 0.66), (x1 - 0.025, 0.66), (x1 - 0.025, 1.2), (x0 + 0.025, 1.2)], p)]
    members += [
        _poly([(1.52, 0.26), (1.6, 0.26), (1.6, 0.36), (1.52, 0.36)], HEADLIGHT, p, round_by=0.02),
        _rect(-1.6, 0.26, -1.54, 0.38, p.detail, p, radius=0.015),
    ]
    return VehicleDrawing(members, _road_wheels("bus", p, members))


def _boat(p: _Paint) -> VehicleDrawing:
    """A small open boat with an outboard motor at its stern (the left): its side is as high as a
    seated rider's waist."""
    hull = [(-0.8, 0.4), (-0.77, 0.07), (-0.6, 0.0), (0.42, 0.0), (0.66, 0.1), (0.8, 0.27), (0.88, 0.46), (0.0, 0.4)]
    members: list[VMobject] = [
        _rect(-0.91, 0.0, -0.86, 0.4, TV_CASE, p),                                      # the motor's leg
        _poly([(-0.95, 0.0), (-0.84, 0.0), (-0.86, 0.05), (-0.93, 0.05)], TV_CASE, p),  # its foot
        _poly(hull, p.main, p, round_by=0.02),
        _poly([(-0.78, 0.27), (0.79, 0.27), (0.82, 0.33), (-0.785, 0.33)], p.detail, p, outline=False),   # a stripe
        *_handle([(-0.8, 0.4), (0.0, 0.4), (0.88, 0.46)], p.dark(p.main), p, width=2.4),   # the gunwale's rim
        _rect(-0.99, 0.38, -0.8, 0.58, p.detail, p, radius=0.04),                       # the motor's head
        _rect(-0.97, 0.47, -0.82, 0.5, p.dark(p.detail), p, outline=False),
        *_handle([(-0.82, 0.5), (-0.6, 0.53)], TV_CASE, p, width=2.0),                 # the tiller
    ]
    return VehicleDrawing(members)


def _envelope_outline(cx: float, cy: float, r: float, mouth: float, mouth_y: float) -> list[tuple[float, float]]:
    """A balloon's envelope: a circle about (``cx``, ``cy``) narrowing to a mouth ``mouth`` wide
    at ``mouth_y``, counterclockwise."""
    return [*_arc(cx, cy, r, -45, 225, 31), (cx - mouth / 2, mouth_y), (cx + mouth / 2, mouth_y)]


def _hot_air_balloon(p: _Paint) -> VehicleDrawing:
    """A wicker basket under a round envelope with two bands of gores (a lighter and a main one)
    narrowing to its mouth, ropes and a small burner between them."""
    outline = _envelope_outline(0.0, 1.62, 0.48, 0.34, 1.2)
    members: list[VMobject] = [
        *(_line(x0, 0.48, x1, 1.2, p.ink, 0.8 * OUTLINE_WIDTH) for x0, x1 in ((-0.34, -0.17), (-0.12, -0.06), (0.12, 0.06), (0.34, 0.17))),
        _rect(-0.07, 1.08, 0.07, 1.2, TV_CASE, p, radius=0.015),                         # the burner
        _poly(outline, p.main, p),
        _poly([(0.62 * x, y) for x, y in outline], p.light(p.main), p, outline=False),
        _poly([(0.24 * x, y) for x, y in outline], p.main, p, outline=False),
        _rect(-0.17, 1.17, 0.17, 1.23, p.dark(p.main), p, radius=0.02),                  # the mouth's ring
        _rect(-0.36, 0.0, 0.36, 0.48, p.detail, p, radius=0.04),                         # the basket
        *(_line(-0.34, y, 0.34, y, p.dark(p.detail), 0.9 * OUTLINE_WIDTH) for y in (0.12, 0.24, 0.36)),
        _rect(-0.39, 0.44, 0.39, 0.51, p.dark(p.detail), p, radius=0.02),               # its rim
    ]
    return VehicleDrawing(members)


def _rocket_body(p: _Paint) -> list[VMobject]:
    """A toy rocket standing on its fins: a round-topped body, a pointed nose, a round window and a
    dark nozzle."""
    return [
        _poly([(-0.035, 0.07), (0.035, 0.07), (0.028, 0.03), (-0.028, 0.03)], TV_CASE, p),                   # the nozzle
        _poly([(-0.052, 0.24), (-0.12, 0.05), (-0.12, 0.0), (-0.052, 0.07)], p.detail, p, round_by=0.008),   # the fins
        _poly([(0.052, 0.24), (0.052, 0.07), (0.12, 0.0), (0.12, 0.05)], p.detail, p, round_by=0.008),
        _rect(-0.055, 0.07, 0.055, 0.43, p.main, p, radius=0.02),
        _poly([(-0.055, 0.42), (0.055, 0.42), (0.04, 0.48), (0.018, 0.53), (0.0, 0.55), (-0.018, 0.53), (-0.04, 0.48)], p.detail, p),
        _circle(0.0, 0.31, 0.032, GLASS, p),
        _rect(-0.012, 0.0, 0.012, 0.13, p.dark(p.detail), p, radius=0.006),                                 # the fin facing us
    ]


def _toy_rocket(p: _Paint) -> VehicleDrawing:
    """A toy rocket, its parachute folded or open above it on four lines."""
    canopy = [*_arc(0.0, 0.92, 0.26, 0, 180, 18), (-0.26, 0.92), (-0.13, 0.95), (0.0, 0.92), (0.13, 0.95), (0.26, 0.92)]
    chute: list[VMobject] = [
        *(_line(x, 0.93, 0.0, 0.55, p.ink, 0.7 * OUTLINE_WIDTH) for x in (-0.25, -0.09, 0.09, 0.25)),
        _poly(canopy, p.light(p.detail), p),
        _poly([*_arc(0.0, 0.92, 0.26, 65, 115, 6), (-0.09, 0.93), (0.09, 0.93)], p.detail, p, outline=False),
        *_rocket_body(p),
    ]
    folded, opened = PROP_SHAPES["toy_rocket"]
    return VehicleDrawing([], shapes={folded: _rocket_body(p), opened: chute})


_DRAWERS = {"bicycle": _bicycle, "car": _car, "bus": _bus, "boat": _boat, "hot_air_balloon": _hot_air_balloon, "toy_rocket": _toy_rocket}


def draw_vehicle(kind: str, paint: _Paint) -> VehicleDrawing:
    """A ``kind`` vehicle (:data:`~vidgen.cartoon.vehicles.VEHICLE_KINDS`) in ``paint``'s colours,
    in prop units (its feet at the origin, its top at 1), as drawn facing right."""
    drawing = _DRAWERS[kind](paint)
    unit = 1.0 / VEHICLES[kind].height
    VGroup(*drawing.members, *(m for members in drawing.shapes.values() for m in members)).scale(unit, about_point=ORIGIN)
    drawing.wheels = [(group, (x * unit, y * unit)) for group, (x, y) in drawing.wheels]
    if drawing.crank is not None:
        group, (x, y) = drawing.crank
        drawing.crank = (group, (x * unit, y * unit))
    return drawing


__all__ = ["GLASS_OPACITY", "VehicleDrawing", "draw_vehicle"]
