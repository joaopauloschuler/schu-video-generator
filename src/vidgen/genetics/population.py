"""Population genetics (DESIGN.md §96.16): Hardy–Weinberg worked with exact numbers and seeded
Wright–Fisher simulations — drift, selection, mutation, migration between two populations, a
bottleneck and a founder event — for the ``population`` scene. No manim.

- **Hardy–Weinberg** (:func:`hardy_weinberg`): the allele frequencies p, q from genotype counts,
  genotype frequencies, p itself or the incidence of a recessive condition (q² = incidence); the
  expected genotype frequencies p², 2pq, q² (with an inbreeding coefficient F: p² + Fpq,
  2pq(1 − F), q² + Fpq); the carrier frequency 2pq; and from counts a chi-square test of HWE with
  df = 1 (three genotype classes − 1 − one allele frequency estimated from the data). Exact
  fractions wherever the inputs are (q = √incidence is exact when both terms are squares:
  1/2500 → q = 1/50).
- **Wright–Fisher** (:func:`simulate`): N diploids, 2N gene copies; each generation the
  expected frequency after selection (fitnesses w_AA, w_Aa, w_aa), mutation (μ: A → a, ν: a → A)
  and migration (m) is sampled binomially, 2N copies. ``numpy.random.default_rng(seed)``: the same
  seed gives the same lines. The deterministic recursion is the same steps without sampling.
  Expected heterozygosity under drift alone: H_t = H_0 · Π(1 − 1/2N_t)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from typing import Any, Mapping

import numpy as np

from vidgen.cellworld.model import did_you_mean
from vidgen.errors import VidgenError

from .model import as_fraction
from .stats import chi_square_p, critical_value, SMALL_EXPECTED

#: The models of a ``population`` scene.
MODELS = ("hardy_weinberg", "drift", "selection", "mutation", "migration", "bottleneck", "founder")
#: Params of each model (beyond model, alleles, seed).
MODEL_KEYS: dict[str, tuple[str, ...]] = {
    "hardy_weinberg": ("counts", "frequencies", "p", "incidence", "inbreeding", "total", "condition"),
    "drift": ("N", "p0", "generations", "replicates", "mu", "nu"),
    "selection": ("N", "p0", "generations", "replicates", "fitness", "s", "h", "mu", "nu"),
    "mutation": ("N", "p0", "generations", "replicates", "mu", "nu"),
    "migration": ("N", "populations", "m", "direction", "generations", "replicates"),
    "bottleneck": ("N", "p0", "generations", "replicates", "bottleneck"),
    "founder": ("N", "p0", "generations", "replicates", "founders"),
}
#: Limits of a simulation (what a scene can draw).
MAX_N, MAX_GENERATIONS, MAX_REPLICATES = 1_000_000, 2000, 20
#: Dots drawn for a population.
DOTS = 100


# ----- numbers ------------------------------------------------------------------------------------


Number = Fraction | float


def frac_text(x: Number) -> str:
    """``49/1250`` for a fraction, the decimal for a float."""
    if isinstance(x, Fraction):
        return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    return dec(x)


def dec(x: Number, digits: int = 4) -> str:
    """A decimal with ``digits`` significant digits (``0.0392``, ``0.96``, ``1``)."""
    v = float(x)
    if v == 0:
        return "0"
    if abs(v) >= 1 and float(v).is_integer():
        return str(int(v))
    places = max(0, digits - 1 - math.floor(math.log10(abs(v))))
    text = f"{v:.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def one_in(x: Number) -> str:
    """``1 in 25.5`` (one decimal below 100, whole numbers above)."""
    v = float(x)
    if v <= 0:
        return "none"
    n = 1 / v
    return f"1 in {n:.1f}".replace(".0", "") if n < 100 else f"1 in {round(n):,}".replace(",", " ")


def exact_sqrt(x: Fraction) -> Number:
    """√x, exact when the numerator and denominator are squares, else a float."""
    a, b = math.isqrt(x.numerator), math.isqrt(x.denominator)
    if a * a == x.numerator and b * b == x.denominator:
        return Fraction(a, b)
    return math.sqrt(float(x))


def _share(value: Any, where: str, what: str) -> Fraction:
    f = as_fraction(value, where, what)
    if not 0 <= f <= 1:
        raise VidgenError(f"{where}: {what} {frac_text(f)} is outside [0, 1]: a frequency is a share between 0 and 1")
    return f


# ----- genotypes ----------------------------------------------------------------------------------


def allele_symbols(value: Any, where: str = "alleles") -> tuple[str, str]:
    """The two allele symbols (``[A, a]`` by default); one or two characters each, different."""
    if value is None:
        return ("A", "a")
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise VidgenError(f"{where}: give two alleles, e.g. [A, a] (the first is the one whose frequency is p)")
    a, b = (str(v).strip() for v in value)
    if not a or not b or a == b or len(a) > 3 or len(b) > 3:
        raise VidgenError(f"{where}: two different short allele symbols, e.g. [A, a] or [B, b], not {list(value)}")
    return (a, b)


def genotype_names(alleles: tuple[str, str]) -> tuple[str, str, str]:
    """``AA``, ``Aa``, ``aa`` (``A1A1`` …): the homozygote of p, the heterozygote, the other."""
    a, b = alleles
    return (a + a, a + b, b + b)


def genotype_index(key: Any, alleles: tuple[str, str], where: str) -> int:
    """0, 1 or 2 copies of the second allele for ``AA`` / ``Aa`` (``aA``, ``A/a``) / ``aa``."""
    text = str(key).replace("/", "").replace(" ", "")
    a, b = alleles
    for i, name in enumerate(genotype_names(alleles)):
        if text == name or (i == 1 and text == b + a):
            return i
    names = list(genotype_names(alleles))
    raise VidgenError(f"{where}: '{key}' is not a genotype of the alleles {a} and {b}: use {', '.join(names)}{did_you_mean(text, names)}")


def _genotype_map(value: Any, alleles: tuple[str, str], where: str, what: str) -> dict[int, Any]:
    if not isinstance(value, Mapping):
        names = genotype_names(alleles)
        raise VidgenError(f"{where}: {what} is a mapping of the three genotypes, e.g. {{{names[0]}: 360, {names[1]}: 480, {names[2]}: 160}}")
    out: dict[int, Any] = {}
    for key, v in value.items():
        i = genotype_index(key, alleles, where)
        if i in out:
            raise VidgenError(f"{where}: genotype {genotype_names(alleles)[i]} is given twice")
        out[i] = v
    missing = [genotype_names(alleles)[i] for i in range(3) if i not in out]
    if missing:
        raise VidgenError(f"{where}: {what} needs all three genotypes; missing {', '.join(missing)} (write 0 for none)")
    return out


# ----- Hardy–Weinberg -----------------------------------------------------------------------------


@dataclass(frozen=True)
class HweTest:
    """Chi-square test of Hardy–Weinberg proportions from genotype counts: observed and exact
    expected counts, the contributions, χ² (exact), df = 1, the p-value, the critical value at
    α = 0.05, whether HWE is rejected, the genotypes with an expected count below 5."""

    observed: tuple[int, int, int]
    expected: tuple[Fraction, Fraction, Fraction]
    contributions: tuple[Fraction, Fraction, Fraction]
    statistic: Fraction
    df: int
    p_value: float
    critical: float
    rejected: bool
    small: tuple[str, ...]


@dataclass(frozen=True)
class HardyWeinberg:
    """A worked Hardy–Weinberg example. ``source``: ``counts``, ``frequencies``, ``p`` or
    ``incidence``; ``p``, ``q`` the allele frequencies (exact fractions, or floats when q = √
    incidence is not exact); ``expected`` the genotype frequencies (with ``inbreeding`` F);
    ``carrier`` = the heterozygote frequency; ``test`` from counts; ``f_hat`` = 1 − H_obs/H_exp."""

    alleles: tuple[str, str]
    source: str
    p: Number
    q: Number
    expected: tuple[Number, Number, Number]
    inbreeding: Fraction
    counts: tuple[int, int, int] | None = None
    observed_freq: tuple[Fraction, Fraction, Fraction] | None = None
    incidence: Fraction | None = None
    condition: str = ""
    test: HweTest | None = None
    f_hat: Fraction | None = None
    notes: tuple[str, ...] = ()

    @property
    def genotypes(self) -> tuple[str, str, str]:
        return genotype_names(self.alleles)

    @property
    def total(self) -> int | None:
        return sum(self.counts) if self.counts is not None else None

    @property
    def carrier(self) -> Number:
        return self.expected[1]

    @property
    def exact(self) -> bool:
        return isinstance(self.q, Fraction)


def hardy_weinberg(spec: Mapping[str, Any], where: str = "params") -> HardyWeinberg:
    """Work out Hardy–Weinberg from one of ``counts``, ``frequencies``, ``p`` or ``incidence``."""
    alleles = allele_symbols(spec.get("alleles"), f"{where}.alleles")
    names = genotype_names(alleles)
    given = [k for k in ("counts", "frequencies", "p", "incidence") if spec.get(k) is not None]
    if len(given) != 1:
        raise VidgenError(f"{where}: give one of counts (genotype counts), frequencies (genotype frequencies), p (the allele "
                          f"frequency of {alleles[0]}) or incidence (of the recessive condition, q² = incidence)"
                          + (f"; got {', '.join(given)}" if given else ""))
    source = given[0]
    F = _share(spec.get("inbreeding", 0), f"{where}.inbreeding", "the inbreeding coefficient F")
    counts = observed = incidence = None
    if source == "counts":
        raw = _genotype_map(spec["counts"], alleles, f"{where}.counts", "counts")
        vals = []
        for i in range(3):
            v = raw[i]
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise VidgenError(f"{where}.counts.{names[i]}: '{v}' is not a count (a whole number ≥ 0)")
            vals.append(v)
        counts = (vals[0], vals[1], vals[2])
        n = sum(counts)
        if n == 0:
            raise VidgenError(f"{where}.counts: the counts add up to 0: give how many individuals have each genotype")
        if spec.get("total") is not None and int(spec["total"]) != n:
            raise VidgenError(f"{where}.counts: {counts[0]} + {counts[1]} + {counts[2]} = {n}, not the total {spec['total']} given; "
                              f"fix the counts or the total")
        p: Number = Fraction(2 * counts[0] + counts[1], 2 * n)
        observed = tuple(Fraction(c, n) for c in counts)
    elif source == "frequencies":
        raw = _genotype_map(spec["frequencies"], alleles, f"{where}.frequencies", "frequencies")
        freqs = [_share(raw[i], f"{where}.frequencies.{names[i]}", f"the frequency of {names[i]}") for i in range(3)]
        if sum(freqs) != 1:
            raise VidgenError(f"{where}.frequencies: {' + '.join(frac_text(f) for f in freqs)} = {frac_text(sum(freqs, Fraction(0)))}; "
                              f"genotype frequencies must add up to 1")
        p = freqs[0] + freqs[1] / 2
        observed = (freqs[0], freqs[1], freqs[2])
    elif source == "p":
        p = _share(spec["p"], f"{where}.p", f"p (the frequency of {alleles[0]})")
    else:
        incidence = _share(spec["incidence"], f"{where}.incidence", "the incidence")
        if incidence == 0 or incidence == 1:
            raise VidgenError(f"{where}.incidence: {frac_text(incidence)}: an incidence between 0 and 1 (e.g. 1/2500)")
        if F:
            raise VidgenError(f"{where}: incidence with inbreeding: q² = incidence holds only under random mating (F = 0); give p instead")
        q0 = exact_sqrt(incidence)
        p = (1 - q0) if isinstance(q0, Fraction) else 1.0 - q0
    q: Number = (1 - p) if isinstance(p, Fraction) else 1.0 - p
    pq = p * q
    expected: tuple[Number, Number, Number] = (p * p + F * pq, 2 * pq * (1 - F), q * q + F * pq)
    test = f_hat = None
    notes: list[str] = []
    if counts is not None:
        test = hwe_test(counts, names)
        h_exp = 2 * Fraction(p) * Fraction(q)
        if h_exp:
            f_hat = 1 - Fraction(counts[1], sum(counts)) / h_exp
    if observed is not None and source == "frequencies":
        h_exp = 2 * Fraction(p) * Fraction(q)
        if h_exp:
            f_hat = 1 - observed[1] / h_exp
    if incidence is not None:
        notes.append(f"for a rare allele 2pq ≈ 2q = {dec(2 * float(q))} ({one_in(2 * float(q))})")
    return HardyWeinberg(alleles, source, p, q, expected, F, counts, observed, incidence, str(spec.get("condition") or ""),
                         test, f_hat, tuple(notes))


def hwe_test(counts: tuple[int, int, int], names: tuple[str, str, str] = ("AA", "Aa", "aa")) -> HweTest:
    """χ² of the genotype counts against p², 2pq, q² with p from the same counts: df = 1."""
    n = sum(counts)
    p = Fraction(2 * counts[0] + counts[1], 2 * n)
    q = 1 - p
    expected = (n * p * p, 2 * n * p * q, n * q * q)
    if any(e == 0 for e in expected):
        raise VidgenError("counts: one allele is absent, so the test of Hardy–Weinberg proportions is undefined (every expected count must be > 0)")
    contributions = tuple((o - e) ** 2 / e for o, e in zip(counts, expected))
    stat = sum(contributions, Fraction(0))
    pv = chi_square_p(float(stat), 1)
    return HweTest(counts, expected, contributions, stat, 1, pv, critical_value(1, 0.05), pv < 0.05,  # type: ignore[arg-type]
                   tuple(names[i] for i, e in enumerate(expected) if e < SMALL_EXPECTED))


def sample_genotypes(freqs: tuple[float, float, float], count: int, seed: int) -> list[int]:
    """``count`` individuals' genotypes (0, 1, 2 copies of the second allele) drawn from the
    genotype frequencies, seeded."""
    rng = np.random.default_rng(seed)
    probs = np.array([max(0.0, float(f)) for f in freqs])
    probs = probs / probs.sum()
    return [int(x) for x in rng.choice(3, size=count, p=probs)]


def proportional_dots(counts: tuple[Number, Number, Number], total: int = DOTS, seed: int = 1) -> list[int]:
    """``total`` dots in proportion to ``counts`` (largest remainders), shuffled with ``seed``."""
    s = float(sum(counts))
    raw = [float(c) / s * total for c in counts]
    whole = [math.floor(r) for r in raw]
    order = sorted(range(3), key=lambda i: raw[i] - whole[i], reverse=True)
    for i in order[: total - sum(whole)]:
        whole[i] += 1
    dots = [g for g in range(3) for _ in range(whole[g])]
    np.random.default_rng(seed).shuffle(dots)
    return dots


# ----- Wright–Fisher -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """One simulated line: its population (0 or 1 for migration), replicate, the allele
    frequency p of each generation 0…T, and the generation it fixed (p = 1) or was lost (p = 0)."""

    population: int
    replicate: int
    values: tuple[float, ...]
    fixed_at: int | None = None
    lost_at: int | None = None


@dataclass(frozen=True)
class Simulation:
    """A seeded simulation: ``sizes[t]`` the number of diploids of generation t, ``lines`` the
    stochastic lines (none without N), ``deterministic`` one curve per population (the recursion
    without drift; ``None`` for drift alone, where it is flat at p₀), the expected heterozygosity
    under drift (``h_expected``) and the replicates' mean 2pq (``h_mean``)."""

    model: str
    alleles: tuple[str, str]
    generations: int
    sizes: tuple[int, ...] | None      # [0] is the founders in a founder model
    lines: tuple[Line, ...]
    deterministic: tuple[tuple[float, ...], ...] | None
    populations: tuple[str, ...]
    p0: tuple[float, ...]
    fitness: tuple[float, float, float] | None = None
    mu: float = 0.0
    nu: float = 0.0
    m: float = 0.0
    direction: str = "both"
    bottleneck: tuple[int, int, int] | None = None      # (at, N, generations)
    founders: int | None = None
    source_p: float | None = None
    h_expected: tuple[float, ...] = ()
    h_mean: tuple[float, ...] = ()
    seed: int = 1
    notes: tuple[str, ...] = field(default=())

    @property
    def N(self) -> int | None:
        return self.sizes[-1] if self.sizes else None

    def fixed(self) -> list[int]:
        return [i for i, line in enumerate(self.lines) if line.fixed_at is not None]

    def lost(self) -> list[int]:
        return [i for i, line in enumerate(self.lines) if line.lost_at is not None]

    def individuals(self, generation: int, count: int = DOTS) -> list[int]:
        """Genotypes (copies of the second allele) of up to ``count`` individuals of the first
        line at ``generation``: its 2N gene copies paired at random (seeded), so the dots carry
        exactly that generation's allele count."""
        if not self.lines or self.sizes is None:
            p = self.deterministic[0][generation] if self.deterministic else self.p0[0]
            q = 1 - p
            return sample_genotypes((p * p, 2 * p * q, q * q), count, self.seed * 7919 + generation)
        n = self.sizes[generation]
        k = round(self.lines[0].values[generation] * 2 * n)
        copies = np.array([0] * k + [1] * (2 * n - k))     # 1 = a copy of the second allele
        rng = np.random.default_rng(self.seed * 7919 + generation)
        rng.shuffle(copies)
        pairs = copies.reshape(n, 2).sum(axis=1)
        return [int(x) for x in pairs[: min(count, n)]]


