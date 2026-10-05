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

DEFAULT_BACKGROUND = "#0E1116"
DEFAULT_FONT = "Inter"
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
DEFAULT_SIZES: dict[str, int | float] = {
    "title": 56,
    "subtitle": 42,
    "heading": 36,
    "body": 32,
    "caption": 24,
    "small": 20,
}


@dataclass(frozen=True)
class ThemePreset:
    """A named set of theme values; ``None``/empty means "not set by this preset".

    Values not set fall through to ``base`` (another preset, if given), then to the defaults.
    Build one with :func:`make_preset`, which validates the values.
    """

    name: str
    description: str = ""
    base: str | None = None
    background: str | None = None
    font: str | None = None
    code_style: str | None = None
    colors: Mapping[str, str] = field(default_factory=dict)
    palette: tuple[str, ...] | None = None
    sizes: Mapping[str, int | float] = field(default_factory=dict)
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
    code_style: str | None = None,
    colors: Mapping[str, str] | None = None,
    palette: Sequence[str] | None = None,
    sizes: Mapping[str, int | float] | None = None,
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
    if font is not None and (not isinstance(font, str) or not font.strip()):
        raise VidgenError(f"{where}: font must be a font family name, got {font!r}")
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
        code_style=code_style,
        colors=MappingProxyType(dict(colors or {})),
        palette=tuple(palette) if palette is not None else None,
        sizes=MappingProxyType(dict(sizes or {})),
        origin=origin,
    )


BUILTIN_PRESETS: Mapping[str, ThemePreset] = MappingProxyType(
    {
        "dark_tech": ThemePreset(
            name="dark_tech",
            description="The default look: near-black background, light text, bright accents.",
            background=DEFAULT_BACKGROUND,
            font=DEFAULT_FONT,
            code_style=DEFAULT_CODE_STYLE,
            colors=MappingProxyType(dict(DEFAULT_COLORS)),
            palette=tuple(DEFAULT_PALETTE),
        ),
        "light_academic": ThemePreset(
            name="light_academic",
            description="Paper-like off-white background, near-black text, deep ink accents.",
            background="#F8F7F3",
            font=DEFAULT_FONT,
            code_style="xcode",
            colors=MappingProxyType(
                {
                    "text": "#1F2328",
                    "dim": "#59606B",
                    "accent": "#B42318",
                    "highlight": "#A64B00",
                    "primary": "#1D4ED8",
                    "secondary": "#C2410C",
                    "tertiary": "#15803D",
                    "surface": "#FFFFFF",
                }
            ),
            palette=("#1D4ED8", "#C2410C", "#7E22CE", "#15803D"),
        ),
        "high_contrast": ThemePreset(
            name="high_contrast",
            description="Black background, white text, saturated accents (WCAG AAA 7:1) and larger small text.",
            background="#000000",
            font=DEFAULT_FONT,
            code_style=DEFAULT_CODE_STYLE,
            colors=MappingProxyType(
                {
                    "text": "#FFFFFF",
                    "dim": "#C9CED6",
                    "accent": "#FF7A7A",
                    "highlight": "#FFE14D",
                    "primary": "#4DD2FF",
                    "secondary": "#FFAA4D",
                    "tertiary": "#7EE787",
                    "surface": "#141414",
                }
            ),
            palette=("#4DD2FF", "#FFAA4D", "#D7A8FF", "#7EE787"),
            sizes=MappingProxyType({"caption": 26, "small": 24}),
        ),
    }
)
