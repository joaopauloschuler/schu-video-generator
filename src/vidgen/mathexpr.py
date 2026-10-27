"""Safe maths expressions of ``x`` for the maths scenes (``function_plot``, DESIGN §87.6; exported
by ``vidgen.api``).

A small whitelisted parser, not ``eval``: numbers, ``x``, the constants ``pi`` / ``e`` / ``tau``,
``+ - * / ^`` (``**`` too), brackets, implicit products (``2x``, ``3(x + 1)``, ``2 sin(x)``),
the functions in :data:`MATH_FUNCTIONS` and, through ``known``, functions defined before
(``g(x) = f(x) + 1``). :func:`parse_expression` compiles the text into a :class:`MathExpression`
that evaluates numpy arrays (``nan`` where the function is undefined). No manim, no vidgen.
"""

from __future__ import annotations

import difflib
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

Evaluate = Callable[[np.ndarray], np.ndarray]


def _log(base: float) -> Callable[[np.ndarray], np.ndarray]:
    return lambda v: np.log(v) / math.log(base)


#: The functions an expression may call: name -> (number of arguments, numpy function).
MATH_FUNCTIONS: dict[str, tuple[int, Callable[..., np.ndarray]]] = {
    "sin": (1, np.sin), "cos": (1, np.cos), "tan": (1, np.tan),
    "asin": (1, np.arcsin), "acos": (1, np.arccos), "atan": (1, np.arctan),
    "sinh": (1, np.sinh), "cosh": (1, np.cosh), "tanh": (1, np.tanh),
    "exp": (1, np.exp), "ln": (1, np.log), "log": (1, np.log), "log10": (1, _log(10)), "log2": (1, _log(2)),
    "sqrt": (1, np.sqrt), "abs": (1, np.abs), "floor": (1, np.floor), "ceil": (1, np.ceil), "sign": (1, np.sign),
    "min": (2, np.minimum), "max": (2, np.maximum),
}
#: Named constants.
MATH_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}
#: The variable.
VARIABLE = "x"
#: Every name an expression knows without being told (the variable, constants, functions): not
#: a name for a function of your own.
MATH_NAMES = frozenset({VARIABLE, *MATH_CONSTANTS, *MATH_FUNCTIONS})
#: Characters written in maths text that mean an ASCII operator or name.
_UNICODE = {"−": "-", "–": "-", "×": "*", "·": "*", "⋅": "*", "÷": "/", "π": " pi ", "τ": " tau ", "√": "sqrt",
            "²": "^2", "³": "^3"}
_TOKEN = re.compile(r"\s*(?:(?P<num>\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|(?P<name>[A-Za-z_]\w*)|(?P<op>\*\*|[-+*/^(),]))")
#: A definition written as ``f(x) = ...`` or ``y = ...``.
_DEFINITION = re.compile(r"^\s*(?:(?P<name>[A-Za-z_]\w*)\s*\(\s*x\s*\)|y)\s*=(?P<body>.*)$", re.S)


@dataclass(frozen=True)
class MathExpression:
    """A parsed expression: its ``text`` as written, the ``names`` of other functions it calls,
    and :meth:`__call__` evaluating it on numbers or numpy arrays (``nan`` where undefined)."""

    text: str
    evaluate: Evaluate = field(repr=False, compare=False)
    names: tuple[str, ...] = ()

    def __call__(self, xs: np.ndarray | float) -> np.ndarray:
        """The values at ``xs`` (floats; ``nan`` where undefined or not finite)."""
        values = np.asarray(xs, dtype=float)
        with np.errstate(all="ignore"):
            out = np.asarray(self.evaluate(values), dtype=float)
        out = np.broadcast_to(out, values.shape).astype(float)
        out[~np.isfinite(out)] = np.nan
        return out

    def at(self, x: float) -> float:
        """The value at one ``x`` (``nan`` where undefined)."""
        return float(self(np.array([x]))[0])

    def slope(self, x: float, step: float = 1e-5) -> float:
        """The derivative at ``x`` (a central difference over ``step``; ``nan`` where undefined)."""
        values = self(np.array([x - step, x + step]))
        return float((values[1] - values[0]) / (2 * step))


def split_definition(text: str) -> tuple[str | None, str]:
    """``("f", "x^2")`` for ``"f(x) = x^2"``, ``(None, "x^2")`` for ``"y = x^2"`` or ``"x^2"``."""
    match = _DEFINITION.match(text)
    if match is None:
        return None, text.strip()
    return match.group("name"), match.group("body").strip()


def _plain(text: str) -> str:
    for char, ascii_text in _UNICODE.items():
        text = text.replace(char, ascii_text)
    return text


