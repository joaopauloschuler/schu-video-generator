"""Distribution functions the fits and bands need, in plain Python (no scipy): the normal and
Student-t distributions (CDF and quantile) through the regularized incomplete beta function,
and the regularized lower incomplete gamma function (χ² tail). Accurate to about 1e-10, checked
against scipy in the tests."""

from __future__ import annotations

import math

_EPS = 1e-15
_TINY = 1e-300


def normal_cdf(x: float) -> float:
    """P(Z ≤ x) for a standard normal Z."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def normal_ppf(p: float) -> float:
    """The standard normal quantile: the x with P(Z ≤ x) = ``p`` (0 < p < 1). Acklam's
    rational approximation refined by two Newton steps on :func:`normal_cdf`."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"a probability must lie strictly between 0 and 1, got {p}")
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
    low = 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p > 1 - low:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    for _ in range(2):
        density = math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
        if density <= 0:
            break
        x -= (normal_cdf(x) - p) / density
    return x


def _beta_fraction(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        step = d * c
        h *= step
        if abs(step - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """The regularized incomplete beta function I_x(a, b) for a, b > 0 and 0 ≤ x ≤ 1."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """P(T ≤ t) for Student's t with ``df`` degrees of freedom (``df`` may be fractional)."""
    if df <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {df}")
    if math.isinf(df):
        return normal_cdf(t)
    tail = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t > 0 else tail


def t_ppf(p: float, df: float) -> float:
    """The quantile of Student's t: the t with P(T ≤ t) = ``p``. Newton steps from the normal
    quantile, kept inside a bracket by bisection."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"a probability must lie strictly between 0 and 1, got {p}")
    if df <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {df}")
    if math.isinf(df) or df > 1e7:
        return normal_ppf(p)
    if p == 0.5:
        return 0.0
    sign = 1.0 if p > 0.5 else -1.0
    q = 1.0 - p if p > 0.5 else p   # the tail beyond |t|, solved directly (no 1 - p round-off)
    lo, hi = 0.0, 1.0
    while _t_tail(hi, df) > q:
        lo, hi = hi, hi * 2.0
        if hi > 1e300:
            return sign * hi
    x = min(max(abs(normal_ppf(q)), lo), hi)
    log_norm = math.lgamma((df + 1) / 2) - math.lgamma(df / 2) - 0.5 * math.log(df * math.pi)
    for _ in range(300):
        f = _t_tail(x, df) - q
        if f == 0 or abs(f) < 1e-15 * q:
            break
        if f < 0:
            hi = x
        else:
            lo = x
        density = math.exp(log_norm - (df + 1) / 2 * math.log1p(x * x / df))
        nxt = x + f / density if density > 0 else (lo + hi) / 2
        if not lo < nxt < hi:
            nxt = (lo + hi) / 2
        if abs(nxt - x) < 1e-14 * max(1.0, abs(x)):
            x = nxt
            break
        x = nxt
    return sign * x


def _t_tail(t: float, df: float) -> float:
    """P(T > t) for t ≥ 0."""
    return 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))


def gammainc(a: float, x: float) -> float:
    """The regularized lower incomplete gamma function P(a, x) (series below a + 1, a
    continued fraction above)."""
    if x <= 0:
        return 0.0
    log_front = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1.0:
        term = total = 1.0 / a
        ap = a
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * _EPS:
                break
        return total * math.exp(log_front)
    b = x + 1.0 - a
    c = 1.0 / _TINY
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = b + an / c
        c = c if abs(c) > _TINY else _TINY
        step = d * c
        h *= step
        if abs(step - 1.0) < _EPS:
            break
    return 1.0 - math.exp(log_front) * h


def chi2_sf(chi2: float, df: float) -> float:
    """P(χ² > ``chi2``) with ``df`` degrees of freedom (the p-value of a goodness of fit)."""
    if df <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {df}")
    return 1.0 - gammainc(df / 2.0, chi2 / 2.0)


def two_sided(level: float) -> float:
    """The upper probability of a two-sided interval holding ``level`` (0.95 -> 0.975)."""
    if not 0.0 < level < 1.0:
        raise ValueError(f"a confidence level must lie between 0 and 1, got {level}")
    return 0.5 + level / 2.0


__all__ = ["betainc", "chi2_sf", "gammainc", "normal_cdf", "normal_ppf", "t_cdf", "t_ppf", "two_sided"]
