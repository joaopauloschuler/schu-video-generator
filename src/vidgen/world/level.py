"""Platform levels written as a small ASCII map (DESIGN.md §86). Plain data, no manim.

A *level* is a grid of *tiles* seen from the side. The map is written top row first, one text
line per row; inside the model rows count from the bottom (row 0 is the lowest) and a tile's
cell spans ``column .. column + 1`` and ``row .. row + 1`` in *tile units*. Symbols are tiles,
letters are *spots*: named places that something stands on (the top of the first tile below the
letter). Messages name cells as the author wrote them: rows from the top, both from 1.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from vidgen.errors import VidgenError

AIR = "air"
GROUND = "ground"
PLATFORM = "platform"
CLOUD = "cloud"
LADDER = "ladder"
#: Map symbol -> tile kind. ``.`` and a space are air; a letter is a spot (air with a name).
TILE_SYMBOLS: dict[str, str] = {".": AIR, " ": AIR, "#": GROUND, "=": PLATFORM, "~": CLOUD, "|": LADDER}
#: The tiles something can stand on (on the tile's top edge).
STANDABLE: frozenset[str] = frozenset({GROUND, PLATFORM, CLOUD})
#: The largest map: wider or taller maps are refused (render time and memory grow with the size).
MAX_COLUMNS = 400
MAX_ROWS = 40
_SYMBOL_WORDS = ". air, # ground, = platform, ~ cloud, | ladder, a letter: a spot"


@dataclass(frozen=True)
class Spot:
    """A named place in a level: its map ``letter``, the letter's cell (``column``, ``row`` from
    the bottom), and where something placed there stands: ``x`` (the cell's middle) and ``y``
    (the top of the first standable tile below it), in tile units."""

    name: str
    letter: str
    column: int
    row: int
    x: float
    y: float


@dataclass(frozen=True)
class Run:
    """``first`` to ``last`` (columns, inclusive) of one ``kind`` of tile next to each other in
    ``row``: a stretch of ground, one floating platform, one cloud."""

    kind: str
    row: int
    first: int
    last: int


@dataclass(frozen=True)
class Level:
    """A parsed level: ``cells[row][column]`` holds the tile kind (row 0 at the bottom) and
    ``spots`` the named places in map order."""

    cells: tuple[tuple[str, ...], ...]
    spots: tuple[Spot, ...] = ()

    @property
    def columns(self) -> int:
        return len(self.cells[0]) if self.cells else 0

    @property
    def rows(self) -> int:
        return len(self.cells)

    def tile(self, column: int, row: int) -> str:
        """The tile at a cell; outside the map: air (a gap goes down forever)."""
        if 0 <= row < self.rows and 0 <= column < self.columns:
            return self.cells[row][column]
        return AIR

    def surface_below(self, column: int, row: int) -> float | None:
        """The height (tile units) of the top of the first standable tile below ``row`` in
        ``column`` (``row`` itself not included); ``None`` over a gap."""
        for r in range(min(row, self.rows) - 1, -1, -1):
            if self.tile(column, r) in STANDABLE:
                return float(r + 1)
        return None

    def top_surface(self, column: int) -> float | None:
        """The highest standable top in ``column`` (``None``: a gap all the way)."""
        return self.surface_below(column, self.rows)

    def column_at(self, x: float) -> int:
        """The column an x (tile units) falls in, held inside the map (the right edge is the
        last column)."""
        return min(max(math.floor(x), 0), self.columns - 1)

    def spot(self, name: str) -> Spot:
        """The spot named ``name``; :class:`VidgenError` listing the spots when there is none."""
        for spot in self.spots:
            if spot.name == name:
                return spot
        known = ", ".join(s.name for s in self.spots) or "none"
        raise VidgenError(f"the level has no spot '{name}' (spots: {known})")

    def spot_names(self) -> list[str]:
        return [spot.name for spot in self.spots]

    def used_rows(self) -> int:
        """How many rows from the bottom hold a tile (the empty sky above them not counted)."""
        for row in range(self.rows - 1, -1, -1):
            if any(kind != AIR for kind in self.cells[row]):
                return row + 1
        return 0

    def runs(self, kind: str) -> list[Run]:
        """Every run of ``kind`` tiles, bottom row first, left to right."""
        found: list[Run] = []
        for row, line in enumerate(self.cells):
            start: int | None = None
            for column, tile in enumerate([*line, AIR]):
                if tile == kind and start is None:
                    start = column
                elif tile != kind and start is not None:
                    found.append(Run(kind, row, start, column - 1))
                    start = None
        return found


def _map_lines(text: str) -> list[str]:
    """The map's rows as written, without the blank lines around it, padded with air on the
    right to the longest row (editors strip trailing spaces)."""
    lines = text.expandtabs(4).splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    width = max((len(line) for line in lines), default=0)
    return [line.ljust(width, ".") for line in lines]


def parse_level(text: str, names: Mapping[str, str] | None = None) -> Level:
    """A :class:`Level` from its ASCII ``text`` (top row first) and ``names`` (map letter -> the
    spot's name; a letter without one is named by itself). Raises :class:`VidgenError` naming the
    row and column (from the top left, from 1) of the first problem."""
    names = dict(names or {})
    lines = _map_lines(text)
    if not lines:
        raise VidgenError("the map is empty: write one line per row, e.g. '..a...' over '######'")
    if len(lines) > MAX_ROWS:
        raise VidgenError(f"the map has {len(lines)} rows; at most {MAX_ROWS}")
    if len(lines[0]) > MAX_COLUMNS:
        raise VidgenError(f"the map is {len(lines[0])} columns wide; at most {MAX_COLUMNS}")
    cells: list[tuple[str, ...]] = []
    letters: dict[str, tuple[int, int]] = {}   # letter -> (row from the top, column), both from 0
    for top_row, line in enumerate(lines):
        kinds = []
        for column, symbol in enumerate(line):
            where = f"row {top_row + 1}, column {column + 1}"
            if symbol.isascii() and symbol.isalpha():
                if symbol in letters:
                    first = letters[symbol]
                    raise VidgenError(f"map {where}: spot '{symbol}' is already at row {first[0] + 1}, column {first[1] + 1}; "
                                      "each letter marks one spot")
                letters[symbol] = (top_row, column)
                kinds.append(AIR)
            elif symbol in TILE_SYMBOLS:
                kinds.append(TILE_SYMBOLS[symbol])
            else:
                raise VidgenError(f"map {where}: unknown symbol '{symbol}' (symbols: {_SYMBOL_WORDS})")
        cells.append(tuple(kinds))
    cells.reverse()   # row 0 at the bottom
    if all(kind not in STANDABLE for line in cells for kind in line):
        raise VidgenError("the map has nothing to stand on: add ground (#), a platform (=) or a cloud (~)")
    unused = sorted(set(names) - set(letters))
    if unused:
        raise VidgenError(f"spots: letter '{unused[0]}' is not on the map (letters on the map: {', '.join(letters) or 'none'})")
    level = Level(tuple(cells))
    spots: list[Spot] = []
    seen: dict[str, str] = {}
    for letter, (top_row, column) in letters.items():
        name = names.get(letter, letter)
        if name in seen:
            raise VidgenError(f"spots: '{name}' names both '{seen[name]}' and '{letter}'; give each spot its own name")
        seen[name] = letter
        row = len(lines) - 1 - top_row
        y = level.surface_below(column, row)
        if y is None:
            raise VidgenError(f"map row {top_row + 1}, column {column + 1}: spot '{name}' has nothing below it to stand on; "
                              "put ground (#), a platform (=) or a cloud (~) under it")
        spots.append(Spot(name, letter, column, row, column + 0.5, y))
    return Level(level.cells, tuple(spots))


__all__ = [
    "AIR",
    "CLOUD",
    "GROUND",
    "LADDER",
    "MAX_COLUMNS",
    "MAX_ROWS",
    "PLATFORM",
    "STANDABLE",
    "TILE_SYMBOLS",
    "Level",
    "Run",
    "Spot",
    "parse_level",
]
