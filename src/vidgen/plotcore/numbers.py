"""Numbers on scientific axes: plain decimals, powers of ten and SI prefixes, written with
Unicode (superscript exponents, the minus sign U+2212, ``×``), so labels need no LaTeX."""

from __future__ import annotations

import math
from collections.abc import Sequence

from vidgen.errors import VidgenError

#: The minus sign of typeset numbers (U+2212), never the hyphen.
MINUS = "−"
#: Multiplication sign between a mantissa and its power of ten.
TIMES = "×"
_SUPERSCRIPTS = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
#: SI prefixes by power of ten (2022 set: ronna / quetta and ronto / quecto included).
SI_PREFIXES: dict[int, str] = {
    -30: "q", -27: "r", -24: "y", -21: "z", -18: "a", -15: "f", -12: "p", -9: "n", -6: "µ", -3: "m",
    0: "", 3: "k", 6: "M", 9: "G", 12: "T", 15: "P", 18: "E", 21: "Z", 24: "Y", 27: "R", 30: "Q",
}
#: Every prefix symbol a unit may already carry (also centi, deci, deca, hecto), for checks.
_ALL_PREFIXES = {v: k for k, v in SI_PREFIXES.items() if v} | {"c": -2, "d": -1, "da": 1, "h": 2, "u": -6, "μ": -6}
#: Units that take SI prefixes (``si`` tick format); a unit already prefixed is refused.
SI_UNITS = frozenset(
    "m s g Hz eV J W V A N Pa C F Ω ohm T Wb H S Bq Gy Sv mol L l K cd lm lx bar t Da B b".split()
)
#: Tick formats an axis accepts besides a ``str.format`` pattern.
TICK_FORMATS = ("auto", "plain", "sci", "si")


def clean(value: float) -> float:
    """``value`` rounded to 12 significant digits (sums of steps without float noise); ``-0.0``
    becomes ``0.0``."""
    if value == 0 or not math.isfinite(value):
        return 0.0 if value == 0 else value
    return float(f"{value:.12g}") + 0.0


def superscript(n: int) -> str:
    """An integer in superscript digits: ``-3`` -> ``⁻³``."""
    return str(n).translate(_SUPERSCRIPTS)


def power_of_ten(n: int) -> str:
    """``10ⁿ`` with a superscript exponent: ``power_of_ten(-6)`` -> ``10⁻⁶``."""
    return "10" + superscript(n)


def exponent_of(value: float) -> int:
    """The decade of ``value``: ``floor(log10 |value|)`` (0 for 0), robust to float noise
    (``exponent_of(1000) == 3``)."""
    if value == 0 or not math.isfinite(value):
        return 0
    e = math.floor(math.log10(abs(value)))
    if abs(value) >= 10.0 ** (e + 1) * (1 - 1e-12):
        e += 1
    return e


def decimals_needed(values: Sequence[float], max_decimals: int = 8) -> int:
    """The fewest decimals (up to ``max_decimals``) that write every value exactly, to 1e-7 of
    the values' spread (of the largest magnitude for one value): ``[0, 0.5, 1]`` -> 1,
    ``[0.25]`` -> 2, ``[1e-9]`` -> ``max_decimals``, ``[1e9, 1e9 + 1]`` -> 0."""
    need = 0
    spread = (max(values) - min(values)) if values else 0.0
    scale = spread or max((abs(v) for v in values), default=0.0)
    for v in values:
        for d in range(max_decimals + 1):
            if abs(round(v, d) - v) <= 1e-7 * scale:
                need = max(need, d)
                break
        else:
            need = max_decimals
    return need


def plain_number(value: float, decimals: int = 0) -> str:
    """``value`` with ``decimals`` decimals and a typographic minus; never ``-0``."""
    text = f"{value:.{max(0, decimals)}f}"
    if text.startswith("-"):
        text = text[1:] if float(text) == 0 else MINUS + text[1:]
    return text


def sci_number(value: float, digits: int | None = None) -> str:
    """``value`` as a mantissa times a power of ten: ``2.5 × 10⁻³``; a mantissa of 1 is left
    out (``10⁶``, ``−10⁶``); powers 0 are written plainly (``4.2``). ``digits`` = significant
    digits of the mantissa (default: as many as it needs, up to 6)."""
    if value == 0:
        return "0"
    e = exponent_of(value)
    mantissa = value / 10.0**e
    decimals = decimals_needed([mantissa], 5) if digits is None else max(0, digits - 1)
    text = plain_number(mantissa, decimals)
    if abs(float(text.replace(MINUS, "-"))) >= 10:  # rounding carried into the next decade
        e += 1
        text = plain_number(math.copysign(1.0, value), 0)
    if e == 0:
        return text
    if text in ("1", MINUS + "1"):
        return text[:-1] + power_of_ten(e)
    return f"{text} {TIMES} {power_of_ten(e)}"


