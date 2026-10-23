"""Mitosis and meiosis as data (DESIGN.md §95.13; no manim): a karyotype (2n chromosomes in
homologous pairs, maternal and paternal, of different lengths and centromere positions), the
stages of each division with the counts per cell (chromosomes, chromatids, ploidy, DNA content
C), crossing over (each bivalent's crossovers, exchanged segments on the non-sister chromatids),
independent assortment (each bivalent's orientation at metaphase I), and the drawing as
keyframes: :class:`Item` s (chromatids as polylines with coloured segments, kinetochores,
microtubules, cell outlines, nuclear envelopes, centrosomes, the contractile ring or the cell
plate) in a local frame with the spindle of the first division along +x and the cell's radius 1.
The scene interpolates item by item between keyframes and turns the frame for portrait videos.

Textbook consensus (Alberts ch. 17; Morgan): sister chromatids are held by cohesin (along the
arms and at the centromere) until separase cleaves it at anaphase; kinetochores of sisters face
opposite poles at mitotic metaphase (bi-orientation) but the same pole at metaphase I
(co-orientation), where chiasmata hold homologues together; arm cohesion is lost at anaphase I,
centromeric cohesion (protected by shugoshin) only at anaphase II; every bivalent needs at least
one crossover (an obligate chiasma) to segregate correctly."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from vidgen.errors import VidgenError

from .model import did_you_mean

Point = tuple[float, float]

#: Relative lengths and centromere positions (from the p telomere) of up to four homologous
#: pairs: a large metacentric, a submetacentric, an acrocentric and a small submetacentric.
LENGTHS = (1.0, 0.72, 0.52, 0.4)
CENTROMERES = (0.45, 0.3, 0.12, 0.38)
#: Points along a chromatid (from its p telomere to its q telomere).
SAMPLES = 25
#: Points along a cell outline's upper and lower edge, and round a nuclear envelope.
OUTLINE = 61
ENVELOPE = 49

MITOSIS_STAGES = ("interphase", "prophase", "prometaphase", "metaphase", "anaphase", "telophase", "cytokinesis")
MEIOSIS_STAGES = ("interphase", "prophase_i", "prometaphase_i", "metaphase_i", "anaphase_i", "telophase_i", "cytokinesis_i",
                  "prophase_ii", "metaphase_ii", "anaphase_ii", "telophase_ii", "cytokinesis_ii")
STAGE_LABELS = {
    "interphase": "Interphase (G<sub>2</sub>)", "prophase": "Prophase", "prometaphase": "Prometaphase", "metaphase": "Metaphase",
    "anaphase": "Anaphase", "telophase": "Telophase", "cytokinesis": "Cytokinesis",
    "prophase_i": "Prophase I", "prometaphase_i": "Prometaphase I", "metaphase_i": "Metaphase I", "anaphase_i": "Anaphase I",
    "telophase_i": "Telophase I", "cytokinesis_i": "Cytokinesis I", "prophase_ii": "Prophase II", "metaphase_ii": "Metaphase II",
    "anaphase_ii": "Anaphase II", "telophase_ii": "Telophase II", "cytokinesis_ii": "Cytokinesis II",
}


def stage_captions(mode: str, cell: str, pairs: int) -> dict[str, tuple[str, ...]]:
    """What each keyframe of a stage shows, in one line each (the scene captions them)."""
    combos = 2 ** pairs
    plant = cell == "plant"
    return {
        "interphase": ("DNA replicated in S: each chromosome is two sister chromatids held by cohesin"
                       + ("" if plant else "; the centrosome has duplicated"),),
        "prophase": ("Chromosomes condense (condensin)" + ("; a preprophase band marks the division plane" if plant
                                                           else "; the centrosomes separate and nucleate asters"),),
        "prometaphase": ("The nuclear envelope breaks down; kinetochores capture spindle microtubules",),
        "metaphase": ("Chromosomes align on the metaphase plate; sister kinetochores face opposite poles (bi-orientation)",),
        "anaphase": ("Separase cleaves cohesin: sister chromatids move to the poles as kinetochore fibres shorten (anaphase A)",
                     "The poles move apart as the spindle elongates (anaphase B)"),
        "telophase": ("Nuclear envelopes reform round each set; chromosomes decondense",),
        "cytokinesis": (("A cell plate grows outwards from the phragmoplast and becomes the new wall" if plant
                         else "An actomyosin contractile ring pinches the cell in two"),),
        "prophase_i": ("Leptotene–zygotene: chromosomes condense and homologues pair",
                       "Pachytene: homologues are synapsed along the synaptonemal complex; crossing over",
                       "Diplotene: homologues pull apart but stay joined at chiasmata, where segments were exchanged"),
        "prometaphase_i": ("The envelope breaks down; both sister kinetochores of a homologue face the same pole",),
        "metaphase_i": (f"Bivalents on the plate, each orienting independently: 2<sup>{pairs}</sup> = {combos} combinations",),
        "anaphase_i": ("Homologues separate (reductional division); arm cohesin is cleaved, centromeric cohesin is protected (shugoshin)",),
        "telophase_i": ("Each pole has n chromosomes, each still of two chromatids",),
        "cytokinesis_i": ("Two haploid cells (n), each chromosome still two (now non-identical) sister chromatids",),
        "prophase_ii": ("No DNA replication: a new spindle forms in each cell",),
        "metaphase_ii": ("Chromosomes align; sister kinetochores bi-orient as in mitosis",),
        "anaphase_ii": ("Centromeric cohesin is cleaved: sister chromatids separate (equational division)",),
        "telophase_ii": ("Nuclei reform round each set of chromatids",),
        "cytokinesis_ii": ("Four haploid cells, each with one chromatid per chromosome; recombinant chromatids from crossing over",),
    }


@dataclass(frozen=True)
class Counts:
    """What each cell holds after a stage: ``cells``, chromosomes and chromatids per cell,
    ploidy (``2n`` / ``n``) and DNA content (``4C`` …)."""

    cells: int
    chromosomes: int
    chromatids: int
    ploidy: str
    dna: str


def stage_counts(mode: str, stage: str, two_n: int) -> Counts:
    """The counts once ``stage`` is reached, per cell — from telophase on, per daughter
    nucleus (a set at one pole) — counting a chromosome by its centromere: in anaphase the
    separated sisters are chromosomes of their own."""
    n = two_n // 2
    if mode == "mitosis":
        if stage == "anaphase":
            return Counts(1, 2 * two_n, 2 * two_n, "4n", "4C")
        if stage in ("telophase", "cytokinesis"):
            return Counts(2, two_n, two_n, "2n", "2C")
        return Counts(1, two_n, 2 * two_n, "2n", "4C")
    k = MEIOSIS_STAGES.index(stage)
    if k <= MEIOSIS_STAGES.index("anaphase_i"):
        return Counts(1, two_n, 2 * two_n, "2n", "4C")
    if k <= MEIOSIS_STAGES.index("metaphase_ii"):
        return Counts(2, n, 2 * n, "n", "2C")
    if stage == "anaphase_ii":
        return Counts(2, 2 * n, 2 * n, "2n", "2C")
    return Counts(4, n, n, "n", "1C")


# ----- the specification and its checks -------------------------------------------------------------


@dataclass(frozen=True)
class DivisionSpec:
    """A division to draw: ``mode`` (mitosis, meiosis), ``two_n`` (2, 4, 6 or 8), ``cell``
    (animal, plant), ``crossovers`` (per pair: positions 0–1 from the p telomere; ``None``: one
    each, placed by the seed), ``assortment`` (per pair: ``m`` or ``p``, the homologue facing
    the first pole at metaphase I; ``None``: by the seed), ``seed``."""

    mode: str = "mitosis"
    two_n: int = 4
    cell: str = "animal"
    crossovers: tuple[tuple[float, ...], ...] | None = None
    assortment: tuple[str, ...] | None = None
    seed: int = 1


def stages_of(mode: str) -> tuple[str, ...]:
    return MITOSIS_STAGES if mode == "mitosis" else MEIOSIS_STAGES


def stage_key(mode: str, name: str) -> str:
    """The stage ``name`` means in ``mode`` (``prophase I``, ``metaphase_1`` and ``anaphase-2``
    are accepted), or a :class:`VidgenError` with did-you-mean."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    for a, b in (("_1", "_i"), ("_2", "_ii"), ("_one", "_i"), ("_two", "_ii")):
        if key.endswith(a):
            key = key[: -len(a)] + b
    known = stages_of(mode)
    if key not in known:
        hint = ""
        if mode == "mitosis" and key.endswith(("_i", "_ii")):
            hint = " (meiosis I and II are mode: meiosis)"
        elif mode == "meiosis" and key in MITOSIS_STAGES and key != "interphase":
            hint = f" (meiosis has {key}_i and {key}_ii)"
        raise VidgenError(f"{mode} has no stage '{name}'{did_you_mean(key, list(known))}{hint} (stages: {', '.join(known)})")
    return key


