"""Transport and membrane processes as plans (DESIGN.md §95.10): the rules and the planned moves
of the ``molecule`` scene's actions — a channel passing ions down their electrochemical
gradient, a carrier's alternating access (uniport, symport, antiport), the Post–Albers cycle of
the Na⁺/K⁺ pump, H⁺ pumps, ABC transporters, aquaporins, simple diffusion and osmosis across a
bilayer, an action potential with its voltage trace — as plain data in nanometres, without
manim. A plan is a list of :class:`Phase` s, each with the states the proteins take, the moves
of particles (paths in nm with a seeded random-walk look) and a caption; a renderer plays it.

Numbers: Alberts (Molecular Biology of the Cell, ch. 11), Lodish (Molecular Cell Biology, ch.
11), Hodgkin and Huxley 1952 (the action potential); RT/F = 26.7 mV at 37 °C."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from .geometry import Point
from .glyphs import Glyph, MoleculeSpec, abc_parts, bound_positions, carrier_parts
from .molecules import BILAYER_NM, BILAYER_PERMEANT, IONS, MOLECULES, RT_OVER_F, TYPICAL_CONCENTRATIONS
from .notation import chem_markup, chem_plain, charge_of

#: RT at 37 °C (kJ/mol) and Faraday's constant (kJ/mol per volt).
RT_KJ, FARADAY_KJ = 2.577, 96.485
#: The action potential (mV and ms): rest, threshold, peak, undershoot (Hodgkin–Huxley, a
#: mammalian neuron's numbers rounded).
AP_REST, AP_THRESHOLD, AP_PEAK, AP_UNDERSHOOT, AP_DURATION = -70.0, -55.0, 35.0, -80.0, 6.0
#: The membrane potential through an action potential (ms, mV): stimulus to threshold, the
#: upstroke as Na⁺ channels open, the peak, repolarisation as they inactivate and K⁺ channels
#: open, the undershoot while K⁺ channels stay open, back to rest.
AP_TRACE: tuple[tuple[float, float], ...] = (
    (0.0, -70.0), (0.35, -70.0), (0.8, -55.0), (1.0, -42.0), (1.2, -5.0), (1.45, 28.0), (1.6, 35.0), (1.8, 26.0), (2.2, -10.0),
    (2.6, -52.0), (3.0, -74.0), (3.4, -80.0), (4.2, -77.0), (5.0, -72.5), (6.0, -70.0),
)
#: When each channel changes in an action potential (ms): Na⁺ opens at threshold, inactivates at
#: the peak and recovers (closed) during the undershoot; K⁺ (delayed rectifier) opens near the
#: peak and closes during the undershoot.
AP_EVENTS = {"na_open": 0.8, "na_inactivated": 1.6, "k_open": 1.5, "na_closed": 3.4, "k_closed": 4.6}


@dataclass(frozen=True)
class Particle:
    """A particle a plan moves: ``id``, ``species`` (an ion such as ``Na+``, else a molecule
    kind: ``glucose``, ``atp``, ``water``), where it is first (``start``, nm) and whether it is
    on screen then (``shown``: a particle the scene already has; else it fades in)."""

    id: str
    species: str
    start: Point
    shown: bool = False


@dataclass(frozen=True)
class Move:
    """A particle moving along ``path`` (nm; the first point is where it is) from ``t0`` to
    ``t1`` (shares of its phase); ``appear``: it fades in as it starts; ``vanish``: it fades out
    as it ends (ATP becoming ADP)."""

    particle: str
    path: tuple[Point, ...]
    t0: float = 0.0
    t1: float = 1.0
    appear: bool = False
    vanish: bool = False


@dataclass(frozen=True)
class Phase:
    """A step of a plan: its share of the time (``weight``), the ``states`` proteins morph to
    during it (``(molecule id, state)``), the particles' ``moves`` and a ``note`` (a caption in
    markup)."""

    weight: float
    states: tuple[tuple[str, str], ...] = ()
    moves: tuple[Move, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Plan:
    """A planned process: its ``particles``, ``phases``, the ``states`` the proteins end in, a
    ``voltage`` trace (``(share of the time, mV)``, an action potential), concentration
    ``levels`` at the end (``(solute, side, mM)``), the ``sides`` particles end on and a
    ``summary``."""

    particles: tuple[Particle, ...]
    phases: tuple[Phase, ...]
    states: dict[str, str] = field(default_factory=dict)
    voltage: tuple[tuple[float, float], ...] = ()
    levels: tuple[tuple[str, str, float], ...] = ()
    sides: dict[str, str] = field(default_factory=dict)
    summary: str = ""


# ----- gradients ---------------------------------------------------------------------------------


def nernst(ion: str, outside: float, inside: float) -> float:
    """The Nernst (equilibrium) potential of ``ion`` (mV, inside relative to outside) at 37 °C."""
    z = charge_of(ion) or 1
    if outside <= 0 or inside <= 0:
        return math.copysign(math.inf, z * (outside - inside))
    return RT_OVER_F / z * math.log(outside / inside)


def delta_g(species: str, source: float, dest: float, potential_change: float) -> float:
    """The free energy (kJ/mol) of moving one mole of ``species`` from ``source`` to ``dest``
    concentration (mM) across ``potential_change`` (mV, destination minus source)."""
    z = charge_of(species) if species in IONS else 0
    if source <= 0:
        return math.inf
    if dest <= 0:
        return -math.inf
    return RT_KJ * math.log(dest / source) + z * FARADAY_KJ * potential_change / 1000.0


@dataclass(frozen=True)
class Gradients:
    """What drives transport across one membrane: concentrations (mM) ``(cytosolic side,
    exoplasmic side)`` by species and the membrane potential (mV, cytosolic side relative to the
    other); ``known`` are the species whose concentrations are known."""

    levels: dict[str, tuple[float, float]]
    potential: float

    @classmethod
    def typical(cls, membrane: str | None, levels: dict[str, tuple[float, float]] | None = None, potential: float | None = None) -> Gradients:
        """The plasma membrane's typical gradients (Alberts Table 11-1, −70 mV) with ``levels``
        and ``potential`` written in the scene over them; other membranes only what is written."""
        base = dict(TYPICAL_CONCENTRATIONS) if membrane == "plasma_membrane" else {}
        base.update(levels or {})
        default = -70.0 if membrane == "plasma_membrane" else 0.0
        return cls(base, default if potential is None else potential)

    def known(self, species: str) -> bool:
        return species in self.levels

    def energy(self, species: str, way: str) -> float:
        """ΔG (kJ/mol) of moving ``species`` ``in`` (to the cytosolic side) or ``out``."""
        inside, outside = self.levels[species]
        if way == "in":
            return delta_g(species, outside, inside, self.potential)
        return delta_g(species, inside, outside, -self.potential)

    def passive_way(self, species: str) -> str | None:
        """The way ``species`` moves by itself (down its electrochemical gradient): ``in``,
        ``out`` or ``None`` (at equilibrium, or unknown)."""
        if not self.known(species):
            return None
        e = self.energy(species, "in")
        if abs(e) < 1e-9:
            return None
        return "in" if e < 0 else "out"

    def describe(self, species: str) -> str:
        inside, outside = self.levels[species]
        text = f"{_mm(outside)} outside and {_mm(inside)} in the cytosol"
        if species in IONS and charge_of(species):
            text += f", E = {nernst(species, outside, inside):+.0f} mV at a membrane potential of {self.potential:+.0f} mV"
        return text


def _mm(value: float) -> str:
    if value >= 1:
        return f"{value:g} mM"
    if value >= 0.001:
        return f"{value * 1000:g} µM"
    return f"{value * 1e6:g} nM"


def _name(species: str) -> str:
    return chem_plain(species) if species in IONS else MOLECULES[species].plain if species in MOLECULES else species


def _markup(species: str) -> str:
    return chem_markup(species) if species in IONS else MOLECULES[species].label if species in MOLECULES else species


# ----- rules -------------------------------------------------------------------------------------

#: Why a channel passes only its ion (the selectivity filter).
SELECTIVITY = {
    "K+": "its selectivity filter (TVGYG) holds dehydrated K⁺ in a cage of carbonyl oxygens spaced for K⁺; the smaller Na⁺ cannot "
          "shed its water shell there",
    "Na+": "its selectivity filter (DEKA) passes Na⁺ with part of its water shell; K⁺ is about 1000 times slower through it",
    "Ca2+": "its selectivity filter (EEEE) binds Ca²⁺ tightly; Na⁺ and K⁺ pass only when no Ca²⁺ is there",
    "Cl-": "its pore is lined with positive charges that let anions through, not cations",
    "H+": "it passes protons only (by hopping along water and side chains)",
    "Mg2+": "it passes Mg²⁺ only",
}


def channel_problem(spec: MoleculeSpec, species: str, state: str) -> str | None:
    """Why ``species`` cannot pass this ion channel (in ``state``) now, or ``None``."""
    own = spec.ion or "K+"
    if species != own:
        return (f"{_name(species)} cannot pass a {_name(own)} channel: {SELECTIVITY.get(own, f'its selectivity filter passes {_name(own)} only')}")
    if state == "closed":
        return f"the channel is closed now: open it first (set_state: <id>, state: open); ions pass only an open channel"
    if state == "inactivated":
        return ("the channel is inactivated now (its inactivation gate plugs the pore): it stays shut until the membrane repolarises "
                "and it returns to closed")
    return None


def aquaporin_problem(species: str) -> str | None:
    if species != "water":
        return (f"an aquaporin passes water (in single file), not {_name(species)}: its narrow pore and the NPA motifs' positive "
                f"charge keep out ions, even H⁺")
    return None


def uphill_problem(what: str, energy: float, details: str) -> str:
    return (f"{what} would move up its gradient (ΔG = {energy:+.1f} kJ/mol per cycle; {details}): active transport needs an energy "
            f"source: ATP or an ion gradient going down")


def carrier_problem(spec: MoleculeSpec, gradients: Gradients) -> str | None:
    """Why this carrier cannot run as written with these gradients (a uniporter moving its
    solute up its gradient; a symporter or antiporter whose coupled moves gain no energy), or
    ``None``. Unknown concentrations are not judged."""
    mode, solutes, moves, ratio = carrier_parts(spec)
    if not all(gradients.known(s) for s in solutes):
        return None
    total = sum(r * gradients.energy(s, way) for s, way, r in zip(solutes, moves, ratio))
    parts = "; ".join(f"{_name(s)}: {gradients.describe(s)}" for s in dict.fromkeys(solutes))
    if mode == "uniport" and total > 0:
        return (f"a uniporter only lets {_name(solutes[0])} down its gradient (facilitated diffusion is passive): {parts}, so it moves "
                f"{'out' if moves[0] == 'in' else 'in'}; moving it {moves[0]} needs an energy source: ATP or an ion gradient (a symporter)")
    if total > 0:
        return uphill_problem(f"this {mode}er", total, parts)
    return None


def diffusion_problem(species: str, membrane: str | None) -> str | None:
    """Why ``species`` cannot cross ``membrane`` by simple diffusion, or ``None``."""
    if membrane is None or species in BILAYER_PERMEANT:
        return None
    if species in IONS:
        return (f"{_name(species)} cannot cross the lipid bilayer by simple diffusion: a charged ion is held back by its water shell in "
                f"the hydrophobic core; it needs a channel or a carrier (use transport on an open {_name(species)} channel)")
    return (f"{_name(species)} cannot cross the lipid bilayer by simple diffusion (it is too large and polar): it needs a carrier "
            f"(glucose: a GLUT uniporter, with transport); only small nonpolar molecules (O₂, CO₂) and, slowly, water diffuse through")


# ----- paths ---------------------------------------------------------------------------------------


def wander(rng: random.Random, a: Point, b: Point, steps: int = 10, amplitude: float = 0.8,
           box: tuple[float, float, float, float] | None = None) -> list[Point]:
    """A path from ``a`` to ``b`` with a random-walk look: a Brownian bridge (a seeded random
    walk pinned at both ends) round the straight line, ``amplitude`` nm at its widest, kept in
    ``box``."""
    walk = [(0.0, 0.0)]
    for _ in range(steps):
        x, y = walk[-1]
        walk.append((x + rng.gauss(0.0, 1.0), y + rng.gauss(0.0, 1.0)))
    end = walk[-1]
    scale = amplitude / max(1.0, math.sqrt(steps) / 2)
    out = []
    for k, (x, y) in enumerate(walk):
        t = k / steps
        px = a[0] + (b[0] - a[0]) * t + (x - t * end[0]) * scale
        py = a[1] + (b[1] - a[1]) * t + (y - t * end[1]) * scale
        if box is not None:
            px = min(max(px, box[0]), box[2])
            py = min(max(py, box[1]), box[3])
        out.append((px, py))
    out[0], out[-1] = a, b
    return out


def jiggle(rng: random.Random, p: Point, steps: int = 10, amplitude: float = 0.6, box: tuple[float, float, float, float] | None = None,
           drift: Point = (0.0, 0.0)) -> list[Point]:
    """A particle's random walk about where it is (it ends a little way off, ``drift`` added)."""
    end = (p[0] + rng.gauss(0.0, amplitude * 0.6) + drift[0], p[1] + rng.gauss(0.0, amplitude * 0.6) + drift[1])
    if box is not None:
        end = (min(max(end[0], box[0]), box[2]), min(max(end[1], box[1]), box[3]))
    return wander(rng, p, end, steps, amplitude, box)


