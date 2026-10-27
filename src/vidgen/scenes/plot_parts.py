"""The params of the ``plot`` scene type (Phase W, DESIGN §97.4–97.6) and how they become numbers:
axes, series (lines, points, histograms) with error bars, fits and annotations, resolved from
inline values or a CSV in the project, checked with clear messages. The scene (``plot.py``)
draws what :meth:`PlotParams.resolve` returns."""

import math
from typing import Any, Literal

import numpy as np

from vidgen.api import *

#: Data files a plot reads.
DATA_SUFFIXES = (".csv", ".tsv", ".txt")
#: What error bars mean (shown in the legend).
ERROR_MEANINGS = {"sd": "± SD", "sem": "± SEM", "ci95": "95 % CI", "range": "min–max", "poisson": "± √N", "other": "± error"}
#: Fit models a plot accepts: the curve models and, for histograms, the distributions.
FIT_MODELS = (*plotcore.MODEL_KINDS, *plotcore.DISTRIBUTIONS)
#: Annotation types.
ANNOTATION_TYPES = ("label", "arrow", "hline", "vline", "xrange", "yrange", "note")
#: Places a note may ask for.
NOTE_SPOTS = ("auto", "top_left", "top_right", "bottom_right", "bottom_left", "top", "bottom")


class PlotAxis(SceneParams):
    """An axis: ``{label, unit, scale, min, max, reversed, format, linthresh, breaks}``."""

    label: TranslatableStr = ""
    """Axis title (the unit is added in parentheses); default: the name of the first series' data column."""
    unit: str = ""
    """Unit, shown as 'label (unit)'; default: the unit in the first series' column header, e.g. 'time (s)'."""
    scale: Literal["linear", "log", "symlog"] = "linear"
    """linear; log (base 10, positive values; ticks at powers of ten with 2-9 minor ticks); symlog (linear near 0, logarithmic beyond ±linthresh: data across zero spanning decades)."""
    min: float | None = None
    """Lower end of the axis; default: from the data (rounded out to a tick when that is near)."""
    max: float | None = None
    """Upper end of the axis; default: from the data."""
    reversed: bool = False
    """Run the axis from high to low (e.g. magnitudes in astronomy, depth)."""
    format: str = "auto"
    """Tick labels: auto (plain numbers, or a power of ten moved into the title: 'distance (10⁶ km)'), plain, sci (2.5 × 10⁻³ on every tick), si (an SI prefix on the unit: 'time (ms)'; on a log axis each tick: '10 kHz'; needs a base unit such as s, m, Hz, eV), or a pattern such as '{:.1f}'."""
    linthresh: float | None = Field(default=None, gt=0)
    """symlog: the range ±linthresh drawn linearly; default: from the data."""
    breaks: list[tuple[float, float]] = Field(default_factory=list)
    """Value ranges cut out of a linear axis, [[from, to], ...], drawn with // marks; data on both sides, none inside."""

    @field_validator("format")
    @classmethod
    def _format(cls, v: str) -> str:
        return plotcore.check_tick_format(v)

    def spec(self, label: str, unit: str, max_ticks: int = 6) -> Any:
        """The core's ``AxisSpec`` with the label and unit decided by the data."""
        return plotcore.AxisSpec(scale=self.scale, lo=self.min, hi=self.max, reversed=self.reversed, linthresh=self.linthresh,
                                 breaks=tuple(tuple(b) for b in self.breaks), format=self.format, unit=unit, label=label, max_ticks=max_ticks)


class PlotErrorPair(SceneParams):
    """Asymmetric error bars: ``{minus, plus}``, each a number, a column or a list."""

    minus: float | str | list[float | None]
    """How far the bar reaches below (left of) each point."""
    plus: float | str | list[float | None]
    """How far it reaches above (right of) each point."""


ErrorValue = float | str | list[float | None] | PlotErrorPair