def check_spec(spec: DivisionSpec) -> DivisionSpec:
    """The spec with its defaults filled in (crossovers, assortment), or a :class:`VidgenError`
    with the reason."""
    if spec.mode not in ("mitosis", "meiosis"):
        raise VidgenError(f"mode: '{spec.mode}' is not a division (mitosis, meiosis)")
    if spec.two_n % 2 or not 2 <= spec.two_n <= 8:
        raise VidgenError(f"chromosomes: 2n = {spec.two_n}; a diploid cell has homologous pairs, so 2n is even "
                          f"(2, 4, 6 or 8 are drawn; 4 is clearest)")
    if spec.cell not in ("animal", "plant"):
        raise VidgenError(f"cell: '{spec.cell}'{did_you_mean(spec.cell, ['animal', 'plant'])} (animal or plant)")
    if spec.cell == "plant" and spec.mode == "meiosis":
        raise VidgenError("cell: plant is drawn for mitosis only (meiosis is drawn in an animal cell)")
    pairs = spec.two_n // 2
    rng = random.Random(f"division:{spec.seed}")
    if spec.mode == "mitosis":
        if spec.crossovers is not None or spec.assortment is not None:
            raise VidgenError("crossovers and assortment belong to meiosis (mitosis has no pairing of homologues)")
        return spec
    crossovers = spec.crossovers
    if crossovers is None:
        made = []
        for k in range(pairs):
            c = CENTROMERES[k]
            long_q = (1 - c) >= c
            lo, hi = (c + 0.25 * (1 - c), c + 0.8 * (1 - c)) if long_q else (0.2 * c, 0.75 * c)
            made.append((round(rng.uniform(lo, hi), 3),))
        crossovers = tuple(made)
    if len(crossovers) != pairs:
        raise VidgenError(f"crossovers: give one list per homologous pair ({pairs} for 2n = {spec.two_n}), got {len(crossovers)}")
    for k, xs in enumerate(crossovers):
        if not xs:
            raise VidgenError(f"crossovers[{k}]: every bivalent needs at least one crossover (an obligate chiasma): without one "
                              f"the homologues are not held together on the metaphase I spindle and missegregate (nondisjunction)")
        if len(xs) > 2:
            raise VidgenError(f"crossovers[{k}]: at most 2 per bivalent are drawn (crossover interference keeps them few and far apart)")
        c = CENTROMERES[k]
        for x in xs:
            if not 0.02 <= x <= 0.98:
                raise VidgenError(f"crossovers[{k}]: {x} is not on the chromosome (0 is the p telomere, 1 the q telomere)")
            if abs(x - c) < 0.06:
                raise VidgenError(f"crossovers[{k}]: {x} is at the centromere ({c}); crossovers are along the arms")
        if len(xs) == 2 and abs(xs[0] - xs[1]) < 0.15:
            raise VidgenError(f"crossovers[{k}]: {xs[0]} and {xs[1]} are too close (interference keeps crossovers apart)")
    assortment = spec.assortment
    if assortment is None:
        assortment = tuple(rng.choice("mp") for _ in range(pairs))
    if len(assortment) != pairs or any(a not in ("m", "p") for a in assortment):
        raise VidgenError(f"assortment: one letter per pair, m (maternal) or p (paternal) facing the first pole at metaphase I "
                          f"({pairs} for 2n = {spec.two_n})")
    return replace(spec, crossovers=tuple(tuple(sorted(x)) for x in crossovers), assortment=tuple(assortment))


def expect_problem(mode: str, stage: str, two_n: int, expect: dict[str, object]) -> str | None:
    """Why counts an author states for ``stage`` are wrong (``None`` when right): chromosomes,
    chromatids (per cell), cells, ploidy (n / 2n), dna (1C, 2C, 4C)."""
    have = stage_counts(mode, stage, two_n)
    per = {"cells": have.cells, "chromosomes": have.chromosomes, "chromatids": have.chromatids, "ploidy": have.ploidy, "dna": have.dna}
    for key, value in expect.items():
        if key not in per:
            return f"expect: unknown count '{key}'{did_you_mean(key, list(per))} (cells, chromosomes, chromatids, ploidy, dna)"
        want = per[key]
        if str(value).replace(" ", "").lower() != str(want).lower():
            label = STAGE_LABELS[stage].replace("<sub>", "").replace("</sub>", "")
            return (f"after {label} there {'are' if have.cells > 1 else 'is'} {have.cells} cell{'s' if have.cells > 1 else ''}, each with "
                    f"{have.chromosomes} chromosomes ({have.chromatids} chromatids, {have.ploidy}, {have.dna}) for 2n = {two_n}; "
                    f"expect.{key} says {value}")
    return None