def scatter(rng: random.Random, box: tuple[float, float, float, float], count: int, gap: float,
            avoid: Sequence[tuple[float, float, float, float]] = (), taken: Sequence[Point] = ()) -> list[Point]:
    """``count`` points in ``box`` at least ``gap`` apart (fewer when they do not fit), off the
    ``avoid`` boxes and the ``taken`` points."""
    out: list[Point] = []
    others = list(taken)
    for _ in range(count):
        for _try in range(200):
            p = (rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3]))
            if any(a[0] <= p[0] <= a[2] and a[1] <= p[1] <= a[3] for a in avoid):
                continue
            if all(math.dist(p, q) >= gap for q in others):
                out.append(p)
                others.append(p)
                break
    return out


# ----- the scene a plan is made in -----------------------------------------------------------------


@dataclass
class Pool:
    """The particles a scene has, by species and side (``p``: exoplasmic, ``n``: cytosolic;
    ``left`` / ``right`` without a membrane): ``(id, point)``. A plan takes the ones nearest to
    where it needs them and makes new ones (fading in) when there are too few."""

    by_side: dict[tuple[str, str], list[tuple[str, Point]]] = field(default_factory=dict)
    boxes: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    made: int = 0

    def take(self, species: str, side: str, near: Point, count: int, rng: random.Random, prefix: str,
             spread: tuple[float, float] = (4.0, 7.0)) -> list[Particle]:
        """``count`` particles of ``species`` on ``side`` nearest ``near`` (taken off the pool), new
        ones round ``near`` for the rest."""
        found = sorted(self.by_side.get((species, side), []), key=lambda item: math.dist(item[1], near))[:count]
        for item in found:
            self.by_side[(species, side)].remove(item)
        out = [Particle(pid, species, p, shown=True) for pid, p in found]
        sign = 1.0 if side == "p" else -1.0
        box = self.boxes.get(side)
        while len(out) < count:
            self.made += 1
            angle = rng.uniform(0.25, 0.75) * math.pi
            r = rng.uniform(*spread)
            p = (near[0] + r * math.cos(angle) * 1.6 * rng.choice((-1, 1)), near[1] + sign * r * math.sin(angle))
            if box is not None:
                p = (min(max(p[0], box[0]), box[2]), min(max(p[1], box[1]), box[3]))
            out.append(Particle(f"{prefix}{self.made}", species, p))
        return out

    def give(self, species: str, side: str, pid: str, point: Point) -> None:
        """A particle that ends on ``side`` at ``point`` joins the pool there."""
        self.by_side.setdefault((species, side), []).append((pid, point))


