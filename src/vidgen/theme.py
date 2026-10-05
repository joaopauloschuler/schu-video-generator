"""Theme: colors, sizes, font and background resolved from config + defaults.

Lookup precedence (highest first): values in ``video.yaml`` > defaults registered by extensions
(:meth:`Theme.add_defaults`) > built-in defaults. This module does not import manim.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidgen.config import ThemeConfig
from vidgen.errors import VidgenError

DEFAULT_COLORS: dict[str, str] = {
    "text": "#E8EAED",
    "dim": "#6B7280",
    "accent": "#FF6B6B",
    "highlight": "#FFD166",
    "primary": "#58C4DD",
    "secondary": "#F2A541",
    "tertiary": "#83C167",
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


class Theme:
    """Resolved theme values. Build one per project with ``Theme(project.config.theme)``."""

    def __init__(self, config: ThemeConfig | None = None) -> None:
        self._config = config if config is not None else ThemeConfig()
        self._registered_colors: dict[str, str] = {}
        self._registered_sizes: dict[str, int | float] = {}

    @property
    def background(self) -> str:
        """Background color (hex)."""
        return self._config.background

    @property
    def font(self) -> str:
        """Font family name."""
        return self._config.font

    @property
    def colors(self) -> dict[str, str]:
        """All color tokens after applying precedence (a copy)."""
        return {**DEFAULT_COLORS, **self._registered_colors, **self._config.colors}

    @property
    def sizes(self) -> dict[str, int | float]:
        """All size tokens after applying precedence (a copy)."""
        return {**DEFAULT_SIZES, **self._registered_sizes, **self._config.sizes}

    @property
    def palette(self) -> list[str]:
        """Ordered series colors (a copy)."""
        palette = self._config.palette if self._config.palette is not None else DEFAULT_PALETTE
        return list(palette)

    def color(self, name_or_hex: str) -> str:
        """Resolve a color token (``"primary"``) to hex; strings starting with ``#`` pass through."""
        if name_or_hex.startswith("#"):
            return name_or_hex
        colors = self.colors
        try:
            return colors[name_or_hex]
        except KeyError:
            known = ", ".join(sorted(colors))
            raise VidgenError(f"unknown theme color '{name_or_hex}'; known colors: {known}") from None

    def size(self, name_or_value: str | int | float) -> int | float:
        """Resolve a size token (``"body"``) to a font size; numbers pass through."""
        if not isinstance(name_or_value, str):
            return name_or_value
        sizes = self.sizes
        try:
            return sizes[name_or_value]
        except KeyError:
            known = ", ".join(sorted(sizes))
            raise VidgenError(f"unknown theme size '{name_or_value}'; known sizes: {known}") from None

    def palette_color(self, index: int) -> str:
        """The ``index``-th palette color, wrapping around."""
        palette = self.palette
        return palette[index % len(palette)]

    def add_defaults(
        self,
        colors: Mapping[str, str] | None = None,
        sizes: Mapping[str, int | float] | None = None,
    ) -> None:
        """Register extra default tokens (used by ``register_theme_defaults``).

        They override built-in defaults but never values set in ``video.yaml``.
        """
        if colors:
            for name, value in colors.items():
                if not isinstance(value, str) or not value.startswith("#"):
                    raise VidgenError(f"theme default color '{name}' must be a hex string, got {value!r}")
            self._registered_colors.update(colors)
        if sizes:
            self._registered_sizes.update(sizes)