def _tokens(text: str) -> list[tuple[str, str, int]]:
    """``(kind, text, column)`` tokens (kind ``num``, ``name``, ``op``, then ``end``)."""
    out: list[tuple[str, str, int]] = []
    pos = 0
    stripped = text.rstrip()
    while pos < len(stripped):
        match = _TOKEN.match(stripped, pos)
        if match is None or match.end() == pos:
            bad = stripped[pos:].lstrip()[:1]
            raise ValueError(f"{text!r}: unexpected {bad!r} at character {len(stripped) - len(stripped[pos:].lstrip()) + 1} (use numbers, x, + - * / ^, brackets and functions like sin(x))")
        kind = match.lastgroup or "op"
        out.append((kind, match.group(kind), match.start(kind) + 1))
        pos = match.end()
    out.append(("end", "", len(stripped) + 1))
    return out


def _found(text: str) -> str:
    return repr(text) if text else "the end"


class _Parser:
    """Recursive descent over the tokens; each rule returns a numpy closure."""

    def __init__(self, text: str, known: Mapping[str, MathExpression], slots: Mapping[str, int] | None = None, values: list[float] | None = None) -> None:
        self.text, self.known = text, known
        self.tokens = _tokens(_plain(text))
        self.i = 0
        self.called: list[str] = []
        self.slots = dict(slots or {})   # parameter name -> index into values (a model's parameters)
        self.values = values if values is not None else []
        self.used: set[str] = set()

    def peek(self) -> tuple[str, str, int]:
        return self.tokens[self.i]

    def take(self) -> tuple[str, str, int]:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def fail(self, message: str) -> ValueError:
        return ValueError(f"{self.text!r}: {message}")

    def expect(self, op: str) -> None:
        kind, text, col = self.take()
        if (kind, text) != ("op", op):
            raise self.fail(f"expected {op!r} at character {col}, found {_found(text)}")

    def parse(self) -> Evaluate:
        if self.peek()[0] == "end":
            raise self.fail("the expression is empty")
        tree = self.sum()
        kind, text, col = self.peek()
        if kind != "end":
            raise self.fail(f"unexpected {text!r} at character {col}")
        return tree

    def sum(self) -> Evaluate:
        left = self.product()
        while self.peek()[:2] in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            right = self.product()
            left = (lambda a, b: lambda v: a(v) + b(v))(left, right) if op == "+" else (lambda a, b: lambda v: a(v) - b(v))(left, right)
        return left

    def _starts_factor(self) -> bool:
        kind, text, _ = self.peek()
        return kind in ("num", "name") or (kind, text) == ("op", "(")

    def product(self) -> Evaluate:
        left = self.unary()
        while True:
            kind, text, _ = self.peek()
            if (kind, text) in (("op", "*"), ("op", "/")):
                self.take()
                right = self.unary()
            elif self._starts_factor():  # an implicit product: 2x, 3(x + 1), x sin(x)
                text = "*"
                right = self.power()
            else:
                return left
            left = (lambda a, b: lambda v: a(v) * b(v))(left, right) if text == "*" else (lambda a, b: lambda v: a(v) / b(v))(left, right)

    def unary(self) -> Evaluate:
        if self.peek()[:2] == ("op", "-"):
            self.take()
            inner = self.unary()
            return lambda v: -inner(v)
        if self.peek()[:2] == ("op", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> Evaluate:
        base = self.atom()
        if self.peek()[:2] in (("op", "^"), ("op", "**")):
            self.take()
            exponent = self.unary()  # right-associative; 2^-x
            return lambda v: np.power(base(v), exponent(v))
        return base

    def atom(self) -> Evaluate:
        kind, text, col = self.take()
        if kind == "num":
            value = float(text)
            return lambda v: np.full_like(v, value)
        if kind == "op" and text == "(":
            inner = self.sum()
            self.expect(")")
            return inner
        if kind == "name":
            return self.name(text, col)
        raise self.fail(f"expected a number, x, a function or '(' at character {col}, found {_found(text)}")

    def name(self, text: str, col: int) -> Evaluate:
        if text == VARIABLE:
            return lambda v: v
        if text in self.slots:
            index, values = self.slots[text], self.values
            self.used.add(text)
            return lambda v: np.full_like(v, values[index])
        if text in MATH_CONSTANTS:
            value = MATH_CONSTANTS[text]
            return lambda v: np.full_like(v, value)
        if text in MATH_FUNCTIONS or text in self.known:
            if self.peek()[:2] != ("op", "("):
                raise self.fail(f"{text} needs its argument in brackets: {text}(x)")
            self.take()
            args = [self.sum()]
            while self.peek()[:2] == ("op", ","):
                self.take()
                args.append(self.sum())
            self.expect(")")
            if text in self.known:
                if len(args) != 1:
                    raise self.fail(f"{text} takes one argument, got {len(args)}")
                self.called.append(text)
                inner, function = args[0], self.known[text]
                return lambda v: function(inner(v))
            count, numpy_function = MATH_FUNCTIONS[text]
            if len(args) != count:
                raise self.fail(f"{text} takes {count} argument{'s' if count > 1 else ''}, got {len(args)}")
            return (lambda f, a: lambda v: f(*(g(v) for g in a)))(numpy_function, args)
        names = [VARIABLE, *self.slots, *MATH_CONSTANTS, *MATH_FUNCTIONS, *self.known]
        close = difflib.get_close_matches(text, names, n=3, cutoff=0.6)
        hint = f" (did you mean {', '.join(close)}?)" if close else ""
        known = f"; functions defined before: {', '.join(self.known)}" if self.known else ""
        params = f"; parameters {', '.join(self.slots)}" if self.slots else ""
        raise self.fail(f"unknown name {text!r} at character {col}{hint}; the variable is x{params}, constants pi, e, tau, functions {', '.join(MATH_FUNCTIONS)}{known}")


def parse_expression(text: str, known: Mapping[str, MathExpression] | None = None) -> MathExpression:
    """Compile ``text`` (an expression of ``x``) into an :class:`MathExpression`; ``known`` are the
    functions it may call by name. Raises ``ValueError`` naming the problem and where it is."""
    parser = _Parser(text, known or {})
    evaluate = parser.parse()
    return MathExpression(text.strip(), evaluate, tuple(dict.fromkeys(parser.called)))


_PARAMETER = re.compile(r"^[A-Za-z_]\w*$")


@dataclass(frozen=True)
class ModelExpression:
    """An expression of ``x`` and named ``parameters`` (a model to fit, e.g. ``a*exp(-x/tau) +
    c``): :meth:`__call__` evaluates it at ``xs`` for parameter ``values`` given in the order of
    ``parameters`` (``nan`` where undefined)."""

    text: str
    parameters: tuple[str, ...]
    evaluate: Evaluate = field(repr=False, compare=False)
    values: list[float] = field(repr=False, compare=False)

    def __call__(self, xs: np.ndarray | float, values: Sequence[float]) -> np.ndarray:
        """The model's values at ``xs`` for the parameter ``values``."""
        if len(values) != len(self.parameters):
            raise ValueError(f"{self.text!r} has {len(self.parameters)} parameters, got {len(values)} values")
        self.values[:] = [float(v) for v in values]
        x = np.asarray(xs, dtype=float)
        with np.errstate(all="ignore"):
            out = np.asarray(self.evaluate(x), dtype=float)
        out = np.broadcast_to(out, x.shape).astype(float)
        out[~np.isfinite(out)] = np.nan
        return out


def parse_model(text: str, parameters: Sequence[str]) -> ModelExpression:
    """Compile ``text``, an expression of ``x`` and the named ``parameters`` (identifiers other
    than ``x`` and the function names; a parameter may take a constant's name, e.g. ``tau``,
    which then means the parameter) into a :class:`ModelExpression`. Raises ``ValueError`` for a
    bad expression, a bad or repeated parameter name, or a parameter the expression does not
    use."""
    names = list(parameters)
    for name in names:
        if not _PARAMETER.match(name):
            raise ValueError(f"parameter name {name!r} is not a name (letters, digits, _)")
        if name == VARIABLE or name in MATH_FUNCTIONS:
            raise ValueError(f"parameter name {name!r} is taken (x is the variable; functions: {', '.join(MATH_FUNCTIONS)})")
        if names.count(name) > 1:
            raise ValueError(f"parameter {name!r} is named twice")
    values: list[float] = [0.0] * len(names)
    parser = _Parser(text, {}, {n: i for i, n in enumerate(names)}, values)
    evaluate = parser.parse()
    unused = [n for n in names if n not in parser.used]
    if unused:
        raise ValueError(f"{text.strip()!r}: the parameter{'s' if len(unused) > 1 else ''} {', '.join(unused)} {'are' if len(unused) > 1 else 'is'} not in the expression")
    return ModelExpression(text.strip(), tuple(names), evaluate, values)


_SUPERSCRIPTS = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def pretty_expression(text: str) -> str:
    """``text`` as maths reads in a label: ``x^2`` -> ``x²``, ``*`` -> ``·`` (dropped before a
    letter or a bracket after a number: ``2*x`` -> ``2x``), ``pi`` -> ``π``, ``sqrt`` -> ``√``,
    ``-`` -> ``−``."""
    out = re.sub(r"\s*\*\*\s*|\s*\^\s*", "^", text.strip())
    out = re.sub(r"\^\(?(-?\d+)\)?(?![\d.])", lambda m: m.group(1).translate(_SUPERSCRIPTS), out)
    out = re.sub(r"(\d)\s*\*\s*(?=[A-Za-z(])", r"\1", out)
    out = re.sub(r"\s*\*\s*", "·", out)
    out = re.sub(r"\bpi\b", "π", out)
    out = re.sub(r"\btau\b", "τ", out)
    out = re.sub(r"\bsqrt\b", "√", out)
    return out.replace("-", "−")
