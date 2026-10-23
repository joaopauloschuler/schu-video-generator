"""The fine structure of the cell world's things, as geometry in µm (DESIGN.md §95.9): cristae
with their junctions, the nuclear envelope opened by its pores, heterochromatin and the
nucleolus's components, ER sheets joined to the envelope and the smooth-ER network, Golgi
cisternae with dilated rims and buds, thylakoids in grana, intraluminal vesicles, centrioles,
the paths of filaments. Pure functions of a thing's shape and a seed, so the model (its
compartments), the renderer and the labels agree. No manim."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

from .catalog import (
    BILAYER, CRISTA_JUNCTION, CRISTA_LUMEN, ER_LUMEN, ER_TUBULE, GOLGI_LUMEN, GOLGI_RIM, GRANUM_PERIOD, GRANUM_WIDTH, MITO_GAP,
    PERINUCLEAR_GAP, THYLAKOID_LUMEN,
)
from .geometry import ArcBand, Capsule, Ellipse, Point, Polyline, RoundedBox
from .regions import Region

#: Cristae per µm of a mitochondrion's length (lamellar cristae about 0.2 µm apart).
CRISTAE_PER_UM = 5.0
#: Pore channel: the pore membrane's diameter (midline to midline) in a section.
PORE_CHANNEL = 0.09


def rng_for(*key: object) -> random.Random:
    """A random generator seeded by ``key`` (the same key, the same numbers)."""
    return random.Random(":".join(str(k) for k in key))


def _rot(x: float, y: float, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return (x * c - y * s, x * s + y * c)


def segment(p: Point, q: Point, width: float) -> Capsule:
    """A capsule ``width`` across from ``p`` to ``q`` (its round ends centred on them)."""
    length = math.dist(p, q)
    return Capsule((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, length + width, width, math.atan2(q[1] - p[1], q[0] - p[0]))


# ----- mitochondria ---------------------------------------------------------------------------


def cristae(inner: Capsule, key: str) -> list[Capsule]:
    """The intracristal spaces of a mitochondrion whose inner boundary membrane is ``inner``:
    lamellar cristae across the long axis from either side, each opening into the
    intermembrane space through a narrow crista junction (the inner membrane is ``inner`` minus
    these shapes, so the intracristal space is continuous with the intermembrane space)."""
    rng = rng_for("cristae", key)
    length = inner.length
    count = max(2, round(length * CRISTAE_PER_UM))
    usable = 2 * inner.half + inner.radius * 0.9
    out: list[Capsule] = []
    for k in range(count):
        x = -usable / 2 + usable * (k + 0.5) / count + rng.uniform(-0.15, 0.15) * usable / count
        side = 1 if k % 2 == 0 else -1
        edge = inner.radius * math.sqrt(max(0.0, 1 - (max(abs(x) - inner.half, 0.0) / inner.radius) ** 2))
        if edge < inner.radius * 0.55:
            continue
        reach = 2 * edge * rng.uniform(0.55, 0.82)
        tilt = rng.uniform(-0.18, 0.18)
        # the junction: a narrow neck through the boundary membrane into the intermembrane space
        y_out = side * (edge + MITO_GAP * 0.5)
        y_neck = side * (edge - 0.035)
        neck_a = _local(inner, x, y_out)
        neck_b = _local(inner, x, y_neck)
        out.append(segment(neck_a, neck_b, CRISTA_JUNCTION + BILAYER))
        tip = (x + side * math.sin(tilt) * reach, side * (edge - 0.035 - reach * math.cos(tilt)))
        out.append(segment(neck_b, _local(inner, *tip), CRISTA_LUMEN + BILAYER))
    return out


def _local(capsule: Capsule, x: float, y: float) -> Point:
    px, py = _rot(x, y, capsule.angle)
    return (capsule.cx + px, capsule.cy + py)


def inner_mitochondrial(inner: Capsule, key: str) -> Region:
    """The inner membrane's region: the inner boundary minus the cristae."""
    return Region.of(inner).minus(*cristae(inner, key))


# ----- nucleus ----------------------------------------------------------------------------------


def pore_channel(center: Point, normal: Point) -> Capsule:
    """The channel a nuclear pore opens through both membranes (outer and inner meet at its rim,
    the pore membrane)."""
    across = PERINUCLEAR_GAP + 2 * BILAYER + 0.05
    return Capsule(center[0], center[1], across, PORE_CHANNEL, math.atan2(normal[1], normal[0]))


