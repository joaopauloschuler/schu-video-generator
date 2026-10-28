"""``mass_spectrum``: a simulated invariant-mass spectrum filling event by event, its fit and the
local significance of the bump (Phase Y, Step 241; DESIGN §99.12).

**Decision: a ``plot`` underneath.** The scene is a :class:`Plot` whose params are made from the
physics (``channel``, ``events``, ``seed`` …): a live histogram of the plot model
``mass_spectrum`` (``particle_physics.spectrum``), a Phase W peak fit (Gaussian or Breit–Wigner
on a polynomial background, binned Poisson likelihood), notes and an optional data − background
panel (``residuals: background``). Filling, rescaling, fits, zoom and the actions ``grow``,
``fit``, ``annotate``, ``reveal`` and ``zoom`` are the plot's own. The scene adds the ticker and the
significance readout that grows with the data, and the 5σ note."""

from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .plot import Plot
from .plot_parts import PlotFit, PlotSeries

sp = particle_physics.spectrum

#: Plot params the scene makes itself (an author giving them is told to use ``plot``).
_MADE = ("series", "panels", "models", "fits", "data", "arrange", "share", "aspect")
#: Shown name of the histogram (legend, ``series:simulated data``).
DATA_NAME = "simulated data"
#: Name of the fit (``fit:fit``).
FIT_NAME = "fit"
#: In 9:16 the count axis reaches this times the highest bin (fixed: the bars rise into it as the
#: events arrive), so the fit box, the readout and the note find room inside the plot.
PORTRAIT_HEADROOM = 2.0
#: In 16:9 the count axis reaches this times the highest bin: the legend, fit box, readout and
#: note find room inside the plot above the data, and the plot keeps the frame's width (beside
#: it, a column of boxes took 40 % of the width).
LANDSCAPE_HEADROOM = 1.35
#: Label size: this margin over the readable size (the boxes are read on phones).
LABEL_MARGIN = 1.2
#: Names of the background shapes as shown in the caption.
_SHAPE_WORDS = {"exponential": "exponential", "power": "power-law", "flat": "flat"}


def _thin(n: int) -> str:
    """12 400 (a narrow no-break space between thousands)."""
    return f"{n:,}".replace(",", " ")


