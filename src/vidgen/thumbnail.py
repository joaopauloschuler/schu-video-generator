"""The video's thumbnail (DESIGN.md §53): ``<output>[_<variant>][_preview]_thumbnail.png``.

Two kinds, chosen by the ``thumbnail:`` config (:class:`vidgen.config.ThumbnailConfig`):

- a **frame** of a scene (``scene``, ``beat``, ``at``): read from the scene's render (rendered
  first when it is missing or stale by its fingerprint), with the video's overlays, or with
  ``overlays: false`` from a render of the project :meth:`~vidgen.project.Project.without_overlays`
  in ``build/..._bare``;
- a **designed** title card (``title``, ``subtitle``, ``icon`` / ``image``, ``preset`` /
  ``background``) drawn with Pillow in the theme's colours and fonts: one big bold title sized
  to fill its box, legible when YouTube shows it small.

Both are cover-fitted to :func:`thumbnail_size` (1280x720 for 16:9 video, 1080x1920 for 9:16,
1080x1080 for square). A copy downscaled to :data:`SMALL_LONG_SIDE` px (YouTube's grid size)
goes to ``build/.../thumbnail/`` for review, and lint-like :class:`ThumbnailCheck` s measure the
designed card's text at that size and its contrast (WCAG ratio from :mod:`vidgen.lint.color`).
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from vidgen.config import FormatConfig, ThemeConfig, ThumbnailConfig
from vidgen.errors import Problem, VidgenError
from vidgen.fileio import remove_file, write_bytes_atomic
from vidgen.lint.color import contrast_ratio, hex_rgb
from vidgen.project import Project
from vidgen.scales import frame_orientation
from vidgen.theme import Theme

#: Thumbnail pixel size per frame orientation (YouTube: 1280x720; Shorts / vertical: 1080x1920).
THUMBNAIL_SIZES: dict[str, tuple[int, int]] = {"landscape": (1280, 720), "portrait": (1080, 1920), "square": (1080, 1080)}
#: Long side of the small review copy: how big YouTube shows thumbnails in its grids (320x180).
SMALL_LONG_SIDE = 320
#: Smallest readable text at the small size, in px: the title, and any other text.
MIN_TITLE_SMALL_PX = 14.0
MIN_TEXT_SMALL_PX = 10.0
#: WCAG AA ratio the thumbnail's text must reach on its background.
MIN_CONTRAST = 4.5
#: More words than this in the title is an ``info`` (thumbnails read best with a few words).
MAX_TITLE_WORDS = 6
#: YouTube's upload limit for thumbnails.
MAX_BYTES = 2 * 1024 * 1024
#: JPEG qualities tried, best first, until the file is under :data:`MAX_BYTES`.
JPEG_QUALITIES: tuple[int, ...] = (92, 88, 84, 80, 75, 70, 62, 55)


@dataclass(frozen=True)
class ThumbnailCheck:
    """One finding about the thumbnail: ``rule`` (``min_font``, ``contrast``, ``max_words``,
    ``fit``, ``file_size``), ``severity`` (``warning`` or ``info``) and a message."""

    rule: str
    severity: str
    message: str

    def to_json(self) -> dict[str, str]:
        """``{rule, severity, message}``."""
        return {"rule": self.rule, "severity": self.severity, "message": self.message}

    def __str__(self) -> str:
        return f"{self.severity} [{self.rule}]: {self.message}"


@dataclass
class ThumbnailResult:
    """What :func:`make_thumbnail` wrote: the PNG (``width`` x ``height``, ``bytes``), the small
    review copy, the JPEG when asked for, where the picture came from (``source``), the checks
    and the scenes rendered for it."""

    kind: str
    path: Path
    width: int
    height: int
    bytes: int
    small: Path
    jpeg: Path | None = None
    jpeg_bytes: int | None = None
    source: dict[str, Any] = field(default_factory=dict)
    checks: list[ThumbnailCheck] = field(default_factory=list)
    rendered: list[str] = field(default_factory=list)


def thumbnail_size(fmt: FormatConfig) -> tuple[int, int]:
    """The thumbnail size for a video of format ``fmt`` (:data:`THUMBNAIL_SIZES` by orientation)."""
    return THUMBNAIL_SIZES[frame_orientation(fmt.width, fmt.height)]


def small_size(size: tuple[int, int]) -> tuple[int, int]:
    """``size`` scaled so its long side is :data:`SMALL_LONG_SIDE` (1280x720 -> 320x180)."""
    factor = SMALL_LONG_SIDE / max(size)
    return max(1, round(size[0] * factor)), max(1, round(size[1] * factor))


def small_dir(project: Project, preview: bool) -> Path:
    """``build/<final|preview>[_<variant>]/thumbnail``: the small review copy."""
    return project.render_dir(preview) / "thumbnail"


# ----- validation --------------------------------------------------------------------------------


def thumbnail_problems(project: Project, theme: Theme) -> list[Problem]:
    """A designed thumbnail's icon, image, preset and background colour exist (call with the
    project's extensions active; scene and beat are checked by the config itself)."""
    from vidgen.icons import available_icons, resolve_icon, unknown_icon_message

    spec = project.config.thumbnail
    if spec is None or spec.kind != "design":
        return []
    problems: list[Problem] = []
    if spec.icon is not None:
        icons = available_icons(project.root)
        if resolve_icon(spec.icon, icons) is None:
            problems.append(Problem("thumbnail.icon", unknown_icon_message(spec.icon, icons)))
    if spec.image is not None and not (project.root / spec.image).is_file():
        problems.append(Problem("thumbnail.image", f"file not found: {spec.image} (looked for {project.root / spec.image})"))
    try:
        design_theme = _design_theme(theme, spec, project.config.format)
    except VidgenError as exc:
        return [*problems, Problem("thumbnail.preset", str(exc))]
    if spec.background is not None:
        try:
            design_theme.color(spec.background)
        except VidgenError as exc:
            problems.append(Problem("thumbnail.background", str(exc)))
    return problems