class PlotSeries(SceneParams):
    """A series: ``{name, x, y}`` (column names of the data file, or lists of numbers),
    ``{name, points: [[x, y], ...]}``, or a histogram ``{name, values, bins}``; ``style``,
    ``color``, ``marker``, ``dashed``, ``width``; error bars ``y_err`` / ``x_err`` with their
    meaning ``error``."""

    name: TranslatableStr = Field(min_length=1)
    """Series name (legend, targets series:<name>, fits: series: <name>)."""
    x: str | list[float] | None = None
    """X values: a column of the data file (by name, e.g. 'time') or a list of numbers."""
    y: str | list[float] | None = None
    """Y values: a column of the data file or a list of numbers (null for a gap)."""
    points: list[tuple[float, float]] | None = None
    """Inline points [[x, y], ...] instead of x and y."""
    values: str | list[float] | None = None
    """Raw values to bin into a histogram (a column or a list) instead of x and y."""
    bins: int | Literal["auto", "sturges", "fd", "scott", "sqrt", "integers"] | list[float] = "auto"
    """Histogram bins: a rule (auto: the narrower of sturges and fd; sturges; fd: Freedman-Diaconis; scott; sqrt; integers: one bin per whole number), a number of equal bins, or the edges [e0, e1, ...]."""
    bin_width: float | None = Field(default=None, gt=0)
    """Histogram bin width (edges on its multiples, or from bin_range's start); overrides a rule."""
    bin_range: tuple[float, float] | None = None
    """Histogram range [low, high]; default: the values' range. Values outside are left out."""
    nice_bins: bool = True
    """Round a rule's bin width to 1, 2, 2.5 or 5 x 10^k with edges on its multiples; false: the rule's exact width from the lowest value."""
    density: bool = False
    """Histogram heights as a probability density (area 1) instead of counts."""
    data: str | None = None
    """A CSV for this series (default: the plot's data)."""
    style: Literal["line", "points", "both", "bars", "step"] | None = None
    """line (joined in data order), points (markers), both; a histogram: bars (default), step (outline) or points (a marker at each bin's centre, e.g. with y_err: sqrt). Default: line, bars for a histogram."""
    color: ThemeColor | None = None
    """Colour; default: the theme palette colour at the series' position."""
    marker: Literal["auto", "circle", "square", "triangle", "diamond"] = "auto"
    """Marker shape of points; auto: by series position."""
    dashed: bool = False
    """Dashed line (e.g. a model next to measurements)."""
    width: float = Field(default=4.0, gt=0, le=12)
    """Line width (pixels at 1080p)."""
    y_err: ErrorValue | None = None
    """Error bars in y: a number (the same for every point), a column, a list, {minus, plus} for asymmetric bars, or sqrt (Poisson: √y; a histogram's √N)."""
    x_err: ErrorValue | None = None
    """Error bars in x: a number, a column, a list or {minus, plus}."""
    error: Literal["sd", "sem", "ci95", "range", "poisson", "other"] | None = None
    """What the error bars mean, shown in the legend: sd (standard deviation), sem (standard error of the mean), ci95 (95 % confidence interval), range (min to max), poisson (√N), other. Default with y_err: sqrt: poisson."""
    model: str | None = None
    """A model of the plot's models whose columns x and y name (default: the plot's only model, when there is no data file)."""
    live: bool | None = None
    """Grow the series over its beat (from its first point to its last, in the model's time or the data's order) with a moving head; a histogram fills as its values arrive, in their order; default: true for a model's series."""
    head: bool = True
    """live: a marker at the growing end."""
    readout: bool | str = False
    """live: show the current value (and the model's time) in a box while it grows: true (labelled by the y column), or the label to use."""
    trail: float | None = Field(default=None, gt=0)
    """live: only the last stretch (this long, in the model's time or points) is drawn strongly, the older part faint (phase-space plots)."""

    @field_validator("y", mode="before")
    @classmethod
    def _gaps(cls, v: Any) -> Any:
        return [math.nan if item is None else item for item in v] if isinstance(v, list) else v

    @model_validator(mode="after")
    def _source(self) -> "PlotSeries":
        given = [k for k in ("x", "y", "points", "values") if getattr(self, k) is not None]
        if self.values is not None:
            if any(k in given for k in ("x", "y", "points")):
                raise ValueError(f"series '{self.name}': a histogram takes values (raw numbers to bin), not x, y or points")
            if isinstance(self.values, list) and len(self.values) < 2:
                raise ValueError(f"series '{self.name}': a histogram needs at least two values")
            if self.style not in (None, "bars", "step", "points"):
                raise ValueError(f"series '{self.name}': a histogram is drawn as bars, step or points (at the bin centres), not {self.style}")
            if self.x_err is not None:
                raise ValueError(f"series '{self.name}': a histogram has no x errors (its bins are its x)")
            if self.y_err is not None and self.y_err != "sqrt":
                raise ValueError(f"series '{self.name}': a histogram's error bars are y_err: sqrt (√N per bin)")
        else:
            if self.points is not None:
                if self.x is not None or self.y is not None:
                    raise ValueError(f"series '{self.name}': give points or x and y, not both")
                if not self.points:
                    raise ValueError(f"series '{self.name}': points is empty")
            elif self.x is None or self.y is None:
                raise ValueError(f"series '{self.name}': give x and y (column names or lists), points, or values (a histogram)")
            elif isinstance(self.x, list) and isinstance(self.y, list) and len(self.x) != len(self.y):
                raise ValueError(f"series '{self.name}': x has {len(self.x)} values but y has {len(self.y)}")
            if self.style in ("bars", "step"):
                raise ValueError(f"series '{self.name}': style {self.style} is for a histogram (values: ...)")
            if self.bins != "auto" or self.bin_width is not None or self.bin_range is not None or self.density:
                raise ValueError(f"series '{self.name}': bins, bin_width, bin_range and density are for a histogram (values: ...)")
            if self.x_err == "sqrt":
                raise ValueError(f"series '{self.name}': x_err: sqrt is not a thing; sqrt (Poisson) is for y_err")
        if self.bin_range is not None and self.bin_range[1] <= self.bin_range[0]:
            raise ValueError(f"series '{self.name}': bin_range must be [low, high] with high > low")
        if self.error is not None and self.y_err is None and self.x_err is None:
            raise ValueError(f"series '{self.name}': error ({self.error}) says what the error bars mean, but there are none (y_err / x_err)")
        if self.data is not None and not self.data.lower().endswith(DATA_SUFFIXES):
            raise ValueError(f"series '{self.name}': data '{self.data}' is not a .csv or .tsv file")
        if self.model is not None:
            if self.data is not None:
                raise ValueError(f"series '{self.name}': give data (a file) or model, not both")
            if not (isinstance(self.values, str) or isinstance(self.x, str) and isinstance(self.y, str)):
                raise ValueError(f"series '{self.name}': a model's series names its columns: x and y (x: t, y: x), or values (a histogram of a column)")
        if self.histogram and self.trail is not None:
            raise ValueError(f"series '{self.name}': a histogram has no trail (it fills as its values arrive)")
        n = self.count()
        for axis in ("x_err", "y_err"):
            for side, v in _sides(getattr(self, axis)):
                if isinstance(v, list) and n is not None and len(v) != n:
                    raise ValueError(f"series '{self.name}': {axis}{side} has {len(v)} values for {n} points")
                if isinstance(v, (int, float)) and v < 0 or isinstance(v, list) and any(e is not None and e < 0 for e in v):
                    raise ValueError(f"series '{self.name}': {axis}{side} must not be negative")
        return self

    @property
    def histogram(self) -> bool:
        return self.values is not None

    @property
    def is_live(self) -> bool:
        """Whether it grows over its beat (``live``, default with a model)."""
        return self.live if self.live is not None else self.model is not None

    @property
    def drawn_as(self) -> str:
        """The style it is drawn in."""
        return self.style or ("bars" if self.histogram else "line")

    @property
    def meaning(self) -> str | None:
        """What its error bars mean (``poisson`` for ``y_err: sqrt`` unless said)."""
        return self.error or ("poisson" if self.y_err == "sqrt" else None)

    def count(self) -> int | None:
        """The number of points, when the params say it (inline numbers)."""
        if self.points is not None:
            return len(self.points)
        for v in (self.x, self.y):
            if isinstance(v, list):
                return len(v)
        return None

    def live_problem(self) -> str | None:
        """What is wrong with its live options once its model is known, or ``None``."""
        if not self.is_live:
            for key in ("readout", "trail"):
                if getattr(self, key):
                    return f"series '{self.name}': {key} is for a live series (live: true, or a model's series)"
        return None

    def columns(self) -> list[str]:
        """The data columns this series names (values and errors too)."""
        out = [v for v in (self.x, self.y, self.values) if isinstance(v, str)]
        for axis in ("x_err", "y_err"):
            out += [v for _, v in _sides(getattr(self, axis)) if isinstance(v, str) and v != "sqrt"]
        return out


