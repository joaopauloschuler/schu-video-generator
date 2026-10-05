"""Layout and timing helpers shared by built-in scenes and project extensions.

Exported by ``vidgen.api``. The pure functions (:func:`wrap_lines`, :func:`distribute`,
:func:`nice_ticks`, :func:`format_value`, :func:`auto_format`) do not touch Manim and are easy to
unit-test; :func:`fit_text` and :func:`shrink_to_fit` build/scale mobjects.
"""

from __future__ import annotations

import math
import re
import shutil
import textwrap
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

from manim import NORMAL, Mobject, Paragraph, Text, config

from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.icon_mobject import scale_icon_strokes
from vidgen.runtime import current_theme
from vidgen.theme import Theme

# ----- text wrapping -------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Collapse runs of spaces/tabs to one space and strip each line; drop blank lines.

    Explicit line breaks (``\\n``) are kept. :func:`fit_text` wraps the normalized text, so
    character indices into it stay valid after wrapping (wrapping only turns spaces into
    ``\\n``).
    """
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def wrap_lines(text: str, max_chars: int) -> list[str]:
    """Greedy word wrap of ``text`` into lines of at most ``max_chars`` characters.

    Explicit ``\\n`` breaks are honoured; whitespace is normalized (:func:`normalize_text`).
    Words longer than ``max_chars`` are never split (they get a line of their own), so
    ``"\\n".join(result)`` has the same length as the normalized text.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    out: list[str] = []
    for paragraph in normalize_text(text).split("\n"):
        if paragraph:
            out.extend(
                textwrap.wrap(paragraph, width=max_chars, break_long_words=False, break_on_hyphens=False)
            )
    return out


def _highlight_ranges(normalized: str, highlights: Mapping[str, Any]) -> dict[str, Any]:
    """``t2c`` entries ``"[a:b]" -> color`` for every occurrence of each highlight substring."""
    t2c: dict[str, Any] = {}
    flat = normalized.replace("\n", " ")
    for needle, color in highlights.items():
        needle = normalize_text(needle).replace("\n", " ")
        if not needle:
            continue
        start = flat.find(needle)
        while start != -1:
            t2c[f"[{start}:{start + len(needle)}]"] = color
            start = flat.find(needle, start + len(needle))
    return t2c


def shrink_to_fit(m: Mobject, max_width: float | None = None, max_height: float | None = None) -> Mobject:
    """Scale ``m`` down (never up) so it fits within ``max_width`` x ``max_height``; returns ``m``.

    Icons inside ``m`` keep their proportions (their strokes are scaled too)."""
    factor = 1.0
    if max_width is not None and m.width > max_width > 0:
        factor = min(factor, max_width / m.width)
    if max_height is not None and m.height > max_height > 0:
        factor = min(factor, max_height / m.height)
    if factor < 1.0:
        m.scale(factor)
        scale_icon_strokes(m, factor)
    return m


def fit_text(
    text: str,
    max_width: float,
    max_height: float | None = None,
    *,
    size: str | float = "body",
    color: Any = "text",
    weight: str = NORMAL,
    slant: str = NORMAL,
    align: str = "center",
    min_size: str | float | None = None,
    highlights: Mapping[str, Any] | None = None,
    line_spacing: float = 0.7,
    squeeze: float = 1.0,
    theme: Theme | None = None,
    font: str | None = None,
) -> Paragraph:
    """Text in the theme font, word-wrapped to ``max_width`` and fitted into ``max_height``.

    Starts at ``size`` (theme token or points). Lines are wrapped by measured width; if the
    block is taller than ``max_height`` the font size is reduced (re-wrapping each time) down
    to ``min_size`` (default: 60% of ``size``), after which the block is scaled down to fit.
    ``align`` is ``"center"``, ``"left"`` or ``"right"``. ``highlights`` maps substrings to
    colors (theme tokens or hex); every occurrence is colored, also across line breaks.
    ``line_spacing`` is Manim's ``Paragraph`` setting (it scales with the font size; Manim's
    own default -1 sets lines almost touching). With ``squeeze > 1``, text that fits on one line
    at up to ``squeeze * max_width`` is scaled down instead of wrapped (good for links).
    ``font`` is a family name (default: the theme font), e.g. ``theme.font_for("heading")``.
    Returns a Manim ``Paragraph`` (one submobject per line).
    """
    block, _ = fit_text_sized(
        text, max_width, max_height, size=size, color=color, weight=weight, slant=slant, align=align,
        min_size=min_size, highlights=highlights, line_spacing=line_spacing, squeeze=squeeze, theme=theme,
        font=font,
    )
    return block


