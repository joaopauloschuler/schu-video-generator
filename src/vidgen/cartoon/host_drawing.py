"""The drawing of a cartoon host (``host:``, DESIGN.md §71): its character and the floor line.

:func:`build_host` needs no stage: it builds the ``characters:`` entry with
:func:`~vidgen.cartoon.character.build_character`, measures it in its pose, asks
:func:`~vidgen.cartoon.host.host_layout` where it stands and builds it again at that height (so
its outline keeps the width a character of that height has).
"""

from __future__ import annotations

from pathlib import Path

from manim import Line, VGroup

from vidgen.cartoon.character import OUTLINE_WIDTH, REFERENCE_HEIGHT, Character, build_character, one_pixel_stroke
from vidgen.cartoon.host import Box, HostLayout, facing_for, host_layout
from vidgen.config import CharacterEntry, HostConfig
from vidgen.helpers import resolve_color
from vidgen.theme import Theme


class HostFigure(VGroup):
    """A host on screen: the floor line (if any) and its :attr:`character` standing on it, as
    :attr:`layout` placed them in :attr:`area`. The layout dump records it as one object of kind
    ``host``. The host actions (Step 134) keep the rest up to date: the :attr:`side` it stands
    on now, its feet's x on screen (:attr:`feet_x`) and its :attr:`room` (the reserved column or
    band, on screen), how far a ``host_move`` slid the content on screen (:attr:`content_shift`;
    a scene x is the screen x minus it), whether it is :attr:`present` (``host_enter`` /
    ``host_exit``) and what it points at (:attr:`pointing_at`)."""

    def __init__(self, character: Character, floor: Line | None, layout: HostLayout, config: HostConfig, area: Box | None = None) -> None:
        super().__init__(*([floor] if floor is not None else []), character)
        self.character = character
        self.floor = floor
        self.layout = layout
        self.config = config
        self.area: Box = area if area is not None else layout.reserve
        self.side: str = config.side
        self.feet_x: float = layout.feet[0]
        self.room: Box = layout.reserve
        self.content_shift = 0.0
        self.present = True
        self.pointing_at: str | None = None

    @property
    def at_home(self) -> bool:
        """Whether it stands where the scene placed it (on screen, not moved to the other side)."""
        return self.present and self.side == self.config.side

    @property
    def half_reach(self) -> float:
        """How far its drawing reaches from its feet on the wider side (a tail behind it), so a
        walk beyond the view's edge by this much leaves nothing of it showing, whichever way it
        faces."""
        feet = float(self.character.feet()[0])
        return max(feet - float(self.character.get_left()[0]), float(self.character.get_right()[0]) - feet)

    def scene_x(self, screen_x: float) -> float:
        """The scene x of a screen x (they differ by :attr:`content_shift` after a ``host_move``)."""
        return screen_x - self.content_shift

    @property
    def host_name(self) -> str:
        """The character's name."""
        return self.character.name


def _posed(entry: CharacterEntry, host: HostConfig, theme: Theme, root: Path | None, motion: str | None, height: float, facing: str) -> Character:
    figure = build_character(entry, theme=theme, height=height, facing="right" if facing == "front" else facing, root=root, motion=motion)
    if facing == "front":
        figure.face("front")   # an SVG character has no front view and keeps its side
    if host.pose is not None:
        figure.set_pose(host.pose)
    if host.expression is not None:
        figure.set_expression(host.expression)
    return figure


def build_host(
    host: HostConfig,
    entry: CharacterEntry,
    *,
    theme: Theme,
    area: Box,
    frame_width: float,
    frame_height: float,
    root: Path | None = None,
    motion: str | None = None,
) -> HostFigure:
    """The host ``host`` (its character ``entry``, coloured with ``theme``) standing in ``area``
    (the scene's safe area without the overlays' reserved room) of the frame."""
    facing = facing_for(host.side, host.facing)
    probe = _posed(entry, host, theme, root, motion, REFERENCE_HEIGHT, facing)
    layout = host_layout(area, frame_width, frame_height, host, probe.width / REFERENCE_HEIGHT)
    figure = _posed(entry, host, theme, root, motion, layout.height, layout.facing)
    # the drawing's middle (not the feet: an arm held out moves it) on the column's middle
    figure.shift([layout.feet[0] - figure.get_center()[0], layout.feet[1] - figure.feet()[1], 0.0])
    floor = None
    if layout.floor is not None:
        x0, x1, y = layout.floor
        width = max(OUTLINE_WIDTH * layout.height / REFERENCE_HEIGHT, one_pixel_stroke())
        floor = Line([x0, y, 0.0], [x1, y, 0.0], color=resolve_color(host.floor_color, theme), stroke_width=width)
        floor.name = "floor"
    return HostFigure(figure, floor, layout, host, area)
