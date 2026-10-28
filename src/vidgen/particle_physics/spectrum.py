"""Simulated collision data and what is read from it (Phase Y, Step 241; DESIGN §99.11) — no
manim. Everything here is **simulated** from a seed (:class:`~vidgen.plotcore.SplitMix64`: the
same seed gives the same events with any numpy version) and is labelled so on screen.

**Invariant-mass spectra** (:func:`generate`): ``events`` events in a mass window [lo, hi]
(GeV), each one signal with probability ``signal / events`` (so the signal count fluctuates like
real data), else background.

- *Signal*: a non-relativistic Breit–Wigner (Cauchy) of the resonance's PDG mass and width
  (:mod:`.data`, PDG 2024) convolved with a Gaussian detector resolution σ: a Breit–Wigner draw
  plus a normal draw times σ, redrawn until it falls in the window. For the Higgs boson (Γ ≈ 4 MeV,
  the Standard Model prediction) the peak is resolution-dominated; for the Z both matter.
- *Background*: smoothly falling, ``exponential`` (dN/dm ∝ exp(−m/λ), λ = ``slope`` in GeV),
  ``power`` (∝ m⁻ᵏ, k = ``index``) or ``flat``; drawn by the inverse of its CDF truncated to the
  window. Shapes and normalisations of the presets are schematic choices that look like
  published spectra; they are not fits to any experiment's data.

**Significance** (all *local*, the look-elsewhere effect not included):

- :func:`asimov`: the expected (median) significance of a counting experiment with s signal and b
  background events, Z = √(2((s + b) ln(1 + s/b) − s)) (Cowan, Cranmer, Gross, Vitells, Eur. Phys.
  J. C 71 (2011) 1554); ≈ s/√b when s ≪ b. :meth:`Spectrum.asimov_curve` evaluates it with the s and
  b expected in the peak window after n events (the window M ± 2√(σ² + (Γ/2)²); the expected
  shares of signal and background inside it: :func:`window_shares`).
- :meth:`Spectrum.counting_curve`: the observed counting significance in the same window, Z =
  √(2(n ln(n/b) − (n − b))) for n > b observed events over the expected background b (else 0).
- :func:`likelihood_significance`: a profile-likelihood ratio from binned Poisson fits (Phase W's
  ``fit_curve(poisson=1)``): background only (a polynomial) against signal + background (a
  Gaussian or Breit–Wigner on the same polynomial); q₀ = 2(ln L_s+b − ln L_b), Z = √q₀ (Wilks'
  theorem for the signal strength at the fitted mass).
- :func:`p_value`: one-sided p = ½ erfc(Z/√2) — **the probability that background alone
  fluctuates up at least this much**, not the probability that the result is wrong; 5σ ↔ p ≈
  2.87 × 10⁻⁷.

**Decay times** (:func:`decay_times`): exponential proper times from a mean life τ (inverse CDF
t = −τ ln(1 − u)); :func:`mean_lifetime` is the maximum-likelihood estimate τ̂ = mean t with its
error τ̂/√N.

**Plot models** (``plot`` scenes, ``kind: function``): ``mass_spectrum``, ``decay_times`` and
``z_lineshape`` (σ(e⁺e⁻ → hadrons) near the Z pole for 2, 3 and 4 light neutrino families: a
relativistic Breit–Wigner with an s-dependent width, peak σ⁰ = 12π Γ_ee Γ_had / (m_Z² Γ_Z²) from
the PDG 2024 Z values — **schematic**: no QED initial-state radiation, which lowers and shifts the
measured peak)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import SplitMix64, fit_curve, make_model, register_model

from .data import PARTICLES

#: Most events a spectrum or a decay-time sample may hold (bars are drawn, not events).
MAX_EVENTS = 200_000
#: (ħc)² in GeV² nb: converts 1/GeV² to a cross-section.
HBARC2_GEV2_NB = 0.3893794e6   # 0.389379 mb GeV² (ħc = 197.3269804 MeV fm, exact SI 2019 constants)
#: Background shapes.
SHAPES = ("exponential", "power", "flat")
#: Peak models a spectrum fit may use.
PEAKS = ("gaussian", "breit_wigner")
#: Significance readouts.
SIGNIFICANCE = ("asimov", "counting", "none")
#: The peak window is M ± this many √(σ² + (Γ/2)²).
WINDOW_WIDTHS = 2.0


def p_value(z: float) -> float:
    """One-sided p-value of a significance ``z`` (in σ): the chance that background alone
    fluctuates up at least this much, ½ erfc(z/√2)."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