# ----- keyframes --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One drawn thing in a keyframe: ``kind`` (chromatid, kinetochore, mt, cell, envelope,
    nucleolus, centrosome, ring, plate, sc, label, ppb), its points (local frame), a width (a
    label's: how far below its point it is written), the
    colour keys (a chromatid's per segment: ``m0`` maternal pair 0…), opacity and ``extra``
    (an envelope's breakdown 0–1; a label's text)."""

    kind: str
    points: tuple[Point, ...]
    width: float = 0.0
    colors: tuple[str, ...] = ()
    opacity: float = 1.0
    extra: float | str = 0.0


@dataclass(frozen=True)
class Keyframe:
    stage: str
    caption: str
    items: dict[str, Item]


@dataclass(frozen=True)
class Chromatid:
    id: str
    pair: int
    parent: str
    sister: int
    length: float
    centromere: float
    colors: tuple[str, ...]


@dataclass
class Division:
    """A planned division: the checked spec, the chromatids, the keyframes in order, and for
    each stage the index of its last keyframe."""

    spec: DivisionSpec
    chromatids: list[Chromatid]
    keyframes: list[Keyframe] = field(default_factory=list)
    stage_end: dict[str, int] = field(default_factory=dict)
    scale: float = 0.4
    width: float = 0.07

    @property
    def stages(self) -> tuple[str, ...]:
        return stages_of(self.spec.mode)

    def extent(self, k: int | None = None) -> tuple[float, float, float, float]:
        """The bounding box of the cells (x0, y0, x1, y1) of keyframe ``k``, or of every one."""
        xs, ys = [], []
        for kf in (self.keyframes if k is None else [self.keyframes[k]]):
            for it in kf.items.values():
                if it.kind == "cell" and it.opacity > 0:
                    xs += [p[0] for p in it.points]
                    ys += [p[1] for p in it.points]
        return min(xs), min(ys), max(xs), max(ys)


def _rot(v: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def _add(a: Point, b: Point, k: float = 1.0) -> Point:
    return (a[0] + k * b[0], a[1] + k * b[1])


def _lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _bump(s: float, s0: float, sigma: float) -> float:
    return math.exp(-((s - s0) / sigma) ** 2)


S_POINTS = tuple(j / (SAMPLES - 1) for j in range(SAMPLES))


def _segment_colors(ch: Chromatid, crossovers: tuple[float, ...], inner: bool, partner: str) -> tuple[str, ...]:
    """Colour keys per segment: the chromatid's own, or its non-sister partner's beyond an odd
    number of crossovers from the centromere (an exchanged segment)."""
    out = []
    for j in range(SAMPLES - 1):
        s = (S_POINTS[j] + S_POINTS[j + 1]) / 2
        swaps = sum(1 for x in crossovers if (ch.centromere < x <= s) or (s <= x < ch.centromere)) if inner else 0
        out.append(partner if swaps % 2 else f"{ch.parent}{ch.pair}")
    return tuple(out)


class Planner:
    """Builds the keyframes of a division (see the module's docstring for the geometry)."""

    def __init__(self, spec: DivisionSpec) -> None:
        self.spec = check_spec(spec)
        self.pairs = spec.two_n // 2
        self.rng = random.Random(f"division:{spec.seed}:layout")
        total = sum(LENGTHS[k] for k in range(self.pairs)) * 2
        self.scale = min(0.42, (1.5 - 0.11 * (spec.two_n - 1)) / total)
        self.w = min(0.075, 0.2 * self.scale)
        self.plant = spec.cell == "plant"
        self.chromatids: list[Chromatid] = []
        for k in range(self.pairs):
            for parent in ("m", "p"):
                for sister in (0, 1):
                    self.chromatids.append(Chromatid(f"c{k}{parent}{sister}", k, parent, sister, LENGTHS[k] * self.scale,
                                                     CENTROMERES[k], ()))
        self.squiggles = {ch.id: self._squiggle(ch) for ch in self.chromatids}
        self.angles = {f"{k}{p}": self.rng.uniform(0, math.pi) for k in range(self.pairs) for p in "mp"}

    # ----- chromatid shapes -------------------------------------------------------------------

    def _squiggle(self, ch: Chromatid) -> list[Point]:
        """Decondensed chromatin about (0, 0): a smooth seeded curve (its territory), sisters
        nearly on top of each other."""
        r = random.Random(f"division:{self.spec.seed}:{ch.pair}{ch.parent}")
        f1, f2 = r.uniform(1.2, 2.0), r.uniform(1.0, 1.8)
        p1, p2 = r.uniform(0, 6.3), r.uniform(0, 6.3)
        g1, g2 = r.uniform(3.5, 4.5), r.uniform(3.0, 4.0)
        amp = 0.13
        d = 0.012 * (1 if ch.sister else -1)
        return [(amp * math.sin(f1 * 2 * math.pi * s + p1) + 0.05 * math.sin(g1 * 2 * math.pi * s) + d,
                 amp * math.sin(f2 * 2 * math.pi * s + p2) + 0.05 * math.cos(g2 * 2 * math.pi * s)) for s in S_POINTS]

    def rod(self, ch: Chromatid, center: Point, angle: float, lane: float, pulls: tuple[tuple[float, float, float], ...] = ()) -> list[Point]:
        """A straight chromatid with its centromere at ``center`` (shifted ``lane`` across), its
        arms along ``angle`` (p arm towards −); ``pulls`` (s, lane, sigma) bend its lane towards
        another near ``s`` (the centromere of sisters, a chiasma)."""
        a = (math.cos(angle), math.sin(angle))
        n = (-a[1], a[0])
        out = []
        for s in S_POINTS:
            off = lane
            for s0, target, sigma in pulls:
                off += (target - off) * _bump(s, s0, sigma)
            out.append(_add(_add(center, a, (s - ch.centromere) * ch.length), n, off))
        return out

    def vee(self, ch: Chromatid, kt: Point, toward: Point, splay: float, side: float = 0.0) -> list[Point]:
        """A chromatid pulled by its kinetochore at ``kt`` towards ``toward`` (a unit vector):
        its arms trail behind, splayed ``splay`` radians either side."""
        back = (-toward[0], -toward[1])
        pa, qa = _rot(back, splay + side), _rot(back, -splay + side)
        out = []
        for s in S_POINTS:
            if s < ch.centromere:
                out.append(_add(kt, pa, (ch.centromere - s) * ch.length))
            else:
                out.append(_add(kt, qa, (s - ch.centromere) * ch.length))
        return out

    def coil(self, ch: Chromatid, rod: list[Point], territory: Point, k: float) -> list[Point]:
        """``rod`` blended towards decondensed chromatin in ``territory`` by ``k`` (1: fully)."""
        sq = self.squiggles[ch.id]
        return [_lerp(p, _add(territory, q), k) for p, q in zip(rod, sq)]

    def colors(self, ch: Chromatid, recombined: bool) -> tuple[str, ...]:
        if self.spec.mode != "meiosis" or not recombined:
            return tuple(f"{ch.parent}{ch.pair}" for _ in range(SAMPLES - 1))
        inner = (ch.parent == "m" and ch.sister == 1) or (ch.parent == "p" and ch.sister == 0)
        partner = f"{'p' if ch.parent == 'm' else 'm'}{ch.pair}"
        assert self.spec.crossovers is not None
        return _segment_colors(ch, self.spec.crossovers[ch.pair], inner, partner)

    def chromatid(self, items: dict[str, Item], ch: Chromatid, pts: list[Point], width: float, recombined: bool,
                  kt: Point | None = None, kt_side: Point = (0.0, 0.0)) -> None:
        items[ch.id] = Item("chromatid", tuple(pts), width, self.colors(ch, recombined))
        if kt is not None:
            items[f"kt:{ch.id}"] = Item("kinetochore", (_add(kt, kt_side, 0.55 * self.w),), 0.022)

    # ----- cells, envelopes, spindles ---------------------------------------------------------

    def cell(self, items: dict[str, Item], cid: str, center: Point, axis: float, rx: float, ry: float, pinch: float = 0.0,
             gap: float = 0.0, opacity: float = 1.0) -> None:
        """A cell outline: an ellipse ``rx`` along ``axis`` by ``ry``, pinched into two round
        daughters as ``pinch`` goes to 1, ``gap`` between them; or the plant cell's box."""
        upper, lower = [], []
        r = rx / 2
        mid = OUTLINE // 2
        for j in range(OUTLINE):
            u = -rx * math.cos(math.pi * j / (OUTLINE - 1))
            if self.plant:
                corner = 0.14
                h = ry if abs(u) <= rx - corner else ry - corner + math.sqrt(max(0.0, corner ** 2 - (abs(u) - rx + corner) ** 2))
                if j in (0, OUTLINE - 1):
                    h = ry - corner
            else:
                ell = ry * math.sqrt(max(0.0, 1 - (u / rx) ** 2))
                two = math.sqrt(max(0.0, r * r - (abs(u) - r) ** 2))
                h = (1 - pinch) * ell + pinch * two
            if j == mid:    # the waist twice: apart by the gap once the daughters separate (the midbody's bridge)
                for uu in (-gap / 2, gap / 2):
                    upper.append(_add(center, _rot((uu, h), axis)))
                    lower.append(_add(center, _rot((uu, -h), axis)))
                continue
            uu = u + math.copysign(gap / 2, u)
            upper.append(_add(center, _rot((uu, h), axis)))
            lower.append(_add(center, _rot((uu, -h), axis)))
        items[f"cell:{cid}"] = Item("cell", tuple(upper + lower[::-1]), 0.0, (), opacity)
        if not self.plant:
            waist = (1 - pinch) * ry
            on = 1.0 if 0.05 < pinch < 0.999 else 0.0
            items[f"ring:{cid}:0"] = Item("ring", (_add(center, _rot((0.0, waist), axis)),), 0.035, (), on * opacity)
            items[f"ring:{cid}:1"] = Item("ring", (_add(center, _rot((0.0, -waist), axis)),), 0.035, (), on * opacity)

    def envelope(self, items: dict[str, Item], nid: str, center: Point, radius: float, broken: float = 0.0, opacity: float = 1.0,
                 nucleolus: float = 0.0) -> None:
        pts = tuple(_add(center, (radius * math.cos(2 * math.pi * j / (ENVELOPE - 1)), radius * math.sin(2 * math.pi * j / (ENVELOPE - 1))))
                    for j in range(ENVELOPE))
        items[f"nuc:{nid}"] = Item("envelope", pts, 0.0, (), opacity, broken)
        items[f"nl:{nid}"] = Item("nucleolus", (_add(center, (0.32 * radius, -0.3 * radius)),), 0.26 * radius, (), nucleolus)

    def pole(self, items: dict[str, Item], pid: str, at: Point, opacity: float = 1.0, asters: float = 0.0, outward: float = 0.0,
             angle: float = 0.0) -> None:
        """A centrosome (two centrioles at right angles; ``angle``) with ``asters`` (0–1) of
        astral microtubules spread round the ``outward`` direction (none in a plant cell)."""
        if self.plant:
            return
        items[f"cs:{pid}"] = Item("centrosome", (at,), 0.05, (), opacity, angle)
        for j in range(5):
            a = outward + (j - 2) * 0.45
            end = _add(at, (math.cos(a), math.sin(a)), 0.3 * asters)
            items[f"mt:a:{pid}:{j}"] = Item("mt", (at, end), 0.0, ("astral",), opacity * (1.0 if asters > 0 else 0.0))

    def fibre(self, items: dict[str, Item], key: str, a: Point, b: Point, opacity: float = 1.0, kind: str = "kinetochore") -> None:
        items[f"mt:{key}"] = Item("mt", (a, b), 0.0, (kind,), opacity)

    def polar(self, items: dict[str, Item], pid: str, at: Point, other: Point, reach: float, opacity: float = 1.0,
              spread: float = 0.13) -> None:
        """Interpolar microtubules from a pole past the middle (``reach`` beyond it)."""
        mid = _lerp(at, other, 0.5)
        d = (other[0] - at[0], other[1] - at[1])
        length = math.hypot(*d) or 1.0
        u = (d[0] / length, d[1] / length)
        n = (-u[1], u[0])
        for j, off in enumerate((-spread, 0.0, spread)):
            start = _add(at, n, off * 0.25) if not self.plant else _add(at, n, off * 2.5)
            items[f"mt:i:{pid}:{j}"] = Item("mt", (start, _add(_add(mid, u, reach), n, off)), 0.0, ("polar",), opacity)

    def pole_point(self, pole: Point, target: Point, axis_v: Point) -> Point:
        """Where a fibre to ``target`` leaves a pole: the centrosome, or in a plant cell's
        broad pole a point along it."""
        if not self.plant:
            return pole
        across = (target[0] - pole[0]) * axis_v[0] + (target[1] - pole[1]) * axis_v[1]
        return _add(pole, axis_v, 0.6 * across)


# ----- the stages -------------------------------------------------------------------------------------


def _territories(center: Point, radius: float, count: int) -> list[Point]:
    return [_add(center, (radius * 0.68 * math.sqrt((i + 0.5) / count) * math.cos(i * 2.39996 + 0.5),
                          radius * 0.68 * math.sqrt((i + 0.5) / count) * math.sin(i * 2.39996 + 0.5))) for i in range(count)]


def plan_division(spec: DivisionSpec) -> Division:
    """The keyframes of a division (checked: :func:`check_spec`)."""
    pl = Planner(spec)
    if pl.spec.mode == "mitosis":
        frames = _mitosis(pl)
    else:
        frames = _meiosis(pl)
    division = Division(pl.spec, pl.chromatids, [], {}, pl.scale, pl.w)
    captions = stage_captions(pl.spec.mode, pl.spec.cell, pl.pairs)
    for stage, items_list in frames:
        for k, items in enumerate(items_list):
            caps = captions[stage]
            division.keyframes.append(Keyframe(stage, caps[min(k, len(caps) - 1)], items))
        division.stage_end[stage] = len(division.keyframes) - 1
    _complete(division)
    return division


def _complete(division: Division) -> None:
    """Every keyframe gets every item: one missing is the nearest keyframe's copy, unseen (so
    it fades in or out where it is; a microtubule grows from its start)."""
    ids: dict[str, None] = {}
    for kf in division.keyframes:
        ids.update(dict.fromkeys(kf.items))
    frames = division.keyframes
    for i, kf in enumerate(frames):
        for key in ids:
            if key in kf.items:
                continue
            near = None
            for d in range(1, len(frames)):
                for j in (i - d, i + d):
                    if 0 <= j < len(frames) and key in frames[j].items:
                        near = frames[j].items[key]
                        break
                if near is not None:
                    break
            assert near is not None
            if near.kind == "mt":
                near = replace(near, points=(near.points[0], near.points[0]))
            kf.items[key] = replace(near, opacity=0.0)


def _plate_slots(pl: Planner, groups: list[tuple[float, float]], span: float) -> list[float]:
    """Centres along the plate of groups (length, centromere share) packed with gaps."""
    gap = 0.11
    total = sum(g[0] for g in groups) + gap * (len(groups) - 1)
    k = min(1.0, span / total) if total > 0 else 1.0
    at = -total * k / 2
    out = []
    for length, c in groups:
        out.append(at + c * length * k)
        at += length * k + gap * k
    return out


def _mitosis(pl: Planner) -> list[tuple[str, list[dict[str, Item]]]]:
    w = pl.w
    plant = pl.plant
    chroms = [(k, p) for k in range(pl.pairs) for p in "mp"]
    by = {(ch.pair, ch.parent, ch.sister): ch for ch in pl.chromatids}
    order = list(chroms)
    random.Random(f"division:{pl.spec.seed}:plate").shuffle(order)
    rx0, ry0 = (1.3, 0.88) if plant else (1.0, 0.9)
    pole_u = 1.0 if plant else 0.82
    terr = dict(zip(chroms, _territories((0.0, 0.0), 0.55, len(chroms))))
    frames: list[tuple[str, list[dict[str, Item]]]] = []
    up = (0.0, 1.0)

    def base(items: dict[str, Item], rx: float = rx0, ry: float = ry0, pinch: float = 0.0, gap: float = 0.0) -> None:
        pl.cell(items, "main", (0.0, 0.0), 0.0, rx, ry, pinch, gap)

    # interphase (G2)
    it: dict[str, Item] = {}
    base(it)
    pl.envelope(it, "main", (0.0, 0.0), 0.55, nucleolus=1.0)
    pl.pole(it, "L", (-0.06, 0.72), angle=0.3)
    pl.pole(it, "R", (0.06, 0.72), angle=1.2)
    for key in chroms:
        for s in (0, 1):
            ch = by[(*key, s)]
            rod = pl.rod(ch, terr[key], pl.angles[f"{key[0]}{key[1]}"], (s - 0.5) * 0.02)
            pl.chromatid(it, ch, pl.coil(ch, rod, terr[key], 1.0), 0.012, False)
    frames.append(("interphase", [it]))

    # prophase
    it = {}
    base(it)
    pl.envelope(it, "main", (0.0, 0.0), 0.55, nucleolus=0.0)
    pl.pole(it, "L", (0.72 * math.cos(2.5), 0.72 * math.sin(2.5)), asters=0.6, outward=2.5, angle=0.3)
    pl.pole(it, "R", (0.72 * math.cos(0.64), 0.72 * math.sin(0.64)), asters=0.6, outward=0.64, angle=1.2)
    if plant:
        it["ppb:0"] = Item("ppb", ((0.0, ry0 - 0.05),), 0.05)
        it["ppb:1"] = Item("ppb", ((0.0, -ry0 + 0.05),), 0.05)
    for key in chroms:
        ang = pl.angles[f"{key[0]}{key[1]}"]
        for s in (0, 1):
            ch = by[(*key, s)]
            lane = (s - 0.5) * 2 * 0.5 * w
            rod = pl.rod(ch, terr[key], ang, lane, ((ch.centromere, 0.0, 0.05),))
            pl.chromatid(it, ch, pl.coil(ch, rod, terr[key], 0.3), 0.6 * w, False)
    frames.append(("prophase", [it]))

    # prometaphase
    it = {}
    base(it)
    pl.envelope(it, "main", (0.0, 0.0), 0.55, broken=1.0, opacity=0.0)
    left, right = (-pole_u, 0.0), (pole_u, 0.0)
    pl.pole(it, "L", left, asters=1.0, outward=math.pi, angle=0.3)
    pl.pole(it, "R", right, asters=1.0, outward=0.0, angle=1.2)
    pl.polar(it, "L", left, right, 0.15)
    pl.polar(it, "R", right, left, 0.15)
    for n_, key in enumerate(chroms):
        t = terr[key]
        mono = n_ % 2 == 1
        ang = (pl.angles[f"{key[0]}{key[1]}"] + math.pi / 2) / 2
        side = -1.0 if t[0] < 0 else 1.0
        c = (0.45 * t[0] + (0.18 * side if mono else 0.0), 0.8 * t[1])
        for s in (0, 1):
            ch = by[(*key, s)]
            lane = (s - 0.5) * 1.25 * w
            a = (math.cos(ang), math.sin(ang))
            nrm = (-a[1], a[0])
            face = nrm if s == 1 else (-nrm[0], -nrm[1])
            pole = right if face[0] > 0 else left
            rod = pl.rod(ch, c, ang, lane, ((ch.centromere, (s - 0.5) * 0.5 * w, 0.05),))
            ktp = _add(c, nrm, (s - 0.5) * 0.5 * w)
            pl.chromatid(it, ch, rod, w, False, ktp, face)
            attached = (not mono) or (pole[0] * side > 0)
            pl.fibre(it, f"k:{ch.id}", pl.pole_point(pole, ktp, up), _add(ktp, face, 0.55 * w), 1.0 if attached else 0.0)
    frames.append(("prometaphase", [it]))

    # metaphase
    it = {}
    base(it)
    pl.pole(it, "L", left, asters=1.0, outward=math.pi, angle=0.3)
    pl.pole(it, "R", right, asters=1.0, outward=0.0, angle=1.2)
    pl.polar(it, "L", left, right, 0.15)
    pl.polar(it, "R", right, left, 0.15)
    slots = _plate_slots(pl, [(by[(*k, 0)].length, by[(*k, 0)].centromere) for k in order], 1.5 * ry0 / 0.9 if not plant else 1.45)
    plate_v = dict(zip(order, slots))
    for key in chroms:
        c = (0.0, plate_v[key])
        for s in (0, 1):
            ch = by[(*key, s)]
            lane = (s - 0.5) * 1.25 * w          # across = -x for angle pi/2: sister 1 faces left
            rod = pl.rod(ch, c, math.pi / 2, lane, ((ch.centromere, (s - 0.5) * 0.5 * w, 0.05),))
            face = (-1.0, 0.0) if s == 1 else (1.0, 0.0)
            ktp = (-(s - 0.5) * 0.5 * w, c[1])
            pl.chromatid(it, ch, rod, w, False, ktp, face)
            pole = left if face[0] < 0 else right
            pl.fibre(it, f"k:{ch.id}", pl.pole_point(pole, ktp, up), _add(ktp, face, 0.55 * w))
    frames.append(("metaphase", [it]))

    # anaphase A and B
    stages = []
    for kt_u, pu, rx, ry in ((0.5, 0.88, 1.12, 0.85), (0.98 if not plant else 0.72, 1.3 if not plant else 1.0, 1.45 if not plant else rx0,
                                                        0.8 if not plant else ry0)):
        it = {}
        base(it, rx, ry)
        lp, rp = (-pu, 0.0), (pu, 0.0)
        pl.pole(it, "L", lp, asters=1.0, outward=math.pi, angle=0.3)
        pl.pole(it, "R", rp, asters=1.0, outward=0.0, angle=1.2)
        pl.polar(it, "L", lp, rp, 0.12 if kt_u < 0.6 else 0.05)
        pl.polar(it, "R", rp, lp, 0.12 if kt_u < 0.6 else 0.05)
        for key in chroms:
            for s in (0, 1):
                ch = by[(*key, s)]
                go = (-1.0, 0.0) if s == 1 else (1.0, 0.0)
                ktp = (go[0] * kt_u, plate_v[key] * (0.72 if kt_u < 0.6 else 0.6))
                pts = pl.vee(ch, ktp, go, 0.32)
                pl.chromatid(it, ch, pts, w, False, ktp, go)
                pole = lp if go[0] < 0 else rp
                pl.fibre(it, f"k:{ch.id}", pl.pole_point(pole, ktp, up), _add(ktp, go, 0.55 * w))
        stages.append(it)
    frames.append(("anaphase", stages))

    # telophase
    it = {}
    du, nr = (0.95, 0.36) if not plant else (0.66, 0.32)
    if plant:
        base(it)
        it["plate:main"] = Item("plate", ((0.0, -0.35), (0.0, 0.35)), 0.04)
        pl.polar(it, "L", (-0.35, 0.0), (0.35, 0.0), 0.05, spread=0.3)
        pl.polar(it, "R", (0.35, 0.0), (-0.35, 0.0), 0.05, spread=0.3)
    else:
        base(it, 1.55, 0.78, 0.45)
        pl.pole(it, "L", (-1.3, 0.0), opacity=1.0, angle=0.3)
        pl.pole(it, "R", (1.3, 0.0), opacity=1.0, angle=1.2)
        pl.polar(it, "L", (-0.3, 0.0), (0.3, 0.0), 0.04, spread=0.06)
        pl.polar(it, "R", (0.3, 0.0), (-0.3, 0.0), 0.04, spread=0.06)
    for side, nid in ((-1, "L"), (1, "R")):
        center = (side * du, 0.0)
        pl.envelope(it, nid, center, nr, broken=0.4, opacity=0.8)
        ts = dict(zip(chroms, _territories(center, nr, len(chroms))))
        for key in chroms:
            ch = by[(*key, 1 if side < 0 else 0)]
            rod = pl.vee(ch, _add(center, (0.1 * -side, 0.0)), (float(side), 0.0), 0.3)
            pl.chromatid(it, ch, pl.coil(ch, rod, ts[key], 0.6), 0.45 * w, False)
    frames.append(("telophase", [it]))

    # cytokinesis
    it = {}
    if plant:
        base(it)
        it["plate:main"] = Item("plate", ((0.0, -ry0), (0.0, ry0)), 0.04)
    else:
        base(it, 1.72, 0.78, 1.0, 0.1)
        pl.pole(it, "L", (-1.2, 0.45), angle=0.3)
        pl.pole(it, "R", (1.2, 0.45), angle=1.2)
    for side, nid in ((-1, "L"), (1, "R")):
        center = (side * (0.91 if not plant else 0.66), 0.0)
        pl.envelope(it, nid, center, nr + 0.04, nucleolus=1.0)
        ts = dict(zip(chroms, _territories(center, nr + 0.04, len(chroms))))
        for key in chroms:
            ch = by[(*key, 1 if side < 0 else 0)]
            rod = pl.vee(ch, center, (float(side), 0.0), 0.3)
            pl.chromatid(it, ch, pl.coil(ch, rod, ts[key], 1.0), 0.012, False)
        it[f"label:{nid}"] = Item("label", (center,), 0.6, (), 1.0, f"2n = {pl.spec.two_n}")
    frames.append(("cytokinesis", [it]))
    return frames


def _meiosis(pl: Planner) -> list[tuple[str, list[dict[str, Item]]]]:
    w = pl.w
    by = {(ch.pair, ch.parent, ch.sister): ch for ch in pl.chromatids}
    pairs = list(range(pl.pairs))
    assert pl.spec.assortment is not None and pl.spec.crossovers is not None
    left_parent = {k: pl.spec.assortment[k] for k in pairs}    # the homologue facing the left pole at metaphase I
    terr = dict(zip(pairs, _territories((0.0, 0.0), 0.5, len(pairs))))
    biv_angle = {k: pl.rng.uniform(0, math.pi) for k in pairs}
    frames: list[tuple[str, list[dict[str, Item]]]] = []
    g = 1.25 * w
    up = (0.0, 1.0)

    def lanes(k: int, spread: float, chiasma: bool) -> dict[tuple[str, int], tuple[float, tuple[tuple[float, float, float], ...]]]:
        """Across positions of the four chromatids of bivalent ``k`` (the left-facing homologue
        at −), each sister pair pinched at its centromere; inner chromatids pulled together at
        the chiasmata when ``chiasma``."""
        out = {}
        c = CENTROMERES[k]
        for parent in "mp":
            # lanes run along the rod's normal (−x for arms along +y): the left homologue at +
            sign = 1.0 if parent == left_parent[k] else -1.0
            mid = sign * (spread + 0.5 * g)
            for sister in (0, 1):
                inner = (parent == "m" and sister == 1) or (parent == "p" and sister == 0)
                lane = mid + (-0.5 * g if inner else 0.5 * g) * sign
                pulls: list[tuple[float, float, float]] = [(c, mid + (lane - mid) * 0.45, 0.05)]
                if chiasma and inner:
                    pulls += [(x, sign * 0.15 * g, 0.07) for x in pl.spec.crossovers[k]]
                out[(parent, sister)] = (lane, tuple(pulls))
        return out

    def cell_main(items: dict[str, Item], rx: float = 1.0, ry: float = 0.9, pinch: float = 0.0, gap: float = 0.0, opacity: float = 1.0) -> None:
        pl.cell(items, "main", (0.0, 0.0), 0.0, rx, ry, pinch, gap, opacity)

    def bivalents(items: dict[str, Item], centers: dict[int, Point], angles: dict[int, float], spread: float, chiasma: bool,
                  recombined: bool, k_coil: float, width: float, sc: float, kts: bool = False,
                  poles: tuple[Point, Point] | None = None) -> None:
        for k in pairs:
            ls = lanes(k, spread, chiasma)
            a = angles[k]
            nrm = (-math.sin(a), math.cos(a))
            for (parent, sister), (lane, pulls) in ls.items():
                ch = by[(k, parent, sister)]
                rod = pl.rod(ch, centers[k], a, lane, pulls)
                pts = pl.coil(ch, rod, centers[k], k_coil) if k_coil > 0 else rod
                ktp = None
                face = (0.0, 0.0)
                if kts:
                    sign = 1.0 if parent == left_parent[k] else -1.0
                    face = (nrm[0] * sign, nrm[1] * sign)
                    ktp = _add(centers[k], nrm, sign * (spread + 0.5 * g) + (lane - sign * (spread + 0.5 * g)) * 0.45)
                pl.chromatid(items, ch, pts, width, recombined, ktp, face)
                if kts and poles is not None and ktp is not None:
                    pole = poles[0] if face[0] < 0 else poles[1]
                    pl.fibre(items, f"k:{ch.id}", pl.pole_point(pole, ktp, up), _add(ktp, face, 0.55 * w))
            if sc >= 0:
                mid = []
                for s in S_POINTS:
                    ch = by[(k, "m", 0)]
                    mid.append(_add(centers[k], (math.cos(a), math.sin(a)), (s - ch.centromere) * ch.length))
                items[f"sc:{k}"] = Item("sc", tuple(mid), 0.012, (), sc)

    # interphase
    it: dict[str, Item] = {}
    cell_main(it)
    pl.envelope(it, "main", (0.0, 0.0), 0.55, nucleolus=1.0)
    pl.pole(it, "L", (-0.06, 0.72), angle=0.3)
    pl.pole(it, "R", (0.06, 0.72), angle=1.2)
    t2 = dict(zip([(k, p) for k in pairs for p in "mp"], _territories((0.0, 0.0), 0.55, 2 * len(pairs))))
    for k in pairs:
        for p in "mp":
            for s in (0, 1):
                ch = by[(k, p, s)]
                rod = pl.rod(ch, t2[(k, p)], pl.angles[f"{k}{p}"], (s - 0.5) * 0.02)
                pl.chromatid(it, ch, pl.coil(ch, rod, t2[(k, p)], 1.0), 0.012, False)
    frames.append(("interphase", [it]))

    # prophase I: leptotene–zygotene, pachytene, diplotene
    pro = []
    for spread, k_coil, width, sc, chiasma, rec, nl in ((0.16, 0.55, 0.45 * w, 0.0, False, False, 1.0),
                                                        (0.0, 0.18, 0.7 * w, 1.0, False, False, 0.6),
                                                        (0.9 * g, 0.0, w, 0.0, True, True, 0.0)):
        it = {}
        cell_main(it)
        pl.envelope(it, "main", (0.0, 0.0), 0.55, nucleolus=nl)
        frac = len(pro) / 2
        aL, aR = 1.75 + 0.75 * frac, 1.39 - 0.75 * frac
        pl.pole(it, "L", (0.74 * math.cos(aL), 0.74 * math.sin(aL)), asters=0.4 + 0.3 * frac, outward=aL, angle=0.3)
        pl.pole(it, "R", (0.74 * math.cos(aR), 0.74 * math.sin(aR)), asters=0.4 + 0.3 * frac, outward=aR, angle=1.2)
        bivalents(it, terr, biv_angle, spread, chiasma, rec, k_coil, width, sc)
        pro.append(it)
    frames.append(("prophase_i", pro))

    # prometaphase I
    left, right = (-0.82, 0.0), (0.82, 0.0)
    slots = _plate_slots(pl, [(LENGTHS[k] * pl.scale, CENTROMERES[k]) for k in pairs], 1.5)
    order = list(pairs)
    random.Random(f"division:{pl.spec.seed}:plate").shuffle(order)
    plate = dict(zip(order, slots))
    it = {}
    cell_main(it)
    pl.envelope(it, "main", (0.0, 0.0), 0.55, broken=1.0, opacity=0.0)
    pl.pole(it, "L", left, asters=1.0, outward=math.pi, angle=0.3)
    pl.pole(it, "R", right, asters=1.0, outward=0.0, angle=1.2)
    pl.polar(it, "L", left, right, 0.15)
    pl.polar(it, "R", right, left, 0.15)
    mid_c = {k: (0.45 * terr[k][0], 0.5 * terr[k][1] + 0.5 * plate[k]) for k in pairs}
    mid_a = {k: (biv_angle[k] + math.pi / 2) / 2 for k in pairs}    # turning on the way to the plate
    bivalents(it, mid_c, mid_a, 0.9 * g, True, True, 0.0, w, -1, kts=True, poles=(left, right))
    frames.append(("prometaphase_i", [it]))

    # metaphase I
    it = {}
    cell_main(it)
    pl.pole(it, "L", left, asters=1.0, outward=math.pi, angle=0.3)
    pl.pole(it, "R", right, asters=1.0, outward=0.0, angle=1.2)
    pl.polar(it, "L", left, right, 0.15)
    pl.polar(it, "R", right, left, 0.15)
    plate_c = {k: (0.0, plate[k]) for k in pairs}
    bivalents(it, plate_c, {k: math.pi / 2 for k in pairs}, 0.9 * g, True, True, 0.0, w, -1, kts=True, poles=(left, right))
    frames.append(("metaphase_i", [it]))

    # anaphase I: homologues (both sisters) to the poles, arms splayed (arm cohesion gone)
    stages = []
    for kt_u, pu, rx, ry in ((0.5, 0.88, 1.12, 0.85), (0.95, 1.25, 1.42, 0.8)):
        it = {}
        cell_main(it, rx, ry)
        lp, rp = (-pu, 0.0), (pu, 0.0)
        pl.pole(it, "L", lp, asters=1.0, outward=math.pi, angle=0.3)
        pl.pole(it, "R", rp, asters=1.0, outward=0.0, angle=1.2)
        pl.polar(it, "L", lp, rp, 0.1)
        pl.polar(it, "R", rp, lp, 0.1)
        for k in pairs:
            for parent in "mp":
                go = (-1.0, 0.0) if parent == left_parent[k] else (1.0, 0.0)
                for sister in (0, 1):
                    ch = by[(k, parent, sister)]
                    ktp = (go[0] * kt_u, plate[k] * 0.7 + (sister - 0.5) * 0.9 * w)
                    pts = pl.vee(ch, ktp, go, 0.26 + 0.14 * sister, side=(sister - 0.5) * 0.1)
                    pl.chromatid(it, ch, pts, w, True, ktp, go)
                    pole = lp if go[0] < 0 else rp
                    pl.fibre(it, f"k:{ch.id}", pole, _add(ktp, go, 0.55 * w))
        stages.append(it)
    frames.append(("anaphase_i", stages))

    # telophase I and cytokinesis I
    centers = {"a": (-0.95, 0.0), "b": (0.95, 0.0)}
    side_of = {k: {left_parent[k]: "a", ("p" if left_parent[k] == "m" else "m"): "b"} for k in pairs}
    for stage, pinch, gap, rx, k_coil, nuc in (("telophase_i", 0.45, 0.0, 1.55, 0.35, 0.7), ("cytokinesis_i", 1.0, 0.1, 1.8, 0.35, 1.0)):
        it = {}
        cell_main(it, rx, 0.8 if stage == "telophase_i" else 0.9, pinch, gap)
        for cid in "ab":
            cx = centers[cid][0] * (1.0 if stage == "cytokinesis_i" else 0.98)
            pl.envelope(it, cid, (cx, 0.0), 0.36, broken=0.3 if stage == "telophase_i" else 0.0, opacity=nuc * 0.8)
            pl.pole(it, "L" if cid == "a" else "R", (cx + (0.42 if cid == "b" else -0.42), 0.0), angle=0.3 if cid == "a" else 1.2)
        ts = {cid: dict(zip(pairs, _territories((centers[cid][0], 0.0), 0.36, len(pairs)))) for cid in "ab"}
        for k in pairs:
            for parent in "mp":
                cid = side_of[k][parent]
                center = ts[cid][k]
                for sister in (0, 1):
                    ch = by[(k, parent, sister)]
                    go = (-1.0, 0.0) if cid == "a" else (1.0, 0.0)
                    pts = pl.vee(ch, _add(center, (0.0, (sister - 0.5) * 0.9 * w)), go, 0.26 + 0.14 * sister)
                    pl.chromatid(it, ch, pl.coil(ch, pts, center, k_coil), 0.7 * w, True)
        if stage == "cytokinesis_i":
            for cid in "ab":   # the daughters take over the outline (same circle)
                pl.cell(it, cid, centers[cid], math.pi / 2, 0.9, 0.9, opacity=0.0)
        frames.append((stage, [it]))

    # meiosis II, in both daughters (spindles at right angles to the first)
    def poles2(cid: str, dv: float) -> tuple[Point, Point]:
        cx = centers[cid][0]
        return (cx, -dv), (cx, dv)

    order2 = {cid: [k for k in order] for cid in "ab"}
    plate2 = {cid: dict(zip(order2[cid], _plate_slots(pl, [(LENGTHS[k] * pl.scale, CENTROMERES[k]) for k in order2[cid]], 1.3)))
              for cid in "ab"}

    def homologue_in(cid: str, k: int) -> str:
        return left_parent[k] if cid == "a" else ("p" if left_parent[k] == "m" else "m")

    def two_cells(items: dict[str, Item], rx: float = 0.9, ry: float = 0.9, pinch: float = 0.0, gap: float = 0.0) -> None:
        pl.cell(items, "main", (0.0, 0.0), 0.0, 1.8, 0.9, 1.0, 0.1, opacity=0.0)
        for cid in "ab":
            pl.cell(items, cid, centers[cid], math.pi / 2, rx, ry, pinch, gap)

    it = {}
    two_cells(it)
    rng2 = random.Random(f"division:{pl.spec.seed}:ii")
    for cid in "ab":
        lo, hi = poles2(cid, 0.72)
        pl.pole(it, f"{cid}0", _lerp(centers[cid], lo, 0.7), asters=0.6, outward=-math.pi / 2, angle=0.3)
        pl.pole(it, f"{cid}1", _lerp(centers[cid], hi, 0.7), asters=0.6, outward=math.pi / 2, angle=1.2)
        ts = dict(zip(pairs, _territories(centers[cid], 0.5, len(pairs))))
        for k in pairs:
            parent = homologue_in(cid, k)
            ang = rng2.uniform(0, math.pi)
            for sister in (0, 1):
                ch = by[(k, parent, sister)]
                rod = pl.rod(ch, ts[k], ang, (sister - 0.5) * 1.25 * w, ((ch.centromere, (sister - 0.5) * 0.5 * w, 0.05),))
                pl.chromatid(it, ch, pl.coil(ch, rod, ts[k], 0.12), 0.85 * w, True)
    frames.append(("prophase_ii", [it]))

    def plate_ii(items: dict[str, Item]) -> None:
        for cid in "ab":
            lo, hi = poles2(cid, 0.72)
            pl.pole(items, f"{cid}0", lo, asters=1.0, outward=-math.pi / 2, angle=0.3)
            pl.pole(items, f"{cid}1", hi, asters=1.0, outward=math.pi / 2, angle=1.2)
            pl.polar(items, f"{cid}0", lo, hi, 0.12)
            pl.polar(items, f"{cid}1", hi, lo, 0.12)

    it = {}
    two_cells(it)
    plate_ii(it)
    for cid in "ab":
        lo, hi = poles2(cid, 0.72)
        for k in pairs:
            parent = homologue_in(cid, k)
            c = (centers[cid][0] + plate2[cid][k], 0.0)
            for sister in (0, 1):
                ch = by[(k, parent, sister)]
                lane = (sister - 0.5) * 1.25 * w            # angle 0: across = +y, sister 1 faces up
                rod = pl.rod(ch, c, 0.0, lane, ((ch.centromere, (sister - 0.5) * 0.5 * w, 0.05),))
                face = (0.0, 1.0) if sister == 1 else (0.0, -1.0)
                ktp = (c[0], c[1] + (sister - 0.5) * 0.5 * w)
                pl.chromatid(it, ch, rod, w, True, ktp, face)
                pl.fibre(it, f"k:{ch.id}", hi if sister == 1 else lo, _add(ktp, face, 0.55 * w))
    frames.append(("metaphase_ii", [it]))

    it = {}
    two_cells(it, 1.1, 0.8)
    plate_ii(it)
    for cid in "ab":
        lo, hi = poles2(cid, 0.8)
        for k in pairs:
            parent = homologue_in(cid, k)
            for sister in (0, 1):
                ch = by[(k, parent, sister)]
                go = (0.0, 1.0) if sister == 1 else (0.0, -1.0)
                ktp = (centers[cid][0] + plate2[cid][k] * 0.75, go[1] * 0.5)
                pl.chromatid(it, ch, pl.vee(ch, ktp, go, 0.32), w, True, ktp, go)
                pl.fibre(it, f"k:{ch.id}", hi if sister == 1 else lo, _add(ktp, go, 0.55 * w))
    frames.append(("anaphase_ii", [it]))

    # the products keep their chromosomes condensed (drawn so), so the exchanged segments stay visible
    for stage, rx, pinch, gap, k_coil, nuc in (("telophase_ii", 1.3, 0.5, 0.0, 0.2, 0.8), ("cytokinesis_ii", 1.36, 1.0, 0.08, 0.12, 1.0)):
        it = {}
        two_cells(it, rx, 0.8 if stage == "telophase_ii" else 0.68, pinch, gap)
        for cid in "ab":
            cx = centers[cid][0]
            for sister in (0, 1):
                cy = (0.68 if stage == "telophase_ii" else 0.72) * (1 if sister else -1)
                nid = f"{cid}{sister}"
                pl.envelope(it, nid, (cx, cy), 0.27 if stage == "telophase_ii" else 0.3, broken=0.3 if stage == "telophase_ii" else 0.0,
                            opacity=nuc * 0.85, nucleolus=1.0 if stage == "cytokinesis_ii" else 0.0)
                pl.pole(it, nid, (cx + (0.42 if cid == "b" else -0.42), cy * 1.35), angle=0.3 + sister)
                ts = dict(zip(pairs, _territories((cx, cy), 0.28, len(pairs))))
                for k in pairs:
                    parent = homologue_in(cid, k)
                    ch = by[(k, parent, sister)]
                    go = (0.0, 1.0) if sister else (0.0, -1.0)
                    pts = pl.vee(ch, ts[k], go, 0.3)
                    pl.chromatid(it, ch, pl.coil(ch, pts, ts[k], k_coil), 0.75 * w, True)
                if stage == "cytokinesis_ii":
                    it[f"label:{nid}"] = Item("label", ((cx, cy),), 0.47, (), 1.0, f"n = {pl.pairs}")
        frames.append((stage, [it]))
    return frames
