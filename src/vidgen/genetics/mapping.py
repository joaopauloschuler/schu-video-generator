"""Genetic maps (DESIGN.md §96.9): recombination frequency (RF) and map distance in centimorgans
with the map functions, and the analysis of two- and three-point test crosses from offspring
counts — parental and recombinant classes, the phase of the heterozygote (coupling or
repulsion), the gene order from the double crossovers, the interval distances, the expected and
observed double crossovers, the coefficient of coincidence and the interference. Exact where the
data are (:class:`fractions.Fraction`); map distances are floats (logarithms). No manim.

Map functions (Griffiths ch. 4; Hartwell ch. 5):

- ``none``: d = 100 · RF cM — what three-point analyses report; good for short distances
  (below ~10–15 cM), it underestimates longer ones (double crossovers between the loci go
  unseen).
- ``haldane``: d = −½ ln(1 − 2r) M, r = ½ (1 − e^(−2d)) — crossovers independent (no interference).
- ``kosambi``: d = ¼ ln((1 + 2r)/(1 − 2r)) M, r = ½ tanh(2d) — with interference as typically seen.

Loci far apart (d → ∞) have RF → 50 %: they assort independently even on one chromosome."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import product
from typing import Any

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .model import as_fraction

MAP_FUNCTIONS: dict[str, str] = {
    "none": "d = 100 × RF (short distances)",
    "haldane": "Haldane: d = −½ ln(1 − 2r)",
    "kosambi": "Kosambi: d = ¼ ln[(1 + 2r)/(1 − 2r)]",
}
#: The plain RF × 100 conversion stays close to the map functions only for short distances.
SHORT_CM = 15.0


def map_function_key(name: Any, where: str = "map_function") -> str:
    key = str(name).strip().lower()
    key = {"plain": "none", "linear": "none", "rf": "none", "morgan": "none", "off": "none", "false": "none"}.get(key, key)
    if key not in MAP_FUNCTIONS:
        raise VidgenError(f"{where}: '{name}' is not a map function: use {', '.join(MAP_FUNCTIONS)}{did_you_mean(key, list(MAP_FUNCTIONS))}")
    return key


def check_rf(r: Any, where: str = "rf") -> Fraction:
    rf = r if isinstance(r, Fraction) else as_fraction(r, where, "RF")
    if rf < 0 or rf > Fraction(1, 2):
        raise VidgenError(f"{where}: RF {float(rf):.3g} is outside 0–0.5: recombination frequency cannot exceed 50 % (loci far apart "
                          f"assort independently, RF → 0.5); a map distance over 50 cM is a sum of shorter intervals")
    return rf


def rf_to_cm(r: Any, function: str = "none") -> float:
    """The map distance (cM) for a recombination frequency ``r`` (0–0.5): ``none`` 100 r;
    ``haldane`` −50 ln(1 − 2r); ``kosambi`` 25 ln((1 + 2r)/(1 − 2r)); infinite at r = 0.5 for
    the map functions."""
    rf = float(check_rf(r))
    key = map_function_key(function)
    if key == "none":
        return 100.0 * rf
    if rf >= 0.5:
        return math.inf
    if key == "haldane":
        return -50.0 * math.log(1.0 - 2.0 * rf)
    return 25.0 * math.log((1.0 + 2.0 * rf) / (1.0 - 2.0 * rf))


def cm_to_rf(d: float, function: str = "none") -> float:
    """The recombination frequency expected between loci ``d`` cM apart: ``none`` d/100 (at
    most 0.5); ``haldane`` ½(1 − e^(−2d/100)); ``kosambi`` ½ tanh(2d/100)."""
    if d < 0:
        raise VidgenError(f"a map distance is not negative ({d} cM)")
    key = map_function_key(function)
    m = d / 100.0
    if key == "none":
        return min(0.5, m)
    if key == "haldane":
        return 0.5 * (1.0 - math.exp(-2.0 * m))
    return 0.5 * math.tanh(2.0 * m)


def cm_text(d: float) -> str:
    return "∞" if math.isinf(d) else f"{d:.1f} cM"


def percent(f: Fraction | float) -> str:
    return f"{float(f) * 100:.1f} %"


# ----- test-cross classes --------------------------------------------------------------------------


def _locus_name(token: str) -> tuple[str, bool]:
    """``v`` → (v, mutant); ``v+``, ``v^+`` → (v, wild type); ``+`` → ("", wild type)."""
    t = token.strip()
    if t in ("+", "^+"):
        return "", True
    for tail in ("^+", "+"):
        if t.endswith(tail):
            return t[: -len(tail)], True
    return t, False


def class_key(text: Any, loci: Sequence[str], where: str) -> tuple[bool, ...]:
    """The alleles of a class written ``v cv+ ct`` (named: any order) or ``v + ct`` (in the
    order of ``loci``; ``+`` the wild type) as one flag per locus (True: the mutant allele)."""
    tokens = str(text).replace(",", " ").split()
    n = len(loci)
    if len(tokens) != n:
        raise VidgenError(f"{where}: class '{text}' names {len(tokens)} allele(s); write one per locus ({', '.join(loci)}), "
                          f"e.g. '{' '.join(loci)}' or '{' '.join('+' for _ in loci)}' (+ the wild type)")
    parsed = [_locus_name(t) for t in tokens]
    flags: dict[str, bool] = {}
    if all(name in loci or name == "" for name, _ in parsed) and all(name in ("", loci[i]) for i, (name, _) in enumerate(parsed)):
        return tuple(not wild for _, wild in parsed)
    for (name, wild), token in zip(parsed, tokens):
        if name == "":
            raise VidgenError(f"{where}: class '{text}': a bare + is read by position (in the order {', '.join(loci)}); "
                              f"name it ({loci[0]}+) when the order differs")
        if name not in loci:
            raise VidgenError(f"{where}: class '{text}': '{token}' is not one of the loci {', '.join(loci)}{did_you_mean(name, list(loci))}")
        if name in flags:
            raise VidgenError(f"{where}: class '{text}' names {name} twice")
        flags[name] = not wild
    return tuple(flags[x] for x in loci)


def class_text(flags: Sequence[bool], loci: Sequence[str], order: Sequence[int] | None = None) -> str:
    """``v + ct`` in ``order`` (indices into ``loci``)."""
    idx = list(order) if order is not None else list(range(len(loci)))
    return " ".join(loci[i] if flags[i] else "+" for i in idx)


def parse_counts(counts: Any, loci: Sequence[str], where: str = "counts") -> dict[tuple[bool, ...], int]:
    """Offspring counts of a test cross: a mapping class → number, every one of the 2ⁿ classes
    once (0 allowed)."""
    if not isinstance(counts, Mapping):
        raise VidgenError(f"{where}: give the offspring classes and their numbers, e.g. {{'{' '.join(loci)}': 580, …}}")
    out: dict[tuple[bool, ...], int] = {}
    for key, value in counts.items():
        flags = class_key(key, loci, where)
        if flags in out:
            raise VidgenError(f"{where}: class '{class_text(flags, loci)}' is listed twice ('{key}')")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise VidgenError(f"{where}['{key}']: {value!r} is not a count (a whole number ≥ 0)")
        out[flags] = value
    missing = [class_text(f, loci) for f in product((False, True), repeat=len(loci)) if f not in out]
    if missing:
        raise VidgenError(f"{where}: {len(missing)} class(es) missing: {', '.join(repr(m) for m in missing)} — a test cross of "
                          f"{len(loci)} loci has {2 ** len(loci)} classes (write 0 for a class not seen)")
    if sum(out.values()) == 0:
        raise VidgenError(f"{where}: no offspring counted")
    return out


def _flip(flags: tuple[bool, ...]) -> tuple[bool, ...]:
    return tuple(not f for f in flags)


@dataclass(frozen=True)
class ProgenyClass:
    """A class of test-cross offspring: its alleles (one flag per locus, True = mutant), count,
    kind (``parental``, ``single`` — with the interval it recombined in —, ``double``,
    ``recombinant`` for two loci)."""

    flags: tuple[bool, ...]
    count: int
    kind: str
    interval: int | None = None


@dataclass(frozen=True)
class Interval:
    """An interval of the map: the loci at its ends, the recombinants counted in it, RF and
    the distance with the map function."""

    left: str
    right: str
    recombinants: int
    rf: Fraction
    cm: float


@dataclass(frozen=True)
class MapAnalysis:
    """A two- or three-point test cross worked out."""

    loci: tuple[str, ...]
    function: str
    total: int
    classes: tuple[ProgenyClass, ...]
    parental: tuple[tuple[bool, ...], tuple[bool, ...]]
    double: tuple[tuple[bool, ...], tuple[bool, ...]] | None
    order: tuple[int, ...]
    intervals: tuple[Interval, ...]
    outer_rf: Fraction | None = None
    expected_double: Fraction | None = None
    observed_double: int | None = None
    coincidence: Fraction | None = None
    interference: Fraction | None = None

    @property
    def ordered(self) -> tuple[str, ...]:
        return tuple(self.loci[i] for i in self.order)

    @property
    def middle(self) -> str | None:
        return self.loci[self.order[1]] if len(self.order) == 3 else None

    @property
    def phase(self) -> str:
        """``coupling`` (cis: the mutant alleles together on one homologue) or ``repulsion``
        (trans) for two loci; for three, ``coupling`` when all mutant alleles are on one
        homologue, else ``mixed``."""
        a = self.parental[0]
        if all(a) or not any(a):
            return "coupling"
        return "repulsion" if len(a) == 2 else "mixed"

    def haplotypes(self) -> tuple[str, str]:
        """The heterozygous parent's two homologues in map order (``v + +`` / ``+ ct cv``)."""
        return class_text(self.parental[0], self.loci, self.order), class_text(self.parental[1], self.loci, self.order)

    def positions(self) -> dict[str, float]:
        """cM positions along the map, the first locus at 0."""
        out = {self.loci[self.order[0]]: 0.0}
        at = 0.0
        for iv in self.intervals:
            at += iv.cm
            out[iv.right] = at
        return out

    def notes(self) -> list[str]:
        out = []
        if any(iv.rf >= Fraction(2, 5) for iv in self.intervals):
            out.append("RF near 50 %: the loci may not be linked (a chi-square test against 1:1:1:1 decides)")
        if any(iv.cm > SHORT_CM for iv in self.intervals) and self.function == "none":
            out.append(f"an interval over {SHORT_CM:g} cM: RF × 100 underestimates it (unseen double crossovers); "
                       f"a map function (haldane, kosambi) corrects for them")
        return out


