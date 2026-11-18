"""``vidgen still``: single frames of a ``web`` scene's page without rendering its clip (DESIGN.md §120.3).

:func:`make_web_stills` builds the scene as the render worker does (the same project, format,
theme and scene class), asks it what its page's frames are drawn from
(:meth:`vidgen.scenes.web.Web.page_clip_args`: size, frame rate, frame count, theme, ``data``,
beats, shape), opens the page with those in one Chromium (:class:`~vidgen.web.page.WebPage`) and
takes the frames asked for. Nothing is written into the project's ``build/`` folder but what
loading a project writes there anyway.
"""

from __future__ import annotations

import difflib
import io
import logging
import math
import re
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic
from vidgen.project import Project
from vidgen.web.entry import entry_of, entry_path, is_web_type
from vidgen.web.inputs import design_width_of
from vidgen.web.page import WebPage

log = logging.getLogger("vidgen.web")

#: The qualities ``--size`` names (a project's formats); anything else is ``WxH``.
QUALITIES: tuple[str, ...] = ("final", "preview", "draft")
#: Width of a contact sheet (pixels) and the most columns chosen without ``--columns``.
SHEET_WIDTH = 1920
SHEET_AUTO_COLUMNS = 6
SHEET_MAX_COLUMNS = 12
#: Colours of a contact sheet: its background and its labels.
SHEET_BACKGROUND = (0, 0, 0)
SHEET_TEXT = (230, 230, 230)
_SIZE = re.compile(r"(\d+)\s*[xX×]\s*(\d+)")


@dataclass(frozen=True)
class Moment:
    """One still asked for: ``kind`` ``at`` (seconds from the scene's start) or ``frame`` (a
    frame number at the size's frame rate) and its ``value``."""

    kind: str
    value: float


@dataclass(frozen=True)
class WebStill:
    """A still written: its file, the frame drawn, that frame's time (``frame / fps``, seconds
    from the scene's start) and how long drawing it took (stepping to it included)."""

    path: Path
    frame: int
    time: float
    seconds: float


@dataclass
class StillResult:
    """What :func:`make_web_stills` made."""

    scene: str
    type: str
    entry: str
    size: str
    width: int
    height: int
    fps: int
    frames: int
    region: str
    exact: bool
    transparent: bool
    stills: list[WebStill] = field(default_factory=list)
    sheet: Path | None = None
    #: Seconds until the first page was ready (Chromium started, the page loaded, ``load(ctx)`` run).
    load_seconds: float = 0.0
    #: Pages opened: 1, plus one for every still earlier than the one before it.
    pages: int = 0


def parse_size(text: str) -> tuple[str, tuple[int, int] | None]:
    """``--size``: a quality of :data:`QUALITIES` (``(name, None)``) or ``WxH`` (``("WxH", (w, h))``)."""
    name = text.strip().lower()
    if name in QUALITIES:
        return name, None
    match = _SIZE.fullmatch(name)
    if match is None:
        close = difflib.get_close_matches(name, QUALITIES, n=1)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        raise VidgenError(f"--size {text}: expected final, preview, draft or WIDTHxHEIGHT (e.g. 640x360){hint}")
    width, height = int(match[1]), int(match[2])
    return f"{width}x{height}", (width, height)


def still_project(path: str | Path, variant: str | None, size: str) -> tuple[Project, bool, str]:
    """The project loaded for stills of ``size`` (:func:`parse_size`), whether it renders as a
    preview, and the size's name. ``WxH``: the final render with that frame size (its frame rate
    kept), so the page is laid out for a video of that size."""
    from pydantic import ValidationError

    from vidgen.config import FormatConfig

    name, pixels = parse_size(size)
    project = Project.load(path, variant=variant, draft=name == "draft")
    if pixels is not None:
        try:
            fmt = FormatConfig(width=pixels[0], height=pixels[1], fps=project.config.format.fps)
        except ValidationError as exc:
            raise VidgenError(f"--size {size}: {exc.errors()[0]['msg'].removeprefix('Value error, ')}") from None
        project.config = project.config.model_copy(update={"format": fmt})
    return project, name in ("preview", "draft"), name


