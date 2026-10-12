"""``vidgen character NAME --png``: one still of a declared character (DESIGN.md §69.1)."""

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
        figure = build_character(entry, theme=theme, height=FRAME_SHORT_SIDE * STILL_CHARACTER_HEIGHT, facing=facing)
        figure.move_to([0, 0, 0])
        camera = Camera()
        camera.capture_mobjects([figure])
        image = camera.get_image().convert("RGB")
    target = path if path is not None else default_png_path(project, entry.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return CharacterStill(target, width, height)