# ----- the thumbnail -----------------------------------------------------------------------------


def make_thumbnail(
    project: Project, preview: bool = False, spec: ThumbnailConfig | None = None, jpeg: bool | None = None, jobs: int = 1
) -> ThumbnailResult:
    """Write the thumbnail of ``project`` (with its variant) and its small review copy.

    ``spec``: what to draw (default: the config's ``thumbnail:``, else a designed card of the
    video's title). ``preview``: frames come from the preview render and the files are named
    ``..._preview_thumbnail``. ``jpeg``: also write the JPEG (default: ``spec.jpeg``); without it
    an old JPEG is removed. ``jobs``: workers when scenes must be rendered.
    """
    from vidgen import extensions

    spec = spec if spec is not None else project.config.thumbnail or ThumbnailConfig()
    size = thumbnail_size(project.config.format)
    rendered: list[str] = []
    checks: list[ThumbnailCheck] = []
    if spec.kind == "frame":
        image, source, rendered = _frame_thumbnail(project, preview, spec, jobs)
        if image.width < size[0] and image.height < size[1]:
            checks.append(
                ThumbnailCheck(
                    "resolution", "info",
                    f"the frame is {image.width}x{image.height} ({'the preview render' if preview else 'the render'}), "
                    f"scaled up to {size[0]}x{size[1]}; a final render gives a sharper thumbnail",
                )
            )
    else:
        with extensions.project_session(project) as theme:
            image, source, checks = design_thumbnail(project, theme, spec, size)
    image = ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    path = project.thumbnail_path(preview)
    data = _encode(image, "PNG")
    write_bytes_atomic(path, data)
    small = small_dir(project, preview) / f"{path.stem}_small.png"
    write_bytes_atomic(small, _encode(image.resize(small_size(size), Image.Resampling.LANCZOS), "PNG"))
    result = ThumbnailResult(spec.kind, path, size[0], size[1], len(data), small, source=source, checks=checks, rendered=rendered)
    jpeg_path = project.thumbnail_path(preview, ".jpg")
    if spec.jpeg if jpeg is None else jpeg:
        result.jpeg, result.jpeg_bytes = jpeg_path, _write_jpeg(image, jpeg_path)
    else:
        remove_file(jpeg_path)  # it would show another thumbnail
    result.checks += _size_checks(result)
    return result