def prefixed_unit_problem(unit: str) -> str | None:
    """Why ``unit`` cannot take SI prefixes on an axis, or ``None``: it must be a base unit
    (``m``, ``s``, ``eV``...) without a prefix (``km`` -> write ``m``)."""
    base = unit.strip()
    if not base:
        return "the si format needs a unit (e.g. unit: m)"
    if base in SI_UNITS:
        return None
    for prefix in sorted(_ALL_PREFIXES, key=len, reverse=True):
        if base.startswith(prefix) and base[len(prefix):] in SI_UNITS:
            return f"unit '{base}' already has the prefix '{prefix}'; write the base unit '{base[len(prefix):]}' and let si choose the prefix"
    return f"unit '{base}' does not take SI prefixes (si works with {', '.join(sorted(SI_UNITS, key=str.lower)[:8])}...); use format: sci or auto"


def si_parts(value: float) -> tuple[float, str]:
    """``value`` scaled into ``[1, 1000)`` and its SI prefix: ``0.0025`` -> ``(2.5, "m")``."""
    if value == 0:
        return 0.0, ""
    e = max(min(3 * math.floor(exponent_of(value) / 3), 30), -30)
    return value / 10.0**e, SI_PREFIXES[e]


def si_number(value: float, unit: str, decimals: int | None = None) -> str:
    """``value`` with an SI prefix on ``unit``: ``si_number(2.5e-6, "s")`` -> ``2.5 µs``."""
    scaled, prefix = si_parts(value)
    d = decimals_needed([scaled], 3) if decimals is None else decimals
    return f"{plain_number(scaled, d)} {prefix}{unit}".rstrip()


def check_tick_format(fmt: str) -> str:
    """A tick format: ``auto``, ``plain``, ``sci``, ``si`` or a ``str.format`` pattern such as
    ``"{:.1f}"`` (checked on a number). Returns it; raises ``ValueError`` otherwise."""
    if fmt in TICK_FORMATS:
        return fmt
    if "{" not in fmt:
        raise ValueError(f"format '{fmt}' is not one of {', '.join(TICK_FORMATS)} or a pattern such as '{{:.1f}}'")
    try:
        fmt.format(1234.5)
    except (ValueError, IndexError, KeyError) as exc:
        raise ValueError(f"invalid number format {fmt!r}: {exc}") from None
    return fmt


def _pattern(value: float, fmt: str) -> str:
    try:
        return fmt.format(value).replace("-", MINUS)
    except (ValueError, IndexError, KeyError) as exc:
        raise VidgenError(f"invalid number format {fmt!r}: {exc}") from None


#: Plain labels on a linear axis while the largest tick is below this (else a power of ten).
PLAIN_MAX = 1e5
#: ... and while the largest tick is at least this.
PLAIN_MIN = 1e-3


class TickLabels:
    """The labels of an axis' ticks and what the axis title must add: ``exponent`` (the ticks
    are in units of 10^exponent, written in the title) or ``title_unit`` (the unit as the title
    shows it, e.g. ``ms`` after an SI prefix was chosen; ``""`` when the ticks carry it)."""

    def __init__(self, labels: list[str], exponent: int = 0, title_unit: str = "") -> None:
        self.labels, self.exponent, self.title_unit = labels, exponent, title_unit

    def __repr__(self) -> str:
        return f"TickLabels({self.labels!r}, exponent={self.exponent}, title_unit={self.title_unit!r})"


def tick_labels(ticks: Sequence[float], fmt: str = "auto", unit: str = "", *, scale: str = "linear") -> TickLabels:
    """Labels for ``ticks`` on a ``linear``, ``log`` or ``symlog`` axis in a tick format.

    - ``auto``: linear: plain numbers with the decimals the ticks need while the largest tick
      lies in ``[PLAIN_MIN, PLAIN_MAX)``, else the ticks are divided by a power of ten that is a
      multiple of 3 and the title says it (``× 10⁶``); log / symlog: plain from 0.001 to 10 000,
      else powers of ten (``10⁻⁹``).
    - ``plain``: plain numbers; ``sci``: each tick a mantissa times a power of ten.
    - ``si``: linear: one SI prefix for the axis, chosen by the largest tick, written in the
      title's unit (``time (ms)``); log / symlog: each tick with its own prefix and the unit
      (``10 kHz``). The unit must be a base unit (:func:`prefixed_unit_problem`).
    - a ``str.format`` pattern (``"{:.1f}"``) for every tick.
    """
    values = [clean(t) for t in ticks]
    if not values:
        return TickLabels([], 0, unit)
    top = max(abs(v) for v in values)
    if fmt not in TICK_FORMATS:
        return TickLabels([_pattern(v, fmt) for v in values], 0, unit)
    if fmt == "si":
        problem = prefixed_unit_problem(unit)
        if problem:
            raise VidgenError(problem)
        if scale != "linear":
            return TickLabels(["0" if v == 0 else si_number(v, unit) for v in values], 0, "")
        _, prefix = si_parts(top)
        e = next(k for k, p in SI_PREFIXES.items() if p == prefix)
        scaled = [clean(v / 10.0**e) for v in values]
        d = decimals_needed(scaled, 6)
        return TickLabels([plain_number(s, d) for s in scaled], 0, prefix + unit)
    if fmt == "sci":
        return TickLabels([sci_number(v) for v in values], 0, unit)
    if fmt == "plain":
        return TickLabels([plain_number(v, decimals_needed(values)) for v in values], 0, unit)
    if scale != "linear":
        nonzero = [abs(v) for v in values if v != 0]
        if all(PLAIN_MIN * (1 - 1e-9) <= v <= 1e4 * (1 + 1e-9) for v in nonzero):
            return TickLabels([plain_number(v, decimals_needed([v])) for v in values], 0, unit)
        return TickLabels([sci_number(v) for v in values], 0, unit)
    if top == 0 or PLAIN_MIN <= top < PLAIN_MAX:
        d = decimals_needed(values)
        if d <= 6:
            return TickLabels([plain_number(v, d) for v in values], 0, unit)
    e = 3 * math.floor(exponent_of(top) / 3)
    scaled = [clean(v / 10.0**e) for v in values]
    d = decimals_needed(scaled, 6)
    if d > 4:
        spread = max(values) - min(values)
        if spread < 1e-3 * top:   # a narrow window far from 0 (10⁹ .. 10⁹ + 3): written in full
            return TickLabels([plain_number(v, decimals_needed(values, 12)) for v in values], 0, unit)
        return TickLabels([sci_number(v) for v in values], 0, unit)
    return TickLabels([plain_number(s, d) for s in scaled], e, unit)