def envelope(outer: Ellipse, inner: Ellipse, pores: Sequence[tuple[Point, Point]]) -> Region:
    """The perinuclear space: between the two nuclear membranes, opened by the pores."""
    return Region.of(outer).minus(inner, *(pore_channel(c, n) for c, n in pores))


def surface_pores(outer: Ellipse, key: str, density: float) -> list[tuple[Point, float, float]]:
    """Nuclear pores seen on a nucleus's surface (``density`` per µm²): ``(centre, how much
    the surface is foreshortened there (1 face on), the radial direction)`` — a pore near the
    projected rim is seen from the side, squeezed towards the rim."""
    rng = rng_for("surface-pores", key)
    out = []
    for _ in range(int(math.pi * outer.a * outer.b * density)):
        r = math.sqrt(rng.uniform(0, 0.97))
        t = rng.uniform(0, 2 * math.pi)
        px, py = r * math.cos(t) * outer.a, r * math.sin(t) * outer.b
        x, y = _rot(px, py, outer.angle)
        out.append(((outer.cx + x, outer.cy + y), math.sqrt(max(0.05, 1 - r * r)), math.atan2(py, px) + outer.angle))
    return out


def heterochromatin(inner: Ellipse, pores: Sequence[tuple[Point, Point]], nucleoli: Sequence[Ellipse], key: str) -> Region:
    """Condensed chromatin: patches lining the inner nuclear membrane (left open at the pores,
    where the nucleoplasm reaches the pore), round the nucleoli and a few clumps inside."""
    rng = rng_for("heterochromatin", key)
    blobs: list[Ellipse] = []
    lining = inner.inset(BILAYER)
    steps = max(24, int(lining.perimeter() / 0.12))
    for k in range(steps):
        t = (k + rng.uniform(0, 0.5)) / steps
        if rng.random() < 0.28:
            continue
        p = lining.point(t)
        if any(math.dist(p, c) < 0.13 for c, _ in pores):
            continue
        r = rng.uniform(0.05, 0.16)
        nx, ny = lining.normal(t)
        blobs.append(Ellipse(p[0] - nx * r * 0.45, p[1] - ny * r * 0.45, r, r * rng.uniform(0.6, 0.9), math.atan2(ny, nx) + math.pi / 2))
    for nucleolus in nucleoli:
        for k in range(10):
            t = rng.uniform(0, 1)
            p = nucleolus.point(t)
            r = rng.uniform(0.06, 0.14)
            blobs.append(Ellipse(p[0], p[1], r, r * 0.8, rng.uniform(0, math.pi)))
    for _ in range(6):
        u, v = rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6)
        x, y = _rot(u * inner.a, v * inner.b, inner.angle)
        p = (inner.cx + x, inner.cy + y)
        if any(n.contains(p, 0.25) for n in nucleoli):
            continue
        r = rng.uniform(0.08, 0.2)
        blobs.append(Ellipse(p[0], p[1], r, r * rng.uniform(0.5, 0.9), rng.uniform(0, math.pi)))
    region = Region.of(*blobs, origin=inner.center()) if blobs else Region.of(inner).minus(inner)
    region = region.times(lining)
    return region.minus(*(Ellipse(c[0], c[1], 0.075, 0.075) for c, _ in pores))


def nucleolus_parts(shape: Ellipse, key: str) -> tuple[list[Ellipse], list[Ellipse]]:
    """A nucleolus's fibrillar centres (pale, where rDNA is transcribed at their surface) and
    the dense fibrillar component round each, in its granular component."""
    rng = rng_for("nucleolus", key)
    centres, rims = [], []
    for _ in range(40):
        if len(centres) >= max(3, round(shape.a * 4)):
            break
        u, v = rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6)
        x, y = _rot(u * shape.a, v * shape.b, shape.angle)
        p = (shape.cx + x, shape.cy + y)
        r = rng.uniform(0.05, 0.09) * shape.a / 0.9
        if not shape.contains(p, -(r + 0.08)) or any(math.dist(p, c.center()) < r + c.a + 0.12 for c in rims):
            continue
        centres.append(Ellipse(p[0], p[1], r, r))
        rims.append(Ellipse(p[0], p[1], r + 0.045, r + 0.04, rng.uniform(0, math.pi)))
    return centres, rims


