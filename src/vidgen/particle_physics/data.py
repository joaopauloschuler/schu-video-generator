"""The particles: the Standard Model's quarks, leptons and bosons and the hadrons used in
teaching, with their antiparticles (Phase Y, Step 237; DESIGN §99.2). No manim.

Source of every mass, width and mean life: **PDG 2024** — Particle Data Group, S. Navas et al.,
*Review of Particle Physics*, Phys. Rev. D 110, 030001 (2024), the summary tables. Values are
central values rounded to the precision a video needs (the uncertainties are not carried).
Conventions and approximations, stated:

- **Quark masses** depend on the scheme: u, d, s are MS-bar masses at μ = 2 GeV; c and b the
  MS-bar masses m(m); t the mass from direct measurements (close to the pole mass). They are
  approximate (a few per cent for u and d) and only meaningful as parameters: quarks are never
  free, so energy checks on quark-level processes are indicative only.
- **Neutrino masses** are not known; ``mass_limit_mev`` holds the direct upper limit on the
  electron-neutrino mass (0.8 eV, KATRIN, as in PDG 2024), which with the measured mass
  splittings bounds all three. Their mass is 0 in energy checks (negligible).
- The **Higgs width** is the Standard Model prediction, 4.1 MeV: the LHC Higgs Cross Section
  Working Group's Yellow Report 4 gives 4.088 MeV at m_H = 125 GeV (125.00), rounded to two
  figures here (# check); the measured value, 3.7 +1.9 −1.4 MeV in PDG 2024, agrees within its
  large error.
- The **Δ(1232)** mass and width are the Breit–Wigner values rounded (1232 MeV, 117 MeV): the
  four charge states differ by less than the width.
- **Flavour quantum numbers** follow the PDG sign convention, the same sign as the quark's
  charge: strangeness S = −1 for s, charm C = +1 for c, beauty B′ = −1 for b, topness T = +1 for
  t. Hadrons get them, and their charge and baryon number, from their quark content; K⁰_S and
  K⁰_L are mixtures of K⁰ (ds̄) and K̄⁰ (sd̄) and have no definite strangeness.
- **Intrinsic parity**: + for fermions and − for antifermions (a convention); J^P of hadrons as
  PDG lists them; C-parity for the neutral self-conjugate particles; G-parity for the non-strange
  mesons (π, η, φ, J/ψ, Υ).

Each value is a published central value; the step's report lists those the author could not
check against the 2024 tables line by line (they are marked ``# check`` here).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from fractions import Fraction

from vidgen.quantities.constants import CONSTANTS
from vidgen.quantities.quantity import decimal_text

#: The edition every value comes from.
EDITION = "PDG 2024"
SOURCE = "Particle Data Group, S. Navas et al., Review of Particle Physics, Phys. Rev. D 110, 030001 (2024)"
#: ħ in MeV·s (exact SI 2019 h and e): Γ = ħ / τ.
HBAR_MEV_S = float(CONSTANTS["h"].number()) / (2 * math.pi) / float(CONSTANTS["e"].number()) * 1e-6
#: The flavour quantum numbers, in order: strangeness, charm, beauty (bottomness), topness.
FLAVOURS = ("S", "C", "B′", "T")
FLAVOUR_NAMES = {"S": "strangeness", "C": "charm", "B′": "beauty", "T": "topness"}
#: The lepton family numbers, in order.
LEPTON_FAMILIES = ("L_e", "L_μ", "L_τ")
FAMILIES = ("quark", "lepton", "gauge boson", "scalar boson", "meson", "baryon")
MINUS = "−"
F = Fraction

Flavour = tuple[int, int, int, int]


@dataclass(frozen=True)
class Particle:
    """One particle (or antiparticle) with its PDG values and quantum numbers.

    ``mass_mev`` is the central mass (0: massless, or a neutrino whose mass is only bounded,
    ``mass_limit_mev``); ``lifetime_s`` or ``width_mev`` is the one PDG quotes (the other is
    computed, Γ = ħ/τ); ``stable`` marks particles not seen to decay. ``components`` is the
    quark content as quark keys (several for a mixture such as π⁰ or K⁰_S); ``flavour`` holds S,
    C, B′, T for one-component particles (``None`` entries: undefined for a mixture)."""

    key: str
    name: str
    symbol: str
    markup: str
    tex: str
    family: str
    mass_mev: float
    charge: Fraction
    spin: Fraction
    antiparticle: str
    baryon: Fraction = F(0)
    lepton: tuple[int, int, int] = (0, 0, 0)
    flavour_numbers: Flavour = (0, 0, 0, 0)
    parity: int | None = None
    c_parity: int | None = None
    g_parity: int | None = None
    colour: str = "1"
    lifetime_s: float | None = None
    width_mev: float | None = None
    stable: bool = False
    mass_limit_mev: float | None = None
    mass_scheme: str = ""
    unit: str = "MeV"
    digits: int = 4
    content: str = ""
    components: tuple[tuple[str, ...], ...] = ()
    generation: int | None = None
    kind: str = ""
    note: str = ""
    aliases: tuple[str, ...] = ()

    @property
    def is_fermion(self) -> bool:
        """Half-integer spin."""
        return self.spin.denominator == 2

    @property
    def self_conjugate(self) -> bool:
        """Its own antiparticle (γ, Z, H, π⁰...)."""
        return self.antiparticle == self.key

    @property
    def is_hadron(self) -> bool:
        return self.family in ("meson", "baryon")

    @property
    def is_quark(self) -> bool:
        return self.family == "quark"

    @property
    def is_lepton(self) -> bool:
        return self.family == "lepton"

    @property
    def is_neutrino(self) -> bool:
        return self.is_lepton and self.charge == 0

    @property
    def lepton_number(self) -> int:
        """Total lepton number L = L_e + L_μ + L_τ."""
        return sum(self.lepton)

    def flavour_options(self) -> list[Flavour]:
        """The flavour numbers (S, C, B′, T) it may carry: one tuple, or one per component of a
        mixture whose components differ (K⁰_S: K⁰ or K̄⁰)."""
        if len(self.components) > 1:
            options = list(dict.fromkeys(content_flavour(c) for c in self.components))
            return options
        return [self.flavour_numbers]

    @property
    def flavour(self) -> tuple[int | None, ...]:
        """S, C, B′, T; ``None`` for a number a mixture leaves undefined."""
        options = self.flavour_options()
        return tuple(options[0][i] if all(o[i] == options[0][i] for o in options) else None for i in range(4))

    @property
    def lifetime(self) -> float | None:
        """Mean life in seconds (from the width when PDG quotes a width); ``None`` when stable or
        not a decaying state."""
        if self.lifetime_s is not None:
            return self.lifetime_s
        if self.width_mev:
            return HBAR_MEV_S / self.width_mev
        return None

    @property
    def width(self) -> float | None:
        """Full width in MeV (from the mean life when PDG quotes a lifetime)."""
        if self.width_mev is not None:
            return self.width_mev
        if self.lifetime_s:
            return HBAR_MEV_S / self.lifetime_s
        return None

    @property
    def c_tau_m(self) -> float | None:
        """cτ in metres (the mean decay length at βγ = 1)."""
        tau = self.lifetime
        return None if tau is None else tau * float(CONSTANTS["c"].number())

    def mass_text(self, digits: int | None = None, unit: str | None = None) -> str:
        """The mass for display: ``0.511 MeV``, ``172.57 GeV``, ``< 0.8 eV``, ``0``."""
        if self.mass_limit_mev is not None:
            return "< " + energy_text(self.mass_limit_mev, 1)
        if self.mass_mev == 0:
            return "0"
        return energy_text(self.mass_mev, digits or self.digits, unit or self.unit)

    def charge_text(self, sign: bool = False) -> str:
        """``2/3``, ``−1/3``, ``−1``, ``0`` (``sign``: ``+2/3``, ``+1``)."""
        return fraction_text(self.charge, sign)

    def spin_text(self) -> str:
        return fraction_text(self.spin)

    def lifetime_text(self, digits: int = 4) -> str:
        """``2.197 µs``, ``878.4 s``, ``stable``; a resonance's from its width."""
        if self.stable:
            return "stable"
        tau = self.lifetime
        return "—" if tau is None else time_text(tau, digits)

    def width_text(self, digits: int = 4) -> str:
        """``2.495 GeV``, ``92.6 keV``; ``—`` for a stable particle."""
        width = self.width
        return "—" if width is None else energy_text(width, digits)


