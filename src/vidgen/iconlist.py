"""``vidgen list-icons``: the available icons as text, JSON or a labelled contact sheet (§22).

The sheet draws every icon with the same code as a render (:func:`vidgen.icon_mobject.build_icon`
and Manim's Cairo camera), so what it shows is what a scene shows; names and categories are
written with Pillow under each icon. Pages are at most about ``1.25 x`` their width high (like
storyboard sheets), so an AI agent can read them when it opens the PNG.

:func:`catalogue_markdown` writes the icon catalogue ``docs/ICONS.md`` from the manifest
(``tools/vendor_icons.py`` regenerates it; a test keeps it in sync).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw

from vidgen.errors import VidgenError
from vidgen.icons import CATEGORIES, IconInfo, builtin_sources, categories
from vidgen.sheets import BACKGROUND, MUTED, PAGE_RATIO, TEXT, fit_line, load_font

if TYPE_CHECKING:
    from vidgen.theme import Theme

#: Sheet width, columns and cell height in pixels; icon box size inside a cell.
SHEET_WIDTH = 1280
SHEET_COLUMNS = 8
CELL_HEIGHT = 150
ICON_PX = 64
HEADER_HEIGHT = 64
#: Colour the icons are drawn in on the sheet.
ICON_COLOR = "#11141A"
#: Tags shown per icon in the text listing.
TAGS_SHOWN = 8


def check_category(category: str | None, icons: Sequence[IconInfo]) -> None:
    """Raise :class:`VidgenError` for a category no icon has and that is not built in."""
    known = categories(icons)
    if category is not None and category not in known:
        raise VidgenError(f"unknown icon category '{category}'; categories: {', '.join(known)}")


def source_line() -> str:
    """``Lucide (lucide-static 1.52.0, ISC)`` for the built-in set(s)."""
    parts = [f"{name.title()} ({s['package']} {s['version']}, {s['license']})" for name, s in builtin_sources().items()]
    return ", ".join(parts)


def summary_lines(icons: Sequence[IconInfo], total: int) -> list[str]:
    """Human listing: ``name  category  [project]  (alias: ...)  tags`` per icon and a count line."""
    width = max((len(i.name) for i in icons), default=0)
    cat_width = max((len(i.category) for i in icons), default=0)
    lines = []
    for info in icons:
        origin = "" if info.origin == "builtin" else ("  [project, overrides built-in]" if info.overrides else "  [project]")
        tags = ", ".join(info.tags[:TAGS_SHOWN]) + (", ..." if len(info.tags) > TAGS_SHOWN else "")
        aliases = f"  (alias: {', '.join(info.aliases)})" if info.aliases else ""
        lines.append(f"{info.name:<{width}}  {info.category:<{cat_width}}{origin}{aliases}  {tags}".rstrip())
    shown = f"{len(icons)} of {total}" if len(icons) != total else str(total)
    lines.append(f"{shown} icons; built-in set: {source_line()}")
    return lines


def categories_json(icons: Sequence[IconInfo]) -> list[dict[str, Any]]:
    """Every category with its description (built-in ones) and number of icons."""
    return [
        {"name": name, "description": CATEGORIES.get(name, ""), "count": sum(1 for i in icons if i.category == name)}
        for name in categories(icons)
    ]


class SheetColors:
    """Colours of an icon sheet: the default black on white, or a theme's (its background, the
    icons in ``primary``, names in ``text``, categories in ``dim``)."""

    def __init__(self, theme: Theme | None = None) -> None:
        self.background: Any = theme.background if theme is not None else "#%02X%02X%02X" % BACKGROUND
        self.icon = theme.color("primary") if theme is not None else ICON_COLOR
        self.text: Any = theme.color("text") if theme is not None else TEXT
        self.muted: Any = theme.color("dim") if theme is not None else MUTED


def _draw_icons(icons: Sequence[IconInfo], columns: int, cell_w: float, rows: int, colors: SheetColors) -> Image.Image:
    """The icons drawn by Manim's camera on a ``columns x rows`` grid of ``cell_w x CELL_HEIGHT``
    cells (icon in the upper part of each cell)."""
    from manim import Camera, tempconfig

    from vidgen.icon_mobject import build_icon

    width, height = round(columns * cell_w), rows * CELL_HEIGHT
    unit = ICON_PX  # 1 Manim unit = one icon box
    settings = {
        "pixel_width": width,
        "pixel_height": height,
        "frame_width": width / unit,
        "frame_height": height / unit,
        "background_color": colors.background,
    }
    with tempconfig(settings):
        camera = Camera()
        mobs = []
        for i, info in enumerate(icons):
            row, col = divmod(i, columns)
            x = (col + 0.5) * cell_w / unit - width / unit / 2
            y = height / unit / 2 - (row * CELL_HEIGHT + 14 + ICON_PX / 2) / unit
            mobs.append(build_icon(info, 1.0, colors.icon).move_to([x, y, 0]))
        camera.capture_mobjects(mobs)
        return camera.get_image().convert("RGB")


def render_sheets(icons: Sequence[IconInfo], path: Path, title: str, theme: Theme | None = None) -> list[Path]:
    """Write labelled contact sheets of ``icons`` (name, then category) to ``path`` and, when
    they need more than one page, ``<stem>-2.png``... (older extra pages are removed); returns
    the files written. With ``theme``, in its colours (see :class:`SheetColors`)."""
    colors = SheetColors(theme)
    if not icons:
        raise VidgenError("no icons to draw (check --search/--category)")
    cell_w = SHEET_WIDTH / SHEET_COLUMNS
    per_page = SHEET_COLUMNS * max(1, int((SHEET_WIDTH * PAGE_RATIO - HEADER_HEIGHT) // CELL_HEIGHT))
    pages = [icons[i : i + per_page] for i in range(0, len(icons), per_page)]
    name_font, small_font, title_font = load_font(17, bold=True), load_font(14), load_font(22, bold=True)
    written: list[Path] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    for number, page_icons in enumerate(pages, start=1):
        rows = math.ceil(len(page_icons) / SHEET_COLUMNS)
        image = Image.new("RGB", (SHEET_WIDTH, HEADER_HEIGHT + rows * CELL_HEIGHT), colors.background)
        image.paste(_draw_icons(page_icons, SHEET_COLUMNS, cell_w, rows, colors), (0, HEADER_HEIGHT))
        draw = ImageDraw.Draw(image)
        heading = title if len(pages) == 1 else f"{title} (page {number}/{len(pages)})"
        draw.text((20, 18), fit_line(title_font, heading, SHEET_WIDTH - 40), font=title_font, fill=colors.text)
        for i, info in enumerate(page_icons):
            row, col = divmod(i, SHEET_COLUMNS)
            cx = (col + 0.5) * cell_w
            top = HEADER_HEIGHT + row * CELL_HEIGHT + 14 + ICON_PX + 12
            label = fit_line(name_font, info.name, cell_w - 10)
            draw.text((cx, top), label, font=name_font, fill=colors.text, anchor="ma")
            note = info.category if info.origin == "builtin" else f"{info.category} · project"
            draw.text((cx, top + 24), fit_line(small_font, note, cell_w - 10), font=small_font, fill=colors.muted, anchor="ma")
        target = path if number == 1 else path.with_name(f"{path.stem}-{number}{path.suffix or '.png'}")
        image.save(target, format="PNG")
        written.append(target)
    number = len(pages) + 1
    while (stale := path.with_name(f"{path.stem}-{number}{path.suffix or '.png'}")).is_file():
        stale.unlink()  # pages of an earlier, longer listing
        number += 1
    return written


def catalogue_markdown(manifest: dict[str, Any]) -> str:
    """The icon catalogue (``docs/ICONS.md``) for a built-in icon ``manifest``: per category a
    table of names, aliases and the first tags."""
    icons = manifest["icons"]
    sources = ", ".join(f"{n.title()} ({s['package']} {s['version']}, {s['license']})" for n, s in manifest["sources"].items())
    lines = [
        "# Icon catalogue",
        "",
        "<!-- Generated by tools/vendor_icons.py from src/vidgen/data/icons/manifest.json; do not edit. -->",
        "",
        f"{len(icons)} built-in icons from {sources}; licence and attribution in",
        "`THIRD_PARTY_NOTICES.md`. Use a name or an alias wherever an icon is asked for (`icon(\"cpu\")`,",
        "an `IconName` param). Search by concept with `vidgen list-icons --search TEXT` (names,",
        "aliases and tags), see them with `vidgen list-icons --sheet icons.png`, and add your own in",
        "`assets/icons/` (docs/CONFIG.md, \"Icons\").",
        "",
    ]
    for category, description in CATEGORIES.items():
        members = [e for e in icons if e["category"] == category]
        lines += [f"## {category} ({len(members)}): {description}", "", "| icon | aliases | tags |", "|---|---|---|"]
        for entry in sorted(members, key=lambda e: e["name"]):
            tags = ", ".join(entry["tags"][:TAGS_SHOWN]) + (", ..." if len(entry["tags"]) > TAGS_SHOWN else "")
            aliases = ", ".join(f"`{a}`" for a in entry.get("aliases", []))
            lines.append(f"| `{entry['name']}` | {aliases} | {tags.replace('|', '/')} |")
        lines.append("")
    return "\n".join(lines)