@scene("mass_spectrum")
class MassSpectrum(Plot):
    """Simulated invariant-mass spectrum (labelled "simulated data"): events arrive in batches
    and fill a histogram (bars, not events, are drawn) with a ticker; a resonance — Z → μμ near
    91.19 GeV with its PDG width, H → γγ near 125 GeV (a narrow, resolution-dominated bump on a
    large falling background) or H → ZZ* → 4ℓ (few events) — over a smoothly falling background;
    the peak fitted with Phase W's Gaussian / Breit–Wigner on a polynomial background (mass ±
    uncertainty and width); the local significance growing as the data accumulate (Asimov, or
    observed counting) and, after the fit, a note with the likelihood-ratio significance and
    what its p-value means; optionally a data − background panel. Steps: fill, fit, note.
    Actions: ``grow`` (fill to ``to`` events), ``fit``, ``annotate`` (``annotation:significance``),
    ``reveal`` (``residuals:fit``: subtract the background on a word), ``zoom`` (``x: [120, 130]``).

    Action targets: those of ``plot`` — ``axes``, ``series:simulated data``, ``fit:fit``,
    ``residuals:fit``, ``annotation:significance``, ``legend``, ``title``."""

    class Params(Plot.Params):
        channel: Literal["z_to_mumu", "h_to_gammagamma", "h_to_4l", "custom"] = "h_to_gammagamma"
        """The resonance and decay: z_to_mumu (Z → μ⁺μ⁻, 70–110 GeV), h_to_gammagamma (H → γγ, 100–160 GeV), h_to_4l (H → ZZ* → 4ℓ, few events), custom (give mass, window and the rest)."""
        seed: int = 1
        """Random seed of the simulation (the same seed gives the same events)."""
        events: int | None = Field(default=None, ge=10, le=200000)
        """Events in all (signal and background); default from the channel."""
        signal: float | None = Field(default=None, ge=0)
        """Expected signal events among them (each event is signal with probability signal/events); default from the channel."""
        mass: float | None = Field(default=None, gt=0)
        """Resonance mass in GeV; default the PDG 2024 mass of the channel's particle (custom: needed)."""
        width: float | None = Field(default=None, ge=0)
        """Natural width Γ in GeV (Breit–Wigner); default the PDG 2024 width (custom: 0)."""
        resolution: float | None = Field(default=None, ge=0)
        """Detector mass resolution σ in GeV (a Gaussian smearing); default from the channel."""
        window: tuple[float, float] | None = None
        """Mass range [low, high] in GeV; default from the channel."""
        bin_width: float | None = Field(default=None, gt=0)
        """Histogram bin width in GeV; default from the channel."""
        background: Literal["exponential", "power", "flat"] | None = None
        """Background shape: exponential (exp(−m/slope)), power (m^−index) or flat; default from the channel."""
        slope: float | None = Field(default=None, gt=0)
        """Exponential background: its fall-off length in GeV."""
        index: float | None = Field(default=None, gt=0)
        """Power-law background: the exponent k of m^−k."""
        peak: Literal["gaussian", "breit_wigner"] | None = None
        """Fit model of the peak: gaussian (resolution-dominated, μ and σ) or breit_wigner (M and Γ; the fitted Γ includes the resolution); default from the channel."""
        background_degree: int | None = Field(default=None, ge=0, le=4)
        """Degree of the fit's polynomial background (0: flat); default from the channel."""
        fit: bool = True
        """Fit the peak once the data are in (Phase W, binned Poisson likelihood): mass ± uncertainty and width."""
        significance: Literal["asimov", "counting", "none"] | None = None
        """Readout growing with the data: asimov (expected local significance √(2((s+b)ln(1+s/b) − s)) of the s and b expected in the peak window), counting (observed excess in that window over the expected background), none; default from the channel."""
        explain: bool | Literal["short", "long"] = True
        """After the fit, a note with the local significance from the likelihood ratio (background only against signal + background) and its one-sided p-value: true or short — three short lines, "6.7σ local", "p = 7.6 × 10⁻¹²", "(background only)" (the narration says the rest); long — four lines saying what the p-value means and what it does not; false — no note."""
        subtract: bool = False
        """A data − background panel under the plot (the fitted background subtracted, the fitted peak drawn over it); reveal residuals:fit to show it on a word."""
        style: Literal["bars", "points"] = "bars"
        """bars (a filled histogram) or points (markers with √N error bars, as in papers)."""
        ticker: bool = True
        """Count the events in the readout ("events: 12 400")."""
        label: TranslatableStr = DATA_NAME
        """What the data are called on screen (always says they are simulated)."""
        # made by the scene (typed loosely so they are not offered for translation; converted below)
        series: list[Any] | None = None
        """Made by the scene from the channel (do not set; use type: plot for your own data)."""
        fits: list[Any] = Field(default_factory=list)
        """Made by the scene (do not set; see fit, peak, background_degree)."""
        panels: list[Any] | None = None
        """Not used (one panel, made by the scene)."""

        @field_validator("series", mode="after")
        @classmethod
        def _series(cls, v: list[Any] | None) -> list[Any] | None:
            return None if v is None else [s if isinstance(s, PlotSeries) else PlotSeries.model_validate(s) for s in v]

        @field_validator("fits", mode="after")
        @classmethod
        def _fits(cls, v: list[Any]) -> list[Any]:
            return [f if isinstance(f, PlotFit) else PlotFit.model_validate(f) for f in v]

        @model_validator(mode="before")
        @classmethod
        def _build(cls, data: Any) -> Any:
            if not isinstance(data, dict):
                return data
            given = [k for k in _MADE if k in data]
            if given:
                raise ValueError(f"mass_spectrum makes its own {', '.join(given)} from the channel; for your own data use type: plot")
            return build(dict(data))

        def spectrum_spec(self) -> Any:
            """The :class:`particle_physics.spectrum.SpectrumSpec` these params simulate."""
            return spec_of(self.model_dump(include=set(_PHYSICS)))

    def construct(self) -> None:
        p = self.params
        self._spectrum = sp.generate(p.spectrum_spec())
        method = p.significance or _channel(p.channel).significance
        self._z = None if method == "none" else self._spectrum.asimov_curve() if method == "asimov" else self._spectrum.counting_curve()
        self._method = method
        if self.is_portrait:   # 9:16: the plot keeps the height (above, boxes would take half the frame)
            p = self.params = self._portrait(p)
        elif p.y.max is None:   # 16:9: headroom, so the boxes sit inside the plot and it keeps the width
            p = self.params = p.model_copy(update={"y": p.y.model_copy(update={"max": self._headroom(p, LANDSCAPE_HEADROOM)})})
        if p.label_size is None:   # a little above the readable size (lint's margin and phones), the plot keeps the room
            self.params = p.model_copy(update={"label_size": readable_size(margin=LABEL_MARGIN)})
        super().construct()

    def _headroom(self, p: Any, factor: float) -> float:
        """The count axis's top: ``factor`` × the highest bin of all the events."""
        s = p.series[0]
        hist = plotcore.histogram(list(self._spectrum.masses), "auto", width=s.bin_width, lo=s.bin_range[0], hi=s.bin_range[1])
        return float(factor * max(hist.counts))

    def _portrait(self, p: Any) -> Any:
        """Headroom above the data (the count axis fixed at PORTRAIT_HEADROOM × the highest bin;
        the bars rise into it, and the readout finds room there), no legend (the caption names
        the simulated data) and one box at the top left of the plot instead of the fit box and
        the note: the fitted mass and width, then the significance in short lines (it comes with
        the note: after the fit, or on its ``annotate`` word)."""
        update: dict[str, Any] = {}
        if p.y.max is None:
            update["y"] = p.y.model_copy(update={"max": self._headroom(p, PORTRAIT_HEADROOM)})
        if p.legend is None:
            update["legend"] = False
        note = next((a for a in p.annotations if a.id == "significance" and a.at == "auto"), None)
        if p.fits and note is not None:   # one box at the top left: the fit's values, then the significance in short lines
            f = p.fits[0]
            z = significance(p.spectrum_spec(), float(p.series[0].bin_width), f.kind, int(f.background)).z
            values = [line for line in p.resolve(None).fits[0].lines() if not line.startswith("χ²")]
            meaning = sp.meaning_lines(z, narrow=True) if p.explain == "long" else sp.short_meaning(z, narrow=True)
            text = "\n".join(values + meaning)
            update["annotations"] = [a.model_copy(update={"text": text}) if a is note else a for a in p.annotations]
            update["fits"] = [f.model_copy(update={"show": "none"})]
        return p.model_copy(update=update)

    def _note_follows_fit(self) -> bool:
        """The significance note comes right after the fit when a ``fit`` action times the fit
        and no action shows the note (else the plot's own steps would bring the note — growing the
        data to its end — before the fit)."""
        if not (self.params.explain and self.params.fits):
            return False
        timed = [t for kind in ("fit", "annotate", "reveal") for use in self.action_uses(kind) for t in use.config.targets()]
        return any(t.startswith("fit") for t in timed) and not any(t in ("annotation1", "annotation:significance") for t in timed)

    def _held(self) -> set[str]:
        held = super()._held()
        return held | {"annotation:significance"} if self._note_follows_fit() else held

    def entrance(self, target: Any) -> list[Animation]:
        """As the plot's; the significance note follows the fit (:meth:`_note_follows_fit`)."""
        anims = super().entrance(target)
        names = [target] if isinstance(target, str) else list(getattr(target, "names", []))
        if anims and "fit:fit" in names and self._note_follows_fit():
            note = next((n["group"] for n in self._notes if n["spec"].id == "significance"), None)
            if note is not None and not self.on_screen_parts(note):
                return [Succession(AnimationGroup(*anims), Wait(0.6), FadeIn(note))]
        return anims

    def _readout_lines(self, k: int, until: float | None) -> list[str]:
        """``events: 12 400`` and the significance after that many events."""
        series = [s for s in self._series if s.panel == k and s.live and s.spec.readout]
        if not series:
            return []
        s = series[0]
        u = min(max(s.times[-1] if until is None else until, s.times[0]), s.times[-1])
        n = int(u)
        lines = []
        if self.params.ticker:
            lines.append(f"events: {_thin(n)}")
        if self._z is not None:
            z = float(self._z[min(n, len(self._z) - 1)])
            asimov = self._method == "asimov"
            lines.append(f"{'expected' if asimov else 'observed'}: {sp.sigma_text(z)}")
            lines.append("(local, Asimov)" if asimov else "(local, counting)")
        return lines


