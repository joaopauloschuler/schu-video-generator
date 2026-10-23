"""Membrane traffic and motors as plans (DESIGN.md §95.10): the rules and the planned shapes of
the ``cell`` scene's ``motor_walk``, ``endocytosis`` and ``exocytosis`` actions, as plain data
without manim. A motor walks hand over hand along its filament (kinesin-1 8 nm steps to the
microtubule's + end, cytoplasmic dynein 8 nm steps to its − end, myosin V 36 nm steps to the
actin filament's barbed end) carrying its cargo; clathrin-mediated endocytosis gathers
receptor–ligand complexes in a coated pit that invaginates, is pinched off by dynamin and loses
its coat; exocytosis docks a vesicle by its SNAREs, opens a fusion pore and flattens the vesicle
into the plasma membrane, releasing its cargo. Membrane shapes are mid-lines in nanometres in a
local frame of the site (``u`` along the membrane, ``v`` out of the cell).

Numbers: Alberts ch. 13 and 16, Lodish ch. 14 and 18 (coated pits 100–200 nm, coated vesicles
50–100 nm, the clathrin coat about 18 nm thick, kinesin 8 nm steps at about 0.8 µm/s, myosin V
36 nm steps)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .catalog import COATS, KINDS
from .geometry import Point, Polyline
from .model import CellWorld, Placed, noun

#: Motor steps (µm), speeds (µm/s) and the end of their filament each walks to.
MOTOR_STEPS = {"kinesin": 0.008, "dynein": 0.008, "myosin": 0.036}
MOTOR_SPEEDS = {"kinesin": 0.8, "dynein": 1.0, "myosin": 0.4}
MOTOR_ENDS = {"kinesin": "plus", "dynein": "minus", "myosin": "plus"}
MOTOR_WHY = {
    "kinesin": "kinesin-1 walks towards a microtubule's + end (out from the centrosome to the cell's periphery: anterograde); to carry "
               "cargo to the − end use dynein",
    "dynein": "cytoplasmic dynein walks towards a microtubule's − end (in to the centrosome: retrograde); to carry cargo to the + end "
              "use kinesin",
    "myosin": "myosin V walks towards an actin filament's + (barbed) end; myosin VI is the one that walks to the − end",
}
#: How far from its filament's end a motor stops (µm).
END_MARGIN = 0.02
#: A clathrin-coated pit and vesicle (nm): the vesicle's radius, the pit's reach along the membrane.
PIT_RADIUS, PIT_HALF = 40.0, 150.0
#: The membrane's mid-line is sampled at this many points.
PROFILE_POINTS = 260


# ----- motors --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MotorTrack:
    """Where a motor is: its filament's line, how far along it (``s``, µm from the − end), the
    side of the filament it walks on and the way it walks (``forward``: +1 to the + end)."""

    line: Polyline
    s: float
    side: float
    forward: float

    def room(self) -> float:
        """How far the motor can walk before its filament ends (µm)."""
        return (self.line.length - self.s if self.forward > 0 else self.s) - END_MARGIN


def motor_track(world: CellWorld, thing: Placed) -> MotorTrack:
    """The track of a placed motor (kinesin, dynein, myosin)."""
    host = world.thing(thing.surface)  # type: ignore[arg-type]
    line = host.footprint[thing.option("track", 0)]
    assert isinstance(line, Polyline)
    s = thing.option("s")
    if s is None:                       # placed before tracks were recorded: the nearest point
        base = thing.option("base", thing.center)
        s = min((k * line.length / 400 for k in range(401)), key=lambda q: math.dist(line.at(q)[0], base))
    forward = -1.0 if thing.kind == "dynein" else 1.0
    return MotorTrack(line, float(s), float(thing.option("side", 1.0)), forward)


def walk_problem(world: CellWorld, entry_id: str, distance: float | None, toward: str | None, walked: float = 0.0) -> str | None:
    """Why the motors of ``entry_id`` cannot walk ``distance`` µm (``toward`` the + or − end),
    having walked ``walked`` already, or ``None``."""
    try:
        entry = world.entry(entry_id)
    except KeyError:
        return f"'{entry_id}' is not an object of this cell"
    if entry.kind not in MOTOR_STEPS:
        return f"'{entry_id}' is a {noun(KINDS[entry.kind].label)}; motor_walk moves motors (kinesin, dynein, myosin) along their filaments"
    if toward is not None and toward != MOTOR_ENDS[entry.kind]:
        return f"{noun(KINDS[entry.kind].label)} cannot walk to the {toward} end: {MOTOR_WHY[entry.kind]}"
    for thing in world.members(entry_id):
        room = motor_track(world, thing).room() - walked
        if room < MOTOR_STEPS[entry.kind]:
            return f"'{thing.key}' is at the {MOTOR_ENDS[entry.kind]} end of its filament already: it has no further to walk"
        if distance is not None and distance > room + 1e-9:
            return (f"'{thing.key}' is {room * 1000:.0f} nm from the {MOTOR_ENDS[entry.kind]} end of its filament; walk at most that far "
                    f"(distance: {room * 1000:.0f} nm)")
    return None


def walk_distance(world: CellWorld, entry_id: str, distance: float | None, walked: float = 0.0) -> float:
    """How far the motors walk (µm): ``distance``, else as far as the nearest end allows, at
    most 1 µm."""
    if distance is not None:
        return distance
    rooms = [motor_track(world, t).room() - walked for t in world.members(entry_id)]
    return max(0.0, min([1.0, *rooms]))


@dataclass(frozen=True)
class MotorPose:
    """A walking motor at one moment: its centre's place along the filament (µm from the − end)
    and each head's place with how high it is lifted off the filament (µm)."""

    s: float
    heads: tuple[tuple[float, float], tuple[float, float]]


