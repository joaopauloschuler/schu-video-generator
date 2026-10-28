"""Tables of numbers for plots: a CSV / TSV read into named columns, the unit of each column
taken from its header (``time (s)``, ``E [MeV]``, ``v / km s^-1``), every cell checked."""

from __future__ import annotations

import csv
import difflib
import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.errors import VidgenError

from .numbers import MINUS

#: Headers ``name (unit)`` (a space before the parenthesis, so ``f(x)`` stays a name),
#: ``name [unit]`` or ``name / unit`` (spaces around the slash).
_HEADER = re.compile(r"^(?P<name>.*?)(?:\s+\((?P<p>[^()]*)\)|\s*\[(?P<b>[^\[\]]*)\]|\s/\s(?P<s>.+))\s*$")
#: Cells read as a missing value (a gap in a line).
MISSING = frozenset({"", "na", "nan", "n/a", "null", "none", "-", "—"})


def split_header(header: str) -> tuple[str, str]:
    """A column header's name and unit: ``"time (s)"`` -> ``("time", "s")``, ``"E [MeV]"`` ->
    ``("E", "MeV")``, ``"v / km/s"`` -> ``("v", "km/s")``, ``"count"`` -> ``("count", "")``."""
    text = header.strip()
    m = _HEADER.match(text)
    if m and m.group("name"):
        unit = next(g for g in (m.group("p"), m.group("b"), m.group("s")) if g is not None)
        return m.group("name").strip(), unit.strip()
    return text, ""


def parse_number(cell: str, where: str) -> float:
    """A number from a table cell or YAML string: ``1.5``, ``-3e-4``, ``−2`` (U+2212), ``1e6``;
    a missing value (blank, ``NA``, ``NaN``) is ``nan``. Anything else raises ``VidgenError``."""
    text = cell.strip()
    if text.lower() in MISSING:
        return math.nan
    normal = text.replace(MINUS, "-").replace(" ", "").replace(" ", "")
    try:
        value = float(normal)
    except ValueError:
        hint = " (use a dot for decimals)" if re.fullmatch(r"-?\d+,\d+", normal) else ""
        raise VidgenError(f"{where}: '{text}' is not a number{hint}") from None
    if not math.isfinite(value):
        raise VidgenError(f"{where}: '{text}' is not a finite number")
    return value


@dataclass(frozen=True)
class Column:
    """One column: its ``name`` and ``unit`` (from the header) and its ``values`` (``nan`` for
    missing cells)."""

    name: str
    unit: str
    values: tuple[float, ...]
    label: str = ""
    """How an axis title names it when the author gives no label (a model's ``θ_min``); "" for the name."""


@dataclass(frozen=True)
class Table:
    """Columns read from a file (``source`` names it in messages), in file order."""

    source: str
    columns: tuple[Column, ...]

    def names(self) -> list[str]:
        """The column names, in file order."""
        return [c.name for c in self.columns]

    def column(self, name: str, where: str = "") -> Column:
        """The column called ``name`` (or whose full header is ``name``, e.g. ``"time (s)"``);
        an unknown name raises ``VidgenError`` naming the columns, with did-you-mean."""
        wanted, _ = split_header(name)
        for c in self.columns:
            if c.name == wanted or c.name.lower() == wanted.lower():
                return c
        prefix = f"{where}: " if where else ""
        raise VidgenError(f"{prefix}{self.source} has no column '{name}' (columns: {', '.join(self.names())})" + did_you_mean(wanted, self.names()))


def did_you_mean(word: str, options: Sequence[str]) -> str:
    """``"; did you mean 'x'?"`` for the closest of ``options``, else ``""``."""
    close = difflib.get_close_matches(word, list(options), n=1, cutoff=0.6)
    if not close:
        lower = {o.lower(): o for o in options}
        close = [lower[c] for c in difflib.get_close_matches(word.lower(), list(lower), n=1, cutoff=0.6)]
    return f"; did you mean '{close[0]}'?" if close else ""


def read_table(text: str, source: str) -> Table:
    """Columns of numbers from CSV text (comma, semicolon or tab separated, picked from the
    header line; lines starting with ``#`` are comments). The first row names the columns,
    with optional units (:func:`split_header`). Raises ``VidgenError`` naming the line and
    column of a bad cell, a row of the wrong length, a repeated or blank header, an empty file
    or a column without numbers."""
    numbered = [(n, ln) for n, ln in enumerate(text.splitlines(), start=1) if ln.strip() and not ln.lstrip().startswith("#")]
    if not numbered:
        raise VidgenError(f"{source}: the file has no rows")
    head = numbered[0][1]
    delim = max(("\t", ";", ","), key=head.count) if any(d in head for d in "\t;,") else ","
    rows = list(csv.reader(io.StringIO("\n".join(ln for _, ln in numbered)), delimiter=delim))
    header = [h.strip() for h in rows[0]]
    if any(not h for h in header):
        raise VidgenError(f"{source}, line {numbered[0][0]}: column {header.index('') + 1} has no name")
    parts = [split_header(h) for h in header]
    names = [p[0] for p in parts]
    for i, name in enumerate(names):
        if name.lower() in (n.lower() for n in names[:i]):
            raise VidgenError(f"{source}, line {numbered[0][0]}: the column '{name}' appears twice")
    if len(rows) < 2:
        raise VidgenError(f"{source}: the file has a header but no data rows")
    values: list[list[float]] = [[] for _ in names]
    for (line_no, _), row in zip(numbered[1:], rows[1:]):
        if len(row) != len(names):
            raise VidgenError(f"{source}, line {line_no}: {len(row)} values, but the header names {len(names)} columns")
        for k, cell in enumerate(row):
            values[k].append(parse_number(cell, f"{source}, line {line_no}, column '{names[k]}'"))
    for name, vals in zip(names, values):
        if all(math.isnan(v) for v in vals):
            raise VidgenError(f"{source}: the column '{name}' has no numbers")
    return Table(source, tuple(Column(n, u, tuple(v)) for (n, u), v in zip(parts, values)))


__all__ = ["MISSING", "Column", "Table", "did_you_mean", "parse_number", "read_table", "split_header"]
