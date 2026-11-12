"""Bundled fonts and font roles (DESIGN.md §21).

schu-video-generator ships three SIL OFL font families as package data (``vidgen/data/fonts``, licences next
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

A project's own fonts are the ``.ttf``, ``.otf`` and ``.woff`` files in its ``fonts/`` folder
(:func:`project_fonts` reads each file's family, weight and style with fontTools).
:func:`register_project_fonts` makes them known to Pango like the bundled ones, ``web`` pages get
an ``@font-face`` per file (:mod:`vidgen.web.inputs`) and :func:`font_file` finds one for Pillow.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from vidgen.errors import VidgenError

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

#: The project folder whose font files vidgen uses, and the suffixes it reads there. A ``.woff``
#: (zlib) is read by fontTools as it is; a ``.woff2`` needs the ``brotli`` package, which a
#: plain install of vidgen does not bring, so vidgen does not read ``.woff2`` files.
PROJECT_FONTS_FOLDER = "fonts"
PROJECT_FONT_SUFFIXES: tuple[str, ...] = (".ttf", ".otf", ".woff")
UNREAD_FONT_SUFFIXES: tuple[str, ...] = (".woff2",)

_registered: list[Path] | None = None
_project_registered: dict[Path, Path] = {}
_project_fonts: list[ProjectFont] = []


@dataclass(frozen=True)
class ProjectFont:
    """A font file of the project: its path, its path from the project folder (posix:
    ``fonts/Name-Bold.ttf``), and the family, weight and style read from the file. ``weight`` is
    ``(lightest, heaviest)``: equal for a static font, the ``wght`` range of a variable one."""

    path: Path
    rel: str
    family: str
    weight: tuple[int, int]
    italic: bool


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


def project_font_files(root: Path) -> list[Path]:
    """The font files vidgen reads in the project at ``root``: every ``.ttf``, ``.otf`` and
    ``.woff`` under its ``fonts/`` folder (sorted)."""
    folder = root / PROJECT_FONTS_FOLDER
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in PROJECT_FONT_SUFFIXES and p.is_file())


@lru_cache(maxsize=256)
def _read_names(path: Path, size: int, mtime_ns: int) -> tuple[str, tuple[int, int], bool]:
    """Family, weight range and italic of the font file at ``path`` (``size`` and ``mtime_ns``
    only key the cache). The family is the typographic one (name 16, else name 1), so the
    Medium and the Bold file of one family carry the same name."""
    from fontTools.ttLib import TTFont

    with TTFont(path, lazy=True, fontNumber=0) as font:
        names, os2 = font["name"], font["OS/2"]
        family = names.getDebugName(16) or names.getDebugName(1)
        if not family:
            raise ValueError("it has no family name")
        weight = (int(os2.usWeightClass), int(os2.usWeightClass))
        if "fvar" in font:
            weight = next(((int(a.minValue), int(a.maxValue)) for a in font["fvar"].axes if a.axisTag == "wght"), weight)
        italic = bool(os2.fsSelection & 0x201)  # bit 0 italic, bit 9 oblique
    return str(family), weight, italic


def font_warnings(root: Path) -> list[str]:
    """One warning per ``.woff2`` file in the project's ``fonts/`` folder that has no ``.ttf``,
    ``.otf`` or ``.woff`` of the same file name beside it: vidgen does not read ``.woff2``."""
    folder = root / PROJECT_FONTS_FOLDER
    unread = sorted(p for p in folder.rglob("*") if p.suffix.lower() in UNREAD_FONT_SUFFIXES) if folder.is_dir() else []
    return [
        f"{path.relative_to(root).as_posix()}: vidgen does not read .woff2 font files; this one is used only by a web page "
        "whose own @font-face names the file. For the whole video, put the .ttf, .otf or .woff file of the same font in the folder."
        for path in unread if not any(path.with_suffix(suffix).is_file() for suffix in PROJECT_FONT_SUFFIXES)
    ]


def project_fonts(root: Path) -> list[ProjectFont]:
    """The project's font files with what each says about itself (:class:`ProjectFont`). A file
    fontTools cannot read is a :class:`VidgenError` naming it; a ``.woff2`` file is not read
    (:func:`font_warnings` says so in ``vidgen validate``)."""
    fonts = []
    for path in project_font_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            stat = path.stat()
            family, weight, italic = _read_names(path, stat.st_size, stat.st_mtime_ns)
        except Exception as exc:  # noqa: BLE001 - fontTools raises many types for a broken file
            raise VidgenError(f"{rel}: not a font file vidgen can read ({type(exc).__name__}: {exc}). "
                              "Replace it with the font's .ttf, .otf or .woff file, or remove it.") from exc
        fonts.append(ProjectFont(path, rel, family, weight, italic))
    return fonts


def _sfnt_copy(font: ProjectFont, folder: Path) -> Path:
    """``font`` (a ``.woff``) as a plain ``.ttf`` / ``.otf`` in ``folder``, written once per
    content: Pango on Windows and Pillow do not read WOFF."""
    import hashlib

    from fontTools.ttLib import TTFont

    data = font.path.read_bytes()
    with TTFont(font.path) as source:
        suffix = ".otf" if source.sfntVersion == "OTTO" else ".ttf"
        target = folder / f"{font.path.stem}-{hashlib.sha256(data).hexdigest()[:12]}{suffix}"
        if not target.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f"{target.name}.{os.getpid()}.part")
            source.flavor = None
            source.save(partial)
            os.replace(partial, target)
    return target


def register_project_fonts(root: Path, build_dir: Path) -> list[ProjectFont]:
    """Make the fonts in the ``fonts/`` folder of the project at ``root`` available to Pango in
    this process (and to :func:`font_file`); returns them. A ``.woff`` is registered through a
    ``.ttf`` / ``.otf`` copy that this function writes to ``build_dir / "fonts"``. Like
    :func:`register_bundled_fonts`: call before the first text is laid out; a file Pango
    refuses is a warning."""
    global _project_fonts
    fonts = project_fonts(root)
    _project_fonts = fonts
    new = [font for font in fonts if font.path not in _project_registered]
    if not new:
        return fonts
    import manimpango

    for font in new:
        try:
            usable = _sfnt_copy(font, build_dir / PROJECT_FONTS_FOLDER) if font.path.suffix.lower() == ".woff" else font.path
            ok = bool(manimpango.register_font(str(usable)))
        except Exception as exc:  # noqa: BLE001 - a platform font API error must not stop a render
            log.warning("could not register the project's font %s: %s", font.rel, exc)
            continue
        if ok:
            _project_registered[font.path] = usable
        else:
            log.warning("could not register the project's font %s (text in %s falls back to another font)", font.rel, font.family)
    _forget_font_lists()
    return fonts


def font_file(family: str, *, bold: bool = False, italic: bool = False) -> Path | None:
    """A ``.ttf`` / ``.otf`` file of ``family`` in that style, e.g. for Pillow: the registered
    project font (:func:`register_project_fonts`) nearest in style and weight, else the bundled
    file (:func:`bundled_font_file`), else ``None``."""
    wanted = 700 if bold else 400
    mine = [font for font in _project_fonts if font.family == family and font.path in _project_registered]
    if not mine:
        return bundled_font_file(family, bold=bold, italic=italic)
    best = min(mine, key=lambda f: (f.italic != italic, 0 if f.weight[0] <= wanted <= f.weight[1] else min(abs(w - wanted) for w in f.weight)))
    return _project_registered[best.path]


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