#: One-sided p of 5σ (≈ 2.87 × 10⁻⁷), the particle-physics discovery convention.
FIVE_SIGMA_P = p_value(5.0)


def asimov(s: float, b: float) -> float:
    """The Asimov (median expected) significance of ``s`` signal over ``b`` background events:
    √(2((s + b) ln(1 + s/b) − s)); 0 for s ≤ 0. Raises for b ≤ 0."""
    if b <= 0:
        raise VidgenError(f"the Asimov significance needs a positive background (b = {b:g})")
    if s <= 0:
        return 0.0
    return math.sqrt(max(0.0, 2.0 * ((s + b) * math.log1p(s / b) - s)))


def counting_significance(n: float, b: float) -> float:
    """Observed significance of ``n`` events over an expected background ``b``:
    √(2(n ln(n/b) − (n − b))) for n > b, else 0."""
    if b <= 0 or n <= b:
        return 0.0
    return math.sqrt(max(0.0, 2.0 * (n * math.log(n / b) - (n - b))))


def sigma_text(z: float) -> str:
    """``3.4σ`` (one decimal); ``> 20σ`` beyond (the approximations behind it say nothing
    finer there)."""
    return "> 20σ" if z > 20 else f"{z:.1f}σ"


def p_text(p: float) -> str:
    """``2.9 × 10⁻⁷`` (two significant figures; plain above 0.001)."""
    if p >= 1e-3:
        return f"{p:.2g}"
    if p < 1e-300:
        return "< 10⁻³⁰⁰"
    exp = math.floor(math.log10(p))
    mant = p / 10**exp
    if round(mant, 1) >= 10:
        mant, exp = mant / 10, exp + 1
    sup = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return f"{mant:.1f} × 10{str(exp).translate(sup)}"


def meaning_lines(z: float, method: str = "likelihood ratio", narrow: bool = False) -> list[str]:
    """What a local significance ``z`` means, in words (the 5σ convention stated correctly);
    ``narrow``: shorter lines (a portrait frame)."""
    p = p_value(z)
    stated = f"p < {p_text(p_value(20.0))}" if z > 20 else f"p = {p_text(p)}"
    if narrow:
        return [f"local significance {sigma_text(z)}", f"({method})", f"one-sided {stated}:", "the chance that background",
                "alone fluctuates this high,", "not that the result is wrong", f"(5σ: p = {p_text(FIVE_SIGMA_P)})"]
    return [f"local significance {sigma_text(z)} ({method})",
            f"one-sided {stated}: the chance that",
            "background alone fluctuates this high,",
            f"not that the result is wrong (5σ: {p_text(FIVE_SIGMA_P)})"]


# ----- channels -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Channel:
    """A preset spectrum: the resonance (a key of :data:`~.data.PARTICLES`), its decay as
    shown, the axis label, resolution σ (GeV), window, bin width, events, expected signal,
    background shape and the fit and readout it uses by default."""

    key: str
    parent: str
    decay: str
    label: str
    resolution: float
    lo: float
    hi: float
    bin_width: float
    events: int
    signal: float
    shape: str
    slope: float = 0.0
    index: float = 0.0
    peak: str = "gaussian"
    background_degree: int = 2
    significance: str = "asimov"
    note: str = ""

    @property
    def mass(self) -> float:
        return PARTICLES[self.parent].mass_mev / 1e3

    @property
    def width(self) -> float:
        return (PARTICLES[self.parent].width_mev or 0.0) / 1e3


