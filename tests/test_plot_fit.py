"""The chart core's data features (Phase W Step 223, DESIGN §97.5): distribution functions,
curve fits with standard errors and bands (against closed forms and, when scipy is installed,
scipy.optimize.curve_fit), histogram binning rules (against numpy), distributions fitted to
histograms, value ± error formatting, tight axis ends, lines broken at axis breaks, model
expressions with parameters, and deterministic annotation placement. No manim, no rendering."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.mathexpr import parse_model
from vidgen.plotcore import (
    AxisSpec,
    PanelInput,
    Rect,
    approx_measure,
    bin_edges,
    build_axis,
    chi2_sf,
    fit_curve,
    fit_distribution,
    histogram,
    layout_figure,
    make_model,
    normal_ppf,
    place_in_plot,
    place_near,
    pretty_name,
    rule_width,
    t_cdf,
    t_ppf,
    unit_ratio,
    value_with_error,
)
from vidgen.plotcore.annotate import best_box, box_cost, place_on_hline

try:
    from scipy import optimize as sp_optimize
    from scipy import stats as sp_stats
except ImportError:   # scipy is not a dependency of schu-video-generator: the closed-form tests still run
    sp_optimize = sp_stats = None

needs_scipy = pytest.mark.skipif(sp_optimize is None, reason="scipy not installed (reference values only)")


# ----- distribution functions --------------------------------------------------------------------


def test_quantiles_match_tables() -> None:
    assert normal_ppf(0.975) == pytest.approx(1.959963984540054, abs=1e-12)
    assert t_ppf(0.975, 1) == pytest.approx(12.706204736174707, rel=1e-10)
    assert t_ppf(0.975, 2) == pytest.approx(4.302652729749464, rel=1e-10)
    assert t_ppf(0.025, 10) == pytest.approx(-2.228138851986274, rel=1e-10)
    assert t_cdf(0.0, 3) == 0.5 and t_ppf(0.5, 7) == 0.0
    assert chi2_sf(3.841458820694124, 1) == pytest.approx(0.05, abs=1e-12)
    with pytest.raises(ValueError, match="strictly between 0 and 1"):
        t_ppf(1.0, 3)


@needs_scipy
def test_quantiles_match_scipy() -> None:
    for p in (1e-9, 0.01, 0.3, 0.9, 0.999999):
        assert normal_ppf(p) == pytest.approx(sp_stats.norm.ppf(p), rel=1e-9, abs=1e-12)
        for df in (1, 1.5, 4, 25, 400):
            assert t_ppf(p, df) == pytest.approx(sp_stats.t.ppf(p, df), rel=1e-8)
    for x, df in ((0.5, 1), (12.0, 3), (40.0, 30)):
        assert chi2_sf(x, df) == pytest.approx(sp_stats.chi2.sf(x, df), rel=1e-9, abs=1e-15)


# ----- fits against closed forms ----------------------------------------------------------------


X = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
NOISE = np.array([0.3, -0.2, 0.1, -0.4, 0.25, -0.1, 0.35, -0.3])


def test_straight_line_is_ordinary_least_squares() -> None:
    y = 2.0 + 3.0 * X + NOISE
    fit = fit_curve(X, y, make_model("linear"))
    n = len(X)
    sxx = float(np.sum((X - X.mean()) ** 2))
    b = float(np.sum((X - X.mean()) * (y - y.mean())) / sxx)
    a = float(y.mean() - b * X.mean())
    s2 = float(np.sum((y - a - b * X) ** 2) / (n - 2))
    assert fit.params == pytest.approx([a, b], rel=1e-12)
    assert fit.errors == pytest.approx([math.sqrt(s2 * (1 / n + X.mean() ** 2 / sxx)), math.sqrt(s2 / sxx)], rel=1e-10)
    assert fit.r2 == pytest.approx(1 - s2 * (n - 2) / float(np.sum((y - y.mean()) ** 2)), rel=1e-12)
    assert fit.reduced_chi2 is None   # no y errors: no χ²/ν
    # bands: s·t·√(1/n + (x − x̄)²/Sxx), the prediction band with 1 + under the root
    t = t_ppf(0.975, n - 2)
    lo, hi = fit.band([1.5, 6.0])
    half = (hi - lo) / 2
    expected = [math.sqrt(s2) * t * math.sqrt(1 / n + (x - X.mean()) ** 2 / sxx) for x in (1.5, 6.0)]
    assert half == pytest.approx(expected, rel=1e-6)
    lo, hi = fit.band([1.5], kind="prediction")
    assert (hi - lo)[0] / 2 == pytest.approx(math.sqrt(s2) * t * math.sqrt(1 + 1 / n + (1.5 - X.mean()) ** 2 / sxx), rel=1e-6)


def test_weighted_line_with_known_errors() -> None:
    y = 1.0 - 0.5 * X + NOISE
    sigma = np.array([0.2, 0.3, 0.2, 0.5, 0.3, 0.2, 0.4, 0.3])
    fit = fit_curve(X, y, make_model("linear"), y_err=sigma)
    w = 1 / sigma**2
    A = np.vstack([np.ones_like(X), X]).T
    cov = np.linalg.inv(A.T @ (A * w[:, None]))
    p = cov @ (A.T @ (w * y))
    assert fit.params == pytest.approx(p, rel=1e-10)
    assert fit.errors == pytest.approx(np.sqrt(np.diag(cov)), rel=1e-8)   # absolute: not scaled by χ²/ν
    chi2 = float(np.sum(w * (y - A @ p) ** 2))
    assert fit.chi2 == pytest.approx(chi2, rel=1e-10) and fit.reduced_chi2 == pytest.approx(chi2 / 6, rel=1e-10)
    assert fit.quantile(0.95) == pytest.approx(1.959963984540054)   # known errors: the normal quantile


def test_noise_free_models_are_recovered() -> None:
    x = np.linspace(0.5, 10, 25)
    cases = [
        ("exponential", {}, lambda x: 800 * np.exp(-0.21 * x), [800, -0.21]),
        ("power", {}, lambda x: 2.0 * x**1.5, [2.0, 1.5]),
        ("logistic", {}, lambda x: 5 / (1 + np.exp(-1.2 * (x - 4.5))), [5, 1.2, 4.5]),
        ("gaussian", {}, lambda x: 7 * np.exp(-0.5 * ((x - 6) / 1.3) ** 2), [7, 6, 1.3]),
        ("gaussian", {"background": 1}, lambda x: 7 * np.exp(-0.5 * ((x - 6) / 1.3) ** 2) + 2 + 0.3 * x, [7, 6, 1.3, 2, 0.3]),
        ("breit_wigner", {}, lambda x: 9 * 1.0**2 / ((x - 5) ** 2 + 1.0**2), [9, 5, 2.0]),
        ("poly", {"degree": 3}, lambda x: 1 - 2 * x + 0.5 * x**2 - 0.01 * x**3, [1, -2, 0.5, -0.01]),
    ]
    for kind, kw, f, true in cases:
        fit = fit_curve(x, f(x), make_model(kind, **kw))
        assert fit.params == pytest.approx(true, rel=1e-6, abs=1e-9), kind
        assert fit.r2 == pytest.approx(1.0, abs=1e-12)


def test_custom_expression_with_named_parameters() -> None:
    x = np.linspace(0, 40, 15)
    y = 900 * np.exp(-x / 11.5) + 40
    model = make_model("custom", expr="a*exp(-x/tau) + c", params=["a", "tau", "c"], guesses={"a": 1000, "tau": 8, "c": 0}, units={"tau": "d"})
    fit = fit_curve(x, y, model)
    assert fit.params == pytest.approx([900, 11.5, 40], rel=1e-7)
    assert model.labels == ("a", "τ", "c") and model.formula == "y = a·exp(−x/τ) + c"
    assert fit.parameter_lines("d", "Bq")[1].startswith("τ = 11.5") and fit.parameter_lines()[1].endswith(" d")


def test_x_errors_enter_as_effective_variance() -> None:
    y = 3.0 + 2.0 * X + NOISE
    # a straight line: σ_eff = |b| σx, the same weights as y errors of 2 σx
    sx = np.full(len(X), 0.25)
    a = fit_curve(X, y, make_model("linear"), x_err=sx)
    b = fit_curve(X, y, make_model("linear"), y_err=np.abs(a.params[1]) * sx)
    assert a.params == pytest.approx(b.params, rel=1e-9) and a.errors == pytest.approx(b.errors, rel=1e-6)


@needs_scipy
@pytest.mark.parametrize("weighted", [False, True], ids=["unweighted", "weighted"])
def test_fits_match_scipy_curve_fit(weighted: bool) -> None:
    rng = np.random.default_rng(7)
    x = np.linspace(1, 30, 24)
    cases = [
        ("exponential", {}, lambda x, A, k: A * np.exp(k * x), 500 * np.exp(-0.08 * x)),
        ("power", {}, lambda x, A, k: A * x**k, 3 * x**0.7),
        ("logistic", {}, lambda x, L, k, x0: L / (1 + np.exp(-k * (x - x0))), 40 / (1 + np.exp(-0.4 * (x - 14)))),
        ("gaussian", {"background": 0}, lambda x, A, m, s, b0: A * np.exp(-0.5 * ((x - m) / s) ** 2) + b0, 20 * np.exp(-0.5 * ((x - 15) / 3) ** 2) + 4),
        ("breit_wigner", {"background": 1}, lambda x, A, M, G, b0, b1: A * (G / 2) ** 2 / ((x - M) ** 2 + (G / 2) ** 2) + b0 + b1 * x,
         25 * 4 / ((x - 16) ** 2 + 4) + 3 + 0.1 * x),
    ]
    for kind, kw, f, clean_y in cases:
        y = clean_y * (1 + 0.04 * rng.standard_normal(len(x))) + 0.2 * rng.standard_normal(len(x))
        sigma = 0.04 * np.abs(clean_y) + 0.3 if weighted else None
        model = make_model(kind, **kw)
        ours = fit_curve(x, y, model, y_err=sigma)
        popt, pcov = sp_optimize.curve_fit(f, x, y, p0=model.guess(x, y), sigma=sigma, absolute_sigma=weighted, maxfev=50000)
        perr = np.sqrt(np.diag(pcov))
        assert np.max(np.abs(ours.params - popt) / perr) < 1e-3, kind
        assert ours.errors == pytest.approx(perr, rel=1e-3), kind


def test_fit_errors_are_clear() -> None:
    with pytest.raises(VidgenError, match="unknown fit model 'exponentail'.*did you mean 'exponential'"):
        make_model("exponentail")
    with pytest.raises(VidgenError, match="custom needs expr"):
        make_model("custom")
    with pytest.raises(VidgenError, match="expr: .*unknown name 'tua'.*did you mean tau"):
        make_model("custom", expr="a*exp(-x/tua)", params=["a", "tau"])
    with pytest.raises(VidgenError, match="has no parameter 'B'"):
        make_model("exponential", guesses={"B": 1})
    with pytest.raises(VidgenError, match="background is for peak models"):
        make_model("linear", background=1)
    with pytest.raises(VidgenError, match="needs more than 2 points"):
        fit_curve([1, 2], [3, 4], make_model("linear"))
    with pytest.raises(VidgenError, match="needs positive x values"):
        fit_curve([0, 1, 2, 3], [1, 2, 3, 4], make_model("power"))
    with pytest.raises(VidgenError, match="y errors must be positive"):
        fit_curve([0, 1, 2, 3], [1, 2, 3, 4], make_model("linear"), y_err=[1, 0, 1, 1])
    with pytest.raises(VidgenError, match="not determined by the data"):
        fit_curve([1, 1, 1, 1], [1, 2, 3, 4], make_model("linear"))


def test_model_expressions_with_parameters() -> None:
    m = parse_model("A sin(w x + phi)", ["A", "w", "phi"])
    assert m(np.array([0.0, 1.0]), [2, math.pi / 2, 0]) == pytest.approx([0, 2])
    assert parse_model("tau*x", ["tau"])(np.array([3.0]), [2])[0] == 6.0   # a parameter may take a constant's name
    with pytest.raises(ValueError, match="the parameter c is not in the expression"):
        parse_model("a*x", ["a", "c"])
    with pytest.raises(ValueError, match="taken"):
        parse_model("x*x", ["x"])
    with pytest.raises(ValueError, match="did you mean amp"):
        parse_model("ampp*x", ["amp"])


def test_names_and_units() -> None:
    assert pretty_name("x0") == "x₀" and pretty_name("sigma") == "σ" and pretty_name("Gamma") == "Γ" and pretty_name("b12") == "b₁₂"
    assert unit_ratio("Bq", "d") == "Bq/d" and unit_ratio("Bq", "d", 2) == "Bq/d²" and unit_ratio("", "d") == "d⁻¹" and unit_ratio("Bq", "") == "Bq"
    assert unit_ratio("J", "m/s") == "J/(m/s)"


@pytest.mark.parametrize(
    ("value", "error", "unit", "text"),
    [
        (985.3, 19.2, "Bq", "985 ± 19 Bq"),
        (-0.08461, 0.00172, "d⁻¹", "−0.0846 ± 0.0017 d⁻¹"),
        (124.9712, 0.47, "GeV", "125.0 ± 0.5 GeV"),
        (2.51e-4, 3.1e-6, "s", "(2.510 ± 0.031) × 10⁻⁴ s"),
        (6.02e23, 0.096e23, "", "(6.02 ± 0.10) × 10²³"),
        (12345.0, 120.0, "", "12350 ± 120"),
        (3.14159, None, "", "3.142"),
    ],
)
def test_value_with_error(value: float, error: float | None, unit: str, text: str) -> None:
    assert value_with_error(value, error, unit) == text


# ----- histograms -------------------------------------------------------------------------------

SAMPLE = np.random.default_rng(3).normal(50, 7, 300)


@pytest.mark.parametrize("rule", ["sturges", "fd", "scott", "sqrt", "auto"])
def test_binning_rules_match_numpy(rule: str) -> None:
    ours = bin_edges(SAMPLE, rule, nice=False)
    assert ours == pytest.approx(list(np.histogram_bin_edges(SAMPLE, bins=rule)), rel=1e-10)
    assert rule_width(SAMPLE, rule) > 0


def test_bins_nice_integers_explicit_and_counts() -> None:
    edges = bin_edges(SAMPLE, "fd")
    width = edges[1] - edges[0]
    assert width in (1, 2, 2.5, 5, 10) and all(abs(e / width - round(e / width)) < 1e-9 for e in edges)
    assert edges[0] <= SAMPLE.min() and edges[-1] >= SAMPLE.max()
    assert bin_edges([0, 1, 1, 3], "integers") == [-0.5, 0.5, 1.5, 2.5, 3.5]
    assert bin_edges(SAMPLE, 4, lo=20, hi=80) == [20, 35, 50, 65, 80]
    assert bin_edges(SAMPLE, width=10, lo=25) [:3] == [25, 35, 45]
    h = histogram(SAMPLE, [30, 40, 50, 60, 70], density=True)
    assert float(np.sum(h.heights * h.widths)) == pytest.approx(1.0) and h.total + h.outside == len(SAMPLE)
    counts = histogram([1, 2, 2, 3, 3, 3], "integers")
    assert list(counts.counts) == [1, 2, 3] and list(counts.errors) == pytest.approx([1, math.sqrt(2), math.sqrt(3)])
    with pytest.raises(VidgenError, match="whole-number values"):
        bin_edges([0.5, 1], "integers")
    with pytest.raises(VidgenError, match="increasing"):
        bin_edges(SAMPLE, [1, 1, 2])
    with pytest.raises(VidgenError, match="unknown binning rule 'freedman'"):
        bin_edges(SAMPLE, "freedman")


def test_distributions_fitted_by_maximum_likelihood() -> None:
    h = histogram(SAMPLE, "fd")
    normal = fit_distribution(h, "normal")
    n = len(SAMPLE)
    sd = float(np.std(SAMPLE))
    assert normal.params == pytest.approx([SAMPLE.mean(), sd]) and normal.errors == pytest.approx([sd / math.sqrt(n), sd / math.sqrt(2 * n)])
    # the curve in counts per bin: N × width × the density, near the bar heights
    assert normal(np.array([SAMPLE.mean()]))[0] == pytest.approx(n * (h.edges[1] - h.edges[0]) / (sd * math.sqrt(2 * math.pi)))
    assert normal.extra["dof"] > 0 and 0 < normal.chi2 / normal.extra["dof"] < 3
    rng = np.random.default_rng(5)
    waits = rng.exponential(2.0, 500)
    expo = fit_distribution(histogram(waits, "auto", lo=0), "exponential")
    assert expo.params[0] == pytest.approx(1 / waits.mean()) and expo.errors[0] == pytest.approx(expo.params[0] / math.sqrt(500))
    counts = rng.poisson(3.2, 400)
    pois = fit_distribution(histogram(counts, "integers"), "poisson")
    assert pois.params[0] == pytest.approx(counts.mean()) and pois.errors[0] == pytest.approx(math.sqrt(counts.mean() / 400))
    k = np.arange(0, 12)
    assert pois(k.astype(float)) == pytest.approx(400 * np.exp(k * math.log(counts.mean()) - counts.mean() - np.array([math.lgamma(v + 1) for v in k])))
    with pytest.raises(VidgenError, match="one bin per whole number"):
        fit_distribution(histogram(counts, 5), "poisson")
    with pytest.raises(VidgenError, match="values ≥ 0"):
        fit_distribution(histogram(SAMPLE - 60, "fd"), "exponential")


@needs_scipy
def test_distribution_mle_matches_scipy() -> None:
    mu, sd = sp_stats.norm.fit(SAMPLE)
    assert fit_distribution(histogram(SAMPLE, "fd"), "normal").params == pytest.approx([mu, sd], rel=1e-10)
    waits = np.random.default_rng(9).exponential(3.0, 300)
    _, scale = sp_stats.expon.fit(waits, floc=0)
    assert fit_distribution(histogram(waits, "auto", lo=0), "exponential").params[0] == pytest.approx(1 / scale, rel=1e-10)


# ----- axes: tight ends and breaks --------------------------------------------------------------


def test_tight_axis_ends() -> None:
    near = build_axis([0.0, 1.88], AxisSpec(tight=0.08))
    assert (near.lo, near.hi) == (0.0, 2.0)                 # 2.0 adds 6 % of the span: rounded out
    far = build_axis([-410.0, 230.0], AxisSpec(tight=0.08))
    assert far.hi == pytest.approx(230 + 0.04 * 640) and far.lo == pytest.approx(-410 - 0.04 * 640)
    assert all(far.lo <= t <= far.hi for t in far.ticks) and len(far.ticks) >= 2
    old = build_axis([-410.0, 230.0], AxisSpec())
    assert (old.lo, old.hi) == (-600.0, 400.0)              # without tight: the outer ticks (Step 222)
    fixed = build_axis([-410.0, 230.0], AxisSpec(tight=0.08, hi=1000))
    assert fixed.hi == 1000
    log = build_axis([1.2, 30.0], AxisSpec(scale="log", tight=0.08))
    assert log.lo == pytest.approx(1.0) and 30 < log.hi < 100   # 1 is near in decades; 100 is not


def test_a_line_never_crosses_a_break() -> None:
    spec = AxisSpec(breaks=((12.0, 95.0),))
    (lay,) = layout_figure(Rect(-6, -3, 6, 3), [PanelInput((1.0, 10.0, 100.0, 120.0), (1.0, 2.0, 3.0, 4.0), spec, AxisSpec())], approx_measure())
    pts = lay.frame_line([1, 10, 100, 120], [1, 2, 3, 4])
    assert len(pts) == 5 and np.isnan(pts[2, 0]) and not np.isnan(pts[[0, 1, 3, 4], 0]).any()
    plain = layout_figure(Rect(-6, -3, 6, 3), [PanelInput((1.0, 2.0), (1.0, 2.0), AxisSpec(), AxisSpec())], approx_measure())[0]
    assert len(plain.frame_line([1, 2], [1, 2])) == 2


# ----- annotation placement ---------------------------------------------------------------------

PLOT = Rect(0, 0, 10, 6)


def test_labels_avoid_data_and_each_other_deterministically() -> None:
    line = np.array([[x, 0.6 * x, 0] for x in np.linspace(0, 10, 101)])   # a diagonal: the upper left is free
    first = place_near((5.0, 3.0), (2.0, 0.5), PLOT, line, [])
    again = place_near((5.0, 3.0), (2.0, 0.5), PLOT, line, [])
    assert first == again and first.cost == 0
    box = first.box
    assert not any(box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1 for x, y, _ in line)
    second = place_near((5.2, 3.1), (2.0, 0.5), PLOT, line, [box])
    assert box_cost(second.box, PLOT, line[:, :2], [box]) == 0 and second.box != box
    corner = place_in_plot((3.0, 1.0), PLOT, line, [])
    assert corner.box.x0 < 5 and corner.box.y1 > 4               # top left: the line runs bottom left to top right
    assert place_in_plot((3.0, 1.0), PLOT, line, [corner.box]).box != corner.box
    name = place_on_hline(1.0, (2.0, 0.4), PLOT, line, [])
    assert name.box.y0 > 1.0 and name.cost == 0
    tie = best_box([Rect(1, 1, 2, 2), Rect(3, 3, 4, 4)], PLOT, np.zeros((0, 2)), [])
    assert tie.index == 0                                        # equal costs: the first candidate