def fit_text_sized(
    text: str,
    max_width: float,
    max_height: float | None = None,
    *,
    size: str | float = "body",
    color: Any = "text",
    weight: str = NORMAL,
    slant: str = NORMAL,
    align: str = "center",
    min_size: str | float | None = None,
    highlights: Mapping[str, Any] | None = None,
    line_spacing: float = 0.7,
    squeeze: float = 1.0,
    theme: Theme | None = None,
    font: str | None = None,
) -> tuple[Paragraph, float]:
    """:func:`fit_text` that also returns the font size the text ends up at (points, after
    any final scaling), e.g. to tell whether it was shrunk below ``min_size``."""
    theme = theme or current_theme()
    font_size = float(theme.size(size))
    floor = float(theme.size(min_size)) if min_size is not None else font_size * 0.6
    normalized = normalize_text(text)
    if not normalized:
        raise VidgenError("fit_text: text is empty")
    kwargs: dict[str, Any] = {
        "font": font or theme.font,
        "color": resolve_color(color, theme),
        "weight": weight,
        "slant": slant,
        "alignment": align,
        "line_spacing": line_spacing,
    }
    if highlights:
        kwargs["t2c"] = _highlight_ranges(
            normalized, {k: resolve_color(v, theme) for k, v in highlights.items()}
        )

    if squeeze > 1.0 and "\n" not in normalized:
        line = Paragraph(normalized, font_size=font_size, **kwargs)
        if line.width <= max_width * squeeze:
            return _shrunk(line, font_size, max_width, max_height)
    # Search the font size arithmetically (word widths and line pitch scale linearly with the
    # size), then build the Paragraph once; re-wrap narrower if the estimate was off.
    metrics = _Metrics(normalized, kwargs["font"], kwargs["weight"], kwargs["slant"], line_spacing)
    for _ in range(40):
        lines = metrics.wrap(font_size, max_width)
        if max_height is None or font_size <= floor or metrics.height(len(lines), font_size) <= max_height:
            break
        font_size = max(floor, font_size * 0.95)
    target = max_width
    block = Paragraph(*lines, font_size=font_size, **kwargs)
    for _ in range(3):
        if block.width <= max_width * 1.001 or len(lines) == len(normalized.split()):
            break
        target *= max_width / block.width * 0.98
        lines = metrics.wrap(font_size, target)
        block = Paragraph(*lines, font_size=font_size, **kwargs)
    return _shrunk(block, font_size, max_width, max_height)


def _shrunk(block: Paragraph, font_size: float, max_width: float, max_height: float | None) -> tuple[Paragraph, float]:
    """``block`` shrunk to fit, and its font size after shrinking."""
    before = block.width
    shrink_to_fit(block, max_width, max_height)
    return block, font_size * (block.width / before if before > 0 else 1.0)


_REF_SIZE = 48.0


@lru_cache(maxsize=4096)
def _ink_width(word: str, font: str, weight: str, slant: str) -> float:
    """Width of ``word`` at the reference size (cached across scenes)."""
    return float(Text(word, font=font, font_size=_REF_SIZE, weight=weight, slant=slant).width)


@lru_cache(maxsize=64)
def _line_metrics(font: str, weight: str, slant: str, line_spacing: float) -> tuple[float, float]:
    """(line height, line pitch) at the reference size."""
    probe = Paragraph("Ag", "Ag", font=font, font_size=_REF_SIZE, weight=weight, slant=slant, line_spacing=line_spacing)
    return float(probe[0].height), float(probe[0].get_y() - probe[1].get_y())


class _Metrics:
    """Measured word widths of one text, for wrapping at any font size without building it."""

    def __init__(self, normalized: str, font: str, weight: str, slant: str, line_spacing: float) -> None:
        self.paragraphs = [p.split(" ") for p in normalized.split("\n")]
        self.widths = {w: _ink_width(w, font, weight, slant) for p in self.paragraphs for w in p}
        self.space = _ink_width("x x", font, weight, slant) - _ink_width("xx", font, weight, slant)
        self.line_h, self.pitch = _line_metrics(font, weight, slant, line_spacing)

    def wrap(self, size: float, max_width: float) -> list[str]:
        """Greedy word wrap at ``size`` points into lines at most ``max_width`` wide."""
        limit = max_width * _REF_SIZE / size
        lines: list[str] = []
        for words in self.paragraphs:
            line, width = [words[0]], self.widths[words[0]]
            for w in words[1:]:
                if width + self.space + self.widths[w] <= limit:
                    line.append(w)
                    width += self.space + self.widths[w]
                else:
                    lines.append(" ".join(line))
                    line, width = [w], self.widths[w]
            lines.append(" ".join(line))
        return lines

    def height(self, n_lines: int, size: float) -> float:
        """Estimated height of ``n_lines`` lines at ``size`` points."""
        return (self.line_h + (n_lines - 1) * self.pitch) * size / _REF_SIZE


# ----- beats ---------------------------------------------------------------------------------