def _away(rng: random.Random, mouth: Point, side: str, box: tuple[float, float, float, float] | None, reach: tuple[float, float] = (3.5, 6.5)) -> Point:
    """Where a released particle drifts to: off the mouth into its side's bulk."""
    sign = 1.0 if side == "p" else -1.0
    angle = rng.uniform(0.2, 0.8) * math.pi
    r = rng.uniform(*reach)
    p = (mouth[0] + 1.5 * r * math.cos(angle), mouth[1] + sign * r * math.sin(angle))
    if box is not None:
        p = (min(max(p[0], box[0]), box[2]), min(max(p[1], box[1]), box[3]))
    return p


def _side_of(way: str, end: str) -> str:
    """The side a solute moving ``way`` (in / out) starts (``end`` = from) or ends on."""
    into_cytosol = way == "in"
    if end == "from":
        return "p" if into_cytosol else "n"
    return "n" if into_cytosol else "p"


def _at(origin: Point, p: object) -> Point:
    x, y = p  # type: ignore[misc]
    return (origin[0] + float(x), origin[1] + float(y))


@dataclass
class _Builder:
    """Collects the particles and phases of a plan."""

    rng: random.Random
    pool: Pool
    prefix: str
    particles: dict[str, Particle] = field(default_factory=dict)
    where: dict[str, Point] = field(default_factory=dict)
    sides: dict[str, str] = field(default_factory=dict)
    phases: list[Phase] = field(default_factory=list)

    def take(self, species: str, side: str, near: Point, count: int) -> list[str]:
        got = self.pool.take(species, side, near, count, self.rng, self.prefix)
        for p in got:
            self.particles[p.id] = p
            self.where[p.id] = p.start
            self.sides[p.id] = side
        return [p.id for p in got]

    def new(self, species: str, at: Point, side: str) -> str:
        self.pool.made += 1
        pid = f"{self.prefix}{self.pool.made}"
        self.particles[pid] = Particle(pid, species, at)
        self.where[pid] = at
        self.sides[pid] = side
        return pid

    def to(self, pid: str, *points: Point, t0: float = 0.0, t1: float = 1.0, wiggle: float = 0.0, vanish: bool = False) -> Move:
        """A move of ``pid`` from where it is through ``points`` (a random-walk look on the first
        leg with ``wiggle``)."""
        start = self.where[pid]
        path: list[Point] = [start]
        if wiggle > 0 and points:
            path = wander(self.rng, start, points[0], 8, wiggle)
            path += list(points[1:])
        else:
            path += list(points)
        self.where[pid] = path[-1]
        appear = not self.particles[pid].shown and not any(pid in [m.particle for m in ph.moves] for ph in self.phases)
        return Move(pid, tuple(path), t0, t1, appear=appear, vanish=vanish)

    def phase(self, weight: float, note: str, moves: Sequence[Move] = (), states: Sequence[tuple[str, str]] = ()) -> None:
        self.phases.append(Phase(weight, tuple(states), tuple(moves), note))

    def plan(self, states: dict[str, str], summary: str, released: Sequence[str] = (), voltage: tuple[tuple[float, float], ...] = ()) -> Plan:
        for pid in released:
            self.pool.give(self.particles[pid].species, self.sides[pid], pid, self.where[pid])
        return Plan(tuple(self.particles.values()), tuple(self.phases), states, voltage, (), dict(self.sides), summary)


