"""Drawings of filaments and motors (DESIGN.md §95.9): microtubules (25 nm, their − end at the
centrosome and + end out, marked when large enough), actin (7 nm: the cortex under the plasma
membrane, stress fibers between focal adhesions with myosin II along them, single filaments),
intermediate filaments (10 nm), a bacterium's flagella (with the basal body and hook in its
envelope) and pili; kinesin, dynein and myosin on their tracks, facing the way they walk."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from manim import VGroup, VMobject

from vidgen.cellworld import KINDS, Capsule, Ellipse, Placed, Polyline, Region
from vidgen.cellworld.curves import Cubic, arc, line, shape_curves, smooth

from .base import RIM_PX
from .closeup import filament_detail

if TYPE_CHECKING:
    from .drawing import CellDrawing

#: The level-of-detail feature that shows each kind as a line, and its least width (px).
LINE_FEATURE = {"microtubule": ("mt_lines", 0.7), "actin_filament": ("actin_lines", 0.5), "actin_cortex": ("actin_lines", 0.45),
                "stress_fiber": ("actin_lines", 0.5), "intermediate_filament": ("if_lines", 0.6), "pilus": ("actin_lines", 0.6),
                "flagellum": (None, 1.0)}


def _curves(line_: Polyline) -> list[Cubic]:
    pts = list(line_.points)
    return smooth(pts) if len(pts) > 2 else [line(pts[0], pts[1])]


def filaments(d: "CellDrawing", kind: str, things: list[Placed]) -> VGroup:
    """The filaments of an entry."""
    hue = KINDS[kind].hue
    lines = [s for t in things for s in t.footprint if isinstance(s, Polyline)]
    feature, least = LINE_FEATURE.get(kind, ("mt_lines", 0.6))
    parts: list[VMobject] = []
    if kind == "actin_cortex":
        thickness = things[0].option("thickness", 0.3)
        band = Region.of(d.world.cell).minus(d.world.cell.inset(thickness))  # type: ignore[attr-defined]
        parts.append(d.piece(d.curves(band.curves()), None, fill=d.colors.fill(hue, 0.16)))
    if kind == "stress_fiber":
        parts += _stress_fibers(d, lines, hue)
    else:
        width = lines[0].width if lines else 0.01
        curves = [c for l in lines for c in _curves(l)]
        parts.append(d.piece(d.curves(curves), feature, stroke=d.colors.solid(hue), px=least, true_um=width))
    if kind == "microtubule":
        parts.append(_ends(d, things, hue))
    if kind == "flagellum":
        parts.append(_basal_bodies(d, things, hue))
    if d.closeups:
        parts.append(filament_detail(d, kind, lines, hue))
    return VGroup(*parts)


def _ends(d: "CellDrawing", things: list[Placed], hue: str) -> VMobject:
    """``+`` beyond each microtubule's plus end and ``−`` beside its minus end."""
    bars: list[object] = []
    for t in things:
        line_ = t.footprint[0]
        assert isinstance(line_, Polyline)
        for end, sign in ((line_.points[-1], 1), (line_.points[0], -1)):
            p, (dx, dy) = line_.at(line_.length if sign > 0 else 0.0)
            c = (end[0] + dx * 0.09 * sign - dy * (0.0 if sign > 0 else 0.07), end[1] + dy * 0.09 * sign + dx * (0.0 if sign > 0 else 0.07))
            bars.append(Capsule(c[0], c[1], 0.07, 0.016, 0.0))
            if sign > 0:
                bars.append(Capsule(c[0], c[1], 0.07, 0.016, math.pi / 2))
    return d.piece(d.path(bars), "fine", fill=d.colors.ink(hue))