#: The presets. Resolutions are typical of a general-purpose detector (about 1 % for muons
#: near 90 GeV and photons near 125 GeV); counts and shapes are schematic choices tuned so the
#: default seed shows what the channel is known for (a dominant Z peak; a small diphoton bump
#: on a large falling background reaching about 5σ; a handful of four-lepton events).
CHANNELS: dict[str, Channel] = {
    "z_to_mumu": Channel("z_to_mumu", "Z", "Z → μ⁺μ⁻", "m(μμ)", 1.0, 70.0, 110.0, 1.0, 6000, 4800, "exponential", slope=18.0,
                         peak="breit_wigner", background_degree=2, significance="none",
                         note="the fitted Γ includes the resolution (natural width 2.50 GeV)"),
    "h_to_gammagamma": Channel("h_to_gammagamma", "H", "H → γγ", "m(γγ)", 1.6, 100.0, 160.0, 1.0, 30000, 320, "exponential", slope=30.0,
                               peak="gaussian", background_degree=3, significance="asimov",
                               note="Γ_H ≈ 4 MeV: the width is the detector resolution"),
    "h_to_4l": Channel("h_to_4l", "H", "H → ZZ* → 4ℓ", "m(4ℓ)", 1.8, 100.0, 160.0, 2.0, 40, 16, "flat",
                       peak="gaussian", background_degree=0, significance="asimov",
                       note="few events: each one counts"),
}


@dataclass(frozen=True)
class SpectrumSpec:
    """What to simulate: resonance ``mass``, ``width`` and ``resolution`` (GeV), window
    ``lo`` … ``hi``, ``events`` in all, ``signal`` expected signal events among them, the
    background ``shape`` (``slope`` λ for exponential, ``index`` k for power) and the ``seed``."""

    mass: float
    width: float
    resolution: float
    lo: float
    hi: float
    events: int
    signal: float
    shape: str = "exponential"
    slope: float = 30.0
    index: float = 4.0
    seed: int = 1

    def problems(self) -> list[str]:
        """What is wrong with these settings (empty when they can be simulated)."""
        out = []
        if not self.hi > self.lo:
            out.append(f"the mass window must be [low, high] with high > low (got [{self.lo:g}, {self.hi:g}])")
        elif not self.lo < self.mass < self.hi:
            out.append(f"the resonance at {self.mass:g} GeV lies outside the window [{self.lo:g}, {self.hi:g}] GeV")
        if self.width < 0 or self.resolution < 0:
            out.append("width and resolution must not be negative")
        if self.width == 0 and self.resolution == 0:
            out.append("a peak needs a width or a resolution above 0")
        if not 1 <= self.events <= MAX_EVENTS:
            out.append(f"events must be 1 … {MAX_EVENTS} (bars are drawn, not events), got {self.events}")
        if not 0 <= self.signal <= self.events:
            out.append(f"signal ({self.signal:g}) must lie between 0 and events ({self.events})")
        if self.shape not in SHAPES:
            out.append(f"background shape '{self.shape}' is not one of {', '.join(SHAPES)}")
        if self.shape == "exponential" and self.slope <= 0:
            out.append(f"an exponential background needs slope > 0 (its fall-off length in GeV), got {self.slope:g}")
        if self.shape == "power" and (self.index <= 0 or self.lo <= 0):
            out.append("a power-law background needs index > 0 and a window above 0 GeV")
        return out

    @property
    def sigma_eff(self) -> float:
        """√(σ² + (Γ/2)²): the peak's effective half-width."""
        return math.hypot(self.resolution, self.width / 2)

    @property
    def window(self) -> tuple[float, float]:
        """The peak window M ± 2√(σ² + (Γ/2)²), inside [lo, hi]."""
        half = WINDOW_WIDTHS * self.sigma_eff
        return max(self.lo, self.mass - half), min(self.hi, self.mass + half)


def channel_spec(channel: str, seed: int = 1, **overrides: Any) -> SpectrumSpec:
    """The :class:`SpectrumSpec` of a preset (:data:`CHANNELS`) with ``overrides`` (``None``
    values ignored)."""
    if channel not in CHANNELS:
        from vidgen.plotcore.data import did_you_mean

        raise VidgenError(f"channel '{channel}' is not one of {', '.join(CHANNELS)}" + did_you_mean(channel, list(CHANNELS)))
    c = CHANNELS[channel]
    spec = SpectrumSpec(c.mass, c.width, c.resolution, c.lo, c.hi, c.events, c.signal, c.shape, c.slope or 30.0, c.index or 4.0, seed)
    given = {k: v for k, v in overrides.items() if v is not None}
    return replace(spec, **given) if given else spec


