"""Isometric places written as a small ASCII map with heights (DESIGN.md §89). Plain data, no manim.

An *iso place* is a grid of *cells* seen from above at an angle: the map is written as the place
is seen, one text line per row, the top line furthest back. A cell spans ``column .. column + 1``
in world ``x`` and ``row .. row + 1`` in world ``y`` (rows count from the map's top line, so ``y``
grows towards the viewer's lower left and ``x`` towards the lower right); ``z`` is up. All three
are in *tile units* (a cell's edge is 1); heights on the map are in *steps* of :data:`STEP_HEIGHT`.

Symbols are ground, walls and the place's many unnamed things (trees, bushes, flowers, fences);
letters are *spots*: named cells that characters and objects stand at. A letter cell takes the
ground and height of the cells around it (a spot on a path is path, on a raised terrace raised).
Ready-made objects that a story names (a house, a well, a bench) are placed by name at a spot
(:func:`place_objects`). Messages name cells as the author wrote them: rows from the top line,
columns from the left, both from 1.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace

from vidgen.errors import VidgenError

#: A place's two kinds: outdoors (grass, paths, water, garden walls) and indoors (a room whose
#: back walls stand and whose front walls are cut away, DESIGN.md §89.4).
OUTDOOR = "outdoor"
INDOOR = "indoor"
PLACES: tuple[str, ...] = (OUTDOOR, INDOOR)

VOID = "void"
FLOOR = "floor"
PATH = "path"
BLOCK = "block"
WATER = "water"
WALL = "wall"
DOOR = "door"
WINDOW = "window"
#: Map symbol -> ground kind. A space or ``-`` is outside the place (``-`` where a YAML block
#: cannot start a line with a space); a digit is a raised :data:`BLOCK` that many steps high.
GROUND_SYMBOLS: dict[str, str] = {" ": VOID, "-": VOID, ".": FLOOR, ":": PATH, "~": WATER, "#": WALL, "+": DOOR, "%": WINDOW}
#: Map symbol -> a ready-made object standing in that cell (named ``tree_1``, ``tree_2``... in map order).
OBJECT_SYMBOLS: dict[str, str] = {"@": "tree", "&": "bush", "*": "flowers", "=": "fence"}
#: The ground kinds walls are made of (a door is a way through, a window a wall).
WALLS: frozenset[str] = frozenset({WALL, DOOR, WINDOW})
#: The ground kinds one can stand on.
STANDABLE: frozenset[str] = frozenset({FLOOR, PATH, BLOCK, DOOR})
_SYMBOL_WORDS = ("space or -: outside, . floor (grass outdoors), : path, ~ water, # wall, + door, % window, 1-9 a block that many "
                 "steps high, @ tree, & bush, * flowers, = fence, a letter: a spot")

#: The height of one step on the map (tile units): a digit ``3`` is a block 1.5 tiles high.
STEP_HEIGHT = 0.5
#: How tall a character of scale 1 stands (tile units).
ISO_CHARACTER_HEIGHT = 2.0
#: Walls (tile units): a room's standing back walls, its cut-away walls, a garden wall outdoors;
#: a door's opening in a standing wall.
WALL_HEIGHT = 3.0
CUT_WALL_HEIGHT = 0.45
GARDEN_WALL_HEIGHT = 1.0
DOOR_HEIGHT = 2.5
#: The largest map: wider or deeper maps are refused (the place would be too small to read).
MAX_COLUMNS = 48
MAX_ROWS = 48


@dataclass(frozen=True)
class ObjectKind:
    """A ready-made object: its footprint (``width`` columns by ``depth`` rows when facing left),
    its height (tile units), whether one can walk on it (a rug, a bridge; ``deck``: how high
    over its base the feet stand on it) and the ground it may stand on (``water``: a bridge spans it); ``top``: how high over its base a
    small thing put on it stands (a table's top, a bench's seat; ``None``: nothing goes on it,
    DESIGN.md §89.10)."""

    width: int
    depth: int
    height: float
    walkable: bool = False
    over_water: bool = False
    deck: float = 0.0
    top: float | None = None


#: The ready-made objects (DESIGN.md §89.5).
OBJECT_KINDS: dict[str, ObjectKind] = {
    "house": ObjectKind(3, 3, 4.6),
    "tree": ObjectKind(1, 1, 4.0),
    "pine": ObjectKind(1, 1, 4.2),
    "bush": ObjectKind(1, 1, 1.1),
    "rock": ObjectKind(1, 1, 0.8, top=0.5),
    "flowers": ObjectKind(1, 1, 0.6),
    "fence": ObjectKind(1, 1, 1.0),
    "bench": ObjectKind(2, 1, 1.1, top=0.55),
    "lamp": ObjectKind(1, 1, 3.4),
    "well": ObjectKind(1, 1, 2.9, top=0.85),
    "sign": ObjectKind(1, 1, 1.7),
    "bridge": ObjectKind(1, 3, 0.35, walkable=True, over_water=True, deck=0.22),
    "table": ObjectKind(2, 1, 1.0, top=0.98),
    "chair": ObjectKind(1, 1, 1.3, top=0.63),
    "bed": ObjectKind(1, 2, 1.0, top=0.58),
    "shelf": ObjectKind(1, 2, 2.5, top=2.4),
    "sofa": ObjectKind(2, 1, 1.15, top=0.55),
    "plant": ObjectKind(1, 1, 1.5),
    "rug": ObjectKind(2, 2, 0.03, walkable=True, deck=0.02),
    # a lab and a memory's props (DESIGN.md §100.11)
    "console": ObjectKind(2, 1, 1.8, top=0.86),
    "server_rack": ObjectKind(1, 1, 2.6),
    "projector_pad": ObjectKind(1, 1, 0.13, walkable=True, deck=0.12),
    "whiteboard": ObjectKind(2, 1, 2.1),
    "flower_arch": ObjectKind(2, 1, 3.2),
    "chess_table": ObjectKind(1, 1, 0.96, top=0.86),
    # a city's tall buildings (DESIGN.md §102.2): its height is the placing's own
    "tower": ObjectKind(2, 2, 9.0),
    # more lab and sci-fi objects (DESIGN.md §103): a wall_clock hangs on a room's back wall (its cell is the wall's)
    "laptop": ObjectKind(1, 1, 1.25),
    "terminal_kiosk": ObjectKind(1, 1, 2.0),
    "quantum_core": ObjectKind(1, 1, 2.0),
    "robot_arm": ObjectKind(1, 1, 1.5),
    "microscope": ObjectKind(1, 1, 1.6),
    "centrifuge": ObjectKind(1, 1, 1.2),
    "coffee_machine": ObjectKind(1, 1, 1.65),
    "lab_stool": ObjectKind(1, 1, 0.75, top=0.72),
    "wall_clock": ObjectKind(1, 1, 2.65),
    "grow_rack": ObjectKind(1, 1, 2.4),
    "terrarium": ObjectKind(1, 1, 1.55),
    "specimen_tank": ObjectKind(1, 1, 2.45),
    "chemistry_bench": ObjectKind(2, 1, 1.45),
    "distillation_rig": ObjectKind(1, 1, 1.9),
    "lab_fridge": ObjectKind(1, 1, 2.3),
    "fume_hood": ObjectKind(1, 1, 2.5),
    "telescope": ObjectKind(1, 1, 1.85),
    "satellite_dish": ObjectKind(1, 1, 2.0),
    "charging_station": ObjectKind(1, 1, 1.8),
    "crate_stack": ObjectKind(1, 1, 1.32, top=1.32),
    "airlock": ObjectKind(2, 1, 2.5),
    "printer_3d": ObjectKind(1, 1, 1.8),
    "hazard_sign": ObjectKind(1, 1, 1.65),
    "fire_extinguisher": ObjectKind(1, 1, 0.85),
    # home objects (DESIGN.md §104)
    "fireplace": ObjectKind(2, 1, 2.4),
    "kitchen_counter": ObjectKind(2, 1, 1.2, top=0.96),
    "stove": ObjectKind(1, 1, 1.25),
    "sink": ObjectKind(1, 1, 1.32),
    "bookshelf_tall": ObjectKind(1, 1, 2.55, top=2.55),
    "armchair": ObjectKind(1, 1, 1.2, top=0.58),
    "floor_lamp": ObjectKind(1, 1, 2.05),
    "tv": ObjectKind(1, 1, 1.48),
    "piano": ObjectKind(2, 1, 1.66, top=1.66),
    # home II, café and shop objects (§104)
    "bathtub": ObjectKind(2, 1, 1.15),
    "wardrobe": ObjectKind(2, 1, 2.42, top=2.42),
    "crib": ObjectKind(1, 1, 1.85),
    "cafe_table": ObjectKind(2, 1, 1.3, top=0.94),
    "counter": ObjectKind(2, 1, 1.25, top=1.12),
    "cash_register": ObjectKind(1, 1, 1.8),
    "display_case": ObjectKind(2, 1, 1.4, top=1.4),
    "market_stall": ObjectKind(2, 1, 2.66),
    "vending_machine": ObjectKind(1, 1, 2.15),
    # town objects (§104)
    "street_lamp": ObjectKind(1, 1, 4.0),
    "traffic_light": ObjectKind(1, 1, 3.15),
    "bus_stop": ObjectKind(2, 1, 2.9),
    "mailbox": ObjectKind(1, 1, 1.52),
    "fountain": ObjectKind(2, 2, 2.6),
    "phone_booth": ObjectKind(1, 1, 2.65),
    "car": ObjectKind(2, 1, 1.32),
    "bicycle": ObjectKind(1, 1, 1.0),
    "newsstand": ObjectKind(2, 1, 2.45),
}
#: The objects whose ``height`` a placing may give (tile units, from .. to), DESIGN.md §102.2.
TALL_KINDS: dict[str, tuple[float, float]] = {"tower": (2.0, 30.0)}
#: Extras an object of a kind may have (``features`` of a placing), DESIGN.md §102.2: a tower's
#: big info ``screen`` on its front and its glowing algae-farm bands (``garden``); a hazard sign's
#: kind (one of them, §103; default ``biohazard``).
HAZARD_SIGNS: tuple[str, ...] = ("biohazard", "radiation", "authorised")
#: A display case's kinds (§104; default ``cakes``).
DISPLAY_CASES: tuple[str, ...] = ("cakes", "jewels")
#: The objects with a ``kind`` (one of these, the first the default): a hazard sign, a display case.
OBJECT_STYLES: dict[str, tuple[str, ...]] = {"hazard_sign": HAZARD_SIGNS, "display_case": DISPLAY_CASES}
OBJECT_FEATURES: dict[str, tuple[str, ...]] = {"tower": ("screen", "garden"), **OBJECT_STYLES}


#: The kinds of things that open (DESIGN.md §89.10): a house's door, flowers (closed: buds), and
#: a ``door`` of the map in a room's standing wall; and those that switch on: a lamp, a house's windows.
OPENING_KINDS: frozenset[str] = frozenset({"house", "flowers", "door", "laptop", "lab_fridge", "airlock", "wardrobe"})
SWITCHED_KINDS: frozenset[str] = frozenset({"house", "lamp", "tower", "laptop", "terminal_kiosk", "quantum_core", "robot_arm", "centrifuge",
                                            "coffee_machine", "grow_rack", "specimen_tank", "chemistry_bench", "distillation_rig",
                                            "lab_fridge", "fume_hood", "satellite_dish", "charging_station", "airlock", "printer_3d",
                                            "fireplace", "stove", "floor_lamp", "tv", "vending_machine", "street_lamp", "traffic_light",
                                            "fountain", "phone_booth", "car"})
#: The objects that hang on a room's standing wall: placed at the wall's cell (DESIGN.md §103).
WALL_KINDS: frozenset[str] = frozenset({"wall_clock"})


@dataclass(frozen=True)
class ObjectState:
    """What an object of the place shows now (DESIGN.md §89.10): whether it is there
    (``shown``), open (a house's or a room's door; flowers in bloom, else in bud) and on (a lamp
    lit; a house's windows lit)."""

    shown: bool = True
    open: bool = False
    on: bool = False


def default_state(kind: str) -> ObjectState:
    """The state of an object of ``kind`` unless the scene says otherwise: there, closed and off;
    flowers in bloom; a laptop open; a tower's windows lit (§102.2)."""
    return ObjectState(open=kind in ("flowers", "laptop"), on=kind == "tower")


@dataclass(frozen=True)
class IsoCell:
    """One cell: its ground kind and its height in steps (:data:`STEP_HEIGHT` each)."""

    ground: str
    steps: int = 0


@dataclass(frozen=True)
class IsoSpot:
    """A named cell: its map ``letter`` and cell (``column``, ``row`` from the map's top line,
    both from 0)."""

    name: str
    letter: str
    column: int
    row: int


@dataclass(frozen=True)
class IsoObject:
    """A ready-made object standing in the place: its ``name`` and ``kind``, its footprint from
    its back cell (``column``, ``row``: the map's top-left cell of it) ``width`` columns by
    ``depth`` rows, its ``height`` (tile units), which way its front faces (``left``: towards the
    viewer's lower left, ``right``: lower right) and, for a fence, the sides it joins its
    neighbours on (``n``, ``e``, ``s``, ``w``)."""

    name: str
    kind: str
    column: int
    row: int
    width: int
    depth: int
    height: float
    facing: str = "left"
    links: tuple[str, ...] = ()
    color: str | None = None
    detail: str | None = None
    #: its extras (:data:`OBJECT_FEATURES`: a tower's ``screen``, ``garden``)
    features: tuple[str, ...] = ()
    #: a wall_clock's time (``"HH:MM"``; ``None``: ten past ten)
    time: str | None = None

    def cells(self) -> list[tuple[int, int]]:
        """The cells it stands on, back to front."""
        return [(c, r) for r in range(self.row, self.row + self.depth) for c in range(self.column, self.column + self.width)]

    @property
    def walkable(self) -> bool:
        return OBJECT_KINDS[self.kind].walkable


@dataclass(frozen=True)
class ObjectPlacing:
    """An object a scene asks for: its kind, where (a spot's name, or a cell ``(column, row)``
    as the author reads the map: from the top left, from 1), its own name, facing, footprint
    (``size``: columns by rows, ``None``: the kind's), colours (theme tokens or ``#hex``), its
    ``height`` (tile units; :data:`TALL_KINDS` only, ``None``: the kind's) and its extras
    (``features``, :data:`OBJECT_FEATURES`)."""

    kind: str
    at: str | tuple[int, int]
    name: str | None = None
    facing: str = "left"
    size: tuple[int, int] | None = None
    color: str | None = None
    detail: str | None = None
    height: float | None = None
    features: tuple[str, ...] = ()
    time: str | None = None


@dataclass(frozen=True)
class IsoPlace:
    """A parsed place: ``cells[row][column]`` (row 0 the map's top line), whether it is indoors,
    its spots and its objects (the map's trees, bushes, flowers and fences, then the placed ones)."""

    cells: tuple[tuple[IsoCell, ...], ...]
    indoor: bool = False
    spots: tuple[IsoSpot, ...] = ()
    objects: tuple[IsoObject, ...] = ()
    _occupied: dict[tuple[int, int], str] = field(default_factory=dict, compare=False, repr=False)

    @property
    def columns(self) -> int:
        return len(self.cells[0]) if self.cells else 0

    @property
    def rows(self) -> int:
        return len(self.cells)

    def cell(self, column: int, row: int) -> IsoCell:
        """The cell at (``column``, ``row``); outside the map: :data:`VOID`."""
        if 0 <= row < self.rows and 0 <= column < self.columns:
            return self.cells[row][column]
        return IsoCell(VOID)

    def ground(self, column: int, row: int) -> str:
        return self.cell(column, row).ground

    def floor_z(self, column: int, row: int) -> float:
        """The height (tile units) of the cell's top: where something standing there has its feet
        (a wall's base for a wall)."""
        return self.cell(column, row).steps * STEP_HEIGHT

    def stand_z(self, column: int, row: int) -> float:
        """The height (tile units) of the feet of someone standing on the cell: its top, or the
        deck of a walkable object on it (a bridge's planks)."""
        item = self.object_at(column, row)
        deck = OBJECT_KINDS[item.kind].deck if item is not None and item.walkable else 0.0
        return self.floor_z(column, row) + deck

    def without(self, names: Collection[str]) -> "IsoPlace":
        """The place without the objects ``names`` (not there now: they appear later, or have
        gone; DESIGN.md §89.10): one walks where they would stand, and not over a bridge that is
        not there."""
        if not names:
            return self
        gone = set(names)
        occupied = {cell: name for cell, name in self._occupied.items() if name not in gone}
        return IsoPlace(self.cells, self.indoor, self.spots, tuple(o for o in self.objects if o.name not in gone), occupied)

    def doors(self) -> list[tuple[str, int, int]]:
        """The doors of the map that can open and close: each ``+`` in a room's standing wall (a
        door drawn on it), named ``door_1``, ``door_2``... in map order, with its cell. A doorway
        in a cut-away wall and a gap in a garden wall are ways through with no door."""
        found = []
        for r in range(self.rows):
            for c in range(self.columns):
                if self.ground(c, r) == DOOR and self.indoor and not self.is_cut(c, r):
                    found.append((f"door_{len(found) + 1}", c, r))
        return found

    def object_at(self, column: int, row: int) -> IsoObject | None:
        """The object standing on the cell (``None``: none)."""
        name = self._occupied.get((column, row))
        return None if name is None else self.object(name)

    def object(self, name: str) -> IsoObject:
        for item in self.objects:
            if item.name == name:
                return item
        raise VidgenError(f"the place has no object '{name}' (objects: {', '.join(o.name for o in self.objects) or 'none'})")

    def is_standable(self, column: int, row: int) -> bool:
        """Whether one can stand on the cell: standable ground with nothing on it but a walkable
        object (a rug, a bridge; a bridge also over water)."""
        item = self.object_at(column, row)
        if item is not None:
            return item.walkable
        return self.ground(column, row) in STANDABLE

    def wall_height(self, column: int, row: int) -> float:
        """How high the wall in the cell stands over its base (tile units; 0: no wall, or a cut
        doorway): outdoors a garden wall; indoors a standing back wall, or a cut-away wall
        (:meth:`is_cut`)."""
        ground = self.ground(column, row)
        if ground not in WALLS:
            return 0.0
        if not self.indoor:
            return 0.0 if ground == DOOR else GARDEN_WALL_HEIGHT
        if self.is_cut(column, row):
            return 0.0 if ground == DOOR else CUT_WALL_HEIGHT
        return WALL_HEIGHT

    def is_cut(self, column: int, row: int) -> bool:
        """Indoors, whether the wall in the cell is cut away: it would hide the room behind it
        (a cell of the place that is not a wall is right behind it, to its left, top or top
        left on the map). Only the walls along the room's back stand (DESIGN.md §89.4)."""
        if not self.indoor or self.ground(column, row) not in WALLS:
            return False
        behind = ((column - 1, row), (column, row - 1), (column - 1, row - 1))
        return any(self.ground(c, r) not in WALLS and self.ground(c, r) != VOID for c, r in behind)

    def spot(self, name: str) -> IsoSpot:
        """The spot named ``name``; :class:`VidgenError` listing the spots when there is none."""
        for spot in self.spots:
            if spot.name == name:
                return spot
        known = ", ".join(s.name for s in self.spots) or "none"
        raise VidgenError(f"the place has no spot '{name}' (spots: {known})")

    def spot_names(self) -> list[str]:
        return [spot.name for spot in self.spots]

    def stand_cell(self, name: str) -> tuple[int, int]:
        """Where a character asked to stand at the spot ``name`` stands: the spot's cell, or, when
        an object stands there (a well, a bench), the nearest free cell in front of it."""
        spot = self.spot(name)
        if self.is_standable(spot.column, spot.row):
            return spot.column, spot.row
        found = self.free_cell_near(spot.column, spot.row)
        if found is None:
            raise VidgenError(f"spot '{name}': there is no free cell to stand on next to it")
        return found

    def free_cell_near(self, column: int, row: int) -> tuple[int, int] | None:
        """The free standable cell nearest to (``column``, ``row``), counted in cells across
        (8 neighbours); between equals the one most in front (the viewer's side), then the
        leftmost. ``None``: none in the place."""
        best: tuple[tuple[int, int, int], tuple[int, int]] | None = None
        for r in range(self.rows):
            for c in range(self.columns):
                if (c, r) == (column, row) or not self.is_standable(c, r):
                    continue
                key = (max(abs(c - column), abs(r - row)), -(c + r), c)
                if best is None or key < best[0]:
                    best = (key, (c, r))
        return None if best is None else best[1]


def _map_lines(text: str, what: str = "map") -> list[str]:
    """The map's rows as written, without the blank lines around it (a line of only spaces
    counts as blank), padded with spaces (outside the place) on the right to the longest row."""
    lines = text.expandtabs(4).splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise VidgenError(f"the {what} is empty: write one line per row, e.g. '..a..' over '.....'")
    width = max(len(line.rstrip()) for line in lines)
    return [line.rstrip().ljust(width) for line in lines]


def _heights(text: str | None, rows: int, columns: int) -> list[list[int | None]]:
    """The ``heights`` map's steps per cell (``None``: not given there)."""
    found: list[list[int | None]] = [[None] * columns for _ in range(rows)]
    if text is None:
        return found
    lines = _map_lines(text, "heights map")
    if len(lines) > rows or len(lines[0]) > columns:
        raise VidgenError(f"heights: the heights map is {len(lines[0])} columns by {len(lines)} rows, larger than the map "
                          f"({columns} by {rows}); write one digit per cell of the map")
    for r, line in enumerate(lines):
        for c, symbol in enumerate(line):
            if symbol.isdigit():
                found[r][c] = int(symbol)
            elif symbol not in ". ":
                raise VidgenError(f"heights row {r + 1}, column {c + 1}: '{symbol}' is not a height; write a digit 0-9 "
                                  "(steps) or . (the map's own)")
    return found


def _inherited(raw: list[list[IsoCell | None]], column: int, row: int) -> IsoCell:
    """The ground a letter or an object symbol stands on: the most common standable ground
    (with its height) of its four neighbours; between equals the lower, then floor before path
    before block; none: floor at height 0."""
    around = []
    for c, r in ((column - 1, row), (column, row - 1), (column + 1, row), (column, row + 1)):
        if 0 <= r < len(raw) and 0 <= c < len(raw[0]):
            cell = raw[r][c]
            if cell is not None and cell.ground in (FLOOR, PATH, BLOCK):
                around.append(cell)
    if not around:
        return IsoCell(FLOOR)
    order = {FLOOR: 0, PATH: 1, BLOCK: 2}
    counts = Counter(around)
    return min(counts, key=lambda cell: (-counts[cell], cell.steps, order[cell.ground]))


def _fence_links(lines: list[str], column: int, row: int) -> tuple[str, ...]:
    """The sides a fence in a cell joins its neighbours on: fences and walls next to it; a fence
    with none runs left to right on the map."""
    links = []
    for side, (c, r) in (("n", (column, row - 1)), ("e", (column + 1, row)), ("s", (column, row + 1)), ("w", (column - 1, row))):
        if 0 <= r < len(lines) and 0 <= c < len(lines[0]) and lines[r][c] in "=#%+":
            links.append(side)
    return tuple(links) or ("e", "w")


def parse_iso_map(text: str, *, names: Mapping[str, str] | None = None, heights: str | None = None,
                  place: str = OUTDOOR) -> IsoPlace:
    """An :class:`IsoPlace` from its ASCII ``text`` (the top line furthest back), ``names`` (map
    letter -> the spot's name; a letter without one is named by itself), an optional ``heights``
    map (a digit per cell: its height in steps) and the kind of ``place``. Raises
    :class:`VidgenError` naming the row and column (from the top left, from 1) of the first problem."""
    if place not in PLACES:
        raise VidgenError(f"place: '{place}' is not a kind of place (outdoor, indoor)")
    names = dict(names or {})
    lines = _map_lines(text)
    if len(lines) > MAX_ROWS:
        raise VidgenError(f"the map has {len(lines)} rows; at most {MAX_ROWS}")
    if len(lines[0]) > MAX_COLUMNS:
        raise VidgenError(f"the map is {len(lines[0])} columns wide; at most {MAX_COLUMNS}")
    rows, columns = len(lines), len(lines[0])
    raw: list[list[IsoCell | None]] = [[None] * columns for _ in range(rows)]
    letters: dict[str, tuple[int, int]] = {}
    symbols: list[tuple[str, int, int]] = []
    for r, line in enumerate(lines):
        for c, symbol in enumerate(line):
            where = f"map row {r + 1}, column {c + 1}"
            if symbol.isascii() and symbol.isalpha():
                if symbol in letters:
                    first = letters[symbol]
                    raise VidgenError(f"{where}: spot '{symbol}' is already at row {first[1] + 1}, column {first[0] + 1}; "
                                      "each letter marks one spot")
                letters[symbol] = (c, r)
            elif symbol in OBJECT_SYMBOLS:
                symbols.append((OBJECT_SYMBOLS[symbol], c, r))
            elif symbol.isdigit() and symbol != "0":
                raw[r][c] = IsoCell(BLOCK, int(symbol))
            elif symbol in GROUND_SYMBOLS or symbol == "0":
                raw[r][c] = IsoCell(GROUND_SYMBOLS.get(symbol, FLOOR))
            else:
                raise VidgenError(f"{where}: unknown symbol '{symbol}' (symbols: {_SYMBOL_WORDS})")
    unused = sorted(set(names) - set(letters))
    if unused:
        raise VidgenError(f"spots: letter '{unused[0]}' is not on the map (letters on the map: {', '.join(letters) or 'none'})")
    given = _heights(heights, rows, columns)
    cells: list[list[IsoCell]] = []
    for r in range(rows):
        row_cells = []
        for c in range(columns):
            cell = raw[r][c] if raw[r][c] is not None else _inherited(raw, c, r)
            steps = given[r][c]
            if steps is not None and steps != cell.steps:
                if cell.ground == VOID:
                    raise VidgenError(f"heights row {r + 1}, column {c + 1}: the map has nothing there (outside the place)")
                if cell.ground == WATER and steps:
                    raise VidgenError(f"heights row {r + 1}, column {c + 1}: water lies at height 0")
                cell = replace(cell, steps=steps)
            row_cells.append(cell)
        cells.append(row_cells)
    if not any(cell.ground in STANDABLE for line in cells for cell in line):
        raise VidgenError("the map has nowhere to stand: add floor (.), a path (:) or a block (1-9)")
    spots: list[IsoSpot] = []
    seen: dict[str, str] = {}
    for letter, (c, r) in letters.items():
        name = names.get(letter, letter)
        if name in seen:
            raise VidgenError(f"spots: '{name}' names both '{seen[name]}' and '{letter}'; give each spot its own name")
        seen[name] = letter
        spots.append(IsoSpot(name, letter, c, r))
    counts: dict[str, int] = {}
    objects = []
    for kind, c, r in symbols:
        counts[kind] = counts.get(kind, 0) + 1
        sort = OBJECT_KINDS[kind]
        objects.append(IsoObject(f"{kind}_{counts[kind]}", kind, c, r, 1, 1, sort.height,
                                 links=_fence_links(lines, c, r) if kind == "fence" else ()))
    found = IsoPlace(tuple(tuple(line) for line in cells), place == INDOOR, tuple(spots))
    return _with_objects(found, objects)


def _with_objects(place: IsoPlace, objects: Sequence[IsoObject]) -> IsoPlace:
    """``place`` with ``objects`` added, after checking each stands inside the map on ground it
    may stand on and on no other object."""
    occupied = dict(place._occupied)
    taken = {o.name for o in place.objects}
    for item in objects:
        if item.name in taken:
            raise VidgenError(f"objects: the name '{item.name}' is used twice; give each object its own name")
        taken.add(item.name)
        kind = OBJECT_KINDS[item.kind]
        for c, r in item.cells():
            where = f"map row {r + 1}, column {c + 1}"
            ground = place.ground(c, r)
            if ground == VOID:
                raise VidgenError(f"'{item.name}' ({item.width} x {item.depth} cells from map row {item.row + 1}, column "
                                  f"{item.column + 1}) reaches outside the place at {where}")
            if item.kind in WALL_KINDS:
                if ground != WALL or not place.wall_height(c, r) >= WALL_HEIGHT:
                    raise VidgenError(f"'{item.name}' hangs on a room's standing wall: put it at a wall cell (#) of a back wall, not at {where}")
            elif ground in WALLS or (ground == WATER and not kind.over_water):
                raise VidgenError(f"'{item.name}' would stand on {'a wall' if ground in WALLS else 'water'} at {where}; "
                                  "move it, or make it smaller (size)")
            if (c, r) in occupied:
                raise VidgenError(f"'{item.name}' and '{occupied[(c, r)]}' would both stand at {where}; move one of them (its at)")
            if place.cell(c, r).steps != place.cell(item.column, item.row).steps:
                raise VidgenError(f"'{item.name}' would stand on two heights (at {where}); put it on level ground")
            occupied[(c, r)] = item.name
    return IsoPlace(place.cells, place.indoor, place.spots, (*place.objects, *objects), occupied)


def place_objects(place: IsoPlace, placings: Sequence[ObjectPlacing]) -> IsoPlace:
    """``place`` with the ready-made objects of ``placings`` standing in it: each at its spot (the
    footprint's back cell, its top left on the map) or cell, named by its own name or its kind
    numbered after the map's (``house``, ``house_2``). :class:`VidgenError` naming the object and
    the cell for an unknown kind or spot, a footprint outside the place, on a wall, on water (but
    a bridge), on two heights or on another object."""
    counts = Counter(o.kind for o in place.objects)
    added = []
    for k, placing in enumerate(placings):
        kind = OBJECT_KINDS.get(placing.kind)
        if kind is None:
            raise VidgenError(f"objects[{k}]: unknown object '{placing.kind}' (objects: {', '.join(OBJECT_KINDS)})")
        if placing.facing not in ("left", "right"):
            raise VidgenError(f"objects[{k}]: facing is left or right, not '{placing.facing}'")
        if isinstance(placing.at, str):
            spot = place.spot(placing.at)
            column, row = spot.column, spot.row
        else:
            column, row = placing.at[0] - 1, placing.at[1] - 1
        width, depth = placing.size if placing.size is not None else (kind.width, kind.depth)
        facing = _wall_facing(place, placing.kind, column, row, placing.facing) if placing.kind in WALL_KINDS else placing.facing
        if placing.size is None and facing == "right":
            width, depth = depth, width
        if placing.time is not None and placing.kind != "wall_clock":
            raise VidgenError(f"objects[{k}]: time is for a wall_clock, not {placing.kind}")
        if placing.height is not None:
            low, high = TALL_KINDS.get(placing.kind, (None, None))
            if low is None or high is None:
                raise VidgenError(f"objects[{k}]: height is for a {' or '.join(TALL_KINDS)}, not {placing.kind}")
            if not low <= placing.height <= high:
                raise VidgenError(f"objects[{k}]: a {placing.kind}'s height is {low:g} to {high:g} tiles, not {placing.height:g}")
        unknown = [f for f in placing.features if f not in OBJECT_FEATURES.get(placing.kind, ())]
        if unknown:
            allowed = ", ".join(OBJECT_FEATURES.get(placing.kind, ())) or "none"
            raise VidgenError(f"objects[{k}]: {placing.kind} has no {', '.join(unknown)} (its extras: {allowed})")
        counts[placing.kind] += 1
        name = placing.name or (placing.kind if counts[placing.kind] == 1 else f"{placing.kind}_{counts[placing.kind]}")
        added.append(IsoObject(name, placing.kind, column, row, width, depth, kind.height if placing.height is None else float(placing.height),
                               facing, color=placing.color, detail=placing.detail, features=tuple(placing.features), time=placing.time))
    return _with_objects(place, added)


def _wall_facing(place: IsoPlace, kind: str, column: int, row: int, facing: str) -> str:
    """Which way an object hanging on the wall at (``column``, ``row``) faces: into the room in
    front of the wall, ``left`` (the floor below it on the map) or ``right`` (the floor to its
    right); ``facing`` when both are open."""
    def open_(c: int, r: int) -> bool:
        return place.ground(c, r) not in WALLS and place.ground(c, r) != VOID

    below, right = open_(column, row + 1), open_(column + 1, row)
    if below and right:
        return facing
    if below or right:
        return "left" if below else "right"
    raise VidgenError(f"a {kind} at map row {row + 1}, column {column + 1} hangs on a wall with the room's floor below it or to its right "
                      "on the map; put it on such a wall cell")


__all__ = [
    "BLOCK",
    "CUT_WALL_HEIGHT",
    "DOOR",
    "DOOR_HEIGHT",
    "DISPLAY_CASES",
    "FLOOR",
    "GARDEN_WALL_HEIGHT",
    "GROUND_SYMBOLS",
    "HAZARD_SIGNS",
    "INDOOR",
    "ISO_CHARACTER_HEIGHT",
    "MAX_COLUMNS",
    "MAX_ROWS",
    "OBJECT_FEATURES",
    "OBJECT_KINDS",
    "OBJECT_STYLES",
    "OPENING_KINDS",
    "OBJECT_SYMBOLS",
    "OUTDOOR",
    "PATH",
    "PLACES",
    "STANDABLE",
    "STEP_HEIGHT",
    "SWITCHED_KINDS",
    "TALL_KINDS",
    "VOID",
    "WALL",
    "WALLS",
    "WALL_HEIGHT",
    "WALL_KINDS",
    "WATER",
    "WINDOW",
    "IsoCell",
    "IsoObject",
    "IsoPlace",
    "IsoSpot",
    "ObjectKind",
    "ObjectPlacing",
    "ObjectState",
    "default_state",
    "parse_iso_map",
    "place_objects",
]