# ----- endoplasmic reticulum ------------------------------------------------------------------


def er_necks(bands: Sequence[ArcBand], outer: Ellipse | None, key: str) -> list[Capsule]:
    """Where the ER is joined up: necks from the outer nuclear membrane to the first sheet (its
    lumen continuous with the perinuclear space) and between neighbouring sheets."""
    rng = rng_for("er-necks", key)
    width = ER_LUMEN + BILAYER
    necks = []
    for k, band in enumerate(bands):
        span = band.end - band.start
        for f in ((0.22, 0.68) if k == 0 else (0.12 + 0.3 * (k % 2), 0.55 + 0.3 * (k % 2))):
            angle = band.start + span * (f + rng.uniform(-0.05, 0.05))
            d = (math.cos(angle), math.sin(angle))
            far = (band.cx + d[0] * (band.radius - 0.012), band.cy + d[1] * (band.radius - 0.012))
            if k == 0:
                if outer is None:
                    continue
                near = _ellipse_towards(outer, (band.cx, band.cy), angle)
            else:
                prev = bands[k - 1]
                near = (prev.cx + d[0] * (prev.radius + 0.012), prev.cy + d[1] * (prev.radius + 0.012))
            necks.append(segment(near, far, width))
    return necks


def _ellipse_towards(ellipse: Ellipse, origin: Point, angle: float) -> Point:
    """Where a ray from ``origin`` at ``angle`` leaves ``ellipse`` (origin inside it)."""
    d = (math.cos(angle), math.sin(angle))
    lo, hi = 0.0, 2 * max(ellipse.a, ellipse.b) + math.dist(origin, ellipse.center())
    for _ in range(50):
        mid = (lo + hi) / 2
        if ellipse.contains((origin[0] + d[0] * mid, origin[1] + d[1] * mid)):
            lo = mid
        else:
            hi = mid
    return (origin[0] + d[0] * lo, origin[1] + d[1] * lo)


def er_network(center: Point, size: float, count: int, key: str, ok: Callable[[Point], bool]) -> tuple[list[Point], list[tuple[int, int]]]:
    """A smooth-ER network: about ``count`` tubules between three-way junctions spread over a
    disc ``size`` across round ``center`` (only points where ``ok``)."""
    rng = rng_for("er-network", key)
    nodes: list[Point] = []
    spacing = max(0.25, size / max(2.0, math.sqrt(count) * 1.6))
    for _ in range(count * 40):
        if len(nodes) >= max(4, round(count * 0.75)):
            break
        r = size / 2 * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        p = (center[0] + r * math.cos(a), center[1] + r * math.sin(a))
        if ok(p) and all(math.dist(p, q) >= spacing for q in nodes):
            nodes.append(p)
    edges: set[tuple[int, int]] = set()
    degree = [0] * len(nodes)
    pairs = sorted(((math.dist(nodes[i], nodes[j]), i, j) for i in range(len(nodes)) for j in range(i + 1, len(nodes))))
    for d, i, j in pairs:
        if d > spacing * 2.4 or degree[i] >= 3 or degree[j] >= 3:
            continue
        # a relative-neighbourhood test keeps the polygons open (no thin triangles)
        if any(max(math.dist(nodes[i], nodes[k]), math.dist(nodes[j], nodes[k])) < d * 0.92 for k in range(len(nodes)) if k not in (i, j)):
            continue
        edges.add((i, j))
        degree[i] += 1
        degree[j] += 1
    return nodes, sorted(edges)


def tubule(p: Point, q: Point, key: str) -> list[Capsule]:
    """A tubule from ``p`` to ``q``, gently bent (two pieces)."""
    rng = rng_for("tubule", key)
    mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    d = math.dist(p, q)
    nx, ny = (-(q[1] - p[1]) / d, (q[0] - p[0]) / d) if d > 0 else (0.0, 0.0)
    bend = rng.uniform(-0.12, 0.12) * d
    m = (mid[0] + nx * bend, mid[1] + ny * bend)
    return [segment(p, m, ER_TUBULE), segment(m, q, ER_TUBULE)]