def _fitness(spec: Mapping[str, Any], alleles: tuple[str, str], where: str) -> tuple[float, float, float]:
    names = genotype_names(alleles)
    if spec.get("fitness") is not None:
        if spec.get("s") is not None or spec.get("h") is not None:
            raise VidgenError(f"{where}: give fitness (w for each genotype) or s and h, not both")
        raw = _genotype_map(spec["fitness"], alleles, f"{where}.fitness", "fitness")
        w = []
        for i in range(3):
            try:
                v = float(raw[i])
            except (TypeError, ValueError):
                raise VidgenError(f"{where}.fitness.{names[i]}: '{raw[i]}' is not a number") from None
            if v < 0:
                raise VidgenError(f"{where}.fitness.{names[i]}: {v:g} is negative; a fitness is a relative survival and fertility ≥ 0")
            w.append(v)
        if max(w) == 0:
            raise VidgenError(f"{where}.fitness: every genotype has fitness 0: nobody would reproduce")
        return (w[0], w[1], w[2])
    if spec.get("s") is None:
        raise VidgenError(f"{where}: selection needs fitness ({{{names[0]}: 1, {names[1]}: 1, {names[2]}: 0.8}}) or s (and h)")
    s = float(as_fraction(spec["s"], f"{where}.s", "s"))
    h = float(as_fraction(spec.get("h", Fraction(1, 2)), f"{where}.h", "h"))
    if not -1 <= s <= 1:
        raise VidgenError(f"{where}.s: {s:g}: the selection coefficient lies in [−1, 1] (w_{names[2]} = 1 − s must not be negative)")
    w = (1.0, 1.0 - h * s, 1.0 - s)
    if w[1] < 0:
        raise VidgenError(f"{where}: h = {h:g} and s = {s:g} give w_{names[1]} = 1 − hs = {w[1]:g}, a negative fitness")
    return w