def _breit_wigner(rng: SplitMix64, mass: float, width: float) -> float:
    if width <= 0:
        return mass
    u = rng.uniform()
    u = min(max(u, 1e-12), 1 - 1e-12)
    return mass + width / 2 * math.tan(math.pi * (u - 0.5))


def _background(rng: SplitMix64, spec: SpectrumSpec) -> float:
    u = rng.uniform()
    lo, hi = spec.lo, spec.hi
    if spec.shape == "exponential":
        lam = spec.slope
        return lo - lam * math.log(1.0 - u * (1.0 - math.exp(-(hi - lo) / lam)))
    if spec.shape == "power":
        k = spec.index
        if abs(k - 1.0) < 1e-12:
            return lo * (hi / lo) ** u
        a, b = lo ** (1 - k), hi ** (1 - k)
        return (a + u * (b - a)) ** (1 / (1 - k))
    return lo + u * (hi - lo)


@dataclass(frozen=True)
class Spectrum:
    """A simulated spectrum: ``masses`` (GeV) in arrival order and which are ``signal``."""

    spec: SpectrumSpec
    masses: np.ndarray
    signal: np.ndarray

    @property
    def events(self) -> int:
        return len(self.masses)

    def counts(self, edges: Any, n: int | None = None) -> np.ndarray:
        """Counts per bin of the first ``n`` events (default all)."""
        m = self.masses if n is None else self.masses[:n]
        return np.histogram(m, bins=np.asarray(edges, dtype=float))[0].astype(float)

    def _shares(self) -> tuple[float, float]:
        """The expected shares of signal and of background events in the peak window
        (:func:`window_shares`: not this sample's, which fluctuate with few events)."""
        return window_shares(replace(self.spec, seed=0))

    def expected(self, n: float) -> tuple[float, float]:
        """``(s, b)``: the signal and background events expected in the peak window after
        ``n`` events (the simulation's own shares)."""
        f = self.spec.signal / self.spec.events
        ws, wb = self._shares()
        return n * f * ws, n * (1 - f) * wb

    def asimov_curve(self) -> np.ndarray:
        """The Asimov significance after 0, 1, …, N events."""
        f = self.spec.signal / self.spec.events
        ws, wb = self._shares()
        n = np.arange(self.events + 1, dtype=float)
        s, b = n * f * ws, n * (1 - f) * wb
        with np.errstate(all="ignore"):
            q = 2.0 * ((s + b) * np.log1p(np.where(b > 0, s / np.where(b > 0, b, 1.0), 0.0)) - s)
        return np.where(b > 0, np.sqrt(np.maximum(q, 0.0)), 0.0)

    def counting_curve(self) -> np.ndarray:
        """The observed counting significance in the peak window after 0, 1, …, N events."""
        lo, hi = self.spec.window
        inside = ((self.masses >= lo) & (self.masses <= hi)).astype(float)
        n_obs = np.concatenate([[0.0], np.cumsum(inside)])
        _, wb = self._shares()
        f = self.spec.signal / self.spec.events
        b = np.arange(self.events + 1, dtype=float) * (1 - f) * wb
        with np.errstate(all="ignore"):
            q = 2.0 * (n_obs * np.log(np.where((n_obs > 0) & (b > 0), n_obs / np.where(b > 0, b, 1.0), 1.0)) - (n_obs - b))
        return np.where((n_obs > b) & (b > 0), np.sqrt(np.maximum(q, 0.0)), 0.0)


def _background_cdf(spec: SpectrumSpec, m: float) -> float:
    """The background's cumulative share below ``m`` in the window."""
    lo, hi = spec.lo, spec.hi
    m = min(max(m, lo), hi)
    if spec.shape == "exponential":
        lam = spec.slope
        return (1 - math.exp(-(m - lo) / lam)) / (1 - math.exp(-(hi - lo) / lam))
    if spec.shape == "power":
        k = spec.index
        if abs(k - 1.0) < 1e-12:
            return math.log(m / lo) / math.log(hi / lo)
        return (m ** (1 - k) - lo ** (1 - k)) / (hi ** (1 - k) - lo ** (1 - k))
    return (m - lo) / (hi - lo)


#: Draws of the signal shape used to find its share in the window (a fixed seed of its own).
SHARE_SAMPLES = 20_000