def _sides(v: Any) -> list[tuple[str, Any]]:
    if v is None:
        return []
    if isinstance(v, PlotErrorPair):
        return [(".minus", v.minus), (".plus", v.plus)]
    return [("", v)]


class PlotFitParam(SceneParams):
    """A fit parameter's starting value and unit: ``{value, unit}``."""

    value: float = 1.0
    """Starting value."""
    unit: str = ""
    """Its unit, shown after the fitted value."""


class PlotFit(SceneParams):
    """A fitted curve: ``{series, model}`` and its options."""

    series: TextRef = Field(min_length=1)
    """The series to fit (its name)."""
    model: str = "linear"
    """linear, poly (degree), exponential (A·exp(k·x)), power (A·xᵏ), logistic, gaussian, breit_wigner (also cauchy, lorentzian), custom (expr); for a histogram also the distributions normal, exponential, poisson (fitted to the raw values)."""
    degree: int = Field(default=2, ge=1, le=6)
    """poly: the degree."""
    background: int | None = Field(default=None, ge=0, le=6)
    """gaussian / breit_wigner: a polynomial background of this degree under the peak (0: constant, 1: a line)."""
    expr: str | None = None
    """custom: the model as an expression of x and named parameters, e.g. 'a*exp(-x/tau) + c'."""
    params: dict[str, float | PlotFitParam] = Field(default_factory=dict)
    """Starting values (needed for custom, optional otherwise): {a: 1000, tau: {value: 8, unit: d}}."""
    name: TranslatableStr = ""
    """The fit's name (legend, targets fit:<name>); default: '<model> fit'."""
    range: tuple[float, float] | None = None
    """Fit only the points with x in [low, high]."""
    weighted: bool = True
    """Weight by the series' y errors (and use its x errors) when it has them; a histogram by √N."""
    band: Literal["none", "confidence", "prediction"] = "none"
    """Shade the confidence band (where the true curve lies) or the prediction band (where a new measurement would lie)."""
    level: float = Field(default=0.95, gt=0, lt=1)
    """The band's confidence level."""
    residuals: bool | Literal["normalized"] = False
    """A residual panel under the plot (y − fit), sharing x; normalized: (y − fit)/σ."""
    show: Literal["auto", "none"] | list[Literal["formula", "params", "r2", "chi2", "n"]] = "auto"
    """What the box beside the curve says: auto (parameters ± standard errors, R², χ²/ν when the points have errors), none, or a list of formula, params, r2, chi2, n. The legend names the fit by its name, else its formula."""
    extend: bool = False
    """Draw the curve across the whole x axis (default: over the fitted points)."""
    color: ThemeColor | None = None
    """Curve colour; default: accent for one fit, the series' colour with several."""
    dashed: bool = False
    """Dashed curve."""
    width: float = Field(default=4.0, gt=0, le=12)
    """Curve width (pixels at 1080p)."""

    @model_validator(mode="after")
    def _check(self) -> "PlotFit":
        kind = plotcore.MODEL_ALIASES.get(self.model, self.model)
        if kind not in FIT_MODELS:
            raise ValueError(f"model '{self.model}' is not one of {', '.join(FIT_MODELS)}" + did_you_mean(self.model, list(FIT_MODELS) + list(plotcore.MODEL_ALIASES)))
        if kind == "custom":
            if not self.expr:
                raise ValueError("model: custom needs expr, e.g. expr: \"a*exp(-x/tau) + c\" with params: {a: 1000, tau: 8, c: 0}")
            if not self.params:
                raise ValueError(f"model: custom needs params: the parameters of '{self.expr}' with starting values, e.g. params: {{a: 1, b: 0.5}}")
        elif self.expr:
            raise ValueError(f"expr is for model: custom (this fit is {self.model})")
        if self.background is not None and kind not in plotcore.PEAK_KINDS:
            raise ValueError(f"background is for the peak models {', '.join(plotcore.PEAK_KINDS)}")
        if self.range is not None and self.range[1] <= self.range[0]:
            raise ValueError("range must be [low, high] with high > low")
        if self.band != "none" and kind == "poisson":
            raise ValueError("a Poisson fit is drawn as steps and has no band")
        return self

    @property
    def kind(self) -> str:
        return plotcore.MODEL_ALIASES.get(self.model, self.model)

    def label(self) -> str:
        """Its name in targets (``fit:<name>``): the name, else '<model> fit'."""
        return str(self.name) or f"{self.model.replace('_', '-')} fit"

    def make_model(self) -> Any:
        """The core's model (raises ``VidgenError``)."""
        guesses = {k: (v.value if isinstance(v, PlotFitParam) else float(v)) for k, v in self.params.items()}
        units = {k: v.unit for k, v in self.params.items() if isinstance(v, PlotFitParam) and v.unit}
        return plotcore.make_model(self.kind, degree=self.degree, background=self.background, expr=self.expr,
                                   params=list(self.params), guesses=guesses or None, units=units)


