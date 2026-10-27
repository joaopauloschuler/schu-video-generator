"""Live and animated plots (Phase W Step 224): the ODE integrators against analytic solutions,
leapfrog's bounded energy against RK4's drift, recurrences, seeded random processes, registered
model functions, the growth and rescaling logic, the plot params of models and live series, the
``grow`` and region ``zoom`` actions, and tiny renders."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import render
from vidgen import extensions, plotcore, registry
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.mathexpr import parse_system
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 3.0}
OSC = {"kind": "ode", "equations": {"x": "v", "v": "-k*x - c*v"}, "params": {"k": 4, "c": 0.3}, "initial": {"x": 1, "v": 0}, "t": [0, 10],
       "units": {"t": "s", "x": "m", "v": "m/s"}}


def harmonic(method: str, **kw: Any) -> Any:
    return plotcore.simulate_ode({"x": "v", "v": "-k*x"}, {"x": 1, "v": 0}, params={"k": 4}, method=method,
                                 quantities={"E": "0.5*v^2 + 0.5*k*x^2"}, conserved=["E"], **kw)


# ----- integrators ------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["rk4", "rk45", "leapfrog"])
def test_harmonic_oscillator_matches_cos(method: str) -> None:
    sim = harmonic(method, t=(0, 10), step=0.002 if method == "leapfrog" else 0.01, rtol=1e-8)
    t = sim.columns["t"]
    tol = {"rk4": 1e-7, "rk45": 1e-6, "leapfrog": 2e-5}[method]
    assert np.max(np.abs(sim.columns["x"] - np.cos(2 * t))) < tol
    assert np.max(np.abs(sim.columns["v"] + 2 * np.sin(2 * t))) < 10 * tol
    assert sim.time == "t" and t[0] == 0 and t[-1] == pytest.approx(10)


def test_exponential_decay_and_a_projectile() -> None:
    sim = plotcore.simulate_ode({"dN/dt": "-lambda*N"}, {"N": 1000}, params={"lambda": 0.3}, t=(0, 20), method="rk45", rtol=1e-9)
    t = sim.columns["t"]
    assert np.max(np.abs(sim.columns["N"] / (1000 * np.exp(-0.3 * t)) - 1)) < 1e-7
    for method in ("rk4", "leapfrog"):   # constant acceleration: both exact to rounding
        p = plotcore.simulate_ode({"x'": "vx", "y'": "vy", "vx'": "0", "vy'": "-g"}, {"x": 0, "y": 0, "vx": 3, "vy": 10}, params={"g": 9.81},
                                  t=(0, 2), step=0.05, method=method)
        tt = p.columns["t"]
        assert np.allclose(p.columns["y"], 10 * tt - 0.5 * 9.81 * tt**2, atol=1e-9)
        assert np.allclose(p.columns["x"], 3 * tt, atol=1e-9)


def test_leapfrog_keeps_the_energy_bounded_where_rk4_drifts() -> None:
    def drift(method: str, end: float) -> float:
        sim = plotcore.simulate_ode({"x": "v", "v": "-x"}, {"x": 1, "v": 0}, t=(0, end), step=0.5, method=method, samples=4000,
                                    quantities={"E": "0.5*v^2 + 0.5*x^2"}, conserved=["E"])
        return sim.drift["E"]

    rk_short, rk_long = drift("rk4", 100), drift("rk4", 1000)
    lf_short, lf_long = drift("leapfrog", 100), drift("leapfrog", 1000)
    assert rk_long > 5 * rk_short and rk_long > 0.2           # RK4 loses energy step after step
    assert lf_long < 1.5 * lf_short and lf_long < 0.1         # leapfrog's error oscillates, bounded


def test_rk45_reports_exact_output_times_and_detects_stiffness() -> None:
    times = [0.5, 1.0, 1.5]
    out, states = plotcore.rk45(lambda t, y: -y, 0.0, [1.0], 1.5, times=times, rtol=1e-9)
    assert list(out) == times and np.allclose(states[:, 0], np.exp(-np.array(times)), rtol=1e-8)
    with pytest.raises(VidgenError, match="stiff"):
        plotcore.simulate_ode({"y": "-1000*(y - cos(t))"}, {"y": 0}, t=(0, 2000), method="rk45")
    short = plotcore.simulate_ode({"y": "-1000*(y - cos(t))"}, {"y": 0}, t=(0, 1), method="rk45")   # a short stiff stretch is fine
    assert short.columns["y"][-1] == pytest.approx(math.cos(1), abs=1e-3)


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"equations": {"x": "v", "v": "-k*xx"}}, r"unknown name 'xx'.*did you mean x"),
        ({"initial": {"x": 1}}, r"no initial condition for v; add initial: \{v: 0\}"),
        ({"initial": {"x": 1, "v": 0, "w": 2}}, "'w' is not a variable of the equations"),
        ({"step": 5}, "step 5 is too large for t from 0 to 10; use at most 2.5"),
        ({"equations": {"x": "x*x", "v": "0"}, "t": (0, 5)}, r"x blows up near t = 1\.0.*smaller step"),
        ({"method": "leapfrog"}, "accelerations that do not depend on velocities, but v' uses v"),
        ({"method": "euler"}, "method 'euler' is not one of rk4, rk45, leapfrog"),
        ({"equations": {"x": "v", "dx/dt": "1"}}, "'x' has two equations"),
        ({"params": {"t": 1, "k": 1, "c": 0}}, "'t' is the time"),
        ({"quantities": {"x": "v"}}, "'x' is already a column"),
        ({"conserved": ["E"]}, "conserved: no column or quantity 'E'"),
        ({"units": {"w": "m"}}, "units: no column 'w'"),
    ],
)
def test_ode_errors_are_clear(kw: dict[str, Any], message: str) -> None:
    base: dict[str, Any] = {"equations": {"x": "v", "v": "-k*x - c*v"}, "initial": {"x": 1, "v": 0}, "params": {"k": 1, "c": 0.1}, "t": (0, 10)}
    base.update(kw)
    equations, initial = base.pop("equations"), base.pop("initial")
    with pytest.raises(VidgenError, match=message):
        plotcore.simulate_ode(equations, initial, source="model 'osc'", **base)


def test_determinism_of_every_model() -> None:
    a, b = harmonic("rk45", t=(0, 5)), harmonic("rk45", t=(0, 5))
    assert all(np.array_equal(a.columns[k], b.columns[k]) for k in a.columns)
    w1, w2, w3 = (plotcore.random_walk(steps=50, seed=s) for s in (3, 3, 4))
    assert np.array_equal(w1.columns["x"], w2.columns["x"]) and not np.array_equal(w1.columns["x"], w3.columns["x"])
    assert plotcore.SplitMix64(0).next() == 0xE220A8397B1DCDAF   # the reference vector: same numbers on every machine


# ----- recurrences, random processes, functions ----------------------------------------------------


def test_recurrences() -> None:
    lm = plotcore.simulate_recurrence({"x": "r*x*(1 - x)"}, {"x": 0.2}, params={"r": 3.7}, steps=4)
    assert lm.time == "n" and list(lm.columns["n"]) == [0, 1, 2, 3, 4]
    assert lm.columns["x"][:3] == pytest.approx([0.2, 0.592, 0.8936832])
    money = plotcore.simulate_recurrence({"balance[n+1]": "balance*(1 + rate)"}, {"balance": 100}, params={"rate": 0.05}, steps=10)
    assert money.columns["balance"][-1] == pytest.approx(100 * 1.05**10)
    with pytest.raises(VidgenError, match="not a finite number after step"):
        plotcore.simulate_recurrence({"x": "x*x*1e100"}, {"x": 10}, steps=10)


def test_random_walks_and_poisson_events() -> None:
    w = plotcore.random_walk(steps=200, seed=1)
    steps = np.diff(w.columns["x"])
    assert set(np.abs(steps)) == {1.0} and w.columns["distance"][0] == 0
    up = plotcore.random_walk(steps=2000, seed=2, p=0.8)
    assert np.mean(np.diff(up.columns["x"]) > 0) == pytest.approx(0.8, abs=0.04)
    plane = plotcore.random_walk(steps=100, seed=5, dims=2, distribution="gaussian", step=0.5)
    assert {"x", "y", "distance"} <= set(plane.columns)
    p = plotcore.poisson_process(rate=50, t=(0, 100), seed=9)
    count = p.columns["count"]
    assert np.all(np.diff(count) >= 0) and np.all(np.diff(p.columns["t"]) >= 0)
    assert abs(count[-1] - 5000) < 5 * math.sqrt(5000)
    with pytest.raises(VidgenError, match="dims must be 1 or 2"):
        plotcore.random_walk(dims=3)


def test_registered_model_functions() -> None:
    @plotcore.register_model("test_parabola")
    def parabola(params: dict[str, float], seed: int) -> dict[str, list[float]]:
        ts = [i / 10 for i in range(11)]
        return {"t": ts, "y": [params.get("a", 1.0) * t * t for t in ts]}

    assert "test_parabola" in plotcore.registered_models()
    sim = plotcore.run_registered("test_parabola", params={"a": 2}, quantities={"twice": "2*y"})
    assert sim.time == "t" and sim.columns["twice"][-1] == pytest.approx(4.0)

    @plotcore.register_model("test_bad")
    def bad(params: dict[str, float], seed: int) -> dict[str, list[float]]:
        return {"t": [0, 1, 2], "y": [1, 2]}

    with pytest.raises(VidgenError, match="different lengths"):
        plotcore.run_registered("test_bad")
    with pytest.raises(VidgenError, match="no model function 'test_parabol' is registered.*did you mean 'test_parabola'"):
        plotcore.run_registered("test_parabol")


def test_parse_system_names() -> None:
    e = parse_system("-k*x + e", ["x", "k", "e"])   # x is an ordinary name; a variable may shadow a constant
    assert e([2.0, 3.0, 1.0])[0] == pytest.approx(-5.0) and e.used == {"x", "k", "e"}
    assert np.allclose(e([np.array([1.0, 2.0]), 1.0, 0.0]), [-1.0, -2.0])
    with pytest.raises(ValueError, match="unknown name 'kk'.*did you mean k"):
        parse_system("kk*x", ["x", "k"])


# ----- growth, rescaling, readouts -------------------------------------------------------------------


def test_growth_head_trail_and_values() -> None:
    t, x, y = [0, 1, 2, 3], [0, 10, 20, 30], [0, 1, 4, 9]
    assert plotcore.grown(t, x, y, -1) == ([], [])
    gx, gy = plotcore.grown(t, x, y, 1.5)
    assert gx == [0, 10, 15] and gy == [0, 1, 2.5]
    assert plotcore.segment(t, x, y, 1.5, 3) == ([15, 20, 30], [2.5, 4, 9])
    assert plotcore.value_at(t, y, 2.5) == 6.5 and plotcore.value_at(t, y, 9) == 9
    assert plotcore.time_like(t, x) and not plotcore.time_like(t, [0, 1, 0])


def test_rescale_schedule_widens_smoothly_and_never_hides_data() -> None:
    times = np.linspace(0, 10, 501)
    values = times * np.sin(times)          # grows past the first domain on both sides
    final = (float(values.min()) - 0.5, float(values.max()) + 0.5)
    first, stops = plotcore.rescale_schedule(times, values, final)
    assert first[1] - first[0] < 0.5 * (final[1] - final[0]) and stops and (stops[-1].lo, stops[-1].hi) == final
    prev = None
    for k, tt in enumerate(times):
        lo, hi = plotcore.domain_at(first, stops, float(tt))
        assert lo <= values[k] + 1e-9 and values[k] <= hi + 1e-9, f"data at t={tt} left the domain"
        if prev is not None:
            assert lo <= prev[0] + 1e-12 and hi >= prev[1] - 1e-12        # it only widens
            assert abs(lo - prev[0]) + abs(hi - prev[1]) < 0.2 * (final[1] - final[0])   # no jumps
        prev = (lo, hi)
    assert plotcore.domain_at(first, stops, 10.0) == final
    fixed_first, _ = plotcore.rescale_schedule(times, values, final, fixed_lo=True)
    assert fixed_first[0] == final[0]
    damped = np.exp(-times / 5) * np.cos(6 * times)   # the largest swing comes first
    calm_first, calm_stops = plotcore.rescale_schedule(times, damped, (-1.1, 1.1))
    assert calm_first == (-1.1, 1.1) and not calm_stops


def test_readouts_and_axes_for_a_domain() -> None:
    assert plotcore.readout_text("x", -0.025812, "m") == "x = −0.0258 m"
    assert plotcore.readout_text("n", 14.0, integer=True) == "n = 14"
    assert plotcore.readout_number(123456.0) == "1.23 × 10⁵" and plotcore.readout_number(12.0) == "12.0"
    spec = plotcore.AxisSpec(label="x", unit="m", max_ticks=6)
    static = plotcore.build_axis([0, 10], spec)
    assert plotcore.axis_for(static, spec, static.lo, static.hi) is static
    zoomed = plotcore.axis_for(static, spec, 2.0, 4.0)
    assert (zoomed.lo, zoomed.hi) == (2.0, 4.0) and all(2 <= v <= 4 for v in zoomed.ticks)
    lay = plotcore.layout_figure(plotcore.Rect(-6, -3, 6, 3), [plotcore.PanelInput((0, 10), (0, 1), spec, spec)], plotcore.approx_measure())[0]
    moved = plotcore.relabel(lay, zoomed, lay.y, plotcore.approx_measure())
    assert moved.plot == lay.plot and moved.x is zoomed and [lab.text for lab in moved.x_labels][0] in ("2.0", "2")


# ----- the plot scene's params and actions ----------------------------------------------------------


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("plot").cls


def test_model_series_resolve_with_units_and_progress() -> None:
    p = cls().validate_params({"models": {"osc": OSC}, "arrange": "columns", "share": False,
                               "panels": [{"series": [{"name": "x", "x": "t", "y": "x", "readout": True}]},
                                                                  {"series": [{"name": "phase", "x": "x", "y": "v", "trail": 2}]}]})
    top, bottom = p.resolve()
    s = top.series[0]
    assert s.spec.model == "osc" and s.live and s.time_col.unit == "s" and len(s.times) == len(s.xs)
    assert top.x.label == "t" and top.x.unit == "s" and top.y.unit == "m" and bottom.series[0].live
    walk = cls().validate_params({"models": {"w": {"kind": "random_walk", "steps": 20}}, "series": [{"name": "w", "x": "n", "y": "x", "live": False}]})
    assert not walk.resolve()[0].series[0].live
    energy = cls().validate_params({"models": {"o": {**OSC, "equations": {"x": "v", "v": "-k*x"}, "params": {"k": 4}, "method": "leapfrog", "step": 0.01,
                                                     "quantities": {"E": "0.5*v^2 + 0.5*k*x^2"}, "conserved": ["E"]}},
                                    "series": [{"name": "E", "x": "t", "y": "E"}]})
    ((model, quantity, drift),) = energy.conservation()
    assert (model, quantity) == ("o", "E") and drift < 1e-3


@pytest.mark.parametrize(
    ("p", "message"),
    [
        ({"models": {"osc": OSC}, "series": [{"name": "a", "x": "t", "y": "x", "model": "oss"}]}, "no model 'oss'; models: osc; did you mean 'osc'"),
        ({"models": {"osc": {**OSC, "rate": 2}}, "series": [{"name": "a", "x": "t", "y": "x"}]}, "kind: ode does not use rate"),
        ({"models": {"osc": {"kind": "poisson"}}, "series": [{"name": "a", "x": "t", "y": "count"}]}, "kind: poisson needs rate"),
        ({"models": {"osc": OSC}, "series": [{"name": "a", "x": "t", "y": "z"}]}, "model 'osc' has no column 'z'"),
        ({"models": {"osc": {**OSC, "method": "leap"}}, "series": [{"name": "a", "x": "t", "y": "x"}]}, "did you mean 'rk4'|not one of rk4, rk45, leapfrog"),
        ({"models": {"osc": {**OSC, "equations": {"x": "v", "v": "-k*y"}}}, "series": [{"name": "a", "x": "t", "y": "x"}]}, "model 'osc' equation for v'"),
        ({"series": [{"name": "a", "x": [0, 1], "y": [1, 2], "readout": True}]}, "readout is for a live series"),
        ({"series": [{"name": "a", "values": [1, 2, 3], "live": True, "trail": 2}]}, "a histogram has no trail"),
        ({"models": {"osc": OSC}, "series": [{"name": "a", "points": [[0, 1]], "model": "osc"}]}, "a model's series names its columns"),
        ({"models": {"a": OSC, "b": OSC}, "series": [{"name": "a", "x": "t", "y": "x"}]}, "with several models, say which"),
    ],
)
def test_model_param_errors(p: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(p)


def test_grow_and_zoom_actions_are_checked(make_project) -> None:
    base = {"models": {"osc": OSC}, "series": [{"name": "x", "x": "t", "y": "x"}]}

    def problems(p: dict[str, Any], actions: list[dict[str, Any]], kind: str = "plot") -> list[str]:
        sc = {"id": "p", "type": kind, "params": p, "beats": [{"text": "one two", "actions": actions}]}
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[sc], narration=NARRATION))))]

    assert problems(base, [{"grow": "series:x", "to": 4}, {"zoom": "axes", "x": [2, 4], "at": "@two"}]) == []
    assert any("grow needs a live series" in m for m in problems({"series": [{"name": "a", "x": [0, 1], "y": [0, 1]}]}, [{"grow": "series1"}]))
    assert any("zoom with x or y zooms the axes of a plot" in m for m in problems({"title": "x", "values": [1, 2]}, [{"zoom": "bar:x", "x": [0, 1]}],
                                                                                  kind="histogram"))
    assert any("x must be [from, to] with to > from" in m for m in problems(base, [{"zoom": "axes", "x": [4, 2]}]))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_live_plots_render(size: tuple[int, int], make_project, media: Path) -> None:
    osc = {"title": "Oscillator", "models": {"osc": OSC}, "arrange": "columns", "share": False,
           "panels": [{"series": [{"name": "x", "x": "t", "y": "x", "readout": True}]}, {"series": [{"name": "phase", "x": "x", "y": "v", "trail": 2}]}]}
    decay = {"models": {"d": {"kind": "ode", "equations": {"N": "-0.3*N"}, "initial": {"N": 1000}, "t": [0, 10], "samples": 30}},
             "series": [{"name": "atoms", "x": "t", "y": "N", "style": "points"}], "fits": [{"series": "atoms", "model": "exponential"}]}
    walk = {"models": {"w": {"kind": "random_walk", "steps": 120, "seed": 7}}, "series": [{"name": "walker", "x": "n", "y": "x", "readout": True}]}
    values = [float(v) for v in np.random.default_rng(3).normal(5.0, 1.0, 300)]
    events = {"series": [{"name": "events", "values": values, "bins": 12, "bin_range": [1, 9], "style": "points", "y_err": "sqrt", "live": True,
                          "readout": True}], "fits": [{"series": "events", "model": "normal"}]}
    scenes = [
        {"id": "osc", "type": "plot", "params": osc, "beats": [{"text": "it swings and slows down"}, {"text": "zoom in", "actions": [{"zoom": "panel1", "x": [2, 4]}]}]},
        {"id": "decay", "type": "plot", "params": decay,
         "beats": [{"text": "half of it", "actions": [{"grow": "series:atoms", "to": 4}]}, {"text": "the rest and a fit", "actions": [{"grow": "series:atoms"}, {"fit": "fit1", "at": "@fit"}]}]},
        {"id": "walk", "type": "plot", "params": walk, "beats": [{"text": "a random walk wanders away"}]},
        {"id": "events", "type": "plot", "params": events, "beats": [{"text": "events arrive one by one"}, {"text": "a normal fits them"}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "osc", media, size)
    assert all(s._shown[i] == s._series[i].times[-1] for i in s._shown)          # grown to the end
    assert s._zoomed == {} and all(s._view[k] is s._lays[k] for k in range(len(s._lays)))   # the zoom went back
    assert all(len(h.family_members_with_points()) for h in s._heads.values()) and s._readouts
    d = render(project, "decay", media, size)
    (fit,) = d.fit_results
    assert fit.result.params[1] == pytest.approx(-0.3, abs=1e-3) and d.is_shown("fit1") and d._shown[0] == 10
    w = render(project, "walk", media, size)
    assert w._shown == {0: 120.0} and not w._growing
    assert w._schedule and w._domains[0]["y"] == w._dom(w._lays[0].y)                # rescaled to the final domain
    e = render(project, "events", media, size)
    (hist,) = e._series
    heights, errors = e._hist_heights(0)
    assert heights == list(hist.ys) and errors == pytest.approx(np.sqrt(hist.hist.counts))   # filled with every value
    assert e._hist_heights(0, 10)[0] != heights and sum(e._hist_heights(0, 10)[0]) <= 10
    assert e._schedule[0]["y"][0][1] < e._dom(e._lays[0].y)[1] and e.is_shown("fit1")