# ----- quarks and their numbers -------------------------------------------------------------------

#: Charge and (S, C, B′, T) of each quark flavour.
QUARK_NUMBERS: dict[str, tuple[Fraction, Flavour]] = {
    "u": (F(2, 3), (0, 0, 0, 0)),
    "d": (F(-1, 3), (0, 0, 0, 0)),
    "s": (F(-1, 3), (-1, 0, 0, 0)),
    "c": (F(2, 3), (0, 1, 0, 0)),
    "b": (F(-1, 3), (0, 0, -1, 0)),
    "t": (F(2, 3), (0, 0, 0, 1)),
}


def _quark_numbers(key: str) -> tuple[Fraction, Fraction, Flavour]:
    """Charge, baryon number and flavour of a quark key (``u``, ``anti-s``)."""
    anti = key.startswith("anti-")
    charge, flavour = QUARK_NUMBERS[key.removeprefix("anti-")]
    sign = -1 if anti else 1
    return sign * charge, sign * F(1, 3), tuple(sign * f for f in flavour)  # type: ignore[return-value]


def content_charge(quarks: tuple[str, ...]) -> Fraction:
    """The electric charge of a quark content."""
    return sum((_quark_numbers(q)[0] for q in quarks), F(0))


def content_baryon(quarks: tuple[str, ...]) -> Fraction:
    """The baryon number of a quark content (1/3 per quark, −1/3 per antiquark)."""
    return sum((_quark_numbers(q)[1] for q in quarks), F(0))