def _stress_fibers(d: "CellDrawing", lines: list[Polyline], hue: str) -> list[VMobject]:
    """A bundle (its parallel actin filaments up close), myosin II along it, a focal adhesion at
    each end."""
    bands, threads, myosin, plaques = [], [], [], []
    for l in lines:
        a, b = l.points[0], l.points[-1]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        length = math.dist(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        bands.append(Capsule(mid[0], mid[1], length, l.width, angle))
        nx, ny = -math.sin(angle), math.cos(angle)
        for k in range(7):
            off = (k - 3) / 3 * l.width * 0.4
            threads.append(line((a[0] + nx * off, a[1] + ny * off), (b[0] + nx * off, b[1] + ny * off)))
        steps = int(length / 0.8)
        for k in range(1, steps):
            p = (a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps)
            myosin.append(Capsule(p[0], p[1], 0.3, 0.05, angle))
        for end in (a, b):
            plaques.append(Ellipse(end[0], end[1], 0.22, 0.09, angle + math.pi / 2))
    purple = KINDS["myosin"].hue
    return [d.piece(d.path(bands), None, fill=d.colors.fill(hue, 0.45)),
            d.piece(d.curves(threads), "actin_lines", stroke=d.colors.solid(hue), px=0.5, true_um=0.007),
            d.piece(d.path(myosin), "fine", fill=d.colors.fill(purple, 0.7)),
            d.piece(d.path(plaques), None, fill=d.colors.fill("#7C6A5A", 0.75))]


def _basal_bodies(d: "CellDrawing", things: list[Placed], hue: str) -> VGroup:
    """Each flagellum's basal body (a rotary motor: rings in the membranes, a rod through) and
    its hook."""
    rings, rods = [], []
    hooks: list[Cubic] = []
    depth = 0.0
    if d.world.envelope:
        depth = d.world.envelope[0][1].bounds()[3] - d.world.cell.bounds()[3]
    for t in things:
        base = t.option("base", t.center)
        nx, ny = t.option("normal", (1.0, 0.0))
        angle = math.atan2(ny, nx)
        rods.append(Capsule(base[0] - nx * depth / 2, base[1] - ny * depth / 2, depth + 0.035, 0.009, angle))
        # C ring (cytoplasm), MS ring (inner membrane); a Gram-negative's P ring (peptidoglycan) and L ring (outer membrane)
        levels = ((-depth - 0.014, 0.045), (-depth, 0.028)) + (((-depth * 0.38, 0.022), (0.0, 0.022)) if d.world.gram == "negative" else ())
        for f, w in levels:
            rings.append(Capsule(base[0] + nx * f, base[1] + ny * f, w, 0.008, angle + math.pi / 2))
        line_ = t.footprint[0]
        assert isinstance(line_, Polyline)
        hooks += smooth([line_.at(s)[0] for s in (0.0, 0.02, 0.04, 0.055)])
    ink = d.colors.ink(hue)
    return VGroup(d.piece(d.path(rods), "fine", fill=d.colors.solid(hue)),
                  d.piece(d.path(rings), "fine", fill=d.colors.fill(hue, 0.8), stroke=ink, px=0.6),
                  d.piece(d.curves(hooks), "fine", stroke=ink, px=1.0, true_um=0.018))


#: A motor's drawn pieces, in drawing order.
MOTOR_PIECES = ("dots", "heads", "rings", "spokes", "stalks", "arrows", "cargo", "cargo_ring")


def motor_parts(kind: str, poses: list[tuple[Placed, Any]]) -> dict[str, list[Any]]:
    """The shapes (µm) of motors at rest or walking: for each ``(thing, pose)`` — a pose of
    :func:`~vidgen.cellworld.traffic.walk_pose` with its track, or ``None`` for where it was
    placed — the dot seen from afar, heads or dynein's motor rings on the filament, stalks and
    lever arms, an arrow the way it walks, its cargo vesicle. Keys: :data:`MOTOR_PIECES` (lists
    of shapes, or of Bézier pieces for ``spokes``, ``stalks``, ``arrows``, ``cargo_ring``)."""
    out: dict[str, list[Any]] = {k: [] for k in MOTOR_PIECES}
    for t, walking in poses:
        rf = t.option("filament_width", 0.025) / 2
        if walking is None:
            base = t.option("base", t.center)
            fx, fy = math.cos(t.facing or 0.0), math.sin(t.facing or 0.0)
            nx, ny = t.normal or (-fy, fx)
            center = t.center
            heads_at: list[tuple[tuple[float, float], tuple[float, float], float]] | None = None
        else:
            pose, track = walking
            base, (dx, dy) = track.line.at(pose.s)
            fx, fy = dx * track.forward, dy * track.forward
            nx, ny = -dy * track.side, dx * track.side
            center = (base[0] + nx * (rf + t.size * 0.3), base[1] + ny * (rf + t.size * 0.3))
            heads_at = []
            for s_head, lift in pose.heads:
                p, (hx, hy) = track.line.at(s_head)
                heads_at.append((p, (hx * track.forward, hy * track.forward), lift))

        def at(a: float, b: float, base: tuple[float, float] = base, fx: float = fx, fy: float = fy, nx: float = nx, ny: float = ny) -> tuple[float, float]:
            return (base[0] + fx * a + nx * (rf + b), base[1] + fy * a + ny * (rf + b))

        def head(k: int, a: float, b: float) -> tuple[tuple[float, float], float]:
            """Head ``k``'s point ``b`` µm off the filament (``a`` along it at rest) and its
            direction's angle."""
            if heads_at is None:
                return at(a, b), math.atan2(fy, fx)
            p, (hx, hy), lift = heads_at[k]
            return (p[0] + nx * (rf + b + lift), p[1] + ny * (rf + b + lift)), math.atan2(hy, hx)

        out["dots"].append(Ellipse(center[0], center[1], t.size / 2, t.size * 0.22, math.atan2(fy, fx)))
        top = 0.06 if kind == "kinesin" else 0.045 if kind == "dynein" else 0.032
        if kind == "kinesin":
            neck = at(0.0, 0.012)
            for k, a in enumerate((-0.0045, 0.0045)):
                p, angle = head(k, a, 0.003)
                out["heads"].append(Ellipse(p[0], p[1], 0.0042, 0.0028, angle))
                q, _ = head(k, a, 0.006)
                out["stalks"].append(line(q, neck))
            out["stalks"] += smooth([neck, at(-0.004, 0.03), at(-0.01, top)])
            out["heads"].append(Ellipse(*at(-0.011, top + 0.004), 0.004, 0.0055, math.atan2(fy, fx)))
        elif kind == "dynein":
            hub = at(-0.002, 0.034)
            for k, a in enumerate((-0.006, 0.006)):
                foot, _ = head(k, a * 1.4, 0.0005)
                ring, _ = head(k, a, 0.019)
                out["rings"].append(Ellipse(ring[0], ring[1], 0.0068, 0.0068))
                out["stalks"].append(line(foot, (ring[0] - (ring[0] - foot[0]) * 0.36, ring[1] - (ring[1] - foot[1]) * 0.36)))
                out["stalks"].append(line(head(k, a, 0.026)[0], hub))
            out["stalks"] += smooth([hub, at(0.001, 0.04), at(0.004, top)])
        else:
            lever = at(0.0, 0.022)
            for k, a in enumerate((-0.018, 0.018)):
                p, angle = head(k, a, 0.003)
                out["heads"].append(Ellipse(p[0], p[1], 0.0045, 0.003, angle + 0.4 * (1 if a > 0 else -1)))
                out["stalks"].append(line(head(k, a, 0.006)[0], lever))
            out["stalks"].append(line(lever, at(0.0, top)))
        # an arrow along the track, ahead of the heads: the way the motor walks
        lead = 0.03 if kind == "myosin" else 0.016
        a, b = at(lead, 0.008), at(lead + 0.014, 0.008)
        out["arrows"] += [line(a, b), line(b, (b[0] - fx * 0.005 + nx * 0.004, b[1] - fy * 0.005 + ny * 0.004)),
                          line(b, (b[0] - fx * 0.005 - nx * 0.004, b[1] - fy * 0.005 - ny * 0.004))]
        if t.option("cargo"):
            r = 0.03
            c = at(-0.012, top + r + 0.004)
            out["cargo"].append(Ellipse(c[0], c[1], r, r))
            out["cargo_ring"] += arc(c[0], c[1], r, 0, 2 * math.pi)
    for ring in out["rings"]:
        for k in range(6):
            a = 2 * math.pi * k / 6
            out["spokes"].append(line((ring.cx + 0.002 * math.cos(a), ring.cy + 0.002 * math.sin(a)), (ring.cx + ring.a * math.cos(a), ring.cy + ring.a * math.sin(a))))
    return out


#: Pieces drawn as Bézier pieces (the others are closed shapes).
MOTOR_CURVES = frozenset({"spokes", "stalks", "arrows", "cargo_ring"})


def motor_curves(parts: dict[str, list[Any]], key: str) -> list[Cubic]:
    """A piece's Bézier pieces (µm)."""
    if key in MOTOR_CURVES:
        return list(parts[key])
    return [cv for shape in parts[key] for cv in shape_curves(shape)]


def motors(d: "CellDrawing", kind: str, things: list[Placed]) -> VGroup:
    """Motor proteins: a dot from afar; up close kinesin's two heads on the microtubule with
    its stalk, dynein's two ring-shaped motor domains on their stalks, myosin V's two heads
    36 nm apart on actin with their lever arms; an arrow the way it walks; a cargo vesicle.
    The pieces are kept by entry (``d.motor_pieces``) so a walk can move them."""
    hue = KINDS[kind].hue
    ink = d.colors.ink(hue)
    vesicle = KINDS["vesicle"].hue
    parts = motor_parts(kind, [(t, None) for t in things])
    looks: dict[str, tuple[str, dict[str, Any]]] = {
        "dots": ("particles&!particle_detail", {"fill": d.colors.solid(hue)}),
        "heads": ("particle_detail", {"fill": d.colors.solid(hue), "stroke": ink, "px": RIM_PX}),
        "rings": ("particle_detail", {"fill": d.colors.solid(hue), "stroke": ink, "px": RIM_PX}),
        "spokes": ("particle_detail", {"stroke": ink, "px": 0.7}),
        "stalks": ("particle_detail", {"stroke": d.colors.solid(hue), "px": 1.2, "true_um": 0.002}),
        "arrows": ("particle_detail", {"stroke": d.colors.text, "px": 1.6, "true_um": 0.0012}),
        "cargo": ("particle_detail", {"fill": d.colors.fill(vesicle, 0.45), "stroke": d.colors.ink(vesicle), "px": 1.0, "true_um": 0.005}),
        "cargo_ring": ("!particle_detail&particles", {"stroke": d.colors.ink(vesicle), "px": 0.6}),
    }
    pieces: dict[str, VMobject] = {}
    out: list[VMobject] = []
    for key in MOTOR_PIECES:
        if not parts[key] and key not in ("dots", "stalks", "arrows"):
            continue
        feature, style = looks[key]
        mob = d.piece(d.curves(motor_curves(parts, key)), feature, **style)
        pieces[key] = mob
        out.append(mob)
    if things:
        d.motor_pieces[things[0].entry] = pieces
    return VGroup(*out)


__all__ = ["MOTOR_PIECES", "filaments", "motor_curves", "motor_parts", "motors"]