def analyse(loci: Sequence[str], counts: Any, function: str = "none", where: str = "counts") -> MapAnalysis:
    """Work out a two- or three-point test cross (the heterozygote × the homozygous recessive
    tester: each offspring class shows the heterozygote's gamete)."""
    loci = tuple(str(x) for x in loci)
    if len(loci) not in (2, 3):
        raise VidgenError(f"loci: a two- or three-point test cross has 2 or 3 loci, not {len(loci)}")
    if len(set(loci)) != len(loci):
        raise VidgenError(f"loci: {', '.join(loci)} names a locus twice")
    for x in loci:
        if not x or "+" in x or " " in x:
            raise VidgenError(f"loci: '{x}': name each locus by its mutant allele's symbol (v, cv, ct); + is the wild type")
    key = map_function_key(function)
    data = parse_counts(counts, loci, where)
    total = sum(data.values())
    pairs = {}
    for f in data:
        rep = min(f, _flip(f))
        pairs[rep] = data[f] + data[_flip(f)]
    ranked = sorted(pairs.items(), key=lambda kv: -kv[1])
    parental_rep, parental_n = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == parental_n:
        raise VidgenError(f"{where}: two reciprocal pairs are equally large ({parental_n} each): the parental classes (the largest "
                          f"pair) cannot be told — are the loci linked?")
    parental = tuple(sorted((parental_rep, _flip(parental_rep)), key=lambda f: -data[f]))
    if len(loci) == 2:
        rec = total - parental_n
        rf = Fraction(rec, total)                 # under 1/2: the parental pair is the larger one
        classes = tuple(ProgenyClass(f, data[f], "parental" if f in parental else "recombinant", 0 if f not in parental else None)
                        for f in sorted(data, key=lambda f: (f not in parental, -data[f])))
        iv = Interval(loci[0], loci[1], rec, rf, rf_to_cm(rf, key))
        return MapAnalysis(loci, key, total, classes, parental, None, (0, 1), (iv,))
    double_rep, double_n = ranked[-1]
    if ranked[-2][1] == double_n:
        raise VidgenError(f"{where}: two reciprocal pairs are equally small ({double_n} each): the double-crossover classes (the "
                          f"smallest pair) cannot be told apart from single crossovers")
    p = parental[0]
    d = double_rep
    diff = [i for i in range(3) if p[i] != d[i]]
    if len(diff) == 2:
        diff = [i for i in range(3) if i not in diff]
    mid = diff[0]
    ends = [i for i in range(3) if i != mid]
    order = (ends[0], mid, ends[1])
    double = tuple(sorted((double_rep, _flip(double_rep)), key=lambda f: -data[f]))

    def recombinant(f: tuple[bool, ...], i: int, j: int) -> bool:
        return (f[i] == f[j]) != (p[i] == p[j])

    intervals = []
    for i, j in ((order[0], order[1]), (order[1], order[2])):
        r = sum(n for f, n in data.items() if recombinant(f, i, j))
        rf = Fraction(r, total)
        if rf >= Fraction(1, 2):
            raise VidgenError(f"{where}: the {loci[i]}–{loci[j]} interval has {percent(rf)} recombinants: an interval of a "
                              f"three-point map is under 50 %")
        intervals.append(Interval(loci[i], loci[j], r, rf, rf_to_cm(rf, key)))
    outer = Fraction(sum(n for f, n in data.items() if recombinant(f, order[0], order[2])), total)
    expected = intervals[0].rf * intervals[1].rf * total
    observed = data[double[0]] + data[double[1]]
    coc = Fraction(observed) / expected if expected else None
    interference = 1 - coc if coc is not None else None

    def kind(f: tuple[bool, ...]) -> tuple[str, int | None]:
        if f in parental:
            return "parental", None
        if f in double:
            return "double", None
        return "single", (0 if recombinant(f, order[0], order[1]) else 1)

    groups = {"parental": 0, "single": 1, "double": 3}
    classes = []
    for f in sorted(data, key=lambda f: (groups[kind(f)[0]] + (kind(f)[1] or 0), -data[f])):
        k, interval = kind(f)
        classes.append(ProgenyClass(f, data[f], k, interval))
    return MapAnalysis(loci, key, total, tuple(classes), parental, double, order, tuple(intervals), outer, expected, observed, coc,
                       interference)