# ----- Golgi ------------------------------------------------------------------------------------


def golgi_cisterna(band: ArcBand, index: int, count: int, key: str) -> list[object]:
    """One cisterna: a flat sac with dilated rims; the cis-most one fenestrated (cut into
    pieces), the trans-most a little swollen (towards the trans-Golgi network)."""
    rng = rng_for("cisterna", key, index)
    rim = GOLGI_RIM / 2
    pieces: list[ArcBand] = []
    if index == 0 and band.length > 0.6:
        cuts = sorted(rng.uniform(0.3, 0.7) for _ in range(1))
        gap = 0.05 / band.radius
        edges = [band.start, *(band.start + (band.end - band.start) * c for c in cuts), band.end]
        for a, b in zip(edges, edges[1:]):
            pieces.append(ArcBand(band.cx, band.cy, band.radius, band.thickness, a + (gap / 2 if a != band.start else 0.0),
                                  b - (gap / 2 if b != band.end else 0.0)))
    else:
        pieces.append(band)
    shapes: list[object] = list(pieces)
    swell = 1.25 if index == count - 1 else 1.0
    for piece in pieces:
        for (ex, ey) in piece.ends():
            shapes.append(Ellipse(ex, ey, rim * swell, rim * swell))
    return shapes


def golgi_buds(bands: Sequence[ArcBand], key: str) -> list[tuple[Point, float, str, int]]:
    """Vesicles budding at the cisternae's rims: COPI on the cis and medial cisternae, clathrin
    on the trans-most one; ``(centre, radius, coat, cisterna)``."""
    rng = rng_for("golgi-buds", key)
    out = []
    count = len(bands)
    for k, band in enumerate(bands):
        coat = "clathrin" if k == count - 1 else "copi"
        radius = 0.045 if coat == "clathrin" else 0.034
        for end, sign in ((band.end, 1.0), (band.start, -1.0)):
            if rng.random() < (0.75 if k in (0, count - 1) else 0.45):
                lateral = end + sign * (radius * 0.6 + GOLGI_RIM / 2) / band.radius
                side = rng.choice((-1.0, 1.0)) if 0 < k < count - 1 else (1.0 if k == 0 else -1.0)
                r = band.radius + side * (GOLGI_RIM / 2 + radius * 0.55)
                out.append(((band.cx + r * math.cos(lateral), band.cy + r * math.sin(lateral)), radius, coat, k))
    return out


# ----- chloroplasts -------------------------------------------------------------------------------


def thylakoids(lens: Ellipse, grana: int, key: str) -> tuple[list[Capsule], list[Capsule]]:
    """A chloroplast's thylakoids: ``grana`` stacks of discs along the long axis (appressed,
    ``GRANUM_PERIOD`` apart) joined by stroma lamellae (single thylakoids running between
    neighbouring grana); ``(granal discs, stroma lamellae)``. Their lumen is one continuous
    space (the thylakoid lumen)."""
    rng = rng_for("thylakoids", key)
    thickness = THYLAKOID_LUMEN + BILAYER
    usable = lens.a * 2 * 0.8
    rows = max(1, min(3, round(lens.b * 2 / 0.75)))
    discs: list[Capsule] = []
    lamellae: list[Capsule] = []
    stacks: list[list[tuple[float, float, int]]] = [[] for _ in range(rows)]
    for row in range(rows):
        # rows across the lens, staggered, so the grana fill the stroma as in a micrograph
        y_row = (row - (rows - 1) / 2) * lens.b * 2 * 0.62 / max(rows, 1)
        count = grana + (row % 2) * (1 if rows > 1 else 0) - (1 if rows > 1 else 0)
        for g in range(max(1, count)):
            x = -usable / 2 + usable * (g + 0.5 + 0.5 * (row % 2) - 0.25) / max(1, count) + rng.uniform(-0.06, 0.06)
            half_h = lens.b * math.sqrt(max(0.0, 1 - (x / lens.a) ** 2)) - 0.1
            n = 8 + rng.randint(-3, 6)
            height = (n - 1) * GRANUM_PERIOD
            y0 = y_row + rng.uniform(-0.05, 0.05)
            if abs(y0) + height / 2 > half_h:
                n = int(max(0.0, 2 * (half_h - abs(y0))) / GRANUM_PERIOD)
                height = (n - 1) * GRANUM_PERIOD
            if n < 3:
                continue
            width = GRANUM_WIDTH * rng.uniform(0.8, 1.1) * min(1.0, half_h / 0.5 + 0.4)
            lo = y0 - height / 2
            for k in range(n):
                discs.append(_lens_capsule(lens, x, lo + k * GRANUM_PERIOD, width, thickness))
            stacks[row].append((x, lo, n))
    for row in stacks:
        for (x0, lo0, n0), (x1, lo1, n1) in zip(row, row[1:]):
            for _ in range(2):
                k0, k1 = rng.randrange(n0), rng.randrange(n1)
                lamellae.append(_lens_segment(lens, (x0 + GRANUM_WIDTH * 0.3, lo0 + k0 * GRANUM_PERIOD),
                                              (x1 - GRANUM_WIDTH * 0.3, lo1 + k1 * GRANUM_PERIOD), thickness))
    for below, above in zip(stacks, stacks[1:]):
        for (x0, lo0, n0) in below:
            near = min(above, key=lambda s: abs(s[0] - x0), default=None)
            if near is not None and abs(near[0] - x0) < usable / max(grana, 1):
                x1, lo1, _n1 = near
                lamellae.append(_lens_segment(lens, (x0, lo0 + (n0 - 1) * GRANUM_PERIOD), (x1, lo1), thickness))
    return discs, lamellae


