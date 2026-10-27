"""Worked calculations: a symbol table and a chain of formulas, evaluated with units and
written step by step (DESIGN §97.9). No manim; the ``calculation`` scene draws what
:func:`work` returns, and lint compares narrated numbers with it.

Each calculation is shown as: the formula (``v = \\sqrt{G M_\\odot / r}``), the values
substituted with their units, an optional intermediate (a function's argument evaluated), the
result with its significant figures (or an exact fraction and its decimal), and conversions
of the result into other units. A later calculation may use an earlier result by its name; a
symbol may take its value from a named constant (:mod:`.constants`) or from a result of another
scene (``imports``).
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from vidgen.errors import VidgenError

from . import expr as ex
from . import quantity as qy
from .constants import ALIASES, CONSTANTS, constant
from .quantity import NumberText, Quantity, QuantityError
from .units import DIMENSIONLESS, Unit, describe_dim, parse_unit, si_unit

#: Result formats.
FORMATS = ("auto", "decimal", "sci", "fraction", "percent")
#: Significant figures of an exact value that is shown rounded (ln 2, a long fraction).
EXACT_DIGITS = 4
#: Significant figures a constant is shown with (its full value is used).
CONSTANT_DIGITS = 4

_GREEK = {n: "\\" + n for n in ("alpha beta gamma delta zeta eta theta iota kappa lambda mu nu xi pi rho sigma tau upsilon chi psi omega "
                                "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega").split()}
_GREEK |= {"epsilon": r"\varepsilon", "phi": r"\varphi", "varepsilon": r"\varepsilon", "varphi": r"\varphi"}
_SUBSCRIPTS = {"sun": r"\odot", "earth": r"\oplus", "half": "1/2"}


def name_tex(name: str) -> str:
    """The TeX of a symbol name: ``M_sun`` -> ``M_{\\odot}``, ``k_B`` -> ``k_{\\mathrm{B}}``,
    ``lambda`` -> ``\\lambda``, ``v_esc`` -> ``v_{\\mathrm{esc}}``, ``t_half`` -> ``t_{1/2}``."""
    base, _, sub = name.partition("_")
    m = re.fullmatch(r"([A-Za-z]+?)(\d+)", base)
    if m and not sub and (m.group(1) in _GREEK or len(m.group(1)) == 1):   # p1 -> p_1, lambda2 -> \lambda_2
        base, sub = m.group(1), m.group(2)

    def part(text: str, subscript: bool) -> str:
        if text in _GREEK:
            return _GREEK[text]
        if subscript and text in _SUBSCRIPTS:
            return _SUBSCRIPTS[text]
        if text.isdigit() or len(text) == 1 and not subscript:
            return text
        return rf"\mathrm{{{text}}}" if subscript else rf"\mathit{{{text}}}"

    out = part(base, False) if base else ""
    if sub:
        out += "_{" + ",".join(part(s, True) for s in sub.split("_") if s) + "}"
    return out


@dataclass
class SymbolInput:
    """A row of the symbol table as written: a ``name`` used in formulas, a value (number,
    fraction or number with unit) or a ``constant`` key or an imported result, and how to
    show it."""

    name: str
    value: str | int | float | None = None
    unit: str = ""
    constant: str | None = None
    sig: int | None = None
    exact: bool | None = None
    tex: str = ""
    meaning: str = ""
    source: str = ""
    digits: int | None = None
    #: A result of another scene: ``(quantity, display unit, number as shown, its TeX symbol)``.
    imported: tuple[Quantity, Unit, NumberText, str] | None = None


@dataclass
class CalcInput:
    """A calculation as written: the result's ``name``, the expression, how to show it."""

    name: str
    expr: str
    unit: str = ""
    convert: Sequence[str] = ()
    sig: int | None = None
    format: str = "auto"
    tex: str = ""
    meaning: str = ""
    symbol: str = ""
    intermediate: bool | None = None
    substitute: bool = True


