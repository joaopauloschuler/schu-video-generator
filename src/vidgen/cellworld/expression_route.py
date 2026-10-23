"""A gene's products on their way through a cell (DESIGN.md §95.11), without manim: the route
the ``cell`` scene's ``transcribe``, ``export``, ``translate``, ``to_golgi`` and ``secrete``
actions draw — mRNAs made at the gene in the nucleoplasm, out through nuclear pores, onto
ribosomes (on the rough ER for a protein with a signal peptide, whose chains go into the ER
lumen; free in the cytosol otherwise), cargo concentrated at an ER exit site and carried by a
COPII vesicle to the cis-Golgi, through the cisternae to the trans-Golgi network, then a
vesicle to the plasma membrane (secretion, or the membrane itself) or, coated with clathrin, to
a lysosome. Places come from the cell world (its nucleus, pores, rough-ER ribosomes, Golgi
cisternae, plasma membrane, lysosomes); each phase has a camera view (µm) that follows the
products. Markers are drawn a few pixels across at any zoom (a protein is ~5 nm)."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field

from .expression import Gene
from .model import CellWorld, Placed
from .traffic import membrane_site

Point = tuple[float, float]
#: Markers: mRNAs made, polysome ribosomes per mRNA, chains per mRNA.
MRNAS, RIBOSOMES, CHAINS = 4, 3, 2
#: Marker kinds and their size on screen (pixels of a 1080-pixel short side).
MARKER_PX = {"mrna": 54.0, "ribosome": 17.0, "protein": 14.0, "vesicle": 38.0, "coated": 38.0, "copii": 38.0}


@dataclass
class Marker:
    """A drawn product: ``kind`` (mrna, ribosome, protein, vesicle, copii, coated)."""

    key: str
    kind: str


@dataclass
class RoutePose:
    """One moment: each marker's place (µm) and opacity, the camera's view (centre, span µm)."""

    els: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    view: tuple[Point, float] = ((0.0, 0.0), 10.0)

    def copy(self) -> "RoutePose":
        return RoutePose(dict(self.els), self.view)

    def at(self, key: str) -> Point:
        x, y, _ = self.els[key]
        return (x, y)


@dataclass
class RouteClip:
    """A step's phases: ``(weight, caption, pose of progress 0–1)``."""

    phases: list[tuple[float, str, Callable[[float], RoutePose]]]
    end: RoutePose

    def edges(self) -> list[float]:
        total = sum(w for w, _, _ in self.phases) or 1.0
        out = [0.0]
        for w, _, _ in self.phases:
            out.append(out[-1] + w / total)
        return out

    def at(self, alpha: float) -> RoutePose:
        edges = self.edges()
        for k, (_, _, fn) in enumerate(self.phases):
            if alpha <= edges[k + 1] or k == len(self.phases) - 1:
                a, b = edges[k], edges[k + 1]
                return fn(min(1.0, max(0.0, (alpha - a) / (b - a))) if b > a else 1.0)
        return self.end


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def window(t: float, a: float, b: float) -> float:
    return ease((t - a) / (b - a)) if b > a else float(t >= b)


