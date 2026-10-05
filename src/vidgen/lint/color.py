"""WCAG 2 colour contrast (https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio) and the contrast
check of a theme's colours (:func:`theme_contrast`, DESIGN.md §19)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vidgen.theme import Theme

RGB = tuple[float, float, float]

#: WCAG AA for normal text (SC 1.4.3) and for graphical objects (SC 1.4.11).
TEXT_RATIO = 4.5
GRAPHIC_RATIO = 3.0
#: Theme colours used for running text, and for accents (shapes, large or emphasised text).
TEXT_TOKENS: tuple[str, ...] = ("text", "dim")
ACCENT_TOKENS: tuple[str, ...] = ("accent", "highlight", "primary", "secondary", "tertiary")


def hex_rgb(color: str) -> RGB:
    """``#RGB``, ``#RRGGBB`` or ``#RRGGBBAA`` (alpha ignored) as RGB components in 0..1."""
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)


def rgb_hex(rgb: RGB) -> str:
    """RGB components in 0..1 as ``#RRGGBB``."""
    r, g, b = (int(round(min(max(c, 0.0), 1.0) * 255)) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def relative_luminance(rgb: RGB) -> float:
    """WCAG relative luminance of an sRGB colour (0 black .. 1 white)."""

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    """WCAG contrast ratio of two colours: 1 (same) .. 21 (black on white)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def blend(foreground: RGB, background: RGB, alpha: float) -> RGB:
    """``foreground`` drawn at opacity ``alpha`` over ``background`` (what the viewer sees)."""
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(foreground, background))  # type: ignore[return-value]


@dataclass(frozen=True)
class ContrastCheck:
    """One theme colour pair: ``subject`` (``"colors.dim"``, ``"palette[2]"``) against
    ``against`` (``"background"`` or ``"colors.surface"``)."""

    subject: str
    color: str
    against: str
    against_color: str
    ratio: float
    minimum: float

    @property
    def ok(self) -> bool:
        """True if the pair reaches its minimum ratio."""
        return self.ratio >= self.minimum

    def __str__(self) -> str:
        verdict = "ok" if self.ok else "too low"
        return (
            f"{self.subject} {self.color} on {self.against} {self.against_color}: "
            f"{self.ratio:.2f}:1 (needs {self.minimum:g}:1, {verdict})"
        )


def theme_contrast(
    theme: Theme, *, text_ratio: float = TEXT_RATIO, graphic_ratio: float = GRAPHIC_RATIO
) -> list[ContrastCheck]:
    """Every contrast pair of ``theme`` that built-in scenes rely on.

    ``text`` and ``dim`` must reach ``text_ratio`` (WCAG AA 4.5:1) on the background and on
    the ``surface`` panel colour; the accent tokens (``accent``, ``highlight``, ``primary``,
    ``secondary``, ``tertiary``) and every palette colour must reach ``graphic_ratio`` (3:1, WCAG
    AA for graphical objects and large text) on the background. Tokens a theme does not define
    are skipped. Use ``[c for c in theme_contrast(t) if not c.ok]`` for the failures.
    """
    colors = theme.colors
    background = theme.background
    pairs: list[tuple[str, str, str, str, float]] = []
    surfaces = [("background", background)]
    if "surface" in colors:
        surfaces.append(("colors.surface", colors["surface"]))
    for token in TEXT_TOKENS:
        if token in colors:
            pairs += [(f"colors.{token}", colors[token], name, value, text_ratio) for name, value in surfaces]
    for token in ACCENT_TOKENS:
        if token in colors:
            pairs.append((f"colors.{token}", colors[token], "background", background, graphic_ratio))
    for i, color in enumerate(theme.palette):
        pairs.append((f"palette[{i}]", color, "background", background, graphic_ratio))
    return [
        ContrastCheck(subject, color, against, against_color, contrast_ratio(hex_rgb(color), hex_rgb(against_color)), minimum)
        for subject, color, against, against_color, minimum in pairs
    ]
