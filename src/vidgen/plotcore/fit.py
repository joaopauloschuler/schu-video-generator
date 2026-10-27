"""Curve fitting for scientific plots, in numpy alone: weighted least squares for models linear
in their parameters (straight line, polynomial), Levenberg–Marquardt for the others
(exponential, power law, logistic, Gaussian and Breit–Wigner peaks with an optional polynomial
background, and a custom expression of ``x`` and named parameters through
:func:`vidgen.mathexpr.parse_model`). A fit gives its parameters with standard errors (from the
covariance matrix), R², χ² and χ²/ν with y errors, residuals, and confidence and prediction
bands (the delta method with Student's t or, for known errors, the normal quantile).

Conventions (as ``scipy.optimize.curve_fit``): without y errors the covariance is scaled by
the residual variance (``absolute_sigma=False``); with y errors they are taken as absolute
(``absolute_sigma=True``) and χ²/ν says whether they fit the scatter. Errors in x enter through
the effective variance σ² = σ_y² + (f′(x) σ_x)², re-weighted a few times."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from vidgen.errors import VidgenError

from .numbers import MINUS, value_with_error
from .stats import normal_ppf, t_ppf, two_sided

#: Model kinds (``custom``: an expression with named parameters).
MODEL_KINDS = ("linear", "poly", "exponential", "power", "logistic", "gaussian", "breit_wigner", "custom")
#: Other names authors use for a model kind.
MODEL_ALIASES = {"line": "linear", "polynomial": "poly", "exp": "exponential", "power_law": "power", "sigmoid": "logistic",
                 "gauss": "gaussian", "cauchy": "breit_wigner", "lorentzian": "breit_wigner"}
#: Models that take a polynomial ``background``.
PEAK_KINDS = ("gaussian", "breit_wigner")
#: Highest polynomial degree (``poly`` and backgrounds).
MAX_DEGREE = 6

_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "kappa": "κ", "lambda": "λ", "lam": "λ",
          "mu": "μ", "nu": "ν", "omega": "ω", "phi": "φ", "rho": "ρ", "sigma": "σ", "tau": "τ", "theta": "θ",
          "Gamma": "Γ", "Delta": "Δ", "Omega": "Ω"}

Function = Callable[[np.ndarray, np.ndarray], np.ndarray]


def pretty_name(name: str) -> str:
    """A parameter name as a label writes it: Greek names as letters (``tau`` -> ``τ``),
    trailing digits as subscripts (``x0`` -> ``x₀``, ``b1`` -> ``b₁``)."""
    match = re.match(r"^(.*?)(\d+)$", name)
    stem, digits = (match.group(1), match.group(2)) if match else (name, "")
    stem = _GREEK.get(stem, stem)
    return stem + digits.translate(_SUB)


def unit_power(unit: str, power: int) -> str:
    """``unit`` to an integer ``power`` as a label writes it: ``d``, ``d⁻¹``, ``m²``;
    a compound unit is bracketed (``(m/s)⁻¹``); ``""`` without a unit or for power 0."""
    if not unit or power == 0:
        return ""
    base = f"({unit})" if any(c in unit for c in " /·*") else unit
    return base if power == 1 else base + str(power).translate(_SUP)


def unit_ratio(top: str, bottom: str, power: int = 1) -> str:
    """The unit of ``top / bottom^power``: ``Bq/d``, ``Bq/d²``, ``d⁻¹`` (no top), ``Bq`` (no
    bottom)."""
    if not bottom or power == 0:
        return top
    if not top:
        return unit_power(bottom, -power)
    return f"{top}/{unit_power(bottom, power)}"


@dataclass(frozen=True)
class Model:
    """A model to fit: its ``kind``, parameter ``names`` (as written in YAML), ``labels`` (as
    shown: ``μ``, ``σ``), the ``formula`` shown (``y = A·exp(k·x)``), the ``function`` f(x, p),
    ``basis`` (models linear in their parameters: x -> design matrix) and ``guess`` (x, y ->
    starting values) and ``units`` (x unit, y unit -> each parameter's unit)."""

    kind: str
    names: tuple[str, ...]
    labels: tuple[str, ...]
    formula: str
    function: Function = field(repr=False, compare=False)
    guess: Callable[[np.ndarray, np.ndarray], np.ndarray] = field(repr=False, compare=False)
    units: Callable[[str, str], tuple[str, ...]] = field(repr=False, compare=False)
    basis: Callable[[np.ndarray], np.ndarray] | None = field(default=None, repr=False, compare=False)
    positive_x: bool = False

    def __call__(self, x: np.ndarray | float, p: Sequence[float]) -> np.ndarray:
        with np.errstate(all="ignore"):
            return np.asarray(self.function(np.asarray(x, dtype=float), np.asarray(p, dtype=float)), dtype=float)


def _poly_basis(degree: int) -> Callable[[np.ndarray], np.ndarray]:
    return lambda x: np.vander(np.asarray(x, dtype=float), degree + 1, increasing=True)


def _poly_terms(names: Sequence[str]) -> str:
    """``c₀ + c₁x + c₂x²`` for coefficient names."""
    out = []
    for i, n in enumerate(names):
        label = pretty_name(n)
        out.append(label if i == 0 else f"{label}x" if i == 1 else f"{label}x{str(i).translate(_SUP)}")
    return " + ".join(out)


def _peak_guess(x: np.ndarray, y: np.ndarray, background: int) -> tuple[float, float, float, list[float]]:
    """Height, centre, full width at half maximum and background coefficients to start from."""
    order = np.argsort(x)
    x, y = x[order], y[order]
    n_edge = max(2, len(x) // 6)
    bg = [0.0] * (background + 1)
    base = np.zeros_like(y)
    if background >= 0 and len(x) >= 2 * n_edge:
        ex = np.concatenate([x[:n_edge], x[-n_edge:]])
        ey = np.concatenate([y[:n_edge], y[-n_edge:]])
        deg = min(background, 1)
        coef = np.polyfit(ex, ey, deg)[::-1]
        bg[: deg + 1] = [float(c) for c in coef]
        base = np.polyval(coef[::-1], x)
    signal = y - base
    k = int(np.argmax(signal))
    height = float(signal[k]) if signal[k] > 0 else float(np.ptp(y) or 1.0)
    above = x[signal >= height / 2]
    width = float(above.max() - above.min()) if len(above) > 1 else float(np.ptp(x) / 6 or 1.0)
    return height, float(x[k]), max(width, float(np.ptp(x)) / max(len(x), 1)), bg


def make_model(
    kind: str,
    *,
    degree: int = 2,
    background: int | None = None,
    expr: str | None = None,
    params: Sequence[str] = (),
    guesses: Mapping[str, float] | None = None,
    units: Mapping[str, str] | None = None,
) -> Model:
    """The model of ``kind`` (or an alias, :data:`MODEL_ALIASES`). ``degree``: of ``poly``;
    ``background``: a polynomial of that degree under a ``gaussian`` / ``breit_wigner`` peak
    (parameters ``b0`` … ``bn``); ``expr`` and ``params`` (names, in order): a ``custom`` model,
    starting from ``guesses`` (default 1 each), its parameters in ``units`` (default none).
    ``guesses`` also override a built-in model's own starting values. Raises ``VidgenError``."""
    kind = MODEL_ALIASES.get(kind, kind)
    if kind not in MODEL_KINDS:
        from .data import did_you_mean

        raise VidgenError(f"unknown fit model '{kind}'; use one of {', '.join(MODEL_KINDS)}{did_you_mean(kind, list(MODEL_KINDS) + list(MODEL_ALIASES))}")
    if background is not None and kind not in PEAK_KINDS:
        raise VidgenError(f"background is for peak models ({', '.join(PEAK_KINDS)}), not {kind}")
    if background is not None and not 0 <= background <= MAX_DEGREE:
        raise VidgenError(f"background must be a polynomial degree 0..{MAX_DEGREE}, got {background}")
    if kind != "custom" and expr:
        raise VidgenError(f"expr is for model: custom (got model: {kind})")
    model = _builtin(kind, degree, background, expr, list(params), units or {})
    if guesses:
        unknown = [g for g in guesses if g not in model.names]
        if unknown:
            raise VidgenError(f"the {kind} model has no parameter '{unknown[0]}'; its parameters: {', '.join(model.names)}")
        own = model.guess
        idx = {n: i for i, n in enumerate(model.names)}

        def guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            p = np.array(own(x, y), dtype=float)
            for name, value in guesses.items():
                p[idx[name]] = float(value)
            return p

        model = Model(model.kind, model.names, model.labels, model.formula, model.function, guess, model.units, None, model.positive_x)
    return model


def _builtin(kind: str, degree: int, background: int | None, expr: str | None, params: list[str], units: Mapping[str, str]) -> Model:
    if kind == "linear":
        return Model("linear", ("a", "b"), ("a", "b"), "y = a + b·x", lambda x, p: p[0] + p[1] * x,
                     lambda x, y: np.zeros(2), lambda xu, yu: (yu, unit_ratio(yu, xu)), _poly_basis(1))
    if kind == "poly":
        if not 1 <= degree <= MAX_DEGREE:
            raise VidgenError(f"a polynomial fit takes degree 1..{MAX_DEGREE}, got {degree}")
        names = tuple(f"c{i}" for i in range(degree + 1))
        return Model("poly", names, tuple(pretty_name(n) for n in names), "y = " + _poly_terms(names),
                     lambda x, p: np.polyval(p[::-1], x), lambda x, y: np.zeros(degree + 1),
                     lambda xu, yu: tuple(unit_ratio(yu, xu, i) for i in range(degree + 1)), _poly_basis(degree))
    if kind == "exponential":
        def exp_guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            ok = y > 0
            if ok.sum() >= 2 and np.ptp(x[ok]) > 0:
                k, ln_a = np.polyfit(x[ok], np.log(y[ok]), 1)
                return np.array([math.exp(ln_a), k])
            return np.array([float(y[np.argmin(np.abs(x))]) or 1.0, 0.0])

        return Model("exponential", ("A", "k"), ("A", "k"), "y = A·exp(k·x)", lambda x, p: p[0] * np.exp(p[1] * x), exp_guess,
                     lambda xu, yu: (yu, unit_power(xu, -1)))
    if kind == "power":
        def pow_guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            ok = (x > 0) & (y > 0)
            if ok.sum() >= 2 and np.ptp(x[ok]) > 0:
                k, ln_a = np.polyfit(np.log(x[ok]), np.log(y[ok]), 1)
                return np.array([math.exp(ln_a), k])
            return np.array([1.0, 1.0])

        return Model("power", ("A", "k"), ("A", "k"), "y = A·xᵏ", lambda x, p: p[0] * np.power(x, p[1]), pow_guess,
                     lambda xu, yu: (yu if not xu else "", ""), positive_x=True)
    if kind == "logistic":
        def logistic_guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            top = float(np.max(y)) * 1.05 if np.max(y) > 0 else 1.0
            inside = (y > 0) & (y < top)
            if inside.sum() >= 2 and np.ptp(x[inside]) > 0:
                k, c = np.polyfit(x[inside], np.log(y[inside] / (top - y[inside])), 1)
                if k != 0:
                    return np.array([top, k, -c / k])
            return np.array([top, 4.0 / (np.ptp(x) or 1.0), float(np.median(x))])

        return Model("logistic", ("L", "k", "x0"), ("L", "k", "x₀"), f"y = L / (1 + exp({MINUS}k(x {MINUS} x₀)))",
                     lambda x, p: p[0] / (1.0 + np.exp(-p[1] * (x - p[2]))), logistic_guess,
                     lambda xu, yu: (yu, unit_power(xu, -1), xu))
    if kind in PEAK_KINDS:
        bg = background
        bg_names = tuple(f"b{i}" for i in range(bg + 1)) if bg is not None else ()
        tail = (" + " + _poly_terms(bg_names)) if bg_names else ""

        def background_of(x: np.ndarray, p: np.ndarray) -> np.ndarray:
            return np.polyval(p[3:][::-1], x) if bg_names else 0.0

        def bg_units(xu: str, yu: str) -> tuple[str, ...]:
            return tuple(unit_ratio(yu, xu, i) for i in range(len(bg_names)))

        if kind == "gaussian":
            def gauss_guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
                h, c, w, coef = _peak_guess(x, y, bg if bg is not None else -1)
                return np.array([h, c, w / 2.3548, *coef[: len(bg_names)]])

            return Model("gaussian", ("A", "mu", "sigma", *bg_names), ("A", "μ", "σ", *map(pretty_name, bg_names)),
                         f"y = A·exp({MINUS}(x {MINUS} μ)²/2σ²)" + tail,
                         lambda x, p: p[0] * np.exp(-0.5 * ((x - p[1]) / p[2]) ** 2) + background_of(x, p), gauss_guess,
                         lambda xu, yu: (yu, xu, xu, *bg_units(xu, yu)))

        def bw_guess(x: np.ndarray, y: np.ndarray) -> np.ndarray:
            h, c, w, coef = _peak_guess(x, y, bg if bg is not None else -1)
            return np.array([h, c, w, *coef[: len(bg_names)]])

        return Model("breit_wigner", ("A", "M", "Gamma", *bg_names), ("A", "M", "Γ", *map(pretty_name, bg_names)),
                     f"y = A·(Γ/2)² / ((x {MINUS} M)² + (Γ/2)²)" + tail,
                     lambda x, p: p[0] * (p[2] / 2) ** 2 / ((x - p[1]) ** 2 + (p[2] / 2) ** 2) + background_of(x, p), bw_guess,
                     lambda xu, yu: (yu, xu, xu, *bg_units(xu, yu)))
    # custom
    from vidgen.mathexpr import parse_model, pretty_expression

    if not expr:
        raise VidgenError("model: custom needs expr (e.g. expr: \"a*exp(-x/tau) + c\") and params (e.g. params: {a: 1000, tau: 8, c: 0})")
    if not params:
        raise VidgenError(f"model: custom needs params: the parameters of {expr!r} with starting values, e.g. params: {{a: 1, b: 0.5}}")
    try:
        compiled = parse_model(expr, params)
    except ValueError as exc:
        raise VidgenError(f"expr: {exc}") from None
    shown = pretty_expression(expr)
    for name in sorted(params, key=len, reverse=True):
        label = pretty_name(name)
        if label != name:
            shown = re.sub(rf"\b{re.escape(name)}\b", label, shown)
    return Model("custom", tuple(params), tuple(pretty_name(n) for n in params), f"y = {shown}",
                 lambda x, p: compiled(x, list(p)), lambda x, y: np.ones(len(params)),
                 lambda xu, yu: tuple(units.get(n, "") for n in params))


@dataclass
class FitResult:
    """A fitted model: ``params`` and their standard ``errors``, the covariance ``cov``, the
    data (``x``, ``y``, the weights' ``sigma`` or ``None``), ``n`` points, ``dof`` = n − p,
    ``chi2`` (Σ ((y − f)/σ)², or the sum of squared residuals without σ), ``reduced_chi2``
    (with σ only), ``r2`` and ``rmse``; ``level`` / quantile helpers make bands."""

    model: Model
    params: np.ndarray
    errors: np.ndarray
    cov: np.ndarray
    x: np.ndarray
    y: np.ndarray
    sigma: np.ndarray | None
    chi2: float
    r2: float
    rmse: float
    iterations: int = 0
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.x)

    @property
    def dof(self) -> int:
        return self.n - len(self.params)

    @property
    def reduced_chi2(self) -> float | None:
        return self.chi2 / self.dof if self.sigma is not None and self.dof > 0 else None

    def __call__(self, x: np.ndarray | float) -> np.ndarray:
        return self.model(x, self.params)

    def value(self, name: str) -> tuple[float, float]:
        """``(value, standard error)`` of the parameter ``name``."""
        if name not in self.model.names:
            raise VidgenError(f"the fit has no parameter '{name}'; its parameters: {', '.join(self.model.names)}")
        i = self.model.names.index(name)
        return float(self.params[i]), float(self.errors[i])

    def residuals(self) -> np.ndarray:
        """y − f(x) at the data."""
        return self.y - self(self.x)

    def quantile(self, level: float) -> float:
        """The two-sided quantile for a band at ``level``: Student's t with ``dof`` degrees of
        freedom, or the normal quantile when the errors are known (y errors given)."""
        p = two_sided(level)
        if self.sigma is not None or self.dof <= 0:
            return normal_ppf(p)
        return t_ppf(p, self.dof)

    def gradient(self, xs: np.ndarray) -> np.ndarray:
        """∂f/∂p at ``xs`` (rows: points, columns: parameters), central differences."""
        return _jacobian(self.model, np.asarray(xs, dtype=float), self.params, self.params)

    def band(self, xs: Sequence[float] | np.ndarray, *, level: float = 0.95, kind: str = "confidence") -> tuple[np.ndarray, np.ndarray]:
        """Lower and upper edges of the ``confidence`` band (where the true curve lies:
        f ± q·√(gᵀCg)) or the ``prediction`` band (where a new measurement lies: the variance
        of a point added — σ² interpolated between the data's errors, else the residual
        variance) at ``xs``."""
        xs = np.asarray(xs, dtype=float)
        g = self.gradient(xs)
        var = np.einsum("ij,jk,ik->i", g, self.cov, g)
        if kind == "prediction":
            if self.sigma is not None:
                order = np.argsort(self.x)
                var = var + np.interp(xs, self.x[order], self.sigma[order] ** 2)
            else:
                var = var + (self.chi2 / self.dof if self.dof > 0 else 0.0)
        elif kind != "confidence":
            raise VidgenError(f"band '{kind}' is not confidence or prediction")
        half = self.quantile(level) * np.sqrt(np.maximum(var, 0.0))
        f = self(xs)
        return f - half, f + half

    def parameter_lines(self, x_unit: str = "", y_unit: str = "") -> list[str]:
        """One line per parameter: ``A = 1003 ± 12 Bq``."""
        units = self.model.units(x_unit, y_unit)
        return [f"{label} = {value_with_error(float(v), float(e), u)}" for label, v, e, u in zip(self.model.labels, self.params, self.errors, units)]


def _jacobian(model: Model, x: np.ndarray, p: np.ndarray, p0: np.ndarray) -> np.ndarray:
    if model.basis is not None:
        return model.basis(x)
    out = np.empty((len(x), len(p)))
    for j in range(len(p)):
        scale = max(abs(p[j]), 1e-3 * abs(p0[j]))
        h = 1e-6 * scale if scale > 0 else 1e-6   # a parameter at 0 (a background offset): an absolute step
        up, down = p.copy(), p.copy()
        up[j] += h
        down[j] -= h
        out[:, j] = (model(x, up) - model(x, down)) / (2 * h)
    return out


def _levenberg_marquardt(model: Model, x: np.ndarray, y: np.ndarray, w: np.ndarray, p0: np.ndarray, max_iter: int) -> tuple[np.ndarray, int]:
    """Minimise Σ w (y − f)² from ``p0`` (w = 1/σ²)."""
    sw = np.sqrt(w)

    def cost(p: np.ndarray) -> float:
        r = (y - model(x, p)) * sw
        return float(r @ r) if np.all(np.isfinite(r)) else math.inf

    p = np.array(p0, dtype=float)
    c = cost(p)
    if not math.isfinite(c):
        raise VidgenError("the model cannot be evaluated at the starting values (give params: starting values that suit the data)")
    lam = 1e-3
    it = 0
    for it in range(1, max_iter + 1):
        J = _jacobian(model, x, p, p0) * sw[:, None]
        if not np.all(np.isfinite(J)):
            raise VidgenError("the fit ran into values where the model is undefined (give params: closer starting values)")
        r = (y - model(x, p)) * sw
        A = J.T @ J
        g = J.T @ r
        diag = np.diag(A).copy()
        diag[diag <= 0] = 1e-12
        improved = False
        while lam < 1e16:
            try:
                step = np.linalg.solve(A + lam * np.diag(diag), g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            trial = p + step
            ct = cost(trial)
            if ct < c:
                done = (c - ct) <= 1e-14 * max(c, 1e-300) or np.all(np.abs(step) <= 1e-12 * (np.abs(p) + 1e-12))
                p, c = trial, ct
                lam = max(lam / 3, 1e-12)
                improved = True
                break
            lam *= 4
        if not improved or done:
            break
    return p, it


def _covariance(J: np.ndarray) -> np.ndarray:
    A = J.T @ J
    if np.linalg.matrix_rank(A) < A.shape[0]:
        raise VidgenError("the fit's parameters are not determined by the data (too few distinct x values, or parameters that depend on each other)")
    return np.linalg.inv(A)


def fit_curve(
    x: Sequence[float],
    y: Sequence[float],
    model: Model,
    *,
    y_err: Sequence[float] | None = None,
    x_err: Sequence[float] | None = None,
    max_iter: int = 400,
) -> FitResult:
    """Fit ``model`` to the points (``nan`` points are left out). ``y_err``: standard errors of
    y (weighted least squares, absolute); ``x_err``: of x (effective variance). Raises
    ``VidgenError`` for too few points, non-positive errors, a power law with x ≤ 0, or a fit
    that cannot be determined."""
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    sy = np.asarray(y_err, dtype=float) if y_err is not None else None
    sx = np.asarray(x_err, dtype=float) if x_err is not None else None
    ok = np.isfinite(xa) & np.isfinite(ya)
    for name, s in (("y errors", sy), ("x errors", sx)):
        if s is not None:
            if s.shape != xa.shape:
                raise VidgenError(f"{name}: {len(s)} values for {len(xa)} points")
            if np.any(s[ok] < 0) or not np.all(np.isfinite(s[ok])):
                raise VidgenError(f"{name} must be positive numbers")
    if sy is not None and np.any(sy[ok] == 0):
        raise VidgenError("y errors must be positive (a zero error would weigh one point infinitely)")
    xa, ya = xa[ok], ya[ok]
    sy = sy[ok] if sy is not None else None
    sx = sx[ok] if sx is not None else None
    k = len(model.names)
    if len(xa) <= k:
        raise VidgenError(f"a {model.kind} fit has {k} parameters and needs more than {k} points, got {len(xa)}")
    if model.positive_x and np.any(xa <= 0):
        raise VidgenError(f"a {model.kind} fit needs positive x values (x = {xa[xa <= 0][0]:g})")
    p0 = np.asarray(model.guess(xa, ya), dtype=float)
    sigma = sy.copy() if sy is not None else None
    if sx is not None and np.any(sx > 0):
        rounds = 4
        if sigma is None:
            sigma = np.ones_like(xa)
            sy = np.zeros_like(xa)
    else:
        rounds = 1
    p = p0
    iterations = 0
    for _ in range(rounds):
        w = 1.0 / sigma**2 if sigma is not None else np.ones_like(xa)
        if model.basis is not None:
            B = model.basis(xa) * np.sqrt(w)[:, None]
            p = np.linalg.lstsq(B, ya * np.sqrt(w), rcond=None)[0]
        else:
            p, it = _levenberg_marquardt(model, xa, ya, w, p, max_iter)
            iterations += it
        if sx is not None and sy is not None:
            h = 1e-6 * (np.abs(xa) + float(np.ptp(xa)) + 1e-12)
            slope = (model(xa + h, p) - model(xa - h, p)) / (2 * h)
            sigma = np.sqrt(sy**2 + (slope * sx) ** 2)
            sigma[sigma <= 0] = np.min(sigma[sigma > 0]) if np.any(sigma > 0) else 1.0
    if model.kind in PEAK_KINDS:
        p = np.array(p, dtype=float)
        p[2] = abs(p[2])   # a width: the model is even in it
    w = 1.0 / sigma**2 if sigma is not None else np.ones_like(xa)
    J = _jacobian(model, xa, p, p0) * np.sqrt(w)[:, None]
    cov = _covariance(J)
    resid = ya - model(xa, p)
    if not np.all(np.isfinite(resid)):
        raise VidgenError("the fitted model is undefined at some data points (give params: other starting values)")
    chi2 = float(np.sum(resid**2 * w))
    if sigma is None:
        cov = cov * (chi2 / (len(xa) - k))
    total = float(np.sum((ya - ya.mean()) ** 2))
    ssr = float(np.sum(resid**2))
    r2 = 1.0 - ssr / total if total > 0 else 1.0
    errors = np.sqrt(np.maximum(np.diag(cov), 0.0))
    return FitResult(model, np.asarray(p, dtype=float), errors, cov, xa, ya, sigma, chi2, r2, math.sqrt(ssr / len(xa)), iterations)


__all__ = [
    "MAX_DEGREE",
    "MODEL_ALIASES",
    "MODEL_KINDS",
    "PEAK_KINDS",
    "FitResult",
    "Model",
    "fit_curve",
    "make_model",
    "pretty_name",
    "unit_power",
    "unit_ratio",
]