def _lens_capsule(lens: Ellipse, x: float, y: float, length: float, width: float) -> Capsule:
    px, py = _rot(x, y, lens.angle)
    return Capsule(lens.cx + px, lens.cy + py, length, width, lens.angle)


def _lens_segment(lens: Ellipse, a: Point, b: Point, width: float) -> Capsule:
    pa, pb = _rot(*a, lens.angle), _rot(*b, lens.angle)
    return segment((lens.cx + pa[0], lens.cy + pa[1]), (lens.cx + pb[0], lens.cy + pb[1]), width)


def starch_grains(lens: Ellipse, key: str) -> list[Ellipse]:
    """One or two starch grains in the stroma, between the grana."""
    rng = rng_for("starch", key)
    out = []
    for k in range(1 + (lens.a > 2.0)):
        x = (-0.22 + 0.44 * k) * lens.a + rng.uniform(-0.05, 0.05) * lens.a
        y = rng.choice((-1, 1)) * lens.b * 0.42
        a = min(0.32, lens.a * 0.12)
        px, py = _rot(x, y, lens.angle)
        out.append(Ellipse(lens.cx + px, lens.cy + py, a, a * 0.55, lens.angle + rng.uniform(-0.3, 0.3)))
    return out


# ----- endosomes, centrosome ----------------------------------------------------------------------


def intraluminal_vesicles(body: Ellipse, key: str) -> list[Ellipse]:
    """A multivesicular body's intraluminal vesicles (about 50 nm, budded inwards from its
    limiting membrane)."""
    rng = rng_for("ilv", key)
    out: list[Ellipse] = []
    wanted = max(4, round(body.a * body.b / 0.0009 * 0.3))       # about a third of the lumen
    for _ in range(wanted * 30):
        if len(out) >= wanted:
            break
        r = rng.uniform(0.022, 0.03)
        u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
        x, y = _rot(u * body.a, v * body.b, body.angle)
        p = (body.cx + x, body.cy + y)
        if body.contains(p, -(r + 0.02)) and all(math.dist(p, e.center()) > r + e.a + 0.012 for e in out):
            out.append(Ellipse(p[0], p[1], r, r))
    return out


def endosome_tubules(body: Ellipse, key: str) -> list[Capsule]:
    """An early endosome's tubules (about 50–60 nm across) reaching out of its vacuolar body."""
    rng = rng_for("endosome-tubules", key)
    out = []
    for k in range(rng.randint(2, 3)):
        angle = rng.uniform(0, 2 * math.pi) if k == 0 else out[0].angle + rng.uniform(1.8, 4.4) * (1 if k == 1 else -1)
        d = (math.cos(angle), math.sin(angle))
        start = (body.cx + d[0] * body.a * 0.5, body.cy + d[1] * body.b * 0.5)
        length = rng.uniform(0.9, 1.4) * body.a
        end = (start[0] + d[0] * length, start[1] + d[1] * length)
        out.append(segment(start, end, 0.055))
    return out


