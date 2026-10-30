"""Step 228: the Phase W review's fixes, against numpy / scipy references where they exist —
histogram edges that keep every value, Poisson maximum-likelihood fits of counts, RK45 dense
output and its absolute tolerance, temperatures on an offset scale, equal-aspect tick steps,
normalized residuals ticked at ±2, intermediate calculation values for the lint, constants and
the seeded generator."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from vidgen import extensions, registry
from vidgen.errors import VidgenError
from vidgen.plotcore import AxisSpec, PanelInput, Rect, approx_measure, bin_edges, fit_curve, histogram, layout_figure, make_model
from vidgen.plotcore.integrate import rk45
from vidgen.plotcore.models import SplitMix64, simulate_ode
from vidgen.quantities import calc as qc
from vidgen.quantities.constants import CONSTANTS

try:
    from scipy import constants as sp_constants
    from scipy import integrate as sp_integrate
    from scipy import optimize as sp_optimize
except ImportError:   # scipy is not a dependency of schu-video-generator: the reference comparisons skip
    sp_constants = sp_integrate = sp_optimize = None

needs_scipy = pytest.mark.skipif(sp_optimize is None, reason="scipy not installed (reference values only)")
DECAY = "A*exp(-lambda*x)"


def _counts(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = np.arange(0.25, 15, 0.5)
    return x, rng.poisson(700 * np.exp(-0.2716 * x)).astype(float)


def _decay_model() -> Any:
    return make_model("custom", expr=DECAY, params=["A", "lambda"], guesses={"A": 700, "lambda": 0.3})


# ----- histograms ----------------------------------------------------------------------------------


def test_histogram_edges_keep_the_smallest_and_largest_value() -> None:
    rng = np.random.default_rng(3)
    for _ in range(60):
        v = rng.normal(0, 1, 50) * 10 ** rng.uniform(-5, 5)
        for bins, nice in ((7, True), ("sturges", False), ("fd", False), ("auto", True)):
            h = histogram(v, bins, nice=nice)
            assert h.outside == 0 and h.total == len(v), (bins, nice)
    v = rng.normal(10, 2, 333)
    ours = histogram(v, 20, density=True)
    ref, edges = np.histogram(v, 20, density=True)
    assert np.allclose(ours.heights, ref, rtol=1e-9) and np.allclose(ours.edges, edges, rtol=1e-11)
    assert bin_edges([0.1 * 3, 1.0], width=0.1)[0] <= 0.1 * 3     # a floor within its tolerance still covers the value


# ----- Poisson maximum likelihood ----------------------------------------------------------------


def test_poisson_fit_solves_the_likelihood_equations() -> None:
    x, n = _counts(1)
    fit = fit_curve(x, n, _decay_model(), poisson=1.0)
    mu = fit(x)
    grad = fit.gradient(x)
    score = ((n - mu) / mu) @ grad                      # ∂ log L / ∂p = Σ (n − μ)/μ ∂μ/∂p = 0
    assert np.all(np.abs(score) < 1e-6 * np.abs(grad).sum(axis=0))
    info = grad.T @ (grad / mu[:, None])                # Fisher information: the errors are its inverse's
    assert np.allclose(fit.errors, np.sqrt(np.diag(np.linalg.inv(info))), rtol=1e-4)
    assert fit.chi2 == pytest.approx(float(np.sum((n - mu) ** 2 / mu)), rel=1e-9)   # Pearson


@needs_scipy
def test_poisson_fit_matches_a_direct_likelihood_minimum() -> None:
    x, n = _counts(2)
    fit = fit_curve(x, n, _decay_model(), y_err=np.sqrt(np.maximum(n, 1)), poisson=1.0)
    nll = lambda p: float(np.sum(p[0] * np.exp(-p[1] * x) - n * np.log(p[0] * np.exp(-p[1] * x))))  # noqa: E731
    ref = sp_optimize.minimize(nll, [700, 0.3], method="Nelder-Mead", options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 20000}).x
    assert np.allclose(fit.params, ref, rtol=1e-6)


def test_root_n_weights_bias_a_decay_low_and_the_likelihood_does_not() -> None:
    model = _decay_model()
    neyman, ml = [], []
    for seed in range(120):
        x, n = _counts(100 + seed)
        neyman.append(fit_curve(x, n, model, y_err=np.sqrt(np.maximum(n, 1))).params[1])
        ml.append(fit_curve(x, n, model, poisson=1.0).params[1])
    spread = float(np.std(ml))
    assert (np.mean(neyman) - 0.2716) / spread > 0.3           # √N from the data: λ too large (the curve pulled low)
    assert abs(np.mean(ml) - 0.2716) / spread < 0.2


def test_poisson_scale_for_a_density_and_errors() -> None:
    x, n = _counts(4)
    counts = fit_curve(x, n, _decay_model(), poisson=1.0)
    scaled = fit_curve(x, n / 50.0, make_model("custom", expr=DECAY, params=["A", "lambda"], guesses={"A": 14, "lambda": 0.3}), poisson=1 / 50.0)
    assert scaled.params[1] == pytest.approx(counts.params[1], rel=1e-7) and scaled.errors[1] == pytest.approx(counts.errors[1], rel=1e-5)
    with pytest.raises(VidgenError, match="counts ≥ 0"):
        fit_curve(x, n - 1000, _decay_model(), poisson=1.0)


def _plot(**p: Any) -> Any:
    extensions.load_builtins()
    return registry.get("plot").cls.validate_params(p)


def test_a_count_of_zero_is_fitted_and_residuals_use_the_fit() -> None:
    x = [0, 1, 2, 3, 4, 5, 6, 7]
    y = [40, 24, 15, 9, 5, 3, 0, 1]
    p = _plot(series=[{"name": "counts", "x": x, "y": y, "style": "points", "y_err": "sqrt"}],
              fits=[{"series": "counts", "model": "exponential", "residuals": "normalized"}])
    (fit,) = p.resolve().fits
    direct = fit_curve(x, y, make_model("exponential"), poisson=1.0)
    assert np.allclose(fit.result.params, direct.params) and fit.poisson is not None
    from vidgen.scenes.plot_figure import PlotFigure

    xs, res, err = PlotFigure._residuals(fit)
    assert len(xs) == 8 and np.allclose(res, (np.array(y) - direct(np.array(x, dtype=float))) / np.sqrt(direct(np.array(x, dtype=float))))


def test_normalized_residual_panel_is_symmetric_and_ticked_at_two() -> None:
    from vidgen.plotcore import build_axis

    spec = AxisSpec(lo=-3.0, hi=3.0, ticks=(-2.0, 2.0, 7.0), include_zero=True, max_ticks=3)
    axis = build_axis([-1.2, 2.4], spec)
    assert axis.ticks == (-2.0, 2.0) and axis.labels == ("−2", "2") and (axis.lo, axis.hi) == (-3.0, 3.0)
    x = [0, 1, 2, 3, 4, 5, 6, 7]
    p = _plot(series=[{"name": "counts", "x": x, "y": [40, 24, 15, 9, 5, 3, 0, 1], "style": "points", "y_err": "sqrt"}],
              fits=[{"series": "counts", "model": "exponential", "residuals": "normalized"}])
    resolved = p.resolve()
    from vidgen.scenes.plot_figure import PlotFigure

    panel_input = PlotFigure._residual_input(PlotFigure, resolved.fits[0], resolved[0], PanelInput(tuple(x), (0.0, 40.0), AxisSpec(), AxisSpec()))
    assert panel_input.y.ticks == (-2.0, 2.0) and panel_input.y.lo == -panel_input.y.hi and panel_input.y.hi >= 2.5


# ----- integrators ---------------------------------------------------------------------------------


def test_rk45_dense_output_is_accurate_and_cheap() -> None:
    calls = [0]

    def f(t: float, y: np.ndarray) -> np.ndarray:
        calls[0] += 1
        return np.array([y[1], -y[0]])

    times = np.linspace(0, 20, 401)[1:]
    out, states = rk45(f, 0.0, [1.0, 0.0], 20.0, times=times, rtol=1e-6, atol=1e-9)
    assert np.array_equal(out, times) and np.max(np.abs(states[:, 0] - np.cos(times))) < 1e-5
    assert calls[0] < 2 * len(times)           # steps follow the error, not the 400 outputs (2401 calls before)
    _, early = rk45(f, 0.0, [1.0, 0.0], 20.0, times=[0.0, 0.5], rtol=1e-6, atol=1e-9)
    assert early[0].tolist() == [1.0, 0.0]


@needs_scipy
def test_rk45_matches_solve_ivp() -> None:
    def f(t: float, y: np.ndarray) -> np.ndarray:
        return np.array([y[0] * (1.0 - y[1]), y[1] * (y[0] - 1.0)])   # Lotka–Volterra

    times = np.linspace(0, 15, 301)[1:]
    _, ours = rk45(f, 0.0, [1.5, 0.5], 15.0, times=times, rtol=1e-8, atol=1e-11)
    ref = sp_integrate.solve_ivp(f, (0, 15), [1.5, 0.5], t_eval=times, rtol=1e-10, atol=1e-13, method="DOP853")
    assert np.max(np.abs(ours - ref.y.T)) < 1e-6


def test_rk45_absolute_floor_follows_the_model_scale() -> None:
    sim = simulate_ode({"c": "-k*c"}, {"c": 1e-7}, params={"k": 0.5}, t=(0, 10), method="rk45")
    t, c = sim.columns["t"], sim.columns["c"]
    assert np.max(np.abs(c / (1e-7 * np.exp(-0.5 * t)) - 1)) < 1e-5


def test_splitmix64_reference_values() -> None:
    g = SplitMix64(1234567)
    assert [g.next() for _ in range(2)] == [6457827717110365317, 3203168211198807973]


# ----- temperatures --------------------------------------------------------------------------------


def _work(symbols: list[dict[str, Any]], calcs: list[dict[str, Any]]) -> Any:
    return qc.work([qc.SymbolInput(**s) for s in symbols], [qc.CalcInput(**c) for c in calcs])


def test_two_celsius_readings_are_not_added() -> None:
    temps = [{"name": "T1", "value": "20.0 °C"}, {"name": "T2", "value": "30.0 °C"}]
    with pytest.raises(VidgenError, match=r"cannot add 'T1' and 'T2'.*a change of 10 °C is 10 K"):
        _work(temps, [{"name": "s", "expr": "T1 + T2", "unit": "°C"}])
    with pytest.raises(VidgenError, match=r"difference of temperatures.*write it in K"):
        _work(temps, [{"name": "d", "expr": "T2 - T1", "unit": "°C"}])
    ok = _work(temps + [{"name": "dT", "value": "5 K"}], [{"name": "d", "expr": "T2 - T1"}, {"name": "w", "expr": "T1 + dT", "unit": "°C"},
                                                         {"name": "h", "expr": "(T2 - T1)/2"}])
    d, w, h = ok.results
    assert d.value.value_text() == "10.0 K" and w.value.value_text() == "25 °C" and h.value.value_text() == "5.00 K"
    with pytest.raises(VidgenError, match="convert: the result is a difference of temperatures"):
        _work(temps, [{"name": "d", "expr": "T2 - T1", "convert": ["°F"]}])
    kelvin = _work([{"name": "T1", "value": "293.15 K"}, {"name": "T2", "value": "303.15 K"}], [{"name": "m", "expr": "(T1 + T2)/2", "unit": "°C"}])
    assert kelvin.results[0].value.value_text() == "25.00 °C"


# ----- layout ----------------------------------------------------------------------------------------


def test_equal_aspect_ticks_both_axes_with_one_step() -> None:
    panel = PanelInput((0.0, 10.0), (0.0, 3.0), AxisSpec(), AxisSpec())
    (lay,) = layout_figure(Rect(-7.0, -4.0, 7.0, 3.0), [panel], approx_measure(), aspect="equal")
    sx = lay.x.ticks[1] - lay.x.ticks[0]
    sy = lay.y.ticks[1] - lay.y.ticks[0]
    assert sx == pytest.approx(sy) and len(lay.y.ticks) >= 2
    assert lay.plot.width / (lay.x.hi - lay.x.lo) == pytest.approx(lay.plot.height / (lay.y.hi - lay.y.lo), rel=1e-6)


# ----- the lint's candidates -------------------------------------------------------------------------


def test_intermediate_values_are_kept_for_the_lint() -> None:
    worked = _work([{"name": "g", "value": "9.81 m/s^2"}, {"name": "h", "value": "10.0 m"}], [{"name": "v", "expr": "sqrt(2*g*h)", "unit": "m/s"}])
    (r,) = worked.results
    parts = [p for s in r.steps for p in s.values]
    assert len(parts) == 1 and parts[0].value_text() == "196 m²/s²" and math.isclose(float(parts[0].quantity.value), 196.2)


# ----- constants -------------------------------------------------------------------------------------


@pytest.mark.skipif(sp_constants is None, reason="scipy not installed")
def test_constants_match_scipy_codata() -> None:
    names = {"c": "speed of light in vacuum", "G": "Newtonian constant of gravitation", "h": "Planck constant", "hbar": "reduced Planck constant",
             "k_B": "Boltzmann constant", "N_A": "Avogadro constant", "e": "elementary charge", "R": "molar gas constant",
             "sigma_SB": "Stefan-Boltzmann constant", "m_e": "electron mass", "m_p": "proton mass", "m_u": "atomic mass constant",
             "epsilon_0": "vacuum electric permittivity", "mu_0": "vacuum mag. permeability", "g": "standard acceleration of gravity"}
    if sp_constants.physical_constants["Newtonian constant of gravitation"][0] != 6.67430e-11 or \
            sp_constants.physical_constants["electron mass"][0] != 9.1093837139e-31:
        pytest.skip("this scipy carries another CODATA release")
    for key, name in names.items():
        assert float(CONSTANTS[key].value) == pytest.approx(sp_constants.physical_constants[name][0], rel=1e-12), key
    assert float(CONSTANTS["AU"].value) == sp_constants.au
