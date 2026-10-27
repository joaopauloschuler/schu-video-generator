"""Quantities with units, exactness and significant figures (DESIGN §97.9). No manim.

A :class:`Quantity` is an SI value (a :class:`~fractions.Fraction` while it is exact and
rational, else a float), a dimension and its significant figures (``sig``; ``None``: exact —
a count, a defined constant, a fraction such as 1/4). The arithmetic here checks dimensions
(:class:`QuantityError` explains both sides) and carries significant figures by the school
rules: a product or quotient has the fewest significant figures of its measured factors; a sum
or difference keeps the coarsest last decimal place (its resolution); functions keep their
argument's. Numbers are written with :func:`decimal_text` (rounded half away from zero, plain
between 10⁻³ and 10⁵ when no digit before the point is uncertain, else scientific notation like
the plot core), fractions with :func:`fraction_text`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

from vidgen.errors import VidgenError

from .units import DIMENSIONLESS, Dim, Number, Unit, describe_dim, dim_div, dim_mul, dim_pow, parse_unit

#: Plain numbers from here up to :data:`PLAIN_MAX` (as the plot core's tick labels).
PLAIN_MIN = 1e-3
PLAIN_MAX = 1e5
#: Significant figures a value may claim (a float holds about 15).
MAX_SIG = 15
#: Fractions are written as fractions up to this numerator / denominator.
FRACTION_LIMIT = 100000


class QuantityError(VidgenError):
    """A calculation that cannot be done: incompatible units, a division by zero, a function
    of a quantity with a unit..."""


@dataclass(frozen=True)
class Quantity:
    """An SI ``value`` of dimension ``dim`` with ``sig`` significant figures (``None``: exact).
    ``temperature``: ``"point"`` for a value written on a scale with an offset (°C, °F; a
    reading of a thermometer), ``"difference"`` for the difference of two such readings, else
    ``""``. In SI (kelvin) the arithmetic is right either way; the marks catch the two slips
    authors make with °C: adding two readings (20 °C + 10 °C, where 10 °C was meant as a
    change) and writing a difference in °C (10 K would read as −263 °C)."""

    value: Number
    dim: Dim = DIMENSIONLESS
    sig: int | None = None
    temperature: str = ""

    @property
    def exact(self) -> bool:
        return self.sig is None

    @property
    def rational(self) -> bool:
        """Exact and a fraction (1/150), not an exact irrational (ln 2, π)."""
        return self.sig is None and isinstance(self.value, Fraction)

    def __float__(self) -> float:
        return float(self.value)


# ----- significant figures ------------------------------------------------------------------------

def decade(value: Number) -> int:
    """``floor(log10 |value|)``, exact for fractions and robust for floats (0 for 0)."""
    if value == 0:
        return 0
    with localcontext() as ctx:
        ctx.prec = 50
        d = _decimal(value)
        return d.adjusted()


def _decimal(value: Number) -> Decimal:
    if isinstance(value, Fraction):
        with localcontext() as ctx:
            ctx.prec = 50
            return Decimal(value.numerator) / Decimal(value.denominator)
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(repr(float(value)))


def resolution(q: Quantity) -> float:
    """The place of a measured value's last significant digit (0 for an exact one)."""
    if q.sig is None:
        return 0.0
    return 10.0 ** (decade(q.value) - q.sig + 1) if q.value != 0 else 10.0 ** (1 - q.sig)


def sig_from_resolution(value: Number, res: float) -> int:
    """Significant figures of ``value`` known to ``res`` (at least 1)."""
    if res <= 0:
        return MAX_SIG
    if value == 0:
        return 1
    return max(1, decade(value) - math.floor(math.log10(res) + 1e-9) + 1)


