"""Theme: colors, sizes, fonts, background and code style resolved from config, preset and defaults.

Lookup precedence (highest first, DESIGN.md §19):

1. values written in ``video.yaml`` (``theme.*``, after merging a variant),
2. the preset named by ``theme.preset`` (its ``base`` preset below it),
3. defaults registered by extensions (:meth:`Theme.add_defaults`, ``register_theme_defaults``),
4. built-in defaults (the ``dark_tech`` look).

Without ``theme.preset`` level 2 is empty. A type scale (``theme.scale``, or the preset's) is
shorthand for the six built-in sizes at the level where it is chosen, below that level's
``sizes``; with none chosen the built-in sizes are the ``auto`` scale for the theme's
orientation (``large`` in portrait, DESIGN.md §20). Presets are looked up when a value is read, so an
extension may register a project preset (:meth:`Theme.add_preset`) after the theme was built.
This module does not import manim.
"""

from __future__ import annotations

from collections.abc import Mapping

from vidgen.config import FormatConfig, ThemeConfig
from vidgen.errors import VidgenError
from vidgen.fonts import FONT_TOKENS, ROLE_DEFAULTS
from vidgen.presets import (
    BUILTIN_PRESETS,
    DEFAULT_BACKGROUND,
    DEFAULT_CODE_STYLE,
    DEFAULT_COLORS,
    DEFAULT_FONT,
    DEFAULT_FONT_MONO,
    DEFAULT_FONT_SERIF,
    DEFAULT_PALETTE,
    DEFAULT_SIZES,
    ThemePreset,
)
from vidgen.scales import DEFAULT_SCALE, Orientation, frame_orientation, resolve_scale, scale_sizes

__all__ = [
    "DEFAULT_BACKGROUND",
    "DEFAULT_CODE_STYLE",
    "DEFAULT_COLORS",
    "DEFAULT_FONT",
    "DEFAULT_FONT_MONO",
    "DEFAULT_FONT_SERIF",
    "DEFAULT_PALETTE",
    "DEFAULT_SIZES",
    "Theme",
]


class Theme:
    """Resolved theme values. Build one per project with :meth:`for_format` (or
    ``Theme(config, orientation=...)``); the orientation only matters for the ``auto`` scale."""

    def __init__(self, config: ThemeConfig | None = None, *, orientation: Orientation = "landscape") -> None:
        self._config = config if config is not None else ThemeConfig()
        self.orientation: Orientation = orientation
        self._registered_colors: dict[str, str] = {}
        self._registered_sizes: dict[str, int | float] = {}
        self._registered_presets: dict[str, ThemePreset] = {}

    @classmethod
    def for_format(cls, config: ThemeConfig, fmt: FormatConfig) -> Theme:
        """The theme of a project (or variant) whose final video has format ``fmt``."""
        return cls(config, orientation=frame_orientation(fmt.width, fmt.height))

    def derive(self, config: ThemeConfig, fmt: FormatConfig | None = None) -> Theme:
        """A theme for ``config`` (and frame ``fmt``, default: this theme's orientation) that
        shares this theme's registered defaults and presets (e.g. a variant's theme)."""
        orientation = self.orientation if fmt is None else frame_orientation(fmt.width, fmt.height)
        theme = Theme(config, orientation=orientation)
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
        """Sans font family: body text and every role without its own family."""
        value = self._config.font or self._from_preset("font")
        return str(value) if value is not None else DEFAULT_FONT

    @property
    def font_serif(self) -> str:
        """Serif font family (the ``serif`` token of font roles)."""
        value = self._config.font_serif or self._from_preset("font_serif")
        return str(value) if value is not None else DEFAULT_FONT_SERIF

    @property
    def font_mono(self) -> str:
        """Monospace font family (the ``mono`` token; code listings)."""
        value = self._config.font_mono or self._from_preset("font_mono")
        return str(value) if value is not None else DEFAULT_FONT_MONO

    @property
    def fonts(self) -> dict[str, str]:
        """Font roles as set by the preset chain, then ``video.yaml`` ``fonts`` (role -> family
        token or family name; a copy, without the built-in role defaults)."""
        fonts: dict[str, str] = {}
        for preset in self.preset_chain():
            fonts.update(preset.fonts)
        fonts.update(self._config.fonts)
        return fonts

    def font_for(self, role: str) -> str:
        """The font family for text of ``role`` (``heading``, ``quote``, ``code``...).

        The role's setting comes from ``video.yaml`` ``fonts``, else the preset chain, else the
        built-in default (``code`` -> ``mono``, ``quote_mark`` -> ``serif``, others ``sans``);
        a family token (``sans``, ``serif``, ``mono``) resolves to :attr:`font`,
        :attr:`font_serif` or :attr:`font_mono`, anything else is a family name.
        """
        setting = self.fonts.get(role) or ROLE_DEFAULTS.get(role, "sans")
        token = FONT_TOKENS.get(setting)
        return str(getattr(self, token)) if token is not None else setting

    @property
    def scale_setting(self) -> str:
        """The type scale as chosen (``compact``, ``standard``, ``large`` or ``auto``)."""
        value = self._config.scale or self._from_preset("scale")
        return str(value) if value is not None else DEFAULT_SCALE

    @property
    def scale(self) -> str:
        """The concrete type scale in use (``auto`` resolved by :attr:`orientation`)."""
        return resolve_scale(self.scale_setting, self.orientation)

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
        chain = self.preset_chain()
        chosen = self._config.scale is not None or any(p.scale is not None for p in chain)
        base = DEFAULT_SIZES if chosen else scale_sizes(DEFAULT_SCALE, self.orientation)
        sizes = {**base, **self._registered_sizes}
        for preset in chain:
            if preset.scale is not None:
                sizes.update(scale_sizes(preset.scale, self.orientation))
            sizes.update(preset.sizes)
        if self._config.scale is not None:
            sizes.update(scale_sizes(self._config.scale, self.orientation))
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