def walk_pose(kind: str, track: MotorTrack, distance: float, t: float) -> MotorPose:
    """Where a motor is ``t`` (0–1) into a walk of ``distance`` µm: hand over hand, one step
    after another — in each step the trailing head swings past the bound leading head (twice
    the step) while the stalk and its cargo move one step."""
    step = MOTOR_STEPS[kind]
    steps = max(1, round(distance / step))
    step = distance / steps
    progress = t * steps
    k = min(int(progress), steps - 1)
    u = min(max(progress - k, 0.0), 1.0)
    swing = u * u * (3 - 2 * u)
    f = track.forward
    start = track.s + f * k * step
    half = step / 2 if kind != "myosin" else step / 2
    lead = start + f * half                       # bound
    trail = start - f * half + f * 2 * step * swing
    lift = 0.006 * math.sin(math.pi * swing) if kind != "myosin" else 0.012 * math.sin(math.pi * swing)
    center = start + f * step * swing
    heads = ((trail, lift), (lead, 0.0)) if k % 2 == 0 else ((lead, 0.0), (trail, lift))
    return MotorPose(center, heads)


# ----- endocytosis and exocytosis ----------------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """A place on the plasma membrane: its ``point`` (µm), the outward ``normal``, the
    ``tangent`` (normal turned clockwise) and the membrane's ``curvature`` there (1/µm, convex
    positive)."""

    point: Point
    normal: Point
    tangent: Point
    curvature: float

    def to_world(self, u: float, v: float) -> Point:
        """The world point (µm) of local ``(u, v)`` (nm: along the membrane, out of the cell),
        following the membrane's own curve."""
        uu, vv = u / 1000.0, v / 1000.0
        bend = self.curvature * uu * uu / 2
        return (self.point[0] + self.tangent[0] * uu + self.normal[0] * (vv - bend),
                self.point[1] + self.tangent[1] * uu + self.normal[1] * (vv - bend))


def membrane_site(world: CellWorld, near: Point) -> Site:
    """The plasma-membrane point nearest ``near`` with its frame."""
    cell = world.cell
    best = min(((k / 2048, cell.point(k / 2048)) for k in range(2048)), key=lambda item: math.dist(item[1], near))  # type: ignore[attr-defined]
    t0 = best[0]
    for span in (1 / 2048, 1 / 16384, 1 / 131072):
        candidates = [t0 + span * j / 4 for j in range(-4, 5)]
        t0 = min(candidates, key=lambda t: math.dist(cell.point(t % 1.0), near))  # type: ignore[attr-defined]
    t0 %= 1.0
    p = cell.point(t0)  # type: ignore[attr-defined]
    n = cell.normal(t0)  # type: ignore[attr-defined]
    h = 1e-4
    a, b = cell.point((t0 - h) % 1.0), cell.point((t0 + h) % 1.0)  # type: ignore[attr-defined]
    # curvature from the three points' circle
    da, db = math.dist(p, a), math.dist(p, b)
    cross = (a[0] - p[0]) * (b[1] - p[1]) - (a[1] - p[1]) * (b[0] - p[0])
    curvature = abs(2 * cross / (da * db * math.dist(a, b))) if da * db > 0 else 0.0
    tangent = (n[1], -n[0])
    return Site(p, n, tangent, curvature)


