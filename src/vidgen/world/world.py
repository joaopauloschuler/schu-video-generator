"""The world of a platform scene (DESIGN.md §86): a level, the bodies and the story props
(:class:`~vidgen.world.items.Item`) in it, as plain data.

A *body* is a character or a prop standing in the level: its feet's ``x`` and ``y`` and its
``height``, in tile units. The rules (movement, jumps, pickups, doors) take a world and scripted
inputs and give the next one; renderers only draw worlds. No manim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from vidgen.errors import VidgenError
from vidgen.world.items import Item
from vidgen.world.level import Level

#: How many tiles tall a character of scale 1 is.
CHARACTER_TILES = 2.0


@dataclass(frozen=True)
class Body:
    """A character or a prop (``kind``) in the world: its feet at (``x``, ``y``) and its
    ``height``, tile units."""

    name: str
    kind: str
    x: float
    y: float
    height: float


@dataclass(frozen=True)
class Placing:
    """Where a body is asked to stand: at a spot of the level (``spot``), else at ``x`` (tile
    units) on the highest tile of that column. ``scale``: its height in characters of scale 1
    (:data:`CHARACTER_TILES` tiles each)."""

    name: str
    kind: str
    spot: str | None = None
    x: float | None = None
    scale: float = 1.0


@dataclass(frozen=True)
class World:
    """A level, the bodies in it (in the order placed) and its story props (``items``: the map's
    coins and stars, then the keys, doors and blockers of the stage)."""

    level: Level
    bodies: tuple[Body, ...] = ()
    items: tuple[Item, ...] = ()

    def body(self, name: str) -> Body:
        for body in self.bodies:
            if body.name == name:
                return body
        raise VidgenError(f"nothing named '{name}' is in the level (bodies: {', '.join(b.name for b in self.bodies) or 'none'})")

    def moved(self, name: str, x: float, y: float) -> World:
        """The world with the body ``name`` (and the item it is: a blocker) standing at (``x``,
        ``y``) instead."""
        self.body(name)
        bodies = tuple(replace(b, x=x, y=y) if b.name == name else b for b in self.bodies)
        return World(self.level, bodies, tuple(replace(i, x=x, y=y) if i.name == name else i for i in self.items))

    def item(self, name: str) -> Item | None:
        """The story prop named ``name`` (``None``: none is)."""
        return next((item for item in self.items if item.name == name), None)

    def with_items(self, *changed: Item) -> World:
        """The world with each of ``changed`` replacing the item of its name (added when new)."""
        by_name = {item.name: item for item in changed}
        kept = tuple(by_name.pop(i.name, i) for i in self.items)
        return World(self.level, self.bodies, kept + tuple(by_name.values()))


def place_bodies(level: Level, placings: Sequence[Placing]) -> World:
    """The world with each of ``placings`` standing where it asks; :class:`VidgenError` for an
    unknown spot or an x over a gap or outside the level."""
    bodies = []
    for placing in placings:
        height = CHARACTER_TILES * placing.scale
        if placing.spot is not None:
            spot = level.spot(placing.spot)
            bodies.append(Body(placing.name, placing.kind, spot.x, spot.y, height))
            continue
        x = float(placing.x if placing.x is not None else 0.0)
        if not 0.0 <= x <= level.columns:
            raise VidgenError(f"'{placing.name}' at x {x:g} is outside the level (0 to {level.columns} tiles)")
        column = level.column_at(x)
        y = level.top_surface(column)
        if y is None:
            raise VidgenError(f"'{placing.name}' would stand over a gap (map column {column + 1} has nothing to stand on); "
                              "put it at a spot or over a tile")
        bodies.append(Body(placing.name, placing.kind, x, y, height))
    return World(level, tuple(bodies), level.items)


__all__ = ["CHARACTER_TILES", "Body", "Placing", "World", "place_bodies"]