def _rate(spec: Mapping[str, Any], key: str, where: str, what: str) -> float:
    if spec.get(key) is None:
        return 0.0
    v = float(as_fraction(spec[key], f"{where}.{key}", what))
    if not 0 <= v <= 1:
        raise VidgenError(f"{where}.{key}: {v:g} is outside [0, 1]: {what} is a probability per generation")
    return v


def step(p: float, w: tuple[float, float, float] | None, mu: float, nu: float) -> float:
    """One generation's expected frequency of the first allele: selection, then mutation."""
    q = 1.0 - p
    if w is not None:
        mean = p * p * w[0] + 2 * p * q * w[1] + q * q * w[2]
        p = (p * p * w[0] + p * q * w[1]) / mean if mean > 0 else p
    if mu or nu:
        p = p * (1 - mu) + (1 - p) * nu
    return min(1.0, max(0.0, p))


def _int(spec: Mapping[str, Any], key: str, where: str, lo: int, hi: int, default: int | None = None) -> int:
    v = spec.get(key, default)
    if v is None:
        raise VidgenError(f"{where}: {key} is needed")
    if isinstance(v, bool) or not isinstance(v, int):
        try:
            v = int(str(v))
        except ValueError:
            raise VidgenError(f"{where}.{key}: '{v}' is not a whole number") from None
    if not lo <= v <= hi:
        raise VidgenError(f"{where}.{key}: {v} is outside {lo}–{hi}")
    return v