@lru_cache(maxsize=32)
def window_shares(spec: SpectrumSpec) -> tuple[float, float]:
    """``(signal, background)``: the expected shares of each in the peak window — the
    background's from its CDF, the signal's from :data:`SHARE_SAMPLES` draws of its shape (seed
    fixed, so the readout does not depend on the data's seed)."""
    lo, hi = spec.window
    b = _background_cdf(spec, hi) - _background_cdf(spec, lo)
    rng = SplitMix64(9_999_991)
    inside = total = 0
    for _ in range(SHARE_SAMPLES):
        m = _breit_wigner(rng, spec.mass, spec.width) + spec.resolution * rng.normal()
        if spec.lo <= m <= spec.hi:
            total += 1
            inside += lo <= m <= hi
    return (inside / total if total else 1.0), b


@lru_cache(maxsize=16)
def generate(spec: SpectrumSpec) -> Spectrum:
    """Simulate ``spec`` (deterministic in its seed; cached). Raises ``VidgenError`` for
    settings that cannot be simulated (:meth:`SpectrumSpec.problems`)."""
    problems = spec.problems()
    if problems:
        raise VidgenError(problems[0])
    rng = SplitMix64(spec.seed * 2_654_435_761 + 241)
    f = spec.signal / spec.events
    masses = np.empty(spec.events)
    flags = np.zeros(spec.events, dtype=bool)
    for i in range(spec.events):
        if rng.uniform() < f:
            flags[i] = True
            for _ in range(10_000):
                m = _breit_wigner(rng, spec.mass, spec.width) + spec.resolution * rng.normal()
                if spec.lo <= m <= spec.hi:
                    break
            masses[i] = m
        else:
            masses[i] = _background(rng, spec)
    return Spectrum(spec, masses, flags)


# ----- fits and the likelihood ratio -------------------------------------------------------------


@dataclass(frozen=True)
class Significance:
    """A profile-likelihood-ratio significance: ``z``, ``q0``, the one-sided ``p``, the signal +
    background ``fit`` and the background-only fit's parameters (``background``) with their
    log-likelihoods."""

    z: float
    q0: float
    p: float
    fit: Any
    background: np.ndarray
    lnl_sb: float
    lnl_b: float

    def lines(self) -> list[str]:
        return meaning_lines(self.z)


def _lnl(counts: np.ndarray, mu: np.ndarray) -> float:
    """Binned Poisson log-likelihood Σ (n ln μ − μ) (the n! term cancels in ratios)."""
    mu = np.maximum(mu, 1e-12)
    return float(np.sum(np.where(counts > 0, counts * np.log(mu), 0.0) - mu))


def background_fit(centers: np.ndarray, counts: np.ndarray, degree: int) -> np.ndarray:
    """The background-only Poisson maximum-likelihood polynomial (coefficients c₀ … cₙ) of the
    counts; degree 0: their mean."""
    if degree == 0:
        return np.array([float(np.mean(counts))])
    r = fit_curve(centers, counts, make_model("poly", degree=degree), poisson=1.0)
    return np.asarray(r.params, dtype=float)


def peak_guesses(peak: str, mass: float, width: float) -> dict[str, float]:
    """Starting values of a peak fit at the expected ``mass`` and ``width`` (σ for a Gaussian, Γ
    for a Breit–Wigner): a small bump on a curved background is not where the data's highest
    point above a line is."""
    return {"mu": mass, "sigma": width} if peak == "gaussian" else {"M": mass, "Gamma": width}


