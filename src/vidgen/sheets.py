"""Contact sheets: frame stills laid out in a grid with labels and narration (Pillow).

:func:`compose_pages` turns scenes and their stills into one or more page images. Layout:

- a page header (title + one line saying what the times and stills mean);
- per scene a header band ``N/M  id  ·  type  ·  beats  ·  time range``;
- the stills in a grid, the stills of one beat side by side as a *block*, each labelled
  ``beat @ time``, with the beat's narration (wrapped, trimmed with an ellipsis) under the block.

Designed to be read by an AI agent opening the PNG: bounded width, font sizes proportional to
the width, dark text on a light background, at most about ``width x max_height`` pixels per
page (longer videos get more pages; a scene continued on the next page repeats its header).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vidgen.fonts import FONTS_DIR

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

#: Font files tried in order: vidgen's bundled Inter first, then names Pillow finds in the system
#: font folders on Windows/macOS/Linux.
REGULAR_FONTS: tuple[str, ...] = (
    str(FONTS_DIR / "Inter" / "Inter-Regular.ttf"), "Inter-Regular.otf", "Inter-Regular.ttf", "DejaVuSans.ttf", "arial.ttf", "Arial.ttf",
    "LiberationSans-Regular.ttf", "Helvetica.ttc",
)
BOLD_FONTS: tuple[str, ...] = (
    str(FONTS_DIR / "Inter" / "Inter-Bold.ttf"), "Inter-SemiBold.otf", "Inter-SemiBold.ttf", "Inter-Bold.otf", "DejaVuSans-Bold.ttf", "arialbd.ttf",
    "Arial Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc",
)

#: Default page width in pixels and the accepted range.
DEFAULT_WIDTH = 1280
MIN_WIDTH, MAX_WIDTH = 640, 2000

#: Default maximum page height as a multiple of the width.
PAGE_RATIO = 1.25

BACKGROUND = (255, 255, 255)
BAND = (226, 231, 238)
TEXT = (17, 20, 26)
MUTED = (70, 76, 88)
BORDER = (120, 126, 138)


@dataclass(frozen=True)
class SheetStill:
    """One still on a sheet. ``time`` is in the video (``None`` if unknown), ``scene_time``
    from the scene start; ``text`` is the beat's narration (``None`` for a silent scene)."""

    scene_id: str
    beat_id: str | None
    k: int
    n: int
    scene_time: float
    time: float | None
    path: Path
    text: str | None


@dataclass(frozen=True)
class SheetScene:
    """A scene section: its position ``number`` of ``total`` scenes, start in the video
    (``None`` if unknown), duration, beat count and stills (in time order)."""

    id: str
    type: str
    number: int
    total: int
    start: float | None
    duration: float
    beats: int
    stills: tuple[SheetStill, ...]


@dataclass
class SheetPage:
    """A composed page and the stills it shows (in order)."""

    image: Image.Image
    stills: list[SheetStill] = field(default_factory=list)


@lru_cache(maxsize=32)
def load_font(size: int, bold: bool = False) -> Font:
    """The first available font of :data:`BOLD_FONTS`/:data:`REGULAR_FONTS` at ``size`` px,
    else Pillow's built-in font."""
    for name in BOLD_FONTS if bold else REGULAR_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1: fixed-size bitmap font
        return ImageFont.load_default()


def format_time(seconds: float) -> str:
    """``m:ss.s`` (``75.25`` -> ``1:15.3``)."""
    tenths = round(seconds * 10)
    minutes, rest = divmod(tenths, 600)
    return f"{minutes}:{rest // 10:02d}.{rest % 10}"


def _text_width(font: Font, text: str) -> float:
    return font.getlength(text)