def simulate(spec: Mapping[str, Any], where: str = "params") -> Simulation:
    """A seeded Wright–Fisher simulation (or the deterministic recursion without ``N``)."""
    model = spec["model"]
    alleles = allele_symbols(spec.get("alleles"), f"{where}.alleles")
    seed = int(spec.get("seed", 1))
    T = _int(spec, "generations", where, 1, MAX_GENERATIONS, 100)
    has_n = spec.get("N") is not None
    if model in ("drift", "bottleneck", "founder") and not has_n:
        raise VidgenError(f"{where}: model: {model} needs N (the population size: diploid individuals, 2N gene copies)")
    N = _int(spec, "N", where, 2, MAX_N) if has_n else None
    R = _int(spec, "replicates", where, 1, MAX_REPLICATES, 6 if has_n else 1) if has_n else 1
    if not has_n and spec.get("replicates") not in (None, 1):
        raise VidgenError(f"{where}: replicates need N (without N the deterministic recursion is drawn: one curve)")
    w = _fitness(spec, alleles, where) if model == "selection" else None
    mu = _rate(spec, "mu", where, "μ (mutation rate)")
    nu = _rate(spec, "nu", where, "ν (back-mutation rate)")
    if model == "mutation" and not (mu or nu):
        raise VidgenError(f"{where}: model: mutation needs mu (the rate {alleles[0]} → {alleles[1]} per copy per generation) and/or nu")
    m = 0.0
    direction = "both"
    names = ("population",)
    if model == "migration":
        pops = spec.get("populations")
        if not isinstance(pops, list) or len(pops) != 2:
            raise VidgenError(f"{where}.populations: two populations, e.g. [{{name: mainland, p0: 0.9}}, {{name: island, p0: 0.1}}]")
        names_l, p0s = [], []
        for k, pop in enumerate(pops):
            pw = f"{where}.populations[{k}]"
            if isinstance(pop, Mapping):
                bad = [x for x in pop if x not in ("name", "p0")]
                if bad:
                    raise VidgenError(f"{pw}: unknown key '{bad[0]}': use name, p0{did_you_mean(str(bad[0]), ['name', 'p0'])}")
                if pop.get("p0") is None:
                    raise VidgenError(f"{pw}: p0 (its starting frequency of {alleles[0]}) is needed")
                names_l.append(str(pop.get("name") or ("population 1", "population 2")[k]))
                p0s.append(float(_share(pop["p0"], pw + ".p0", "p0")))
            else:
                names_l.append(("population 1", "population 2")[k])
                p0s.append(float(_share(pop, pw, "p0")))
        names = tuple(names_l)
        p0 = tuple(p0s)
        if spec.get("m") is None:
            raise VidgenError(f"{where}: model: migration needs m (the share of each generation's parents that are migrants)")
        m = _rate(spec, "m", where, "m (the migration rate)")
        direction = str(spec.get("direction") or "both")
        if direction not in ("both", "one_way"):
            raise VidgenError(f"{where}.direction: '{direction}': both (the populations exchange migrants) or one_way "
                              f"(migrants from the first to the second only: continent → island){did_you_mean(direction, ['both', 'one_way'])}")
    else:
        if spec.get("p0") is None:
            raise VidgenError(f"{where}: p0 (the starting frequency of {alleles[0]}) is needed")
        p0 = (float(_share(spec["p0"], f"{where}.p0", "p0")),)
    sizes: list[int] | None = None
    bottle = None
    founders = None
    if N is not None:
        sizes = [N] * (T + 1)
        if model == "bottleneck":
            b = spec.get("bottleneck")
            if not isinstance(b, Mapping):
                raise VidgenError(f"{where}.bottleneck: {{at: 20, N: 10, generations: 5}} (when it starts, its size, how long)")
            bad = [x for x in b if x not in ("at", "N", "generations")]
            if bad:
                raise VidgenError(f"{where}.bottleneck: unknown key '{bad[0]}': use at, N, generations{did_you_mean(str(bad[0]), ['at', 'N', 'generations'])}")
            at = _int(b, "at", f"{where}.bottleneck", 1, T)
            nb = _int(b, "N", f"{where}.bottleneck", 1, MAX_N)
            dur = _int(b, "generations", f"{where}.bottleneck", 1, T, 1)
            if nb >= N:
                raise VidgenError(f"{where}.bottleneck.N: {nb} is not smaller than N = {N}: a bottleneck is a drop in size")
            for t in range(at, min(T, at + dur - 1) + 1):
                sizes[t] = nb
            bottle = (at, nb, dur)
        if model == "founder":
            founders = _int(spec, "founders", where, 1, MAX_N)
            if founders >= N:
                raise VidgenError(f"{where}.founders: {founders} is not smaller than N = {N}: the founders are a few individuals of the source")
            sizes[0] = founders
    rng = np.random.default_rng(seed)
    pops = len(p0)

    def advance(ps: list[float]) -> list[float]:
        exp = [step(x, w, mu, nu) for x in ps]
        if pops == 2 and m:
            a, b = exp
            exp = [a if direction == "one_way" else (1 - m) * a + m * b, (1 - m) * b + m * a]
        return exp

    deterministic = None
    if model in ("selection", "mutation", "migration") or mu or nu:
        curves = [[x] for x in p0]
        cur = list(p0)
        for _ in range(T):
            cur = advance(cur)
            for k in range(pops):
                curves[k].append(cur[k])
        deterministic = tuple(tuple(c) for c in curves)
    lines: list[Line] = []
    if sizes is not None:
        runs: list[list[list[float]]] = []
        for r in range(R):
            if model == "founder":
                start = [rng.binomial(2 * sizes[0], p0[0]) / (2 * sizes[0])]
            else:
                start = list(p0)
            runs.append([[x] for x in start])
        for t in range(1, T + 1):
            n2 = 2 * sizes[t]
            for r in range(R):
                cur = [runs[r][k][-1] for k in range(pops)]
                exp = advance(cur)
                for k in range(pops):
                    runs[r][k].append(float(rng.binomial(n2, exp[k])) / n2)
        for r in range(R):
            for k in range(pops):
                vals = tuple(runs[r][k])
                fixed = next((t for t, v in enumerate(vals) if v >= 1.0), None)
                lost = next((t for t, v in enumerate(vals) if v <= 0.0), None)
                if fixed is not None and any(v < 1.0 for v in vals[fixed:]):
                    fixed = None                  # mutation or migration brought the other allele back
                if lost is not None and any(v > 0.0 for v in vals[lost:]):
                    lost = None
                lines.append(Line(k, r, vals, fixed, lost))
    h_expected: tuple[float, ...] = ()
    h_mean: tuple[float, ...] = ()
    source_p = None
    if sizes is not None and model in ("drift", "bottleneck", "founder") and not (mu or nu):
        h = 2 * p0[0] * (1 - p0[0])
        hs = []
        for t in range(T + 1):
            if t > 0 or model == "founder":
                h *= 1 - 1 / (2 * sizes[t])
            hs.append(h)
        h_expected = tuple(hs)
        h_mean = tuple(float(np.mean([2 * line.values[t] * (1 - line.values[t]) for line in lines])) for t in range(T + 1))
        if model == "founder":
            source_p = p0[0]
    sim = Simulation(model, alleles, T, tuple(sizes) if sizes else None, tuple(lines), deterministic, names, p0, w, mu, nu, m,
                     direction, bottle, founders, source_p, h_expected, h_mean, seed)
    return _with_notes(sim)