def count_sig(text: str) -> int:
    """Significant figures of a number as written: leading zeros never count, trailing zeros
    count after a decimal point (``0.0250`` -> 3, ``2.50e3`` -> 3), not in a whole number
    without one (``1500`` -> 2)."""
    mantissa = re.split(r"[eE]|\s*[×x*]\s*10\^", text.strip().lstrip("+-−"))[0]
    if "." in mantissa:
        digits = mantissa.replace(".", "").lstrip("0")
        return max(1, len(digits)) if digits else max(1, len(mantissa.split(".")[1]))
    digits = mantissa.lstrip("0").rstrip("0")
    return max(1, len(digits))


def round_sig(value: Number, sig: int) -> Decimal:
    """``value`` rounded to ``sig`` significant figures, halves away from zero."""
    with localcontext() as ctx:
        ctx.prec = 60
        d = _decimal(value)
        if d == 0:
            return Decimal(0)
        place = d.adjusted() - sig + 1
        q = d.quantize(Decimal(1).scaleb(place), rounding=ROUND_HALF_UP)
        if q.adjusted() > d.adjusted():   # 9.996 -> 10.0: keep sig digits
            q = q.quantize(Decimal(1).scaleb(place + 1), rounding=ROUND_HALF_UP)
        return q


# ----- writing numbers ----------------------------------------------------------------------------

MINUS = "−"
_SUPER = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


@dataclass(frozen=True)
class NumberText:
    """A number as text (Unicode) and as TeX; ``approx``: rounded (written after ``≈``);
    ``sci``: a mantissa times a power of ten (a product, for brackets)."""

    plain: str
    tex: str
    approx: bool = False
    sci: bool = False
    fraction: bool = False


def _plain_decimal(d: Decimal, decimals: int) -> str:
    text = f"{d:.{max(0, decimals)}f}"
    return "0" + text[2:] if text.startswith("-0") and float(text) == 0 else text


def decimal_text(value: Number, sig: int, mode: str = "auto") -> NumberText:
    """``value`` with ``sig`` significant figures: ``plain`` (``0.00667``), ``sci`` (``2.98 ×
    10⁴``) or ``auto`` — plain from 10⁻³ to 10⁵ when no digit left of the decimal point is
    uncertain (29 800 with 3 significant figures is written 2.98 × 10⁴)."""
    if not math.isfinite(float(value)):
        raise QuantityError(f"the result is not a finite number ({float(value)})")
    q = round_sig(value, sig)
    approx = Fraction(q) != Fraction(value) if isinstance(value, Fraction) else True
    if q == 0:
        text = _plain_decimal(q, sig - 1)
        return NumberText(text, text, approx)
    e = q.adjusted()
    place = e - sig + 1
    # a whole number ending in a significant 0 (240 to 3 figures) would read as less precise
    ambiguous = place == 0 and q % 10 == 0
    if mode == "plain" or (mode == "auto" and place <= 0 and not ambiguous and PLAIN_MIN <= abs(q) < PLAIN_MAX):
        text = _plain_decimal(q, -place)
        return NumberText(text.replace("-", MINUS), text, approx)
    mantissa = _plain_decimal(q.scaleb(-e), sig - 1)
    plain = f"{mantissa.replace('-', MINUS)} × 10{str(e).translate(_SUPER)}"
    tex = rf"{mantissa} \times 10^{{{e}}}"
    return NumberText(plain, tex, approx, sci=True)