def centrioles(center: Point, angle: float) -> tuple[Capsule, Point]:
    """A centrosome's mother centriole (cut lengthwise: about 0.25 × 0.45 µm) and where its
    daughter is, at right angles to it (cut across: a ring of nine triplets, 0.25 µm)."""
    mother = Capsule(center[0] - 0.1 * math.cos(angle), center[1] - 0.1 * math.sin(angle), 0.45, 0.25, angle)
    tip = (center[0] + 0.25 * math.cos(angle) - 0.05 * math.sin(angle), center[1] + 0.25 * math.sin(angle) + 0.05 * math.cos(angle))
    return mother, tip


# ----- filaments -----------------------------------------------------------------------------------


def ray(start: Point, direction: float, length: float, blocked: Callable[[Point], object | None], room: Callable[[Point], bool],
        step: float = 0.08) -> list[Point]:
    """A filament's path from ``start``: straight ahead, bending round what ``blocked`` returns
    (a shape it may not cross: the nucleus), stopping where ``room`` says it may not go on
    (the plasma membrane) or after ``length`` µm."""
    points = [start]
    angle = direction
    p = start
    travelled = 0.0
    turned = 0.0
    while travelled < length:
        nxt = (p[0] + step * math.cos(angle), p[1] + step * math.sin(angle))
        if not room(nxt):
            break
        shape = blocked(nxt)
        if shape is not None:
            # turn along the obstacle: towards whichever side keeps closer to the way it was going
            cx, cy = shape.center()  # type: ignore[attr-defined]
            away = math.atan2(p[1] - cy, p[0] - cx)
            options = [away + math.pi / 2, away - math.pi / 2]
            angle = min(options, key=lambda a: abs(math.remainder(a - direction, 2 * math.pi)))
            turned += 1
            if turned > 80:
                break
            continue
        p = nxt
        points.append(p)
        travelled += step
        angle += math.remainder(direction - angle, 2 * math.pi) * 0.08
    return points


def wavy(start: Point, end: Point, key: str, amplitude: float = 0.12, wavelength: float = 1.2) -> list[Point]:
    """Points of a gently wavy line from ``start`` to ``end`` (intermediate filaments)."""
    rng = rng_for("wavy", key)
    d = math.dist(start, end)
    if d == 0:
        return [start, end]
    ux, uy = (end[0] - start[0]) / d, (end[1] - start[1]) / d
    phase = rng.uniform(0, 2 * math.pi)
    n = max(3, int(d / 0.12))
    out = []
    for k in range(n + 1):
        s = d * k / n
        off = amplitude * math.sin(phase + 2 * math.pi * s / wavelength) * math.sin(math.pi * k / n)
        out.append((start[0] + ux * s - uy * off, start[1] + uy * s + ux * off))
    return out


def helix(base: Point, direction: float, length: float, amplitude: float = 0.18, wavelength: float = 2.3) -> list[Point]:
    """A bacterial flagellum's filament seen from the side: a helix (a sine in projection),
    starting straight at its hook."""
    out = []
    n = max(4, int(length / 0.05))
    c, s = math.cos(direction), math.sin(direction)
    for k in range(n + 1):
        u = length * k / n
        grow = min(1.0, u / 0.6)
        v = amplitude * grow * math.sin(2 * math.pi * u / wavelength)
        out.append((base[0] + u * c - v * s, base[1] + u * s + v * c))
    return out


def polyline_offset(line: Polyline, s: float, side: float) -> tuple[Point, Point, Point]:
    """A point ``side`` µm beside ``line`` at ``s`` µm from its start (to the left for positive
    ``side``), the line's point there and its direction."""
    p, (dx, dy) = line.at(s)
    return (p[0] - dy * side, p[1] + dx * side), p, (dx, dy)


def box_side_point(box: RoundedBox, t: float, inward: float) -> tuple[Point, float]:
    """A point ``inward`` µm inside ``box``'s outline at ``t`` (0..1 round it) and the outline's
    direction there (radians)."""
    p = box.point(t)
    nx, ny = box.normal(t)
    return (p[0] - nx * inward, p[1] - ny * inward), math.atan2(ny, nx) + math.pi / 2