def content_flavour(quarks: tuple[str, ...]) -> Flavour:
    """S, C, B′, T of a quark content."""
    total = [0, 0, 0, 0]
    for q in quarks:
        for i, f in enumerate(_quark_numbers(q)[2]):
            total[i] += f
    return tuple(total)  # type: ignore[return-value]


def quark_symbol(key: str) -> str:
    """``u`` / ``ū`` (combining macron) for a quark key."""
    return key.removeprefix("anti-") + ("̄" if key.startswith("anti-") else "")


# ----- text helpers ---------------------------------------------------------------------------------


def fraction_text(value: Fraction, sign: bool = False) -> str:
    """``2/3``, ``−1/3``, ``1``, ``0`` with a Unicode minus (``sign``: ``+`` on positives)."""
    text = str(abs(value.numerator)) if value.denominator == 1 else f"{abs(value.numerator)}/{value.denominator}"
    if value < 0:
        return MINUS + text
    return ("+" + text) if sign and value > 0 else text


def _number(value: float, digits: int) -> str:
    return decimal_text(value, digits, "plain").plain


#: Energy units and their size in MeV, largest first.
ENERGY_UNITS = (("TeV", 1e6), ("GeV", 1e3), ("MeV", 1.0), ("keV", 1e-3), ("eV", 1e-6))


def energy_text(mev: float, digits: int = 4, unit: str | None = None) -> str:
    """An energy (or mass, width) in MeV for display with ``digits`` significant figures, in
    ``unit`` or the largest unit giving a number of at least 1 (``92.6 keV``, ``1.273 GeV``)."""
    if mev == 0:
        return "0"
    if unit is None and abs(mev) < 1e-8:   # below 0.01 eV (a long-lived particle's width): 10ⁿ eV
        return f"{decimal_text(mev * 1e6, min(digits, 3), 'sci').plain} eV"
    if unit is None:
        unit, scale = next(((u, s) for u, s in ENERGY_UNITS if abs(mev) >= s), ENERGY_UNITS[-1])
    else:
        scale = dict(ENERGY_UNITS)[unit]
    return f"{_number(mev / scale, digits)} {unit}"


#: Time units for lifetimes, largest first.
TIME_UNITS = (("s", 1.0), ("ms", 1e-3), ("µs", 1e-6), ("ns", 1e-9), ("ps", 1e-12), ("fs", 1e-15))


def time_text(seconds: float, digits: int = 4) -> str:
    """A lifetime: ``878.4 s``, ``2.197 µs``, ``290.3 fs``; below a femtosecond ``8.43 × 10⁻¹⁷ s``."""
    if seconds >= 1e-15:
        unit, scale = next((u, s) for u, s in TIME_UNITS if seconds >= s)
        return f"{_number(seconds / scale, digits)} {unit}"
    return f"{decimal_text(seconds, min(digits, 3), 'sci').plain} s"


# ----- building the table ---------------------------------------------------------------------------