def fit_line(font: Font, text: str, width: float) -> str:
    """``text`` cut with an ellipsis so it fits ``width`` pixels."""
    if _text_width(font, text) <= width:
        return text
    while text and _text_width(font, text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap_text(font: Font, text: str, width: float, max_lines: int) -> list[str]:
    """Greedy word wrap to ``width`` pixels; more than ``max_lines`` lines end with an ellipsis.
    Words longer than a line are broken."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if _text_width(font, candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while _text_width(font, word) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and _text_width(font, word[:cut]) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_line(font, lines[-1] + "…", width)
    return lines


@dataclass(frozen=True)
class _Metrics:
    width: int
    max_height: int
    columns: int
    margin: int
    gutter: int
    cell_w: int
    cell_h: int
    title: Font
    subtitle: Font
    header: Font
    label: Font
    narration: Font
    narration_lines: int

    @property
    def header_h(self) -> int:
        """Height of a scene header band plus the space under it."""
        return self.line_height(self.header) + self.gutter

    def line_height(self, font: Font) -> int:
        if isinstance(font, ImageFont.FreeTypeFont):
            ascent, descent = font.getmetrics()
            return math.ceil((ascent + descent) * 1.18)
        left, top, right, bottom = font.getbbox("Ag")  # Pillow's old bitmap font
        return math.ceil((bottom - top) * 1.5)


#: Most stills in one row.
MAX_COLUMNS = 8


def _columns(frame_size: tuple[int, int], detail: bool, per_beat: int = 1) -> int:
    """Stills per row: wide frames get fewer, tall (9:16) frames more; ``detail`` (a single
    scene's sheet) uses larger stills. With several stills per beat, the multiple of
    ``per_beat`` nearest to that (so beats do not leave holes or break across rows)."""
    w, h = frame_size
    aspect = w / h
    if aspect >= 1.4:
        base = 2 if detail else 4
    elif aspect >= 0.8:
        base = 3 if detail else 5
    else:
        base = 4 if detail else 5
    if per_beat <= 1:
        return base
    if per_beat >= MAX_COLUMNS:
        return MAX_COLUMNS
    multiples = range(per_beat, MAX_COLUMNS + 1, per_beat)
    return min(multiples, key=lambda c: (abs(c - base), -c))


def _metrics(width: int, frame_size: tuple[int, int], detail: bool, max_height: int | None, per_beat: int) -> _Metrics:
    scale = width / DEFAULT_WIDTH
    px = lambda v: max(round(v * scale), 9)  # noqa: E731 - tiny local scaler
    columns = _columns(frame_size, detail, per_beat)
    margin, gutter = px(28), px(20)
    cell_w = (width - 2 * margin - (columns - 1) * gutter) // columns
    cell_h = round(cell_w * frame_size[1] / frame_size[0])
    return _Metrics(
        width=width,
        max_height=max_height or round(width * PAGE_RATIO),
        columns=columns,
        margin=margin,
        gutter=gutter,
        cell_w=cell_w,
        cell_h=cell_h,
        title=load_font(px(30), bold=True),
        subtitle=load_font(px(19)),
        header=load_font(px(20), bold=True),
        label=load_font(px(19), bold=True),
        narration=load_font(px(19)),
        narration_lines=6 if detail else 4,
    )


@dataclass
class _Block:
    """Stills of one beat side by side (at most ``columns``) and the narration under them."""

    stills: list[SheetStill]
    text: list[str]


@dataclass
class _Segment:
    """The part of a row that belongs to one scene; ``header``: draw the scene's header band
    above it (``continued``: the scene started on an earlier page)."""

    scene: SheetScene
    blocks: list[_Block] = field(default_factory=list)
    header: bool = True
    continued: bool = False

    @property
    def cells(self) -> int:
        return sum(len(b.stills) for b in self.blocks)


@dataclass
class _Row:
    segments: list[_Segment] = field(default_factory=list)

    @property
    def cells(self) -> int:
        return sum(s.cells for s in self.segments)


def _blocks(scene: SheetScene, m: _Metrics) -> list[_Block]:
    """Group consecutive stills of a beat (chunks of at most ``columns``); the narration goes
    under the beat's last chunk."""
    groups: list[list[SheetStill]] = []
    for still in scene.stills:
        if groups and groups[-1][0].beat_id == still.beat_id:
            groups[-1].append(still)
        else:
            groups.append([still])
    blocks: list[_Block] = []
    for group in groups:
        chunks = [group[i : i + m.columns] for i in range(0, len(group), m.columns)]
        for i, chunk in enumerate(chunks):
            text: list[str] = []
            if i == len(chunks) - 1:
                narration = f"\u201c{chunk[0].text}\u201d" if chunk[0].text else f"(silent scene, {scene.duration:.1f} s)"
                if chunk[0].n > 1:
                    narration = f"{chunk[0].beat_id or scene.id}: {narration}"
                text = wrap_text(m.narration, narration, _span(len(chunk), m), m.narration_lines)
            blocks.append(_Block(chunk, text))
    return blocks


def _span(cells: int, m: _Metrics) -> int:
    """Width in px of ``cells`` stills side by side."""
    return cells * m.cell_w + (cells - 1) * m.gutter


def _rows(scenes: Sequence[SheetScene], m: _Metrics) -> list[_Row]:
    """Flow the scenes into rows of at most ``columns`` stills. A scene that fits entirely in
    the rest of the current row shares it; otherwise it starts a new row (and may span several).
    """
    rows: list[_Row] = []
    for scene in scenes:
        blocks = _blocks(scene, m)
        if not blocks:
            continue
        total = sum(len(b.stills) for b in blocks)
        if rows and rows[-1].cells + total <= m.columns:
            rows[-1].segments.append(_Segment(scene, blocks))
            continue
        segment: _Segment | None = None
        for block in blocks:
            if segment is None or rows[-1].cells + len(block.stills) > m.columns:
                segment = _Segment(scene, header=segment is None)
                rows.append(_Row([segment]))
            segment.blocks.append(block)
    return rows


def _row_height(row: _Row, m: _Metrics) -> int:
    lines = max(len(b.text) for s in row.segments for b in s.blocks)
    header = m.header_h if any(s.header for s in row.segments) else 0
    return header + m.cell_h + m.gutter // 3 + m.line_height(m.label) + lines * m.line_height(m.narration) + m.gutter


def _header_text(scene: SheetScene, continued: bool, font: Font, width: float) -> str:
    """``N/M  id  ·  type  ·  start–end (duration)``; the details that do not fit ``width`` are
    left out (time range, then the type) before the rest is cut with an ellipsis."""
    when = f"{scene.duration:.1f} s"
    if scene.start is not None:
        when = f"{format_time(scene.start)}\u2013{format_time(scene.start + scene.duration)} ({when})"
    if not scene.beats:
        when = f"silent, {when}"
    name = f"{scene.number}/{scene.total}  {scene.id}"
    suffix = "  (continued)" if continued else ""
    for parts in ([name, scene.type, when], [name, scene.type], [name]):
        text = "  \u00b7  ".join(parts) + suffix
        if _text_width(font, text) <= width:
            return text
    return fit_line(font, name + suffix, width)


def _label(still: SheetStill, video_times: bool) -> str:
    """``beat @ time``; with several stills per beat ``k/n @ time`` (the beat id is then
    written before the narration under the block)."""
    name = f"{still.k}/{still.n}" if still.n > 1 else still.beat_id or f"{still.scene_id} (silent)"
    if video_times and still.time is not None:
        return f"{name} @ {format_time(still.time)}"
    return f"{name} @ {still.scene_time:.1f} s"


def _paginate(rows: list[_Row], m: _Metrics, top: int) -> list[list[_Row]]:
    """Split rows into as few pages of at most ``max_height`` px as possible (a row taller
    than that gets a page of its own), balanced so the last page is not nearly empty."""
    heights = [_row_height(row, m) for row in rows]
    limit = m.max_height - m.margin - top
    pages = _split(heights, limit)
    if len(pages) > 1:  # the smallest limit giving the same number of pages
        low = max(max(heights), sum(heights) // len(pages))
        while low < limit:
            balanced = _split(heights, low)
            if len(balanced) <= len(pages):
                pages = balanced
                break
            low += max(limit // 50, 1)
    result = [[rows[i] for i in page] for page in pages]
    for page in result[1:]:
        first = page[0].segments[0]
        if not first.header:  # a scene continued from the previous page: repeat its header
            first.header = first.continued = True
    return result


def _split(heights: list[int], limit: int) -> list[list[int]]:
    """Greedy split of row indexes into pages whose rows add up to at most ``limit``."""
    pages: list[list[int]] = [[]]
    used = 0
    for i, height in enumerate(heights):
        if pages[-1] and used + height > limit:
            pages.append([])
            used = 0
        pages[-1].append(i)
        used += height
    return pages


def compose_pages(
    title: str,
    subtitle: str,
    scenes: Sequence[SheetScene],
    frame_size: tuple[int, int],
    *,
    width: int = DEFAULT_WIDTH,
    detail: bool = False,
    video_times: bool = True,
    max_height: int | None = None,
) -> list[SheetPage]:
    """Lay out ``scenes`` on pages ``width`` px wide and at most about ``max_height`` (default:
    ``width * PAGE_RATIO``) px high; returns the pages (at least one).

    ``frame_size`` is the stills' pixel size; ``detail`` uses larger stills (a single scene's
    sheet); ``video_times`` labels stills with their time in the video (else in the scene).
    """
    per_beat = max((still.n for scene in scenes for still in scene.stills), default=1)
    m = _metrics(width, frame_size, detail, max_height, per_beat)
    top = m.margin + m.line_height(m.title) + m.line_height(m.subtitle) + m.gutter // 2
    pages = _paginate(_rows(scenes, m), m, top)
    result = []
    for number, rows in enumerate(pages, start=1):
        height = top + sum(_row_height(row, m) for row in rows) + m.margin - m.gutter
        image = Image.new("RGB", (width, max(height, top + m.margin)), BACKGROUND)
        draw = ImageDraw.Draw(image)
        page_info = f"  \u00b7  page {number}/{len(pages)}" if len(pages) > 1 else ""
        text_width = width - 2 * m.margin
        draw.text((m.margin, m.margin), fit_line(m.title, title, text_width), font=m.title, fill=TEXT)
        draw.text(
            (m.margin, m.margin + m.line_height(m.title)),
            fit_line(m.subtitle, subtitle + page_info, text_width),
            font=m.subtitle,
            fill=MUTED,
        )
        page = SheetPage(image)
        y = top
        for row in rows:
            _draw_row(image, draw, row, m, y, video_times)
            page.stills.extend(still for s in row.segments for b in s.blocks for still in b.stills)
            y += _row_height(row, m)
        result.append(page)
    return result


def _draw_row(image: Image.Image, draw: ImageDraw.ImageDraw, row: _Row, m: _Metrics, y: int, video_times: bool) -> None:
    has_header = any(s.header for s in row.segments)
    cells_y = y + (m.header_h if has_header else 0)
    x = m.margin
    for segment in row.segments:
        if segment.header:
            span = _span(segment.cells, m)
            pad = m.gutter // 4  # bands of neighbouring scenes stay apart
            draw.rectangle((x - pad, y, x + span + pad, y + m.header_h - m.gutter // 2), fill=BAND)
            draw.text(
                (x, y + m.gutter // 6),
                _header_text(segment.scene, segment.continued, m.header, span),
                font=m.header,
                fill=TEXT,
            )
        for block in segment.blocks:
            block_x = x
            for still in block.stills:
                with Image.open(still.path) as source:
                    thumb = source.convert("RGB")
                    thumb.thumbnail((m.cell_w, m.cell_h), Image.Resampling.LANCZOS)
                image.paste(thumb, (x, cells_y))
                draw.rectangle((x - 1, cells_y - 1, x + thumb.width, cells_y + thumb.height), outline=BORDER)
                draw.text(
                    (x, cells_y + m.cell_h + m.gutter // 3),
                    fit_line(m.label, _label(still, video_times), m.cell_w),
                    font=m.label,
                    fill=TEXT,
                )
                x += m.cell_w + m.gutter
            text_y = cells_y + m.cell_h + m.gutter // 3 + m.line_height(m.label)
            for line in block.text:
                draw.text((block_x, text_y), line, font=m.narration, fill=MUTED)
                text_y += m.line_height(m.narration)