@dataclass
class SymbolValue:
    """A known value: a symbol of the table or a result, with how it is shown."""

    name: str
    tex: str
    meaning: str
    source: str
    quantity: Quantity
    unit: Unit
    number: NumberText
    #: The value written in SI base / derived units (for a substitution without units).
    si_number: NumberText | None = None
    si_unit: Unit | None = None

    def value_tex(self, units: bool = True) -> tuple[str, float]:
        """The value as TeX (with its unit, or in SI without one) and its precedence."""
        number = self.number if units or self.si_number is None else self.si_number
        unit = self.unit if units else None
        tex = number.tex
        if unit is not None and unit.parts:
            if unit.tex.startswith("^{"):   # 30°
                tex += unit.tex
            else:
                tex += r"\," + unit.tex
            level = ex.PROD
        else:
            level = ex.PROD if number.sci else (ex.FRAC if number.fraction else ex.ATOM)
        if tex.startswith("-"):
            level = ex.NEG
        return tex, level

    def value_text(self) -> str:
        """The value in Unicode with its unit: ``29.8 km/s``."""
        unit = self.unit.text
        if not unit:
            return self.number.plain
        return self.number.plain + ("" if unit == "°" else " ") + unit


@dataclass
class Step:
    """A line of a worked calculation: ``kind`` (``formula``, ``substitute``,
    ``intermediate``, ``result``, ``convert``), its right side in TeX after ``relation``
    (``=`` or ``\\approx``); ``alt``: the same without units (a substitution in SI numbers)."""

    kind: str
    tex: str
    relation: str = "="
    alt: str = ""
    plain: str = ""
    #: ``tex`` and ``alt`` with their outermost products on two lines (for a narrow frame).
    stacked: str = ""
    alt_stacked: str = ""
    #: ``tex`` with one factor of its outermost product per line (three factors or more).
    deep: str = ""

    def variants(self) -> list[str]:
        """The ways to write this line, from the most explicit: with units, with units on two
        lines, with units one factor per line, SI numbers, SI numbers on two lines (repeats
        left out)."""
        return list(dict.fromkeys(t for t in (self.tex, self.stacked, self.deep, self.alt, self.alt_stacked) if t))

    def unit_variants(self) -> list[str]:
        """The ways of :meth:`variants` that keep the units."""
        return list(dict.fromkeys(t for t in (self.tex, self.stacked, self.deep) if t))