def _anti(p: Particle, key: str, name: str, symbol: str, markup: str, tex: str, aliases: tuple[str, ...] = ()) -> Particle:
    """The antiparticle of ``p``: charge, baryon, lepton and flavour numbers reversed, colour
    conjugated, the intrinsic parity of a fermion reversed; the quark content conjugated."""
    def conj(q: str) -> str:
        return q.removeprefix("anti-") if q.startswith("anti-") else "anti-" + q

    components = tuple(tuple(conj(q) for q in c) for c in p.components)
    colour = {"3": "3̄", "3̄": "3"}.get(p.colour, p.colour)
    return replace(
        p, key=key, name=name, symbol=symbol, markup=markup, tex=tex, antiparticle=p.key,
        charge=-p.charge, baryon=-p.baryon, lepton=tuple(-x for x in p.lepton),  # type: ignore[arg-type]
        flavour_numbers=tuple(-x for x in p.flavour_numbers),  # type: ignore[arg-type]
        parity=(-p.parity if p.parity is not None and p.is_fermion else p.parity), colour=colour,
        components=components, content="".join(quark_symbol(q) for q in components[0]) if len(components) == 1 else p.content,
        aliases=aliases,
    )


def _quark(key: str, name: str, generation: int, mass: float, scheme: str, unit: str, digits: int, aliases: tuple[str, ...],
           width: float | None = None) -> tuple[Particle, Particle]:
    charge, flavour = QUARK_NUMBERS[key]
    kind = "up-type" if charge > 0 else "down-type"
    q = Particle(
        key, f"{name} quark", key, key, key, "quark", mass, charge, F(1, 2), "anti-" + key, baryon=F(1, 3),
        flavour_numbers=flavour, parity=1, colour="3", width_mev=width, mass_scheme=scheme, unit=unit, digits=digits,
        content=key, components=((key,),), generation=generation, kind=kind, aliases=aliases,
    )
    bar = key + "̄"
    return q, _anti(q, "anti-" + key, f"{name} antiquark", bar, bar, rf"\bar{{{key}}}", (f"{key}bar", f"anti{name}"))


def _lepton(base: str, name: str, generation: int, family_index: int, mass: float, symbol: str, markup: str,
            tex: str, anti: tuple[str, str, str, str, str], lifetime: float | None, stable: bool, digits: int,
            aliases: tuple[str, ...], anti_aliases: tuple[str, ...], limit: float | None = None) -> tuple[Particle, Particle]:
    neutrino = base.startswith("nu")
    lepton = [0, 0, 0]
    lepton[family_index] = 1
    p = Particle(
        base + ("" if neutrino else "-"), name, symbol, markup, tex, "lepton", mass, F(0) if neutrino else F(-1), F(1, 2),
        anti[0], lepton=tuple(lepton), parity=1, lifetime_s=lifetime, stable=stable,  # type: ignore[arg-type]
        mass_limit_mev=limit, digits=digits, generation=generation, kind="neutrino" if neutrino else "charged lepton",
        note="mass not known: the direct limit (KATRIN, PDG 2024) bounds all three" if neutrino else "", aliases=aliases,
    )
    return p, _anti(p, *anti, aliases=anti_aliases)


def _hadron(key: str, name: str, symbol: str, markup: str, tex: str, family: str, mass: float, charge: int, spin: Fraction,
            parity: int, components: tuple[tuple[str, ...], ...], *, content: str = "", lifetime: float | None = None,
            width: float | None = None, stable: bool = False, c: int | None = None, g: int | None = None, digits: int = 6,
            unit: str = "MeV", antiparticle: str | None = None, note: str = "", aliases: tuple[str, ...] = ()) -> Particle:
    """A hadron; baryon number and flavour from its quark content. Its charge is given and
    checked against the content (``particle_problems``)."""
    first = components[0]
    return Particle(
        key, name, symbol, markup, tex, family, mass, F(charge), spin, antiparticle or key, baryon=content_baryon(first),
        flavour_numbers=content_flavour(first) if len(components) == 1 else (0, 0, 0, 0), parity=parity, c_parity=c,
        g_parity=g, lifetime_s=lifetime, width_mev=width, stable=stable, unit=unit, digits=digits,
        content=content or "".join(quark_symbol(q) for q in first), components=components, kind=family, note=note,
        aliases=aliases,
    )


def _pair(p: Particle, key: str, name: str, symbol: str, markup: str, tex: str, aliases: tuple[str, ...] = ()) -> tuple[Particle, Particle]:
    p = replace(p, antiparticle=key)
    return p, _anti(p, key, name, symbol, markup, tex, aliases)


def _sup(base: str, charge: str) -> str:
    """Pango markup ``base<sup>charge</sup>`` (charge in Unicode minus)."""
    return f"{base}<sup>{charge.replace('-', MINUS)}</sup>"