# ----- maps from positions ---------------------------------------------------------------------------


def parse_positions(value: Any, where: str = "map") -> dict[str, float]:
    """Loci and their positions in cM (``{y: 0, w: 1.5, v: 33}``), in map order."""
    if not isinstance(value, Mapping) or len(value) < 2:
        raise VidgenError(f"{where}: give at least two loci with their positions in cM, e.g. {{y: 0, w: 1.5, v: 33}}")
    out: dict[str, float] = {}
    for name, at in value.items():
        if isinstance(at, bool) or not isinstance(at, (int, float)):
            raise VidgenError(f"{where}.{name}: {at!r} is not a position in cM")
        if at < 0:
            raise VidgenError(f"{where}.{name}: positions are cM from the map's first locus (0 or more)")
        out[str(name)] = float(at)
    ordered = dict(sorted(out.items(), key=lambda kv: kv[1]))
    names = list(ordered)
    for a, b in zip(names, names[1:]):
        if ordered[a] == ordered[b]:
            raise VidgenError(f"{where}: {a} and {b} are both at {ordered[a]:g} cM: loci without recombination between them are not "
                              f"resolved on a genetic map")
    return ordered


def interval_between(positions: Mapping[str, float], a: str, b: str, function: str, where: str = "measure") -> tuple[float, float]:
    """The distance (cM) and the RF expected with ``function`` between two loci of a map."""
    for x in (a, b):
        if x not in positions:
            raise VidgenError(f"{where}: '{x}' is not a locus of the map ({', '.join(positions)}){did_you_mean(x, list(positions))}")
    if a == b:
        raise VidgenError(f"{where}: name two different loci ({a}-{b})")
    d = abs(positions[a] - positions[b])
    return d, cm_to_rf(d, function)