#: The params that decide the simulation.
_PHYSICS = ("channel", "seed", "events", "signal", "mass", "width", "resolution", "window", "background", "slope", "index")


def _channel(key: str) -> Any:
    return sp.CHANNELS.get(key, sp.CHANNELS["h_to_gammagamma"]) if key != "custom" else None


def spec_of(d: dict[str, Any]) -> Any:
    """The simulation's spec from the params (``channel`` defaults, then what is given)."""
    channel = d.get("channel") or "h_to_gammagamma"
    window = d.get("window")
    over = {"events": d.get("events"), "signal": d.get("signal"), "mass": d.get("mass"), "width": d.get("width"),
            "resolution": d.get("resolution"), "shape": d.get("background"), "slope": d.get("slope"), "index": d.get("index"),
            "lo": window[0] if window else None, "hi": window[1] if window else None}
    seed = int(d.get("seed", 1))
    if channel == "custom":
        missing = [k for k in ("mass", "window") if d.get(k) is None]
        if missing:
            raise ValueError(f"channel: custom needs {' and '.join(missing)} (e.g. mass: 750, window: [600, 900])")
        mass = float(d["mass"])
        width = float(d.get("width") or 0.0)
        resolution = float(d["resolution"]) if d.get("resolution") is not None else 0.01 * mass
        events = int(d.get("events") or 5000)
        signal = float(d["signal"]) if d.get("signal") is not None else 0.05 * events
        lo, hi = float(window[0]), float(window[1])
        return sp.SpectrumSpec(mass, width, resolution, lo, hi, events, signal, d.get("background") or "exponential",
                               float(d.get("slope") or (hi - lo) / 2), float(d.get("index") or 4.0), seed)
    return sp.channel_spec(channel, seed=seed, **{k: (float(v) if k not in ("events", "shape") and v is not None else v) for k, v in over.items()})