def _with_notes(sim: Simulation) -> Simulation:
    """The card's facts for the model."""
    a, b = sim.alleles
    notes: list[str] = []
    N = sim.N
    if sim.model == "drift":
        notes.append(f"drift alone: the chance that {a} is eventually fixed is its starting frequency, p₀ = {dec(sim.p0[0])}")
        notes.append(f"heterozygosity falls by 1/2N per generation: H_t = H₀ (1 − 1/2N)^t, here 1/{2 * N} per generation")
    elif sim.model == "selection" and sim.fitness is not None:
        w = sim.fitness
        best = max(range(3), key=lambda i: w[i])
        notes.append("fitnesses " + ", ".join(f"w({g}) = {dec(x)}" for g, x in zip(genotype_names(sim.alleles), w)))
        if w[1] > max(w[0], w[2]):
            s, t = 1 - w[0] / w[1], 1 - w[2] / w[1]
            notes.append(f"heterozygote advantage: a stable polymorphism at p̂ = t/(s + t) = {dec(t / (s + t))}")
        elif w[1] < min(w[0], w[2]):
            notes.append("heterozygote disadvantage: an unstable equilibrium; the population goes to whichever allele is ahead")
        else:
            notes.append(f"{genotype_names(sim.alleles)[best]} is fittest: {a if best == 0 else b} rises towards fixation")
        if N is not None:
            s_eff = abs(w[0] - w[2]) / max(w)
            if s_eff and 2 * N * s_eff < 1:
                notes.append(f"2Ns = {2 * N * s_eff:.2g} < 1: drift outweighs selection here (selection dominates when 2Ns ≫ 1)")
    elif sim.model == "mutation":
        if sim.mu and sim.nu:
            notes.append(f"mutation equilibrium p̂ = ν/(μ + ν) = {dec(sim.nu / (sim.mu + sim.nu))}")
        notes.append(f"μ = {sim.mu:g} per copy per generation: mutation alone changes allele frequencies very slowly")
    elif sim.model == "migration":
        if sim.direction == "one_way":
            notes.append(f"one-way migration: p_t = p_c + (p₀ − p_c)(1 − m)^t, m = {dec(sim.m)}")
        else:
            notes.append(f"two-way migration: the difference between the populations shrinks by (1 − 2m) = {dec(1 - 2 * sim.m)} each generation")
    elif sim.model == "bottleneck" and sim.bottleneck is not None:
        at, nb, dur = sim.bottleneck
        notes.append(f"N drops from {N} to {nb} for {dur} generation{'s' if dur != 1 else ''} at generation {at}, then recovers")
        loss = 1 - math.prod(1 - 1 / (2 * nb) for _ in range(dur))
        notes.append(f"the bottleneck alone removes {loss * 100:.0f} % of the heterozygosity: Π(1 − 1/2N_t) over its generations")
    elif sim.model == "founder" and sim.founders is not None:
        notes.append(f"{sim.founders} founders carry {2 * sim.founders} gene copies sampled from the source (p = {dec(sim.p0[0])})")
        notes.append(f"expected heterozygosity right after founding: H₀ (1 − 1/{2 * sim.founders})")
    return Simulation(**{**sim.__dict__, "notes": tuple(notes)})


