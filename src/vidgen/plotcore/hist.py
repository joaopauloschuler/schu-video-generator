"""Histograms for scientific plots: bin edges by a rule (Sturges, Freedman–Diaconis, Scott,
square root, ``auto`` = the narrower of Sturges and Freedman–Diaconis as numpy does, one bin per
integer), a count or a width, or explicit edges; counts or a density with Poisson (√N) errors;
and distributions fitted to the raw values by maximum likelihood (normal, exponential,
Poisson), drawn over the bars in the histogram's units with a Pearson χ² against the bins.
Peaks over a background (Gaussian, Breit–Wigner) are least-squares fits of the counts:
:func:`vidgen.plotcore.fit.fit_curve` with σ = √N."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from vidgen.errors import VidgenError

from .fit import FitResult, Model, unit_power
from .numbers import clean

#: Binning rules.
BIN_RULES = ("auto", "sturges", "fd", "scott", "sqrt", "integers")
#: Distributions fitted by maximum likelihood.
DISTRIBUTIONS = ("normal", "exponential", "poisson")
#: Most bins a histogram may have.
MAX_BINS = 400


def rule_width(values: Sequence[float], rule: str) -> float:
    """The bin width a rule gives for ``values`` (before rounding), as numpy's
    ``histogram_bin_edges``: Sturges (range / (log₂ n + 1)), Freedman–Diaconis (2 IQR / ∛n),
    Scott ((24√π / n)^⅓ σ ≈ 3.49 σ / ∛n), square root (range / √n), ``auto`` (the smaller of
    Sturges and Freedman–Diaconis, Sturges when the IQR is 0)."""
    v = np.asarray([x for x in values if math.isfinite(x)], dtype=float)
    n = len(v)
    if n < 2:
        raise VidgenError("a histogram needs at least two values to choose bins")
    span = float(np.ptp(v))
    if span == 0:
        return 1.0
    if rule == "sturges":
        return span / (math.log2(n) + 1.0)
    if rule == "sqrt":
        return span / math.sqrt(n)
    if rule == "scott":
        sd = float(np.std(v))
        return (24.0 * math.sqrt(math.pi) / n) ** (1 / 3) * sd if sd > 0 else span / (math.log2(n) + 1.0)
    q75, q25 = np.percentile(v, [75, 25])
    fd = 2.0 * float(q75 - q25) / n ** (1 / 3)
    if rule == "fd":
        if fd <= 0:
            raise VidgenError("the Freedman-Diaconis rule needs spread data (the interquartile range is 0); use bins: sturges or a number")
        return fd
    if rule == "auto":
        sturges = span / (math.log2(n) + 1.0)
        return min(fd, sturges) if fd > 0 else sturges
    raise VidgenError(f"unknown binning rule '{rule}'; use one of {', '.join(BIN_RULES)}, a number of bins or a list of edges")


def nice_width(raw: float) -> float:
    """The round width (1, 2, 2.5 or 5 × 10ᵏ) nearest to ``raw`` on a log scale."""
    if raw <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw))
    return clean(min((m * magnitude for m in (1, 2, 2.5, 5, 10)), key=lambda w: abs(math.log(w / raw))))


def bin_edges(
    values: Sequence[float],
    bins: str | int | Sequence[float] = "auto",
    *,
    width: float | None = None,
    lo: float | None = None,
    hi: float | None = None,
    nice: bool = True,
) -> list[float]:
    """Bin edges for ``values``: ``bins`` a rule (:data:`BIN_RULES`), a number of equal bins or
    explicit increasing edges; ``width`` a bin width (overrides a rule); ``lo`` / ``hi`` the
    range (default the values'). With a rule or width and ``nice``, the width is rounded to 1,
    2, 2.5 or 5 × 10ᵏ and the edges are its multiples (from ``lo`` when given); without
    ``nice`` the rule's width exactly, bins starting at the range's low end (numpy's rule
    edges). ``integers``: one bin per integer, edges at k ± ½."""
    finite = [float(v) for v in values if math.isfinite(v)]
    if isinstance(bins, (list, tuple)):
        edges = [float(e) for e in bins]
        if len(edges) < 2 or any(b <= a for a, b in zip(edges, edges[1:])):
            raise VidgenError("bins as edges need at least two increasing numbers")
        return edges
    if not finite:
        raise VidgenError("a histogram needs values")
    a = lo if lo is not None else min(finite)
    b = hi if hi is not None else max(finite)
    if b < a:
        raise VidgenError(f"the bin range [{a:g}, {b:g}] runs backwards")
    if bins == "integers":
        if any(abs(v - round(v)) > 1e-9 for v in finite):
            raise VidgenError("bins: integers needs whole-number values (counts)")
        first, last = math.floor(a + 1e-9), math.ceil(b - 1e-9)
        edges = [k - 0.5 for k in range(first, last + 2)]
        return _limit(edges)
    if b == a:
        a, b = a - 0.5, b + 0.5
    if isinstance(bins, int) and width is None:
        if not 1 <= bins <= MAX_BINS:
            raise VidgenError(f"bins must be 1..{MAX_BINS}, got {bins}")
        return _cover([clean(e) for e in np.linspace(a, b, bins + 1)], a, b)
    inside = [v for v in finite if a <= v <= b]
    w = width if width is not None else rule_width(inside if len(inside) >= 2 else finite, str(bins))
    if w <= 0:
        raise VidgenError(f"a bin width must be positive, got {w:g}")
    if not nice and width is None:
        count = max(1, math.ceil((b - a) / w))
        return _limit(_cover([clean(e) for e in np.linspace(a, b, count + 1)], a, b))
    if nice and width is None:
        w = nice_width(w)
    start = lo if lo is not None else math.floor(a / w + 1e-9) * w
    count = max(1, math.ceil((b - start) / w - 1e-9))   # the last bin includes its right edge
    return _limit(_cover([clean(start + k * w) for k in range(count + 1)], a, b))


def _cover(edges: list[float], a: float, b: float) -> list[float]:
    """The edges with the outer ones moved (by round-off at most) to include ``a`` and ``b``:
    the 12-digit cleaning, or a floor / ceiling within its tolerance, must not drop the smallest
    or largest value from the histogram."""
    if edges[0] > a:
        edges[0] = a
    if edges[-1] < b:
        edges[-1] = b
    return edges


def _limit(edges: list[float]) -> list[float]:
    if len(edges) - 1 > MAX_BINS:
        raise VidgenError(f"these bins make {len(edges) - 1} bins (at most {MAX_BINS}); use a larger width or fewer bins")
    return edges


@dataclass
class Histogram:
    """Binned values: ``edges``, ``counts`` (values per bin; the last bin includes its right
    edge, as numpy), ``density`` (heights are counts / (N × width): the area is 1), ``total``
    N (values inside the bins), ``outside`` (values left out), the raw ``values``."""

    edges: np.ndarray
    counts: np.ndarray
    density: bool = False
    total: int = 0
    outside: int = 0
    values: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def centers(self) -> np.ndarray:
        return (self.edges[:-1] + self.edges[1:]) / 2

    @property
    def widths(self) -> np.ndarray:
        return np.diff(self.edges)

    @property
    def uniform(self) -> bool:
        w = self.widths
        return bool(np.allclose(w, w[0], rtol=1e-9))

    @property
    def heights(self) -> np.ndarray:
        """Bar heights: counts, or the density."""
        if self.density:
            return self.counts / (max(self.total, 1) * self.widths)
        return self.counts.astype(float)

    @property
    def errors(self) -> np.ndarray:
        """Poisson errors of the heights: √N per bin (scaled like the heights for a density)."""
        e = np.sqrt(self.counts.astype(float))
        return e / (max(self.total, 1) * self.widths) if self.density else e

    def scale(self) -> np.ndarray | float:
        """What a probability density is multiplied by to give heights: N × width (counts) or 1
        (density)."""
        return 1.0 if self.density else self.total * self.widths[0]


def histogram(
    values: Sequence[float],
    bins: str | int | Sequence[float] = "auto",
    *,
    width: float | None = None,
    lo: float | None = None,
    hi: float | None = None,
    density: bool = False,
    nice: bool = True,
) -> Histogram:
    """Bin ``values`` (:func:`bin_edges`); values outside the edges are counted in
    ``outside``."""
    v = np.asarray([x for x in values if math.isfinite(x)], dtype=float)
    edges = np.asarray(bin_edges(v, bins, width=width, lo=lo, hi=hi, nice=nice), dtype=float)
    counts, _ = np.histogram(v, bins=edges)
    total = int(counts.sum())
    if total == 0:
        raise VidgenError("the histogram is empty: no value falls into the bins")
    return Histogram(edges, counts, density, total, int(len(v) - total), v)


def _distribution_model(kind: str, hist: Histogram) -> Model:
    """The fitted distribution as a :class:`Model` of x in the histogram's height units."""
    s = hist.scale()
    if kind == "normal":
        return Model("normal", ("mu", "sigma"), ("μ", "σ"), "normal(μ, σ)",
                     lambda x, p: s * np.exp(-0.5 * ((x - p[0]) / p[1]) ** 2) / (p[1] * math.sqrt(2 * math.pi)),
                     lambda x, y: np.zeros(2), lambda xu, yu: (xu, xu))
    if kind == "exponential":
        return Model("exponential", ("lambda",), ("λ",), "exponential(λ)",
                     lambda x, p: np.where(x >= 0, s * p[0] * np.exp(-p[0] * np.maximum(x, 0)), 0.0),
                     lambda x, y: np.zeros(1), lambda xu, yu: (unit_power(xu, -1),))
    return Model("poisson", ("mu",), ("μ",), "Poisson(μ)", lambda x, p: s * poisson_pmf(x, p[0]), lambda x, y: np.zeros(1), lambda xu, yu: ("",))


def poisson_pmf(x: np.ndarray | float, mu: float) -> np.ndarray:
    """P(K = k) of a Poisson distribution with mean ``mu`` at the whole numbers nearest ``x``
    (0 below 0)."""
    k = np.round(np.asarray(x, dtype=float))
    safe = np.clip(k, 0, None)
    log_fact = np.vectorize(lambda v: math.lgamma(v + 1.0))(safe) if safe.size else safe
    out = np.exp(safe * math.log(max(mu, 1e-300)) - mu - log_fact)
    return np.where(k >= 0, out, 0.0)


def fit_distribution(hist: Histogram, kind: str) -> FitResult:
    """A distribution fitted to the histogram's raw values by maximum likelihood: ``normal``
    (μ = mean, σ = √(Σ(x − μ)²/N); errors σ/√N and σ/√(2N)), ``exponential`` (λ = 1/mean,
    error λ/√N; values ≥ 0), ``poisson`` (μ = mean, error √(μ/N); whole numbers ≥ 0). The
    result's model gives heights in the histogram's units; ``chi2`` is Pearson's Σ (O − E)² / E
    over the bins with E > 0 and ``extra["dof"]`` its degrees of freedom (bins − 1 −
    parameters); ``r2`` compares the heights."""
    if kind not in DISTRIBUTIONS:
        from .data import did_you_mean

        raise VidgenError(f"unknown distribution '{kind}'; use one of {', '.join(DISTRIBUTIONS)}{did_you_mean(kind, list(DISTRIBUTIONS))}")
    v = hist.values[(hist.values >= hist.edges[0]) & (hist.values <= hist.edges[-1])]
    n = len(v)
    if n < 2:
        raise VidgenError("a distribution fit needs at least two values in the bins")
    if not hist.density and not hist.uniform:
        raise VidgenError("a distribution over bins of different widths needs density: true")
    if kind == "normal":
        mu, sd = float(v.mean()), float(v.std())
        if sd <= 0:
            raise VidgenError("a normal fit needs values that differ")
        params, errors = np.array([mu, sd]), np.array([sd / math.sqrt(n), sd / math.sqrt(2 * n)])
    elif kind == "exponential":
        if np.any(v < 0):
            raise VidgenError("an exponential fit needs values ≥ 0")
        lam = 1.0 / float(v.mean()) if v.mean() > 0 else math.inf
        if not math.isfinite(lam):
            raise VidgenError("an exponential fit needs values above 0")
        params, errors = np.array([lam]), np.array([lam / math.sqrt(n)])
    else:
        if np.any(v < 0) or np.any(np.abs(v - np.round(v)) > 1e-9):
            raise VidgenError("a Poisson fit needs whole-number values ≥ 0 (counts)")
        if not np.allclose(hist.widths, 1.0):
            raise VidgenError("a Poisson fit needs one bin per whole number (bins: integers)")
        mu = float(v.mean())
        params, errors = np.array([mu]), np.array([math.sqrt(mu / n) if mu > 0 else 0.0])
    model = _distribution_model(kind, hist)
    expected = _expected_counts(kind, params, hist)
    observed = hist.counts.astype(float)
    use = expected > 0
    chi2 = float(np.sum((observed[use] - expected[use]) ** 2 / expected[use]))
    heights = hist.heights
    fitted = model(hist.centers, params)
    total = float(np.sum((heights - heights.mean()) ** 2))
    r2 = 1.0 - float(np.sum((heights - fitted) ** 2)) / total if total > 0 else 1.0
    cov = np.diag(errors**2)
    dof = int(use.sum()) - 1 - len(params)
    rmse = math.sqrt(float(np.mean((heights - fitted) ** 2)))
    return FitResult(model, params, errors, cov, hist.centers, heights, None, chi2, r2, rmse, 0, {"dof": float(dof), "n": float(n)})


def _expected_counts(kind: str, p: np.ndarray, hist: Histogram) -> np.ndarray:
    """Expected counts per bin: N × the probability of each bin."""
    a, b = hist.edges[:-1], hist.edges[1:]
    if kind == "normal":
        from .stats import normal_cdf

        cdf = np.vectorize(lambda x: normal_cdf((x - p[0]) / p[1]))
        prob = cdf(b) - cdf(a)
    elif kind == "exponential":
        prob = np.exp(-p[0] * np.maximum(a, 0)) - np.exp(-p[0] * np.maximum(b, 0))
    else:
        prob = poisson_pmf(hist.centers, float(p[0]))
    return hist.total * prob


__all__ = ["BIN_RULES", "DISTRIBUTIONS", "MAX_BINS", "Histogram", "bin_edges", "fit_distribution", "histogram", "nice_width", "poisson_pmf", "rule_width"]