def likelihood_significance(edges: Any, counts: Any, peak: str = "gaussian", degree: int = 2,
                            guesses: dict[str, float] | None = None) -> Significance:
    """Fit ``counts`` in the bins ``edges`` with a ``peak`` (gaussian / breit_wigner) on a
    polynomial background of ``degree`` and with the background alone (binned Poisson maximum
    likelihood, starting from ``guesses`` — :func:`peak_guesses` — and the background-only
    polynomial); the local significance
    Z = √(2(ln L_s+b − ln L_b))."""
    if peak not in PEAKS:
        raise VidgenError(f"peak '{peak}' is not one of {', '.join(PEAKS)}")
    edges = np.asarray(edges, dtype=float)
    counts = np.asarray(counts, dtype=float)
    centers = (edges[:-1] + edges[1:]) / 2
    bg = background_fit(centers, counts, degree)
    start = {**{f"b{i}": float(c) for i, c in enumerate(bg)}, **(guesses or {})}
    fit = fit_curve(centers, counts, make_model(peak, background=degree, guesses=start), poisson=1.0)
    lnl_sb = _lnl(counts, fit(centers))
    lnl_b = _lnl(counts, np.polyval(bg[::-1], centers))
    q0 = max(0.0, 2.0 * (lnl_sb - lnl_b)) if fit.params[0] > 0 else 0.0
    z = math.sqrt(q0)
    return Significance(z, q0, p_value(z), fit, bg, lnl_sb, lnl_b)


def peak_background(fit: Any, x: Any) -> np.ndarray:
    """The polynomial background part of a peak fit (``gaussian`` / ``breit_wigner`` with a
    background) at ``x``."""
    p = np.asarray(fit.params, dtype=float)
    return np.polyval(p[3:][::-1], np.asarray(x, dtype=float)) if len(p) > 3 else np.zeros_like(np.asarray(x, dtype=float))


# ----- decay times --------------------------------------------------------------------------------


def decay_times(tau: float, events: int, seed: int = 1) -> np.ndarray:
    """``events`` exponential decay times of mean life ``tau`` (in ``tau``'s unit), seeded."""
    if not tau > 0:
        raise VidgenError(f"a mean life must be positive, got {tau:g}")
    if not 1 <= events <= MAX_EVENTS:
        raise VidgenError(f"events must be 1 … {MAX_EVENTS}, got {events}")
    rng = SplitMix64(seed * 2_654_435_761 + 7)
    return np.array([-tau * math.log(1.0 - rng.uniform()) for _ in range(events)])


def mean_lifetime(times: Any) -> tuple[float, float]:
    """``(τ̂, error)``: the maximum-likelihood mean life of exponential ``times`` (their mean)
    and its error τ̂/√N."""
    t = np.asarray(times, dtype=float)
    if len(t) < 2 or np.any(t < 0):
        raise VidgenError("a lifetime fit needs at least two decay times ≥ 0")
    tau = float(np.mean(t))
    return tau, tau / math.sqrt(len(t))


# ----- the Z lineshape ----------------------------------------------------------------------------


def z_cross_section(sqrt_s: Any, neutrinos: float = 3.0) -> np.ndarray:
    """σ(e⁺e⁻ → Z → hadrons) in nb at ``sqrt_s`` (GeV) for ``neutrinos`` light neutrino
    families: a relativistic Breit–Wigner with an s-dependent width, peak 12π Γ_ee Γ_had /
    (m_Z² Γ_Z²) (×(ħc)²); each family adds Γ_inv/3 to Γ_Z. Schematic: no QED radiative
    corrections (the measured peak is lower and shifted up by a few hundred MeV)."""
    from .branching import branching

    z = PARTICLES["Z"]
    m, gamma3 = z.mass_mev / 1e3, z.width_mev / 1e3
    br = {mode.label: mode.fraction for mode in branching("Z").modes}
    g_ee = br["e⁺e⁻"] * gamma3
    g_had = br["hadrons"] * gamma3
    g_nu = br["invisible"] * gamma3 / 3
    gamma = gamma3 + (neutrinos - 3.0) * g_nu
    s = np.asarray(sqrt_s, dtype=float) ** 2
    peak = 12 * math.pi * g_ee * g_had / (m**2 * gamma**2) * HBARC2_GEV2_NB
    return peak * s * gamma**2 / ((s - m**2) ** 2 + s**2 * gamma**2 / m**2)


# ----- plot models --------------------------------------------------------------------------------


def _only(name: str, params: dict[str, float], allowed: set[str]) -> None:
    extra = sorted(set(params) - allowed)
    if extra:
        raise VidgenError(f"{name} does not take {', '.join(extra)} (it takes {', '.join(sorted(allowed))})")