# ----- channels, aquaporins ------------------------------------------------------------------------


def plan_channel(molecule: str, glyph: Glyph, origin: Point, species: str, way: str, count: int, b: _Builder) -> Plan:
    """Ions through an open channel, one after another, down their gradient (``way``)."""
    path = [_at(origin, q) for q in glyph.facts["path"]]  # type: ignore[union-attr]
    if way == "in":
        source, dest, through = "p", "n", path
    else:
        source, dest, through = "n", "p", path[::-1]
    ions = b.take(species, source, through[0], count)
    moves = []
    for k, pid in enumerate(ions):
        t0 = 0.75 * k / max(1, count)
        exit_ = _away(b.rng, through[-1], dest, b.pool.boxes.get(dest))
        b.sides[pid] = dest
        start = b.where[pid]
        approach = wander(b.rng, start, through[0], 7, 0.7)
        leave = wander(b.rng, through[-1], exit_, 7, 0.7)
        b.where[pid] = exit_
        appear = not b.particles[pid].shown
        moves.append(Move(pid, tuple(approach + through[1:-1] + leave), t0, min(1.0, t0 + 0.42), appear=appear))
    b.phase(1.0, f"{count} {_markup(species)} flow{'s' if count == 1 else ''} {'into the cell' if way == 'in' else 'out of the cell'} "
                 f"through the open channel, down {'its' if count == 1 else 'their'} electrochemical gradient", moves)
    return b.plan({}, f"{count} {_name(species)} {way}", released=ions)


def plan_aquaporin(molecule: str, glyph: Glyph, origin: Point, way: str, count: int, b: _Builder) -> Plan:
    """Water molecules in single file through an aquaporin."""
    path = [_at(origin, q) for q in glyph.facts["path"]]  # type: ignore[union-attr]
    source, dest = ("p", "n") if way == "in" else ("n", "p")
    through = path if way == "in" else path[::-1]
    waters = b.take("water", source, through[0], count)
    moves = []
    for k, pid in enumerate(waters):
        t0 = 0.7 * k / max(1, count)
        exit_ = _away(b.rng, through[-1], dest, b.pool.boxes.get(dest), (2.5, 5.0))
        b.sides[pid] = dest
        approach = wander(b.rng, b.where[pid], through[0], 6, 0.5)
        leave = wander(b.rng, through[-1], exit_, 6, 0.5)
        b.where[pid] = exit_
        moves.append(Move(pid, tuple(approach + through[1:-1] + leave), t0, min(1.0, t0 + 0.35), appear=not b.particles[pid].shown))
    b.phase(1.0, f"Water passes the aquaporin in single file ({'into the cell' if way == 'in' else 'out of the cell'})", moves)
    return b.plan({}, f"{count} water {way}", released=waters)


# ----- carriers ------------------------------------------------------------------------------------


def _facing(way_from: str) -> str:
    """The state that opens a carrier to the side a solute comes from."""
    return "outward" if way_from == "p" else "inward"


def plan_carrier(molecule: str, spec: MoleculeSpec, glyph: Glyph, origin: Point, state: str, cycles: int, b: _Builder) -> Plan:
    """A carrier's alternating access, cycle by cycle: open to the side its solutes come from,
    bind them (the driving ion first), occlude, open to the other side, release; a uniporter or
    symporter returns empty, an antiporter (exchanger) carries its other solute back."""
    mode, solutes, moves, ratio = carrier_parts(spec)
    sites = {k: _at(origin, v) for k, v in glyph.facts["sites"].items()}  # type: ignore[union-attr]
    mouths = {"p": _at(origin, glyph.facts["mouth_out"]), "n": _at(origin, glyph.facts["mouth_in"])}
    released: list[str] = []
    current = state
    if mode == "antiport":
        # the exchanger: one solute through, then the other back (ping-pong)
        order = [0, 1] if _facing(_side_of(moves[0], "from")) == current or current == "occluded" else [1, 0]
        batches = [[order[0]], [order[1]]]
    else:
        batches = [list(range(len(solutes)))]
    for _cycle in range(cycles):
        for batch in batches:
            way = moves[batch[0]]
            src, dst = _side_of(way, "from"), _side_of(way, "to")
            open_src = _facing(src)
            if current != open_src:
                b.phase(0.5, f"The carrier opens to the {'outside' if src == 'p' else 'cytosol'}", states=[(molecule, open_src)])
                current = open_src
            loaded: list[str] = []
            positions = bound_positions(sites[open_src], sum(ratio[k] for k in batch))
            slot = 0
            for k in batch:     # the driving ion binds first (it is listed first)
                pids = b.take(solutes[k], src, mouths[src], ratio[k])
                bind = []
                for pid in pids:
                    bind.append(b.to(pid, mouths[src], positions[slot], wiggle=0.8))
                    slot += 1
                count = f"{ratio[k]} " if ratio[k] > 1 else ""
                b.phase(0.9, f"{count}{_markup(solutes[k])} bind{'s' if ratio[k] == 1 else ''} from the {'outside' if src == 'p' else 'cytosol'}", bind)
                loaded += pids
            occluded = bound_positions(sites["occluded"], len(loaded))
            b.phase(0.6, "Occluded: the binding site is closed to both sides", [b.to(pid, q) for pid, q in zip(loaded, occluded)],
                    [(molecule, "occluded")])
            open_dst = _facing(dst)
            dest_sites = bound_positions(sites[open_dst], len(loaded))
            b.phase(0.6, f"It opens to the {'outside' if dst == 'p' else 'cytosol'} (alternating access)",
                    [b.to(pid, q) for pid, q in zip(loaded, dest_sites)], [(molecule, open_dst)])
            current = open_dst
            leave = []
            for pid in loaded:
                b.sides[pid] = dst
                leave.append(b.to(pid, mouths[dst], _away(b.rng, mouths[dst], dst, b.pool.boxes.get(dst)), wiggle=0.0))
            names = " and ".join(f"{ratio[k]} {_markup(solutes[k])}" if ratio[k] > 1 else _markup(solutes[k]) for k in batch)
            b.phase(0.9, f"{names} {'are' if len(loaded) > 1 else 'is'} released {'into the cytosol' if dst == 'n' else 'outside'}", leave)
            released += loaded
        if mode != "antiport":
            back = _facing(_side_of(moves[0], "from"))
            b.phase(0.6, "The empty carrier turns back", states=[(molecule, back)])
            current = back
    total = ", ".join(f"{r * cycles} {_name(s)} {w}" for s, w, r in zip(solutes, moves, ratio))
    return b.plan({molecule: current}, total, released=released)


