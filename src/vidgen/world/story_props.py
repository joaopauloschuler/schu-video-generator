"""The rules of a platform world's story props (DESIGN.md §86.8) besides moving: opening and
closing doors (a locked one only by whoever holds its key, standing next to it), a blocker
stepping aside, a key taken, handed over or put down. Pure functions on a
:class:`~vidgen.world.world.World`, no manim; each refusal is a :class:`VidgenError` saying what
to write instead. Walking and jumping past them, and picking up coins and stars on the way, are
in :mod:`vidgen.world.moves`.
"""

from __future__ import annotations

from dataclasses import replace

from vidgen.errors import VidgenError
from vidgen.world.items import BLOCKER, DOOR, KEY, Item
from vidgen.world.world import World

#: How far (tiles across, feet to feet) from a door a character opens it, and how far up or down
#: (tiles) it may stand from the door's feet.
DOOR_REACH = 1.6
DOOR_REACH_UP = 0.5


def _kind(world: World, name: str, kind: str, what: str) -> Item:
    item = world.item(name)
    if item is None or item.kind != kind:
        known = ", ".join(i.name for i in world.items if i.kind == kind) or "none"
        raise VidgenError(f"'{name}' is not {what} of the level ({what}s: {known})")
    return item


def open_door(world: World, door: str, by: str | None = None, *, reach: bool = True) -> World:
    """The world once ``by`` (``None``: nobody in particular) has opened ``door``. A locked door
    (its :attr:`~vidgen.world.items.Item.key`) opens only by a character holding its key; whoever
    opens a door stands within :data:`DOOR_REACH` of it (``reach`` false: where it stands is not
    known, not checked). :class:`VidgenError` otherwise."""
    item = _kind(world, door, DOOR, "a door")
    if item.open:
        return world
    if item.key is not None:
        key = world.item(item.key)
        holder = key.holder if key is not None else None
        if by is None:
            raise VidgenError(f"the door '{door}' is locked: say who opens it with its key '{item.key}' "
                              f"(- open: {door}, by: {holder or '<who holds ' + item.key + '>'})")
        if holder != by:
            held = f" ('{holder}' holds it)" if holder else f"; pick it up first (- pick_up: {by}, to: {item.key})"
            raise VidgenError(f"'{by}' cannot open the door '{door}': it is locked and '{by}' does not hold its key '{item.key}'{held}")
    if by is not None and reach:
        body = world.body(by)
        across, up = abs(body.x - item.x), abs(body.y - item.y)
        if up > DOOR_REACH_UP:
            raise VidgenError(f"'{by}' is not standing on the floor of the door '{door}' ({up:.1f} tiles above or below it); "
                              "walk_to next to it first")
        if across > DOOR_REACH:
            raise VidgenError(f"'{by}' is too far from the door '{door}' to open it ({across:.1f} tiles; at most {DOOR_REACH:g}); "
                              "walk_to next to it first")
    return world.with_items(replace(item, open=True))


def close_door(world: World, door: str) -> World:
    """The world with ``door`` closed (it is in the way again; a locked one stays locked)."""
    return world.with_items(replace(_kind(world, door, DOOR, "a door"), open=False))


def step_aside(world: World, name: str) -> World:
    """The world once the blocker ``name`` has moved out of the way (it no longer blocks)."""
    return world.with_items(replace(_kind(world, name, BLOCKER, "a blocker"), aside=True))


def hold_key(world: World, key: str, holder: str | None) -> World:
    """The world with ``holder`` holding the key ``key`` (``None``: nobody, it was put down,
    thrown or blown away); a name that is not a key of the level leaves the world as it is."""
    item = world.item(key)
    if item is None or item.kind != KEY:
        return world
    return world.with_items(replace(item, holder=holder))


__all__ = ["DOOR_REACH", "DOOR_REACH_UP", "close_door", "hold_key", "open_door", "step_aside"]
