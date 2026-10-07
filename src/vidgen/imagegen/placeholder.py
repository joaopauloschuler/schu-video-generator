"""The placeholder card shown for a generated picture not made yet (DESIGN.md §58).

A card at the picture's aspect ratio in the theme's colours: a soft gradient, a picture glyph,
"Image to generate", the prompt and a hint to run ``vidgen imagegen``. Drawn with Pillow and
cached in ``build/imagegen/`` (keyed by the request and the colours / font), so previews,
storyboards and lint work before anything is generated.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageFont

from vidgen.fileio import write_bytes_atomic
from vidgen.imagegen import ImageRequest

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.theme import Theme

#: Bumped when the drawing changes (placeholders are drawn again).
PLACEHOLDER_VERSION = 1
#: Long side of the placeholder in pixels.
LONG_SIDE = 1280
#: Most lines of the prompt shown (the rest is cut with an ellipsis).
MAX_PROMPT_LINES = 6


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) in (3, 4):
        color = "".join(c * 2 for c in color[:3])
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def _font(family: str, px: int, bold: bool = False) -> Any:
    """The theme's sans family at ``px`` (a bundled file), else Pillow's default font."""
    from vidgen.fonts import bundled_font_file

    path = bundled_font_file(family, bold=bold) or bundled_font_file("Inter", bold=bold)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), px)
        except OSError:
            pass
    try:
        return ImageFont.load_default(px)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _px(font: Any) -> int:
    """A font's size in pixels (Pillow's old bitmap font has none: about 11)."""
    return int(getattr(font, "size", 11))


def _wrap(font: Any, text: str, width: float) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def _fit_prompt(family: str, text: str, width: float, start: int, smallest: int) -> tuple[Any, list[str]]:
    """The largest font from ``start`` down to ``smallest`` px whose wrap of ``text`` fits
    :data:`MAX_PROMPT_LINES` lines of ``width``; at the smallest size the text is cut."""
    px = start
    while True:
        font = _font(family, px)
        lines = _wrap(font, text, width)
        if (len(lines) <= MAX_PROMPT_LINES and all(font.getlength(line) <= width for line in lines)) or px <= smallest:
            break
        px = max(smallest, int(px * 0.88))
    if len(lines) > MAX_PROMPT_LINES:
        lines = lines[:MAX_PROMPT_LINES]
        last = lines[-1]
        while last and font.getlength(last + " …") > width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + " …"
    return font, lines


def _colors(theme: Theme) -> dict[str, tuple[int, int, int]]:
    return {
        "background": _rgb(theme.background),
        "surface": _rgb(theme.color("surface")),
        "text": _rgb(theme.color("text")),
        "dim": _rgb(theme.color("dim")),
        "primary": _rgb(theme.color("primary")),
    }


def placeholder_size(request: ImageRequest) -> tuple[int, int]:
    """The card's pixel size: the request's aspect ratio, long side :data:`LONG_SIDE`."""
    w, h = request.pixels
    scale = LONG_SIDE / max(w, h)
    return max(1, round(w * scale)), max(1, round(h * scale))


def draw_placeholder(request: ImageRequest, theme: Theme) -> Image.Image:
    """The placeholder card of ``request`` in ``theme``'s colours and sans font (RGB)."""
    c = _colors(theme)
    w, h = placeholder_size(request)
    short = min(w, h)
    top, bottom = c["surface"], _mix(c["surface"], c["primary"], 0.16)
    image = Image.new("RGB", (w, h), top)
    draw = ImageDraw.Draw(image)
    for y in range(h):  # vertical gradient
        draw.line([(0, y), (w, y)], fill=_mix(top, bottom, y / max(1, h - 1)))
    inset = round(short * 0.035)
    draw.rounded_rectangle(
        [inset, inset, w - 1 - inset, h - 1 - inset], radius=round(short * 0.04),
        outline=_mix(c["dim"], c["surface"], 0.45), width=max(2, round(short * 0.004)),
    )

    family = theme.font
    label_font = _font(family, max(10, round(short * 0.036)), bold=True)
    hint_font = _font(family, max(9, round(short * 0.03)))
    text_width = w * 0.78
    prompt_font, lines = _fit_prompt(family, request.prompt, text_width, max(12, round(short * 0.058)), max(10, round(short * 0.03)))

    # picture glyph: a framed landscape (sun and two hills)
    g = round(short * 0.16)
    gw, gh = round(g * 1.3), g
    line_h = round(_px(prompt_font) * 1.3)
    hint_gap = round(short * 0.05)
    block = gh + round(short * 0.05) + _px(label_font) + round(short * 0.035) + line_h * len(lines) + hint_gap + _px(hint_font)
    y = (h - block) // 2  # one centred block: a cover fit crops the edges, never the text
    x0 = (w - gw) // 2
    stroke = max(2, round(short * 0.008))
    glyph = c["primary"]
    draw.rounded_rectangle([x0, y, x0 + gw, y + gh], radius=round(g * 0.12), outline=glyph, width=stroke)
    draw.ellipse([x0 + gw * 0.62, y + gh * 0.18, x0 + gw * 0.62 + g * 0.2, y + gh * 0.18 + g * 0.2], outline=glyph, width=stroke)
    hills = [(x0 + gw * 0.12, y + gh * 0.84), (x0 + gw * 0.4, y + gh * 0.42), (x0 + gw * 0.6, y + gh * 0.66),
             (x0 + gw * 0.72, y + gh * 0.54), (x0 + gw * 0.88, y + gh * 0.84)]
    draw.line(hills, fill=glyph, width=stroke, joint="curve")
    y += gh + round(short * 0.05)

    label = "IMAGE TO GENERATE"
    draw.text(((w - label_font.getlength(label)) / 2, y), label, font=label_font, fill=c["primary"])
    y += _px(label_font) + round(short * 0.035)
    for line in lines:
        draw.text(((w - prompt_font.getlength(line)) / 2, y), line, font=prompt_font, fill=c["text"])
        y += line_h

    hint = "placeholder · run vidgen imagegen"
    draw.text(((w - hint_font.getlength(hint)) / 2, y + hint_gap - line_h + _px(prompt_font)), hint, font=hint_font, fill=c["dim"])
    return image


def placeholder_path(project: Project, request: ImageRequest, theme: Theme) -> Path:
    """The placeholder of ``request`` as ``build/imagegen/<key>-<look>.png`` (drawn when
    missing; ``look`` = the theme colours, font and drawing version)."""
    look = repr((PLACEHOLDER_VERSION, sorted(_colors(theme).items()), theme.font, placeholder_size(request), request.prompt))
    digest = hashlib.sha1(look.encode("utf-8")).hexdigest()[:10]
    path = project.build_dir / "imagegen" / f"{request.key}-{digest}.png"
    if not path.is_file():
        out = io.BytesIO()
        draw_placeholder(request, theme).save(out, format="PNG", optimize=True)
        write_bytes_atomic(path, out.getvalue())
    return path
