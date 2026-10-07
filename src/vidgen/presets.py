"""Theme presets: named sets of theme values selected with ``theme: {preset: NAME}``.

A preset sits between the built-in defaults (plus extension defaults) and the values written in
``video.yaml`` (DESIGN.md §19). Built-in presets live here; projects register their own with
``vidgen.api.register_theme_preset``. This module does not import manim.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType

from vidgen.config import HEX_COLOR_PATTERN, ID_PATTERN
from vidgen.errors import VidgenError
from vidgen.fonts import FONT_TOKENS, MONO_FAMILY, SANS_FAMILY, SERIF_FAMILY
from vidgen.scales import SCALE_CHOICES, TYPE_SCALES

DEFAULT_BACKGROUND = "#0E1116"
DEFAULT_FONT = SANS_FAMILY
DEFAULT_FONT_SERIF = SERIF_FAMILY
DEFAULT_FONT_MONO = MONO_FAMILY
DEFAULT_CODE_STYLE = "github-dark"
DEFAULT_COLORS: dict[str, str] = {
    "text": "#E8EAED",
    "dim": "#838B98",
    "accent": "#FF6B6B",
    "highlight": "#FFD166",
    "primary": "#58C4DD",
    "secondary": "#F2A541",
    "tertiary": "#83C167",
    "surface": "#161B24",
}
DEFAULT_PALETTE: list[str] = ["#58C4DD", "#F2A541", "#C792EA", "#83C167"]
DEFAULT_SIZES: dict[str, int | float] = dict(TYPE_SCALES["standard"])


@dataclass(frozen=True)
class ThemePreset:
    """A named set of theme values; ``None``/empty means "not set by this preset".

    Values not set fall through to ``base`` (another preset, if given), then to the defaults.
    ``scale`` names a type scale (``vidgen.scales``) applied below ``sizes``; ``fonts`` maps font
    roles (``heading``, ``quote``, ``code``...) to a family token (``sans``, ``serif``, ``mono``)
    or a family name, read with ``Theme.font_for`` (DESIGN.md §20, §21).
    Build one with :func:`make_preset`, which validates the values.
    """

    name: str
    description: str = ""
    base: str | None = None
    background: str | None = None
    font: str | None = None
    font_serif: str | None = None
    font_mono: str | None = None
    code_style: str | None = None
    colors: Mapping[str, str] = field(default_factory=dict)
    palette: tuple[str, ...] | None = None
    sizes: Mapping[str, int | float] = field(default_factory=dict)
    scale: str | None = None
    fonts: Mapping[str, str] = field(default_factory=dict)
    origin: str = "builtin"


@lru_cache(maxsize=1)
def _styles() -> tuple[str, ...]:
    from pygments.styles import get_all_styles

    return tuple(sorted(get_all_styles()))


def code_styles() -> list[str]:
    """Names of the installed Pygments styles (valid ``code_style`` values)."""
    return list(_styles())


def check_code_style(style: str) -> None:
    """Raise ``ValueError`` if ``style`` is not an installed Pygments style."""
    if style not in code_styles():
        raise ValueError(f"unknown code style {style!r}; available: {', '.join(code_styles())}")


def make_preset(
    name: str,
    *,
    description: str = "",
    base: str | None = None,
    background: str | None = None,
    font: str | None = None,
    font_serif: str | None = None,
    font_mono: str | None = None,
    code_style: str | None = None,
    colors: Mapping[str, str] | None = None,
    palette: Sequence[str] | None = None,
    sizes: Mapping[str, int | float] | None = None,
    scale: str | None = None,
    fonts: Mapping[str, str] | None = None,
    origin: str = "builtin",
) -> ThemePreset:
    """A validated :class:`ThemePreset`; bad values raise :class:`VidgenError`."""
    where = f"theme preset '{name}'"
    if not isinstance(name, str) or not re.match(ID_PATTERN, name):
        raise VidgenError(f"theme preset name {name!r} must use only letters, digits and _")
    hexes = {"background": background, **{f"colors.{k}": v for k, v in (colors or {}).items()}}
    hexes.update({f"palette[{i}]": v for i, v in enumerate(palette or [])})
    for key, value in hexes.items():
        if value is not None and (not isinstance(value, str) or not re.match(HEX_COLOR_PATTERN, value)):
            raise VidgenError(f"{where}: {key} must be a hex color like '#1D4ED8', got {value!r}")
    for key in colors or {}:
        if not re.match(ID_PATTERN, key):
            raise VidgenError(f"{where}: color name {key!r} must use only letters, digits and _")
    for key, value in (sizes or {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise VidgenError(f"{where}: size '{key}' must be a positive number, got {value!r}")
    if palette is not None and len(palette) == 0:
        raise VidgenError(f"{where}: palette must have at least one color")
    for key, family in (("font", font), ("font_serif", font_serif), ("font_mono", font_mono)):
        if family is not None and (not isinstance(family, str) or not family.strip()):
            raise VidgenError(f"{where}: {key} must be a font family name, got {family!r}")
    for role, family in (fonts or {}).items():
        if not isinstance(role, str) or not re.match(ID_PATTERN, role):
            raise VidgenError(f"{where}: font role {role!r} must use only letters, digits and _")
        if not isinstance(family, str) or not family.strip():
            raise VidgenError(
                f"{where}: fonts.{role} must be a font family name or one of {', '.join(FONT_TOKENS)}, got {family!r}"
            )
    if scale is not None and scale not in SCALE_CHOICES:
        raise VidgenError(f"{where}: unknown type scale {scale!r}; available: {', '.join(SCALE_CHOICES)}")
    if code_style is not None:
        try:
            check_code_style(code_style)
        except ValueError as exc:
            raise VidgenError(f"{where}: {exc}") from None
    return ThemePreset(
        name=name,
        description=description,
        base=base,
        background=background,
        font=font,
        font_serif=font_serif,
        font_mono=font_mono,
        code_style=code_style,
        colors=MappingProxyType(dict(colors or {})),
        palette=tuple(palette) if palette is not None else None,
        sizes=MappingProxyType(dict(sizes or {})),
        scale=scale,
        fonts=MappingProxyType(dict(fonts or {})),
        origin=origin,
    )



def _builtin(name: str, description: str, *, palette: Sequence[str], **values: object) -> ThemePreset:
    """A built-in preset (validated like a project preset)."""
    return make_preset(name, description=description, palette=palette, **values)  # type: ignore[arg-type]


BUILTIN_PRESETS: Mapping[str, ThemePreset] = MappingProxyType(
    {
        preset.name: preset
        for preset in (
            _builtin(
                "dark_tech",
                "The default look: near-black background, light text, bright accents.",
                background=DEFAULT_BACKGROUND,
                font=DEFAULT_FONT,
                code_style=DEFAULT_CODE_STYLE,
                colors=DEFAULT_COLORS,
                palette=DEFAULT_PALETTE,
                scale="auto",
            ),
            _builtin(
                "light_academic",
                "Paper-like off-white background, near-black text, deep ink accents, serif headings.",
                background="#F8F7F3",
                font=DEFAULT_FONT,
                code_style="xcode",
                colors={
                    "text": "#1F2328",
                    "dim": "#59606B",
                    "accent": "#B42318",
                    "highlight": "#A64B00",
                    "primary": "#1D4ED8",
                    "secondary": "#C2410C",
                    "tertiary": "#15803D",
                    "surface": "#FFFFFF",
                },
                palette=("#1D4ED8", "#C2410C", "#9D2F8F", "#15803D"),
                scale="auto",
                fonts={"heading": "serif"},
            ),
            _builtin(
                "high_contrast",
                "Black background, white text, saturated accents (WCAG AAA 7:1) and the large type scale.",
                background="#000000",
                font=DEFAULT_FONT,
                code_style=DEFAULT_CODE_STYLE,
                colors={
                    "text": "#FFFFFF",
                    "dim": "#C9CED6",
                    "accent": "#FF7A7A",
                    "highlight": "#FFE14D",
                    "primary": "#4DD2FF",
                    "secondary": "#FFAA4D",
                    "tertiary": "#7EE787",
                    "surface": "#141414",
                },
                palette=("#4DD2FF", "#FFAA4D", "#FF8FD8", "#7EE787"),
                scale="large",
            ),
            _builtin(
                "warm_editorial",
                "Warm cream paper, espresso text, petrol and terracotta accents, serif headings and quotes: a magazine feel.",
                background="#F6F0E4",
                font=DEFAULT_FONT,
                code_style="default",
                colors={
                    "text": "#2B2118",
                    "dim": "#6A5A4A",
                    "accent": "#9B1D3A",
                    "highlight": "#8F5700",
                    "primary": "#1F5E6E",
                    "secondary": "#B4441B",
                    "tertiary": "#37704F",
                    "surface": "#FFFBF4",
                },
                palette=("#1F5E6E", "#B04A16", "#8D4AAB", "#1A7C4D", "#8C2024"),
                scale="auto",
                fonts={"heading": "serif", "quote": "serif"},
            ),
            _builtin(
                "brand_neutral",
                "Light grey and white, graphite text, one blue: a neutral base for a brand colour.",
                background="#F4F5F7",
                font=DEFAULT_FONT,
                code_style="xcode",
                colors={
                    "text": "#15181D",
                    "dim": "#596270",
                    "accent": "#C42B3B",
                    "highlight": "#A35200",
                    "primary": "#0B57C2",
                    "secondary": "#4A5565",
                    "tertiary": "#0E7C66",
                    "surface": "#FFFFFF",
                },
                palette=("#0B57C2", "#C2410C", "#08775A", "#A04A8A", "#5B6068"),
                scale="auto",
            ),
            _builtin(
                "soft_pastel",
                "Dusky plum background with soft pastel accents: calm and friendly.",
                background="#252238",
                font=DEFAULT_FONT,
                code_style="zenburn",
                colors={
                    "text": "#F3EEFA",
                    "dim": "#B0A8C4",
                    "accent": "#F7879F",
                    "highlight": "#FCE38A",
                    "primary": "#86BDFF",
                    "secondary": "#FFC27F",
                    "tertiary": "#9BEBC9",
                    "surface": "#2C2843",
                },
                palette=("#86BDFF", "#FFC27F", "#9E8BEF", "#9BEBC9", "#F7879F"),
                scale="auto",
            ),
            _builtin(
                "bold_neon",
                "Violet-black background, electric cyan, magenta and yellow, large type: for social video.",
                background="#0B0614",
                font=DEFAULT_FONT,
                code_style="monokai",
                colors={
                    "text": "#F7F4FF",
                    "dim": "#A59CC2",
                    "accent": "#FF2E8B",
                    "highlight": "#F4FF3A",
                    "primary": "#00C8FF",
                    "secondary": "#FF8A1F",
                    "tertiary": "#39FF9C",
                    "surface": "#170F27",
                },
                palette=("#00C8FF", "#FF2E8B", "#F4FF3A", "#8C5BFF", "#39FF9C"),
                scale="large",
            ),
        )
    }
)
