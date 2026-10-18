"""Story props in a platform world (DESIGN.md §86.8), as plain data: keys, doors, coins, stars and
friendly blockers. No manim.

A coin or a star is written on the map (:data:`ITEM_SYMBOLS`) and floats in the middle of its
cell; a key, a door and a blocker are things standing on the stage (a prop or a character) that
the level's ``locks`` and ``blockers`` give a part in its rules. The rules that change them are in
:mod:`vidgen.world.moves` (pickups on the way, closed doors and blockers in the way) and
:mod:`vidgen.world.story_props` (opening doors, stepping aside, who holds a key).
"""

from __future__ import annotations

from dataclasses import dataclass

KEY = "key"
DOOR = "door"
COIN = "coin"
STAR = "star"
BLOCKER = "blocker"
#: The items picked up when a body's way touches them.
COLLECTIBLES: frozenset[str] = frozenset({COIN, STAR})
#: Map symbol -> the item floating in that (air) cell.
ITEM_SYMBOLS: dict[str, str] = {"$": COIN, "*": STAR}


@dataclass(frozen=True)
class Item:
    """A story prop of the level: its ``name`` and ``kind``, where it is (tile units: a coin's or
    a star's middle, else the feet of what stands there) and how tall it stands; a door's ``key``
    (``None``: not locked) and whether it is ``open``; whether a blocker has stepped ``aside``;
    who holds a key or has picked up a coin or a star (``holder``)."""

    name: str
    kind: str
    x: float
    y: float
    height: float = 0.0
    key: str | None = None
    open: bool = False
    aside: bool = False
    holder: str | None = None

    @property
    def blocks(self) -> bool:
        """Whether it is in the way: a closed door, a blocker that has not stepped aside."""
        return (self.kind == DOOR and not self.open) or (self.kind == BLOCKER and not self.aside)

    @property
    def label(self) -> str:
        """How messages name it: ``the closed door 'gate'``, ``'shelly'``, ``coin 'coin_2'``."""
        if self.kind == DOOR:
            return f"the {'locked' if self.key else 'closed'} door '{self.name}'"
        if self.kind == BLOCKER:
            return f"'{self.name}'"
        return f"{self.kind} '{self.name}'"

    @property
    def hint(self) -> str:
        """What clears it out of the way, as an action to write."""
        if self.kind == DOOR and self.key:
            return f"open it first with its key '{self.key}' (- open: {self.name}, by: <who holds {self.key}>)"
        if self.kind == DOOR:
            return f"open it first (- open: {self.name})"
        return f"ask it to move first (- step_aside: {self.name})"


__all__ = ["BLOCKER", "COIN", "COLLECTIBLES", "DOOR", "ITEM_SYMBOLS", "KEY", "STAR", "Item"]