def fraction_text(value: Fraction) -> NumberText:
    """An exact fraction: ``1/150``, ``\\frac{1}{150}``; a whole number plainly."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v.denominator == 1:
        return NumberText((sign + str(v.numerator)).replace("-", MINUS), sign + str(v.numerator))
    return NumberText(f"{sign}{v.numerator}/{v.denominator}".replace("-", MINUS), rf"{sign}\frac{{{v.numerator}}}{{{v.denominator}}}", fraction=True)


def nice_fraction(value: Number) -> bool:
    """Whether an exact value reads well as a fraction (numerator and denominator up to
    :data:`FRACTION_LIMIT`)."""
    return isinstance(value, Fraction) and value.denominator != 1 and abs(value.numerator) <= FRACTION_LIMIT and value.denominator <= FRACTION_LIMIT


_NUMBER = re.compile(
    r"^\s*(?P<num>[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:(?:[eE][+\-−]?\d+)|(?:\s*[×x*]\s*10\s*\^\s*\(?[+\-−]?\d+\)?))?)"
    r"(?:\s*/\s*(?P<den>\d+)(?![\d.]))?"
)


def split_number(text: str) -> tuple[str, str | None, str]:
    """``(number, denominator, rest)`` of ``"29.8 km/s"``: ``("29.8", None, "km/s")``;
    ``"1/25"`` -> ``("1", "25", "")``. Raises ``ValueError`` when ``text`` starts with no
    number."""
    m = _NUMBER.match(text)
    if m is None:
        raise ValueError(f"'{text}' does not start with a number")
    num = m.group("num").replace("−", "-")
    rest = text[m.end():].strip()
    den = m.group("den")
    if den is not None and "." in num or den is not None and re.search(r"[eE×x*]", num):
        raise ValueError(f"'{text}': a fraction is written with whole numbers (1/25)")
    return num, den, rest


def number_value(num: str) -> Fraction:
    """The exact value of a decimal written as text (``6.674e-11``, ``2.5 × 10^3``)."""
    m = re.match(r"^(.*?)\s*[×x*]\s*10\s*\^\s*\(?([+\-]?\d+)\)?$", num)
    if m:
        return Fraction(m.group(1)) * Fraction(10) ** int(m.group(2))
    return Fraction(num)


def written_number(num: str, den: str | None = None) -> NumberText:
    """A number as the author wrote it: ``6.674e-11`` -> ``6.674 × 10⁻¹¹`` (same digits),
    ``1/25`` -> a fraction, ``29.8`` as is."""
    if den is not None:
        return fraction_text(Fraction(int(num), int(den)))
    m = re.match(r"^([+\-]?[\d.]+)(?:[eE]([+\-]?\d+)|\s*[×x*]\s*10\s*\^\s*\(?([+\-]?\d+)\)?)$", num)
    if m:
        e = int(m.group(2) or m.group(3))
        mantissa = m.group(1)
        return NumberText(f"{mantissa.replace('-', MINUS)} × 10{str(e).translate(_SUPER)}", rf"{mantissa} \times 10^{{{e}}}", sci=True)
    return NumberText(num.replace("-", MINUS), num)


# ----- arithmetic -------------------------------------------------------------------------------

def _is_exact_number(v: Number) -> bool:
    return isinstance(v, (Fraction, int))


def _sig_min(*sigs: int | None) -> int | None:
    known = [s for s in sigs if s is not None]
    return min(known) if known else None


def check_finite(value: Number, what: str) -> Number:
    if isinstance(value, float) and not math.isfinite(value):
        raise QuantityError(f"{what} is not a finite number (it overflows)")
    return value


def add(a: Quantity, b: Quantity, sign: int = 1, left: str = "", right: str = "") -> Quantity:
    """``a + b`` (``sign`` -1: ``a − b``); the units must agree; the result keeps the coarser
    last decimal place."""
    if a.dim != b.dim:
        verb = "add" if sign > 0 else "subtract"
        joint = "and" if sign > 0 else "from"
        x, y = (left, right) if sign > 0 else (right, left)
        dx, dy = (a.dim, b.dim) if sign > 0 else (b.dim, a.dim)
        raise QuantityError(f"cannot {verb} {x or 'a quantity'} {joint} {y or 'a quantity'}: {describe_dim(dx)} vs {describe_dim(dy)} "
                            "— only quantities of the same kind can be added or subtracted")
    points = (a.temperature == "point", b.temperature == "point")
    if sign > 0 and all(points):
        raise QuantityError(f"cannot add {left or 'a temperature'} and {right or 'a temperature'}: both are readings on a scale "
                            "with an offset (°C or °F); write a change of temperature in K (a change of 10 °C is 10 K), "
                            "or the readings in K to average them")
    temperature = "difference" if all(points) else "point" if points[0] or (points[1] and sign > 0) else \
        "difference" if "difference" in (a.temperature, b.temperature) else ""
    if _is_exact_number(a.value) and _is_exact_number(b.value):
        value: Number = Fraction(a.value) + sign * Fraction(b.value)
    else:
        value = float(a.value) + sign * float(b.value)
    if a.sig is None and b.sig is None:
        return Quantity(value, a.dim, None, temperature)
    res = max(resolution(a), resolution(b))
    return Quantity(value, a.dim, sig_from_resolution(value, res), temperature)


def _scaled_temperature(a: Quantity, b: Quantity) -> str:
    """The mark of a product or quotient: a difference stays one when scaled by a pure number
    (half a change is a change); a reading times anything is no longer a reading."""
    for q, other in ((a, b), (b, a)):
        if q.temperature == "difference" and other.dim == DIMENSIONLESS:
            return "difference"
    return ""


def mul(a: Quantity, b: Quantity) -> Quantity:
    """``a × b``; the fewest significant figures of the measured factors."""
    if _is_exact_number(a.value) and _is_exact_number(b.value):
        value: Number = Fraction(a.value) * Fraction(b.value)
    else:
        value = check_finite(float(a.value) * float(b.value), "a product")
    return Quantity(value, dim_mul(a.dim, b.dim), _sig_min(a.sig, b.sig), _scaled_temperature(a, b))


def div(a: Quantity, b: Quantity, divisor: str = "") -> Quantity:
    """``a / b``; refuses a division by zero."""
    if b.value == 0:
        raise QuantityError(f"division by zero: {divisor or 'the divisor'} is 0")
    if _is_exact_number(a.value) and _is_exact_number(b.value):
        value: Number = Fraction(a.value) / Fraction(b.value)
    else:
        value = check_finite(float(a.value) / float(b.value), "a quotient")
    return Quantity(value, dim_div(a.dim, b.dim), _sig_min(a.sig, b.sig), _scaled_temperature(a, b) if b.dim == DIMENSIONLESS else "")


def neg(a: Quantity) -> Quantity:
    return Quantity(-a.value, a.dim, a.sig, "difference" if a.temperature == "difference" else "")


def _iroot(n: int, k: int) -> int | None:
    """The exact integer ``k``-th root of ``n`` ≥ 0, or ``None``."""
    if n < 0:
        return None
    r = round(n ** (1.0 / k)) if n < 2**1000 else int(math.exp(math.log(n) / k))
    for c in (r - 1, r, r + 1):
        if c >= 0 and c**k == n:
            return c
    return None


def exact_root(value: Fraction, k: int) -> Fraction | None:
    """The exact ``k``-th root of a fraction ≥ 0 when numerator and denominator are perfect
    powers (√(1/2500) = 1/50), else ``None``."""
    if value < 0:
        return None
    n, d = _iroot(value.numerator, k), _iroot(value.denominator, k)
    return Fraction(n, d) if n is not None and d is not None else None


def power(base: Quantity, exponent: Quantity, base_text: str = "", exp_text: str = "") -> Quantity:
    """``base ^ exponent``: the exponent is a pure number; a base with a unit needs a fixed
    rational exponent (``r^2``, ``x^(1/2)``)."""
    if exponent.dim != DIMENSIONLESS:
        raise QuantityError(f"the exponent {exp_text or ''} has a unit ({describe_dim(exponent.dim)}); an exponent must be a pure number".replace("  ", " "))
    p = exponent.value
    if base.dim != DIMENSIONLESS:
        if not (_is_exact_number(p) and exponent.sig is None):
            raise QuantityError(f"{base_text or 'a quantity'} has a unit ({describe_dim(base.dim)}), so its exponent must be a fixed "
                                "number such as 2, -1 or 1/2")
    if base.value == 0 and float(p) < 0:
        raise QuantityError(f"division by zero: {base_text or 'the base'} is 0 and the exponent is negative")
    d = dim_pow(base.dim, Fraction(p)) if base.dim != DIMENSIONLESS else DIMENSIONLESS
    sig = _sig_min(base.sig, exponent.sig)
    if _is_exact_number(base.value) and _is_exact_number(p):
        b, e = Fraction(base.value), Fraction(p)
        whole = b ** abs(e.numerator)
        if e.denominator == 1:
            value: Number = whole if e > 0 else 1 / whole
            return Quantity(value, d, sig)
        if b < 0 and e.denominator % 2 == 0:
            raise QuantityError(f"{base_text or 'the base'} is negative and the exponent {exp_text or p} takes an even root")
        root = exact_root(abs(whole), e.denominator)
        if root is not None:
            root = root if b >= 0 else -root
            return Quantity(root if e > 0 else 1 / root, d, sig)
    fb, fp = float(base.value), float(p)
    if fb < 0 and not float(fp).is_integer():
        raise QuantityError(f"{base_text or 'the base'} is negative and the exponent {exp_text or fp} is not a whole number")
    try:
        value = fb**fp
    except OverflowError:
        raise QuantityError("a power overflows") from None
    if isinstance(value, complex):
        raise QuantityError(f"{base_text or 'the base'} to the power {exp_text} is not a real number")
    return Quantity(check_finite(value, "a power"), d, sig)


_DIMLESS_FUNCS = {
    "exp": math.exp, "ln": math.log, "log": math.log, "log10": math.log10, "log2": math.log2,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
}
#: The functions a calculation may call.
FUNCTIONS = ("sqrt", "abs", "min", "max", *_DIMLESS_FUNCS)


def call(name: str, args: list[Quantity], texts: list[str]) -> Quantity:
    """A function of quantities: ``sqrt`` halves the dimension (exact for perfect squares),
    ``abs`` keeps it, ``min`` / ``max`` need equal units, the others need a pure number (an
    angle in rad or deg is one)."""
    if name == "sqrt":
        a = args[0]
        if a.value < 0:
            raise QuantityError(f"the square root of a negative number ({texts[0]})")
        return power(a, Quantity(Fraction(1, 2)), texts[0], "1/2")
    if name == "abs":
        return Quantity(abs(args[0].value), args[0].dim, args[0].sig, args[0].temperature)
    if name in ("min", "max"):
        a, b = args
        if a.dim != b.dim:
            raise QuantityError(f"{name}({texts[0]}, {texts[1]}): {describe_dim(a.dim)} vs {describe_dim(b.dim)} cannot be compared")
        pick = (min if name == "min" else max)((a, b), key=lambda q: float(q.value))
        return pick
    a = args[0]
    if a.dim != DIMENSIONLESS:
        raise QuantityError(f"{name}({texts[0]}): {texts[0]} has a unit ({describe_dim(a.dim)}); {name} takes a pure number "
                            "(divide by a quantity of the same kind first)")
    try:
        value = _DIMLESS_FUNCS[name](float(a.value))
    except (ValueError, OverflowError):
        raise QuantityError(f"{name}({texts[0]}) is not defined for {float(a.value):g}") from None
    return Quantity(check_finite(value, f"{name}({texts[0]})"), DIMENSIONLESS, a.sig)


# ----- values written by authors ----------------------------------------------------------------

@dataclass(frozen=True)
class Written:
    """A value as written (``"29.8 km/s"``): the quantity in SI, the unit it was written in,
    and the number as written (for the screen)."""

    quantity: Quantity
    unit: Unit
    number: NumberText


def in_unit(q: Quantity, unit: Unit) -> tuple[Number, int | None]:
    """``q``'s value in ``unit`` and its significant figures there (they change only across an
    offset: 25.0 °C = 298.2 K). Raises :class:`QuantityError` when the dimensions differ."""
    if q.dim != unit.dim:
        raise QuantityError(f"cannot express {describe_dim(q.dim)} in {unit.text or 'a pure number'} ({describe_dim(unit.dim)})")
    if unit.offset and q.temperature == "difference":
        raise QuantityError(f"the result is a difference of temperatures: in {unit.text} it would read as a temperature on the scale "
                            f"({float(unit.from_si(q.value)):.4g} {unit.text}); write it in K (a change of 1 {unit.text} is "
                            f"{'1 K' if unit.factor == 1 else '5/9 K'})")
    value = unit.from_si(q.value)
    if q.sig is None or not unit.offset:
        return value, q.sig
    res = resolution(q) / float(unit.factor)
    return value, sig_from_resolution(value, res)


def written(value: str | int | float, unit: str = "", sig: int | None = None, exact: bool | None = None) -> Written:
    """A value from a symbol table: a number (``29.8``, ``"6.674e-11"``, ``"2.5 × 10^3"``, a
    fraction ``"1/25"``), optionally followed by its unit (``"29.8 km/s"``) or with ``unit``.

    Exactness: ``exact: true`` makes it exact, ``sig`` gives its significant figures (the
    value is rounded to them); otherwise a fraction is exact, a whole number without a unit is
    exact (a count), and any other number is measured, its significant figures counted from
    its digits (:func:`count_sig`)."""
    if isinstance(value, bool):
        raise QuantityError(f"{value!r} is not a number")
    text = repr(value) if isinstance(value, float) else str(value)
    try:
        num, den, rest = split_number(text)
    except ValueError as exc:
        raise QuantityError(str(exc)) from None
    if rest and unit:
        raise QuantityError(f"'{text}' carries a unit and unit: '{unit}' is given too; write the unit once")
    u = parse_unit(rest or unit)
    exact_value = Fraction(int(num), int(den)) if den is not None else number_value(num)
    if den is not None and int(den) == 0:
        raise QuantityError(f"'{text}': division by zero")
    if sig is not None and not 1 <= sig <= MAX_SIG:
        raise QuantityError(f"sig: {sig} is impossible (from 1 to {MAX_SIG} significant figures)")
    if exact and sig is not None:
        raise QuantityError("give exact: true or sig, not both (an exact value has no last uncertain digit)")
    whole = den is None and re.fullmatch(r"[+\-]?\d+", num) is not None
    if exact or (sig is None and exact is None and (den is not None or (whole and u.dimensionless and not u.parts))):
        s: int | None = None
    else:
        s = sig if sig is not None else count_sig(num)
    number = written_number(num, den)
    if sig is not None:   # the value as stated: rounded to its figures
        exact_value = Fraction(round_sig(exact_value, sig))
        number = decimal_text(exact_value, sig)
    si = u.to_si(exact_value)
    if s is not None and u.offset:
        res = 10.0 ** (decade(exact_value) - s + 1) * float(u.factor)
        s = sig_from_resolution(si, res)
    return Written(Quantity(si, u.dim, s, "point" if u.offset else ""), u, number)


__all__ = [
    "FRACTION_LIMIT",
    "FUNCTIONS",
    "MAX_SIG",
    "NumberText",
    "PLAIN_MAX",
    "PLAIN_MIN",
    "Quantity",
    "QuantityError",
    "Written",
    "add",
    "call",
    "count_sig",
    "decade",
    "decimal_text",
    "div",
    "exact_root",
    "fraction_text",
    "in_unit",
    "mul",
    "neg",
    "nice_fraction",
    "number_value",
    "power",
    "resolution",
    "round_sig",
    "sig_from_resolution",
    "split_number",
    "written",
    "written_number",
]