class PlotAnnotation(SceneParams):
    """An annotation tied to the data: ``{type, text, x, y, series, ...}``."""

    type: Literal["label", "arrow", "hline", "vline", "xrange", "yrange", "note"]
    """label (text by a point, a ring on it), arrow (text with an arrow to a point), hline / vline (a dashed reference line at y / x), xrange / yrange (a shaded range [from, to]), note (a text box in a free corner)."""
    text: TranslatableStr = ""
    """The text (optional for lines and ranges)."""
    x: float | tuple[float, float] | None = None
    """label / arrow: the point's x (with series: the series' point nearest it); vline: where; xrange: [from, to]."""
    y: float | tuple[float, float] | None = None
    """label / arrow: the point's y; hline: where; yrange: [from, to]."""
    series: TextRef | None = None
    """label / arrow: the series whose point is meant (with x: nearest that x; with index; alone: its highest point)."""
    index: int | None = Field(default=None, ge=1)
    """label / arrow: the series' point by number (1 = first)."""
    at: Literal["auto", "top_left", "top_right", "bottom_right", "bottom_left", "top", "bottom"] = "auto"
    """note: where the box goes (auto: a free corner)."""
    panel: int | None = Field(default=None, ge=1)
    """The panel (1 = first); default: the series' panel, else the first."""
    color: ThemeColor | None = None
    """Colour of the mark, line or range; default: highlight."""
    id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    """A name for targets annotation:<id>."""

    @model_validator(mode="after")
    def _check(self) -> "PlotAnnotation":
        t = self.type
        pair_x, pair_y = isinstance(self.x, tuple), isinstance(self.y, tuple)
        if t in ("label", "arrow"):
            if pair_x or pair_y:
                raise ValueError(f"a {t} points at one point: x and y are numbers")
            if self.series is None and (self.x is None or self.y is None):
                raise ValueError(f"a {t} needs its point: x and y, or series (with x or index)")
            if self.series is not None and self.y is not None:
                raise ValueError(f"a {t} on a series takes x or index (the y is the series' value), not y")
            if self.index is not None and self.x is not None:
                raise ValueError(f"a {t} takes x or index, not both")
            if not str(self.text):
                raise ValueError(f"a {t} needs text")
        elif t in ("hline", "vline"):
            need, other = ("y", "x") if t == "hline" else ("x", "y")
            if not isinstance(getattr(self, need), (int, float)):
                raise ValueError(f"an {t} needs {need}: a number")
            if getattr(self, other) is not None:
                raise ValueError(f"an {t} takes {need} only")
        elif t in ("xrange", "yrange"):
            need, other = ("x", "y") if t == "xrange" else ("y", "x")
            v = getattr(self, need)
            if not isinstance(v, tuple) or v[1] <= v[0]:
                raise ValueError(f"an {t} needs {need}: [from, to] with to > from")
            if getattr(self, other) is not None:
                raise ValueError(f"an {t} takes {need} only")
        elif t == "note":
            if not str(self.text):
                raise ValueError("a note needs text")
            if self.x is not None or self.y is not None or self.series is not None:
                raise ValueError("a note stands in a free corner (at: auto | top_left | ...); it takes no x, y or series")
        if t not in ("label", "arrow") and (self.series is not None or self.index is not None):
            raise ValueError(f"series and index are for label and arrow, not {t}")
        if t != "note" and self.at != "auto":
            raise ValueError(f"at is for a note, not {t}")
        return self