@dataclass
class CalcResult:
    """A worked calculation: its result (a :class:`SymbolValue`), the steps, the names it
    used, and warnings for lint (significant figures claimed beyond the inputs)."""

    index: int
    value: SymbolValue
    steps: list[Step]
    used: list[str]
    conversions: list[SymbolValue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.value.name


@dataclass
class Worked:
    """The symbols and the results of a scene's calculations, in order."""

    symbols: dict[str, SymbolValue]
    results: list[CalcResult]

    def value(self, name: str) -> SymbolValue:
        if name in self.symbols:
            return self.symbols[name]
        for r in self.results:
            if r.name == name:
                return r.value
        raise KeyError(name)


Wrap = Callable[[str, str], str]


def _no_wrap(key: str, tex: str) -> str:
    return tex


def _exact_number(q: Quantity, unit: Unit, sig: int | None, fmt: str) -> NumberText:
    """How a value is written: a fraction or whole number when exact and short, else decimals
    with its significant figures (``fmt``: auto, decimal, sci, fraction, percent)."""
    value, s = qy.in_unit(q, unit)
    if fmt == "fraction":
        if not (q.rational and isinstance(value, Fraction)):
            raise QuantityError("format: fraction needs an exact result (every input exact: counts, fractions, exact: true)")
        return qy.fraction_text(value)
    shown = sig if sig is not None else s
    if shown is None:
        if isinstance(value, Fraction) and value.denominator == 1 and abs(value) < 10**15 and fmt in ("auto", "decimal"):
            return qy.fraction_text(value)
        if fmt == "auto" and isinstance(value, Fraction) and qy.nice_fraction(value):
            return qy.fraction_text(value)
        shown = EXACT_DIGITS
    mode = "sci" if fmt == "sci" else ("plain" if fmt == "decimal" else "auto")
    return qy.decimal_text(value, shown, mode)


def _decimal_of(value: Fraction, sig: int | None) -> NumberText:
    """The decimal written after an exact fraction: exactly when it terminates within six
    significant figures (1/50 = 0.02), else to ``sig`` (default 3) figures (1/150 ≈ 0.00667)."""
    d = value.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    if d == 1 and sig is None:
        digits = len(str(abs(value.numerator * 10**30 // value.denominator)).rstrip("0"))
        if digits <= 6:
            return qy.decimal_text(value, max(1, digits), "plain" if abs(value) < qy.PLAIN_MAX else "auto")
    return qy.decimal_text(value, sig or 3)


class _Context:
    def __init__(self, where: str) -> None:
        self.where = where

    def fail(self, message: str) -> VidgenError:
        return VidgenError(f"{self.where}: {message}")


def _symbol(k: int, s: SymbolInput) -> SymbolValue:
    where = f"symbols[{k}] ({s.name})"
    sources = sum(x is not None for x in (s.value, s.constant, s.imported))
    if sources != 1:
        raise VidgenError(f"{where}: give exactly one of value, constant or from_scene" if sources else f"{where}: give its value (value: 29.8 km/s), "
                          f"a constant (constant: G) or a result of another scene (from_scene: scene_id)")
    if s.digits is not None and not 1 <= s.digits <= qy.MAX_SIG:
        raise VidgenError(f"{where}: digits {s.digits} is impossible (1 to {qy.MAX_SIG})")
    try:
        if s.imported is not None:
            q, unit, number, tex = s.imported
            return _with_si(SymbolValue(s.name, s.tex or tex, s.meaning, s.source, q, unit, number))
        if s.constant is not None:
            c = constant(s.constant)
            unit = parse_unit(s.unit) if s.unit else parse_unit(c.unit)
            exact = c.exact
            base = qy.written(c.value, c.unit, exact=True if exact else None)
            q = base.quantity if exact else Quantity(base.quantity.value, base.quantity.dim, qy.count_sig(c.value))
            if s.sig is not None:
                if not 1 <= s.sig <= qy.MAX_SIG:
                    raise QuantityError(f"sig: {s.sig} is impossible (from 1 to {qy.MAX_SIG} significant figures)")
                q = Quantity(Fraction(qy.round_sig(q.value, s.sig)) if isinstance(q.value, Fraction) else float(qy.round_sig(q.value, s.sig)), q.dim, s.sig)
            if q.dim != unit.dim:
                raise QuantityError(f"unit '{s.unit}' is {describe_dim(unit.dim)}, but {c.key} is {describe_dim(q.dim)}")
            value, sig = qy.in_unit(q, unit)
            digits = s.digits or (min(sig, CONSTANT_DIGITS) if sig is not None else CONSTANT_DIGITS)
            if isinstance(value, Fraction) and value.denominator == 1 and len(str(abs(value.numerator)).rstrip("0")) <= digits:
                number = qy.fraction_text(value)
            else:
                number = qy.decimal_text(value, digits)
            # the constant's own symbol when the name is the constant's (G, M_sun), else the name's (r for AU)
            own = s.name == c.key or ALIASES.get(s.name) == c.key
            return _with_si(SymbolValue(s.name, s.tex or (c.tex if own else name_tex(s.name)), s.meaning or c.meaning, s.source or c.source, q, unit, number))
        w = qy.written(s.value, s.unit, s.sig, s.exact)
        number = w.number if s.digits is None else qy.decimal_text(qy.in_unit(w.quantity, w.unit)[0], s.digits)
        return _with_si(SymbolValue(s.name, s.tex or name_tex(s.name), s.meaning, s.source, w.quantity, w.unit, number))
    except VidgenError as error:
        raise VidgenError(f"{where}: {error}") from None


def _with_si(v: SymbolValue) -> SymbolValue:
    """``v`` with its value written in SI (for substitutions without units)."""
    unit = si_unit(v.quantity.dim)
    if unit.text == v.unit.text and not v.unit.offset:
        v.si_number, v.si_unit = v.number, None
        return v
    v.si_number = _exact_number(v.quantity, unit, None, "auto")
    v.si_unit = None
    return v


def _unknown(ctx: _Context, name: str, known: Sequence[str], later: Mapping[str, int]) -> VidgenError:
    if name in later:
        return ctx.fail(f"'{name}' is computed by calculations[{later[name]}], after this one; put that calculation first")
    if name in CONSTANTS or name in ("hbar", "k_B", "N_A"):
        return ctx.fail(f"unknown symbol '{name}': it is a constant; add it to the symbols: {{name: {name}, constant: {name}}}")
    options = list(known) + ["pi", "e", "tau"]
    close = difflib.get_close_matches(name, options, n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    return ctx.fail(f"unknown symbol '{name}'{hint}; the symbols are {', '.join(known) or 'none'} (add it to symbols:, or compute it in an earlier calculation)")


def check_name(name: str, where: str) -> None:
    """A symbol or result name must be an identifier other than a function name."""
    if not re.fullmatch(r"[A-Za-z_]\w*", name):
        raise VidgenError(f"{where}: '{name}' is not a name (letters, digits and _, starting with a letter: v, M_sun, t_half)")
    if name in qy.FUNCTIONS:
        raise VidgenError(f"{where}: '{name}' is a function name; choose another")


def work(symbols: Sequence[SymbolInput], calcs: Sequence[CalcInput], wrap: Wrap | None = None, *, lenient: bool = False) -> Worked:
    """Evaluate ``calcs`` in order with the ``symbols``; each result becomes a name later
    calculations may use. ``wrap(key, tex)`` wraps each symbol's TeX (the scene marks parts to
    highlight; ``key`` is the symbol's name). ``lenient``: names of symbols without a value yet
    (imports not resolved) skip the calculations that need them instead of failing. Raises
    :class:`VidgenError` naming the symbol or calculation, with did-you-mean."""
    wrap = wrap or _no_wrap
    known: dict[str, SymbolValue] = {}
    pending: set[str] = set()
    names_seen: dict[str, str] = {}
    for k, s in enumerate(symbols, start=1):
        check_name(s.name, f"symbols[{k}]")
        if s.name in names_seen:
            raise VidgenError(f"symbols[{k}]: '{s.name}' is already {names_seen[s.name]}")
        names_seen[s.name] = f"symbols[{k}]"
        if lenient and s.value is None and s.constant is None and s.imported is None:
            pending.add(s.name)
            continue
        known[s.name] = _symbol(k, s)
    later = {}
    for k, c in enumerate(calcs, start=1):
        check_name(c.name, f"calculations[{k}]")
        if c.name in names_seen:
            raise VidgenError(f"calculations[{k}]: the result name '{c.name}' is already {names_seen[c.name]}")
        names_seen[c.name] = f"calculations[{k}]"
        later[c.name] = k
    worked = Worked({n: v for n, v in known.items()}, [])
    for k, c in enumerate(calcs, start=1):
        later.pop(c.name, None)
        ctx = _Context(f"calculations[{k}] ({c.name})")
        try:
            tree = ex.parse(c.expr)
        except VidgenError as error:
            raise ctx.fail(str(error)) from None
        used = tree.names()
        if any(n in pending for n in used):
            pending.add(c.name)
            continue
        result = _calculate(k, c, tree, known, later, ctx, wrap)
        worked.results.append(result)
        known[c.name] = result.value
    return worked


def _calculate(k: int, c: CalcInput, tree: ex.Node, known: dict[str, SymbolValue], later: Mapping[str, int], ctx: _Context, wrap: Wrap) -> CalcResult:
    if c.format not in FORMATS:
        raise ctx.fail(f"format '{c.format}' is not one of {', '.join(FORMATS)}")
    if c.sig is not None and not 1 <= c.sig <= qy.MAX_SIG:
        raise ctx.fail(f"sig: {c.sig} is impossible (from 1 to {qy.MAX_SIG} significant figures)")
    env = {n: v.quantity for n, v in known.items()}
    try:
        q = ex.evaluate(tree, env, lambda name: _unknown(ctx, name, list(known), later))
    except QuantityError as error:
        raise ctx.fail(str(error)) from None
    try:
        unit = parse_unit(c.unit) if c.unit else si_unit(q.dim)
    except VidgenError as error:
        raise ctx.fail(f"unit: {error}") from None
    if unit.dim != q.dim:
        raise ctx.fail(f"the result is {describe_dim(q.dim)}, but unit '{c.unit}' is {describe_dim(unit.dim)}")
    if c.format == "percent":
        if q.dim != DIMENSIONLESS:
            raise ctx.fail(f"format: percent needs a pure number, but the result is {describe_dim(q.dim)}")
        unit = parse_unit("%")
    if c.format == "fraction" and c.sig is not None:
        raise ctx.fail("sig and format: fraction exclude each other (an exact fraction has no significant figures)")
    warnings = []
    if c.sig is not None and q.sig is not None and c.sig > q.sig:
        warnings.append(f"sig {c.sig} claims more than the inputs give ({q.sig} significant figures)")
    try:
        number = _exact_number(q, unit, c.sig, c.format)
    except QuantityError as error:
        raise ctx.fail(str(error)) from None
    shown = Quantity(q.value, q.dim, c.sig if c.sig is not None else q.sig)
    value = _with_si(SymbolValue(c.name, c.symbol or name_tex(c.name), c.meaning, "", shown, unit, number))
    steps = _steps(c, tree, q, value, known, wrap)
    conversions = []
    for target in c.convert:
        try:
            u = parse_unit(target)
        except VidgenError as error:
            raise ctx.fail(f"convert: {error}") from None
        if u.dim != q.dim:
            raise ctx.fail(f"convert: '{target}' is {describe_dim(u.dim)}, but the result is {describe_dim(q.dim)}")
        n = _exact_number(value.quantity, u, None, "auto" if c.format in ("fraction", "percent") else c.format)
        conv = SymbolValue(c.name, value.tex, c.meaning, "", value.quantity, u, n)
        conversions.append(conv)
        tex, _ = conv.value_tex()
        steps.append(Step("convert", tex, r"\approx" if n.approx and value.quantity.sig is None else "=", plain=conv.value_text()))
    if len(conversions) > 1:   # several conversions: one line, = 29.8 km/s = 1.07 × 10⁵ km/h
        joined = [s for s in steps if s.kind == "convert"]
        merged = Step("convert", joined[0].tex + "".join(f" {s.relation} {s.tex}" for s in joined[1:]), joined[0].relation,
                      plain=" = ".join(s.plain for s in joined))
        steps = [s for s in steps if s.kind != "convert"] + [merged]
    return CalcResult(k, value, steps, [n for n in tree.names() if n in known], conversions, warnings)


def _steps(c: CalcInput, tree: ex.Node, q: Quantity, value: SymbolValue, known: Mapping[str, SymbolValue], wrap: Wrap) -> list[Step]:
    def symbol(node: ex.Node) -> tuple[str, float] | None:
        v = known.get(node.value)
        return (wrap(node.value, "{" + v.tex + "}"), ex.ATOM) if v is not None else None

    def substituted(units: bool) -> Callable[[ex.Node], tuple[str, float] | None]:
        def leaf(node: ex.Node) -> tuple[str, float] | None:
            v = known.get(node.value)
            if v is None:
                return None
            tex, level = v.value_tex(units)
            return wrap(node.value, "{" + tex + "}"), level
        return leaf

    formula = c.tex or ex.to_tex(tree, symbol)[0]
    steps = [Step("formula", formula, plain=c.expr)]
    leaves = [n for n in tree.walk() if n.kind == "name" and n.value in known]
    if c.substitute and leaves:
        variants = {(units, stack): ex.to_tex(tree, substituted(units), values=True, stack=stack)[0] for units in (True, False) for stack in (0, 1, 2)}
        steps.append(Step("substitute", variants[True, 0], alt=variants[False, 0], stacked=variants[True, 1], alt_stacked=variants[False, 1],
                          deep=variants[True, 2]))
    want = c.intermediate if c.intermediate is not None else True
    if want and tree.kind in ("call", "^") and len(tree.walk()) > 3:
        replace = {}
        env = {n: v.quantity for n, v in known.items()}
        for child in tree.children:
            if child.kind in ("num", "name"):
                continue
            part = ex.evaluate(child, env)
            u = si_unit(part.dim)
            # one guard digit beyond the result's significant figures
            guard = min(part.sig, c.sig + 1) if part.sig is not None and c.sig is not None else part.sig
            n = _exact_number(Quantity(part.value, part.dim, guard), u, None, "auto")
            sv = SymbolValue("", "", "", "", part, u, n)
            replace[id(child)] = sv.value_tex()
        if replace:
            steps.append(Step("intermediate", ex.to_tex(tree, symbol, replace, values=True)[0]))
    shown, _ = value.value_tex()
    exact_frac = value.number.fraction and q.rational
    if exact_frac:
        shown_value = Fraction(qy.in_unit(q, value.unit)[0])
        approx = _decimal_of(shown_value, c.sig)
        sign = r"\approx" if approx.approx else "="
        unit_tex = "" if not value.unit.parts else r"\," + value.unit.tex
        steps.append(Step("result", rf"{shown} {sign} {approx.tex}{unit_tex}", "=", plain=f"{value.value_text()} {'≈' if approx.approx else '='} {approx.plain}"))
    else:
        relation = r"\approx" if q.sig is None and value.number.approx and c.sig is None else "="
        steps.append(Step("result", shown, relation, plain=value.value_text()))
    return steps


__all__ = [
    "CONSTANT_DIGITS",
    "CalcInput",
    "CalcResult",
    "EXACT_DIGITS",
    "FORMATS",
    "Step",
    "SymbolInput",
    "SymbolValue",
    "Worked",
    "check_name",
    "name_tex",
    "work",
]
