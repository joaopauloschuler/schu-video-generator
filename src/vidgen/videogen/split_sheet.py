"""Cut a style sheet picture into named panels (DESIGN.md §113.16): ``vidgen split-sheet``.

Free and local (ffmpeg, like the owner's first cut: ``crop``, then ``scale`` with ``flags=lanczos``;
the same filters give the same pixels). The panels go into a folder of PNGs, by a grid of equal
panels with a gap between them, or by explicit pixel boxes; each may be enlarged so the crops are
large enough to use as references.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vidgen.errors import VidgenError

#: A panel name: letters, digits, ``_`` and ``-`` (it becomes a file name).
_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class SplitPanel:
    """A panel written: its name, file, ``(x, y, width, height)`` box of the sheet and pixel size."""

    name: str
    path: Path
    box: tuple[int, int, int, int]
    size: tuple[int, int]


def parse_box(text: str) -> tuple[int, int, int, int]:
    """``X,Y,W,H`` in pixels. Raises :class:`VidgenError` when it is not four whole numbers."""
    parts = text.replace(" ", "").split(",")
    try:
        x, y, width, height = (int(p) for p in parts)
    except ValueError:
        raise VidgenError(f"--box {text!r} is not X,Y,WIDTH,HEIGHT in whole pixels") from None
    if width <= 0 or height <= 0:
        raise VidgenError(f"--box {text!r}: width and height must be positive")
    return x, y, width, height


def grid_boxes(sheet_width: int, sheet_height: int, columns: int, rows: int, gap: int) -> list[tuple[int, int, int, int]]:
    """Equal panels in reading order, ``gap`` pixels apart. Refuses a sheet that does not divide
    into whole pixels (the gap is probably wrong)."""
    if columns < 1 or rows < 1:
        raise VidgenError("--columns and --rows must be at least 1")
    if gap < 0:
        raise VidgenError("--gap must not be negative")
    width = (sheet_width - gap * (columns - 1)) / columns
    height = (sheet_height - gap * (rows - 1)) / rows
    if width < 1 or height < 1 or width != int(width) or height != int(height):
        raise VidgenError(
            f"the sheet is {sheet_width}x{sheet_height}: with {columns} column(s), {rows} row(s) and a gap of {gap} px the panels are "
            f"{width:g}x{height:g} px, not whole pixels. Check the gap, or give the panels explicitly with --box X,Y,W,H"
        )
    panel_width, panel_height = int(width), int(height)
    return [(c * (panel_width + gap), r * (panel_height + gap), panel_width, panel_height) for r in range(rows) for c in range(columns)]


def _names(names: Sequence[str] | None, count: int) -> list[str]:
    if names is None:
        return [f"panel{n}" for n in range(1, count + 1)]
    found = [n.strip() for n in names]
    if len(found) != count:
        raise VidgenError(f"--names gives {len(found)} name(s) for {count} panel(s)")
    if len(set(found)) != len(found):
        raise VidgenError("--names: the panel names must differ")
    bad = [n for n in found if not _NAME.match(n)]
    if bad:
        raise VidgenError(f"--names: {bad[0]!r} is not a file name (use letters, digits, _ and -)")
    return found


def split_sheet(
    picture: Path, *, out_dir: Path | None = None, names: Sequence[str] | None = None, columns: int | None = None, rows: int | None = None,
    gap: int = 0, boxes: Sequence[str] | None = None, scale: float = 1.0,
) -> list[SplitPanel]:
    """Write the panels of ``picture`` as ``<out_dir>/<name>.png`` (default folder:
    ``<sheet name>_panels`` beside the picture) and return them. A grid needs ``columns`` (and
    ``rows``, default 1); ``boxes`` (``X,Y,W,H`` texts) replace it. Raises :class:`VidgenError`
    for an unreadable picture, a box off the picture, or names that do not fit the panels."""
    from PIL import Image, UnidentifiedImageError

    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    if boxes and (columns is not None or rows is not None or gap):
        raise VidgenError("give either --box or --columns / --rows / --gap, not both")
    if not boxes and columns is None and rows is None:
        raise VidgenError("say how to cut the sheet: --columns N [--rows N] [--gap PX], or --box X,Y,W,H for each panel")
    if not scale > 0:
        raise VidgenError(f"--scale must be above 0, not {scale:g}")
    if not picture.is_file():
        raise VidgenError(f"no picture {picture}")
    try:
        with Image.open(picture) as opened:
            width, height = opened.size
    except (UnidentifiedImageError, OSError) as exc:
        raise VidgenError(f"cannot read the picture {picture}: {exc}") from None
    if boxes:
        found = [parse_box(text) for text in boxes]
        for box in found:
            x, y, w, h = box
            if x < 0 or y < 0 or x + w > width or y + h > height:
                raise VidgenError(f"--box {','.join(map(str, box))} is not inside the {width}x{height} picture")
    else:
        found = grid_boxes(width, height, columns or 1, rows or 1, gap)
    panel_names = _names(names, len(found))
    folder = out_dir if out_dir is not None else picture.parent / f"{picture.stem}_panels"
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    panels: list[SplitPanel] = []
    for name, box in zip(panel_names, found):
        x, y, w, h = box
        size = (round(w * scale), round(h * scale))
        graph = f"crop={w}:{h}:{x}:{y}" + (f",scale={size[0]}:{size[1]}:flags=lanczos" if scale != 1.0 else "")
        path = folder / f"{name}.png"
        run_ffmpeg(ffmpeg, ["-i", str(picture), "-vf", graph, "-frames:v", "1", str(path)], f"cutting panel {name} of {picture.name}")
        panels.append(SplitPanel(name, path, box, size))
    return panels


__all__ = ["SplitPanel", "grid_boxes", "parse_box", "split_sheet"]