class ResolvedSeries:
    """A series with its numbers: ``xs`` / ``ys`` (a histogram: bin centres and heights),
    errors as ``(minus, plus)`` arrays or ``None``, the columns it read (units), its
    ``hist`` (a :class:`plotcore.Histogram` or ``None``) and its ``panel`` index."""

    def __init__(self, spec: PlotSeries, xs: list[float], ys: list[float], x_col: Any, y_col: Any, *, hist: Any = None,
                 y_err: tuple[np.ndarray, np.ndarray] | None = None, x_err: tuple[np.ndarray, np.ndarray] | None = None) -> None:
        self.spec, self.xs, self.ys = spec, xs, ys
        self.x_col, self.y_col = x_col, y_col   # plotcore.Column or None (inline numbers)
        self.hist, self.y_err, self.x_err = hist, y_err, x_err
        self.panel = 0
        #: A live series: its progress at each point (the model's time column, else 0, 1, 2…),
        #: and the time column (name, unit) for its readout; ``None`` for a static series.
        self.times: np.ndarray | None = None
        self.time_col: Any = None
        self.discrete = False   # its progress counts steps: a readout shows the last one reached

    @property
    def live(self) -> bool:
        return self.times is not None

    def x_values(self) -> list[float]:
        """The x values its axis must show (a histogram: its edges)."""
        return [float(e) for e in self.hist.edges] if self.hist is not None else list(self.xs)

    def y_values(self) -> list[float]:
        """The y values its axis must show (a histogram: 0 and its heights)."""
        return [0.0, *self.ys] if self.hist is not None else list(self.ys)

    def extents(self, axis: str) -> list[float]:
        """The ends of its error bars on ``axis``."""
        err = self.y_err if axis == "y" else self.x_err
        if err is None:
            return []
        base = np.asarray(self.ys if axis == "y" else self.xs, dtype=float)
        lo, hi = err
        return [float(v) for v in np.concatenate([base - lo, base + hi]) if math.isfinite(v)]

    def sigma(self) -> np.ndarray | None:
        """Symmetric y errors for a fit (the mean of the two sides), or ``None``."""
        if self.y_err is None:
            return None
        return (self.y_err[0] + self.y_err[1]) / 2


