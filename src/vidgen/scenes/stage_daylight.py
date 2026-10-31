"""A day passing in one scene (DESIGN.md §105.3): the part of a ``stage`` that fades the light to
another time of day (the ``time_of_day`` action) and switches the lights on by themselves as the
light passes dusk, and off as it passes dawn. Written against ``vidgen.api`` only;
:class:`DayPassing` is a part of :class:`~vidgen.scenes.stage.Stage`.

The fade itself is the ``light`` action's (§69.31: the grade of the sky, the ground and everything
on the set, the stars fading in and out, the shadows, an iso place's pools of light growing with
:func:`~vidgen.cartoon.lighting.pool_strength`). Where the fade crosses :data:`DUSK_DARK`
(:func:`dusk_crossing`), each light that switches by itself (an iso place's
:data:`AUTO_LIGHT_KINDS`, a flat stage's lamps; not those with ``auto_light: false``) comes on (or
goes out) over :data:`AUTO_SWITCH_SECONDS`, a little early or late by its name
(:func:`auto_switch_time`), so a street's lamps light one after another.
"""

from typing import Any

from vidgen.api import *


class DayPassing:
    """The day-passing part of a ``stage`` (DESIGN.md §105.3)."""

    def _light_uses(self) -> list[Any]:
        """The scene's actions that change the light: ``light`` and ``time_of_day``."""
        return [*self.action_uses("light"), *self.action_uses("time_of_day")]

    def pass_time(self, setting: str, start: float, seconds: float, *, move_sun: bool = False, auto_lights: bool = True) -> list[str]:
        """Fade the light to the preset ``setting`` from scene time ``start`` over ``seconds``
        (:meth:`change_light`; from daylight to night through a sunset, from night to day through
        a morning: :func:`day_stages`) and, with ``auto_lights``, switch the lights on as it passes
        dusk or off as it passes dawn (not for ``indoor``, which is no time of day). The names
        switched."""
        light = getattr(self, "light", None)
        start, seconds = float(start), max(float(seconds), 0.0)
        before = light_at(light.base, light.changes, start) if light is not None else self.base_light
        crossing = None
        done = 0.0
        for preset, share in day_stages(before, setting):
            begin, length = start + done * seconds, (share - done) * seconds
            self.change_light(preset, begin, length, move_sun=move_sun)
            after = self.flashback_look(resolve_light(preset, self.theme))
            crossing = crossing or dusk_crossing(before, after, begin, length)
            before, done = after, share
        if not auto_lights or setting == "indoor" or crossing is None:
            return []
        return self._auto_switch(crossing[0], crossing[1], start, seconds)

    def _auto_switch(self, crossing: float, on: bool, start: float, seconds: float) -> list[str]:
        """Switch the lights that switch by themselves on (or off) around scene time
        ``crossing`` of a fade from ``start`` over ``seconds``; those already so stay. The names
        switched."""
        switched: list[str] = []
        if self.params.iso is not None:
            for name in self.params.iso.auto_lit():
                time = auto_switch_time(name, crossing, start, seconds)
                changed = name in self.iso_objects and self.iso_change(name, time, AUTO_SWITCH_SECONDS, auto=True, on=on)
                if self.iso_switch_vehicles([name], on, time) or changed:   # a driven car's headlights (§105.1)
                    switched.append(name)
        given = dict(zip(self.params.prop_names(), self.params.stage_props()))
        for name, live in getattr(self, "living", {}).items():
            prop = given.get(name)
            if live.kind != "lamp" or prop is None or not prop.auto_light:
                continue
            time = auto_switch_time(name, crossing, start, seconds)
            if live.is_on(time) != on:
                live.switch(on, time, AUTO_SWITCH_SECONDS)
                switched.append(name)
        if switched and getattr(self, "living", None):
            self._watch_living()
        return switched


__all__ = ["DayPassing"]