@lru_cache(maxsize=16)
def significance(spec: Any, bin_width: float, peak: str, degree: int) -> Any:
    """The likelihood-ratio fit of the simulation in the plot's bins (cached: params are
    resolved several times)."""
    sim = sp.generate(spec)
    edges = np.asarray(plotcore.bin_edges(list(sim.masses), "auto", width=bin_width, lo=spec.lo, hi=spec.hi), dtype=float)
    guess_width = spec.resolution if peak == "gaussian" else spec.width + spec.resolution
    return sp.likelihood_significance(edges, sim.counts(edges), peak, degree, sp.peak_guesses(peak, spec.mass, guess_width))


def build(d: dict[str, Any]) -> dict[str, Any]:
    """The ``plot`` params of a ``mass_spectrum``: the model, the live histogram, the fit (with
    starting values from the data), the significance note and the axes' names."""
    channel = d.get("channel") or "h_to_gammagamma"
    if channel not in (*sp.CHANNELS, "custom"):
        return d   # the Literal check names the choices
    c = _channel(channel)
    spec = spec_of(d)
    problems = spec.problems()
    if problems:
        raise ValueError(problems[0])
    bw = float(d.get("bin_width") or (c.bin_width if c is not None else max(round((spec.hi - spec.lo) / 40, 1), 0.1)))
    if (spec.hi - spec.lo) / bw > 400:
        raise ValueError(f"bin_width {bw:g} GeV makes more than 400 bins over [{spec.lo:g}, {spec.hi:g}] GeV")
    peak = d.get("peak") or (c.peak if c is not None else "gaussian")
    degree = d.get("background_degree")
    degree = int(degree if degree is not None else (c.background_degree if c is not None else 2))
    method = d.get("significance") or (c.significance if c is not None else "asimov")
    params = {"mass": spec.mass, "width": spec.width, "resolution": spec.resolution, "lo": spec.lo, "hi": spec.hi,
              "events": float(spec.events), "signal": spec.signal}
    params.update({"slope": spec.slope} if spec.shape == "exponential" else {"index": spec.index} if spec.shape == "power" else {"flat": 1.0})
    style = d.get("style") or "bars"
    readout = bool(d.get("ticker", True)) or method != "none"
    series = {"name": DATA_NAME, "values": "m", "model": "events", "live": True, "bin_width": bw, "bin_range": [spec.lo, spec.hi],
              "style": style, "readout": "events" if readout else False}
    if style == "points":
        series["y_err"] = "sqrt"
    out = dict(d)
    out["models"] = {"events": {"kind": "function", "function": "mass_spectrum", "params": params, "seed": spec.seed}}
    out["series"] = [series]
    name = c.decay if c is not None else "X"
    label = c.label if c is not None else "invariant mass"
    x = dict(d.get("x") or {})
    x.setdefault("label", label)
    x.setdefault("unit", "GeV")
    out["x"] = x
    y = dict(d.get("y") or {})
    y.setdefault("label", f"events / {bw:g} GeV")
    out["y"] = y
    out.setdefault("title", f"{name}: invariant mass" if c is not None else "Invariant mass")
    shown = str(d.get("label") or DATA_NAME)
    caption = str(d.get("caption") or "")
    shape = _SHAPE_WORDS[spec.shape]
    gamma = f"{spec.width * 1e3:.2g} MeV" if spec.width < 0.1 else f"{spec.width:.3g} GeV"
    peak_words = f"Γ = {gamma}, resolution {spec.resolution:g} GeV" if spec.width > 0 else f"resolution {spec.resolution:g} GeV"
    if not caption:
        caption = f"{shown} (seed {spec.seed}) · {peak_words} · {shape} background"
    elif "simulat" not in caption.lower():
        caption = f"{shown} · {caption}"
    out["caption"] = caption
    series["name"] = shown if "simulat" in shown.lower() else f"{shown} (simulated)"
    fits: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    if d.get("fit", True):
        guess_width = spec.resolution if peak == "gaussian" else spec.width + spec.resolution
        try:
            result = significance(spec, bw, peak, degree)
        except VidgenError as error:
            raise ValueError(f"the peak fit fails for this simulation ({error}); try another seed, more events or a wider bin_width") from None
        start = {**{f"b{i}": float(v) for i, v in enumerate(result.background)}, **sp.peak_guesses(peak, spec.mass, guess_width)}
        fits.append({"series": series["name"], "model": peak, "background": degree, "name": FIT_NAME, "params": start,
                     "parameters": ["mu", "sigma"] if peak == "gaussian" else ["M", "Gamma"], "show": ["params", "chi2"],
                     "residuals": "background" if d.get("subtract") else False})
        explain = d.get("explain", True)
        if explain:
            lines = sp.meaning_lines(result.z) if explain == "long" else sp.short_meaning(result.z, narrow=True)
            notes.append({"type": "note", "id": "significance", "text": "\n".join(lines)})
    elif d.get("subtract"):
        raise ValueError("subtract needs the fit (fit: true): the background subtracted is the fitted one")
    out["fits"] = fits
    out["annotations"] = notes + list(d.get("annotations") or [])
    return out


__all__ = ["DATA_NAME", "FIT_NAME", "MassSpectrum", "build", "spec_of"]