@register_model("mass_spectrum", labels={"n": "event", "m": "invariant mass", "signal": "signal event"}, units={"m": "GeV"})
def _spectrum_model(params: dict[str, float], seed: int) -> dict[str, Any]:
    """The plot model ``mass_spectrum``: simulated invariant masses. Params ``mass``, ``width``,
    ``resolution`` (GeV), ``lo``, ``hi`` (the window), ``events``, ``signal`` (expected signal
    events), the background ``slope`` (exponential, GeV) or ``index`` (power law) or ``flat: 1``;
    columns ``n`` (1 … N), ``m`` (GeV) and ``signal`` (1 for a signal event)."""
    allowed = {"mass", "width", "resolution", "lo", "hi", "events", "signal", "slope", "index", "flat"}
    _only("mass_spectrum", params, allowed)
    for key in ("mass", "lo", "hi", "events", "signal"):
        if key not in params:
            raise VidgenError(f"mass_spectrum needs {key} (it takes {', '.join(sorted(allowed))})")
    shape = "flat" if params.get("flat") else "power" if "index" in params else "exponential"
    spec = SpectrumSpec(float(params["mass"]), float(params.get("width", 0.0)), float(params.get("resolution", 0.0)), float(params["lo"]),
                        float(params["hi"]), int(params["events"]), float(params["signal"]), shape, float(params.get("slope", 30.0)),
                        float(params.get("index", 4.0)), int(seed))
    sp = generate(spec)
    return {"n": np.arange(1, sp.events + 1, dtype=float), "m": sp.masses, "signal": sp.signal.astype(float)}


@register_model("decay_times", labels={"n": "decay", "t": "decay time"})
def _decay_model(params: dict[str, float], seed: int) -> dict[str, Any]:
    """The plot model ``decay_times``: ``events`` exponential decay times of mean life ``tau``
    (give the unit with the plot's ``units: {t: µs}``); columns ``n`` and ``t``."""
    _only("decay_times", params, {"tau", "events"})
    if "tau" not in params:
        raise VidgenError("decay_times needs tau, the mean life (e.g. tau: 2.197 with units: {t: µs} for the muon)")
    times = decay_times(float(params["tau"]), int(params.get("events", 1000)), seed)
    return {"n": np.arange(1, len(times) + 1, dtype=float), "t": times}


@register_model("z_lineshape", labels={"sqrt_s": "√s", "sigma": "σ(e⁺e⁻ → hadrons), 3 ν", "sigma_2nu": "2 ν", "sigma_4nu": "4 ν"},
                units={"sqrt_s": "GeV", "sigma": "nb", "sigma_2nu": "nb", "sigma_4nu": "nb"})
def _lineshape_model(params: dict[str, float], seed: int) -> dict[str, Any]:
    """The plot model ``z_lineshape`` (schematic, no radiative corrections): σ(e⁺e⁻ → hadrons)
    in nb against √s from ``lo`` to ``hi`` GeV (default 86 … 96) for 3 light neutrino families
    (``sigma``) and for 2 and 4 (``sigma_2nu``, ``sigma_4nu``)."""
    _only("z_lineshape", params, {"lo", "hi", "samples"})
    lo, hi = float(params.get("lo", 86.0)), float(params.get("hi", 96.0))
    if not 0 < lo < hi:
        raise VidgenError(f"z_lineshape: need 0 < lo < hi (got {lo:g}, {hi:g} GeV)")
    x = np.linspace(lo, hi, max(20, min(int(params.get("samples", 241)), 2000)))
    return {"sqrt_s": x, "sigma": z_cross_section(x, 3), "sigma_2nu": z_cross_section(x, 2), "sigma_4nu": z_cross_section(x, 4)}


__all__ = [
    "CHANNELS",
    "FIVE_SIGMA_P",
    "HBARC2_GEV2_NB",
    "MAX_EVENTS",
    "PEAKS",
    "SHAPES",
    "SIGNIFICANCE",
    "WINDOW_WIDTHS",
    "Channel",
    "Significance",
    "Spectrum",
    "SpectrumSpec",
    "asimov",
    "background_fit",
    "channel_spec",
    "counting_significance",
    "decay_times",
    "generate",
    "likelihood_significance",
    "mean_lifetime",
    "meaning_lines",
    "p_text",
    "p_value",
    "peak_background",
    "peak_guesses",
    "sigma_text",
    "window_shares",
    "z_cross_section",
]