# ----- the plan ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PopulationPlan:
    """What a ``population`` scene shows: the model, ``hw`` or ``sim``."""

    model: str
    alleles: tuple[str, str]
    hw: HardyWeinberg | None = None
    sim: Simulation | None = None
    seed: int = 1


def build_population_plan(spec: Mapping[str, Any], where: str = "params") -> PopulationPlan:
    model = str(spec.get("model") or "hardy_weinberg")
    if model not in MODELS:
        raise VidgenError(f"{where}.model: unknown model '{model}': use {', '.join(MODELS)}{did_you_mean(model, list(MODELS))}")
    allowed = set(MODEL_KEYS[model]) | {"model", "alleles", "seed"}
    for key, value in spec.items():
        if value is None or key in allowed:
            continue
        owners = [m for m, keys in MODEL_KEYS.items() if key in keys]
        hint = f" (a param of model: {' / '.join(owners)})" if owners else ""
        raise VidgenError(f"{where}.{key}: not a param of model: {model}{hint}")
    alleles = allele_symbols(spec.get("alleles"), f"{where}.alleles")
    seed = int(spec.get("seed", 1))
    if model == "hardy_weinberg":
        return PopulationPlan(model, alleles, hw=hardy_weinberg(spec, where), seed=seed)
    return PopulationPlan(model, alleles, sim=simulate({**spec, "model": model}, where), seed=seed)


@lru_cache(maxsize=64)
def _cached(key: str) -> PopulationPlan:
    return build_population_plan(json.loads(key))


def plan_population(spec: Mapping[str, Any]) -> PopulationPlan:
    """:func:`build_population_plan`, cached by the spec's JSON."""
    return _cached(json.dumps(dict(spec), sort_keys=True, default=str))


__all__ = ["DOTS", "MODELS", "MODEL_KEYS", "HardyWeinberg", "HweTest", "Line", "PopulationPlan", "Simulation", "allele_symbols",
           "build_population_plan", "dec", "exact_sqrt", "frac_text", "genotype_index", "genotype_names", "hardy_weinberg", "hwe_test",
           "one_in", "plan_population", "proportional_dots", "sample_genotypes", "simulate", "step"]
