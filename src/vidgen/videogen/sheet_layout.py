"""A shot's stylesheet composed from its subjects' panels (``generated_shot.subjects``).

One picture at the clip's size, no text: the panels laid out in the grid of columns x rows that
shows them largest (each panel scaled to fit its cell, never cropped, centred), :data:`GAP` pixels
around each cell, filled row by row. The sheet's prompt names each panel by its place in that grid,
in the format of a hand-made sheet's ``sheet_prompt:`` ("top left, ...; top right, ..."). Free and
local (Pillow); the same panels and background give the same bytes.

The background (``sheet_background:``) is black, or a picture put behind the panels
(:func:`on_background`): the black around them (the gaps and each panel's black that touches them)
is replaced. The location's background (:func:`location_background`) is what the Orrery film found
keeps a lit scene lit (the black alone made LTX's clip dark): its panel filling the sheet, blurred,
a little brighter and blended with its own average colour lifted to a mid brightness.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidgen.config import MAX_SHEET_PANELS
from vidgen.errors import VidgenError

#: Black pixels between the cells and around the sheet's edge.
GAP = 4
#: Words for a cell's column (by the number of columns) and row (by the number of rows).
_COLUMNS: dict[int, tuple[str, ...]] = {1: ("",), 2: ("left", "right"), 3: ("left", "centre", "right"),
                                        4: ("far left", "centre left", "centre right", "far right")}
_ROWS: dict[int, tuple[str, ...]] = {1: ("",), 2: ("top", "bottom"), 3: ("top", "middle", "bottom"),
                                     4: ("top", "upper middle", "lower middle", "bottom")}


#: A pixel whose red + green + blue is at most this counts as the black a background replaces.
NEAR_BLACK = 14
#: The location background's blur radius on a sheet whose long side is 768 px (scaled with the sheet).
BLUR_768 = 18
#: The location background's brightness factor after the blur.
LIFT = 1.1
#: How much of the location background is its average colour (lifted to :data:`TINT_LUMA`).
TINT_SHARE = 0.35
#: The brightness (luma, 0-255) the average colour is lifted to (the film's warm tint had about 100).
TINT_LUMA = 100.0
#: Pixels the edge between a panel and the background is softened over.
EDGE_BLUR = 2


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


def _cover(picture: Any, width: int, height: int) -> Any:
    """``picture`` scaled to fill ``width`` x ``height`` (aspect kept, the overhang cut off evenly)."""
    from PIL import Image

    scale = max(width / picture.width, height / picture.height)
    size = max(width, round(picture.width * scale)), max(height, round(picture.height * scale))
    left, top = (size[0] - width) // 2, (size[1] - height) // 2
    return picture.convert("RGB").resize(size, Image.LANCZOS).crop((left, top, left + width, top + height))


def _read(path: Path, what: str) -> Any:
    from PIL import Image

    try:
        with Image.open(path) as opened:
            return opened.convert("RGB")
    except OSError as exc:
        raise VidgenError(f"cannot read the {what} {path}: {exc}") from None


def location_background(path: Path, width: int, height: int) -> Any:
    """The location panel ``path`` as a sheet background: filling the sheet, blurred, x :data:`LIFT`,
    blended :data:`TINT_SHARE` with its average colour lifted to luma :data:`TINT_LUMA` (at least)."""
    from PIL import Image, ImageEnhance, ImageFilter, ImageStat

    room = _cover(_read(path, "location panel"), width, height)
    radius = max(1, round(BLUR_768 * max(width, height) / 768))
    soft = ImageEnhance.Brightness(room.filter(ImageFilter.GaussianBlur(radius))).enhance(LIFT)
    mean = ImageStat.Stat(room).mean
    luma = 0.299 * mean[0] + 0.587 * mean[1] + 0.114 * mean[2]
    gain = max(TINT_LUMA, luma) / max(luma, 1.0)
    tint = tuple(min(255, round(c * gain)) for c in mean)
    return Image.blend(soft, Image.new("RGB", (width, height), tint), TINT_SHARE)


def picture_background(path: Path, width: int, height: int) -> Any:
    """The picture file ``path`` as a sheet background, filling the sheet."""
    return _cover(_read(path, "sheet background picture"), width, height)


def colour_background(colour: str, width: int, height: int) -> Any:
    """A plain ``#rrggbb`` sheet background."""
    from PIL import Image

    return Image.new("RGB", (width, height), tuple(int(colour[k:k + 2], 16) for k in (1, 3, 5)))


def on_background(sheet: Any, background: Any) -> Any:
    """``sheet`` (panels on black, :data:`GAP` black at its corner) with its black around the panels
    (the near-black region joined to the gaps, :data:`NEAR_BLACK`) replaced by ``background``,
    the edge softened over :data:`EDGE_BLUR` px."""
    import numpy as np
    from PIL import Image, ImageFilter
    from scipy import ndimage

    dark = np.asarray(sheet, dtype=np.int32).sum(axis=2) <= NEAR_BLACK
    labels, _ = ndimage.label(dark)
    around = labels == labels[0, 0]
    mask = Image.fromarray(around.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(EDGE_BLUR))
    return Image.composite(background, sheet, mask)


def compose_sheet(panels: Sequence[SheetPanel], width: int, height: int, dest: Path, background: Any = None) -> tuple[int, int]:
    """Write ``dest``: the panels at ``width`` x ``height`` (:func:`choose_grid`) on black, or on
    ``background`` (a picture of that size, :func:`on_background`); returns ``(columns, rows)``."""
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
    if background is not None:
        sheet = on_background(sheet, background)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, format="PNG", optimize=False)
    return columns, rows


__all__ = [
    "BLUR_768", "EDGE_BLUR", "GAP", "LIFT", "NEAR_BLACK", "TINT_LUMA", "TINT_SHARE", "SheetPanel", "cell_size", "choose_grid", "colour_background",
    "compose_sheet", "location_background", "on_background", "picture_background", "place_words", "sheet_prompt",
]