def mix(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def view_of(points: list[Point], least: float = 1.6, most: float = 9.0) -> tuple[Point, float]:
    """A view (centre, span µm) that frames ``points`` with room round them."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.5
    return (cx, cy), min(most, max(least, span))


class RoutePlanner:
    """The places of a gene's route in ``world`` and the clips of its steps, each from where the
    markers are now (``pose``)."""

    def __init__(self, world: CellWorld, gene: Gene, seed: int, start: tuple[Point, float], mrna_first: bool = False) -> None:
        self.world, self.gene = world, gene
        self.rng = random.Random(f"route:{seed}")
        self.markers: list[Marker] = []
        for k in range(MRNAS):
            self.markers.append(Marker(f"m{k}", "mrna"))
            for j in range(RIBOSOMES):
                self.markers.append(Marker(f"r{k}_{j}", "ribosome"))
            for j in range(CHAINS):
                self.markers.append(Marker(f"p{k}_{j}", "protein"))
        self.markers += [Marker("copii", "copii"), Marker("vesicle", "vesicle"), Marker("coated", "coated")]
        self.pose = RoutePose({m.key: (0.0, 0.0, 0.0) for m in self.markers}, start)
        self._places()
        if mrna_first:
            # the scene starts with mature mRNAs in the cytosol, by the pores they left through
            for k in range(MRNAS):
                pore = self.pore_list[k % len(self.pore_list)] if self.pore_list else None
                at = (pore.center[0] + (pore.normal or (1, 0))[0] * 0.25, pore.center[1] + (pore.normal or (1, 0))[1] * 0.25) if pore else \
                    self._jitter(self.locus, 0.6)
                self.pose.els[f"m{k}"] = (*at, 1.0)

    # ----- places --------------------------------------------------------------------------------

    def _places(self) -> None:
        w = self.world
        nucleus = self._one("nucleus")
        self.nucleus = nucleus
        self.pores: list[Placed] = w.members("nucleus.pores") if nucleus is not None and _has(w, "nucleus.pores") else []
        # ribosomes on the rough ER, and on the outer nuclear membrane (part of the rough ER: its lumen is the perinuclear space)
        self.er_ribosomes: list[Placed] = [r for e in ("rough_er.ribosomes", "nucleus.ribosomes") if _has(w, e) for r in w.members(e)]
        golgi = self._one("golgi")
        self.golgi = golgi
        c = nucleus.center if nucleus is not None else (0.0, 0.0)
        # the gene: in the nucleoplasm, between the nucleus's middle and its pores towards the Golgi
        toward = golgi.center if golgi is not None else (c[0] + 1.0, c[1])
        self.locus = self._locus(c, toward)
        pores = sorted(self.pores, key=lambda p: math.dist(p.center, self.locus))[:MRNAS]
        self.pore_list = pores
        self.cisternae: list[Point] = []
        if golgi is not None:
            parts = [p for p in golgi.parts if p.interior and "golgi" in p.interior[0]]
            self.cisternae = [p.outer.center() for p in parts]
            facing = golgi.facing or 0.0
            # the trans-Golgi network: beyond the trans cisterna, away from the cis face
            tx, ty = self.cisternae[-1] if self.cisternae else golgi.center
            self.tgn = (tx - 0.35 * math.cos(facing), ty - 0.35 * math.sin(facing))
            cx, cy = self.cisternae[0] if self.cisternae else golgi.center
            self.cis = (cx + 0.3 * math.cos(facing), cy + 0.3 * math.sin(facing))
        else:
            self.tgn = self.cis = toward

    def _one(self, entry: str) -> Placed | None:
        return self.world.members(entry)[0] if _has(self.world, entry) else None

    def _locus(self, c: Point, toward: Point) -> Point:
        """A point of the nucleoplasm for the gene, clear of the nucleolus."""
        d = math.atan2(toward[1] - c[1], toward[0] - c[0])
        for k in range(24):
            ang = d + (k // 2) * 0.35 * (1 if k % 2 else -1)
            for r in (1.6, 1.2, 2.0, 0.8):
                p = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
                if self.world.compartment_at(p)[0] == "nucleoplasm" and self.world.region_at(p) is None:
                    return p
        return c

    def _jitter(self, p: Point, r: float) -> Point:
        a = self.rng.uniform(0, 2 * math.pi)
        d = r * math.sqrt(self.rng.random())
        return (p[0] + d * math.cos(a), p[1] + d * math.sin(a))

    def _lumen_point(self, ribo: Placed) -> Point:
        """A point of the ER lumen just across the membrane from a bound ribosome."""
        nx, ny = ribo.normal or (0.0, 1.0)
        for depth in (0.05, 0.04, 0.06, 0.035, 0.08):
            q = (ribo.center[0] - nx * depth, ribo.center[1] - ny * depth)
            if self.world.compartment_at(q)[0] in ("er_lumen", "perinuclear_space"):
                return q
        return (ribo.center[0] - nx * 0.05, ribo.center[1] - ny * 0.05)

    # ----- steps ----------------------------------------------------------------------------------

    def play(self, step: str) -> RouteClip:
        builders = {"transcribe": self._transcribe, "export": self._export, "translate": self._translate, "to_golgi": self._to_golgi}
        phases: list[tuple[float, str, Callable[[float], RoutePose]]] = []
        if step == "secrete":
            self._secrete(phases, "outside")
        elif step.startswith("secrete:"):
            self._secrete(phases, step.split(":", 1)[1])
        else:
            builders[step](phases)
        return RouteClip(phases, self.pose)

    def _phase(self, phases: list, weight: float, note: str, fn: Callable[[RoutePose, float], RoutePose]) -> None:
        start = self.pose

        def at(u: float, start: RoutePose = start, fn: Callable[[RoutePose, float], RoutePose] = fn) -> RoutePose:
            return fn(start, u)

        phases.append((weight, note, at))
        self.pose = at(1.0)

    def _camera(self, s: RoutePose, u: float, view: tuple[Point, float]) -> tuple[Point, float]:
        (c0, s0), (c1, s1) = s.view, view
        t = ease(u)
        return (mix(c0, c1, t), s0 * (s1 / s0) ** t)

    def _transcribe(self, phases: list) -> None:
        euk = self.gene.eukaryote
        made = [self._jitter(self.locus, 0.35) for _ in range(MRNAS)]
        view = view_of([self.locus] + [p.center for p in self.pore_list] + made, 3.2, 6.0)

        def fn(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            for k, q in enumerate(made):
                a = window(u, 0.15 + 0.15 * k, 0.35 + 0.15 * k)
                p.els[f"m{k}"] = (*mix(self.locus, q, a), a)
            p.view = self._camera(s, min(1.0, u * 2.5), view)
            return p

        note = ("RNA polymerase II transcribes the gene; the pre-mRNAs are capped, spliced and polyadenylated as they are made "
                "(in a molecule scene each step is shown up close)" if euk else
                "RNA polymerase transcribes the gene in the nucleoid; ribosomes start on the mRNAs at once")
        self._phase(phases, 3.0, note, fn)

    def _export(self, phases: list) -> None:
        starts = {k: self.pose.at(f"m{k}") for k in range(MRNAS)}
        ends: dict[int, tuple[Point, Point, Point]] = {}
        for k in range(MRNAS):
            pore = self.pore_list[k % len(self.pore_list)] if self.pore_list else None
            if pore is None:
                continue
            nx, ny = pore.normal or (1.0, 0.0)
            inside = (pore.center[0] - nx * 0.12, pore.center[1] - ny * 0.12)
            outside = (pore.center[0] + nx * 0.25, pore.center[1] + ny * 0.25)
            ends[k] = (inside, pore.center, outside)
        view = view_of(list(starts.values()) + [e[2] for e in ends.values()], 3.2, 6.0)

        def fn(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            for k, (inside, mid, outside) in ends.items():
                a = window(u, 0.1 * k, 0.6 + 0.1 * k)
                path = [starts[k], inside, mid, outside]
                p.els[f"m{k}"] = (*_along(path, a), 1.0)
            p.view = self._camera(s, u, view)
            return p

        self._phase(phases, 3.0, "Mature mRNPs reach nuclear pore complexes and NXF1–NXT1 carries them through into the cytosol, 5′ end first",
                    fn)
        self.exported = {k: e[2] for k, e in ends.items()}

    def _translate(self, phases: list) -> None:
        g = self.gene
        signal = g.signal > 0 and self.er_ribosomes
        starts = {k: self.pose.at(f"m{k}") for k in range(MRNAS)}
        if signal:
            used: set[str] = set()
            sites: dict[int, Placed] = {}
            for k in range(MRNAS):
                cands = sorted((r for r in self.er_ribosomes if r.key not in used), key=lambda r: math.dist(r.center, starts[k]))
                if cands:
                    sites[k] = cands[0]
                    for r in cands[:8]:
                        used.add(r.key)
            targets = {k: (r.center[0] + (r.normal or (0, 1))[0] * 0.04, r.center[1] + (r.normal or (0, 1))[1] * 0.04) for k, r in sites.items()}
            chains = {k: self._lumen_point(r) for k, r in sites.items()}
        else:
            targets = {k: self._jitter(starts[k], 0.5) for k in range(MRNAS)}
            chains = {k: targets[k] for k in range(MRNAS)}
        self.chain_sites = chains
        view = view_of(list(starts.values()) + list(targets.values()), 3.2, 7.0)

        def move(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            for k, q in targets.items():
                p.els[f"m{k}"] = (*mix(starts[k], q, ease(u)), 1.0)
                # ribosomes join the mRNA (on the ER: the first one targeted by SRP, the others with it)
                for j in range(RIBOSOMES):
                    a = window(u, 0.45 + 0.15 * j, 0.6 + 0.15 * j)
                    off = (j - 1) * 0.045
                    p.els[f"r{k}_{j}"] = (q[0] + off, q[1] + off * 0.6, a)
            p.view = self._camera(s, u, view)
            return p

        def grow(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            for k, q in chains.items():
                for j in range(CHAINS):
                    a = window(u, 0.2 + 0.3 * j, 0.5 + 0.3 * j)
                    p.els[f"p{k}_{j}"] = (*self._spread(q, k, j), a)
            p.view = s.view
            return p

        if signal:
            self._phase(phases, 2.0, "In the cytosol ribosomes start on the mRNAs; SRP binds each signal peptide as it emerges and brings "
                                     "the ribosome to the rough ER", move)
            self._phase(phases, 2.0, "Polysomes on the rough ER translate the mRNAs; the chains go through Sec61 into the ER lumen, lose "
                                     "their signal peptides, are N-glycosylated and fold with BiP and calnexin", grow)
        else:
            self._phase(phases, 2.0, "Free ribosomes in the cytosol join the mRNAs: polysomes", move)
            self._phase(phases, 2.0, "The proteins are made in the cytosol (they have no signal peptide) and fold there", grow)

    def _spread(self, q: Point, k: int, j: int) -> Point:
        a = 2.4 * k + 1.7 * j
        return (q[0] + 0.035 * math.cos(a), q[1] + 0.035 * math.sin(a))

    def _to_golgi(self, phases: list) -> None:
        chains = getattr(self, "chain_sites", {})
        er_pts = [r.center for r in self.er_ribosomes]
        exit_site = min(er_pts, key=lambda q: math.dist(q, self.cis)) if er_pts else self.cis
        self.exit_site = exit_site
        cis, cisternae, tgn = self.cis, self.cisternae, self.tgn
        bud = mix(exit_site, cis, 0.15)
        view1 = view_of([exit_site, cis] + list(chains.values()), 3.2, 8.0)
        view2 = view_of([cis, tgn] + cisternae, 2.6, 5.0)

        def gather(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            for k in chains:
                for j in range(CHAINS):
                    key = f"p{k}_{j}"
                    x, y, o = s.els[key]
                    p.els[key] = (x, y, o * (1.0 - window(u, 0.0, 0.6)))
                for j in range(RIBOSOMES):
                    key = f"r{k}_{j}"
                    x, y, o = s.els[key]
                    p.els[key] = (x, y, o * (1.0 - window(u, 0.0, 0.5)))
                x, y, o = s.els[f"m{k}"]
                p.els[f"m{k}"] = (x, y, o * (1.0 - window(u, 0.0, 0.5)))
            p.els["copii"] = (*bud, window(u, 0.5, 1.0))
            for k in range(MRNAS):
                for j in range(CHAINS):
                    if u > 0.6:
                        p.els[f"p{k}_{j}"] = (*self._cargo(bud, k, j), window(u, 0.6, 1.0))
            p.view = self._camera(s, u, view1)
            return p

        def carry(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            at = mix(bud, cis, ease(u))
            p.els["copii"] = (*at, 1.0 - window(u, 0.85, 1.0))
            for k in range(MRNAS):
                for j in range(CHAINS):
                    p.els[f"p{k}_{j}"] = (*self._cargo(at, k, j), 1.0)
            p.view = self._camera(s, u, view_of([bud, cis], 2.6, 5.0))
            return p

        def through(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            path = [cis] + cisternae + [tgn]
            at = _along(path, ease(u))
            for k in range(MRNAS):
                for j in range(CHAINS):
                    p.els[f"p{k}_{j}"] = (*self._cargo(at, k, j, 0.12), 1.0)
            p.view = self._camera(s, u, view2)
            return p

        self._phase(phases, 2.0, "Only folded proteins leave the ER: COPII (Sar1-GTP, Sec23/24, Sec13/31) concentrates them at an ER exit "
                                 "site and buds a vesicle", gather)
        self._phase(phases, 1.6, "The COPII vesicle loses its coat and fuses (via the ERGIC) with the cis-Golgi", carry)
        self._phase(phases, 2.4, "Cisternae mature cis → medial → trans; enzymes trim and rebuild the N-glycans (complex glycans in the "
                                 "medial and trans cisternae) and add O-glycans", through)

    def _cargo(self, at: Point, k: int, j: int, r: float = 0.032) -> Point:
        a = 2.4 * k + 1.7 * j
        d = r * (0.4 + 0.6 * ((k * 2 + j) % 3) / 2)
        return (at[0] + d * math.cos(a), at[1] + d * math.sin(a))

    def _secrete(self, phases: list, to: str) -> None:
        w = self.world
        tgn = self.tgn
        if to == "lysosome":
            lyso = [t for e in ("lysosomes", "late_endosome", "lysosome") if _has(w, e) for t in w.members(e)]
            dest = min(lyso, key=lambda t: math.dist(t.center, tgn)).center if lyso else tgn
            key, note1 = "coated", ("In the trans-Golgi network mannose 6-phosphate receptors bind the M6P-tagged enzymes; clathrin and AP1 "
                                     "coat a vesicle")
            note2 = "The vesicle sheds its coat and fuses with a late endosome / lysosome; the receptors return to the Golgi"
        else:
            away = (tgn[0] + (tgn[0] - (self.nucleus.center[0] if self.nucleus else 0.0)) * 3.0, tgn[1] + (tgn[1] - (self.nucleus.center[1] if self.nucleus else 0.0)) * 3.0)
            site = membrane_site(w, away)
            dest = (site.point[0] - site.normal[0] * 0.06, site.point[1] - site.normal[1] * 0.06)
            self.pm_site = site
            key = "vesicle"
            note1 = ("Secretory vesicles bud from the trans-Golgi network" if to == "outside" else
                     "The membrane protein leaves the trans-Golgi network in a vesicle's membrane")
            note2 = ("The vesicle reaches the plasma membrane and fuses (SNAREs): exocytosis releases the protein outside the cell"
                     if to == "outside" else "The vesicle fuses with the plasma membrane: the protein becomes part of it, its lumenal side "
                                             "now facing outside")
        view = view_of([tgn, dest], 3.0, 10.0)

        def bud(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            p.els[key] = (*tgn, window(u, 0.2, 0.7))
            for k in range(MRNAS):
                for j in range(CHAINS):
                    p.els[f"p{k}_{j}"] = (*mix(s.at(f"p{k}_{j}"), self._cargo(tgn, k, j), ease(u)), 1.0)
            p.view = self._camera(s, u, view_of([tgn], 2.6, 3.0))
            return p

        def go(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            at = mix(tgn, dest, ease(u))
            p.els[key] = (*at, 1.0)
            for k in range(MRNAS):
                for j in range(CHAINS):
                    p.els[f"p{k}_{j}"] = (*self._cargo(at, k, j), 1.0)
            p.view = self._camera(s, u, view)
            return p

        def fuse(s: RoutePose, u: float) -> RoutePose:
            p = s.copy()
            x, y, _ = s.els[key]
            p.els[key] = (x, y, 1.0 - window(u, 0.2, 0.7))
            for k in range(MRNAS):
                for j in range(CHAINS):
                    q = s.at(f"p{k}_{j}")
                    if to == "outside":
                        site = self.pm_site
                        n = site.normal
                        a = 2.4 * k + 1.7 * j
                        far = (site.point[0] + n[0] * (0.15 + 0.12 * ((k + j) % 3)) + site.tangent[0] * 0.25 * math.sin(a),
                               site.point[1] + n[1] * (0.15 + 0.12 * ((k + j) % 3)) + site.tangent[1] * 0.25 * math.sin(a))
                        p.els[f"p{k}_{j}"] = (*mix(q, far, window(u, 0.3, 1.0)), 1.0)
                    elif to == "membrane":
                        site = self.pm_site
                        along = (k * CHAINS + j - MRNAS) * 0.05
                        spot = (site.point[0] + site.tangent[0] * along, site.point[1] + site.tangent[1] * along)
                        p.els[f"p{k}_{j}"] = (*mix(q, spot, window(u, 0.3, 1.0)), 1.0)
                    else:
                        p.els[f"p{k}_{j}"] = (*q, 1.0)
            p.view = s.view
            return p

        self._phase(phases, 1.4, note1, bud)
        self._phase(phases, 2.4, "The vesicle travels along microtubules (kinesin)" if to != "lysosome" else
                    "The coated vesicle travels to the endosomes", go)
        self._phase(phases, 1.6, note2, fuse)


def _has(world: CellWorld, entry: str) -> bool:
    return any(e.id == entry for e in world.entries)


def _along(path: list[Point], t: float) -> Point:
    lengths = [math.dist(a, b) for a, b in zip(path, path[1:])]
    total = sum(lengths) or 1.0
    goal = t * total
    for (a, b), d in zip(zip(path, path[1:]), lengths):
        if goal <= d:
            return mix(a, b, goal / d if d > 0 else 1.0)
        goal -= d
    return path[-1]


def route_problem(world: CellWorld, gene: Gene, step: str) -> str | None:
    """Why the cell cannot show ``step`` (it lacks the place the step needs)."""
    if not gene.eukaryote or world.kind == "bacterium":
        if step in ("export", "to_golgi", "secrete"):
            return f"{step} needs a eukaryotic cell (a bacterium has no nucleus, ER or Golgi)"
        return None
    if step in ("transcribe", "export") and not _has(world, "nucleus"):
        return f"{step} needs a nucleus in the cell (contents: typical, or an object of kind nucleus)"
    if step == "export" and not _has(world, "nucleus.pores"):
        return "export needs nuclear pores: the nucleus has pores: false"
    if step == "translate" and gene.signal and not _has(world, "rough_er"):
        return "the protein has a signal peptide: its ribosomes go to the rough ER, which this cell lacks (add {kind: rough_er})"
    if step in ("to_golgi", "secrete") and not _has(world, "golgi"):
        return f"{step} needs a Golgi apparatus in the cell (add {{kind: golgi}})"
    return None


__all__ = ["MARKER_PX", "Marker", "RouteClip", "RoutePlanner", "RoutePose", "route_problem", "view_of"]
