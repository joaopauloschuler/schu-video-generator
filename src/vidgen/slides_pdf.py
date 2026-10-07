"""``vidgen slides --format pdf``: the video's key frames as a PDF deck (DESIGN.md §56).

The slides come from :func:`vidgen.deck.deck_frames`, like the HTML deck of ``vidgen slides``.
Without notes every slide is one page at the video's aspect ratio (the long side 960 pt, the
13.33 in of a widescreen presentation), the picture filling the page. With ``notes`` every slide
gets a notes page on paper (A4 or US Letter, portrait): a header with the chapter and the video's
title, the picture, a line saying where the slide is in the video, the narration (the variant's
translated text) wrapped in the bundled Inter font, and a page number; long notes continue on
the next page. An optional title page shows the thumbnail (``vidgen thumbnail``) when there is
one and the title, author and date. The PDF has the ``metadata:`` title / author / subject, the
video's language, and an outline (bookmarks): chapters, the slides under them.

The PDF is written with `fpdf2 <https://py-pdf.github.io/fpdf2/>`_ (pure Python, embeds subsets
of TrueType fonts): the optional extra ``schu-video-generator[pdf]``; without it the command says how to add it.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vidgen import DIST_NAME, __version__
from vidgen.deck import Deck, DeckMode, DeckSlide, deck_frames
from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic
from vidgen.fonts import FONTS_DIR, SANS_FAMILY
from vidgen.project import Project
from vidgen.sheets import format_time
from vidgen.slides import MIN_WIDTH, encode_still

#: Picture formats of the PDF deck: JPEG (embedded as is, small) or PNG (lossless, larger).
PDF_IMAGE_FORMATS: tuple[str, ...] = ("jpeg", "png")
DEFAULT_PDF_QUALITY = 85
#: Paper sizes of notes pages (portrait, points).
PAPER_SIZES: dict[str, tuple[float, float]] = {"a4": (595.28, 841.89), "letter": (612.0, 792.0)}
#: The long side of a slide page (points): 13.33 in, a widescreen presentation's page.
SLIDE_LONG_SIDE = 960.0
#: Margin of notes pages (points, about 17 mm).
MARGIN = 48.0
#: The picture of a notes page is at most this fraction of the paper's height (9:16 slides).
NOTES_PICTURE_SHARE = 0.5
INK = (17, 24, 39)
MUTED = (100, 108, 120)
RULE = (205, 210, 218)
_INTER = FONTS_DIR / "Inter"


@dataclass
class PdfOptions:
    """How :func:`write_pdf` lays out the deck: ``notes`` pages or full-page slides, a
    ``title_page``, the ``paper`` of notes pages, the pictures' ``image_format`` / ``quality`` /
    ``max_width``."""

    notes: bool = False
    title_page: bool = False
    paper: str = "a4"
    image_format: str = "jpeg"
    quality: int = DEFAULT_PDF_QUALITY
    max_width: int | None = None


@dataclass
class PdfResult:
    """What :func:`make_slides_pdf` wrote: the PDF (``path``, ``bytes``, ``pages``), the options,
    the pictures' size, the outline entries and the :class:`~vidgen.deck.Deck` it shows."""

    path: Path
    bytes: int
    pages: int
    options: PdfOptions
    width: int
    height: int
    bookmarks: int
    thumbnail: Path | None
    deck: Deck


def pdf_path(project: Project, preview: bool, notes: bool = False) -> Path:
    """The default file: ``exports/<output>[_<variant>][_preview]_slides.pdf`` (``_notes.pdf``
    with notes pages)."""
    return project.exports_dir / f"{project.export_stem(preview)}_{'notes' if notes else 'slides'}.pdf"


def _fpdf() -> Any:
    """The ``fpdf`` module (fpdf2), or a :class:`VidgenError` saying how to install it."""
    try:
        import fpdf
    except ImportError:
        raise VidgenError(
            f'the PDF deck needs fpdf2, an optional dependency: pip install "{DIST_NAME}[pdf]" (or pip install fpdf2)'
        ) from None
    # fontTools logs every step of the font subsetting at INFO (the CLI shows INFO)
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    return fpdf


def slide_page_size(width: int, height: int) -> tuple[float, float]:
    """A slide page (points) of the video's aspect ratio, its long side :data:`SLIDE_LONG_SIDE`."""
    if width >= height:
        return SLIDE_LONG_SIDE, round(SLIDE_LONG_SIDE * height / width, 2)
    return round(SLIDE_LONG_SIDE * width / height, 2), SLIDE_LONG_SIDE


