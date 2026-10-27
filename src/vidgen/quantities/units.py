"""Units and dimensions for worked calculations (Phase W, DESIGN §97.9). No manim.

A dimension is a tuple of seven rational exponents of the SI base quantities (length, mass,
time, electric current, temperature, amount of substance, luminous intensity). A unit is an SI
factor (an exact :class:`~fractions.Fraction` when the unit is defined exactly, a float when its
definition involves π), a dimension and, for °C / °F only, an offset. :func:`parse_unit` reads
unit strings as people write them (``m/s^2``, ``km h^-1``, ``kg·m²·s⁻²``, ``GeV/c^2``, ``J/(mol·K)``,
``µM``, ``°C``) and :func:`si_unit` writes a dimension in SI for display, naming a derived unit
when one fits (``kg·m²·s⁻²`` -> ``J``).

Exact definitions: SI 2019 (BIPM SI Brochure, 9th edition): the electronvolt from e, the
astronomical unit (IAU 2012 Resolution B2), the light year (Julian year × c), atm, bar, mmHg,
the thermochemical calorie (4.184 J), the Julian year (365.25 d). The dalton is CODATA 2022
(measured). The parsec is 648 000/π au (IAU 2015 Resolution B2).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache

from vidgen.errors import VidgenError

Number = Fraction | float
Dim = tuple[Fraction, ...]

#: The SI base units, in the order of a dimension's exponents.
BASE_UNITS = ("m", "kg", "s", "A", "K", "mol", "cd")
#: What each base dimension measures.
BASE_NAMES = ("length", "mass", "time", "electric current", "temperature", "amount of substance", "luminous intensity")
_ZERO = Fraction(0)
DIMENSIONLESS: Dim = (_ZERO,) * 7


def dim(m: float = 0, kg: float = 0, s: float = 0, A: float = 0, K: float = 0, mol: float = 0, cd: float = 0) -> Dim:  # noqa: N803
    """A dimension from base exponents: ``dim(m=1, s=-1)`` is a speed."""
    return tuple(Fraction(x) for x in (m, kg, s, A, K, mol, cd))


def dim_mul(a: Dim, b: Dim) -> Dim:
    """The dimension of a product."""
    return tuple(x + y for x, y in zip(a, b))


def dim_div(a: Dim, b: Dim) -> Dim:
    """The dimension of a quotient."""
    return tuple(x - y for x, y in zip(a, b))


def dim_pow(a: Dim, p: Fraction) -> Dim:
    """The dimension of a power."""
    return tuple(x * p for x in a)


#: SI prefixes by symbol: power of ten (``u`` and ``μ`` are written ``µ``).
PREFIXES: dict[str, int] = {
    "q": -30, "r": -27, "y": -24, "z": -21, "a": -18, "f": -15, "p": -12, "n": -9, "µ": -6, "μ": -6, "u": -6, "m": -3,
    "c": -2, "d": -1, "da": 1, "h": 2, "k": 3, "M": 6, "G": 9, "T": 12, "P": 15, "E": 18, "Z": 21, "Y": 24, "R": 27, "Q": 30,
}


@dataclass(frozen=True)
class UnitDef:
    """A named unit: one of it is ``factor`` SI units of ``dim``; ``offset`` (°C, °F): the SI
    value is ``(value + offset) × factor``. ``prefixable``: SI prefixes may precede it."""

    symbol: str
    factor: Number
    dim: Dim
    name: str
    prefixable: bool = False
    offset: Fraction = _ZERO
    tex: str = ""
    #: How the symbol is written on screen (``u`` -> ``µ`` is a prefix matter; ``ohm`` -> ``Ω``).
    shown: str = ""

    def display(self) -> str:
        return self.shown or self.symbol


def _f(text: str) -> Fraction:
    return Fraction(text)


_ENERGY = dim(kg=1, m=2, s=-2)
_DEFS: list[UnitDef] = [
    # SI base units (the kilogram through the gram, so prefixes work: kg, mg, µg)
    UnitDef("m", 1, dim(m=1), "metre", True),
    UnitDef("g", _f("0.001"), dim(kg=1), "gram", True),
    UnitDef("s", 1, dim(s=1), "second", True),
    UnitDef("A", 1, dim(A=1), "ampere", True),
    UnitDef("K", 1, dim(K=1), "kelvin", True),
    UnitDef("mol", 1, dim(mol=1), "mole", True),
    UnitDef("cd", 1, dim(cd=1), "candela", True),
    # SI derived units
    UnitDef("Hz", 1, dim(s=-1), "hertz", True),
    UnitDef("Bq", 1, dim(s=-1), "becquerel", True),
    UnitDef("N", 1, dim(kg=1, m=1, s=-2), "newton", True),
    UnitDef("Pa", 1, dim(kg=1, m=-1, s=-2), "pascal", True),
    UnitDef("J", 1, _ENERGY, "joule", True),
    UnitDef("W", 1, dim(kg=1, m=2, s=-3), "watt", True),
    UnitDef("C", 1, dim(A=1, s=1), "coulomb", True),
    UnitDef("V", 1, dim(kg=1, m=2, s=-3, A=-1), "volt", True),
    UnitDef("Ω", 1, dim(kg=1, m=2, s=-3, A=-2), "ohm", True, tex=r"\Omega"),
    UnitDef("ohm", 1, dim(kg=1, m=2, s=-3, A=-2), "ohm", True, tex=r"\Omega", shown="Ω"),
    UnitDef("F", 1, dim(kg=-1, m=-2, s=4, A=2), "farad", True),
    UnitDef("S", 1, dim(kg=-1, m=-2, s=3, A=2), "siemens", True),
    UnitDef("T", 1, dim(kg=1, s=-2, A=-1), "tesla", True),
    UnitDef("Wb", 1, dim(kg=1, m=2, s=-2, A=-1), "weber", True),
    UnitDef("H", 1, dim(kg=1, m=2, s=-2, A=-2), "henry", True),
    UnitDef("Gy", 1, dim(m=2, s=-2), "gray", True),
    UnitDef("Sv", 1, dim(m=2, s=-2), "sievert", True),
    UnitDef("rad", 1, DIMENSIONLESS, "radian", True),
    UnitDef("sr", 1, DIMENSIONLESS, "steradian"),
    # time
    UnitDef("min", 60, dim(s=1), "minute"),
    UnitDef("h", 3600, dim(s=1), "hour"),
    UnitDef("d", 86400, dim(s=1), "day"),
    UnitDef("yr", _f("31557600"), dim(s=1), "Julian year", True),
    # volume, concentration, mass
    UnitDef("L", _f("0.001"), dim(m=3), "litre", True),
    UnitDef("l", _f("0.001"), dim(m=3), "litre", True, shown="L"),
    UnitDef("M", 1000, dim(mol=1, m=-3), "molar (mol/L)", True),
    UnitDef("t", 1000, dim(kg=1), "tonne"),
    UnitDef("Da", _f("1.66053906892e-27"), dim(kg=1), "dalton", True),
    UnitDef("u", _f("1.66053906892e-27"), dim(kg=1), "atomic mass unit"),
    # energy
    UnitDef("eV", _f("1.602176634e-19"), _ENERGY, "electronvolt", True),
    UnitDef("cal", _f("4.184"), _ENERGY, "calorie", True),
    UnitDef("Wh", 3600, _ENERGY, "watt-hour", True),
    # length
    UnitDef("Å", _f("1e-10"), dim(m=1), "ångström", tex=r"\text{\AA}"),
    UnitDef("au", 149597870700, dim(m=1), "astronomical unit"),
    UnitDef("AU", 149597870700, dim(m=1), "astronomical unit"),
    UnitDef("ly", 9460730472580800, dim(m=1), "light year"),
    UnitDef("pc", 149597870700 * 648000 / math.pi, dim(m=1), "parsec", True),
    # pressure
    UnitDef("atm", 101325, dim(kg=1, m=-1, s=-2), "standard atmosphere"),
    UnitDef("bar", 100000, dim(kg=1, m=-1, s=-2), "bar", True),
    UnitDef("mmHg", _f("133.322387415"), dim(kg=1, m=-1, s=-2), "millimetre of mercury"),
    UnitDef("Torr", Fraction(101325, 760), dim(kg=1, m=-1, s=-2), "torr"),
    # angles and ratios
    UnitDef("deg", math.pi / 180, DIMENSIONLESS, "degree", tex=r"^{\circ}", shown="°"),
    UnitDef("°", math.pi / 180, DIMENSIONLESS, "degree", tex=r"^{\circ}"),
    UnitDef("%", Fraction(1, 100), DIMENSIONLESS, "percent", tex=r"\%"),
    UnitDef("ppm", Fraction(1, 1000000), DIMENSIONLESS, "part per million"),
    # the speed of light as a unit (GeV/c², MeV/c)
    UnitDef("c", 299792458, dim(m=1, s=-1), "speed of light", tex="c"),
    # temperatures with an offset (a value in them must stand alone)
    UnitDef("°C", 1, dim(K=1), "degree Celsius", offset=_f("273.15"), tex=r"{}^{\circ}\mathrm{C}"),
    UnitDef("degC", 1, dim(K=1), "degree Celsius", offset=_f("273.15"), tex=r"{}^{\circ}\mathrm{C}", shown="°C"),
    UnitDef("℃", 1, dim(K=1), "degree Celsius", offset=_f("273.15"), tex=r"{}^{\circ}\mathrm{C}", shown="°C"),
    UnitDef("°F", Fraction(5, 9), dim(K=1), "degree Fahrenheit", offset=_f("459.67"), tex=r"{}^{\circ}\mathrm{F}"),
    UnitDef("degF", Fraction(5, 9), dim(K=1), "degree Fahrenheit", offset=_f("459.67"), tex=r"{}^{\circ}\mathrm{F}", shown="°F"),
]
#: Every unit by symbol.
UNITS: dict[str, UnitDef] = {u.symbol: u for u in _DEFS}


@dataclass(frozen=True)
class UnitPart:
    """One factor of a written unit: a prefix (power of ten, as written), a unit, a power."""

    prefix: str
    unit: UnitDef
    power: Fraction

    @property
    def factor(self) -> Number:
        scale = Fraction(10) ** PREFIXES[self.prefix] if self.prefix else Fraction(1)
        base = self.unit.factor
        f = scale * base if isinstance(base, Fraction) or isinstance(base, int) else float(scale) * base
        return _power(f, self.power)

    def text(self, power: Fraction | None = None) -> str:
        p = self.power if power is None else power
        prefix = "µ" if self.prefix in ("u", "μ") else self.prefix
        return prefix + self.unit.display() + (superscript_fraction(p) if p != 1 else "")

    def tex(self, power: Fraction | None = None) -> str:
        p = self.power if power is None else power
        prefix = r"\mu" if self.prefix in ("u", "μ", "µ") else (rf"\mathrm{{{self.prefix}}}" if self.prefix else "")
        body = self.unit.tex or rf"\mathrm{{{self.unit.display()}}}"
        if self.prefix and body.startswith(r"\mathrm{") and prefix.startswith(r"\mathrm{"):
            body = r"\mathrm{" + self.prefix + body[len(r"\mathrm{"):]
            prefix = ""
        out = prefix + body
        if p != 1:
            out = "{" + out + "}^{" + _tex_power(p) + "}"
        return out


def _power(f: Number, p: Fraction) -> Number:
    if p.denominator == 1:
        return f ** int(p) if isinstance(f, Fraction) else float(f) ** int(p)
    return float(f) ** float(p)


def _tex_power(p: Fraction) -> str:
    return str(p.numerator) if p.denominator == 1 else f"{p.numerator}/{p.denominator}"


_SUPER = str.maketrans("0123456789-/", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻ᐟ")


def superscript_fraction(p: Fraction) -> str:
    """An exponent in superscript: ``2`` -> ``²``, ``-1`` -> ``⁻¹``, ``1/2`` -> ``¹ᐟ²``."""
    text = str(p.numerator) if p.denominator == 1 else f"{p.numerator}/{p.denominator}"
    return text.translate(_SUPER)


@dataclass(frozen=True)
class Unit:
    """A unit as written: its parts (``km``, ``h⁻¹``), with the SI ``factor``, ``dim`` and
    ``offset`` of the whole. ``text`` / ``tex`` write it for the screen."""

    parts: tuple[UnitPart, ...]
    factor: Number
    dim: Dim
    offset: Fraction = _ZERO
    source: str = field(default="", compare=False)

    @property
    def dimensionless(self) -> bool:
        return self.dim == DIMENSIONLESS

    @property
    def text(self) -> str:
        """The unit in Unicode: ``km/s``, ``m³·kg⁻¹·s⁻²``, ``GeV/c²``, ``°C``."""
        return _write(self.parts, lambda part, p: part.text(p), "·", "/")

    @property
    def tex(self) -> str:
        """The unit in math-mode TeX: ``\\mathrm{km}/\\mathrm{s}``."""
        return _write(self.parts, lambda part, p: part.tex(p), r"\,", "/")

    def to_si(self, value: Number) -> Number:
        """``value`` in this unit as an SI value."""
        if self.offset:
            return _mul(_add(value, self.offset), self.factor)
        return _mul(value, self.factor)

    def from_si(self, value: Number) -> Number:
        """An SI value in this unit."""
        out = _div(value, self.factor)
        return _add(out, -self.offset) if self.offset else out


def _mul(a: Number, b: Number) -> Number:
    if isinstance(a, (Fraction, int)) and isinstance(b, (Fraction, int)):
        return Fraction(a) * Fraction(b)
    return float(a) * float(b)


def _div(a: Number, b: Number) -> Number:
    if isinstance(a, (Fraction, int)) and isinstance(b, (Fraction, int)):
        return Fraction(a) / Fraction(b)
    return float(a) / float(b)


def _add(a: Number, b: Number) -> Number:
    if isinstance(a, (Fraction, int)) and isinstance(b, (Fraction, int)):
        return Fraction(a) + Fraction(b)
    return float(a) + float(b)


def _write(parts: tuple[UnitPart, ...], one, sep: str, slash: str) -> str:
    """Parts written with ``sep``; a single part with a negative power after positive ones
    goes after a slash (``km/s``, ``m/s²``), else negative powers stay (``mol⁻¹·K⁻¹``)."""
    up = [p for p in parts if p.power > 0]
    down = [p for p in parts if p.power < 0]
    if up and len(down) == 1:
        return sep.join(one(p, None) for p in up) + slash + one(down[0], -down[0].power)
    return sep.join(one(p, None) for p in parts)


#: An empty unit (a pure number).
ONE = Unit((), Fraction(1), DIMENSIONLESS, source="")

_UNIT_TOKEN = re.compile(
    r"(?:(?P<name>°[A-Za-z]?|[A-Za-zµμΩ℃Å%]+)(?P<sup>[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)?|(?P<num>\d+(?:\.\d+)?)|(?P<op>\*\*|[*·⋅./^()]|-?\d+|\s+))"
)
_FROM_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def unit_symbols() -> list[str]:
    """Every unit symbol :func:`parse_unit` knows (without prefixes)."""
    return list(UNITS)


def _lookup(name: str, source: str) -> tuple[str, UnitDef]:
    """``(prefix, unit)`` for a written symbol: the unit itself first (``Pa``, ``cd``, ``min``),
    then a prefix and a unit that takes prefixes (``km``, ``MeV``, ``µM``)."""
    if name in UNITS:
        return "", UNITS[name]
    for prefix in sorted(PREFIXES, key=len, reverse=True):
        rest = name[len(prefix):]
        if name.startswith(prefix) and rest in UNITS:
            unit = UNITS[rest]
            if not unit.prefixable:
                raise VidgenError(f"unit '{source}': '{rest}' ({unit.name}) does not take a prefix ('{prefix}{rest}')")
            return prefix, unit
    import difflib

    close = difflib.get_close_matches(name, list(UNITS), n=2, cutoff=0.5)
    hint = f" (did you mean {' or '.join(repr(c) for c in close)}?)" if close else ""
    raise VidgenError(f"unit '{source}': unknown unit '{name}'{hint}; units are SI symbols with prefixes (m, kg, s, km/h, MeV, µM), "
                      "and min, h, d, yr, L, M, eV, au, ly, pc, atm, bar, mmHg, cal, Wh, Da, u, deg, %, °C, °F, c")


class _UnitParser:
    def __init__(self, text: str) -> None:
        self.source = text
        self.tokens: list[tuple[str, str]] = []
        pos = 0
        s = text.strip()
        while pos < len(s):
            m = _UNIT_TOKEN.match(s, pos)
            if m is None or m.end() == pos:
                raise VidgenError(f"unit '{text}': unexpected {s[pos]!r} at character {pos + 1}")
            pos = m.end()
            if m.group("name"):
                self.tokens.append(("name", m.group("name")))
                if m.group("sup"):
                    self.tokens.append(("sup", m.group("sup").translate(_FROM_SUPER)))
            elif m.group("num"):
                self.tokens.append(("num", m.group("num")))
            else:
                op = m.group("op")
                if op.isspace():
                    self.tokens.append(("op", " "))
                elif op.lstrip("-").isdigit():
                    self.tokens.append(("num", op))
                else:
                    self.tokens.append(("op", {"·": "*", "⋅": "*", ".": "*", "**": "^"}.get(op, op)))
        # spaces next to an operator or bracket mean nothing; between two factors they multiply
        cleaned: list[tuple[str, str]] = []
        for k, t in enumerate(self.tokens):
            if t == ("op", " "):
                prev = cleaned[-1] if cleaned else None
                nxt = next((u for u in self.tokens[k + 1:] if u != ("op", " ")), None)
                if prev is None or nxt is None or prev[1] in ("*", "/", "^", "(") or nxt[1] in ("*", "/", "^", ")"):
                    continue
                t = ("op", "*")
            cleaned.append(t)
        self.tokens = cleaned
        self.i = 0

    def peek(self) -> tuple[str, str]:
        return self.tokens[self.i] if self.i < len(self.tokens) else ("end", "")

    def take(self) -> tuple[str, str]:
        t = self.peek()
        self.i += 1
        return t

    def fail(self, message: str) -> VidgenError:
        return VidgenError(f"unit '{self.source}': {message}")

    def parse(self) -> list[UnitPart]:
        parts = self.product()
        if self.peek()[0] != "end":
            raise self.fail(f"unexpected {self.peek()[1]!r}")
        return parts

    def product(self) -> list[UnitPart]:
        parts = self.factor()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            nxt = self.factor()
            parts += nxt if op == "*" else [UnitPart(p.prefix, p.unit, -p.power) for p in nxt]
        return parts

    def exponent(self) -> Fraction:
        kind, text = self.take()
        if kind == "op" and text == "(":
            num = self.take()
            if num[0] != "num":
                raise self.fail("expected a number in the exponent")
            value = Fraction(num[1])
            if self.peek() == ("op", "/"):
                self.take()
                den = self.take()
                if den[0] != "num":
                    raise self.fail("expected a number after '/' in the exponent")
                value /= Fraction(den[1])
            if self.take() != ("op", ")"):
                raise self.fail("expected ')' after the exponent")
            return value
        if kind == "num":
            return Fraction(text)
        raise self.fail(f"expected an exponent after '^', found {text or 'the end'!r}")

    def factor(self) -> list[UnitPart]:
        kind, text = self.take()
        if kind == "op" and text == "(":
            parts = self.product()
            if self.take() != ("op", ")"):
                raise self.fail("a '(' is not closed")
        elif kind == "name":
            prefix, unit = _lookup(text, self.source)
            parts = [UnitPart(prefix, unit, Fraction(1))]
        elif kind == "num" and Fraction(text) == 1:
            parts = []
        else:
            raise self.fail(f"expected a unit, found {text or 'the end'!r}")
        power = Fraction(1)
        if self.peek()[0] == "sup":
            power = Fraction(self.take()[1])
        elif self.peek() == ("op", "^"):
            self.take()
            power = self.exponent()
        if power == 0:
            raise self.fail("a power of 0")
        return [UnitPart(p.prefix, p.unit, p.power * power) for p in parts]


@lru_cache(maxsize=1024)
def parse_unit(text: str) -> Unit:
    """The unit written in ``text``: symbols with SI prefixes, products (``*``, ``·``, ``.``, a
    space), quotients (``/`` divides by the factor after it: ``m/s/s`` = ``m·s⁻²``; group with
    brackets: ``J/(mol·K)``), powers (``^2``, ``^-1``, ``**2``, ``²``, ``⁻¹``, ``^(1/2)``). An
    empty string is a pure number. °C and °F must stand alone (an offset scale cannot be
    multiplied). Raises :class:`VidgenError` with did-you-mean for an unknown symbol."""
    s = text.strip()
    if not s or s == "1":
        return ONE
    parts = _UnitParser(s).parse()
    merged: dict[tuple[str, str], Fraction] = {}
    for p in parts:
        key = (p.prefix, p.unit.symbol)
        merged[key] = merged.get(key, Fraction(0)) + p.power
    clean = tuple(UnitPart(pre, UNITS[sym], pw) for (pre, sym), pw in merged.items() if pw != 0)
    offset_parts = [p for p in clean if p.unit.offset]
    if offset_parts:
        p = offset_parts[0]
        if len(parts) != 1 or p.power != 1 or p.prefix:
            raise VidgenError(f"unit '{s}': {p.unit.display()} is a scale with an offset and must stand alone; a change of "
                              f"1 {p.unit.display()} is {'1 K' if p.unit.display() == '°C' else '5/9 K'}, so write the unit with K "
                              f"(e.g. {s.replace(p.unit.symbol, 'K')})")
        return Unit(clean, p.unit.factor, p.unit.dim, p.unit.offset, s)
    factor: Number = Fraction(1)
    d = DIMENSIONLESS
    for p in clean:
        factor = _mul(factor, p.factor)
        d = dim_mul(d, dim_pow(p.unit.dim, p.power))
    return Unit(clean, factor, d, _ZERO, s)


# ----- describing and simplifying dimensions ----------------------------------------------------

#: Derived units named when a result's dimension matches exactly (``kg·m²·s⁻²`` -> ``J``).
_NAMED = ["N", "J", "W", "Pa", "C", "V", "Ω", "F", "T", "Wb", "H"]
#: Names of common dimensions (for explanations).
_DIM_NAMES: dict[Dim, str] = {
    DIMENSIONLESS: "a pure number",
    dim(m=1): "length", dim(kg=1): "mass", dim(s=1): "time", dim(A=1): "electric current", dim(K=1): "temperature",
    dim(mol=1): "amount of substance", dim(cd=1): "luminous intensity",
    dim(m=2): "area", dim(m=3): "volume", dim(m=1, s=-1): "speed", dim(m=1, s=-2): "acceleration",
    dim(s=-1): "frequency or rate", dim(kg=1, m=1, s=-2): "force", dim(kg=1, m=2, s=-2): "energy", dim(kg=1, m=2, s=-3): "power",
    dim(kg=1, m=-1, s=-2): "pressure", dim(A=1, s=1): "electric charge", dim(kg=1, m=2, s=-3, A=-1): "voltage",
    dim(kg=1, m=-3): "density", dim(mol=1, m=-3): "concentration", dim(kg=1, m=1, s=-1): "momentum",
    dim(kg=1, m=2, s=-1): "action (energy × time)", dim(m=3, s=-2): "gravitational parameter (G·M)",
    dim(m=2, s=-2): "speed squared (energy per mass)", dim(kg=1, mol=-1): "molar mass",
    dim(kg=1, m=2, s=-3, A=-2): "resistance", dim(kg=1, s=-2, A=-1): "magnetic flux density",
}


def _base_parts(d: Dim) -> tuple[UnitPart, ...]:
    """``d`` as SI base unit parts: positive powers first, then kg, m, s, A, K, mol, cd."""
    parts = [UnitPart("k" if sym == "kg" else "", UNITS["g" if sym == "kg" else sym], p) for sym, p in zip(BASE_UNITS, d) if p != 0]
    order = {"g": 0, "m": 1, "s": 2, "A": 3, "K": 4, "mol": 5, "cd": 6}
    return tuple(sorted(parts, key=lambda q: (q.power < 0, order[q.unit.symbol])))


def base_unit_text(d: Dim, tex: bool = False) -> str:
    """``d`` in SI base units: ``kg·m²·s⁻²`` (or TeX); ``""`` for a pure number."""
    parts = _base_parts(d)
    if not tex:
        return "·".join(q.text() for q in parts)
    return r"\,".join(q.tex() for q in parts)


def describe_dim(d: Dim) -> str:
    """A dimension in words with its SI units: ``energy (kg·m²·s⁻², J)``, ``length (m)``,
    ``m³·kg⁻¹·s⁻²`` when it has no common name, ``a pure number``."""
    base = base_unit_text(d)
    if d == DIMENSIONLESS:
        return "a pure number"
    name = _DIM_NAMES.get(d)
    named = next((u for u in _NAMED if UNITS[u].dim == d), None)
    units = base + (f", {named}" if named and named != base else "")
    return f"{name} ({units})" if name else units


@lru_cache(maxsize=256)
def si_unit(d: Dim) -> Unit:
    """The SI unit to show a value of dimension ``d`` in: a named derived unit when one fits
    exactly (``J``, ``N``, ``Pa``, ``W``...), ``J·s`` for an action, else the base units
    (``m·s⁻¹``, ``m³·kg⁻¹·s⁻²``); ``s⁻¹`` stays (it could be Hz or Bq)."""
    named = next((u for u in _NAMED if UNITS[u].dim == d), None)
    if named:
        return parse_unit(named)
    if d == dim(kg=1, m=2, s=-1):
        return parse_unit("J*s")
    return Unit(_base_parts(d), Fraction(1), d, _ZERO, base_unit_text(d))


def same_dimension_hint(d: Dim) -> str:
    """Examples of units of dimension ``d`` (for an explanation): ``m, km, au``."""
    found = [u.symbol for u in _DEFS if u.dim == d and not u.shown and u.symbol not in ("°C", "°F", "℃")]
    return ", ".join(found[:5])


__all__ = [
    "BASE_NAMES",
    "BASE_UNITS",
    "DIMENSIONLESS",
    "Dim",
    "Number",
    "ONE",
    "PREFIXES",
    "UNITS",
    "Unit",
    "UnitDef",
    "UnitPart",
    "base_unit_text",
    "describe_dim",
    "dim",
    "dim_div",
    "dim_mul",
    "dim_pow",
    "parse_unit",
    "same_dimension_hint",
    "si_unit",
    "superscript_fraction",
    "unit_symbols",
]
