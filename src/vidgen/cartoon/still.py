"""Stills: ``vidgen character NAME --png`` (one declared character, DESIGN.md §69.1), the prop
gallery (every built-in prop, §69.8) and ``vidgen character-sheet`` (every pose, expression and
mouth shape of a character on one PNG, §69.16)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from vidgen.config import CharacterEntry
from vidgen.project import Project
from vidgen.render.worker import FRAME_SHORT_SIDE, frame_size
from vidgen.theme import Theme

if TYPE_CHECKING:
    from PIL import Image as PILImage

    from vidgen.cartoon.character import Character

#: Pixels of the still's shorter side (the longer one follows the video's aspect ratio).
STILL_SHORT_SIDE_PX = 720
#: The character's height as a fraction of the frame's shorter side.
STILL_CHARACTER_HEIGHT = 0.8


@dataclass(frozen=True)
class CharacterStill:
    """What :func:`write_character_png` wrote."""

    path: Path
    width: int
    height: int


def default_png_path(project: Project, name: str) -> Path:
    """``<root>/exports/character_<name>.png``."""
    return project.exports_dir / f"character_{name}.png"


def write_character_png(
    project: Project, entry: CharacterEntry, theme: Theme, path: Path | None = None, *, facing: str = "right"
) -> CharacterStill:
    """Draw the character ``entry`` of ``project`` in ``theme`` on the theme background, in the
    video's aspect ratio, and write it to ``path`` (default: :func:`default_png_path`; folders
    are created). Call it with the project's extensions active (``extensions.project_session``)."""
    from manim import Camera, tempconfig

    from vidgen.cartoon.character import build_character

    fmt = project.config.format
    scale = STILL_SHORT_SIDE_PX / min(fmt.width, fmt.height)
    width, height = round(fmt.width * scale / 2) * 2, round(fmt.height * scale / 2) * 2
    frame_width, frame_height = frame_size(width, height)
    settings = {
        "pixel_width": width, "pixel_height": height, "frame_width": frame_width, "frame_height": frame_height,
        "background_color": theme.background,
    }
    with tempconfig(settings):
        figure = build_character(entry, theme=theme, height=FRAME_SHORT_SIDE * STILL_CHARACTER_HEIGHT, facing=facing, root=project.root)
        figure.move_to([0, 0, 0])
        camera = Camera()
        camera.capture_mobjects([figure])
        image = camera.get_image().convert("RGB")
    target = path if path is not None else default_png_path(project, entry.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return CharacterStill(target, width, height)


#: Columns of the prop gallery (rows follow from the number of props).
GALLERY_COLUMNS = 6


def write_props_png(
    theme: Theme, path: Path, *, width: int = 960, height: int = 540, kinds: Sequence[str] | None = None,
    columns: int = GALLERY_COLUMNS,
) -> Path:
    """Draw the built-in props ``kinds`` (default: the ones that are not
    :data:`~vidgen.cartoon.props.FURNITURE`, :data:`~vidgen.cartoon.props.SMALL_PROPS` or vehicles) in ``theme``, each in a cell of a ``columns`` wide
    grid with its name below (a prop with more shapes once per shape, :data:`PROP_SHAPES`), on
    the theme background, and write a ``width`` x ``height`` PNG to ``path`` (folders are
    created; colours reduced to a 64-colour palette, so the file is small enough for the docs)."""
    from manim import Camera, Text, VGroup, tempconfig

    from vidgen.cartoon.props import FURNITURE, PROP_KINDS, PROP_SHAPES, SMALL_PROPS, VEHICLE_KINDS, draw_prop

    chosen = [kind for kind in PROP_KINDS if kind not in (*FURNITURE, *SMALL_PROPS, *VEHICLE_KINDS)] if kinds is None else list(kinds)
    shown = [(kind, shape) for kind in chosen for shape in PROP_SHAPES.get(kind, (None,))]
    frame_width, frame_height = frame_size(width, height)
    rows = -(-len(shown) // columns)
    cell_w, cell_h = frame_width / columns, frame_height / rows
    settings = {
        "pixel_width": width, "pixel_height": height, "frame_width": frame_width, "frame_height": frame_height,
        "background_color": theme.background,
    }
    with tempconfig(settings):
        cells = VGroup()
        for k, (kind, shape) in enumerate(shown):
            row, column = divmod(k, columns)
            left, top = -frame_width / 2 + column * cell_w, frame_height / 2 - row * cell_h
            prop = draw_prop(kind, height=0.6 * cell_h, theme=theme, character_height=1.2 * cell_h, shape=shape)
            if prop.width > 0.8 * cell_w:
                prop.scale(0.8 * cell_w / prop.width)
            prop.shift([left + cell_w / 2, top - 0.75 * cell_h, 0.0] - prop.feet())
            name = kind if shape is None or shape == PROP_SHAPES[kind][0] else f"{kind} ({shape})"
            label = Text(name, font=theme.font, font_size=0.11 * cell_h * 72, color=theme.color("text"))
            label.move_to([left + cell_w / 2, top - 0.87 * cell_h, 0.0])
            cells.add(prop, label)
        camera = Camera()
        camera.capture_mobjects([cells])
        image = camera.get_image().convert("RGB").quantize(colors=64)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path


def write_looks_png(
    theme: Theme, path: Path, entries: Sequence[CharacterEntry], *, columns: int = 4, cell_width: int = 120, cell_height: int = 210,
) -> Path:
    """Draw each generated character of ``entries`` from the side and from the front, side by
    side, with its name below, in rows of ``columns`` characters on the theme background, and
    write the PNG to ``path`` (folders are created; 64 colours, small enough for the docs). The
    look gallery of DESIGN.md §69.47. A figure reaching past its character's cell (a long tail)
    is moved back inside it."""
    from manim import Camera, Text, VGroup, tempconfig

    from vidgen.cartoon.character import build_character

    rows = -(-len(entries) // columns)
    width, height = 2 * columns * cell_width, rows * cell_height
    frame_width, frame_height = frame_size(width, height)
    unit_w, unit_h = frame_width / (2 * columns), frame_height / rows
    settings = {
        "pixel_width": width, "pixel_height": height, "frame_width": frame_width, "frame_height": frame_height,
        "background_color": theme.background,
    }
    with tempconfig(settings):
        cells = VGroup()
        for k, entry in enumerate(entries):
            row, column = divmod(k, columns)
            top, ground = frame_height / 2 - row * unit_h, frame_height / 2 - row * unit_h - 0.84 * unit_h
            for view, facing in enumerate(("right", "front")):
                figure = build_character(entry.model_copy(update={"idle": False}), theme=theme, height=0.72 * unit_h, facing=facing)
                x = -frame_width / 2 + (2 * column + view + 0.5) * unit_w
                figure.shift([x, ground, 0.0] - figure.feet())
                cell_left = -frame_width / 2 + 2 * column * unit_w + 0.03 * unit_w
                cell_right = cell_left + 1.94 * unit_w
                figure.shift([max(0.0, cell_left - figure.get_left()[0]) - max(0.0, figure.get_right()[0] - cell_right), 0.0, 0.0])
                cells.add(figure)
            label = Text(entry.name, font=theme.font, font_size=0.075 * unit_h * 72, color=theme.color("text"))
            label.move_to([-frame_width / 2 + (2 * column + 1) * unit_w, top - 0.92 * unit_h, 0.0])
            cells.add(label)
        camera = Camera()
        camera.capture_mobjects([cells])
        image = camera.get_image().convert("RGB").quantize(colors=64)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path


# ----- character sheet (vidgen character-sheet) -------------------------------------------------------

#: Most cells in one row of a character sheet.
SHEET_COLUMNS = 8
#: Cell sizes in px: every cell is this wide; a pose cell (the whole figure) is taller than a
#: close-up cell (the head: expressions and mouth shapes).
SHEET_CELL_WIDTH = 128
SHEET_POSE_CELL_HEIGHT = 160
SHEET_HEAD_CELL_HEIGHT = 128
SHEET_MARGIN = 20
SHEET_GUTTER = 12
#: Line heights in px: the title, the line under it, a section heading, a cell's label.
SHEET_TITLE_LINE, SHEET_SUBTITLE_LINE, SHEET_SECTION_LINE, SHEET_LABEL_LINE = 36, 24, 30, 22
#: Colours in the written PNG (palette), which keeps the file small.
SHEET_COLORS = 64
#: Close-up cells: the head (with face, hat or glasses) fills this share of the cell.
HEAD_FILL = 0.6
#: Parts a close-up frames (those the character has; none: the whole figure).
HEAD_PARTS: tuple[str, ...] = ("head", "eyes", "brows", "mouth", "accessory")

SheetKind = Literal["pose", "expression", "mouth", "view"]
#: Sections drawn as the whole figure (the others are close-ups of the head).
WHOLE_FIGURE_KINDS: frozenset[str] = frozenset({"pose", "view"})


@dataclass(frozen=True)
class SheetSection:
    """A row group of a character sheet: ``kind`` ``pose`` or ``view`` (whole figure; a view is
    a way it faces other than its side, DESIGN.md §69.47), ``expression`` or ``mouth``
    (close-ups of the head); ``names`` in order; ``own`` the character's own entries."""

    kind: SheetKind
    title: str
    names: tuple[str, ...]
    own: tuple[str, ...] = ()


@dataclass(frozen=True)
class SheetCell:
    """Where one picture goes on the sheet (px, top-left corner), its section and name."""

    section: int
    name: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class SheetLayout:
    """The sheet's size, the top of each section heading and every cell (:func:`sheet_layout`)."""

    width: int
    height: int
    columns: int
    section_tops: tuple[int, ...]
    cells: tuple[SheetCell, ...]


def character_sheet_sections(entry: CharacterEntry, root: Path) -> list[SheetSection]:
    """The sections of ``entry``'s sheet without drawing it: its poses and expressions (built-in,
    then its own), its mouth shapes (none without a mouth; an svg look is read from ``root``)
    and, for a generated look, its front view (kind ``view``)."""
    from vidgen.cartoon.cast import character_part_shapes
    from vidgen.cartoon.poses import merged_table

    sections = [
        SheetSection(kind, f"{kind}s", tuple(merged_table(kind, own)), tuple(own))
        for kind, own in (("pose", entry.poses), ("expression", entry.expressions))
    ]
    mouths = character_part_shapes(entry, root).get("mouth", [])
    if mouths:
        sections.append(SheetSection("mouth", "mouth shapes", tuple(mouths)))
    if entry.look.svg is None:
        sections.append(SheetSection("view", "front view", ("front",)))
    return sections


def sheet_layout(sections: Sequence[SheetSection], columns: int = SHEET_COLUMNS) -> SheetLayout:
    """Lay out ``sections`` (no drawing): a title, then per section a heading and its cells in
    rows of at most ``columns`` (fewer when no section has that many)."""
    columns = max(1, min(columns, max((len(s.names) for s in sections), default=1)))
    width = 2 * SHEET_MARGIN + columns * SHEET_CELL_WIDTH + (columns - 1) * SHEET_GUTTER
    y = SHEET_MARGIN + SHEET_TITLE_LINE + SHEET_SUBTITLE_LINE
    tops: list[int] = []
    cells: list[SheetCell] = []
    for index, section in enumerate(sections):
        tops.append(y)
        y += SHEET_SECTION_LINE
        cell_height = SHEET_POSE_CELL_HEIGHT if section.kind in WHOLE_FIGURE_KINDS else SHEET_HEAD_CELL_HEIGHT
        for k, name in enumerate(section.names):
            row, column = divmod(k, columns)
            x = SHEET_MARGIN + column * (SHEET_CELL_WIDTH + SHEET_GUTTER)
            cells.append(SheetCell(index, name, x, y + row * (cell_height + SHEET_LABEL_LINE + SHEET_GUTTER), SHEET_CELL_WIDTH, cell_height))
        rows = math.ceil(len(section.names) / columns)
        y += rows * (cell_height + SHEET_LABEL_LINE + SHEET_GUTTER)
    return SheetLayout(width, y + SHEET_MARGIN - SHEET_GUTTER, columns, tuple(tops), tuple(cells))


@dataclass(frozen=True)
class CharacterSheet:
    """What :func:`write_character_sheet` wrote: the character's name, the PNG, its size in px and
    bytes, the sections."""

    character: str
    path: Path
    width: int
    height: int
    bytes: int
    sections: tuple[SheetSection, ...]


def default_sheet_path(project: Project, name: str) -> Path:
    """``<root>/exports/character_sheet_<name>.png``."""
    return project.exports_dir / f"character_sheet_{name}.png"


def write_character_sheet(
    project: Project, entry: CharacterEntry, theme: Theme, path: Path | None = None
) -> CharacterSheet:
    """Draw every pose (whole figure, rest face), expression and mouth shape (head close-ups) of
    the character ``entry`` of ``project`` in ``theme``, facing right, and its front view (a
    generated look), each in a labelled cell on
    the theme background, and write the sheet to ``path`` (default: :func:`default_sheet_path`;
    folders are created) as a PNG of :data:`SHEET_COLORS` colours. Call it with the project's
    extensions active (``extensions.project_session``)."""
    from PIL import Image, ImageDraw

    from vidgen.sheets import BACKGROUND, BORDER, MUTED, TEXT, fit_line, load_font

    sections = character_sheet_sections(entry, project.root)
    layout = sheet_layout(sections)
    page = Image.new("RGB", (layout.width, layout.height), BACKGROUND)
    draw = ImageDraw.Draw(page)
    title, subtitle = load_font(24, bold=True), load_font(15)
    heading, label = load_font(17, bold=True), load_font(14)
    text_width = layout.width - 2 * SHEET_MARGIN
    draw.text((SHEET_MARGIN, SHEET_MARGIN), fit_line(title, f"{entry.name} \u2014 character sheet", text_width), font=title, fill=TEXT)
    note = "poses with the rest face; expressions and mouth shapes close up; facing right"
    if any(section.kind == "view" for section in sections):
        note += "; front view at the end"
    if any(section.own for section in sections):
        note += "; * = the character's own"
    draw.text((SHEET_MARGIN, SHEET_MARGIN + SHEET_TITLE_LINE), fit_line(subtitle, note, text_width), font=subtitle, fill=MUTED)
    for index, section in enumerate(sections):
        draw.text((SHEET_MARGIN, layout.section_tops[index] + 4), f"{section.title} ({len(section.names)})", font=heading, fill=TEXT)
        cells = [cell for cell in layout.cells if cell.section == index]
        pictures = _section_pictures(project, entry, theme, section, SHEET_CELL_WIDTH, cells[0].height)
        for cell, picture in zip(cells, pictures):
            page.paste(picture, (cell.x, cell.y))
            draw.rectangle((cell.x - 1, cell.y - 1, cell.x + cell.width, cell.y + cell.height), outline=BORDER)
            name = f"{cell.name}*" if cell.name in section.own else cell.name
            draw.text((cell.x, cell.y + cell.height + 4), fit_line(label, name, cell.width), font=label, fill=TEXT)
    target = path if path is not None else default_sheet_path(project, entry.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    page.quantize(colors=SHEET_COLORS, dither=Image.Dither.NONE).save(target, optimize=True)
    return CharacterSheet(entry.name, target, layout.width, layout.height, target.stat().st_size, tuple(sections))


def _section_pictures(
    project: Project, entry: CharacterEntry, theme: Theme, section: SheetSection, width: int, height: int
) -> list[PILImage.Image]:
    """One ``width`` x ``height`` picture per name of ``section``, drawn by Manim's camera."""
    from manim import Camera, tempconfig

    from vidgen.cartoon.character import build_character

    frame_width, frame_height = frame_size(width, height)
    settings = {
        "pixel_width": width, "pixel_height": height, "frame_width": frame_width, "frame_height": frame_height,
        "background_color": theme.background,
    }
    pictures = []
    with tempconfig(settings):
        probe = build_character(entry, theme=theme, height=1.0, root=project.root)
        whole = section.kind in WHOLE_FIGURE_KINDS
        if whole:
            sizes = [(_show_whole(probe, section.kind, name).width, probe.height) for name in section.names]
            figure_height = min(0.84 * frame_height / max(h for _, h in sizes), 0.9 * frame_width / max(w for w, _ in sizes))
        else:
            box_width, box_height = _box_size(_head_box(probe))
            figure_height = HEAD_FILL * min(frame_width / box_width, frame_height / box_height)
        figure = build_character(entry, theme=theme, height=figure_height, root=project.root)
        if not whole:
            low, high = _head_box(figure)
            figure.shift([-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, 0.0])
        for name in section.names:
            if whole:
                _show_whole(figure, section.kind, name)
                low, high = _box(figure)
                figure.shift([-(low[0] + high[0]) / 2, -0.42 * frame_height - figure.feet()[1], 0.0])
            elif section.kind == "expression":
                figure.set_expression(name)
            else:
                figure.swap("mouth", name)
            camera = Camera()
            camera.capture_mobjects([figure])
            pictures.append(camera.get_image().convert("RGB"))
    return pictures


def _show_whole(figure: Character, kind: str, name: str) -> Character:
    """``figure`` in pose ``name`` (``kind`` ``pose``) or facing ``name`` (``view``)."""
    return figure.set_pose(name) if kind == "pose" else figure.face(name)


def _box(figure: Character, parts: Sequence[str] | None = None) -> tuple[list[float], list[float]]:
    """The lower-left and upper-right corners (x, y) of the figure's drawn ``parts`` (default: all)."""
    import numpy as np

    points = np.vstack([figure.parts[part].get_all_points() for part in parts or list(figure.parts)])
    return list(points[:, :2].min(axis=0)), list(points[:, :2].max(axis=0))


def _head_box(figure: Character) -> tuple[list[float], list[float]]:
    """:func:`_box` of the head and face parts (:data:`HEAD_PARTS`), else of the whole figure."""
    return _box(figure, [part for part in HEAD_PARTS if figure.has_part(part)])


def _box_size(box: tuple[list[float], list[float]]) -> tuple[float, float]:
    """Width and height of a :func:`_box` (never 0)."""
    low, high = box
    return max(high[0] - low[0], 1e-6), max(high[1] - low[1], 1e-6)
