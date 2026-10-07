"""``vidgen slides``: the video's key frames as one self-contained HTML slide deck (DESIGN.md §55).

The slides come from :func:`vidgen.deck.deck_frames` (shared with the PDF deck of Step 53). The
page embeds every slide picture as a ``data:`` URI (WebP by default, or JPEG / PNG), the beats'
narration as speaker notes, optionally the beats' MP3s for a narrated play mode, and its own
CSS / JS (``vidgen/data/slides/``): keyboard, click and swipe navigation, a notes panel, an
overview grid by chapter, fullscreen, a slide counter and the slide number in the URL hash. No
network access is needed to open it. ``separate=True`` writes the pictures (and MP3s) into a
``<name>_files/`` folder beside the page instead.
"""

from __future__ import annotations

import base64
import html
import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from vidgen import DIST_NAME, __version__
from vidgen.deck import Deck, DeckMode, DeckSlide, deck_frames
from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, write_bytes_atomic
from vidgen.project import Project
from vidgen.sheets import format_time

log = logging.getLogger("vidgen")

IMAGE_FORMATS: tuple[str, ...] = ("webp", "jpeg", "png")
DEFAULT_IMAGE_FORMAT = "webp"
DEFAULT_QUALITY = 80
#: Smallest ``max_width`` accepted (px).
MIN_WIDTH = 160
#: A page bigger than this gets a warning (suggesting ``--quality`` / ``--max-width`` / ``--separate``).
LARGE_PAGE_BYTES = 50_000_000
_MIME = {"webp": "image/webp", "jpeg": "image/jpeg", "png": "image/png"}
_SUFFIX = {"webp": ".webp", "jpeg": ".jpg", "png": ".png"}
_ASSETS = Path(__file__).resolve().parent / "data" / "slides"


@dataclass
class SlidesResult:
    """What :func:`make_slides` wrote: the page (``path``, ``bytes``), the folder of separate
    files (``None`` when everything is embedded), the picture format / quality / size, the
    number of MP3s included and the :class:`~vidgen.deck.Deck` it shows."""

    path: Path
    bytes: int
    files_dir: Path | None
    image_format: str
    quality: int
    width: int
    height: int
    audio: int
    deck: Deck


def slides_path(project: Project, preview: bool) -> Path:
    """The default page: ``exports/<output>[_<variant>][_preview]_slides.html``."""
    return project.exports_dir / f"{project.export_stem(preview)}_slides.html"