# ----- the linkage_map scene's plan ---------------------------------------------------------------------

PLAN_KEYS = ("loci", "counts", "map", "map_function", "phase", "crossover")


@dataclass(frozen=True)
class LinkagePlan:
    """What a ``linkage_map`` scene shows: ``mode`` (``counts``: a test cross worked out;
    ``map``: loci at given positions), the loci (as given), the analysis, the map order (indices
    into ``loci``), the cM positions, the heterozygote's two homologues (a flag per locus, True =
    mutant allele, in the given order), the map function, the crossovers drawn (interval indices
    in map order: 0 between the first two loci) and notes."""

    mode: str
    loci: tuple[str, ...]
    analysis: MapAnalysis | None
    order: tuple[int, ...]
    positions: dict[str, float]
    homologues: tuple[tuple[bool, ...], tuple[bool, ...]]
    function: str
    crossovers: tuple[int, ...]
    notes: tuple[str, ...] = ()

    @property
    def ordered(self) -> tuple[str, ...]:
        return tuple(self.loci[i] for i in self.order)

    def interval_names(self) -> list[str]:
        names = self.ordered
        return [f"{a}-{b}" for k, a in enumerate(names) for b in names[k + 1:]]


def _interval(text: str, plan_names: Sequence[str], where: str) -> tuple[str, str]:
    parts = [x.strip() for x in str(text).replace("–", "-").split("-")]
    if len(parts) != 2 or not all(parts):
        raise VidgenError(f"{where}: '{text}': name an interval by its two loci, e.g. {plan_names[0]}-{plan_names[1]}")
    for x in parts:
        if x not in plan_names:
            raise VidgenError(f"{where}: '{x}' is not a locus ({', '.join(plan_names)}){did_you_mean(x, list(plan_names))}")
    if parts[0] == parts[1]:
        raise VidgenError(f"{where}: '{text}' names one locus twice")
    return parts[0], parts[1]


