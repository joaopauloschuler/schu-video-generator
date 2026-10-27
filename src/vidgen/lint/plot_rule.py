"""The plot lint rules (DESIGN.md §97.11): a ``plot`` scene's figure and narration checked against
its params and data (resolved as the render resolves them, no render).

``plot_units`` (an axis of a physical quantity without its unit), ``plot_log`` (error bars, fits,
bands, reference lines at or below zero on a log axis; data refused when resolved),
``plot_errors`` (error bars without a stated meaning, or said to mean something else),
``plot_series`` (series that cannot be told apart), ``plot_truncated`` (bars not starting at
zero, also in ``bar_chart``), ``plot_conserved`` (a model's conserved quantity drifting) and
``plot_fit_claims`` (a fitted value said differently from the fit). The text knowledge is in
:mod:`vidgen.quantities.accuracy`; the runner adds :func:`plot_issues` to
:attr:`SceneContext.science`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.lint.calc_rule import screen_texts
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.lint.science_rule import ScienceIssue, _issues, _params, _scene_class
from vidgen.quantities import accuracy as qa

if TYPE_CHECKING:
    from vidgen.config import LintRules, SceneConfig
    from vidgen.project import Project

#: The rules of this module, in :data:`vidgen.config.LINT_RULES` order.
PLOT_RULES: tuple[str, ...] = ("plot_units", "plot_log", "plot_errors", "plot_series", "plot_truncated", "plot_conserved", "plot_fit_claims")
#: Axis titles naming a physical quantity, and an SI unit to suggest.
QUANTITY_UNITS: tuple[tuple[str, str], ...] = (
    (r"time|elapsed\s+time|duration|age|period|half-life", "s"), (r"distance|length|height|depth|altitude|radius|diameter|wavelength|displacement", "m"),
    (r"mass", "kg"), (r"energy|kinetic\s+energy|potential\s+energy", "J"), (r"speed|velocity", "m/s"), (r"acceleration", "m/s²"),
    (r"temperature", "K"), (r"pressure", "Pa"), (r"force", "N"), (r"power", "W"), (r"voltage|membrane\s+potential", "V"),
    (r"current", "A"), (r"charge", "C"), (r"activity", "Bq"), (r"dose", "Gy"), (r"concentration", "mol/L"),
)
_QUANTITY = re.compile(rf"^(?:the\s+)?(?:{'|'.join(p for p, _ in QUANTITY_UNITS)})$", re.IGNORECASE)
#: Titles that are pure numbers by nature, or already carry a unit.
_UNITLESS = re.compile(r"\b(?:relative|normali[sz]ed|fraction|ratio|share|index|arbitrary|a\.u\.|log|number|count|probability|proportion|"
                       r"percent|score|efficiency|scaled|dimensionless)\b|%|\(.*\)|\[.*\]|\s/\s|\bin\s+\w+|\bper\s+\w+", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"^(?:series|data|line|set|curve|trace|y|s|plot|values?)\s*[_ -]?\d*$", re.IGNORECASE)


def plot_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every plot finding of scene ``scene_id`` (rules turned off are skipped)."""
    spec = project.scene(scene_id)
    on = {name for name in PLOT_RULES if getattr(rules, name).severity != "off"}
    if not on or spec.type not in ("plot", "bar_chart"):
        return []
    first = spec.beats[0].id if spec.beats else None
    out: list[ScienceIssue] = []

    def add(rule_name: str, message: str, beat: str | None = first, severity: str | None = None) -> None:
        if rule_name in on:
            out.append(ScienceIssue(rule_name, beat, message, severity))

    params = _params(spec)
    if params is None:
        return out
    if spec.type == "bar_chart":
        _bar_chart(params, add)
        return out
    try:
        resolved = params.resolve(project)
    except Exception as error:  # noqa: BLE001 - validation reports the others
        text = str(error)
        if "log scale" in text:
            add("plot_log", f"{text} (found when the plot's data were read: the render would stop here)")
        resolved = None
    if resolved is not None:
        _units(params, resolved, add)
        _log(params, resolved, add)
        _truncated(resolved, add)
        _fit_claims(spec, resolved, rules, add)
    _errors(spec, params, add)
    _series(params, add)
    if "plot_conserved" in on:
        _conserved(params, rules, add)
    return out


# ----- the checks ------------------------------------------------------------------------------------------


def _axes(resolved: Any) -> Iterator[tuple[int, str, Any]]:
    """``(panel index, axis name, AxisSpec)`` once per distinct axis."""
    seen: set[int] = set()
    for k, panel in enumerate(resolved.panels):
        for name in ("x", "y"):
            spec = getattr(panel, name)
            if id(spec) in seen:
                continue
            seen.add(id(spec))
            yield k, name, spec


def _where(resolved: Any, k: int, axis: str) -> str:
    return f"panels[{k + 1}].{axis}" if len(resolved.panels) > 1 else axis