def _encode(image: Image.Image, fmt: str, **options: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def _write_jpeg(image: Image.Image, path: Path) -> int:
    """Write ``image`` as the best JPEG quality of :data:`JPEG_QUALITIES` under :data:`MAX_BYTES`
    (the lowest when none is); returns its size."""
    data = b""
    for quality in JPEG_QUALITIES:
        data = _encode(image, "JPEG", quality=quality, optimize=True, progressive=True)
        if len(data) <= MAX_BYTES:
            break
    write_bytes_atomic(path, data)
    return len(data)


def _size_checks(result: ThumbnailResult) -> list[ThumbnailCheck]:
    """YouTube's 2 MB limit: the JPEG when there is one, else the PNG."""
    limit = f"YouTube accepts thumbnails up to {MAX_BYTES // (1024 * 1024)} MB"
    if result.jpeg is not None and result.jpeg_bytes is not None:
        if result.jpeg_bytes > MAX_BYTES:
            return [ThumbnailCheck("file_size", "warning", f"{result.jpeg.name} is {result.jpeg_bytes / 1e6:.1f} MB even at the lowest quality; {limit}")]
        return []
    if result.bytes > MAX_BYTES:
        return [
            ThumbnailCheck(
                "file_size", "warning", f"{result.path.name} is {result.bytes / 1e6:.1f} MB; {limit} (set thumbnail: {{jpeg: true}} or use --jpeg)"
            )
        ]
    return []


# ----- frame thumbnails --------------------------------------------------------------------------


def _frame_thumbnail(project: Project, preview: bool, spec: ThumbnailConfig, jobs: int) -> tuple[Image.Image, dict[str, Any], list[str]]:
    """The frame ``spec`` names, from the scene's render (made first when missing or stale)."""
    from vidgen import extensions, registry
    from vidgen.render.pipeline import render_scenes
    from vidgen.render.worker import scene_timings_path, scene_video_path

    assert spec.scene is not None
    source = project if spec.overlays is not False else project.without_overlays()
    scene = project.scene(spec.scene)
    with extensions.project_session(source):
        outro = float(registry.get(scene.type).cls.outro)
    rendered: list[str] = []
    if not render_current(source, preview, scene.id):
        rendered = render_scenes(source, preview, [scene.id], jobs=jobs).rendered
    timings = json.loads(scene_timings_path(source, preview, scene.id).read_text(encoding="utf-8"))
    frame, beat = frame_number(project, spec, timings, outro)
    video = scene_video_path(source, preview, scene.id)
    fps = timings["render"]["fps"]
    info = {
        "scene": scene.id,
        "beat": beat,
        "at": spec.at,
        "frame": frame,
        "time": round(frame / fps, 6),
        "overlays": spec.overlays is not False,
        "render": str(video.resolve()),
        "render_size": [timings["render"]["width"], timings["render"]["height"]],
    }
    return read_frame(video, frame), info, rendered


def render_current(project: Project, preview: bool, scene_id: str) -> bool:
    """True if the scene has a render at the current format made from its current inputs (its
    fingerprint, DESIGN.md §14)."""
    from vidgen.render.fingerprint import scene_fingerprint
    from vidgen.render.worker import scene_timings_path, scene_video_path

    try:
        meta = json.loads(scene_timings_path(project, preview, scene_id).read_text(encoding="utf-8")).get("render", {})
    except (OSError, ValueError):
        return False
    fmt = project.render_format(preview)
    return (
        scene_video_path(project, preview, scene_id).is_file()
        and (meta.get("width"), meta.get("height"), meta.get("fps")) == (fmt.width, fmt.height, fmt.fps)
        and meta.get("fingerprint") == scene_fingerprint(project, scene_id)
    )


def frame_number(project: Project, spec: ThumbnailConfig, timings: dict[str, Any], outro: float) -> tuple[int, str | None]:
    """The frame of the scene's render that ``spec`` names, and its beat id (``None`` when
    ``at`` counts from the scene's start).

    A beat without ``at``: its last frame (narration + ``narration.pad``, like the beat-end still
    of DESIGN.md §13); ``at``: the frame shown that many seconds into the beat (or the scene).
    Neither: the end of the scene's last beat, or for a silent scene the frame before its
    fade-out (``outro``). A time past the scene's end is a :class:`VidgenError`.
    """
    assert spec.scene is not None
    scene = project.scene(spec.scene)
    fps = int(timings["render"]["fps"])
    total = round(float(timings["duration"]) * fps)
    beats = timings["beats"]
    pad = project.config.narration.pad
    beat_id: str | None = None
    if spec.beat is not None or (spec.at is None and beats):
        ids = [b["id"] for b in beats]
        k = len(ids) - 1 if spec.beat is None else spec.beat - 1 if isinstance(spec.beat, int) else ids.index(spec.beat)
        beat = beats[k]
        beat_id = beat["id"]
        start = round(float(beat["start"]) * fps)
        if spec.at is not None:
            frame = math.floor((float(beat["start"]) + spec.at) * fps + 1e-6)
        else:
            frame = start + round((float(beat["end"]) - float(beat["start"]) + pad) * fps) - 1
            if k + 1 < len(beats):
                frame = min(frame, round(float(beats[k + 1]["start"]) * fps) - 1)
    elif spec.at is not None:
        frame = math.floor(spec.at * fps + 1e-6)
    else:
        frame = round(((scene.duration or 0.0) - outro) * fps) - 1
    if frame >= total:
        where = f"beat '{beat_id}' + {spec.at:g} s" if beat_id is not None and spec.at is not None else f"{spec.at:g} s"
        raise VidgenError(f"thumbnail: {where} is past the end of scene '{scene.id}' ({total / fps:.2f} s)")
    return max(0, min(frame, total - 1)), beat_id


def read_frame(video: Path, index: int) -> Image.Image:
    """Frame ``index`` (from 0) of ``video``, decoded with PyAV."""
    import av

    try:
        with av.open(str(video)) as container:
            for i, frame in enumerate(container.decode(video=0)):
                if i == index:
                    return frame.to_image()
    except (OSError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read {video}: {exc}") from None
    raise VidgenError(f"{video} has no frame {index}")


# ----- designed thumbnails -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass
class _TextBlock:
    font: Any
    px: int
    lines: list[str]
    line_height: float
    cut: bool = False

    @property
    def height(self) -> float:
        return self.line_height * len(self.lines)


def _design_theme(theme: Theme, spec: ThumbnailConfig, fmt: FormatConfig) -> Theme:
    """The project's theme, or ``spec.preset``'s alone (unknown: :class:`VidgenError`)."""
    if spec.preset is None:
        return theme
    derived = theme.derive(ThemeConfig(preset=spec.preset), fmt)
    derived.preset_chain()
    return derived


def _readable(color: str, background: str, minimum: float, fallback: str) -> str:
    """``color`` if it reaches ``minimum`` on ``background``, else ``fallback``."""
    return color if contrast_ratio(hex_rgb(color), hex_rgb(background)) >= minimum else fallback


def _strongest(background: str, *colors: str) -> str:
    """The colour of ``colors`` (or black / white) with the highest contrast on ``background``."""
    return max([*colors, "#000000", "#FFFFFF"], key=lambda c: contrast_ratio(hex_rgb(c), hex_rgb(background)))


def _font(family: str, px: int, bold: bool) -> Any:
    """``family`` at ``px`` for Pillow: a bundled file, an installed font of that name, else
    Inter / DejaVu (:func:`vidgen.sheets.load_font`)."""
    from vidgen.fonts import bundled_font_file
    from vidgen.sheets import load_font

    path = bundled_font_file(family, bold=bold)
    candidates = [str(path)] if path is not None else [f"{family}{' Bold' if bold else ''}.ttf", f"{family.replace(' ', '')}{'-Bold' if bold else '-Regular'}.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return load_font(px, bold=bold)


def _wrap(font: Any, text: str, width: float) -> list[str]:
    """Greedy word wrap of ``text`` to ``width`` px (a word wider than that stays whole)."""
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def _balanced(font: Any, text: str, width: float) -> list[str]:
    """:func:`_wrap` with the narrowest width that keeps the same number of lines (even lines)."""
    lines = _wrap(font, text, width)
    best = lines
    narrower = width
    while narrower > width * 0.5:
        narrower *= 0.96
        tried = _wrap(font, text, narrower)
        if len(tried) != len(lines):
            break
        best = tried
    return best


def _fit_text(text: str, family: str, bold: bool, box_width: float, height: float, max_lines: int, sizes: range, leading: float) -> _TextBlock:
    """The largest size of ``sizes`` (descending) at which ``text`` wraps into at most
    ``max_lines`` lines of ``box_width`` px within ``height`` px; at the smallest size, the
    lines that fit (the last one cut with an ellipsis, ``cut``)."""
    px = sizes.start
    for px in sizes:
        font = _font(family, px, bold)
        lines = _balanced(font, text, box_width)
        if len(lines) <= max_lines and px * leading * len(lines) <= height and all(font.getlength(l) <= box_width for l in lines):
            return _TextBlock(font, px, lines, px * leading)
    font = _font(family, px, bold)
    lines = _wrap(font, text, box_width)
    room = max(1, min(max_lines, int(height // (px * leading))))
    cut = len(lines) > room or any(font.getlength(l) > box_width for l in lines)
    lines = lines[:room]
    if cut:
        last = lines[-1]
        while last and font.getlength(f"{last}…") > box_width:
            last = last[:-1].rstrip()
        lines[-1] = f"{last}…"
    return _TextBlock(font, px, lines, px * leading, cut)


def _icon_image(name: str, root: Path, px: int, color: str, background: str) -> Image.Image:
    """The icon drawn by Manim's camera (as in a render) on a ``px`` square of ``background``."""
    from manim import Camera, tempconfig

    from vidgen.icon_mobject import build_icon
    from vidgen.icons import available_icons, find_icon

    info = find_icon(name, available_icons(root))
    settings = {"pixel_width": px, "pixel_height": px, "frame_width": 1.0, "frame_height": 1.0, "background_color": background}
    with tempconfig(settings):
        camera = Camera()
        camera.capture_mobjects([build_icon(info, 1.0, color)])
        return camera.get_image().convert("RGB")


def design_thumbnail(
    project: Project, theme: Theme, spec: ThumbnailConfig, size: tuple[int, int]
) -> tuple[Image.Image, dict[str, Any], list[ThumbnailCheck]]:
    """Draw a designed thumbnail of ``size``: the title (largest bold size that fits, at most 3
    lines; 4 in 9:16), an accent bar, the subtitle, and the icon (on a ``surface`` disc) or image
    beside it (above it in portrait / square frames). Returns the image, what it shows and the
    checks of its text at the small size (:data:`MIN_TITLE_SMALL_PX`, :data:`MIN_TEXT_SMALL_PX`),
    contrast (:data:`MIN_CONTRAST`), words (:data:`MAX_TITLE_WORDS`) and fit."""
    theme = _design_theme(theme, spec, project.config.format)
    width, height = size
    short = min(width, height)
    side = width > 1.2 * height  # the visual beside the text (16:9), else above it
    background = theme.color(spec.background) if spec.background is not None else theme.background
    colors = theme.colors
    title_color = _readable(colors.get("text", "#FFFFFF"), background, MIN_CONTRAST, _strongest(background))
    accents = [colors[t] for t in ("highlight", "primary", "accent") if t in colors]
    subtitle_color = next((c for c in accents if contrast_ratio(hex_rgb(c), hex_rgb(background)) >= MIN_CONTRAST), title_color)
    bar_color = colors.get("accent", title_color)
    title = spec.title or project.config.title
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)

    margin = round(0.075 * short)
    visual = spec.icon is not None or spec.image is not None
    if not visual:
        text = _Box(margin, margin, width - margin, height - margin)
    elif side:
        text = _Box(margin, margin, 0.58 * width - 0.6 * margin, height - margin)
    else:
        text = _Box(margin, 0.5 * height, width - margin, height - margin)

    if spec.image is not None:
        panel = (round(0.58 * width), 0, width, height) if side else (0, 0, width, round(0.46 * height))
        picture = Image.open(project.root / spec.image).convert("RGB")
        image.paste(ImageOps.fit(picture, (panel[2] - panel[0], panel[3] - panel[1]), method=Image.Resampling.LANCZOS), panel[:2])
    elif spec.icon is not None:
        area = _Box(0.6 * width, margin, width - margin, height - margin) if side else _Box(margin, margin, width - margin, 0.44 * height)
        disc = round(min(area.width, area.height))
        cx, cy = (area.left + area.right) / 2, (area.top + area.bottom) / 2
        plate = colors.get("surface", background)
        draw.ellipse((cx - disc / 2, cy - disc / 2, cx + disc / 2, cy + disc / 2), fill=plate)
        icon_color = _readable(colors.get("primary", title_color), plate, 3.0, _strongest(plate, title_color))
        px = round(disc * 0.58)  # the square fits inside the disc
        image.paste(_icon_image(spec.icon, project.root, px, icon_color, plate), (round(cx - px / 2), round(cy - px / 2)))

    sub_px = round(0.068 * short)
    gap = 0.045 * short
    bar_h = max(2, round(0.016 * short))
    subtitle = None
    reserved = bar_h + 2 * gap
    if spec.subtitle is not None:
        subtitle = _fit_text(spec.subtitle, theme.font_for("body"), False, text.width, 2 * sub_px * 1.2 + 1, 2, range(sub_px, sub_px - 1, -1), 1.2)
        reserved += subtitle.height
    max_lines = 3 if side else 4
    title_sizes = range(round(0.2 * short), round(0.078 * short) - 1, -2)
    block = _fit_text(title, theme.font_for("heading"), True, text.width, text.height - reserved, max_lines, title_sizes, 1.08)

    y = text.top + max(0.0, (text.height - block.height - reserved) / 2)
    anchor, x = ("la", text.left) if side else ("ma", (text.left + text.right) / 2)
    for line in block.lines:
        draw.text((x, y), line, font=block.font, fill=title_color, anchor=anchor)
        y += block.line_height
    y += gap
    bar_w = round(0.22 * short)
    bar_x = x if anchor == "la" else x - bar_w / 2
    draw.rectangle((bar_x, y, bar_x + bar_w, y + bar_h), fill=bar_color)
    y += bar_h + gap
    if subtitle is not None:
        for line in subtitle.lines:
            draw.text((x, y), line, font=subtitle.font, fill=subtitle_color, anchor=anchor)
            y += subtitle.line_height

    factor = SMALL_LONG_SIDE / max(size)
    checks = _design_checks(title, block, subtitle, title_color, subtitle_color, background, factor)
    source = {
        "title": title,
        "subtitle": spec.subtitle,
        "icon": spec.icon,
        "image": spec.image,
        "preset": spec.preset,
        "background": background,
        "title_px": block.px,
        "subtitle_px": None if subtitle is None else subtitle.px,
        "title_lines": block.lines,
    }
    return image, source, checks


def _design_checks(
    title: str, block: _TextBlock, subtitle: _TextBlock | None, title_color: str, subtitle_color: str, background: str, factor: float
) -> list[ThumbnailCheck]:
    """Text size at the small size, contrast, word count and fit of a designed thumbnail."""
    checks: list[ThumbnailCheck] = []
    small = f"the small size ({SMALL_LONG_SIDE} px long side)"
    words = len(title.split())
    if block.cut:
        checks.append(ThumbnailCheck("fit", "warning", f"the title does not fit in {block.px} px type and was cut ({words} words); shorten it"))
    if block.px * factor < MIN_TITLE_SMALL_PX:
        checks.append(
            ThumbnailCheck(
                "min_font", "warning",
                f"the title is {block.px * factor:.1f} px at {small} (needs {MIN_TITLE_SMALL_PX:g}); shorten it ({words} words)",
            )
        )
    if subtitle is not None and subtitle.px * factor < MIN_TEXT_SMALL_PX:
        checks.append(
            ThumbnailCheck("min_font", "warning", f"the subtitle is {subtitle.px * factor:.1f} px at {small} (needs {MIN_TEXT_SMALL_PX:g})")
        )
    texts = [("title", title_color)] + ([("subtitle", subtitle_color)] if subtitle is not None else [])
    for what, color in texts:
        ratio = contrast_ratio(hex_rgb(color), hex_rgb(background))
        if ratio < MIN_CONTRAST:
            checks.append(
                ThumbnailCheck("contrast", "warning", f"the {what} {color} on {background}: {ratio:.2f}:1 (needs {MIN_CONTRAST:g}:1)")
            )
    if words > MAX_TITLE_WORDS:
        checks.append(
            ThumbnailCheck("max_words", "info", f"the title has {words} words; thumbnails read best with {MAX_TITLE_WORDS} or fewer")
        )
    return checks
