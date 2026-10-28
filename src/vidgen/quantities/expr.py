"""Calculation expressions with units (DESIGN §97.9). No manim, no ``eval``.

The grammar of :mod:`vidgen.mathexpr` (numbers, names, ``+ - * / ^`` / ``**``, brackets,
implicit products ``2pq``, function calls), parsed into a small tree so that one expression can
be evaluated on quantities (:func:`evaluate`: units checked, exactness and significant figures
carried) and written in TeX — with the symbols (``v = \\sqrt{\\frac{G M_{\\odot}}{r}}``), with
their values and units substituted, or with parts replaced by their values (:func:`to_tex`).
A number may carry a unit in square brackets: ``0.5 [m]``. Numbers written in a formula are
exact (``2`` in ``2pq``, ``1/2`` in ``mv^2/2``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from vidgen.errors import VidgenError

from . import quantity as qy
from .quantity import Quantity
from .units import parse_unit

#: Names of constants every expression knows (a symbol of the same name takes precedence).
EXPR_CONSTANTS = {"pi": r"\pi", "tau": r"\tau", "e": "e"}
_CONST_VALUES = {"pi": 3.141592653589793, "tau": 6.283185307179586, "e": 2.718281828459045}
_UNICODE = {"−": "-", "–": "-", "×": "*", "·": "*", "⋅": "*", "÷": "/", "π": " pi ", "τ": " tau ", "√": "sqrt", "²": "^2", "³": "^3"}
_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|(?P<unit>\[[^\]]*\])|(?P<name>[A-Za-z_]\w*)|(?P<op>\*\*|[-+*/^(),]))"
)
#: TeX of the functions.
_FUNC_TEX = {"ln": r"\ln", "log": r"\log", "log10": r"\log_{10}", "log2": r"\log_{2}", "sin": r"\sin", "cos": r"\cos", "tan": r"\tan",
             "asin": r"\arcsin", "acos": r"\arccos", "atan": r"\arctan", "sinh": r"\sinh", "cosh": r"\cosh", "tanh": r"\tanh",
             "min": r"\min", "max": r"\max"}

# precedence levels of TeX parts: a part below what its place needs is bracketed
SUM, NEG, PROD, FRAC, POW, ATOM = 1, 1.5, 2, 3, 4, 5


@dataclass
class Node:
    """A node of an expression tree: ``kind`` is ``num``, ``name``, ``neg``, ``+``, ``-``,
    ``*``, ``/``, ``^`` or ``call``; ``text`` is the node as written (for messages)."""

    kind: str
    text: str
    children: list[Node] = field(default_factory=list)
    value: str = ""          # num: the digits; name: the name; call: the function
    unit: str = ""           # num: a unit in [brackets]
    implicit: bool = False   # *: written without an operator (2pq)

    def names(self) -> list[str]:
        """The names the expression reads, in order, once each."""
        out: list[str] = []
        if self.kind == "name":
            out.append(self.value)
        for c in self.children:
            out += c.names()
        return list(dict.fromkeys(out))

    def walk(self) -> list[Node]:
        out = [self]
        for c in self.children:
            out += c.walk()
        return out


def _plain(text: str) -> str:
    for char, ascii_text in _UNICODE.items():
        text = text.replace(char, ascii_text)
    return text


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        source = _plain(text)
        self.source = source
        self.tokens: list[tuple[str, str, int, int]] = []
        pos = 0
        stripped = source.rstrip()
        while pos < len(stripped):
            m = _TOKEN.match(stripped, pos)
            if m is None or m.end() == pos:
                bad = stripped[pos:].lstrip()[:1]
                raise VidgenError(f"{text!r}: unexpected {bad!r} (use numbers, names, + - * / ^, brackets, sqrt(...), and units in [brackets])")
            kind = m.lastgroup or "op"
            self.tokens.append((kind, m.group(kind), m.start(kind), m.end(kind)))
            pos = m.end()
        self.tokens.append(("end", "", len(stripped), len(stripped)))
        self.i = 0

    def peek(self) -> tuple[str, str, int, int]:
        return self.tokens[self.i]

    def take(self) -> tuple[str, str, int, int]:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def fail(self, message: str) -> VidgenError:
        return VidgenError(f"{self.text!r}: {message}")

    def span(self, start: int) -> str:
        end = self.tokens[self.i - 1][3] if self.i else start
        return self.source[start:end].strip()

    def parse(self) -> Node:
        if self.peek()[0] == "end":
            raise self.fail("the expression is empty")
        node = self.sum()
        kind, text, col, _ = self.peek()
        if kind != "end":
            raise self.fail(f"unexpected {text!r} at character {col + 1}")
        return node

    def sum(self) -> Node:
        start = self.peek()[2]
        left = self.product()
        while self.peek()[:2] in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            right = self.product()
            left = Node(op, self.span(start), [left, right])
        return left

    def _starts_factor(self) -> bool:
        kind, text, _, _ = self.peek()
        return kind in ("num", "name") or (kind, text) == ("op", "(")

    def product(self) -> Node:
        start = self.peek()[2]
        left = self.unary()
        while True:
            kind, text, _, _ = self.peek()
            if (kind, text) in (("op", "*"), ("op", "/")):
                self.take()
                right = self.unary()
                left = Node(text, self.span(start), [left, right])
            elif self._starts_factor():
                right = self.power()
                left = Node("*", self.span(start), [left, right], implicit=True)
            else:
                return left

    def unary(self) -> Node:
        start = self.peek()[2]
        if self.peek()[:2] == ("op", "-"):
            self.take()
            inner = self.unary()
            return Node("neg", self.span(start), [inner])
        if self.peek()[:2] == ("op", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> Node:
        start = self.peek()[2]
        base = self.atom()
        if self.peek()[:2] in (("op", "^"), ("op", "**")):
            self.take()
            exponent = self.unary()
            return Node("^", self.span(start), [base, exponent])
        return base

    def atom(self) -> Node:
        kind, text, col, _ = self.take()
        if kind == "num":
            unit = ""
            if self.peek()[0] == "unit":
                unit = self.take()[1][1:-1].strip()
                parse_unit(unit)
            return Node("num", text + (f" [{unit}]" if unit else ""), value=text, unit=unit)
        if kind == "unit":
            raise self.fail(f"a unit in brackets ({text}) follows a number: 2 {text}")
        if kind == "op" and text == "(":
            inner = self.sum()
            if self.take()[:2] != ("op", ")"):
                raise self.fail("a '(' is not closed")
            return inner
        if kind == "name":
            if self.peek()[:2] == ("op", "("):
                if text not in qy.FUNCTIONS:
                    import difflib

                    close = difflib.get_close_matches(text, list(qy.FUNCTIONS), n=1, cutoff=0.6)
                    hint = f" (did you mean {close[0]}?)" if close else ""
                    raise self.fail(f"unknown function {text!r}{hint}; functions: {', '.join(qy.FUNCTIONS)}")
                self.take()
                args = [self.sum()]
                while self.peek()[:2] == ("op", ","):
                    self.take()
                    args.append(self.sum())
                if self.take()[:2] != ("op", ")"):
                    raise self.fail(f"{text}(...) is not closed")
                want = 2 if text in ("min", "max") else 1
                if len(args) != want:
                    raise self.fail(f"{text} takes {want} argument{'s' if want > 1 else ''}, got {len(args)}")
                return Node("call", f"{text}({', '.join(a.text for a in args)})", args, value=text)
            if text in qy.FUNCTIONS:
                raise self.fail(f"{text} needs its argument in brackets: {text}(x)")
            return Node("name", text, value=text)
        raise self.fail(f"expected a number, a name, a function or '(' at character {col + 1}, found {text or 'the end'!r}")


def parse(text: str) -> Node:
    """The tree of ``text``; raises :class:`VidgenError` naming the problem and where."""
    return _Parser(text).parse()


# ----- evaluation -------------------------------------------------------------------------------

def literal(node: Node) -> Quantity:
    """A number written in a formula: exact (with its unit, if any)."""
    value = qy.number_value(node.value)
    unit = parse_unit(node.unit)
    return Quantity(unit.to_si(value), unit.dim, None, "point" if unit.offset else "")


def evaluate(node: Node, env: Mapping[str, Quantity], unknown: Callable[[str], VidgenError] | None = None) -> Quantity:
    """The value of ``node`` with the names in ``env``; ``e``, ``pi``, ``tau`` unless a name
    shadows them. Raises :class:`QuantityError` (units, division by zero) or ``unknown(name)``."""
    k = node.kind
    if k == "num":
        return literal(node)
    if k == "name":
        if node.value in env:
            return env[node.value]
        if node.value in _CONST_VALUES:
            return Quantity(_CONST_VALUES[node.value], sig=None)
        raise unknown(node.value) if unknown is not None else VidgenError(f"unknown name '{node.value}'")
    args = [evaluate(c, env, unknown) for c in node.children]
    texts = [c.text for c in node.children]
    if k == "neg":
        return qy.neg(args[0])
    if k in ("+", "-"):
        return qy.add(args[0], args[1], 1 if k == "+" else -1, f"'{texts[0]}'", f"'{texts[1]}'")
    if k == "*":
        return qy.mul(*args)
    if k == "/":
        return qy.div(args[0], args[1], f"'{texts[1]}'")
    if k == "^":
        return qy.power(args[0], args[1], f"'{texts[0]}'", texts[1])
    return qy.call(node.value, args, [f"'{t}'" for t in texts])


# ----- TeX --------------------------------------------------------------------------------------

Leaf = Callable[[Node], "tuple[str, float] | None"]


def number_tex(text: str) -> tuple[str, float]:
    """A number of a formula in TeX: ``6.674e-11`` -> ``6.674 \\times 10^{-11}``."""
    nt = qy.written_number(text)
    return nt.tex, (PROD if nt.sci else ATOM)


def _wrap(tex: str, level: float, need: float) -> str:
    return rf"\left({tex}\right)" if level < need else tex


def _factors(node: Node) -> list[Node]:
    """The factors of a chain of products (``a*b*c`` -> ``[a, b, c]``)."""
    if node.kind != "*":
        return [node]
    return [f for c in node.children for f in _factors(c)]


def _root_side(node: Node) -> bool:
    """A product with a root of a sum beside the other factor (``sqrt(g^2 - 1)*c``): set apart
    by a thin space, or the root's last term runs into the factor (``√(γ²−1)cτ`` read as ``1c``)."""
    left, right = _factors(node.children[0])[-1], _factors(node.children[1])[0]
    return any(f.kind == "call" and f.value == "sqrt" and f.children and f.children[0].kind in ("+", "-") for f in (left, right))


