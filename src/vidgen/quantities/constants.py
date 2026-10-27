"""Physical and astronomical constants for worked calculations (DESIGN §97.9). No manim.

Sources:

- **SI 2019** (BIPM SI Brochure, 9th edition, 2019): the defining constants are exact —
  c, h, e, k_B, N_A (so ħ, R = N_A·k_B and σ are exact too, ħ and σ irrational).
- **CODATA 2022** (Mohr, Tiesinga, Newell, Taylor, *CODATA recommended values of the fundamental
  physical constants: 2022*, published 2024): G, m_e, m_p, m_u (dalton), ε₀, μ₀.
- **CGPM 1901**: standard gravity g_n = 9.806 65 m s⁻² (exact by definition).
- **IAU 2012 Resolution B2**: the astronomical unit, 149 597 870 700 m (exact).
- **IAU 2015 Resolution B3**: nominal (GM)☉ = 1.327 124 4 × 10²⁰ m³ s⁻², (GM)⊕ = 3.986 004 ×
  10¹⁴ m³ s⁻², nominal equatorial Earth radius 6.378 1 × 10⁶ m. The masses M☉ and M⊕ are those
  products divided by CODATA 2022 G, so they carry G's six significant figures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from vidgen.errors import VidgenError


@dataclass(frozen=True)
class Constant:
    """A constant: ``value`` as text (its digits are its significant figures unless
    ``exact``), its ``unit``, TeX symbol, meaning and source."""

    key: str
    value: str
    unit: str
    tex: str
    meaning: str
    source: str
    exact: bool = False
    #: An exact value that is not a decimal (ħ = h/2π): kept as a float.
    irrational: bool = False

    def number(self) -> Fraction | float:
        """The value: a Fraction when the decimal text is exact, else a float."""
        if self.irrational:
            return float(self.value)
        try:
            return Fraction(self.value)
        except ValueError:
            return float(self.value)


_HBAR = 6.62607015e-34 / (2 * math.pi)
_SIGMA = 2 * math.pi**5 * 1.380649e-23**4 / (15 * 6.62607015e-34**3 * 299792458.0**2)

#: The constants by key (the name a calculation's symbol table uses: ``{name: G, constant: G}``).
CONSTANTS: dict[str, Constant] = {
    c.key: c
    for c in [
        Constant("c", "299792458", "m/s", "c", "speed of light in vacuum", "SI 2019 (exact)", True),
        Constant("G", "6.67430e-11", "m^3 kg^-1 s^-2", "G", "gravitational constant", "CODATA 2022"),
        Constant("h", "6.62607015e-34", "J*s", "h", "Planck constant", "SI 2019 (exact)", True),
        Constant("hbar", repr(_HBAR), "J*s", r"\hbar", "reduced Planck constant", "SI 2019 (exact, h/2π)", True, True),
        Constant("k_B", "1.380649e-23", "J/K", r"k_{\mathrm{B}}", "Boltzmann constant", "SI 2019 (exact)", True),
        Constant("N_A", "6.02214076e23", "mol^-1", r"N_{\mathrm{A}}", "Avogadro constant", "SI 2019 (exact)", True),
        Constant("e", "1.602176634e-19", "C", "e", "elementary charge", "SI 2019 (exact)", True),
        Constant("R", "8.31446261815324", "J/(mol*K)", "R", "molar gas constant", "SI 2019 (exact, N_A·k_B)", True),
        Constant("sigma_SB", repr(_SIGMA), "W m^-2 K^-4", r"\sigma", "Stefan–Boltzmann constant", "SI 2019 (exact)", True, True),
        Constant("m_e", "9.1093837139e-31", "kg", r"m_{\mathrm{e}}", "electron mass", "CODATA 2022"),
        Constant("m_p", "1.67262192595e-27", "kg", r"m_{\mathrm{p}}", "proton mass", "CODATA 2022"),
        Constant("m_u", "1.66053906892e-27", "kg", r"m_{\mathrm{u}}", "atomic mass constant (1 Da)", "CODATA 2022"),
        Constant("epsilon_0", "8.8541878188e-12", "F/m", r"\varepsilon_{0}", "vacuum electric permittivity", "CODATA 2022"),
        Constant("mu_0", "1.25663706127e-6", "N/A^2", r"\mu_{0}", "vacuum magnetic permeability", "CODATA 2022"),
        Constant("g", "9.80665", "m/s^2", "g", "standard gravity", "CGPM 1901 (exact)", True),
        Constant("AU", "149597870700", "m", r"\mathrm{au}", "astronomical unit", "IAU 2012 (exact)", True),
        Constant("GM_sun", "1.3271244e20", "m^3 s^-2", r"GM_{\odot}", "solar mass parameter", "IAU 2015 (nominal)"),
        Constant("GM_earth", "3.986004e14", "m^3 s^-2", r"GM_{\oplus}", "Earth mass parameter", "IAU 2015 (nominal)"),
        Constant("M_sun", "1.98841e30", "kg", r"M_{\odot}", "mass of the Sun", "IAU 2015 / CODATA 2022"),
        Constant("M_earth", "5.97217e24", "kg", r"M_{\oplus}", "mass of the Earth", "IAU 2015 / CODATA 2022"),
        Constant("R_earth", "6.3781e6", "m", r"R_{\oplus}", "equatorial radius of the Earth", "IAU 2015 (nominal)"),
    ]
}
#: Other spellings of the keys.
ALIASES: dict[str, str] = {
    "hbar": "hbar", "h_bar": "hbar", "kB": "k_B", "k": "k_B", "NA": "N_A", "me": "m_e", "mp": "m_p", "u": "m_u", "Da": "m_u",
    "eps0": "epsilon_0", "epsilon0": "epsilon_0", "mu0": "mu_0", "g_n": "g", "au": "AU", "Msun": "M_sun", "M_sol": "M_sun",
    "Mearth": "M_earth", "M_E": "M_earth", "Rearth": "R_earth", "R_E": "R_earth", "GMsun": "GM_sun", "GMearth": "GM_earth",
    "sigma": "sigma_SB", "c0": "c", "q_e": "e",
}


def constant(key: str) -> Constant:
    """The constant called ``key`` (or an alias); raises :class:`VidgenError` with
    did-you-mean otherwise."""
    if key in CONSTANTS:
        return CONSTANTS[key]
    if key in ALIASES:
        return CONSTANTS[ALIASES[key]]
    import difflib

    names = list(CONSTANTS) + list(ALIASES)
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.6)
    hint = f" (did you mean '{ALIASES.get(close[0], close[0])}'?)" if close else ""
    raise VidgenError(f"unknown constant '{key}'{hint}; constants: {', '.join(CONSTANTS)}")


__all__ = ["ALIASES", "CONSTANTS", "Constant", "constant"]
