"""The ``lightning`` and ``rainbow`` beat actions (DESIGN.md §69.61) on a ``stage``: a flash of
lightning with a bolt and thunder after it, and a rainbow fading in (or out) in the sky. Written
against ``vidgen.api`` only, like project actions. They draw nothing themselves (``animates =
False``, like ``light``): the runner cues them when their beat starts and the stage shows them on
the scene clock, whatever plays meanwhile."""

from typing import Any

from vidgen.api import *


def _place_problems(action: Action, params: Any, example: str) -> list[tuple[str, str]]:
    """At most one place, a mark of the stage or an x from 0 to 1."""
    names = action.config.targets()
    if len(names) > 1:
        return [("target", f"one place per action: write `{example}` (a mark or an x from 0 to 1)")]
    place = _place(action)
    if place is not None:
        try:
            mark_x(place, params.stage_marks())
        except ValueError as exc:
            return [("target", str(exc))]
    return []


def _place(action: Action) -> str | float | None:
    """The action's place (its target: a mark, or an x written as a number), or ``None``."""
    names = action.config.targets()
    if not names:
        return None
    try:
        return float(names[0])
    except ValueError:
        return names[0]


@action("lightning")
class Lightning(Action):
    """Lightning strikes at `at` of the beat: the whole set flashes two or three times and a bolt
    strikes the ground (`- lightning: left`: where, a mark or an x; default a place picked by the
    scene), and its thunder follows `distance` km later (a third of a km a second; with foley).
    In a room the windows flash and the room lights up a little, without a bolt. Stage scenes
    only; rain with `lightning: true` strikes on its own."""

    class Options(ActionOptions):
        distance: float = Field(THUNDER_DISTANCE, ge=0.0, le=MAX_DISTANCE)
        """How far away it strikes (km): the thunder comes 3 s later per km, quieter, longer and lower; a far strike flashes less."""
        bolt: bool = True
        """false: a flash only (sheet lightning), no bolt."""
        seed: int | None = None
        """Varies the bolt's shape and the flashes; default: one from the scene and the time."""

    run_time = FLASH_SECONDS
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False
    number_target = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "strike_lightning"):
            return [("action", f"lightning is for stage scenes; a {scene_cls.__name__} scene has no sky to flash")]
        return _place_problems(self, params, "- lightning: left")

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Strike at scene ``time``."""
        o = self.options
        scene.strike_lightning(_place(self), time, distance=o.distance, bolt=o.bolt, seed=o.seed)


@action("rainbow")
class RainbowAction(Action):
    """A rainbow fades in over `run_time` seconds (3) from `at` of the beat and stays (`- rainbow:
    centre`: where its middle stands, a mark or an x; default the middle of the stage), a half ring
    standing on the horizon behind the hills, the ground and everything on it; best after rain.
    `hide: true` fades the rainbows out instead. Outdoors only (not in a room). Stage scenes only."""

    class Options(ActionOptions):
        width: float = Field(RAINBOW_WIDTH, gt=0.0, le=3.0)
        """How wide it is across, in frame widths."""
        opacity: float = Field(RAINBOW_OPACITY, gt=0.0, le=1.0)
        """How strongly it shows when fully in (it stays a little see-through)."""
        hide: bool = False
        """true: the rainbows shown so far fade out (no place)."""

    run_time = RAINBOW_FADE_SECONDS
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False
    number_target = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "show_rainbow"):
            return [("action", f"rainbow is for stage scenes; a {scene_cls.__name__} scene has no sky for it")]
        if getattr(params, "room", None) is not None:
            return [("action", "a rainbow is in the sky outdoors, not in a room (the stage has room:)")]
        if self.options.hide and self.config.targets():
            return [("target", "hide: true fades the rainbows out; it takes no place")]
        return _place_problems(self, params, "- rainbow: centre")

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Fade a rainbow in at scene ``time`` (or every rainbow out, with ``hide``)."""
        seconds = self.run_time if self.config.run_time is None else float(self.config.run_time)
        if self.options.hide:
            scene.hide_rainbows(time, seconds)
        else:
            scene.show_rainbow(_place(self), time, seconds, width=self.options.width, opacity=self.options.opacity)