def endocytosis_problem(world: CellWorld, near: Point | None) -> str | None:
    """Why the cell cannot take something up by clathrin-mediated endocytosis at ``near``."""
    if world.kind == "bacterium":
        return ("bacteria do not take up material by endocytosis: they have no endomembrane system, clathrin or dynamin "
                "(nutrients cross their envelope through porins and transporters)")
    if near is None:
        return None
    site = membrane_site(world, near)
    for depth in (0.03, 0.08, 0.13, 0.18):
        q = (site.point[0] - site.normal[0] * depth, site.point[1] - site.normal[1] * depth)
        compartment, instance = world.compartment_at(q)
        if compartment != "cytosol":
            return (f"there is no room under the plasma membrane at [{site.point[0]:.2f}, {site.point[1]:.2f}] µm: the {noun(compartment.replace('_', ' '))} "
                    f"of '{instance.split('.')[0]}' is {depth * 1000:.0f} nm inside; choose another site")
    return None


def exocytosis_problem(world: CellWorld, entry_id: str, with_: str = "cell") -> str | None:
    """Why the vesicle ``entry_id`` cannot fuse with the plasma membrane (``with_``)."""
    try:
        entry = world.entry(entry_id)
    except KeyError:
        return f"'{entry_id}' is not an object of this cell"
    if with_ != "cell":
        target = world.entry(with_).kind if with_ in [e.id for e in world.entries] else with_
        if target == "nucleus":
            return ("a vesicle cannot fuse with the nuclear envelope: the nucleus takes in and sends out molecules through its pores "
                    "(its envelope is continuous with the ER, not a target of secretory vesicles)")
        return f"exocytosis fuses a vesicle with the plasma membrane (with: cell), not with '{with_}'"
    if entry.kind != "vesicle":
        return f"'{entry_id}' is a {noun(KINDS[entry.kind].label)}; exocytosis fuses a vesicle (kind: vesicle) with the plasma membrane"
    if world.kind == "bacterium":
        return "bacteria have no secretory vesicles (they secrete through secretion systems in their envelope)"
    thing = world.members(entry_id)[0]
    coat = thing.option("coat") or "none"
    if coat != "none":
        return (f"a {coat}-coated vesicle cannot fuse: it sheds its coat first (uncoating exposes its v-SNAREs); a secretory vesicle "
                f"has coat: none")
    if thing.host != "cytosol":
        return f"the vesicle is in the {thing.host}, not the cytosol: only a vesicle in the cytosol can reach the plasma membrane"
    return None


@dataclass(frozen=True)
class Shape:
    """A membrane event's shapes at one moment (nm, the site's local frame): the plasma
    membrane's mid-line, a vesicle (centre ``v`` below the membrane and radius) or none, the
    stretch of the mid-line under a coat (index range) and the coat's fade, a neck (its half
    width and ``v`` range) for dynamin, SNARE bridges (pairs of points)."""

    membrane: tuple[Point, ...]
    vesicle: tuple[float, float] | None = None
    coat: tuple[int, int] | None = None
    coat_on_vesicle: float = 0.0
    neck: tuple[float, float, float] | None = None
    snares: tuple[tuple[Point, Point], ...] = ()


def _flat(half: float = PIT_HALF, n: int = PROFILE_POINTS) -> list[Point]:
    return [(-half + 2 * half * k / (n - 1), 0.0) for k in range(n)]


def pit(r: float, c: float, w: float | None, half: float = PIT_HALF, n: int = PROFILE_POINTS) -> tuple[list[Point], tuple[float, float, float] | None]:
    """The membrane's mid-line with a pit: a circle of radius ``r`` whose centre is ``c`` nm
    under the surface (negative: above it, a shallow dish), joined to the flat membrane
    directly or (``w``) by a neck of half width ``w``; resampled to ``n`` points evenly by
    length. Returns the points and the neck (half width, top, bottom) if there is one."""
    pts: list[Point] = []
    a = math.sqrt(max(r * r - c * c, 0.0))
    necked = w is not None and c > math.sqrt(max(r * r - w * w, 0.0))      # the circle's top lies under the surface there
    if not necked:
        # the circle meets the surface at ±a
        phi_l, phi_r = math.atan2(c, -a), math.atan2(c, a)
        if phi_l > phi_r:
            phi_r += 2 * math.pi
        # via the bottom: from the left meeting point round to the right one
        if not (phi_l < 1.5 * math.pi < phi_r or phi_l < -0.5 * math.pi < phi_r):
            phi_l, phi_r = phi_r, phi_l + 2 * math.pi
        pts += [(-half, 0.0), (-a, 0.0)]
        steps = 160
        pts += [(r * math.cos(phi_l + (phi_r - phi_l) * k / steps), -c + r * math.sin(phi_l + (phi_r - phi_l) * k / steps)) for k in range(steps + 1)]
        pts += [(a, 0.0), (half, 0.0)]
        neck = None
    else:
        top = math.sqrt(max(r * r - w * w, 0.0))
        v_join = -c + top                       # where the neck meets the circle
        fillet = min(8.0, max(1.0, -v_join * 0.45))
        pts += [(-half, 0.0), (-w - fillet, 0.0)]
        pts += [(-w - fillet + fillet * math.sin(math.pi / 2 * k / 8), -fillet + fillet * math.cos(math.pi / 2 * k / 8)) for k in range(1, 9)]
        pts.append((-w, v_join))
        phi_l = math.atan2(top, -w)
        phi_r = math.atan2(top, w) + 2 * math.pi
        steps = 200
        pts += [(r * math.cos(phi_l + (phi_r - phi_l) * k / steps), -c + r * math.sin(phi_l + (phi_r - phi_l) * k / steps)) for k in range(steps + 1)]
        pts.append((w, -fillet))
        pts += [(w + fillet - fillet * math.cos(math.pi / 2 * k / 8), -fillet + fillet * math.sin(math.pi / 2 * k / 8)) for k in range(1, 9)]
        pts.append((half, 0.0))
        neck = (w, -fillet, v_join)
    return resample(pts, n), neck


