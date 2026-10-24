"""Chi-square goodness of fit for a cross (DESIGN.md §96.7): observed counts of the phenotype
classes against the counts the cross predicts, the statistic (exact, as a fraction), its degrees
of freedom (classes − 1), the p-value from the upper regularized gamma function and the critical
value at the chosen significance level. Own implementation (series and Lentz's continued
fraction, as in Numerical Recipes §6.2), so no SciPy is needed. No manim."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from vidgen.errors import VidgenError

#: Below this expected count a class makes the chi-square approximation poor (Cochran's rule).
SMALL_EXPECTED = 5
_EPS = 1e-15
_TINY = 1e-300


def _lower_series(a: float, x: float) -> float:
    """P(a, x) by its series (x < a + 1)."""
    term = total = 1.0 / a
    n = a
    for _ in range(10_000):
        n += 1.0
        term *= x / n
        total += term
        if abs(term) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _upper_fraction(a: float, x: float) -> float:
    """Q(a, x) by its continued fraction (x ≥ a + 1), Lentz's method."""
    b = x + 1.0 - a
    c = 1.0 / _TINY
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = _TINY if abs(d) < _TINY else d
        c = b + an / c
        c = _TINY if abs(c) < _TINY else c
        d = 1.0 / d
        step = d * c
        h *= step
        if abs(step - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def regularized_gamma_q(a: float, x: float) -> float:
    """The upper regularized gamma function Q(a, x) = Γ(a, x) / Γ(a), for a > 0, x ≥ 0."""
    if a <= 0:
        raise ValueError("a must be positive")
    if x <= 0:
        return 1.0
    if x < a + 1.0:
        return max(0.0, 1.0 - _lower_series(a, x))
    return min(1.0, _upper_fraction(a, x))


def chi_square_p(statistic: float, df: int) -> float:
    """P(χ² ≥ ``statistic``) with ``df`` degrees of freedom: Q(df/2, statistic/2)."""
    return regularized_gamma_q(df / 2.0, float(statistic) / 2.0)


def critical_value(df: int, alpha: float) -> float:
    """The χ² value whose upper tail is ``alpha`` (7.815 for df 3, α 0.05), by bisection."""
    lo, hi = 0.0, max(10.0, 10.0 * df)
    while chi_square_p(hi, df) > alpha:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if chi_square_p(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@dataclass(frozen=True)
class ChiRow:
    """One class: its label, observed count, exact expected count and (O − E)² / E."""

    label: str
    observed: int
    expected: Fraction
    contribution: Fraction


@dataclass(frozen=True)
class ChiSquare:
    """A chi-square goodness-of-fit test: the rows, the total, χ² (exact), df, the p-value, α,
    the critical value at α, whether the hypothesis is rejected (p < α) and the classes whose
    expected count is below :data:`SMALL_EXPECTED`."""

    rows: tuple[ChiRow, ...]
    total: int
    statistic: Fraction
    df: int
    p: float
    alpha: Fraction
    critical: float
    rejected: bool
    small: tuple[str, ...]


def chi_square(labels: Sequence[str], observed: Sequence[int], probabilities: Sequence[Fraction],
               alpha: Fraction = Fraction(1, 20), where: str = "observed") -> ChiSquare:
    """Test ``observed`` counts against the exact class ``probabilities`` (summing to 1)."""
    if not (len(labels) == len(observed) == len(probabilities)):
        raise VidgenError(f"{where}: one observed count per class")
    if len(labels) < 2:
        raise VidgenError(f"{where}: a chi-square test needs at least two classes (df = classes − 1)")
    if sum(probabilities, Fraction(0)) != 1:
        raise VidgenError(f"{where}: the expected shares do not add up to 1")
    total = sum(observed)
    if total <= 0:
        raise VidgenError(f"{where}: the observed counts add up to 0: give the numbers counted in each class")
    rows = []
    for label, o, p in zip(labels, observed, probabilities):
        e = total * Fraction(p)
        if e == 0:
            raise VidgenError(f"{where}: class '{label}' is not expected from this cross (probability 0)")
        rows.append(ChiRow(label, int(o), e, (o - e) ** 2 / e))
    statistic = sum((r.contribution for r in rows), Fraction(0))
    df = len(rows) - 1
    p = chi_square_p(float(statistic), df)
    return ChiSquare(tuple(rows), total, statistic, df, p, alpha, critical_value(df, float(alpha)), p < alpha,
                     tuple(r.label for r in rows if r.expected < SMALL_EXPECTED))


def p_text(p: float) -> str:
    """``p = 0.925``, ``p = 0.031``, ``p < 0.001``."""
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}" if p < 0.995 else "p > 0.99"


__all__ = ["SMALL_EXPECTED", "ChiRow", "ChiSquare", "chi_square", "chi_square_p", "critical_value", "p_text", "regularized_gamma_q"]