def encode_still(path: Path, image_format: str, quality: int, max_width: int | None = None) -> tuple[bytes, int, int]:
    """The still at ``path`` encoded as ``image_format`` (``webp`` / ``jpeg`` at ``quality``
    1-100, lossless ``png``), scaled down to ``max_width`` px if wider; returns the bytes and
    the size."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    if max_width is not None and image.width > max_width:
        image = image.resize((max_width, max(1, round(image.height * max_width / image.width))), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    if image_format == "webp":
        image.save(buffer, format="WEBP", quality=quality, method=4)
    elif image_format == "jpeg":
        image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), image.width, image.height


def _data_uri(mime: str, payload: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def _where(slide: DeckSlide) -> str:
    """``2 · Results — Feedback loop``: chapter and scene title (or id)."""
    parts = []
    if slide.chapter is not None:
        parts.append(f"{slide.chapter.label} · {slide.chapter.title}")
    parts.append(slide.scene_title or slide.scene)
    return " — ".join(parts)


def _notes_html(slide: DeckSlide, count: int) -> str:
    meta = [f"Slide {slide.index} / {count}", f"scene {slide.scene_number} <b>{html.escape(slide.scene)}</b> ({html.escape(slide.scene_type)})"]
    if slide.chapter is not None:
        meta.insert(1, html.escape(f"chapter {slide.chapter.label} · {slide.chapter.title}"))
    if slide.n > 1:
        meta.append(f"still {slide.k}/{slide.n} of its beat")
    if slide.time is not None:
        meta.append(f"{format_time(slide.time)} in the video")
    body = [f'<p class="meta">{" · ".join(meta)}</p>']
    if slide.beats:
        body.extend(f'<p data-beat="{html.escape(b.id)}">{html.escape(" ".join(b.text.split()))}</p>' for b in slide.beats)
    else:
        body.append('<p class="silent">No narration (a silent scene).</p>')
    return f'<div class="notes">{"".join(body)}</div>'


def _overview_html(deck: Deck, width: int, height: int) -> str:
    groups: list[tuple[str | None, list[DeckSlide]]] = []
    for slide in deck.slides:
        heading = None if slide.chapter is None else f"{slide.chapter.label} · {slide.chapter.title}"
        if not groups or groups[-1][0] != heading:
            groups.append((heading, []))
        groups[-1][1].append(slide)
    sections = []
    for heading, members in groups:
        thumbs = "".join(
            f'<button class="thumb" type="button" data-index="{s.index - 1}" aria-label="Slide {s.index}: {html.escape(s.scene_title or s.scene, quote=True)}">'
            f'<img alt="" width="{width}" height="{height}"><span>{s.index} · {html.escape(s.scene_title or s.scene)}</span></button>'
            for s in members
        )
        title = "" if heading is None else f"<h3>{html.escape(heading)}</h3>"
        sections.append(f'<section>{title}<div class="grid">{thumbs}</div></section>')
    return "".join(sections)


_HELP_ROWS = (
    ("<kbd>→</kbd> <kbd>↓</kbd> <kbd>Space</kbd> <kbd>PgDn</kbd> <kbd>Enter</kbd>, click right", "next slide"),
    ("<kbd>←</kbd> <kbd>↑</kbd> <kbd>Shift</kbd>+<kbd>Space</kbd> <kbd>PgUp</kbd>, click left", "previous slide"),
    ("swipe left / right", "next / previous slide"),
    ("<kbd>Home</kbd> / <kbd>End</kbd>", "first / last slide"),
    ("number, then <kbd>Enter</kbd>", "go to that slide"),
    ("<kbd>S</kbd> or <kbd>N</kbd>", "speaker notes (the narration) beside the slide"),
    ("<kbd>O</kbd>", "overview of all slides, by chapter"),
    ("<kbd>F</kbd>", "fullscreen"),
    ("<kbd>P</kbd>", "play / pause: the slides follow the video's timing (with narration when included)"),
    ("<kbd>?</kbd>", "this help"),
    ("<kbd>Esc</kbd>", "close the overview or help; stop playing"),
)


def _icon(paths: str) -> str:
    return (
        '<svg class="icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )


_ICONS = {
    "btn-prev": _icon('<path d="M15 18l-6-6 6-6"/>'),
    "btn-next": _icon('<path d="M9 18l6-6-6-6"/>'),
    "btn-play": _icon('<path class="i-play" d="M7 4l13 8-13 8z"/><path class="i-pause" d="M8 5v14M16 5v14"/>'),
    "btn-notes": _icon('<path d="M4 6h16M4 12h16M4 18h10"/>'),
    "btn-overview": _icon('<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/>'),
    "btn-fullscreen": _icon('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
    "btn-help": _icon('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.5h.01"/>'),
}


def slides_html(deck: Deck, images: list[str], size: tuple[int, int], audio: dict[str, str]) -> str:
    """The deck page: ``images`` are the slides' picture URLs (``data:`` URIs or relative paths)
    in slide order, ``size`` their pixel size, ``audio`` beat id -> MP3 URL for the beats to
    include (empty: no sound)."""
    project = deck.project
    title = project.config.title
    count = len(deck.slides)
    width, height = size
    sections = []
    for slide, src in zip(deck.slides, images):
        alt = html.escape(slide.alt_text(), quote=True)
        hidden = "" if slide.index == 1 else " hidden"
        sections.append(
            f'<section class="slide" id="slide-{slide.index}" role="group" aria-roledescription="slide" '
            f'aria-label="{slide.index} of {count}"{hidden}>'
            f'<img src="{src}" alt="{alt}" width="{width}" height="{height}" decoding="async" draggable="false">'
            f"{_notes_html(slide, count)}</section>"
        )
    clips = [c for c in deck.clips if c.beat in audio]
    data: dict[str, Any] = {
        "generator": f"{DIST_NAME} {__version__}",
        "title": title,
        "count": count,
        "mode": deck.mode,
        "duration": deck.duration,
        "slides": [
            {
                "scene": s.scene,
                "type": s.scene_type,
                "beats": [b.id for b in s.beats],
                "chapter": None if s.chapter is None else s.chapter.title,
                "where": _where(s),
                "at": s.at,
                "until": s.until,
                "time": s.time,
            }
            for s in deck.slides
        ],
        "clips": [{"id": f"audio-{c.beat}", "beat": c.beat, "at": c.at, "duration": c.duration} for c in clips],
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    audio_tags = "".join(f'<audio id="audio-{html.escape(c.beat)}" preload="auto" src="{audio[c.beat]}"></audio>' for c in clips)
    help_rows = "".join(f"<tr><td>{keys}</td><td>{what}</td></tr>" for keys, what in _HELP_ROWS)
    css = (_ASSETS / "deck.css").read_text(encoding="utf-8")
    script = (_ASSETS / "deck.js").read_text(encoding="utf-8")
    language = html.escape(project.config.language or "en", quote=True)
    sound = "with narration" if clips else "timed like the video"

    def button(ident: str, label: str, key: str, extra: str = "") -> str:
        return (
            f'<button class="btn" id="{ident}" type="button" title="{label} ({key})"{extra}>'
            f'{_ICONS[ident]}<span class="label">{label}</span><span class="key">{key}</span></button>'
        )

    return f"""<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="{DIST_NAME} {html.escape(__version__)}">