def distribute(n_steps: int, n_beats: int) -> list[list[int]]:
    """Assign ``n_steps`` reveal steps to ``n_beats`` beats; returns step indices per beat.

    With no more steps than beats, step ``i`` goes to beat ``i`` and the remaining beats get no
    step (they hold). With more steps than beats, steps are split into contiguous runs whose
    sizes differ by at most one (earlier beats get the extra ones). ``n_beats < 1`` counts as 1.
    """
    if n_steps < 0:
        raise ValueError("n_steps must not be negative")
    n_beats = max(1, n_beats)
    if n_steps <= n_beats:
        return [[i] for i in range(n_steps)] + [[] for _ in range(n_beats - n_steps)]
    base, extra = divmod(n_steps, n_beats)
    out, start = [], 0
    for b in range(n_beats):
        size = base + (1 if b < extra else 0)
        out.append(list(range(start, start + size)))
        start += size
    return out


# ----- numbers -------------------------------------------------------------------------------


def nice_ticks(lo: float, hi: float, max_ticks: int = 6) -> list[float]:
    """Round tick values (steps of 1, 2, 2.5 or 5 x 10^k) covering ``lo..hi``.

    The first tick is ``<= lo`` and the last ``>= hi``; at most ``max_ticks`` ticks (at least 2).
    """
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad
    max_ticks = max(2, max_ticks)
    raw = (hi - lo) / (max_ticks - 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * magnitude
        first = math.floor(lo / step + 1e-9) * step
        last = math.ceil(hi / step - 1e-9) * step
        count = round((last - first) / step) + 1
        if count <= max_ticks:
            break
    ticks = [first + i * step for i in range(count)]
    digits = max(0, -math.floor(math.log10(step)) + 2)
    return [round(t, digits) + 0.0 for t in ticks]


def auto_format(values: Sequence[float], max_decimals: int = 2) -> str:
    """A ``str.format`` pattern showing as many decimals as the values need (up to
    ``max_decimals``), with thousands separators: ``[1, 2]`` -> ``"{:,.0f}"``,
    ``[1.5, 2.25]`` -> ``"{:,.2f}"``."""
    decimals = 0
    for v in values:
        text = f"{abs(float(v)):.{max_decimals}f}".rstrip("0")
        decimals = max(decimals, len(text.split(".")[1]) if "." in text else 0)
    return f"{{:,.{decimals}f}}"


def format_value(value: float, fmt: str | None = None, unit: str = "") -> str:
    """Format a number for a label: ``fmt`` (``str.format`` pattern, default ``"{:,.0f}"``)
    then ``unit`` appended verbatim (``format_value(0.5, "{:.0%}")`` -> ``"50%"``,
    ``format_value(12.5, "{:.1f}", " ms")`` -> ``"12.5 ms"``)."""
    pattern = fmt or "{:,.0f}"
    try:
        text = pattern.format(value)
    except (ValueError, IndexError, KeyError) as exc:
        raise VidgenError(f"invalid number format {pattern!r}: {exc}") from None
    return text + unit


def check_format(fmt: str) -> str:
    """Validate a number format pattern (for ``Params`` validators); returns it unchanged."""
    try:
        fmt.format(1234.5)
    except (ValueError, IndexError, KeyError) as exc:
        raise ValueError(f"invalid number format {fmt!r}: {exc}") from None
    return fmt


# ----- LaTeX ---------------------------------------------------------------------------------


def missing_latex_tools() -> list[str]:
    """Programs Manim needs for ``Tex``/``MathTex`` that are not on PATH (empty if all found)."""
    compiler = getattr(config.tex_template, "tex_compiler", "latex") or "latex"
    output = getattr(config.tex_template, "output_format", ".dvi")
    tools = [compiler] + (["dvisvgm"] if output in (".dvi", ".xdv") else [])
    return [tool for tool in tools if shutil.which(tool) is None]


def latex_available() -> bool:
    """True when ``Tex``/``MathTex`` can be rendered (LaTeX and dvisvgm found on PATH)."""
    return not missing_latex_tools()


LATEX_HINT = (
    "Install a TeX distribution: on Windows MiKTeX (https://miktex.org; it includes dvisvgm — "
    "open a new terminal afterwards), on macOS MacTeX, on Linux TeX Live plus dvisvgm "
    "(e.g. `apt install texlive texlive-latex-extra dvisvgm`)."
)


def require_latex(feature: str) -> None:
    """Raise a clear :class:`VidgenError` if LaTeX tools are missing (``feature`` names what
    needs them, e.g. ``"scene 'eq' (type equation)"``)."""
    missing = missing_latex_tools()
    if missing:
        raise VidgenError(f"{feature} needs LaTeX, but {' and '.join(missing)} not found on PATH. {LATEX_HINT}")