def resample(pts: Sequence[Point], n: int) -> list[Point]:
    """``n`` points evenly spaced by length along the polyline ``pts``."""
    lengths = [0.0]
    for a, b in zip(pts, pts[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    total = lengths[-1]
    out = []
    j = 0
    for k in range(n):
        goal = total * k / (n - 1)
        while j < len(pts) - 2 and lengths[j + 1] < goal:
            j += 1
        seg = lengths[j + 1] - lengths[j]
        t = (goal - lengths[j]) / seg if seg > 0 else 0.0
        out.append((pts[j][0] + (pts[j + 1][0] - pts[j][0]) * t, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * t))
    return out


def _mix(a: Sequence[Point], b: Sequence[Point], t: float) -> tuple[Point, ...]:
    return tuple((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t) for p, q in zip(a, b))


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _window(t: float, a: float, b: float) -> float:
    return _ease((t - a) / (b - a)) if b > a else float(t >= b)


def _coat_range(pts: Sequence[Point], depth: float = 4.0) -> tuple[int, int] | None:
    """The stretch of the mid-line that is in the pit (deeper than ``depth`` nm), widened a little."""
    inside = [k for k, p in enumerate(pts) if p[1] < -depth]
    if not inside:
        return None
    return max(0, inside[0] - 6), min(len(pts) - 1, inside[-1] + 6)


#: Endocytosis: the shapes the pit passes through (r, c, w) and when (share of the action).
ENDO_KEYS = ((0.12, None), (0.3, (140.0, -118.0, None)), (0.45, (46.0, 14.0, None)), (0.6, (40.0, 74.0, 13.0)), (0.72, (40.0, 86.0, 2.5)))
#: When dynamin pinches the vesicle off; when the coat is gone.
ENDO_SCISSION, ENDO_UNCOATED = 0.72, 0.97
ENDO_STEPS = ((0.0, "Receptors bind their ligands and gather; AP2 adaptors and clathrin assemble on the cytosolic face (a coated pit)"),
              (0.2, "The clathrin lattice curves the membrane: the coated pit invaginates"),
              (0.48, "Dynamin assembles round the neck of the deep pit"),
              (0.66, "Dynamin hydrolyses GTP and pinches the vesicle off"),
              (0.78, "Hsc70 and auxilin strip the clathrin coat: an uncoated vesicle carries the cargo inwards"))


def endocytosis_shape(t: float, r: float = PIT_RADIUS) -> Shape:
    """The membrane and the vesicle ``t`` (0–1) into clathrin-mediated endocytosis."""
    keys = [(when, _flat() if spec is None else pit(*spec)[0], None if spec is None else pit(*spec)[1]) for when, spec in ENDO_KEYS]
    if t < ENDO_SCISSION:
        prev = keys[0]
        for key in keys[1:]:
            if t <= key[0]:
                u = _window(t, prev[0], key[0])
                membrane = _mix(prev[1], key[1], u)
                neck = None
                if prev[2] is not None and key[2] is not None:
                    neck = tuple(a + (b - a) * u for a, b in zip(prev[2], key[2]))
                elif key[2] is not None and u > 0.5:
                    neck = key[2]
                coat = _coat_range(membrane)
                return Shape(membrane, coat=coat, neck=neck)  # type: ignore[arg-type]
            prev = key
        membrane = tuple(keys[0][1]) if t < keys[0][0] else tuple(keys[-1][1])
        return Shape(membrane, coat=_coat_range(membrane))
    # after scission: the membrane relaxes, the vesicle moves in and loses its coat
    relax = _window(t, ENDO_SCISSION, ENDO_SCISSION + 0.1)
    stub, _ = pit(28.0, -22.0, None)
    membrane = _mix(stub, _flat(), relax)
    depth = 88.0 + 110.0 * _window(t, ENDO_SCISSION, 1.0)
    coat = 1.0 - _window(t, 0.8, ENDO_UNCOATED)
    return Shape(membrane, vesicle=(depth, r), coat_on_vesicle=coat)


#: Exocytosis: when the vesicle docks, the pore opens, the vesicle has collapsed.
EXO_DOCK, EXO_PORE, EXO_FLAT = 0.3, 0.45, 0.95
EXO_STEPS = ((0.0, "The vesicle reaches the plasma membrane"),
             (0.22, "v-SNARE (synaptobrevin) and t-SNAREs (syntaxin, SNAP-25) zipper into a trans-SNARE complex: docking"),
             (0.42, "The membranes fuse: a fusion pore opens and the cargo is released outside"),
             (0.7, "The vesicle membrane flattens into the plasma membrane (full collapse)"))


def exocytosis_shape(t: float, r: float, start: float) -> Shape:
    """The membrane and the vesicle (radius ``r`` nm; its centre ``start`` nm inside the
    membrane at first) ``t`` (0–1) into exocytosis."""
    docked = r + 3.0
    if t < EXO_PORE:
        approach = _window(t, 0.0, EXO_DOCK)
        zip_ = _window(t, EXO_DOCK, EXO_PORE)
        depth = start + (docked + 6.0 - start) * approach - 6.0 * zip_
        snares = ()
        if t > EXO_DOCK * 0.75:
            top = -depth + r
            snares = tuple(((x, top + 0.5), (x * 1.6, -2.5)) for x in (-14.0, -5.0, 5.0, 14.0))
        return Shape(tuple(_flat()), vesicle=(depth, r), snares=snares)
    keys = ((EXO_PORE, (r, docked, 2.0)), (0.58, (r, r - 4.0, 12.0)), (0.72, (r, r * 0.45, None)), (0.85, (r * 3.2, -r * 2.75, None)), (EXO_FLAT, None))
    prev_t, prev_spec = keys[0]
    for when, spec in keys[1:]:
        if t <= when:
            u = _window(t, prev_t, when)
            a, _ = pit(*prev_spec)  # type: ignore[misc]
            b = pit(*spec)[0] if spec is not None else _flat()
            return Shape(_mix(a, b, u))
        prev_t, prev_spec = when, spec
    return Shape(tuple(_flat()))


def exocytosis_start(world: CellWorld, entry_id: str) -> tuple[Site, float, float]:
    """The site a vesicle fuses at (the plasma-membrane point nearest it), its radius (nm) and
    how deep its centre lies under the membrane there (nm)."""
    thing = world.members(entry_id)[0]
    site = membrane_site(world, thing.center)
    r = thing.size / 2 * 1000.0
    depth = math.dist(site.point, thing.center) * 1000.0
    return site, r, depth


def cargo_points(count: int, r: float, seed: str) -> list[Point]:
    """``count`` cargo molecules inside a vesicle of radius ``r`` (nm, about its centre)."""
    import random

    rng = random.Random(seed)
    out: list[Point] = []
    while len(out) < count:
        x, y = rng.uniform(-r, r), rng.uniform(-r, r)
        if math.hypot(x, y) < r * 0.72 and all(math.dist((x, y), q) > r * 0.22 for q in out):
            out.append((x, y))
        elif rng.random() < 0.02:
            out.append((x * 0.5, y * 0.5))
    return out


def coat_thickness() -> float:
    """The clathrin coat's thickness (nm)."""
    return COATS["clathrin"] * 1000.0


__all__ = [
    "ENDO_SCISSION", "ENDO_STEPS", "EXO_DOCK", "EXO_PORE", "EXO_STEPS", "MOTOR_ENDS", "MOTOR_SPEEDS", "MOTOR_STEPS", "MotorPose", "MotorTrack",
    "PIT_HALF", "PIT_RADIUS", "Shape", "Site", "cargo_points", "coat_thickness", "endocytosis_problem", "endocytosis_shape",
    "exocytosis_problem", "exocytosis_shape", "exocytosis_start", "membrane_site", "motor_track", "pit", "resample", "walk_distance",
    "walk_pose", "walk_problem",
]
