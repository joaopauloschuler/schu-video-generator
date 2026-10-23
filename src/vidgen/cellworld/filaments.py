"""Placing the cytoskeleton, a bacterium's appendages and motor proteins (DESIGN.md §95.9):
microtubules radiating from the centrosome (minus ends there, plus ends out at the periphery) or,
in plant cells, cortical arrays under the plasma membrane; the actin cortex, stress fibers and
single actin filaments; intermediate filaments from the nucleus to the cell's edge; flagella and
pili anchored in a bacterium's envelope; kinesin, dynein and myosin on their filaments, facing
the way they walk. A filament's points run from its minus end to its plus end. No manim."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from .catalog import CORTEX, KINDS, Kind
from .geometry import Ellipse, Point, Polyline, Shape
from .model import ObjectSpec, Placed, at_text, did_you_mean, fail, noun
from .morphology import helix, polyline_offset, ray, wavy

if TYPE_CHECKING:
    from .builder import Builder

#: Actin filaments drawn per µm² of cortex.
CORTEX_DENSITY = 26.0


def _filament(key: str, entry_id: str, kind: Kind, points: list[Point], width: float, host: str = "cytosol",
              options: tuple[tuple[str, object], ...] = ()) -> Placed:
    line = Polyline(tuple(points), width)
    start, direction = line.at(0.0)
    return Placed(key, entry_id, kind.name, line.center(), line.length, width, math.atan2(direction[1], direction[0]), (line,), (), host,
                  options=options)


def _key(entry_id: str, n: int, count: int) -> str:
    return entry_id if count == 1 else f"{entry_id}#{n + 1}"


def place_filaments(builder: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """The filaments of an ``objects`` entry (or the appendages of a bacterium)."""
    b = builder
    name = kind.name
    if name in ("flagellum", "pilus"):
        return _appendages(b, entry_id, spec, kind)
    if name == "microtubule":
        return _microtubules(b, entry_id, spec, kind)
    if name == "actin_cortex":
        return [_cortex(b, entry_id, spec, kind)]
    if name == "stress_fiber":
        return _stress_fibers(b, entry_id, spec, kind)
    if name == "intermediate_filament":
        return _intermediate(b, entry_id, spec, kind)
    return _straight(b, entry_id, spec, kind)


def _blocked(b: "Builder") -> Callable[[Point], Shape | None]:
    nuclei = [p.footprint[0] for p in b.placed if p.kind in ("nucleus", "vacuole")]

    def blocked(p: Point) -> Shape | None:
        return next((s for s in nuclei if s.contains(p, 0.12)), None)

    return blocked


def _room(b: "Builder", margin: float) -> Callable[[Point], bool]:
    def room(p: Point) -> bool:
        return b.cell.contains(p, -margin)

    return room


def _microtubules(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    rng = b.rng(entry_id)
    width = kind.width or 0.025
    if spec.at is not None:
        return _straight(b, entry_id, spec, kind)
    if b.spec.kind == "plant":
        return _cortical(b, entry_id, spec, kind)
    centrosome = next((p for p in b.placed if p.kind == "centrosome"), None)
    if centrosome is None:
        raise fail(spec, entry_id, "microtubules radiate from the centrosome (their minus ends anchored there); add a centrosome "
                                   "(contents: typical has one), or give at and angle for one microtubule")
    cx, cy = centrosome.center
    r0 = centrosome.size * 0.28
    blocked, room = _blocked(b), _room(b, 0.18)
    out = []
    for n in range(spec.count):
        angle = 2 * math.pi * (n + rng.uniform(-0.35, 0.35)) / spec.count + rng.uniform(0, 0.2)
        start = (cx + r0 * math.cos(angle), cy + r0 * math.sin(angle))
        points = ray(start, angle, spec.size or 60.0, blocked, room)
        keep = max(2, int(len(points) * rng.uniform(0.6, 1.0)))     # dynamic instability: plus ends at different lengths
        points = points[:keep]
        if len(points) < 2:
            continue
        out.append(_filament(_key(entry_id, n, spec.count), entry_id, kind, _thin(points), width, options=(("from", centrosome.key),)))
    return out


def _thin(points: list[Point], step: int = 3) -> list[Point]:
    """Every ``step``-th point of a path (and its last)."""
    out = points[::step]
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _cortical(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """Plant cortical microtubules: arrays under the plasma membrane, along it."""
    rng = b.rng(entry_id, "cortical")
    cell = b.cell
    world = b.world()
    out: list[Placed] = []
    for n in range(spec.count):
        for _ in range(200):
            t = rng.random()
            p, normal = cell.point(t), cell.normal(t)
            depth = rng.uniform(0.12, 0.3)
            start = (p[0] - normal[0] * depth, p[1] - normal[1] * depth)
            direction = math.atan2(normal[1], normal[0]) + math.pi / 2 * rng.choice((-1, 1)) + rng.uniform(-0.12, 0.12)
            length = spec.size or rng.uniform(1.5, 4.0)
            points = [start]
            for k in range(1, int(length / 0.1) + 1):
                q = (start[0] + 0.1 * k * math.cos(direction), start[1] + 0.1 * k * math.sin(direction))
                if not cell.contains(q, -0.08) or world.compartment_at(q)[0] != "cytosol":
                    break
                points.append(q)
            if len(points) >= 6:
                out.append(_filament(_key(entry_id, n, spec.count), entry_id, kind, [points[0], points[-1]], kind.width or 0.025))
                break
    return out


def _straight(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """Single straight filaments: at ``at`` (the minus end) towards ``angle``, or scattered."""
    rng = b.rng(entry_id, "straight")
    world = b.world()
    size = spec.size or kind.size_in(b.spec.kind) * (0.6 if kind.name == "microtubule" else 1.0)
    width = spec.width or kind.width or 0.007
    out = []
    for n in range(spec.count):
        for attempt in range(1 if spec.at is not None else 400):
            start = spec.at if spec.at is not None else b.random_point(rng)
            angle = math.radians(spec.angle) if spec.angle is not None else rng.uniform(0, 2 * math.pi)
            steps = max(2, int(size / 0.05))
            points = [(start[0] + size * k / steps * math.cos(angle), start[1] + size * k / steps * math.sin(angle)) for k in range(steps + 1)]
            bad = next((q for q in points if world.compartment_at(q)[0] != "cytosol" or world.region_at(q) is not None
                        or not b.cell.contains(q, -0.05)), None)
            if bad is None:
                out.append(_filament(_key(entry_id, n, spec.count), entry_id, kind, [points[0], points[-1]], width))
                break
            if spec.at is not None:
                where = world.compartment_at(bad)[1]
                raise fail(spec, entry_id, f"from {at_text(spec.at)} towards {spec.angle or 0:g}°, {size:g} µm long: it leaves the cytosol "
                                           f"(at {at_text((round(bad[0], 2), round(bad[1], 2)))}, {where}); {kind.why}; shorten it (size) or turn it (angle)")
        else:
            raise fail(spec, entry_id, f"could not fit {spec.count} of them ({size:g} µm long) into the cytosol; use a smaller count or size")
    return out


def _cortex(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> Placed:
    """The actin cortex: a meshwork of short filaments in a band ``size`` thick under the plasma
    membrane, mostly along it."""
    rng = b.rng(entry_id, "cortex")
    cell = b.cell
    thickness = spec.size or CORTEX
    perimeter = cell.perimeter()
    count = int(perimeter * thickness * CORTEX_DENSITY)
    structures = b.structures()
    lines = []
    for _ in range(count):
        t = rng.random()
        p, (nx, ny) = cell.point(t), cell.normal(t)
        depth = thickness * rng.random() ** 1.4 + 0.012
        mid = (p[0] - nx * depth, p[1] - ny * depth)
        direction = math.atan2(ny, nx) + math.pi / 2 + rng.uniform(-0.7, 0.7)
        half = rng.uniform(0.08, 0.22)
        a = (mid[0] - half * math.cos(direction), mid[1] - half * math.sin(direction))
        c = (mid[0] + half * math.cos(direction), mid[1] + half * math.sin(direction))
        if not (cell.contains(a, -0.008) and cell.contains(c, -0.008)) or any(t.contains(a) or t.contains(c) for t in structures):
            continue
        lines.append(Polyline((a, c), kind.width or 0.007))
    if not lines:
        raise fail(spec, entry_id, "no room for the cortex")
    return Placed(entry_id, entry_id, kind.name, cell.center(), thickness, thickness, 0.0, tuple(lines), (), "cytosol",
                  options=(("thickness", thickness),))


def _chord(cell: Shape, center: Point, angle: float, margin: float) -> tuple[Point, Point]:
    def edge(sign: float) -> Point:
        lo, hi = 0.0, 200.0
        for _ in range(40):
            mid = (lo + hi) / 2
            q = (center[0] + sign * mid * math.cos(angle), center[1] + sign * mid * math.sin(angle))
            if cell.contains(q, -margin):
                lo = mid
            else:
                hi = mid
        return (center[0] + sign * lo * math.cos(angle), center[1] + sign * lo * math.sin(angle))

    return edge(-1.0), edge(1.0)


def _stress_fibers(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """Stress fibers: straight bundles across the cell between focal adhesions at the plasma
    membrane, clear of the nucleus."""
    rng = b.rng(entry_id, "stress")
    cell = b.cell
    x0, y0, x1, y1 = cell.bounds()
    nuclei = [p.footprint[0] for p in b.placed if p.kind == "nucleus"]
    width = spec.width or kind.width or 0.2
    out: list[Placed] = []
    lines: list[Polyline] = []
    for n in range(spec.count):
        for _ in range(400):
            angle = math.radians(spec.angle) if spec.angle is not None else rng.uniform(-0.45, 0.45) + rng.choice((0.0, math.pi / 2)) * (rng.random() < 0.25)
            c = (rng.uniform(x0, x1) * 0.7, rng.uniform(y0, y1) * 0.8)
            if not cell.contains(c, -0.5):
                continue
            a, e = _chord(cell, c, angle, 0.12)
            line = Polyline((a, e), width)
            if line.length < (spec.size or 4.0) * 0.5:
                continue
            samples = line.outline(40)
            if any(s.contains(q, width / 2 + 0.25) for s in nuclei for q in samples):
                continue
            if any(other.distance(q) < 0.7 for other in lines for q in samples):
                continue
            lines.append(line)
            out.append(_filament(_key(entry_id, n, spec.count), entry_id, kind, [a, e], width, options=(("bipolar", True),)))
            break
        else:
            raise fail(spec, entry_id, f"no room for {spec.count} stress fibers clear of the nucleus; use a smaller count")
    return out


def _intermediate(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """Intermediate filaments: wavy strands from the nuclear envelope out to the plasma
    membrane."""
    rng = b.rng(entry_id, "if")
    nucleus = next((p for p in b.placed if p.kind == "nucleus"), None)
    room = _room(b, 0.2)
    out = []
    for n in range(spec.count):
        if nucleus is not None:
            shape = nucleus.footprint[0]
            assert isinstance(shape, Ellipse)
            t = (n + rng.uniform(0, 0.8)) / spec.count
            p, normal = shape.point(t), shape.normal(t)
            start = (p[0] + normal[0] * 0.06, p[1] + normal[1] * 0.06)
            angle = math.atan2(normal[1], normal[0]) + rng.uniform(-0.45, 0.45)
        else:
            start, angle = b.cell.center(), rng.uniform(0, 2 * math.pi)
        end = start
        for k in range(1, 4000):
            q = (start[0] + 0.05 * k * math.cos(angle), start[1] + 0.05 * k * math.sin(angle))
            if not room(q):
                break
            end = q
        if math.dist(start, end) < 0.5:
            continue
        points = wavy(start, end, f"{entry_id}:{n}", 0.1 + 0.06 * rng.random(), rng.uniform(0.9, 1.6))
        out.append(_filament(_key(entry_id, n, spec.count), entry_id, kind, points, kind.width or 0.01))
    if not out:
        raise fail(spec, entry_id, "no room for intermediate filaments")
    return out


def _appendages(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """Flagella (helical filaments from a basal body in the envelope) or pili (straight), round
    the cell or at ``angle`` (degrees round it: 0 is the right pole)."""
    if spec.at is not None:
        raise fail(spec, entry_id, f"a {noun(kind.label)} is anchored in the cell envelope: give angle (degrees round the cell, 0 = the "
                                   "right pole) instead of at")
    rng = b.rng(entry_id, "appendage")
    layers = [shape for name, shape in b.envelope if name != "capsule"]
    face = layers[-1] if layers else b.cell
    size = spec.size or kind.size
    out = []
    for n in range(spec.count):
        if spec.angle is not None:
            target = math.radians(spec.angle) + (n - (spec.count - 1) / 2) * 0.18
            t = min((k / 720 for k in range(720)), key=lambda u: abs(math.remainder(math.atan2(face.point(u)[1], face.point(u)[0]) - target, 2 * math.pi)))
        else:
            t = (n + rng.uniform(0.15, 0.85)) / spec.count + (0.08 if kind.name == "pilus" else 0.0)
        base, normal = face.point(t), face.normal(t)
        direction = math.atan2(normal[1], normal[0]) + rng.uniform(-0.45, 0.45)
        if kind.name == "flagellum":
            points = helix(base, direction, size * rng.uniform(0.9, 1.1))
        else:
            length = size * rng.uniform(0.55, 1.0)
            points = [base, (base[0] + length * math.cos(direction), base[1] + length * math.sin(direction))]
        out.append(_filament(_key(entry_id, n, spec.count), entry_id, kind, points, kind.width or 0.02, host="extracellular",
                             options=(("base", base), ("normal", normal))))
    return out


def place_motors(b: "Builder", entry_id: str, spec: ObjectSpec, kind: Kind) -> list[Placed]:
    """Motor proteins on the filaments of ``on:``, each facing the end it walks to."""
    entries = {e.id: e for e in b.entries if e.owner is None}
    allowed = " or ".join(noun(KINDS[k].label) for k in sorted(kind.surfaces))
    if spec.on is None:
        raise fail(spec, entry_id, f"a {noun(kind.label)} walks on a filament: give on: <the id of a {allowed} object>; {kind.why}")
    if spec.on not in entries:
        raise fail(spec, entry_id, f"on: '{spec.on}' is not an object of this cell{did_you_mean(spec.on, list(entries))}")
    host_kind = KINDS[entries[spec.on].kind]
    if host_kind.name not in kind.surfaces:
        raise fail(spec, entry_id, f"a {noun(kind.label)} cannot walk on a {noun(host_kind.label)} (only on a {allowed}): {kind.why}")
    hosts = [b.world().thing(k) for k in entries[spec.on].keys]
    rng = b.rng(entry_id, "motors")
    size = spec.size or kind.size
    out: list[Placed] = []
    for n in range(spec.count):
        for _ in range(400):
            host = rng.choice(hosts)
            line = rng.choice(host.footprint)
            assert isinstance(line, Polyline)
            if line.length < size * 2:
                continue
            s = rng.uniform(0.2, 0.8) * line.length
            side = rng.choice((-1.0, 1.0))
            center, base, (dx, dy) = polyline_offset(line, s, side * (line.width / 2 + size * 0.3))
            if any(math.dist(center, o.center) < size * 1.2 for o in out):
                continue
            forward = -1.0 if kind.name == "dynein" else 1.0
            facing = math.atan2(dy * forward, dx * forward)
            normal = (-dy * side, dx * side)
            key = _key(entry_id, n, spec.count)
            out.append(Placed(key, entry_id, kind.name, center, size, size * 0.45, facing, (Ellipse(center[0], center[1], size / 2, size * 0.25, facing),),
                              (), "cytosol", surface=host.key, normal=normal, facing=facing,
                              options=(("cargo", bool(spec.cargo)), ("base", base), ("filament_width", line.width))))
            break
        else:
            raise fail(spec, entry_id, f"no room for {spec.count} of them on '{spec.on}'; use a smaller count")
    return out


__all__ = ["place_filaments", "place_motors"]
