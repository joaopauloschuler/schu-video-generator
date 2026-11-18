"""``vidgen parts``: a labelled contact sheet of the ready-made three.js parts (DESIGN.md §122.5).

The parts live in the registry ``vidgen/parts`` (``data/web/modules/parts.js``); each shipped
module describes its own in ``data/web/parts/<module>.js`` with ``definePart(info, make)``, whose
``info`` is JSON so that this module reads it without a browser (:func:`read_parts`,
``vidgen parts --list``). The sheet is drawn by one page in one Chromium
(``data/web/parts-sheet.js``): frame ``n`` builds part ``n`` in a scene of its own and draws it at
its time ``at``; the tiles are then laid out with their names and the one line that uses them.
"""

from __future__ import annotations

import difflib
import fnmatch
import io
import json
import math
import re
import shutil
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "web"
#: The parts files (``<module>.js``) and the registry module they register with.
PARTS_DIR = DATA_DIR / "parts"
REGISTRY_FILE = DATA_DIR / "modules" / "parts.js"
#: The page that draws the sheet.
SHEET_SCRIPT = DATA_DIR / "parts-sheet.js"
#: The kinds of parts in the sheet's order (``KINDS`` of ``vidgen/parts``; a test keeps them equal).
KINDS: tuple[str, ...] = ("sky", "body", "light", "air", "craft", "craft-part", "phenomenon", "camera", "structure", "effect", "environment")
REQUIRED: tuple[str, ...] = ("name", "kind", "module", "label", "use")
OPTIONAL: dict[str, Any] = {"options": {}, "seed": 1, "at": 2}
#: A tile's size by default (pixels), and the one large tile of a single part.
TILE = (320, 180)
LARGE_TILE = (960, 540)
TILE_MIN, TILE_MAX = 48, 1920
#: Columns chosen without ``--columns``, and the most allowed.
AUTO_COLUMNS = 5
MAX_COLUMNS = 12
#: Seconds the whole sheet may take by default (the page stops after the tile that passes it).
TIME_LIMIT = 300.0
BACKGROUND = (12, 12, 14)
NAME_COLOUR = (240, 240, 240)
KIND_COLOUR = (150, 160, 175)
USE_COLOUR = (140, 205, 255)
_DEFINE = re.compile(r"\bdefinePart\(\s*")


@dataclass(frozen=True)
class PartInfo:
    """A part as its file describes it: ``name``, ``kind``, ``module`` (the import that has its
    code), ``label`` (what it is), ``use`` (the one line that uses it), default ``options``, ``seed``,
    ``at`` (the time in seconds the sheet shows) and the parts ``file`` it is defined in."""

    name: str
    kind: str
    module: str
    label: str
    use: str
    options: dict[str, Any]
    seed: int
    at: float
    file: str

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "module": self.module, "label": self.label, "use": self.use,
                "options": self.options, "seed": self.seed, "at": self.at, "file": self.file,
                "import": f'import "vidgen/parts/{self.file}"'}


def _object_at(text: str, start: int, where: str) -> tuple[str, int]:
    """The ``{...}`` starting at ``text[start]`` (braces inside strings ignored) and the index after it."""
    if start >= len(text) or text[start] != "{":
        raise VidgenError(f"{where}: definePart's first argument must be a JSON object")
    depth, quote, k = 0, False, start
    while k < len(text):
        c = text[k]
        if quote:
            if c == "\\":
                k += 1
            elif c == '"':
                quote = False
        elif c == '"':
            quote = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : k + 1], k + 1
        k += 1
    raise VidgenError(f"{where}: definePart's first argument never closes")


def parse_parts(text: str, file: str) -> list[PartInfo]:
    """The parts a parts file defines: the JSON first argument of each ``definePart(`` call."""
    out = []
    for match in _DEFINE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        where = f"data/web/parts/{file}:{line}"
        body, _ = _object_at(text, match.end(), where)
        try:
            info = json.loads(body)
        except ValueError as exc:
            raise VidgenError(f"{where}: definePart's first argument is not JSON ({exc}); write it with double-quoted keys and strings") from None
        missing = [k for k in REQUIRED if not isinstance(info.get(k), str) or not info[k]]
        unknown = [k for k in info if k not in REQUIRED and k not in OPTIONAL]
        if missing or unknown:
            raise VidgenError(f"{where}: part {info.get('name', '?')!r}: " + "; ".join(
                ([f"needs {', '.join(missing)}"] if missing else []) + ([f"unknown field(s) {', '.join(unknown)}"] if unknown else [])))
        if info["kind"] not in KINDS:
            raise VidgenError(f"{where}: part {info['name']!r}: kind {info['kind']!r}; kinds: {', '.join(KINDS)}")
        out.append(PartInfo(info["name"], info["kind"], info["module"], info["label"], info["use"], dict(info.get("options", {})),
                            int(info.get("seed", 1)), float(info.get("at", 2)), file))
    return out


