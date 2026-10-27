"""Models that generate data for live plots (Phase W, DESIGN §97.7), without manim and
deterministic: the same inputs (and seed) always give the same numbers, on every machine.

- :func:`simulate_ode` — a system of ODEs written as safe expressions (``x' = v``, ``v' = -k*x -
  c*v``) with named parameters and initial conditions, integrated by RK4 (fixed step), RK45
  (adaptive) or velocity Verlet / leapfrog (symplectic; for ``x' = v``, ``v' = a(t, x)``);
- :func:`simulate_recurrence` — discrete maps ``x[n+1] = f(x[n], n)`` (the logistic map,
  compound growth);
- :func:`random_walk` and :func:`poisson_process` — seeded stochastic processes on an own
  generator (:class:`SplitMix64`), so a seed means the same walk with any numpy version;
- :func:`register_model` — a Python function registered by name (through ``vidgen.api``) for
  anything else.

Each returns a :class:`Simulation`: named columns (the first is the progress column — ``t`` or
``n``), units, derived ``quantities`` (expressions of the columns, e.g. an energy) and the
relative drift of quantities declared ``conserved`` (for lint)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from vidgen.errors import VidgenError
from vidgen.mathexpr import MATH_FUNCTIONS, SystemExpression, parse_system

from .data import Column, Table, did_you_mean
from .integrate import IntegrationError, rk4, rk45, verlet

#: Integration methods of :func:`simulate_ode`.
ODE_METHODS = ("rk4", "rk45", "leapfrog")
#: Aliases of the methods.
METHOD_ALIASES = {"verlet": "leapfrog", "velocity_verlet": "leapfrog", "symplectic": "leapfrog", "dopri": "rk45", "adaptive": "rk45",
                  "runge_kutta": "rk4"}
#: Outputs of an integration by default (the drawing does not need every step).
DEFAULT_SAMPLES = 600
#: A step larger than this share of the time span is refused.
MAX_STEP_SHARE = 0.25


@dataclass(frozen=True)
class Simulation:
    """A model's output: ``columns`` (name -> values, in order; the first is the progress column
    ``time``), their ``units``, and ``drift`` (quantity -> relative drift: max |q − q₀| over
    max(|q₀|, the quantity's typical size), for the quantities declared conserved)."""

    source: str
    columns: dict[str, np.ndarray]
    units: dict[str, str] = field(default_factory=dict)
    drift: dict[str, float] = field(default_factory=dict)

    @property
    def time(self) -> str:
        """The name of the progress column (``t``, ``n`` or the first column)."""
        return next(iter(self.columns))

    def table(self) -> Table:
        """The columns as a :class:`~vidgen.plotcore.Table` (series pick them by name)."""
        return Table(self.source, tuple(Column(n, self.units.get(n, ""), tuple(float(v) for v in vals)) for n, vals in self.columns.items()))


def conservation_drift(values: Sequence[float]) -> float:
    """How far a quantity that should stay constant moved: max |q − q₀| relative to max(|q₀|,
    the largest |q|) (0 for a constant; ``inf`` when it is not finite)."""
    q = np.asarray(values, dtype=float)
    if not len(q) or not np.all(np.isfinite(q)):
        return math.inf
    scale = max(abs(float(q[0])), float(np.max(np.abs(q))))
    return float(np.max(np.abs(q - q[0]))) / scale if scale > 0 else 0.0


def _check_name(name: str, where: str) -> None:
    if not name.isidentifier():
        raise VidgenError(f"{where}: '{name}' is not a name (letters, digits and _, not starting with a digit)")
    if name in MATH_FUNCTIONS:
        raise VidgenError(f"{where}: '{name}' is the name of a function; pick another")


def equation_variable(key: str) -> str:
    """The variable an equation's key names: ``x``, ``dx/dt``, ``x'`` and ``x_next`` -> ``x``."""
    k = key.strip().replace(" ", "")
    if k.startswith("d") and "/d" in k:
        k = k[1 : k.index("/d")]
    k = k.rstrip("'")
    for end in ("[n+1]", "_next", "(n+1)"):
        if k.endswith(end):
            k = k[: -len(end)]
    return k


def _compile(text: str, names: Sequence[str], where: str) -> SystemExpression:
    try:
        return parse_system(str(text), names)
    except ValueError as exc:
        raise VidgenError(f"{where}: {exc}") from None


def _quantities(columns: dict[str, np.ndarray], quantities: Mapping[str, str], params: Mapping[str, float], where: str) -> None:
    """Add each derived quantity (an expression of the columns and parameters) as a column."""
    for name, text in quantities.items():
        _check_name(name, f"{where} quantities")
        if name in columns or name in params:
            raise VidgenError(f"{where} quantities: '{name}' is already a {'column' if name in columns else 'parameter'}; pick another name")
        names = [*columns, *params]
        expr = _compile(text, names, f"{where} quantity {name}")
        n = len(next(iter(columns.values())))
        values = [columns[c] for c in columns] + [np.full(n, float(params[p])) for p in params]
        columns[name] = np.broadcast_to(expr(values), (n,)).astype(float)


def _finish(source: str, columns: dict[str, np.ndarray], units: Mapping[str, str], quantities: Mapping[str, str], params: Mapping[str, float],
            conserved: Sequence[str], where: str) -> Simulation:
    _quantities(columns, quantities, params, where)
    for key in units:
        if key not in columns:
            raise VidgenError(f"{where} units: no column '{key}' (columns: {', '.join(columns)})" + did_you_mean(key, list(columns)))
    drift = {}
    for name in conserved:
        if name not in columns:
            raise VidgenError(f"{where} conserved: no column or quantity '{name}' (columns: {', '.join(columns)})" + did_you_mean(name, list(columns)))
        drift[name] = conservation_drift(columns[name])
    return Simulation(source, columns, dict(units), drift)


def simulate_ode(
    equations: Mapping[str, str],
    initial: Mapping[str, float],
    *,
    params: Mapping[str, float] | None = None,
    t: tuple[float, float] = (0.0, 10.0),
    step: float | None = None,
    method: str = "rk4",
    rtol: float = 1e-6,
    samples: int | None = None,
    quantities: Mapping[str, str] | None = None,
    conserved: Sequence[str] = (),
    units: Mapping[str, str] | None = None,
    time: str = "t",
    source: str = "model",
) -> Simulation:
    """Integrate ``d(var)/dt = expression`` for each equation (keys ``x``, ``dx/dt`` or ``x'``)
    from ``initial`` over ``t`` = (start, end): columns ``t``, each state variable (in the
    equations' order), then the ``quantities``. Expressions may use the state variables, the
    ``params`` and ``t``. ``method``: ``rk4`` (fixed ``step``; default span/1000), ``rk45``
    (adaptive, relative tolerance ``rtol``), ``leapfrog`` (velocity Verlet; the equations must
    pair each position with a velocity, ``x' = v``, and accelerations must not use velocities).
    Raises ``VidgenError`` naming the problem: an unknown name (did-you-mean), a missing or
    unknown initial condition, a step too large, a blow-up or a stiff system."""
    where = source
    params = dict(params or {})
    method = METHOD_ALIASES.get(method, method)
    if method not in ODE_METHODS:
        raise VidgenError(f"{where}: method '{method}' is not one of {', '.join(ODE_METHODS)}" + did_you_mean(method, list(ODE_METHODS)))
    if not equations:
        raise VidgenError(f"{where}: give equations, e.g. {{x: v, v: \"-k*x\"}} for x' = v, v' = -k·x")
    variables = []
    for key in equations:
        var = equation_variable(key)
        _check_name(var, f"{where} equations")
        if var in variables:
            raise VidgenError(f"{where} equations: '{var}' has two equations")
        variables.append(var)
    for p in params:
        _check_name(p, f"{where} params")
        if p in variables:
            raise VidgenError(f"{where}: '{p}' is both a variable and a parameter")
    if time in variables or time in params:
        raise VidgenError(f"{where}: '{time}' is the time; name the variable or parameter otherwise")
    missing = [v for v in variables if v not in initial]
    if missing:
        raise VidgenError(f"{where}: no initial condition for {', '.join(missing)}; add initial: {{{', '.join(f'{v}: 0' for v in missing)}}}")
    unknown = [k for k in initial if k not in variables]
    if unknown:
        raise VidgenError(f"{where} initial: '{unknown[0]}' is not a variable of the equations ({', '.join(variables)})" + did_you_mean(unknown[0], variables))
    t0, t1 = float(t[0]), float(t[1])
    if not t1 > t0:
        raise VidgenError(f"{where}: t must run from a start to a later end, got [{t0:g}, {t1:g}]")
    span = t1 - t0
    if step is not None:
        if step <= 0:
            raise VidgenError(f"{where}: step must be positive, got {step:g}")
        if step > span * MAX_STEP_SHARE:
            raise VidgenError(f"{where}: step {step:g} is too large for t from {t0:g} to {t1:g}; use at most {span * MAX_STEP_SHARE:g} "
                              f"(about {span / 1000:g}, a thousandth of the span, is usual)")
    names = [*variables, *params, time]
    exprs = [_compile(equations[k], names, f"{where} equation for {v}'") for k, v in zip(equations, variables)]
    pvals = [float(params[p]) for p in params]
    y0 = np.array([float(initial[v]) for v in variables])
    n = len(variables)

    def rhs(tt: float, y: np.ndarray) -> np.ndarray:
        values = [*y.tolist(), *pvals, tt]
        return np.array([e.scalar(values) for e in exprs])

    try:
        with np.errstate(all="ignore"):
            times, states = _integrate(method, rhs, equations, variables, exprs, params, pvals, y0, t0, t1, step, span, samples, rtol, where, time)
    except IntegrationError as error:
        name = variables[error.variable] if error.variable is not None and error.variable < n else None
        if error.kind == "blow_up":
            what = f"{name} blows up" if name else "the solution blows up"
            hint = f"try a smaller step (now {step or span / 1000:g}) or method: rk45" if method != "rk45" else "check the equations and parameters (a sign?)"
            raise VidgenError(f"{where}: {what} near {time} = {error.time:.4g} (it grows without bound or is not a number): the system is unstable "
                              f"there or the step is too large; {hint}") from None
        raise VidgenError(f"{where}: {error}") from None
    columns: dict[str, np.ndarray] = {time: np.asarray(times, dtype=float)}
    for k, v in enumerate(variables):
        columns[v] = np.asarray(states[:, k], dtype=float)
    return _finish(source, columns, units or {}, quantities or {}, params, conserved, where)


def _integrate(method: str, rhs: Callable[[float, np.ndarray], np.ndarray], equations: Mapping[str, str], variables: list[str],
               exprs: list[SystemExpression], params: Mapping[str, float], pvals: list[float], y0: np.ndarray, t0: float, t1: float,
               step: float | None, span: float, samples: int | None, rtol: float, where: str, time: str) -> tuple[np.ndarray, np.ndarray]:
    if method == "leapfrog":
        return _leapfrog(equations, variables, exprs, params, pvals, y0, t0, t1, step or span / 1000, samples, where, time)
    if method == "rk4":
        return rk4(rhs, t0, y0, t1, step or span / 1000, samples=samples or DEFAULT_SAMPLES)
    outs = np.linspace(t0, t1, (samples or DEFAULT_SAMPLES) + 1)
    size = float(np.max(np.abs(y0))) if len(y0) and np.any(y0 != 0) else 1.0   # the absolute floor follows the model's own scale
    _, states = rk45(rhs, t0, y0, t1, times=outs[1:], rtol=rtol, atol=rtol * 1e-3 * size, first_step=step, max_step=span / 20)
    return outs, np.vstack([y0, states])


def leapfrog_pairs(equations: Mapping[str, str]) -> dict[str, str]:
    """``{position: velocity}`` for each equation ``x' = v`` whose right side is just another
    variable of the system."""
    variables = [equation_variable(k) for k in equations]
    out = {}
    for key, text in equations.items():
        rhs = str(text).strip()
        if rhs in variables and rhs != equation_variable(key):
            out[equation_variable(key)] = rhs
    return out


def _leapfrog(equations: Mapping[str, str], variables: list[str], exprs: list[SystemExpression], params: Mapping[str, float], pvals: list[float],
              y0: np.ndarray, t0: float, t1: float, step: float, samples: int | None, where: str, time: str) -> tuple[np.ndarray, np.ndarray]:
    pairs = leapfrog_pairs(equations)
    positions = list(pairs)
    velocities = [pairs[p] for p in positions]
    others = [v for v in variables if v not in positions and v not in velocities]
    if not positions or others or len(set(velocities)) != len(velocities) or set(positions) & set(velocities):
        raise VidgenError(f"{where}: method: leapfrog needs every position paired with a velocity (x' = v, v' = an acceleration); "
                          f"{', '.join(others) or 'the equations'} {'do' if len(others) != 1 else 'does'} not fit; use rk4 or rk45")
    for vel in velocities:
        e = exprs[variables.index(vel)]
        bad = sorted(e.used & set(velocities))
        if bad:
            raise VidgenError(f"{where}: method: leapfrog needs accelerations that do not depend on velocities, but {vel}' uses {', '.join(bad)} "
                              "(friction, drag); use rk4 or rk45")
    pos_idx = [variables.index(p) for p in positions]
    vel_idx = [variables.index(v) for v in velocities]
    acc = [exprs[i] for i in vel_idx]

    def accel(tt: float, x: np.ndarray) -> np.ndarray:
        y = np.zeros(len(variables))
        y[pos_idx] = x
        values = [*y.tolist(), *pvals, tt]
        return np.array([e.scalar(values) for e in acc])

    times, xs, vs = verlet(accel, t0, y0[pos_idx], y0[vel_idx], t1, step, samples=samples or DEFAULT_SAMPLES)
    states = np.zeros((len(times), len(variables)))
    states[:, pos_idx] = xs
    states[:, vel_idx] = vs
    return times, states


def simulate_recurrence(
    equations: Mapping[str, str],
    initial: Mapping[str, float],
    *,
    params: Mapping[str, float] | None = None,
    steps: int = 50,
    quantities: Mapping[str, str] | None = None,
    conserved: Sequence[str] = (),
    units: Mapping[str, str] | None = None,
    index: str = "n",
    source: str = "model",
) -> Simulation:
    """Iterate ``var[n+1] = expression`` (keys ``x``, ``x_next`` or ``x[n+1]``; the right
    sides read the values at ``n``, the parameters and ``n``) ``steps`` times from
    ``initial``: columns ``n`` (0 … steps) and each variable."""
    where = source
    params = dict(params or {})
    if not equations:
        raise VidgenError(f"{where}: give equations, e.g. {{x: \"r*x*(1 - x)\"}} for the logistic map")
    if steps < 1 or steps > 100_000:
        raise VidgenError(f"{where}: steps must be 1 to 100000, got {steps}")
    variables = []
    for key in equations:
        var = equation_variable(key)
        _check_name(var, f"{where} equations")
        if var in variables:
            raise VidgenError(f"{where} equations: '{var}' has two equations")
        variables.append(var)
    if index in variables or index in params:
        raise VidgenError(f"{where}: '{index}' is the step number; name the variable or parameter otherwise")
    missing = [v for v in variables if v not in initial]
    if missing:
        raise VidgenError(f"{where}: no initial value for {', '.join(missing)}; add initial: {{{', '.join(f'{v}: 0' for v in missing)}}}")
    unknown = [k for k in initial if k not in variables]
    if unknown:
        raise VidgenError(f"{where} initial: '{unknown[0]}' is not a variable of the equations ({', '.join(variables)})" + did_you_mean(unknown[0], variables))
    names = [*variables, *params, index]
    exprs = [_compile(equations[k], names, f"{where} equation for {v}") for k, v in zip(equations, variables)]
    pvals = [float(params[p]) for p in params]
    y = np.array([float(initial[v]) for v in variables])
    rows = [y]
    for n in range(steps):
        values = [*y.tolist(), *pvals, float(n)]
        with np.errstate(all="ignore"):
            y = np.array([e.scalar(values) for e in exprs])
        if not np.all(np.isfinite(y)) or np.any(np.abs(y) > 1e300):
            k = int(np.flatnonzero(~np.isfinite(y) | (np.abs(y) > 1e300))[0])
            raise VidgenError(f"{where}: {variables[k]} is not a finite number after step {n + 1} (it grows without bound or divides by 0)")
        rows.append(y)
    arr = np.array(rows)
    columns: dict[str, np.ndarray] = {index: np.arange(steps + 1, dtype=float)}
    for k, v in enumerate(variables):
        columns[v] = arr[:, k]
    return _finish(source, columns, units or {}, quantities or {}, params, conserved, where)


class SplitMix64:
    """A small 64-bit generator (Steele, Lea and Flood's SplitMix64): the same seed gives the
    same numbers everywhere (unlike numpy's streams, which may change between versions)."""

    _MASK = (1 << 64) - 1

    def __init__(self, seed: int) -> None:
        self.state = int(seed) & self._MASK

    def next(self) -> int:
        """The next 64-bit integer."""
        self.state = (self.state + 0x9E3779B97F4A7C15) & self._MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self._MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self._MASK
        return z ^ (z >> 31)

    def uniform(self) -> float:
        """A float in [0, 1) (53 random bits)."""
        return (self.next() >> 11) * (1.0 / (1 << 53))

    def normal(self) -> float:
        """A standard normal number (Box–Muller, one of the pair)."""
        u1 = 1.0 - self.uniform()
        u2 = self.uniform()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)


def random_walk(
    *,
    steps: int = 100,
    seed: int = 1,
    step: float = 1.0,
    p: float = 0.5,
    dims: int = 1,
    distribution: str = "lattice",
    start: Sequence[float] | None = None,
    quantities: Mapping[str, str] | None = None,
    units: Mapping[str, str] | None = None,
    source: str = "model",
) -> Simulation:
    """A seeded random walk of ``steps`` steps: columns ``n``, ``x`` (and ``y`` for ``dims:
    2``), ``distance`` (from the start). ``lattice``: ±``step`` (in 1-D up with probability
    ``p``; in 2-D one of four directions); ``gaussian``: normal steps of standard deviation
    ``step`` on each axis."""
    where = source
    if dims not in (1, 2):
        raise VidgenError(f"{where}: dims must be 1 or 2, got {dims}")
    if distribution not in ("lattice", "gaussian"):
        raise VidgenError(f"{where}: distribution must be lattice or gaussian, got '{distribution}'" + did_you_mean(distribution, ["lattice", "gaussian"]))
    if not 0 <= p <= 1:
        raise VidgenError(f"{where}: p must be a probability (0 to 1), got {p:g}")
    if steps < 1 or steps > 100_000:
        raise VidgenError(f"{where}: steps must be 1 to 100000, got {steps}")
    gen = SplitMix64(seed)
    pos = np.array(list(start) if start is not None else [0.0] * dims, dtype=float)
    if len(pos) != dims:
        raise VidgenError(f"{where}: start needs {dims} number{'s' if dims > 1 else ''}")
    origin = pos.copy()
    rows = [pos.copy()]
    for _ in range(steps):
        if distribution == "gaussian":
            pos = pos + np.array([gen.normal() * step for _ in range(dims)])
        elif dims == 1:
            pos = pos + (step if gen.uniform() < p else -step)
        else:
            k = gen.next() % 4
            pos = pos + step * np.array(((1, 0), (-1, 0), (0, 1), (0, -1))[k], dtype=float)
        rows.append(pos.copy())
    arr = np.array(rows)
    columns: dict[str, np.ndarray] = {"n": np.arange(steps + 1, dtype=float), "x": arr[:, 0]}
    if dims == 2:
        columns["y"] = arr[:, 1]
    columns["distance"] = np.linalg.norm(arr - origin, axis=1)
    return _finish(source, columns, units or {}, quantities or {}, {}, (), where)


def poisson_process(
    *,
    rate: float,
    t: tuple[float, float] = (0.0, 10.0),
    seed: int = 1,
    quantities: Mapping[str, str] | None = None,
    units: Mapping[str, str] | None = None,
    source: str = "model",
) -> Simulation:
    """A seeded Poisson process of ``rate`` events per unit time over ``t``: columns ``t`` and
    ``count`` as a staircase (the count steps up at each event), and ``expected`` (rate·t)."""
    where = source
    if rate <= 0:
        raise VidgenError(f"{where}: rate must be positive, got {rate:g}")
    t0, t1 = float(t[0]), float(t[1])
    if not t1 > t0:
        raise VidgenError(f"{where}: t must run from a start to a later end, got [{t0:g}, {t1:g}]")
    if rate * (t1 - t0) > 50_000:
        raise VidgenError(f"{where}: about {rate * (t1 - t0):,.0f} events expected (at most 50000); lower the rate or shorten t")
    gen = SplitMix64(seed)
    times, counts = [t0], [0.0]
    now, n = t0, 0
    while True:
        now += -math.log(1.0 - gen.uniform()) / rate
        if now >= t1:
            break
        times += [now, now]
        counts += [float(n), float(n + 1)]
        n += 1
    times.append(t1)
    counts.append(float(n))
    tt = np.array(times)
    columns: dict[str, np.ndarray] = {"t": tt, "count": np.array(counts), "expected": rate * (tt - t0)}
    return _finish(source, columns, units or {}, quantities or {}, {"rate": rate}, (), where)


#: Functions registered with :func:`register_model`: name -> function(params, seed) -> columns.
_REGISTERED: dict[str, Callable[..., Mapping[str, Sequence[float]]]] = {}


def register_model(name: str) -> Callable[[Callable[..., Mapping[str, Sequence[float]]]], Callable[..., Mapping[str, Sequence[float]]]]:
    """Register a Python function as a model a plot can name (``kind: function, function:
    <name>``): ``fn(params: dict[str, float], seed: int) -> {column: values}``, the first
    column being the progress (time) column, every column of equal length. It must be
    deterministic (same params and seed, same numbers). Exported by ``vidgen.api``."""
    if not isinstance(name, str) or not name.isidentifier():
        raise VidgenError(f"register_model: '{name}' is not a name (letters, digits, _)")

    def decorate(fn: Callable[..., Mapping[str, Sequence[float]]]) -> Callable[..., Mapping[str, Sequence[float]]]:
        if not callable(fn):
            raise VidgenError(f"register_model('{name}') must decorate a function")
        _REGISTERED[name] = fn
        return fn

    return decorate


def registered_models() -> list[str]:
    """The names of the registered model functions."""
    return sorted(_REGISTERED)


def run_registered(
    name: str,
    *,
    params: Mapping[str, float] | None = None,
    seed: int = 1,
    quantities: Mapping[str, str] | None = None,
    conserved: Sequence[str] = (),
    units: Mapping[str, str] | None = None,
    source: str = "model",
) -> Simulation:
    """Call the function registered as ``name`` and check what it returns."""
    where = source
    fn = _REGISTERED.get(name)
    if fn is None:
        known = registered_models()
        raise VidgenError(f"{where}: no model function '{name}' is registered ({', '.join(known) or 'none'}; register one with "
                          "@vidgen.api.register_model(\"name\") in an extension)" + did_you_mean(name, known))
    params = dict(params or {})
    try:
        out = fn(dict(params), int(seed))
    except VidgenError:
        raise
    except Exception as exc:   # an author's function: report, do not crash the render
        raise VidgenError(f"{where}: the model function '{name}' failed: {type(exc).__name__}: {exc}") from None
    if not isinstance(out, Mapping) or not out:
        raise VidgenError(f"{where}: the model function '{name}' must return {{column: values}}, got {type(out).__name__}")
    columns: dict[str, np.ndarray] = {}
    length = None
    for key, values in out.items():
        _check_name(str(key), f"{where} (function '{name}')")
        try:
            arr = np.asarray(values, dtype=float).reshape(-1)
        except (TypeError, ValueError):
            raise VidgenError(f"{where}: the model function '{name}' returned column '{key}' that is not numbers") from None
        if length is not None and len(arr) != length:
            raise VidgenError(f"{where}: the model function '{name}' returned columns of different lengths ('{key}': {len(arr)}, not {length})")
        length = len(arr)
        columns[str(key)] = arr
    if not length or length < 2:
        raise VidgenError(f"{where}: the model function '{name}' returned fewer than two rows")
    first = next(iter(columns.values()))
    if np.any(~np.isfinite(first)) or np.any(np.diff(first) < 0):
        raise VidgenError(f"{where}: the first column of '{name}' ('{next(iter(columns))}') is its progress (time) and must not decrease")
    return _finish(source, columns, units or {}, quantities or {}, params, conserved, where)


__all__ = [
    "DEFAULT_SAMPLES",
    "METHOD_ALIASES",
    "ODE_METHODS",
    "Simulation",
    "SplitMix64",
    "conservation_drift",
    "equation_variable",
    "leapfrog_pairs",
    "poisson_process",
    "random_walk",
    "register_model",
    "registered_models",
    "run_registered",
    "simulate_ode",
    "simulate_recurrence",
]
