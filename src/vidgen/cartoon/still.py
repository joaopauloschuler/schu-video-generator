"""Stills: ``vidgen character NAME --png`` (one declared character, DESIGN.md §69.1) and the prop
gallery (every built-in prop, §69.8)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vidgen.config import CharacterEntry
from vidgen.project import Project
from vidgen.render.worker import FRAME_SHORT_SIDE, frame_size
from vidgen.theme import Theme

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


def write_props_png(theme: Theme, path: Path, *, width: int = 960, height: int = 540) -> Path:
    """Draw every built-in prop (:data:`~vidgen.cartoon.props.PROP_KINDS`) in ``theme``, each
    in a cell with its name below, on the theme background, and write a ``width`` x ``height``
    PNG to ``path`` (folders are created; colours reduced to a 64-colour palette, so the file is
    small enough for the docs)."""
    from manim import Camera, Text, VGroup, tempconfig

    from vidgen.cartoon.props import PROP_KINDS, draw_prop

    frame_width, frame_height = frame_size(width, height)
    rows = -(-len(PROP_KINDS) // GALLERY_COLUMNS)
    cell_w, cell_h = frame_width / GALLERY_COLUMNS, frame_height / rows
    settings = {
        "pixel_width": width, "pixel_height": height, "frame_width": frame_width, "frame_height": frame_height,
        "background_color": theme.background,
    }
    with tempconfig(settings):
        cells = VGroup()
        for k, kind in enumerate(PROP_KINDS):
            row, column = divmod(k, GALLERY_COLUMNS)
            left, top = -frame_width / 2 + column * cell_w, frame_height / 2 - row * cell_h
            prop = draw_prop(kind, height=0.6 * cell_h, theme=theme, character_height=1.2 * cell_h)
            if prop.width > 0.8 * cell_w:
                prop.scale(0.8 * cell_w / prop.width)
            prop.shift([left + cell_w / 2, top - 0.75 * cell_h, 0.0] - prop.feet())
            label = Text(kind, font=theme.font, font_size=0.11 * cell_h * 72, color=theme.color("text"))
            label.move_to([left + cell_w / 2, top - 0.87 * cell_h, 0.0])
            cells.add(prop, label)
        camera = Camera()
        camera.capture_mobjects([cells])
        image = camera.get_image().convert("RGB").quantize(colors=64)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path
