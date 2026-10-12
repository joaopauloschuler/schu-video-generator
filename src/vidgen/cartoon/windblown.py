"""Drawing a stage's wind (DESIGN.md §69.32): :class:`SwayingProp` bends a tree, bush, plant,
sign or lamp about its base, and :class:`StageWind` sets, for a scene time, every swaying prop's
lean and every character's trailing pieces (:meth:`~vidgen.cartoon.character.Character.set_wind`)
from a :class:`~vidgen.cartoon.wind.Wind`. The maths is in :mod:`vidgen.cartoon.wind`."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np
from manim import Mobject

from vidgen.cartoon.character import Character
from vidgen.cartoon.wind import SWAYS, Wind, bent_points, sway_degrees, trail_degrees, trail_memory_seconds, wind_phase


class SwayingProp:
    """A built-in prop of a :data:`~vidgen.cartoon.wind.SWAYS` kind that bends in the wind about
    its base, from its points as they are now (it must not move otherwise); ``x_share`` is where
    it stands (0 left edge .. 1 right edge of the stage)."""

    def __init__(self, prop: Mobject, kind: str, x_share: float) -> None:
        self.prop = prop
        self.kind = kind
        self.x_share = x_share
        self.phase = wind_phase(getattr(prop, "name", kind))
        self.foot_y = float(prop.get_bottom()[1])
        self.height = float(prop.height)
        self.rest = [(member, np.array(member.points, dtype=float)) for member in prop.family_members_with_points()]
        self.degrees = 0.0

    def lean(self, degrees: float) -> None:
        """Bend it so its top leans ``degrees`` to the right (0: as drawn)."""
        if degrees == self.degrees:
            return
        self.degrees = degrees
        bend_from = SWAYS[self.kind].bend_from
        for member, rest in self.rest:
            member.points = bent_points(rest, degrees, self.foot_y, self.height, bend_from)


class StageWind:
    """A stage's ``wind`` on screen: :meth:`update` leans the ``props`` and turns the trailing
    pieces of the ``characters`` (name -> character) for a scene time; ``x_share(x)`` turns an x
    on screen into a share of the stage's width (where a gust reaches it)."""

    def __init__(
        self, wind: Wind, props: Sequence[SwayingProp], characters: Mapping[str, Character], x_share: Callable[[float], float],
    ) -> None:
        self.wind = wind
        self.props = list(props)
        self.characters = {name: figure for name, figure in characters.items() if figure.has_trails}
        self.x_share = x_share

    def update(self, now: float) -> None:
        """Lean every prop and turn every trailing piece for scene time ``now``."""
        wind = self.wind
        for item in self.props:
            force = wind.force(now, wind.delay(item.x_share, now))
            item.lean(sway_degrees(item.kind, force, now, item.phase))
        for name, figure in self.characters.items():
            delay = wind.delay(self.x_share(float(figure.feet()[0])), now)
            figure.set_wind(trail_degrees(wind, now, delay=delay, phase=wind_phase(name)))

    def moving(self, start: float, end: float) -> bool:
        """Whether anything may move between scene times ``start`` and ``end`` (the wind blows, or
        a trailing piece is still swinging back after it dropped)."""
        if not self.props and not self.characters:
            return False
        return self.wind.blowing(start - trail_memory_seconds(), end)

    def mobjects(self) -> list[Mobject]:
        """The mobjects it moves: the swaying props and the characters with trailing pieces."""
        return [item.prop for item in self.props] + list(self.characters.values())

    def particle_push(self, start: float, now: float) -> tuple[float, float]:
        """For particles (:data:`~vidgen.particle_field.ParticleWind`): the force added up from
        ``start`` to ``now`` and the force at ``now``."""
        return self.wind.blown(start, now), self.wind.force(now)