def _units(params: Any, resolved: Any, add: Any) -> None:
    named: set[tuple[str, str]] = set()
    for k, axis, spec in _axes(resolved):
        label = str(spec.label).strip()
        if spec.unit or not label or (label, axis) in named:
            continue
        named.add((label, axis))
        if _QUANTITY.match(label) and not _UNITLESS.search(label):
            unit = next(u for p, u in QUANTITY_UNITS if re.fullmatch(rf"(?:the\s+)?(?:{p})", label, re.IGNORECASE))
            add("plot_units", f"{_where(resolved, k, axis)} axis '{label}' has no unit: a viewer cannot read its numbers; add {axis}: "
                              f"{{unit: {unit}}} (or the unit in the column header, '{label} ({unit})')")
    for i, f in enumerate(params.fits, start=1):
        units = [v.unit for v in f.params.values() if getattr(v, "unit", "")]
        fit = next((r for r in resolved.fits if r.spec is f), None)
        if units and fit is not None and not resolved.panels[fit.panel].x.unit:
            add("plot_units", f"fits[{i}] ({f.label()}) gives its parameters units ({', '.join(units)}) but the x axis has none: add x: "
                              f"{{unit: ...}} so the axis says what the fit's units are measured against")


def _log(params: Any, resolved: Any, add: Any) -> None:
    for k, panel in enumerate(resolved.panels):
        for axis in ("x", "y"):
            spec = getattr(panel, axis)
            if spec.scale != "log":
                continue
            where = f"the log {_where(resolved, k, axis)} axis"
            for s in panel.series:
                err = s.y_err if axis == "y" else s.x_err
                if err is None:
                    continue
                base = np.asarray(s.ys if axis == "y" else s.xs, dtype=float)
                low = base - err[0]
                bad = int(np.sum(np.isfinite(low) & (low <= 0)))
                if bad:
                    add("plot_log", f"series '{s.spec.name}': {bad} error bar{'s' if bad > 1 else ''} reach{'' if bad > 1 else 'es'} zero or below "
                                    f"on {where} (drawn to the axis edge, which looks like a huge error): give asymmetric errors that stay "
                                    f"positive (y_err: {{minus, plus}}), or use a linear axis")
            for f in resolved.fits:
                if f.panel != k:
                    continue
                xs = f.curve_x(f.lo, f.hi, panel.x.scale)
                ys = np.asarray(f.result(xs), dtype=float)
                what = f"fit '{f.spec.label()}'"
                if axis == "y" and np.any(np.isfinite(ys) & (ys <= 0)):
                    add("plot_log", f"{what}: the fitted curve reaches zero or below on {where} (that part is not drawn): fit a model "
                                    f"that stays positive (exponential, power), or restrict range")
                elif axis == "y" and f.spec.band != "none":
                    lo, _ = f.result.band(xs, level=f.spec.level, kind=f.spec.band)
                    if np.any(np.isfinite(lo) & (lo <= 0)):
                        add("plot_log", f"{what}: its {f.spec.band} band reaches zero or below on {where} (clipped at the axis edge): the "
                                        f"band is too wide for a log axis; use a linear axis or band: none")
            for i, a in enumerate(params.annotations, start=1):
                if (a.panel or 1) - 1 != k:
                    continue
                values = []
                if axis == "y" and a.type in ("hline", "yrange"):
                    values = [a.y] if a.type == "hline" else list(a.y)
                if axis == "x" and a.type in ("vline", "xrange"):
                    values = [a.x] if a.type == "vline" else list(a.x)
                if any(v is not None and v <= 0 for v in values):
                    add("plot_log", f"annotations[{i}] ({a.type}) is at zero or below on {where}, which a log axis cannot show: move it, "
                                    f"or use scale: symlog")


def _truncated(resolved: Any, add: Any) -> None:
    for k, panel in enumerate(resolved.panels):
        bars = [s for s in panel.series if s.hist is not None and s.spec.drawn_as == "bars"]
        if bars and panel.y.breaks:
            add("plot_truncated", f"series '{bars[0].spec.name}': bars on a y axis with a break ({_where(resolved, k, 'y')}): their heights no "
                                  f"longer compare; drop the break, or draw style: step / points", severity=None)


def _bar_chart(params: Any, add: Any) -> None:
    base = float(params.baseline)
    values = [v for row in [params.values, *params.changes] for v in row]
    if base != 0 and values and (all(v >= base for v in values) or all(v <= base for v in values)):
        add("plot_truncated", f"baseline {base:g}: every bar starts at {base:g}, not 0, so their lengths exaggerate the differences (a bar "
                              f"twice as long is not twice the value); say so on screen, or use baseline: 0")