# ----- pumps ---------------------------------------------------------------------------------------


def _bulk(b: _Builder, origin: Point, glyph: Glyph, side: str) -> Point:
    """A point in ``side``'s bulk beside a protein (beyond its drawing)."""
    x0, y0, x1, y1 = glyph.bounds
    y = (y1 + 2.5) if side == "p" else (y0 - 1.5)
    return (origin[0] + b.rng.uniform(x0 - 1.0, x1 + 1.0), origin[1] + y)


def plan_na_k_pump(molecule: str, glyph: Glyph, origin: Point, state: str, cycles: int, b: _Builder) -> Plan:
    """The Post–Albers cycle of the Na⁺/K⁺ pump: E1 binds 3 Na⁺ from the cytosol and ATP; ATP
    phosphorylates the P domain's Asp (E1P, Na⁺ occluded; ADP leaves); E2P opens outside and
    releases 3 Na⁺; 2 K⁺ bind from outside; the phosphate leaves as Pᵢ (E2, K⁺ occluded); ATP
    binds and E1 opens to the cytosol, releasing 2 K⁺ inside."""
    f = glyph.facts
    sites = {k: _at(origin, v) for k, v in f["sites"].items()}  # type: ignore[union-attr]
    n_dom = f["n_domains"]
    atp_at = {k: _at(origin, (v[0] + 0.2, v[1] - 1.75)) for k, v in n_dom.items()}  # type: ignore[union-attr]
    mouths = {"p": _at(origin, f["mouth_out"]), "n": _at(origin, f["mouth_in"])}
    asp = _at(origin, f["asp"])
    released: list[str] = []
    if state != "e1":
        b.phase(0.5, "E1: the pump opens to the cytosol", states=[(molecule, "e1")])
    for _ in range(cycles):
        na = b.take("Na+", "n", mouths["n"], 3)
        atp = b.take("atp", "n", atp_at["e1"], 1)[0]
        bind = [b.to(pid, mouths["n"], q, wiggle=0.8, t0=0.12 * k, t1=0.7 + 0.1 * k) for k, (pid, q) in enumerate(zip(na, bound_positions(sites["inward"], 3, 0.75)))]
        bind.append(b.to(atp, atp_at["e1"], wiggle=1.0, t0=0.3))
        b.phase(1.2, "E1: 3 Na<sup>+</sup> bind from the cytosol, ATP binds the N domain", bind)
        adp = b.new("adp", atp_at["e1p"], "n")
        hold = [b.to(pid, q) for pid, q in zip(na, bound_positions(sites["occluded"], 3, 0.75))]
        hold.append(b.to(atp, atp_at["e1p"], t1=0.45, vanish=True))
        b.phase(1.0, "ATP → ADP: the pump phosphorylates its own Asp (E1P); 3 Na<sup>+</sup> are occluded",
                hold + [Move(adp, (atp_at["e1p"], atp_at["e1p"]), 0.4, 0.55, appear=True)], [(molecule, "e1p")])
        b.phase(0.6, "ADP leaves", [b.to(adp, _bulk(b, origin, glyph, "n"), wiggle=1.0)])
        out = bound_positions(sites["outward"], 3, 0.75)
        b.phase(0.8, "E2P: the pump opens to the outside", [b.to(pid, q) for pid, q in zip(na, out)], [(molecule, "e2p")])
        leave = []
        for k, pid in enumerate(na):
            b.sides[pid] = "p"
            leave.append(b.to(pid, mouths["p"], _away(b.rng, mouths["p"], "p", b.pool.boxes.get("p")), t0=0.1 * k))
        b.phase(0.9, "3 Na<sup>+</sup> are released outside", leave)
        k_ions = b.take("K+", "p", mouths["p"], 2)
        bind_k = [b.to(pid, mouths["p"], q, wiggle=0.8, t0=0.15 * k) for k, (pid, q) in enumerate(zip(k_ions, bound_positions(sites["outward"], 2, 0.75)))]
        b.phase(0.9, "2 K<sup>+</sup> bind from the outside", bind_k)
        pi = b.new("pi", asp, "n")
        hold_k = [b.to(pid, q) for pid, q in zip(k_ions, bound_positions(sites["occluded"], 2, 0.75))]
        b.phase(0.9, "The phosphate leaves as P<sub>i</sub> (E2): 2 K<sup>+</sup> are occluded",
                hold_k + [b.to(pi, (asp[0] + 0.6, asp[1] - 1.2), _bulk(b, origin, glyph, "n"), t0=0.3, wiggle=0.0)], [(molecule, "e2")])
        atp2 = b.take("atp", "n", atp_at["e2"], 1)[0]
        b.phase(0.6, "ATP binds", [b.to(atp2, atp_at["e2"], wiggle=1.0)])
        back = [b.to(pid, q) for pid, q in zip(k_ions, bound_positions(sites["inward"], 2, 0.75))]
        back.append(b.to(atp2, atp_at["e1"]))
        b.phase(0.8, "E1: the pump opens to the cytosol again", back, [(molecule, "e1")])
        leave_k = []
        for k, pid in enumerate(k_ions):
            b.sides[pid] = "n"
            leave_k.append(b.to(pid, mouths["n"], _away(b.rng, mouths["n"], "n", b.pool.boxes.get("n")), t0=0.1 * k))
        b.phase(0.9, "2 K<sup>+</sup> are released into the cytosol: 3 Na<sup>+</sup> out, 2 K<sup>+</sup> in per ATP", leave_k)
        released += na + k_ions + [adp, pi]
        # the ATP bound for the next turn starts it
        b.pool.give("atp", "n", atp2, b.where[atp2])
    return b.plan({molecule: "e1"}, f"{3 * cycles} Na+ out, {2 * cycles} K+ in, {cycles} ATP", released=released)