def read_parts(folder: Path = PARTS_DIR) -> list[PartInfo]:
    """Every shipped part, in the order of :data:`KINDS`, then file by file as defined; a name
    defined twice is a :class:`VidgenError`."""
    found: list[PartInfo] = []
    for path in sorted(folder.glob("*.js")):
        found += parse_parts(path.read_text(encoding="utf-8"), path.name)
    seen: dict[str, str] = {}
    for p in found:
        if p.name in seen:
            raise VidgenError(f"part {p.name!r} is defined in {seen[p.name]} and {p.file}")
        seen[p.name] = p.file
    return sorted(found, key=lambda p: KINDS.index(p.kind))


def select_parts(parts: Sequence[PartInfo], names: Sequence[str] = (), kind: str | None = None) -> list[PartInfo]:
    """The parts named (a name, or a pattern such as ``star-*`` or ``*ring*``) and of ``kind``;
    an unknown name or kind is a :class:`VidgenError` with the closest one."""
    if kind is not None and kind not in KINDS:
        close = difflib.get_close_matches(kind, KINDS, n=1)
        raise VidgenError(f"--kind {kind}: no such kind{f' (did you mean {close[0]!r}?)' if close else ''}; kinds: {', '.join(KINDS)}")
    chosen = [p for p in parts if kind is None or p.kind == kind]
    if kind is not None and not chosen:
        raise VidgenError(f"--kind {kind}: no part of that kind yet; kinds with parts: {', '.join(sorted({p.kind for p in parts}, key=KINDS.index))}")
    if not names:
        return chosen
    picked: list[PartInfo] = []
    for name in names:
        hits = [p for p in chosen if fnmatch.fnmatchcase(p.name, name)]
        if not hits:
            close = difflib.get_close_matches(name, [p.name for p in chosen], n=1)
            raise VidgenError(f"no part {name!r}{f' (did you mean {close[0]!r}?)' if close else ''}{f' of kind {kind}' if kind else ''}; "
                              "vidgen parts --list names them")
        picked += [p for p in hits if p not in picked]
    return picked


def parse_tile(text: str | None, single: bool) -> tuple[int, int]:
    """``--size WxH`` (default :data:`TILE`, or :data:`LARGE_TILE` for one part)."""
    if text is None:
        return LARGE_TILE if single else TILE
    match = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", text)
    if match is None:
        raise VidgenError(f"--size {text}: expected WIDTHxHEIGHT, e.g. 320x180")
    w, h = int(match[1]), int(match[2])
    if not (TILE_MIN <= w <= TILE_MAX and TILE_MIN <= h <= TILE_MAX) or w % 2 or h % 2:
        raise VidgenError(f"--size {text}: width and height must be even, {TILE_MIN} to {TILE_MAX} pixels")
    return w, h


def list_text(parts: Sequence[PartInfo]) -> str:
    """The parts as text: per kind, each name, what it is, the import and the one line that uses it."""
    lines: list[str] = []
    for kind in KINDS:
        group = [p for p in parts if p.kind == kind]
        if not group:
            continue
        lines.append(f"{kind}:")
        for p in group:
            lines.append(f"  {p.name:<20} {p.label}")
            lines.append(f"  {'':<20} {p.module}: {p.use}")
    lines.append(f"{len(parts)} part(s); a page uses one with import \"vidgen/parts/<file>\" + buildPart(name, stage), "
                 "or with its module's own call (the second line)")
    return "\n".join(lines)


@dataclass
class Tile:
    """A tile drawn: the part, and the seconds building and drawing it took."""

    part: PartInfo
    seconds: float


@dataclass
class SheetResult:
    """What :func:`make_parts_sheet` drew: the sheet's file and size, the tiles, the parts left
    out at the time limit, the seconds until the page was ready and in all."""

    path: Path
    tile: tuple[int, int]
    columns: int
    size: tuple[int, int] = (0, 0)
    tiles: list[Tile] = field(default_factory=list)
    skipped: list[PartInfo] = field(default_factory=list)
    load_seconds: float = 0.0
    seconds: float = 0.0


