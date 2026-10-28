"""Values written by authors with their units (``"1 AU"``, ``"7.8 km/s"``, ``"92.7 min"``,
``"45 deg"``), read through the units engine of :mod:`vidgen.quantities` into SI numbers, and
the units orbits are shown in (Phase X, DESIGN §98). No manim."""

from __future__ import annotations

import math
import re
from typing import Any

from vidgen.errors import VidgenError
from vidgen.quantities import QuantityError, constant, describe_dim, dim, written
from vidgen.quantities.units import DIMENSIONLESS

#: The dimension of each kind of value an orbit takes.
KINDS = {
    "length": dim(m=1),
    "speed": dim(m=1, s=-1),
    "time": dim(s=1),
    "angle": DIMENSIONLESS,
    "gm": dim(m=3, s=-2),
    "mass": dim(kg=1),
}
#: How to write each kind (for error messages).
EXAMPLES = {
    "length": "'1.5 AU', '7000 km' or '42164 km'",
    "speed": "'7.8 km/s' or '29780 m/s'",
    "time": "'365.25 d', '92 min', '2 yr' or '3600 s'",
    "angle": "a number of degrees (51.6), '51.6 deg' or '0.9 rad'",
    "gm": "'3.986e14 m^3/s^2' (or give mass: '5.97e24 kg')",
    "mass": "'5.97e24 kg', '2.1 Msun' or '0.5 Mearth'",
}
#: The gravitational constant (CODATA 2022) for a body given by its mass, and the astronomical
#: unit (IAU 2012), from :mod:`vidgen.quantities.constants`.
G = float(constant("G").number())
AU = float(constant("AU").number())
DAY = 86_400.0
YEAR = 365.25 * DAY
#: Masses in solar and Earth masses ('2.1 Msun', '0.5 Mearth'), read as GM / G with the IAU
#: nominal GM so a body given in solar masses has exactly that many GM☉.
GM_SUN_NOMINAL = float(constant("GM_sun").number())
GM_EARTH_NOMINAL = float(constant("GM_earth").number())
_SOLAR = re.compile(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(M_?sun|M☉|M_?earth|M⊕)", re.IGNORECASE)


def value_si(value: Any, kind: str, where: str) -> float:
    """``value`` (a number or text with a unit) of ``kind`` (``length``, ``speed``, ``time``,
    ``angle``, ``gm``, ``mass``) in SI (an angle in radians; a bare number is degrees). Raises
    :class:`VidgenError` naming ``where`` for a missing or wrong unit."""
    if isinstance(value, bool) or value is None:
        raise VidgenError(f"{where}: {value!r} is not a value; write {EXAMPLES[kind]}")
    if kind == "angle" and isinstance(value, (int, float)):
        return math.radians(float(value))
    if isinstance(value, (int, float)):
        raise VidgenError(f"{where}: {value:g} needs a unit; write {EXAMPLES[kind]}")
    solar = _SOLAR.fullmatch(str(value).strip()) if kind == "mass" else None
    if solar is not None:   # '2.1 Msun': the mass whose G × mass is that many nominal GM☉ (GM⊕)
        return float(solar.group(1)) * (GM_SUN_NOMINAL if solar.group(2).lower().replace("_", "") in ("msun", "m☉") else GM_EARTH_NOMINAL) / G
    try:
        w = written(str(value).strip())
    except QuantityError as error:
        raise VidgenError(f"{where}: {error}; write {EXAMPLES[kind]}") from None
    q = w.quantity
    if kind == "angle" and not w.unit.parts:
        return math.radians(float(q.value))
    if not w.unit.parts and kind != "angle":
        raise VidgenError(f"{where}: '{value}' needs a unit; write {EXAMPLES[kind]}")
    if q.dim != KINDS[kind]:
        raise VidgenError(f"{where}: '{value}' is {describe_dim(q.dim)}, not a {kind if kind != 'gm' else 'gravitational parameter GM'}; "
                          f"write {EXAMPLES[kind]}")
    out = float(q.value)
    if not math.isfinite(out):
        raise VidgenError(f"{where}: '{value}' is not a finite number")
    return out


def length_unit(extent: float, unit: str = "auto") -> tuple[str, float]:
    """The unit lengths are shown in and its size in metres: ``AU`` when the view spans more
    than 0.05 AU (``auto``), else ``km``."""
    if unit == "AU" or (unit == "auto" and extent > 0.05 * AU):
        return "AU", AU
    if unit in ("km", "auto"):
        return "km", 1000.0
    raise VidgenError(f"unit '{unit}' is not auto, AU or km")


def time_unit(span: float) -> tuple[str, float]:
    """The unit a time readout of a run of ``span`` seconds uses: min, h, d or yr."""
    if span <= 3 * 3600:
        return "min", 60.0
    if span <= 4 * DAY:
        return "h", 3600.0
    if span <= 3 * YEAR:
        return "d", DAY
    return "yr", YEAR


def speedup_text(factor: float) -> str:
    """A speed-up factor in words a viewer reads at a glance: ``× 1.6 million``, ``× 4 800``,
    ``× 2.3 billion``."""
    if not math.isfinite(factor) or factor <= 0:
        return "×  —"
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if factor >= size:
            v = factor / size
            return f"× {v:.2g} {word}" if v < 10 else f"× {v:.0f} {word}"
    if factor >= 100:
        digits = f"{round(factor, -int(math.floor(math.log10(factor))) + 1):.0f}"
        groups = []
        while digits:
            groups.insert(0, digits[-3:])
            digits = digits[:-3]
        return "× " + " ".join(groups)
    return f"× {factor:.2g}"


__all__ = ["AU", "DAY", "EXAMPLES", "G", "KINDS", "YEAR", "length_unit", "speedup_text", "time_unit", "value_si"]