def crossover_index(text: str, ordered: Sequence[str], where: str = "crossover") -> int:
    """The interval index (in map order) a ``v-ct`` names; the loci must be neighbours."""
    a, b = _interval(text, ordered, where)
    i, j = sorted((ordered.index(a), ordered.index(b)))
    if j != i + 1:
        raise VidgenError(f"{where}: {a} and {b} are not neighbours on the map ({' – '.join(ordered)}): a crossover is drawn in "
                          f"an interval between neighbouring loci")
    return i


def build_linkage_plan(data: Mapping[str, Any]) -> LinkagePlan:
    """Check a ``linkage_map`` scene's params and work out what it shows."""
    function = map_function_key(data.get("map_function", "none"))
    counts, positions_in, loci_in = data.get("counts"), data.get("map"), data.get("loci")
    if (counts is None) == (positions_in is None):
        raise VidgenError("linkage_map: give counts (a test cross to work out, with loci) or map (loci at their positions in cM), "
                          "one of them")
    notes: list[str] = []
    if counts is not None:
        if not loci_in:
            raise VidgenError("counts: name the loci first (loci: [v, cv, ct]: the mutant alleles' symbols, in any order)")
        if "phase" in data and data["phase"] is not None:
            raise VidgenError("phase: the counts show the phase (the parental classes); phase belongs to map:")
        analysis = analyse(loci_in, counts, function)
        loci = analysis.loci
        order = analysis.order
        positions = analysis.positions()
        homologues = analysis.parental
        notes += analysis.notes()
        mode = "counts"
    else:
        if loci_in:
            raise VidgenError("loci: with map: the map names the loci ({y: 0, w: 1.5, v: 33}); leave loci out")
        positions = parse_positions(positions_in)
        loci = tuple(positions)
        analysis = None
        order = tuple(range(len(loci)))
        phase = data.get("phase") or "coupling"
        if phase not in ("coupling", "repulsion"):
            raise VidgenError(f"phase: '{phase}': coupling (the mutant alleles on one homologue) or repulsion (alternating)")
        bottom = tuple(True for _ in loci) if phase == "coupling" else tuple(k % 2 == 0 for k in range(len(loci)))
        homologues = (tuple(not f for f in bottom), bottom)
        mode = "map"
        if function == "none" and len(loci) > 1 and positions[loci[-1]] - positions[loci[0]] > 50:
            notes.append("loci over 50 cM apart: their RF is 50 % (independent assortment); give map_function for RF from distance")
    ordered = tuple(loci[i] for i in order)
    raw = data.get("crossover", "auto")
    if raw is None or raw == "auto":
        crossovers: tuple[int, ...] = (0,)
    elif raw in ("none", False) or raw == []:
        crossovers = ()
    elif raw == "double":
        if len(ordered) < 3:
            raise VidgenError("crossover: double needs three loci (a crossover in each interval)")
        crossovers = (0, 1)
    else:
        items = [raw] if isinstance(raw, str) else list(raw)
        crossovers = tuple(sorted({crossover_index(str(x), ordered) for x in items}))
    return LinkagePlan(mode, loci, analysis, order, positions, homologues, function, crossovers, tuple(notes))


@lru_cache(maxsize=32)
def _cached(key: str) -> LinkagePlan:
    return build_linkage_plan(json.loads(key))


def plan_linkage(data: Mapping[str, Any]) -> LinkagePlan:
    """:func:`build_linkage_plan`, cached by the params' JSON (validation and the scene share it)."""
    return _cached(json.dumps({k: data[k] for k in PLAN_KEYS if k in data}, default=str))


def measure_interval(plan: LinkagePlan, text: str, where: str = "measure") -> tuple[str, str, float, float]:
    """``(a, b, cM, RF)`` for a ``v-ct`` of the plan's map (RF from the map function)."""
    a, b = _interval(text, plan.ordered, where)
    d, rf = interval_between(plan.positions, a, b, plan.function, where)
    return a, b, d, rf