def web_scene_spec(project: Project, scene_id: str) -> Any:
    """The scene ``scene_id`` of an activated ``project``, checked to show a page: an unknown id
    or a scene of another type is a :class:`VidgenError` saying what to use instead."""
    known = [s.id for s in project.config.scenes]
    if scene_id not in known:
        close = difflib.get_close_matches(scene_id, known, n=1)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        web = [s.id for s in project.config.scenes if is_web_type(s.type)]
        raise VidgenError(f"unknown scene '{scene_id}'{hint} (web scenes: {', '.join(web) or 'none'})")
    spec = project.scene(scene_id)
    if not is_web_type(spec.type):
        raise VidgenError(
            f"scene '{scene_id}' is a {spec.type} scene: vidgen still draws the page of a web scene (type web, or an "
            f"extension type that subclasses Web). For frames of this scene use vidgen storyboard --scene {scene_id} "
            "--per-beat N (stills of its beats; it renders the scene)"
        )
    return spec


def page_setup(project: Project, preview: bool, scene_id: str) -> tuple[dict[str, Any], str, str]:
    """What the render draws the page of ``scene_id`` from (:meth:`Web.page_clip_args`), the
    video's background colour and the scene's type: the scene is built here as the render worker
    builds it (Manim configured for the format, the project's extensions loaded), but not
    rendered. Manim's settings are put back afterwards."""
    from manim import tempconfig

    from vidgen import extensions, registry
    from vidgen.fonts import register_bundled_fonts
    from vidgen.render.worker import configure_manim

    register_bundled_fonts()
    with extensions.project_session(project) as theme:
        spec = web_scene_spec(project, scene_id)
        cls = registry.get(spec.type).cls
        with tempfile.TemporaryDirectory(prefix="vidgen_still_") as media, tempconfig({}):
            configure_manim(project, preview, theme.background, Path(media), scene_id, False)
            scene = cls(spec, project, theme, audio=False)
            scene.is_preview = preview
            args = scene.page_clip_args()
        return args, str(theme.background), spec.type


def frame_numbers(moments: Sequence[Moment], count: int | None, *, fps: int, frames: int, scene_id: str) -> list[int]:
    """The frames to draw, in the order asked: ``at`` seconds is the frame ``round(t * fps)``
    (the frame the render shows at that time); ``count`` adds that many frames spread evenly
    over the scene (the middle of each of ``count`` equal parts). A time or frame outside the
    scene is a :class:`VidgenError` naming the scene's range."""
    last = frames - 1
    span = f"scene '{scene_id}' has frames 0 to {last} at {fps} fps (0 to {last / fps:.3f} s)"
    out: list[int] = []
    for moment in moments:
        if moment.kind == "at":
            n = round(moment.value * fps)
            if not (math.isfinite(moment.value) and 0 <= n <= last):
                raise VidgenError(f"--at {moment.value:g}: outside the scene; {span}; --at counts seconds from the scene's start")
        else:
            n = int(moment.value)
            if not 0 <= n <= last:
                raise VidgenError(f"--frame {n}: outside the scene; {span}")
        out.append(n)
    if count is not None:
        if count < 1:
            raise VidgenError("--count must be at least 1")
        out += [min(last, int((i + 0.5) * frames / count)) for i in range(count)]
    if not out:
        raise VidgenError("which frames? give --at SECONDS (seconds from the scene's start; repeatable), --frame N or --count N")
    return out