class ResolvedFit:
    """A fit with its result and where it is drawn: ``spec``, ``series`` (the
    :class:`ResolvedSeries` fitted), ``result`` (:class:`plotcore.FitResult`), ``panel``
    (index), ``discrete`` (a Poisson distribution: drawn as steps), ``x_unit`` / ``y_unit``."""

    def __init__(self, spec: PlotFit, series: ResolvedSeries, result: Any, discrete: bool, lo: float, hi: float) -> None:
        self.spec, self.series, self.result, self.discrete = spec, series, result, discrete
        self.lo, self.hi = lo, hi   # the x range the curve covers by default
        self.panel = series.panel
        self.x_unit = self.y_unit = ""
        #: Poisson data fitted by maximum likelihood: the variance per unit of y at each point
        #: of the series (1 for counts; residuals are then normalized by √(scale·fit)), else None.
        self.poisson: np.ndarray | None = None

    def reduced_chi2(self) -> float | None:
        """χ²/ν: with y errors (a curve fit), or Pearson's against the bins (a distribution)."""
        r = self.result
        if "dof" in r.extra:
            return r.chi2 / r.extra["dof"] if r.extra["dof"] > 0 else None
        return r.reduced_chi2

    def lines(self) -> list[str]:
        """The text of its box."""
        show = self.spec.show
        if show == "none":
            return []
        wanted = ["params", "r2", "chi2"] if show == "auto" else list(show)
        r = self.result
        out = []
        if "formula" in wanted:
            out.append(r.model.formula)
        if "params" in wanted:
            out += r.parameter_lines(self.x_unit, self.y_unit)
        if "r2" in wanted and "dof" not in r.extra:
            out.append(f"R² = {r.r2:.4f}" if r.r2 > 0.99 else f"R² = {r.r2:.3f}")
        chi = self.reduced_chi2()
        if "chi2" in wanted and chi is not None:
            out.append(f"χ²/ν = {chi:.2f}")
        if "n" in wanted:
            out.append(f"n = {int(r.extra.get('n', r.n))}")
        return out

    def curve_x(self, lo: float, hi: float, scale: str, count: int = 240) -> np.ndarray:
        """Sample positions from ``lo`` to ``hi`` (even in log space on a log axis)."""
        if scale == "log" and lo > 0:
            return np.logspace(math.log10(lo), math.log10(hi), count)
        return np.linspace(lo, hi, count)