def plan_p_type_h(molecule: str, glyph: Glyph, origin: Point, state: str, cycles: int, b: _Builder) -> Plan:
    """A P-type H⁺ pump: E1 binds H⁺ and ATP, phosphorylates itself (E1P), opens outside (E2P),
    releases H⁺, loses the phosphate (E2) and returns to E1."""
    f = glyph.facts
    sites = {k: _at(origin, v) for k, v in f["sites"].items()}  # type: ignore[union-attr]
    atp_at = {k: _at(origin, (v[0] + 0.2, v[1] - 1.75)) for k, v in f["n_domains"].items()}  # type: ignore[union-attr]
    mouths = {"p": _at(origin, f["mouth_out"]), "n": _at(origin, f["mouth_in"])}
    asp = _at(origin, f["asp"])
    released: list[str] = []
    if state != "e1":
        b.phase(0.5, "E1: the pump opens to the cytosol", states=[(molecule, "e1")])
    for _ in range(cycles):
        h = b.take("H+", "n", mouths["n"], 1)[0]
        atp = b.take("atp", "n", atp_at["e1"], 1)[0]
        b.phase(1.0, "E1: H<sup>+</sup> binds from the cytosol, ATP binds the N domain",
                [b.to(h, mouths["n"], sites["inward"], wiggle=0.8), b.to(atp, atp_at["e1"], wiggle=1.0, t0=0.2)])
        adp = b.new("adp", atp_at["e1p"], "n")
        b.phase(0.9, "ATP → ADP: the pump phosphorylates itself (E1P)",
                [b.to(h, sites["occluded"]), b.to(atp, atp_at["e1p"], t1=0.45, vanish=True), Move(adp, (atp_at["e1p"], atp_at["e1p"]), 0.4, 0.55, appear=True)],
                [(molecule, "e1p")])
        b.sides[h] = "p"
        b.phase(1.0, "E2P opens outside: H<sup>+</sup> is released",
                [b.to(adp, _bulk(b, origin, glyph, "n"), wiggle=1.0), b.to(h, sites["outward"], mouths["p"], _away(b.rng, mouths["p"], "p", b.pool.boxes.get("p")))],
                [(molecule, "e2p")])
        pi = b.new("pi", asp, "n")
        b.phase(0.8, "The phosphate leaves as P<sub>i</sub> (E2)", [b.to(pi, (asp[0] + 0.6, asp[1] - 1.2), _bulk(b, origin, glyph, "n"))], [(molecule, "e2")])
        b.phase(0.5, "E1: open to the cytosol again", states=[(molecule, "e1")])
        released += [h, adp, pi]
    return b.plan({molecule: "e1"}, f"{cycles} H+ out, {cycles} ATP", released=released)


def plan_v_type(molecule: str, glyph: Glyph, origin: Point, cycles: int, b: _Builder) -> Plan:
    """The rotary V-ATPase: ATP hydrolysed in V₁ turns the rotor; H⁺ cross Vₒ from the cytosol
    into the lumen (about 2 per ATP here)."""
    f = glyph.facts
    path = [_at(origin, q) for q in f["path"]]  # type: ignore[union-attr]
    site = _at(origin, f["atp_site"])
    released: list[str] = []
    for _ in range(cycles):
        atp = b.take("atp", "n", site, 1)[0]
        pi_at = (site[0] + 0.8, site[1])
        adp = b.new("adp", site, "n")
        pi = b.new("pi", pi_at, "n")
        b.phase(0.9, "ATP binds V<sub>1</sub> and is hydrolysed", [b.to(atp, site, wiggle=1.0, t1=0.75, vanish=True),
                                                             Move(adp, (site, site), 0.7, 0.8, appear=True), Move(pi, (pi_at, pi_at), 0.7, 0.8, appear=True)])
        hs = b.take("H+", "n", path[0], 2)
        moves = []
        for k, h in enumerate(hs):
            b.sides[h] = "p"
            moves.append(b.to(h, *path, _away(b.rng, path[-1], "p", b.pool.boxes.get("p")), t0=0.3 * k, t1=0.6 + 0.3 * k, wiggle=0.8))
        moves += [b.to(adp, _bulk(b, origin, glyph, "n"), wiggle=1.0), b.to(pi, _bulk(b, origin, glyph, "n"), wiggle=1.0)]
        b.phase(1.2, "The rotor turns: 2 H<sup>+</sup> cross V<sub>o</sub> into the lumen; ADP and P<sub>i</sub> leave", moves)
        released += hs + [adp, pi]
    return b.plan({}, f"{2 * cycles} H+ into the lumen, {cycles} ATP", released=released)


def plan_abc(molecule: str, spec: MoleculeSpec, glyph: Glyph, origin: Point, state: str, cycles: int, b: _Builder) -> Plan:
    """An ABC transporter: export — the substrate binds the inward-facing pump from the
    cytosol, 2 ATP bind and close the NBDs (outward-facing), the substrate leaves outside,
    hydrolysis (2 ADP + 2 Pᵢ leave) resets it; a bacterial importer the other way round."""
    substrate, way = abc_parts(spec)
    f = glyph.facts
    sites = {k: _at(origin, v) for k, v in f["sites"].items()}  # type: ignore[union-attr]
    mouths = {"p": _at(origin, f["mouth_out"]), "n": _at(origin, f["mouth_in"])}
    atp_sites = [_at(origin, q) for q in f["atp_sites"]]  # type: ignore[union-attr]
    released: list[str] = []
    for _ in range(cycles):
        if way == "out":
            if state != "inward":
                b.phase(0.5, "Inward-facing", states=[(molecule, "inward")])
            s = b.take(substrate, "n", mouths["n"], 1)[0]
            b.phase(1.0, f"{_markup(substrate)} binds from the cytosol (inward-facing)", [b.to(s, mouths["n"], sites["inward"], wiggle=0.9)])
            atps = b.take("atp", "n", mouths["n"], 2)
            b.phase(1.0, "2 ATP bind the nucleotide-binding domains", [b.to(a, q, wiggle=1.0, t0=0.15 * k) for k, (a, q) in enumerate(zip(atps, atp_sites))])
            b.phase(0.8, "The NBDs close on the ATP: the pump turns outward-facing", [b.to(s, sites["outward"])], [(molecule, "outward")])
            b.sides[s] = "p"
            b.phase(0.8, f"{_markup(substrate)} is released outside", [b.to(s, mouths["p"], _away(b.rng, mouths["p"], "p", b.pool.boxes.get("p")))])
            prods = []
            for k, a in enumerate(atps):
                adp = b.new("adp", atp_sites[k], "n")
                pi = b.new("pi", (atp_sites[k][0] + 0.7, atp_sites[k][1]), "n")
                prods += [b.to(a, atp_sites[k], t1=0.3, vanish=True), Move(adp, (atp_sites[k], atp_sites[k]), 0.25, 0.35, appear=True),
                          Move(pi, (b.where[pi], b.where[pi]), 0.25, 0.35, appear=True)]
                released += [adp, pi]
            b.phase(0.9, "2 ATP → 2 ADP + 2 P<sub>i</sub>: the pump resets (inward-facing)", prods, [(molecule, "inward")])
            b.phase(0.7, "ADP and P<sub>i</sub> leave", [b.to(pid, _bulk(b, origin, glyph, "n"), wiggle=1.0) for pid in released[-4:]])
            released.append(s)
            state = "inward"
        else:
            atps = b.take("atp", "n", mouths["n"], 2)
            b.phase(1.0, "2 ATP bind and close the NBDs: outward-facing", [b.to(a, q, wiggle=1.0) for a, q in zip(atps, atp_sites)],
                    [(molecule, "outward")])
            s = b.take(substrate, "p", mouths["p"], 1)[0]
            b.phase(1.0, f"{_markup(substrate)} binds from the outside", [b.to(s, mouths["p"], sites["outward"], wiggle=0.9)])
            prods = []
            for k, a in enumerate(atps):
                adp = b.new("adp", atp_sites[k], "n")
                pi = b.new("pi", (atp_sites[k][0] + 0.7, atp_sites[k][1]), "n")
                prods += [b.to(a, atp_sites[k], t1=0.3, vanish=True), Move(adp, (atp_sites[k], atp_sites[k]), 0.25, 0.35, appear=True),
                          Move(pi, (b.where[pi], b.where[pi]), 0.25, 0.35, appear=True)]
                released += [adp, pi]
            b.phase(0.9, "2 ATP → 2 ADP + 2 P<sub>i</sub>: the pump turns inward-facing", prods + [b.to(s, sites["inward"])], [(molecule, "inward")])
            b.sides[s] = "n"
            b.phase(0.9, f"{_markup(substrate)} is released into the cytosol",
                    [b.to(s, mouths["n"], _away(b.rng, mouths["n"], "n", b.pool.boxes.get("n")))] +
                    [b.to(pid, _bulk(b, origin, glyph, "n"), wiggle=1.0) for pid in released[-4:]])
            released.append(s)
            state = "inward"
    return b.plan({molecule: state}, f"{cycles} {_name(substrate)} {way}, {2 * cycles} ATP", released=released)