def to_tex(node: Node, leaf: Leaf, replace: Mapping[int, tuple[str, float]] | None = None, values: bool = False,
           stack: int = 0) -> tuple[str, float]:
    """``node`` in TeX and the precedence level of its top part. ``leaf(node)`` writes a name
    (a symbol, or a value with its unit) as ``(tex, level)``; ``replace`` maps ``id(node)`` to
    a part written instead (an evaluated sub-expression); ``values``: the names are written as
    values, so every product gets a times sign; ``stack``: the outermost products are set on
    two lines (1, a narrow frame) or one factor per line (2)."""
    if replace and id(node) in replace:
        return replace[id(node)]
    k = node.kind
    if k == "num":
        tex, level = number_tex(node.value)
        if node.unit:
            return tex + r"\," + parse_unit(node.unit).tex, PROD
        return tex, level
    if k == "name":
        got = leaf(node)
        if got is not None:
            return got
        return EXPR_CONSTANTS.get(node.value, node.value), ATOM
    if k == "*" and stack:
        factors = [to_tex(f, leaf, replace, values) for f in _factors(node)]
        texts = [_wrap(t, level, PROD) for t, level in factors]
        if stack >= 2:   # a bare number stays with the factor after it (2 × G, not 2 alone)
            lines, carry = [], []
            for f, t in zip(_factors(node), texts):
                carry.append(t)
                if not (f.kind == "num" and not f.unit):
                    lines.append(r" \times ".join(carry))
                    carry = []
            if carry:
                lines.append(r" \times ".join(carry))
        else:
            half = (len(texts) + 1) // 2
            lines = [r" \times ".join(texts[:half]), r" \times ".join(texts[half:])]
        rows = r" \\ {} \times ".join(lines)
        return rf"\begin{{array}}{{c}} {rows} \end{{array}}", ATOM
    parts = [to_tex(c, leaf, replace, values, stack) for c in node.children]
    if k == "neg":
        tex, level = parts[0]
        return "-" + _wrap(tex, level, PROD), NEG
    if k in ("+", "-"):
        (a, la), (b, lb) = parts
        return f"{_wrap(a, la, SUM)} {k} {_wrap(b, lb, SUM + (0.5 if k == '-' else 0))}", SUM
    if k == "*":
        (a, la), (b, lb) = parts
        a, b = (a if la == NEG else _wrap(a, la, PROD)), _wrap(b, lb, PROD)   # -k t: a leading minus needs no brackets
        # symbols side by side (2pq, G M); numbers and substituted values with ×
        sep = r" \times " if values or re.match(r"(\\frac\{)?[\d.]", b) else (r"\," if "_" in a + b or _root_side(node) else " ")
        return a + sep + b, PROD
    if k == "/":
        (a, _), (b, _) = parts
        return rf"\frac{{{a}}}{{{b}}}", FRAC
    if k == "^":
        (a, la), (b, lb) = parts
        exp_node = node.children[1]
        if exp_node.kind == "/" and all(c.kind == "num" for c in exp_node.children):
            b = f"{exp_node.children[0].value}/{exp_node.children[1].value}"
        return rf"{{{_wrap(a, la, ATOM)}}}^{{{b}}}", POW
    name = node.value
    if name == "sqrt":
        return rf"\sqrt{{{parts[0][0]}}}", ATOM
    if name == "exp":
        return rf"e^{{{parts[0][0]}}}", POW
    if name == "abs":
        return rf"\left|{parts[0][0]}\right|", ATOM
    head = _FUNC_TEX[name]
    if name in ("min", "max"):
        return rf"{head}\left({parts[0][0]}, {parts[1][0]}\right)", ATOM
    tex, level = parts[0]
    simple = node.children[0].kind in ("num", "name") and level >= ATOM
    return (rf"{head} {tex}" if simple else rf"{head}\left({tex}\right)"), PROD


__all__ = ["ATOM", "EXPR_CONSTANTS", "FRAC", "NEG", "Node", "POW", "PROD", "SUM", "evaluate", "literal", "number_tex", "parse", "to_tex"]