def _thumbnail(project: Project, preview: bool) -> Path | None:
    """The thumbnail ``vidgen thumbnail`` wrote (this quality's first, else the other's)."""
    for quality in (preview, not preview):
        path = project.thumbnail_path(quality)
        if path.is_file():
            return path
    return None


def _chapter_line(slide: DeckSlide) -> str:
    return "" if slide.chapter is None else f"{slide.chapter.label} · {slide.chapter.title}"


def _where(slide: DeckSlide, count: int) -> str:
    parts = [f"Slide {slide.index} / {count}", slide.scene_title or slide.scene]
    if slide.n > 1:
        parts.append(f"still {slide.k}/{slide.n} of its beat")
    if slide.time is not None:
        parts.append(f"{format_time(slide.time)} in the video")
    return " · ".join(parts)


class _Writer:
    """Builds the PDF page by page with fpdf2."""

    def __init__(self, deck: Deck, options: PdfOptions, size: tuple[int, int]) -> None:
        fpdf = _fpdf()
        self.fpdf = fpdf
        self.deck = deck
        self.options = options
        self.size = size
        self.title = deck.project.config.metadata.title or deck.project.config.title
        self.slide_page = slide_page_size(*size)
        self.paper = PAPER_SIZES[options.paper]
        pdf = fpdf.FPDF(unit="pt", format=self.slide_page)
        pdf.set_auto_page_break(False)
        pdf.set_margins(MARGIN, MARGIN, MARGIN)
        pdf.add_font(SANS_FAMILY, "", _INTER / "Inter-Regular.ttf")
        pdf.add_font(SANS_FAMILY, "B", _INTER / "Inter-Bold.ttf")
        pdf.add_font(SANS_FAMILY, "I", _INTER / "Inter-Italic.ttf")
        pdf.header = self._header  # type: ignore[method-assign]
        pdf.footer = self._footer  # type: ignore[method-assign]
        self.pdf = pdf
        self.chrome = False  # header and footer on this page (notes pages)
        self.chapter = ""  # the header's chapter line
        self.bookmarks = 0

    # ----- document ------------------------------------------------------------------------

    def metadata(self) -> None:
        """Title, author, subject, keywords, language, creator and the outline shown on opening."""
        config = self.deck.project.config
        meta = config.metadata
        pdf = self.pdf
        pdf.set_title(self.title)
        if meta.artist:
            pdf.set_author(meta.artist)
        subject = meta.description or meta.comment
        if subject:
            pdf.set_subject(subject)
        keywords = [k for k in (meta.album, meta.genre) if k]
        if keywords:
            pdf.set_keywords(", ".join(keywords))
        if config.language:
            pdf.set_lang(config.language)
        pdf.set_creator(f"{DIST_NAME} {__version__}")
        pdf.set_creation_date(datetime.now(timezone.utc))
        pdf.page_mode = "USE_OUTLINES"

    def bookmark(self, name: str, level: int) -> None:
        self.pdf.start_section(name, level=level)
        self.bookmarks += 1

    # ----- page chrome (notes pages) -------------------------------------------------------

    def _header(self) -> None:
        if not self.chrome:
            return
        pdf = self.pdf
        width = pdf.w - 2 * MARGIN
        pdf.set_xy(MARGIN, MARGIN - 22)
        pdf.set_font(SANS_FAMILY, "B", 9)
        pdf.set_text_color(*MUTED)
        chapter = self.chapter
        title_width = width * (0.5 if chapter else 1.0)
        if chapter:
            pdf.cell(width - title_width, 12, _fit(pdf, chapter, width - title_width - 8))
        pdf.set_font(SANS_FAMILY, "", 9)
        pdf.cell(title_width, 12, _fit(pdf, self.title, title_width), align="R")
        pdf.set_draw_color(*RULE)
        pdf.set_line_width(0.6)
        pdf.line(MARGIN, MARGIN - 6, pdf.w - MARGIN, MARGIN - 6)
        pdf.set_xy(MARGIN, MARGIN)

    def _footer(self) -> None:
        if not self.chrome:
            return
        pdf = self.pdf
        pdf.set_xy(MARGIN, pdf.h - MARGIN + 14)
        pdf.set_font(SANS_FAMILY, "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(pdf.w - 2 * MARGIN, 12, f"{pdf.page_no()} / {pdf.str_alias_nb_pages}", align="C")

    # ----- pages ---------------------------------------------------------------------------

    def notes_layout(self) -> tuple[float, float, float]:
        """The picture's width, height and left edge on a notes page."""
        width = self.paper[0] - 2 * MARGIN
        height = width * self.size[1] / self.size[0]
        limit = self.paper[1] * NOTES_PICTURE_SHARE
        if height > limit:
            width, height = limit * self.size[0] / self.size[1], limit
        return width, height, (self.paper[0] - width) / 2

    def picture(self, data: bytes, x: float, y: float, w: float, h: float, alt: str, border: bool) -> None:
        self.pdf.image(io.BytesIO(data), x=x, y=y, w=w, h=h, alt_text=alt)
        if border:
            self.pdf.set_draw_color(*RULE)
            self.pdf.set_line_width(0.6)
            self.pdf.rect(x, y, w, h)

    def title_page(self, thumbnail: bytes | None, thumb_size: tuple[int, int] | None, slides: int) -> None:
        """The deck's first page: the thumbnail (if any) and the title, author, date."""
        meta = self.deck.project.config.metadata
        spec = self.deck.project.config.thumbnail
        subtitle = spec.subtitle if spec is not None and spec.subtitle else None
        byline = " · ".join(x for x in (meta.artist, meta.date) if x)
        pdf = self.pdf
        notes = self.options.notes
        self.chrome = False
        pdf.add_page(orientation="P", format=self.paper if notes else self.slide_page)
        self.bookmark(self.title, 0)
        if thumbnail is not None and thumb_size is not None and not notes:
            # the page's size when the aspect ratios match (the usual case), else fitted inside
            scale = min(pdf.w / thumb_size[0], pdf.h / thumb_size[1])
            w, h = thumb_size[0] * scale, thumb_size[1] * scale
            self.picture(thumbnail, (pdf.w - w) / 2, (pdf.h - h) / 2, w, h, f"Thumbnail: {self.title}", border=False)
            return
        width = pdf.w - 2 * MARGIN
        if thumbnail is not None and thumb_size is not None:
            w, h, x = self.notes_layout()
            h = w * thumb_size[1] / thumb_size[0]
            self.picture(thumbnail, x, MARGIN + 24, w, h, f"Thumbnail: {self.title}", border=True)
            top = MARGIN + 24 + h + 36
        else:
            top = pdf.h * 0.32
        pdf.set_xy(MARGIN, top)
        pdf.set_text_color(*INK)
        pdf.set_font(SANS_FAMILY, "B", 30 if notes else 40)
        pdf.multi_cell(width, (30 if notes else 40) * 1.2, self.title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*MUTED)
        if subtitle:
            pdf.ln(8)
            pdf.set_font(SANS_FAMILY, "", 16 if notes else 20)
            pdf.multi_cell(width, (16 if notes else 20) * 1.35, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        if byline:
            pdf.ln(16)
            pdf.set_font(SANS_FAMILY, "", 13)
            pdf.multi_cell(width, 18, byline, align="C", new_x="LMARGIN", new_y="NEXT")
        if notes:
            pdf.ln(10)
            pdf.set_font(SANS_FAMILY, "", 11)
            length = format_time(self.deck.duration).rsplit(".", 1)[0]
            pdf.multi_cell(width, 16, f"{slides} slides with speaker notes · {length} of narration", align="C", new_x="LMARGIN", new_y="NEXT")

    def slide(self, slide: DeckSlide, data: bytes, marks: list[tuple[str, int]]) -> None:
        """A full-page slide; ``marks``: its outline entries (name, level)."""
        self.chrome = False
        self.pdf.add_page(orientation="P", format=self.slide_page)
        for name, level in marks:
            self.bookmark(name, level)
        self.picture(data, 0, 0, self.pdf.w, self.pdf.h, slide.alt_text(), border=False)

    def notes_page(self, slide: DeckSlide, data: bytes, count: int, marks: list[tuple[str, int]]) -> None:
        """The slide's picture with its narration below (continued on further pages if long);
        ``marks``: its outline entries (name, level)."""
        pdf = self.pdf
        self.chrome = True
        self.chapter = _chapter_line(slide)
        pdf.set_auto_page_break(True, margin=MARGIN)
        pdf.add_page(orientation="P", format=self.paper)
        for name, level in marks:
            self.bookmark(name, level)
        w, h, x = self.notes_layout()
        self.picture(data, x, MARGIN + 6, w, h, slide.alt_text(), border=True)
        width = pdf.w - 2 * MARGIN
        pdf.set_xy(MARGIN, MARGIN + 6 + h + 14)
        pdf.set_font(SANS_FAMILY, "", 9)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(width, 12, _where(slide, count), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)
        if not slide.beats:
            pdf.set_font(SANS_FAMILY, "I", 11)
            pdf.multi_cell(width, 16, "No narration (a silent scene).", align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*INK)
        for number, beat in enumerate(slide.beats):
            if number:
                pdf.ln(7)
            pdf.set_font(SANS_FAMILY, "", 11.5)
            pdf.multi_cell(width, 17, " ".join(beat.text.split()), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_auto_page_break(False)

    def output(self) -> bytes:
        return bytes(self.pdf.output())


def _fit(pdf: Any, text: str, width: float) -> str:
    """``text`` cut with an ellipsis to fit ``width`` points in the current font."""
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def write_pdf(deck: Deck, options: PdfOptions) -> tuple[bytes, int, tuple[int, int], int, Path | None]:
    """The PDF of ``deck``: its bytes, page count, picture size, outline entries and the
    thumbnail used on the title page (``None``: none, or no title page)."""
    pictures = [encode_still(s.still, options.image_format, options.quality, options.max_width) for s in deck.slides]
    fmt = deck.format
    size = (pictures[0][1], pictures[0][2]) if pictures else (fmt.width, fmt.height)
    writer = _Writer(deck, options, size)
    writer.metadata()
    thumbnail = _thumbnail(deck.project, deck.preview) if options.title_page else None
    if options.title_page:
        thumb = encode_still(thumbnail, options.image_format, options.quality) if thumbnail is not None else None
        writer.title_page(None if thumb is None else thumb[0], None if thumb is None else thumb[1:], len(deck.slides))
    chapter = None
    count = len(deck.slides)
    for slide, (data, _, _) in zip(deck.slides, pictures):
        # outline: chapters at the top level, their slides under them (slides before the first
        # chapter at the top level)
        marks: list[tuple[str, int]] = []
        if slide.chapter is not None and slide.chapter != chapter:
            chapter = slide.chapter
            marks.append((_chapter_line(slide), 0))
        marks.append((f"{slide.index}. {slide.scene_title or slide.scene}", 0 if chapter is None else 1))
        if options.notes:
            writer.notes_page(slide, data, count, marks)
        else:
            writer.slide(slide, data, marks)
    return writer.output(), writer.pdf.page_no(), size, writer.bookmarks, thumbnail


def make_slides_pdf(
    project: Project,
    *,
    preview: bool = True,
    mode: DeckMode = "beat",
    per_beat: int = 1,
    overlays: bool = True,
    dedupe: bool = True,
    notes: bool = False,
    title_page: bool = False,
    paper: str = "a4",
    image_format: str = "jpeg",
    quality: int = DEFAULT_PDF_QUALITY,
    max_width: int | None = None,
    output: Path | None = None,
    jobs: int = 1,
    force: bool = False,
) -> PdfResult:
    """Render what is needed and write the PDF deck of ``project`` (loaded with its variant).

    Slide choice (``mode``, ``per_beat``, ``overlays``, ``dedupe``, ``jobs``, ``force``) as in
    :func:`~vidgen.deck.deck_frames`. ``notes``: a notes page per slide on ``paper`` (``a4`` /
    ``letter``) instead of full-page slides; ``title_page``: a first page with the thumbnail,
    title, author and date; pictures as ``jpeg`` (``quality`` 1-100) or ``png``, scaled down to
    ``max_width`` px; ``output``: the file (default :func:`pdf_path`).
    """
    if image_format not in PDF_IMAGE_FORMATS:
        raise VidgenError(f"--image-format must be one of {', '.join(PDF_IMAGE_FORMATS)} for a PDF deck")
    if not 1 <= quality <= 100:
        raise VidgenError("--quality must be between 1 and 100")
    if max_width is not None and max_width < MIN_WIDTH:
        raise VidgenError(f"--max-width must be at least {MIN_WIDTH} pixels")
    if paper not in PAPER_SIZES:
        raise VidgenError(f"--paper must be one of {', '.join(PAPER_SIZES)}")
    path = output if output is not None else pdf_path(project, preview, notes)
    if path.suffix.lower() != ".pdf":
        raise VidgenError(f"--output must be a .pdf file, not {path.name}")
    _fpdf()  # before rendering: say early that fpdf2 is missing
    deck = deck_frames(
        project, preview=preview, mode=mode, per_beat=per_beat, overlays=overlays, dedupe=dedupe, jobs=jobs, force=force
    )
    options = PdfOptions(notes, title_page, paper, image_format, quality, max_width)
    data, pages, size, bookmarks, thumbnail = write_pdf(deck, options)
    write_bytes_atomic(path, data)
    return PdfResult(path, len(data), pages, options, size[0], size[1], bookmarks, thumbnail, deck)