<title>{html.escape(title)}</title>
<style>
{css}.thumb img {{ --ratio: {width} / {height}; }}
</style>
</head>
<body>
<div class="deck" id="deck">
<header class="bar top"><span class="deck-title">{html.escape(title)}</span><span class="where" id="where"></span></header>
<main class="stage" id="stage" tabindex="-1" aria-label="Slides">
{"".join(sections)}
</main>
<aside class="notes-panel" id="notes-panel" aria-label="Speaker notes" hidden></aside>
<footer class="bar bottom">
{button("btn-prev", "Previous", "←", ' aria-label="Previous slide"')}
<span class="counter" id="counter" aria-hidden="true">1 / {count}</span>
{button("btn-next", "Next", "→", ' aria-label="Next slide"')}
<span class="spacer"></span>
{button("btn-play", "Play", "P", f' aria-pressed="false" aria-label="Play ({sound})"')}
{button("btn-notes", "Notes", "S", ' aria-pressed="false"')}
{button("btn-overview", "Overview", "O")}
{button("btn-fullscreen", "Fullscreen", "F")}
{button("btn-help", "Help", "?")}
</footer>
</div>
<div class="layer overview" id="overview" role="dialog" aria-label="All slides" hidden>
<div class="layer-head"><h2>{html.escape(title)} · {count} slides</h2><button class="btn" id="btn-close-overview" type="button">Close <span class="key">Esc</span></button></div>
{_overview_html(deck, width, height)}
</div>
<div class="layer help" id="help" role="dialog" aria-label="Keyboard shortcuts" hidden>
<div class="layer-head"><h2>Keyboard and mouse</h2><button class="btn" id="btn-close-help" type="button">Close <span class="key">Esc</span></button></div>
<table>{help_rows}</table>
</div>
<div class="jump" id="jump" aria-hidden="true" hidden></div>
<div class="sr-only" id="live" aria-live="polite"></div>
<div hidden>{audio_tags}</div>
<script type="application/json" id="deck-data">{payload}</script>
<script>
{script}</script>
</body>
</html>
"""


def _files_dir(path: Path) -> Path:
    return path.with_name(f"{path.stem}_files")


def _clear_files(folder: Path) -> None:
    """Remove what an earlier run wrote there (slide pictures and MP3s)."""
    if not folder.is_dir():
        return
    for old in sorted(folder.iterdir()):
        if old.is_file() and (old.name.startswith("slide-") or old.suffix == ".mp3"):
            remove_file(old)


def make_slides(
    project: Project,
    *,
    preview: bool = True,
    mode: DeckMode = "beat",
    per_beat: int = 1,
    overlays: bool = True,
    dedupe: bool = True,
    image_format: str = DEFAULT_IMAGE_FORMAT,
    quality: int = DEFAULT_QUALITY,
    max_width: int | None = None,
    audio: bool = False,
    separate: bool = False,
    output: Path | None = None,
    jobs: int = 1,
    force: bool = False,
) -> SlidesResult:
    """Render what is needed and write the HTML deck of ``project`` (loaded with its variant).

    Slide choice (``mode``, ``per_beat``, ``overlays``, ``dedupe``, ``jobs``, ``force``) as in
    :func:`~vidgen.deck.deck_frames`. ``image_format`` ``webp`` / ``jpeg`` / ``png`` at
    ``quality`` (1-100; not used by PNG), scaled down to ``max_width`` px; ``audio``: include the
    beats' MP3s for the play mode; ``separate``: write pictures and MP3s into ``<name>_files/``
    beside the page instead of embedding them; ``output``: the page (default :func:`slides_path`).
    """
    if image_format not in IMAGE_FORMATS:
        raise VidgenError(f"--image-format must be one of {', '.join(IMAGE_FORMATS)}")
    if not 1 <= quality <= 100:
        raise VidgenError("--quality must be between 1 and 100")
    if max_width is not None and max_width < MIN_WIDTH:
        raise VidgenError(f"--max-width must be at least {MIN_WIDTH} pixels")
    path = output if output is not None else slides_path(project, preview)
    if path.suffix.lower() not in (".html", ".htm"):
        raise VidgenError(f"--output must be an .html file, not {path.name}")
    deck = deck_frames(
        project, preview=preview, mode=mode, per_beat=per_beat, overlays=overlays, dedupe=dedupe, jobs=jobs, force=force
    )
    files_dir = _files_dir(path) if separate else None
    if files_dir is not None:
        _clear_files(files_dir)
    images: list[str] = []
    size = (deck.format.width, deck.format.height)
    for slide in deck.slides:
        payload, w, h = encode_still(slide.still, image_format, quality, max_width)
        size = (w, h)
        if files_dir is None:
            images.append(_data_uri(_MIME[image_format], payload))
        else:
            name = f"slide-{slide.index:03d}{_SUFFIX[image_format]}"
            write_bytes_atomic(files_dir / name, payload)
            images.append(f"{files_dir.name}/{name}")
    sounds: dict[str, str] = {}
    if audio:
        for clip in deck.clips:
            if files_dir is None:
                sounds[clip.beat] = _data_uri("audio/mpeg", clip.audio.read_bytes())
            else:
                write_bytes_atomic(files_dir / clip.audio.name, clip.audio.read_bytes())
                sounds[clip.beat] = f"{files_dir.name}/{clip.audio.name}"
        if not deck.clips:
            log.warning("slides: --audio given but no beat has an MP3 in %s (run `vidgen tts`); the deck plays silently", project.audio_dir)
    page = slides_html(deck, images, size, sounds).encode("utf-8")
    write_bytes_atomic(path, page)
    written = len(page)
    if written > LARGE_PAGE_BYTES:
        log.warning(
            "slides: %s is %.0f MB; lower --quality or --max-width, or use --separate", path.name, written / 1e6
        )
    return SlidesResult(
        path=path,
        bytes=written,
        files_dir=files_dir,
        image_format=image_format,
        quality=quality,
        width=size[0],
        height=size[1],
        audio=len(sounds),
        deck=deck,
    )