def still_paths(numbers: Sequence[int], *, fps: int, scene_id: str, out: Path | None, default_dir: Path) -> list[Path]:
    """Where each still goes: ``out`` when it names a ``.png`` file (one still only), else
    ``<scene>_<seconds>s.png`` (``intro_0012.500s.png``) in the folder ``out`` (default
    ``default_dir``)."""
    if out is not None and out.suffix.lower() == ".png":
        if len(set(numbers)) != 1:
            raise VidgenError(f"--out {out} names one file, but {len(set(numbers))} stills were asked for: give a folder (--out DIR)")
        return [out] * len(numbers)
    if out is not None and out.suffix:
        raise VidgenError(f"--out {out}: stills are PNG files; give a .png file or a folder")
    folder = out if out is not None else default_dir
    return [folder / f"{scene_id}_{n / fps:08.3f}s.png" for n in numbers]


def over_background(pixels: np.ndarray, background: str) -> np.ndarray:
    """RGBA ``pixels`` (straight alpha) over the colour ``background`` (``#RRGGBB``), as RGB."""
    colour = np.array([int(background.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)
    alpha = pixels[..., 3:4].astype(np.float64) / 255.0
    return np.rint(pixels[..., :3] * alpha + colour * (1.0 - alpha)).astype(np.uint8)


def _png(pixels: np.ndarray) -> bytes:
    from PIL import Image

    data = io.BytesIO()
    Image.fromarray(pixels).save(data, format="PNG")
    return data.getvalue()


def sheet_columns(count: int, columns: int | None) -> int:
    """Columns of a contact sheet of ``count`` stills: ``columns``, else up to
    :data:`SHEET_AUTO_COLUMNS` in rows about as many as columns."""
    if columns is not None:
        if not 1 <= columns <= SHEET_MAX_COLUMNS:
            raise VidgenError(f"--columns must be 1 to {SHEET_MAX_COLUMNS}")
        return columns
    return max(1, min(SHEET_AUTO_COLUMNS, math.ceil(math.sqrt(count))))


def contact_sheet(tiles: Sequence[tuple[np.ndarray, str]], columns: int, width: int = SHEET_WIDTH) -> Any:
    """A contact sheet (PIL image) of ``tiles`` (RGB pixels and a label each), ``columns`` to a
    row, each scaled to fit ``width / columns`` (never enlarged) with its label underneath."""
    from PIL import Image, ImageDraw

    from vidgen.sheets import load_font

    height, full = tiles[0][0].shape[:2]
    tile_w = min(full, width // columns)
    tile_h = max(1, round(tile_w * height / full))
    font_px = max(11, min(22, tile_w // 16))
    font = load_font(font_px)
    band = font_px + 8
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new("RGB", (columns * tile_w, rows * (tile_h + band)), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for i, (pixels, label) in enumerate(tiles):
        x, y = (i % columns) * tile_w, (i // columns) * (tile_h + band)
        picture = Image.fromarray(pixels)
        if picture.size != (tile_w, tile_h):
            picture = picture.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        sheet.paste(picture, (x, y))
        draw.text((x + 4, y + tile_h + 3), label, fill=SHEET_TEXT, font=font)
    return sheet


def still_label(scene_id: str, n: int, fps: int) -> str:
    """A still's label on a contact sheet: ``intro  12.500 s  f375``."""
    return f"{scene_id}  {n / fps:.3f} s  f{n}"


def make_web_stills(
    project_path: str | Path,
    scene_id: str,
    *,
    moments: Sequence[Moment] = (),
    count: int | None = None,
    size: str = "final",
    variant: str | None = None,
    out: Path | None = None,
    sheet: Path | None = None,
    columns: int | None = None,
    exact: bool = False,
    transparent: bool = False,
    on_still: Callable[[WebStill], None] | None = None,
) -> StillResult:
    """Write stills of the page of the ``web`` scene ``scene_id``: PNG files of the frames
    ``moments`` (and ``count``, :func:`frame_numbers`) name, at ``size`` (:func:`parse_size`),
    to ``out`` (:func:`still_paths`; default ``<project>/exports/stills/``), and with ``sheet``
    a contact sheet of them (``columns`` to a row).

    Each still is the picture the render's page clip holds for that frame: the same page, clock,
    theme, ``data``, beats, size and frame rate. The frames are drawn in the order asked, on one
    page while each is later than the one before (the clock only runs forward: an earlier frame
    opens a new page). Without ``exact`` the clock moves straight to a frame's time, which is
    the render's picture for a page that draws from the time alone; with ``exact`` the page is
    first stepped through every frame before it, as the render steps it (for a page that keeps
    state from frame to frame). ``transparent`` keeps the page's alpha; otherwise the picture is
    laid over the video's background colour. ``on_still`` is called after each still is written.
    """
    project, preview, size_name = still_project(project_path, variant, size)
    args, background, scene_type = page_setup(project, preview, scene_id)
    fps, frames, (width, height) = int(args["fps"]), int(args["frames"]), args["size"]
    numbers = frame_numbers(moments, count, fps=fps, frames=frames, scene_id=scene_id)
    paths = still_paths(numbers, fps=fps, scene_id=scene_id, out=out, default_dir=project.exports_dir / "stills")
    if sheet is not None and sheet.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise VidgenError(f"--sheet {sheet}: give a .png or .jpg file")
    sheet_cols = sheet_columns(len(numbers), columns) if sheet is not None else 0
    params = args["params"]
    entry = entry_of(params)
    entry_path(args["root"], entry, scene_id)
    result = StillResult(scene=scene_id, type=scene_type, entry=entry.posix, size=size_name, width=width, height=height, fps=fps,
                         frames=frames, region=str(args["shape"]["region"]), exact=exact, transparent=transparent)
    tiles: list[tuple[np.ndarray, str]] = []
    drawn: dict[int, np.ndarray] = {}
    page: WebPage | None = None
    at = -1   # the frame the open page stands at

    def open_page() -> WebPage:
        from vidgen.web.clip import scene_data

        started = time.monotonic()
        opened = WebPage(args["root"], entry, scene_id=scene_id, size=(width, height), fps=fps, frames=frames, theme=args["theme"],
                         data=scene_data(params), beats=[dict(b) for b in args["beats"]], shape=args["shape"],
                         design_width=design_width_of(params), music=args.get("music"),
                         orbits=args.get("orbits")).__enter__()
        if result.pages == 0:
            result.load_seconds = time.monotonic() - started
        result.pages += 1
        return opened

    try:
        for n, path in zip(numbers, paths):
            started = time.monotonic()
            if n not in drawn:
                if page is None or n <= at:
                    if page is not None:
                        log.info("%s: frame %d is not after frame %d: opening the page again", scene_id, n, at)
                        page.close()
                    page, at = open_page(), -1
                    started = time.monotonic() if result.pages == 1 else started
                if exact:
                    for between in range(at + 1, n):
                        page.advance(between)
                drawn[n] = page.frame(n)
                at = n
            pixels = drawn[n] if transparent else over_background(drawn[n], background)
            write_bytes_atomic(path, _png(pixels))
            still = WebStill(path, n, n / fps, time.monotonic() - started)
            result.stills.append(still)
            tiles.append((over_background(drawn[n], background), still_label(scene_id, n, fps)))
            if on_still is not None:
                on_still(still)
    finally:
        if page is not None:
            page.close()
    if sheet is not None:
        picture = contact_sheet(tiles, sheet_cols)
        data = io.BytesIO()
        if sheet.suffix.lower() == ".png":
            picture.save(data, format="PNG")
        else:
            picture.save(data, format="JPEG", quality=90)
        write_bytes_atomic(sheet, data.getvalue())
        result.sheet = sheet
    return result


__all__ = ["QUALITIES", "Moment", "StillResult", "WebStill", "contact_sheet", "frame_numbers", "make_web_stills", "over_background",
           "page_setup", "parse_size", "sheet_columns", "still_label", "still_paths", "still_project", "web_scene_spec"]