class Resolved(list):
    """What the params resolve to: a list of the panels (:class:`ResolvedPanel`: its
    :class:`ResolvedSeries`, x / y ``AxisSpec`` and weight) with the ``fits``
    (:class:`ResolvedFit`)."""

    def __init__(self, panels: list["ResolvedPanel"], fits: list[ResolvedFit]) -> None:
        super().__init__(panels)
        self.fits = fits

    @property
    def panels(self) -> list["ResolvedPanel"]:
        return list(self)

    @property
    def series(self) -> list[ResolvedSeries]:
        return [s for p in self for s in p.series]


class ResolvedPanel:
    """A panel's series and the axis specs decided from params and data."""

    def __init__(self, series: list[ResolvedSeries], x: Any, y: Any, weight: float) -> None:
        self.series, self.x, self.y, self.weight = series, x, y, weight


def error_arrays(value: Any, n: int, table: Any, where: str, base: list[float], hist: Any = None) -> tuple[np.ndarray, np.ndarray] | None:
    """``(minus, plus)`` error arrays of ``n`` points from a number, a column, a list, a pair or
    ``sqrt`` (√|base|, a histogram's √N); gaps count as no bar (0)."""
    if value is None:
        return None
    if isinstance(value, PlotErrorPair):
        lo = error_arrays(value.minus, n, table, f"{where}.minus", base)
        hi = error_arrays(value.plus, n, table, f"{where}.plus", base)
        return (lo[0], hi[0]) if lo is not None and hi is not None else None
    if value == "sqrt":
        e = hist.errors if hist is not None else np.sqrt(np.abs(np.asarray(base, dtype=float)))
        return np.asarray(e, dtype=float), np.asarray(e, dtype=float)
    if isinstance(value, str):
        if table is None:
            raise VidgenError(f"{where}: '{value}' names a column but no data file is given (data: assets/file.csv)")
        col = table.column(value, where)
        arr = np.asarray(col.values, dtype=float)
    elif isinstance(value, list):
        arr = np.asarray([math.nan if v is None else v for v in value], dtype=float)
    else:
        arr = np.full(n, float(value))
    if len(arr) != n:
        raise VidgenError(f"{where}: {len(arr)} values for {n} points")
    arr = np.where(np.isfinite(arr), arr, 0.0)
    if np.any(arr < 0):
        raise VidgenError(f"{where}: an error bar must not be negative ({arr[arr < 0][0]:g})")
    return arr, arr.copy()


def series_point(s: ResolvedSeries, x: float | None, index: int | None) -> tuple[float, float]:
    """The point of a series an annotation means: by ``index`` (1-based), nearest ``x``, or
    its highest point."""
    xs, ys = np.asarray(s.xs, dtype=float), np.asarray(s.ys, dtype=float)
    ok = np.isfinite(xs) & np.isfinite(ys)
    if not ok.any():
        raise VidgenError(f"series '{s.spec.name}' has no point to annotate")
    if index is not None:
        if index > len(xs):
            raise VidgenError(f"series '{s.spec.name}' has {len(xs)} points; index {index} is past its end")
        if not ok[index - 1]:
            raise VidgenError(f"series '{s.spec.name}': point {index} is a gap")
        return float(xs[index - 1]), float(ys[index - 1])
    candidates = np.flatnonzero(ok)
    if x is not None:
        k = candidates[np.argmin(np.abs(xs[candidates] - x))]
    else:
        k = candidates[np.argmax(ys[candidates])]
    return float(xs[k]), float(ys[k])


__all__ = [
    "ANNOTATION_TYPES",
    "DATA_SUFFIXES",
    "ERROR_MEANINGS",
    "FIT_MODELS",
    "NOTE_SPOTS",
    "PlotAnnotation",
    "PlotAxis",
    "PlotErrorPair",
    "PlotFit",
    "PlotFitParam",
    "PlotSeries",
    "Resolved",
    "ResolvedFit",
    "ResolvedPanel",
    "ResolvedSeries",
    "error_arrays",
    "series_point",
]
