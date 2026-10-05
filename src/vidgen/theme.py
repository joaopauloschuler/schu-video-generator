"""Theme: colors, sizes, font, background and code style resolved from config, preset and defaults.

Lookup precedence (highest first, DESIGN.md §19):

1. values written in ``video.yaml`` (``theme.*``, after merging a variant),
2. the preset named by ``theme.preset`` (its ``base`` preset below it),
3. defaults registered by extensions (:meth:`Theme.add_defaults`, ``register_theme_defaults``),
4. built-in defaults (the ``dark_tech`` look).

Without ``theme.preset`` level 2 is empty. Presets are looked up when a value is read, so an
extension may register a project preset (:meth:`Theme.add_preset`) after the theme was built.
This module does not import manim.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidgen.config import ThemeConfig
from vidgen.errors import VidgenError
from vidgen.presets import (
    BUILTIN_PRESETS,
    DEFAULT_BACKGROUND,
    DEFAULT_CODE_STYLE,
    DEFAULT_COLORS,
    DEFAULT_FONT,
    DEFAULT_PALETTE,
    DEFAULT_SIZES,
    ThemePreset,
)

__all__ = [
    "DEFAULT_BACKGROUND",
    "DEFAULT_CODE_STYLE",
    "DEFAULT_COLORS",
    "DEFAULT_FONT",
    "DEFAULT_PALETTE",
    "DEFAULT_SIZES",
    "Theme",
]


class Theme:
    """Resolved theme values. Build one per project with ``Theme(project.config.theme)``."""

    def __init__(self, config: ThemeConfig | None = None) -> None:
        self._config = config if config is not None else ThemeConfig()
        self._registered_colors: dict[str, str] = {}
        self._registered_sizes: dict[str, int | float] = {}
        self._registered_presets: dict[str, ThemePreset] = {}

    def derive(self, config: ThemeConfig) -> Theme:
        """A theme for ``config`` that shares this theme's registered defaults and presets
        (e.g. a variant's theme in the same project)."""
        theme = Theme(config)
        theme._registered_colors = dict(self._registered_colors)
        theme._registered_sizes = dict(self._registered_sizes)
        theme._registered_presets = dict(self._registered_presets)
        return theme

    # ----- presets ---------------------------------------------------------------------------

    @property
    def preset(self) -> str | None:
        """Name of the selected preset (``theme.preset``), or ``None``."""
        return self._config.preset

    @property
    def presets(self) -> dict[str, ThemePreset]:
        """Every preset this theme knows: built-in, then project presets (a copy)."""
        return {**BUILTIN_PRESETS, **self._registered_presets}

    def preset_chain(self) -> list[ThemePreset]:
        """The selected preset and its bases, lowest first (empty without a preset).

        Raises :class:`VidgenError` if the preset is not known.
        """
        chain: list[ThemePreset] = []
        name = self._config.preset
        presets = self.presets
        while name is not None:
            found = presets.get(name)
            if found is None:
                known = ", ".join(sorted(presets))
                raise VidgenError(
                    f"unknown theme preset '{name}'; known presets: {known} (project presets must be "
                    "registered with register_theme_preset before the theme is used)"
                )
            chain.insert(0, found)
            name = found.base
        return chain

    def add_preset(self, preset: ThemePreset) -> None:
        """Register a project preset (used by ``register_theme_preset``)."""
        if preset.name in BUILTIN_PRESETS:
            raise VidgenError(f"theme preset '{preset.name}' is a built-in preset; choose another name")
        if preset.name in self._registered_presets:
            other = self._registered_presets[preset.name].origin
            raise VidgenError(f"theme preset '{preset.name}' is already registered by {other}")
        if preset.base is not None and preset.base not in self.presets:
            known = ", ".join(sorted(self.presets))
            raise VidgenError(f"theme preset '{preset.name}': unknown base preset '{preset.base}'; known presets: {known}")
        self._registered_presets[preset.name] = preset

    def _from_preset(self, attribute: str) -> object | None:
        """The last value of ``attribute`` set along the preset chain."""
        value = None
        for preset in self.preset_chain():
            own = getattr(preset, attribute)
            if own is not None:
                value = own
        return value

    # ----- values ----------------------------------------------------------------------------

    @property
    def background(self) -> str:
        """Background color (hex)."""
        value = self._config.background or self._from_preset("background")
        return str(value) if value is not None else DEFAULT_BACKGROUND

    @property
    def font(self) -> str:
        """Font family name."""
        value = self._config.font or self._from_preset("font")
        return str(value) if value is not None else DEFAULT_FONT

    @property
    def code_style(self) -> str:
        """Pygments style for code listings."""
        value = self._config.code_style or self._from_preset("code_style")
        return str(value) if value is not None else DEFAULT_CODE_STYLE

    @property
    def colors(self) -> dict[str, str]:
        """All color tokens after applying precedence (a copy)."""
        colors = {**DEFAULT_COLORS, **self._registered_colors}
        for preset in self.preset_chain():
            colors.update(preset.colors)
        colors.update(self._config.colors)
        return colors

    @property
    def sizes(self) -> dict[str, int | float]:
        """All size tokens after applying precedence (a copy)."""
        sizes = {**DEFAULT_SIZES, **self._registered_sizes}
        for preset in self.preset_chain():
            sizes.update(preset.sizes)
        sizes.update(self._config.sizes)
        return sizes

    @property
    def palette(self) -> list[str]:
        """Ordered series colors (a copy)."""
        if self._config.palette is not None:
            return list(self._config.palette)
        preset = self._from_preset("palette")
        return list(preset) if isinstance(preset, tuple) else list(DEFAULT_PALETTE)

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

        They override built-in defaults but never a selected preset or values set in
        ``video.yaml``.
        """
        if colors:
            for name, value in colors.items():
                if not isinstance(value, str) or not value.startswith("#"):
                    raise VidgenError(f"theme default color '{name}' must be a hex string, got {value!r}")
            self._registered_colors.update(colors)
        if sizes:
            for name, value in sizes.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    raise VidgenError(f"theme default size '{name}' must be a positive number, got {value!r}")
            self._registered_sizes.update(sizes)