def _errors(spec: SceneConfig, params: Any, add: Any) -> None:
    declared: set[str] = set()
    for s in params.all_series():
        if s.y_err is None and s.x_err is None:
            continue
        if s.meaning is None:
            add("plot_errors", f"series '{s.name}': error bars without a stated meaning: a viewer cannot tell a standard deviation from a "
                               f"standard error or a confidence interval; add error: sd | sem | ci95 | range | poisson | other (the legend "
                               f"then says it)")
        else:
            declared.add(s.meaning)
    for beat in spec.beats:
        for claim in qa.error_meaning_claims(str(beat.text), declared):
            add("plot_errors", f'"{claim.quote}": {claim.message}', beat.id)


def _series(params: Any, add: Any) -> None:
    cls = _scene_class("plot")
    legends = cls._legend_panels(params) if cls is not None else []
    named = {str(a.series) for a in params.annotations if a.type in ("label", "arrow") and a.series is not None}
    for k, panel in enumerate(params.panel_list()):
        if len(panel.series) < 2:
            continue
        where = f"panels[{k + 1}]" if params.panel_count() > 1 else "the plot"
        if k < len(legends) and not legends[k]:
            unnamed = [str(s.name) for s in panel.series if str(s.name) not in named]
            if unnamed:
                add("plot_series", f"{where} has {len(panel.series)} series and no legend (legend: false), and nothing names "
                                   f"{', '.join(repr(n) for n in unnamed[:3])}: the viewer cannot tell them apart; show the legend or label "
                                   f"each series (annotations: {{type: label, series: ...}})")
        for s in panel.series:
            if _PLACEHOLDER.match(str(s.name).strip()):
                add("plot_series", f"series '{s.name}' in {where}: a placeholder name (the legend shows it): name it after what it is "
                                   f"(measured, model, control...)")


def _conserved(params: Any, rules: LintRules, add: Any) -> None:
    tol = rules.plot_conserved.tolerance
    try:
        drifts = params.conservation()
    except Exception:  # noqa: BLE001 - validation reports a model that fails
        return
    for model, quantity, drift in drifts:
        if not math.isfinite(drift) or drift <= tol:
            continue
        m = params.models[model]
        step = f"step {m.step:g}" if m.step else "the default step (span/1000)"
        fix = (f"halve the step (now {step})" if m.method == "leapfrog" else
               f"use method: leapfrog (symplectic: the energy error stays bounded) or a smaller step (now {step}, method {m.method})")
        add("plot_conserved", f"model '{model}': {quantity} is declared conserved but drifts by {drift:.2%} over the run (more than "
                              f"{tol:.2%}): the plot shows the integrator's error, not physics; {fix}")


def _fit_claims(spec: SceneConfig, resolved: Any, rules: LintRules, add: Any) -> None:
    quantities: list[qa.FitQuantity] = []
    for f in resolved.fits:
        r = f.result
        try:
            units = r.model.units(f.x_unit, f.y_unit)
        except Exception:  # noqa: BLE001 - a custom model without units
            units = [""] * len(r.model.names)
        quantities += qa.fit_quantities(f.spec.label(), f.spec.kind, r.model.names, list(r.params), list(r.errors), list(units), f.x_unit)
    if not quantities:
        return
    settings = rules.plot_fit_claims
    first = spec.beats[0].id if spec.beats else None
    for beat in spec.beats:
        for claim in qa.fit_claims(str(beat.text), quantities, settings.sigmas, settings.tolerance):
            add("plot_fit_claims", f'"{claim.quote}": {claim.message}', beat.id)
    for where, text in screen_texts(spec):
        for claim in qa.fit_claims(text, quantities, settings.sigmas, settings.tolerance):
            add("plot_fit_claims", f"{where} '{claim.quote}': {claim.message}", first)


# ----- the rules -----------------------------------------------------------------------------------------


@rule("plot_units", scope="scene")
def plot_units(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A plot axis of a physical quantity (time, energy, distance...) without its unit."""
    yield from _issues(ctx, "plot_units")


@rule("plot_log", scope="scene")
def plot_log(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Error bars, a fitted curve or band, or a reference line at or below zero on a log axis."""
    yield from _issues(ctx, "plot_log")


@rule("plot_errors", scope="scene")
def plot_errors(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Error bars without a stated meaning (sd, sem, ci95...), or narration calling them something else."""
    yield from _issues(ctx, "plot_errors")


@rule("plot_series", scope="scene")
def plot_series(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Series a viewer cannot tell apart: no legend and no labels, or placeholder names."""
    yield from _issues(ctx, "plot_series")


@rule("plot_truncated", scope="scene", default="info")
def plot_truncated(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Bars that do not start at zero (a histogram on a broken y axis, a bar_chart baseline other than 0)."""
    yield from _issues(ctx, "plot_truncated")


@rule("plot_conserved", scope="scene")
def plot_conserved(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A quantity a plot's model declares conserved drifting beyond tolerance (suggest leapfrog or a smaller step)."""
    yield from _issues(ctx, "plot_conserved")


@rule("plot_fit_claims", scope="scene")
def plot_fit_claims(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A fitted value said in the narration or a note differently from what the fit gives."""
    yield from _issues(ctx, "plot_fit_claims")
