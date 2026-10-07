"""WCAG 2 colour contrast (https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio), the contrast
check of a theme's colours (:func:`theme_contrast`, DESIGN.md §19) and how distinguishable a
palette stays for colour-blind viewers (:func:`palette_distinctness`, DESIGN.md §20)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
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


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def relative_luminance(rgb: RGB) -> float:
    """WCAG relative luminance of an sRGB colour (0 black .. 1 white)."""
    r, g, b = (_linear(c) for c in rgb)
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


# ----- colour-vision deficiency ------------------------------------------------------------------

#: Machado, Oliveira & Fernandes (2009) matrices for full dichromacy, on linear RGB.
CVD_MATRICES: dict[str, tuple[RGB, RGB, RGB]] = {
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}
#: The visions :func:`palette_distinctness` compares colours under.
VISIONS: tuple[str, ...] = ("normal", *CVD_MATRICES)


def simulate_cvd(rgb: RGB, vision: str) -> RGB:
    """How ``rgb`` looks with ``vision`` (``normal`` or a key of :data:`CVD_MATRICES`)."""
    if vision == "normal":
        return rgb
    linear = [_linear(c) for c in rgb]
    return tuple(_gamma(sum(m * c for m, c in zip(row, linear))) for row in CVD_MATRICES[vision])  # type: ignore[return-value]


def lab(rgb: RGB) -> tuple[float, float, float]:
    """CIELAB (D65) of an sRGB colour."""
    r, g, b = (_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 colour difference (about 2.3 is just noticeable; 10+ reads as a different colour).

    Reference: Sharma, Wu & Dalal, "The CIEDE2000 color-difference formula: implementation
    notes, supplementary test data, and mathematical observations", Color Res. Appl. 30 (2005)."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c_mean = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_mean**7 / (c_mean**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dh = 0.0
    if c1p * c2p != 0:
        dh = h2p - h1p
        dh = dh - 360 if dh > 180 else dh + 360 if dh < -180 else dh
    d_hue = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    l_mean, cp_mean = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_mean = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_mean = (h1p + h2p) / 2
    else:
        h_mean = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_mean - 30))
        + 0.24 * math.cos(math.radians(2 * h_mean))
        + 0.32 * math.cos(math.radians(3 * h_mean + 6))
        - 0.20 * math.cos(math.radians(4 * h_mean - 63))
    )
    d_theta = 30 * math.exp(-(((h_mean - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_mean**7 / (cp_mean**7 + 25**7))
    s_l = 1 + 0.015 * (l_mean - 50) ** 2 / math.sqrt(20 + (l_mean - 50) ** 2)
    s_c = 1 + 0.045 * cp_mean
    s_h = 1 + 0.015 * cp_mean * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    dl, dc, dhh = (l2 - l1) / s_l, (c2p - c1p) / s_c, d_hue / s_h
    return math.sqrt(dl**2 + dc**2 + dhh**2 + r_t * dc * dhh)


def palette_distinctness(palette: list[str]) -> dict[str, float]:
    """The smallest CIEDE2000 difference between any two ``palette`` colours, per vision in
    :data:`VISIONS` (normal and simulated protanopia, deuteranopia, tritanopia). A palette
    with fewer than two colours gets ``inf``."""
    rgbs = [hex_rgb(c) for c in palette]
    result: dict[str, float] = {}
    for vision in VISIONS:
        labs = [lab(simulate_cvd(rgb, vision)) for rgb in rgbs]
        result[vision] = min((delta_e(a, b) for a, b in combinations(labs, 2)), default=math.inf)
    return result