# ----- diffusion and osmosis -------------------------------------------------------------------------


@dataclass(frozen=True)
class Crossing:
    """Where particles may cross: ``spots`` (x of open pores, nm) or anywhere (``spots`` empty),
    the membrane's ``y`` (nm) and half thickness ``half``; ``None`` membrane: a line x = 0
    between the left and right halves."""

    spots: tuple[float, ...]
    y: float = 0.0
    half: float = BILAYER_NM / 2
    membrane: bool = True


def plan_diffusion(species: str, field_: dict[str, list[tuple[str, Point]]], boxes: dict[str, tuple[float, float, float, float]],
                   crossing: Crossing, share: float, rng: random.Random, note: str) -> Plan:
    """Simple diffusion: every particle of ``species`` random-walks; ``share`` of the way to
    equal numbers on the two sides, particles cross from the crowded side (and, to show it is
    random, a few the other way: the net flux is down the gradient)."""
    sides = list(boxes)
    counts = {s: len(field_.get(s, [])) for s in sides}
    high, low = max(sides, key=lambda s: counts[s]), min(sides, key=lambda s: counts[s])
    net = round((counts[high] - counts[low]) / 2 * share)
    back = min(counts[low], net // 3) if net >= 3 else 0
    moves: list[Move] = []
    particles: list[Particle] = []
    ends: dict[str, str] = {}
    crossers = {pid for pid, _ in _nearest(field_.get(high, []), crossing, high, net + back)}
    returners = {pid for pid, _ in _nearest(field_.get(low, []), crossing, low, back)}
    for side in sides:
        for pid, p in field_.get(side, []):
            particles.append(Particle(pid, species, p, shown=True))
            if pid in crossers or pid in returners:
                other = low if pid in crossers else high
                spot = _spot(crossing, p, rng)
                a, z = _through(crossing, spot, side)
                end = (rng.uniform(boxes[other][0], boxes[other][2]), rng.uniform(boxes[other][1], boxes[other][3]))
                t0 = rng.uniform(0.0, 0.45)
                path = wander(rng, p, a, 7, 1.2, boxes[side]) + wander(rng, z, end, 7, 1.2, boxes[other])
                moves.append(Move(pid, tuple(path), t0, min(1.0, t0 + rng.uniform(0.45, 0.55))))
                ends[pid] = other
            else:
                moves.append(Move(pid, tuple(jiggle(rng, p, 10, 1.0, boxes[side])), 0.0, 1.0))
                ends[pid] = side
    summary = f"{net} {_name(species)} net from {high} to {low}"
    return Plan(tuple(particles), (Phase(1.0, (), tuple(moves), note),), {}, (), (), ends, summary)


def _nearest(items: list[tuple[str, Point]], crossing: Crossing, side: str, count: int) -> list[tuple[str, Point]]:
    """The ``count`` particles nearest where they can cross."""
    if count <= 0:
        return []

    def reach(item: tuple[str, Point]) -> float:
        p = item[1]
        if not crossing.membrane:
            return abs(p[0])
        dy = abs(p[1] - crossing.y)
        if crossing.spots:
            return min(math.hypot(p[0] - x, dy) for x in crossing.spots)
        return dy
    return sorted(items, key=reach)[:count]


def _spot(crossing: Crossing, p: Point, rng: random.Random) -> float:
    """Where along the boundary a particle at ``p`` crosses (x on a membrane, y on the line
    between two halves)."""
    if not crossing.membrane:
        return p[1] + rng.uniform(-1.5, 1.5)
    if crossing.spots:
        return min(crossing.spots, key=lambda x: abs(x - p[0]))
    return p[0] + rng.uniform(-1.5, 1.5)


def _through(crossing: Crossing, x: float, side: str) -> tuple[Point, Point]:
    """The two mouths of a crossing at ``x`` from ``side``."""
    if not crossing.membrane:
        sign = -1.0 if side == "left" else 1.0
        return (sign * 0.6, x), (-sign * 0.6, x)
    reach = crossing.half + 1.2
    sign = 1.0 if side == "p" else -1.0
    return (x, crossing.y + sign * reach), (x, crossing.y - sign * reach)


def osmolarity(levels: dict[str, float]) -> float:
    """The osmolarity (mOsm/L) of solutes (mM, each particle counted once)."""
    return sum(v for k, v in levels.items() if k != "water" and k not in BILAYER_PERMEANT)


def osmosis_way(cytosol: dict[str, float], outside: dict[str, float]) -> str | None:
    """The way water moves: ``in`` (to the cytosolic side, the more concentrated) or ``out``;
    ``None`` when both sides have the same osmolarity (isotonic)."""
    a, b = osmolarity(cytosol), osmolarity(outside)
    if abs(a - b) < 1e-9:
        return None
    return "in" if a > b else "out"


def osmosis_problem(cytosol: dict[str, float], outside: dict[str, float]) -> str | None:
    if osmosis_way(cytosol, outside) is None:
        return (f"no net water flow: both sides have the same osmolarity ({osmolarity(cytosol):g} mOsm/L, isotonic); give the solutes "
                f"different concentrations on the two sides")
    return None


# ----- the action potential ------------------------------------------------------------------------


def ap_voltage(t_ms: float) -> float:
    """The membrane potential (mV) ``t_ms`` into an action potential (a monotone cubic through
    :data:`AP_TRACE`)."""
    pts = AP_TRACE
    if t_ms <= pts[0][0]:
        return pts[0][1]
    if t_ms >= pts[-1][0]:
        return pts[-1][1]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(pts)
    d = [(ys[k + 1] - ys[k]) / (xs[k + 1] - xs[k]) for k in range(n - 1)]
    m = [d[0]] + [0.0 if d[k - 1] * d[k] <= 0 else (d[k - 1] + d[k]) / 2 for k in range(1, n - 1)] + [d[-1]]
    for k in range(n - 1):     # Fritsch–Carlson: keep it monotone between the points
        if d[k] == 0:
            m[k] = m[k + 1] = 0.0
            continue
        a, b = m[k] / d[k], m[k + 1] / d[k]
        s = a * a + b * b
        if s > 9:
            tau = 3 / math.sqrt(s)
            m[k], m[k + 1] = tau * a * d[k], tau * b * d[k]
    k = max(i for i in range(n - 1) if xs[i] <= t_ms)
    h = xs[k + 1] - xs[k]
    t = (t_ms - xs[k]) / h
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    return h00 * ys[k] + h10 * h * m[k] + h01 * ys[k + 1] + h11 * h * m[k + 1]


def ap_trace(samples: int = 121) -> tuple[tuple[float, float], ...]:
    """The action potential sampled: ``(ms, mV)``."""
    return tuple((AP_DURATION * k / (samples - 1), ap_voltage(AP_DURATION * k / (samples - 1))) for k in range(samples))


def plan_action_potential(na: Sequence[tuple[str, Glyph, Point]], k: Sequence[tuple[str, Glyph, Point]], b: _Builder, ions: int = 3) -> Plan:
    """An action potential at a patch of membrane: a stimulus depolarises it to threshold
    (−55 mV); voltage-gated Na⁺ channels open and Na⁺ rushes in (to +35 mV); they inactivate as
    the K⁺ channels open and K⁺ flows out (repolarisation); the K⁺ channels stay open into the
    undershoot (−80 mV) while the Na⁺ channels recover (closed); they close and the membrane
    returns to rest (−70 mV). The phases last as long as their part of the trace (ms)."""
    e = AP_EVENTS

    def state_moves(group: Sequence[tuple[str, Glyph, Point]], species: str, way: str, count: int, t_span: tuple[float, float]) -> list[Move]:
        moves = []
        for mol, glyph, origin in group:
            path = [_at(origin, q) for q in glyph.facts["path"]]  # type: ignore[union-attr]
            through = path if way == "in" else path[::-1]
            src, dst = ("p", "n") if way == "in" else ("n", "p")
            pids = b.take(species, src, through[0], count)
            for j, pid in enumerate(pids):
                t0 = t_span[0] + (t_span[1] - t_span[0]) * j / max(1, count)
                end = _away(b.rng, through[-1], dst, b.pool.boxes.get(dst))
                b.sides[pid] = dst
                path_ = wander(b.rng, b.where[pid], through[0], 6, 0.6) + through[1:-1] + wander(b.rng, through[-1], end, 6, 0.6)
                b.where[pid] = end
                moves.append(Move(pid, tuple(path_), t0, min(1.0, t0 + 0.5), appear=not b.particles[pid].shown))
        return moves

    na_ids = [m for m, _, _ in na]
    k_ids = [m for m, _, _ in k]
    b.phase(e["na_open"], "A stimulus depolarises the membrane to threshold (−55 mV)")
    b.phase(e["na_inactivated"] - e["na_open"], "Voltage-gated Na<sup>+</sup> channels open: Na<sup>+</sup> rushes in (depolarisation)",
            state_moves(na, "Na+", "in", ions, (0.0, 0.5)), [(m, "open") for m in na_ids])
    b.phase(e["na_closed"] - e["na_inactivated"], "Na<sup>+</sup> channels inactivate; K<sup>+</sup> channels open: K<sup>+</sup> flows out (repolarisation)",
            state_moves(k, "K+", "out", ions, (0.0, 0.55)), [(m, "inactivated") for m in na_ids] + [(m, "open") for m in k_ids])
    b.phase(e["k_closed"] - e["na_closed"], "Undershoot (−80 mV): K<sup>+</sup> channels still open; Na<sup>+</sup> channels recover (closed)",
            state_moves(k, "K+", "out", 1, (0.0, 0.3)), [(m, "closed") for m in na_ids])
    b.phase(AP_DURATION - e["k_closed"], "K<sup>+</sup> channels close: back to the resting potential (−70 mV)", (), [(m, "closed") for m in k_ids])
    states = {m: "closed" for m in na_ids + k_ids}
    trace = tuple((t / AP_DURATION, v) for t, v in ap_trace())
    released = [pid for pid in b.particles]
    return b.plan(states, "action potential", released=released, voltage=trace)


def builder(seed: str, pool: Pool, prefix: str) -> _Builder:
    """A plan builder with its own seeded random numbers (``seed``) drawing on ``pool``."""
    return _Builder(random.Random(seed), pool, prefix)


__all__ = [
    "AP_DURATION", "AP_EVENTS", "AP_PEAK", "AP_REST", "AP_THRESHOLD", "AP_TRACE", "AP_UNDERSHOOT", "Crossing", "Gradients", "Move", "Particle",
    "Phase", "Plan", "Pool", "SELECTIVITY", "aquaporin_problem", "ap_trace", "ap_voltage", "builder", "carrier_problem", "channel_problem",
    "delta_g", "diffusion_problem", "jiggle", "nernst", "osmolarity", "osmosis_problem", "osmosis_way", "plan_abc", "plan_action_potential",
    "plan_aquaporin", "plan_carrier", "plan_channel", "plan_diffusion", "plan_na_k_pump", "plan_p_type_h", "plan_v_type", "scatter",
    "uphill_problem", "wander",
]
