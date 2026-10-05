"""Bundled fonts and font roles (DESIGN.md §21).

vidgen ships three SIL OFL font families as package data (``vidgen/data/fonts``, licences next
to the files): Inter (sans), Source Serif 4 (serif) and JetBrains Mono NL (mono, without
ligatures so code reads as typed). :func:`register_bundled_fonts` makes them known to Pango for
this process, so no system install is needed; system fonts keep working, and a family that is
also installed system-wide is simply found twice (same name, either copy renders it).

Pango reads the registered files when it builds its font map, i.e. at the first text laid out in
the process: registration must come before that. The render worker registers at start, and
:mod:`vidgen.helpers` / :mod:`vidgen.regions` register when imported (before any vidgen text).

Font **roles** name what a text is for (``heading``, ``quote``, ``code``...); a theme maps a
role to a family token (``sans``, ``serif``, ``mono`` = theme ``font``, ``font_serif``,
``font_mono``) or to a literal family name (``Theme.font_for``). Apart from registration this
module does not import manim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: Folder holding the bundled font families (one sub-folder per family, with its ``OFL.txt``).
FONTS_DIR = Path(__file__).resolve().parent / "data" / "fonts"

SANS_FAMILY = "Inter"
SERIF_FAMILY = "Source Serif 4"
MONO_FAMILY = "JetBrains Mono NL"


@dataclass(frozen=True)
class BundledFamily:
    """A bundled font family: its Pango family name, folder and files per style."""

    family: str
    folder: str
    regular: str
    bold: str
    italic: str | None = None

    @property
    def files(self) -> list[Path]:
        """The family's font files."""
        names = [self.regular, self.bold] + ([self.italic] if self.italic else [])
        return [FONTS_DIR / self.folder / name for name in names]

    @property
    def license(self) -> Path:
        """The family's licence text (SIL Open Font License 1.1)."""
        return FONTS_DIR / self.folder / "OFL.txt"


BUNDLED_FAMILIES: tuple[BundledFamily, ...] = (
    BundledFamily(SANS_FAMILY, "Inter", "Inter-Regular.ttf", "Inter-Bold.ttf", "Inter-Italic.ttf"),
    BundledFamily(SERIF_FAMILY, "SourceSerif4", "SourceSerif4-Regular.ttf", "SourceSerif4-Bold.ttf", "SourceSerif4-It.ttf"),
    BundledFamily(MONO_FAMILY, "JetBrainsMono", "JetBrainsMonoNL-Regular.ttf", "JetBrainsMonoNL-Bold.ttf"),
)

#: Family tokens a font role may name, and the theme value each stands for.
FONT_TOKENS: dict[str, str] = {"sans": "font", "serif": "font_serif", "mono": "font_mono"}

#: Roles whose default is not ``sans``: code listings use the mono family, the big quote mark
#: of the ``quote`` scene the serif family. Every other role defaults to ``sans``.
ROLE_DEFAULTS: dict[str, str] = {"code": "mono", "quote_mark": "serif"}

#: The roles built-in scenes read (documented in docs/CONFIG.md "Fonts").
BUILTIN_ROLES: tuple[str, ...] = ("body", "heading", "quote", "quote_mark", "code")

_registered: list[Path] | None = None


def bundled_font_files() -> list[Path]:
    """Every bundled font file (all families)."""
    return [path for family in BUNDLED_FAMILIES for path in family.files]


def bundled_font_file(family: str, *, bold: bool = False, italic: bool = False) -> Path | None:
    """The bundled file of ``family`` in that style (``None`` if not bundled), e.g. for Pillow."""
    for entry in BUNDLED_FAMILIES:
        if entry.family == family:
            name = entry.italic if italic and entry.italic else entry.bold if bold else entry.regular
            return FONTS_DIR / entry.folder / name
    return None


def register_bundled_fonts() -> list[Path]:
    """Make the bundled fonts available to Pango in this process; returns the files registered.

    Idempotent (later calls return the first result). A file that cannot be registered is
    logged as a warning and skipped: text in that family then falls back to an installed font
    of the same name, else to Pango's default. Call before the first text is laid out.
    """
    global _registered
    if _registered is not None:
        return list(_registered)
    import manimpango

    done: list[Path] = []
    for path in bundled_font_files():
        ok = False
        if path.is_file():
            try:
                ok = bool(manimpango.register_font(str(path)))
            except Exception as exc:  # noqa: BLE001 - a platform font API error must not stop a render
                log.warning("could not register bundled font %s: %s", path.name, exc)
                continue
        if ok:
            done.append(path)
        else:
            log.warning("could not register bundled font %s (system fonts are used instead)", path)
    _registered = done
    _forget_font_lists()
    return list(done)


def _forget_font_lists() -> None:
    """Drop Manim's cached font list, so its missing-font warning knows the bundled families."""
    import sys

    module = sys.modules.get("manim.mobject.text.text_mobject")
    if module is None:
        return
    for name in ("Text", "MarkupText"):
        cached = getattr(getattr(module, name, None), "font_list", None)
        if cached is not None and hasattr(cached, "cache_clear"):
            cached.cache_clear()