def _build() -> dict[str, Particle]:
    out: list[Particle] = []
    # quarks (MS-bar: u, d, s at 2 GeV; c, b at m(m); t: direct measurements)
    out += _quark("u", "up", 1, 2.16, "MS-bar at 2 GeV", "MeV", 3, ("up",))            # check (2024 vs 2022 errors)
    out += _quark("d", "down", 1, 4.70, "MS-bar at 2 GeV", "MeV", 3, ("down",))        # check (4.67 in PDG 2022)
    out += _quark("s", "strange", 2, 93.5, "MS-bar at 2 GeV", "MeV", 3, ("strange",))   # check (93.4 in PDG 2022)
    out += _quark("c", "charm", 2, 1273.0, "MS-bar m(m)", "GeV", 4, ("charm",))         # check (1.27 in PDG 2022)
    out += _quark("b", "bottom", 3, 4183.0, "MS-bar m(m)", "GeV", 4, ("bottom", "beauty"))   # check (4.18 in PDG 2022)
    out += _quark("t", "top", 3, 172570.0, "direct measurements (≈ pole mass)", "GeV", 5, ("top", "truth"), width=1420.0)   # check
    # leptons
    out += _lepton("e", "electron", 1, 0, 0.51099895, "e⁻", _sup("e", "-"), "e^-", ("e+", "positron", "e⁺", _sup("e", "+"), "e^+"),
                   None, True, 6, ("e", "electron", "e^-"), ("positron", "e^+", "antielectron"))
    out += _lepton("mu", "muon", 2, 1, 105.6583755, "μ⁻", _sup("μ", "-"), r"\mu^-", ("mu+", "antimuon", "μ⁺", _sup("μ", "+"), r"\mu^+"),
                   2.1969811e-6, False, 7, ("mu", "muon", "mu^-"), ("antimuon", "mu^+"))
    out += _lepton("tau", "tau", 3, 2, 1776.93, "τ⁻", _sup("τ", "-"), r"\tau^-", ("tau+", "antitau", "τ⁺", _sup("τ", "+"), r"\tau^+"),
                   290.3e-15, False, 6, ("tau", "tau lepton", "tau^-"), ("antitau", "tau^+"))      # check (1776.86 in PDG 2022)
    for i, (sub, sub_markup, sub_tex, word) in enumerate([("e", "ₑ", "e", "electron"), ("mu", "_μ", r"\mu", "muon"), ("tau", "_τ", r"\tau", "tau")]):
        symbol = "ν" + sub_markup
        out += _lepton(f"nu_{sub}", f"{word} neutrino", i + 1, i, 0.0, symbol, f"ν<sub>{symbol[1:].lstrip('_').replace('ₑ', 'e')}</sub>",
                       rf"\nu_{{{sub_tex}}}",
                       (f"anti-nu_{sub}", f"{word} antineutrino", "ν̄" + sub_markup, f"ν̄<sub>{symbol[1:].lstrip('_').replace('ₑ', 'e')}</sub>",
                        rf"\bar{{\nu}}_{{{sub_tex}}}"),
                       None, True, 2, (f"nu{sub}", f"{word} neutrino", f"nu_{sub}"), (f"nubar_{sub}", f"nu_{sub}bar", f"{word} antineutrino"),
                       limit=0.8e-6)
    # gauge and scalar bosons
    out.append(Particle("gamma", "photon", "γ", "γ", r"\gamma", "gauge boson", 0.0, F(0), F(1), "gamma", parity=-1, c_parity=-1,
                        stable=True, kind="gauge boson", note="mass < 1 × 10⁻¹⁸ eV (PDG 2024)", aliases=("photon", "y")))
    out.append(Particle("g", "gluon", "g", "g", "g", "gauge boson", 0.0, F(0), F(1), "g", parity=-1, colour="8", stable=True,
                        kind="gauge boson", note="massless in the theory; eight colour states", aliases=("gluon",)))
    w = Particle("W+", "W boson", "W⁺", _sup("W", "+"), "W^+", "gauge boson", 80369.2, F(1), F(1), "W-", width_mev=2085.0, unit="GeV",
                 digits=6, kind="gauge boson", aliases=("W^+", "Wplus"))   # PDG 2024, confirmed in review (80.377 in PDG 2022)
    out += [w, _anti(w, "W-", "W boson", "W⁻", _sup("W", "-"), "W^-", ("W^-", "Wminus"))]
    out.append(Particle("Z", "Z boson", "Z", "Z", "Z", "gauge boson", 91188.0, F(0), F(1), "Z", width_mev=2495.5, unit="GeV", digits=6,
                        kind="gauge boson", aliases=("Z0", "Z^0", "Z boson")))   # PDG 2024, confirmed in review (91.1876 / 2.4952 in PDG 2022)
    out.append(Particle("H", "Higgs boson", "H", "H", "H", "scalar boson", 125200.0, F(0), F(0), "H", parity=1, c_parity=1, width_mev=4.1,
                        unit="GeV", digits=5, kind="scalar boson", note="width: the Standard Model prediction (measured 3.7 +1.9 −1.4 MeV)",
                        aliases=("H0", "h", "h0", "higgs", "Higgs boson")))   # PDG 2024, confirmed in review (125.25 in PDG 2022); width: check (YR4 4.088 MeV at 125.00 GeV)
    # light mesons
    half, one, three_halves = F(1, 2), F(1), F(3, 2)
    pi = _hadron("pi+", "charged pion", "π⁺", _sup("π", "+"), r"\pi^+", "meson", 139.57039, 1, F(0), -1, (("u", "anti-d"),), lifetime=2.6033e-8,
                 g=-1, digits=7, aliases=("pion+", "pi^+"))
    out += _pair(pi, "pi-", "charged pion", "π⁻", _sup("π", "-"), r"\pi^-", ("pion-", "pi^-"))
    out.append(_hadron("pi0", "neutral pion", "π⁰", _sup("π", "0"), r"\pi^0", "meson", 134.9768, 0, F(0), -1, (("u", "anti-u"), ("d", "anti-d")),
                       content="(uū − dd̄)/√2", lifetime=8.43e-17, c=1, g=-1, aliases=("pion0", "pi^0")))   # check lifetime
    out.append(_hadron("eta", "eta meson", "η", "η", r"\eta", "meson", 547.862, 0, F(0), -1, (("u", "anti-u"), ("d", "anti-d"), ("s", "anti-s")),
                       content="≈ (uū + dd̄ − 2ss̄)/√6", width=1.31e-3, c=1, g=1, note="quark content approximate (η–η′ mixing)",
                       aliases=("eta0",)))
    k = _hadron("K+", "charged kaon", "K⁺", _sup("K", "+"), "K^+", "meson", 493.677, 1, F(0), -1, (("u", "anti-s"),), lifetime=1.2380e-8,
                aliases=("kaon+", "K^+"))
    out += _pair(k, "K-", "charged kaon", "K⁻", _sup("K", "-"), "K^-", ("kaon-", "K^-"))
    k0 = _hadron("K0", "neutral kaon", "K⁰", _sup("K", "0"), "K^0", "meson", 497.611, 0, F(0), -1, (("d", "anti-s"),),
                 note="produced by the strong interaction; decays as K⁰_S or K⁰_L", aliases=("K^0", "kaon0"))
    out += _pair(k0, "anti-K0", "neutral antikaon", "K̄⁰", "K̄<sup>0</sup>", r"\bar{K}^0", ("K0bar", "Kbar0"))
    mix = (("d", "anti-s"), ("s", "anti-d"))
    out.append(_hadron("K0_S", "K-short", "K⁰_S", "K<sup>0</sup><sub>S</sub>", "K^0_S", "meson", 497.611, 0, F(0), -1, mix,
                       content="K⁰ (ds̄) and K̄⁰ (sd̄) mixed", lifetime=0.8954e-10,
                       aliases=("K_S", "KS", "K_S0", "KS0", "K0S", "Kshort", "K-short", "K_short")))
    out.append(_hadron("K0_L", "K-long", "K⁰_L", "K<sup>0</sup><sub>L</sub>", "K^0_L", "meson", 497.611, 0, F(0), -1, mix,
                       content="K⁰ (ds̄) and K̄⁰ (sd̄) mixed", lifetime=5.116e-8,
                       aliases=("K_L", "KL", "K_L0", "KL0", "K0L", "Klong", "K-long", "K_long")))
    out.append(_hadron("phi", "phi meson", "φ", "φ", r"\phi", "meson", 1019.461, 0, one, -1, (("s", "anti-s"),), width=4.249, c=-1, g=-1,
                       digits=7, aliases=("phi(1020)", "phi0")))
    # heavy quarkonia and heavy-flavour mesons
    out.append(_hadron("J/psi", "J/psi", "J/ψ", "J/ψ", r"J/\psi", "meson", 3096.900, 0, one, -1, (("c", "anti-c"),), width=0.0926, c=-1, g=-1,
                       digits=7, aliases=("jpsi", "J/psi(1S)", "Jpsi", "psi")))
    out.append(_hadron("Upsilon(1S)", "Upsilon(1S)", "Υ(1S)", "Υ(1S)", r"\Upsilon(1S)", "meson", 9460.40, 0, one, -1, (("b", "anti-b"),),
                       width=0.05402, c=-1, g=-1, aliases=("Upsilon", "Upsilon1S", "Y(1S)")))
    d = _hadron("D+", "charged D meson", "D⁺", _sup("D", "+"), "D^+", "meson", 1869.66, 1, F(0), -1, (("c", "anti-d"),), lifetime=1.033e-12,
                aliases=("D^+",))
    out += _pair(d, "D-", "charged D meson", "D⁻", _sup("D", "-"), "D^-", ("D^-",))
    d0 = _hadron("D0", "neutral D meson", "D⁰", _sup("D", "0"), "D^0", "meson", 1864.84, 0, F(0), -1, (("c", "anti-u"),), lifetime=410.3e-15,
                 aliases=("D^0",))   # check lifetime (410.1 fs in PDG 2022)
    out += _pair(d0, "anti-D0", "neutral anti-D meson", "D̄⁰", "D̄<sup>0</sup>", r"\bar{D}^0", ("D0bar", "Dbar0"))
    b = _hadron("B+", "charged B meson", "B⁺", _sup("B", "+"), "B^+", "meson", 5279.41, 1, F(0), -1, (("u", "anti-b"),), lifetime=1.638e-12,
                aliases=("B^+",))   # check mass (5279.34 in PDG 2022)
    out += _pair(b, "B-", "charged B meson", "B⁻", _sup("B", "-"), "B^-", ("B^-",))
    b0 = _hadron("B0", "neutral B meson", "B⁰", _sup("B", "0"), "B^0", "meson", 5279.72, 0, F(0), -1, (("d", "anti-b"),), lifetime=1.517e-12,
                 aliases=("B^0",))   # check mass (5279.65 in PDG 2022)
    out += _pair(b0, "anti-B0", "neutral anti-B meson", "B̄⁰", "B̄<sup>0</sup>", r"\bar{B}^0", ("B0bar", "Bbar0"))
    # baryons
    p = _hadron("p", "proton", "p", "p", "p", "baryon", 938.27209, 1, half, 1, (("u", "u", "d"),), stable=True,
                note="no decay seen: mean life > 10²⁹ years", aliases=("proton", "p+", "p^+"))
    out += _pair(p, "anti-p", "antiproton", "p̄", "p̄", r"\bar{p}", ("pbar", "antiproton", "p-"))
    n = _hadron("n", "neutron", "n", "n", "n", "baryon", 939.56542, 0, half, 1, (("u", "d", "d"),), lifetime=878.4, digits=6,
                aliases=("neutron", "n0"))
    out += _pair(n, "anti-n", "antineutron", "n̄", "n̄", r"\bar{n}", ("nbar", "antineutron"))
    for key, name, symbol, mark, tex, mass, charge, content, tau, akey, asym, amark, atex, aliases in [
        ("Lambda", "Lambda baryon", "Λ", "Λ", r"\Lambda", 1115.683, 0, ("u", "d", "s"), 2.617e-10,     # PDG 2024 average (2.632 before)
         "anti-Lambda", "Λ̄", "Λ̄", r"\bar{\Lambda}", ("Lambda0",)),
        ("Sigma+", "Sigma baryon", "Σ⁺", _sup("Σ", "+"), r"\Sigma^+", 1189.37, 1, ("u", "u", "s"), 0.8018e-10,
         "anti-Sigma-", "Σ̄⁻", _sup("Σ̄", "-"), r"\bar{\Sigma}^-", ()),
        ("Sigma0", "Sigma baryon", "Σ⁰", _sup("Σ", "0"), r"\Sigma^0", 1192.642, 0, ("u", "d", "s"), 7.4e-20,
         "anti-Sigma0", "Σ̄⁰", _sup("Σ̄", "0"), r"\bar{\Sigma}^0", ()),
        ("Sigma-", "Sigma baryon", "Σ⁻", _sup("Σ", "-"), r"\Sigma^-", 1197.449, -1, ("d", "d", "s"), 1.479e-10,
         "anti-Sigma+", "Σ̄⁺", _sup("Σ̄", "+"), r"\bar{\Sigma}^+", ()),
        ("Xi0", "Xi baryon", "Ξ⁰", _sup("Ξ", "0"), r"\Xi^0", 1314.86, 0, ("u", "s", "s"), 2.90e-10,
         "anti-Xi0", "Ξ̄⁰", _sup("Ξ̄", "0"), r"\bar{\Xi}^0", ()),
        ("Xi-", "Xi baryon", "Ξ⁻", _sup("Ξ", "-"), r"\Xi^-", 1321.71, -1, ("d", "s", "s"), 1.639e-10,
         "anti-Xi+", "Ξ̄⁺", _sup("Ξ̄", "+"), r"\bar{\Xi}^+", ()),
    ]:
        h = _hadron(key, name, symbol, mark, tex, "baryon", mass, charge, half, 1, (content,), lifetime=tau, aliases=aliases)
        out += _pair(h, akey, "anti-" + name.replace(" baryon", "") + " baryon", asym, amark, atex)
    omega = _hadron("Omega-", "Omega baryon", "Ω⁻", _sup("Ω", "-"), r"\Omega^-", "baryon", 1672.45, -1, three_halves, 1, (("s", "s", "s"),),
                    lifetime=0.821e-10)
    out += _pair(omega, "anti-Omega+", "anti-Omega baryon", "Ω̄⁺", _sup("Ω̄", "+"), r"\bar{\Omega}^+")
    for key, charge, content, akey, acharge in [("Delta++", 2, ("u", "u", "u"), "anti-Delta--", "--"), ("Delta+", 1, ("u", "u", "d"), "anti-Delta-", "-"),
                                                ("Delta0", 0, ("u", "d", "d"), "anti-Delta0", "0"), ("Delta-", -1, ("d", "d", "d"), "anti-Delta+", "+")]:
        sign = key.removeprefix("Delta")
        h = _hadron(key, "Delta(1232)", "Δ" + _superscript(sign), _sup("Δ", sign), rf"\Delta^{{{sign}}}", "baryon", 1232.0, charge, three_halves, 1,
                    (content,), width=117.0, digits=4, note="Breit–Wigner mass and width, rounded")
        out += _pair(h, akey, "anti-Delta(1232)", "Δ̄" + _superscript(acharge), _sup("Δ̄", acharge), rf"\bar{{\Delta}}^{{{acharge}}}")
    return {p.key: p for p in out}


