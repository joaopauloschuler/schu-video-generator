"""WCAG 2 colour contrast (https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio)."""

from __future__ import annotations

RGB = tuple[float, float, float]


def hex_rgb(color: str) -> RGB:
    """``#RRGGBB`` as RGB components in 0..1."""
    value = color.lstrip("#")
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