def _wrap(draw: Any, text: str, font: Any, width: int, lines: int) -> list[str]:
    """``text`` broken at spaces (else anywhere) into at most ``lines`` lines of ``width`` pixels, the last cut with an ellipsis."""
    out: list[str] = []
    rest = text
    while rest and len(out) < lines:
        if draw.textlength(rest, font=font) <= width:
            out.append(rest)
            break
        cut = len(rest)
        while cut > 1 and draw.textlength(rest[:cut], font=font) > width:
            cut -= 1
        space = rest.rfind(" ", 0, cut)
        cut = space + 1 if space > cut // 2 else cut
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest and len(out) == lines and out[-1] != rest:
        last = out[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        out[-1] = last + "…"
    return out


def compose_sheet(tiles: Sequence[tuple[np.ndarray, PartInfo]], columns: int, title: str) -> Any:
    """The sheet (a PIL image): a title line, then ``columns`` tiles to a row, each with its name
    and kind, what it is, and the line that uses it (wrapped to the tile's width)."""
    from PIL import Image, ImageDraw, ImageFont

    from vidgen.fonts import MONO_FAMILY, bundled_font_file
    from vidgen.sheets import load_font

    h, w = tiles[0][0].shape[:2]
    size = max(11, min(18, w // 24))
    name_font, text_font = load_font(size + 1, bold=True), load_font(size)
    mono_file = bundled_font_file(MONO_FAMILY)
    mono = ImageFont.truetype(str(mono_file), size) if mono_file else text_font
    pad, gap = 8, 3
    band = (size + 1 + gap) + 2 * (size + gap) + 3 * (size + gap) + pad
    head = size + 2 * pad + 4
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new("RGB", (pad + columns * (w + pad), head + rows * (h + band + pad)), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, pad), title, fill=NAME_COLOUR, font=load_font(size + 2, bold=True))
    for i, (pixels, p) in enumerate(tiles):
        x, y = pad + (i % columns) * (w + pad), head + (i // columns) * (h + band + pad)
        sheet.paste(Image.fromarray(pixels), (x, y))
        ty = y + h + gap + 1
        draw.text((x, ty), p.name, fill=NAME_COLOUR, font=name_font)
        draw.text((x + draw.textlength(p.name + "  ", font=name_font), ty + 1), p.kind, fill=KIND_COLOUR, font=text_font)
        ty += size + 1 + gap
        for line in _wrap(draw, p.label, text_font, w, 2):
            draw.text((x, ty), line, fill=KIND_COLOUR, font=text_font)
            ty += size + gap
        ty = y + h + gap + 1 + (size + 1 + gap) + 2 * (size + gap)
        for line in _wrap(draw, p.use, mono, w, 3):
            draw.text((x, ty), line, fill=USE_COLOUR, font=mono)
            ty += size + gap
    return sheet


def make_parts_sheet(parts: Sequence[PartInfo], out: Path, *, tile: tuple[int, int] = TILE, columns: int | None = None,
                     time_limit: float = TIME_LIMIT, on_tile: Callable[[int, int, Tile], None] | None = None) -> SheetResult:
    """Draw ``parts`` (one tile of ``tile`` pixels each) in one Chromium and write the labelled
    contact sheet to ``out`` (PNG or JPEG). Tiles are drawn in order until ``time_limit`` seconds
    have passed (the first one always); the rest are left out (``skipped``) and the sheet says so. ``on_tile(k, n, tile)``
    after each tile (k from 1)."""
    from vidgen.web.entry import WebEntry
    from vidgen.web.loaded import PARTS_FOLDER, VIDGEN_PREFIX
    from vidgen.web.page import WebPage
    from vidgen.web.still import over_background

    if not parts:
        raise VidgenError("no parts to draw")
    if out.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise VidgenError(f"--out {out}: give a .png or .jpg file")
    if columns is not None and not 1 <= columns <= MAX_COLUMNS:
        raise VidgenError(f"--columns must be 1 to {MAX_COLUMNS}")
    cols = columns or max(1, min(AUTO_COLUMNS, len(parts)))
    result = SheetResult(out, tile, cols)
    started = time.monotonic()
    files = sorted({p.file for p in parts})
    data = {"names": [p.name for p in parts], "files": [f"/{VIDGEN_PREFIX}{PARTS_FOLDER}/{f}" for f in files]}
    drawn: list[tuple[np.ndarray, PartInfo]] = []
    with tempfile.TemporaryDirectory(prefix="vidgen_parts_") as root:
        shutil.copyfile(SHEET_SCRIPT, Path(root) / "sheet.js")
        with WebPage(Path(root), WebEntry("script", "sheet.js"), scene_id="parts", size=tile, fps=1, frames=len(parts), data=data) as page:
            result.load_seconds = time.monotonic() - started
            for k, p in enumerate(parts):
                if k and time.monotonic() - started > time_limit:  # the first part is always drawn
                    result.skipped = list(parts[k:])
                    break
                began = time.monotonic()
                pixels = over_background(page.frame(k), "#000000")
                done = Tile(p, time.monotonic() - began)
                result.tiles.append(done)
                drawn.append((pixels, p))
                if on_tile is not None:
                    on_tile(k + 1, len(parts), done)
    title = f"vidgen parts: {len(drawn)} part(s), {tile[0]}x{tile[1]}"
    if result.skipped:
        title += f"; {len(result.skipped)} left out at the time limit ({time_limit:g} s): {', '.join(p.name for p in result.skipped[:6])}"
    picture = compose_sheet(drawn, cols, title)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG" if out.suffix.lower() == ".png" else "JPEG", **({} if out.suffix.lower() == ".png" else {"quality": 90}))
    write_bytes_atomic(out, buffer.getvalue())
    result.size = picture.size
    result.seconds = time.monotonic() - started
    return result


__all__ = ["KINDS", "LARGE_TILE", "PARTS_DIR", "PartInfo", "SheetResult", "TILE", "Tile", "compose_sheet", "list_text",
           "make_parts_sheet", "parse_parts", "parse_tile", "read_parts", "select_parts"]