def axis_title(label: str, unit: str = "", exponent: int = 0) -> str:
    """An axis title in the form ``label (unit)``: ``time (s)``, ``distance (10⁶ km)``,
    ``count (× 10³)``; just the label without unit or exponent."""
    if exponent:
        inner = f"{power_of_ten(exponent)} {unit}".strip() if unit else f"{TIMES} {power_of_ten(exponent)}"
    else:
        inner = unit.strip()
    if not label:
        return inner
    return f"{label} ({inner})" if inner else label


def error_digits(error: float) -> tuple[float, int]:
    """``error`` rounded by the Particle Data Group's rule and the decimal place it ends at:
    its three leading digits 100–354 keep two significant digits, 355–949 one, 950–999 round
    up to 1000 with two (``0.0123`` -> ``(0.012, 3)``, ``0.47`` -> ``(0.5, 1)``)."""
    e = exponent_of(error)
    lead = int(round(error / 10.0 ** (e - 2)))   # three leading digits, 100..1000
    if lead >= 1000:
        e, lead = e + 1, 100
    if lead <= 354:
        digits = 2
    elif lead <= 949:
        digits = 1
    else:
        e, digits = e + 1, 2
    place = e - digits + 1
    return clean(round(error / 10.0**place) * 10.0**place), -place


def _round_half_up(value: float, decimals: int) -> float:
    """``value`` rounded to ``decimals`` (negative: tens, hundreds) with halves away from 0, as
    results are written (Python's ``round`` goes to the even neighbour: 12345 -> 12340)."""
    step = 10.0 ** (-decimals)
    q = abs(value) / step
    rounded = math.floor(q + 0.5 + 1e-9 * max(q, 1.0))
    return math.copysign(clean(rounded * step), value) + 0.0


def value_with_error(value: float, error: float | None, unit: str = "", digits: int = 4) -> str:
    """``value ± error`` as a result is written: the error rounded by :func:`error_digits`, the
    value to the same decimal place, a power of ten outside brackets when the value is below
    10⁻³ or from 10⁵ (``(2.51 ± 0.03) × 10⁻⁴ s⁻¹``), then the unit. Without a usable error the
    value with ``digits`` significant digits."""
    unit = f" {unit}" if unit else ""
    if not math.isfinite(value):
        return f"{value}{unit}"
    if error is None or not math.isfinite(error) or error <= 1e-12 * abs(value):   # no error, or one of float noise (an exact fit)
        top = abs(value)
        if top == 0 or PLAIN_MIN <= top < PLAIN_MAX:
            d = max(0, digits - 1 - exponent_of(value)) if value else 0
            return plain_number(value, min(d, 8)) + unit
        return sci_number(float(f"{value:.{digits}g}")) + unit
    top = max(abs(value), error)
    e = 0 if PLAIN_MIN <= top < PLAIN_MAX else exponent_of(top)
    scaled_error, decimals = error_digits(error / 10.0**e)
    scaled_value = _round_half_up(value / 10.0**e, decimals)
    d = max(decimals, 0)
    body = f"{plain_number(scaled_value, d)} ± {plain_number(scaled_error, d)}"
    if e:
        return f"({body}) {TIMES} {power_of_ten(e)}{unit}"
    return body + unit


__all__ = [
    "MINUS",
    "PLAIN_MAX",
    "PLAIN_MIN",
    "SI_PREFIXES",
    "SI_UNITS",
    "TICK_FORMATS",
    "TIMES",
    "TickLabels",
    "axis_title",
    "check_tick_format",
    "clean",
    "decimals_needed",
    "error_digits",
    "exponent_of",
    "plain_number",
    "power_of_ten",
    "prefixed_unit_problem",
    "sci_number",
    "si_number",
    "si_parts",
    "superscript",
    "tick_labels",
    "value_with_error",
]