def _superscript(charge: str) -> str:
    return charge.translate(str.maketrans({"+": "⁺", "-": "⁻", "0": "⁰"}))


#: Every particle by key, the Standard Model first, each followed by its antiparticle.
PARTICLES: dict[str, Particle] = _build()
#: The Standard Model's elementary particles (keys), particles and antiparticles.
ELEMENTARY: tuple[str, ...] = tuple(k for k, p in PARTICLES.items() if p.family in ("quark", "lepton", "gauge boson", "scalar boson"))
#: The hadrons (keys).
HADRONS: tuple[str, ...] = tuple(k for k, p in PARTICLES.items() if p.is_hadron)


def particle_problems() -> list[str]:
    """Inconsistencies in the table (empty when it is sound): a hadron's charge or baryon number
    against its quark content, an antiparticle that is not the conjugate, a negative mass."""
    problems: list[str] = []
    for p in PARTICLES.values():
        if p.mass_mev < 0:
            problems.append(f"{p.key}: negative mass")
        anti = PARTICLES.get(p.antiparticle)
        if anti is None or anti.antiparticle != p.key:
            problems.append(f"{p.key}: antiparticle '{p.antiparticle}' does not point back")
        elif anti.charge != -p.charge or anti.baryon != -p.baryon or anti.mass_mev != p.mass_mev:
            problems.append(f"{p.key}: antiparticle numbers are not reversed")
        for c in p.components:
            if p.is_hadron and (content_charge(c) != p.charge or content_baryon(c) != p.baryon):
                problems.append(f"{p.key}: charge {p.charge} / baryon number {p.baryon} disagree with its quark content {c}")
        if p.is_hadron and p.baryon not in (0, 1, -1):
            problems.append(f"{p.key}: a hadron with baryon number {p.baryon}")
    return problems


__all__ = [
    "EDITION",
    "ELEMENTARY",
    "ENERGY_UNITS",
    "FAMILIES",
    "FLAVOURS",
    "FLAVOUR_NAMES",
    "HADRONS",
    "HBAR_MEV_S",
    "LEPTON_FAMILIES",
    "PARTICLES",
    "QUARK_NUMBERS",
    "SOURCE",
    "Particle",
    "content_baryon",
    "content_charge",
    "content_flavour",
    "energy_text",
    "fraction_text",
    "particle_problems",
    "quark_symbol",
    "time_text",
]
