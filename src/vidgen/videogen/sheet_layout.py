"""A shot's stylesheet composed from its subjects' panels (``generated_shot.subjects``, DESIGN.md §113.24).

One picture at the clip's size, black background, no text: the panels laid out in the grid of
columns x rows that shows them largest (each panel scaled to fit its cell, never cropped, centred),
:data:`GAP` black pixels around each cell, filled row by row. The sheet's prompt names each panel by
its place in that grid, in the format of a hand-made sheet's ``sheet_prompt:`` ("top left, ...; top
right, ..."). Free and local (Pillow); the same panels give the same bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vidgen.config import MAX_SHEET_PANELS
from vidgen.errors import VidgenError

#: Black pixels between the cells and around the sheet's edge.
GAP = 4
#: Words for a cell's column (by the number of columns) and row (by the number of rows).
_COLUMNS: dict[int, tuple[str, ...]] = {1: ("",), 2: ("left", "right"), 3: ("left", "centre", "right"),
                                        4: ("far left", "centre left", "centre right", "far right")}
_ROWS: dict[int, tuple[str, ...]] = {1: ("",), 2: ("top", "bottom"), 3: ("top", "middle", "bottom"),
                                     4: ("top", "upper middle", "lower middle", "bottom")}


@dataclass(frozen=True)
class SheetPanel:
    """A panel to place: its picture file and what it shows (the ``sheet_prompt`` words)."""

    path: Path
    words: str


def _fit(size: tuple[int, int], box: tuple[int, int]) -> tuple[int, int]:
    """``size`` scaled to fit inside ``box`` (aspect kept, at least 1 x 1)."""
    scale = min(box[0] / size[0], box[1] / size[1])
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def cell_size(width: int, height: int, columns: int, rows: int) -> tuple[int, int]:
    """The size of one cell of a ``columns`` x ``rows`` grid on a ``width`` x ``height`` sheet."""
    return (width - GAP * (columns + 1)) // columns, (height - GAP * (rows + 1)) // rows


def choose_grid(width: int, height: int, sizes: Sequence[tuple[int, int]]) -> tuple[int, int]:
    """``(columns, rows)`` that shows panels of ``sizes`` largest on a ``width`` x ``height`` sheet
    (the smallest panel's area decides; ties: fewer empty cells, then fewer columns)."""
    count = len(sizes)
    if not 1 <= count <= MAX_SHEET_PANELS:
        raise VidgenError(f"a sheet holds 1-{MAX_SHEET_PANELS} panels, not {count}")
    best: tuple[tuple[int, int, int], tuple[int, int]] | None = None
    for columns in range(1, count + 1):
        rows = -(-count // columns)
        cell = cell_size(width, height, columns, rows)
        if cell[0] < 1 or cell[1] < 1:
            continue
        smallest = min(w * h for w, h in (_fit(s, cell) for s in sizes))
        score = (smallest, -(columns * rows - count), -columns)
        if best is None or score > best[0]:
            best = (score, (columns, rows))
    if best is None:
        raise VidgenError(f"a {width}x{height} sheet is too small for {count} panels")
    return best[1]


def place_words(columns: int, rows: int, index: int) -> str:
    """Where cell ``index`` (row by row) is: "top left", "right", "bottom", or "the whole sheet"."""
    row, column = divmod(index, columns)
    words = " ".join(w for w in (_ROWS[rows][row], _COLUMNS[columns][column]) if w)
    return words or "the whole sheet"


def sheet_prompt(panels: Sequence[SheetPanel], columns: int, rows: int) -> str:
    """``"top left, <words>; top right, <words>"``: each panel by its place."""
    return "; ".join(f"{place_words(columns, rows, k)}, {p.words}" for k, p in enumerate(panels))


def compose_sheet(panels: Sequence[SheetPanel], width: int, height: int, dest: Path) -> tuple[int, int]:
    """Write ``dest``: the panels on black at ``width`` x ``height`` (:func:`choose_grid`); returns ``(columns, rows)``."""
    from PIL import Image

    pictures = []
    for panel in panels:
        try:
            with Image.open(panel.path) as opened:
                pictures.append(opened.convert("RGB"))
        except OSError as exc:
            raise VidgenError(f"cannot read the panel {panel.path}: {exc}") from None
    columns, rows = choose_grid(width, height, [p.size for p in pictures])
    cell_w, cell_h = cell_size(width, height, columns, rows)
    sheet = Image.new("RGB", (width, height), (0, 0, 0))
    for k, picture in enumerate(pictures):
        row, column = divmod(k, columns)
        size = _fit(picture.size, (cell_w, cell_h))
        x = GAP + column * (cell_w + GAP) + (cell_w - size[0]) // 2
        y = GAP + row * (cell_h + GAP) + (cell_h - size[1]) // 2
        sheet.paste(picture.resize(size, Image.LANCZOS), (x, y))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, format="PNG", optimize=False)
    return columns, rows


__all__ = ["GAP", "SheetPanel", "cell_size", "choose_grid", "compose_sheet", "place_words", "sheet_prompt"]
