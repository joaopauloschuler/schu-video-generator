"""The ``wind`` beat action (DESIGN.md §69.32): a ``stage``'s wind fades to a new strength,
starting at ``at`` of the beat; written against ``vidgen.api`` only, like project actions. It
draws nothing itself (``animates = False``, like ``light``): the runner cues it when its beat
starts, and the stage fades the wind over ``run_time`` seconds from then, whatever plays
meanwhile."""

import difflib
from typing import Any

from vidgen.api import *


@action("wind")
class WindAction(Action):
    """Change a stage's wind from `at` of the beat: `- wind: 0.8` (0 calm .. 1 a gale to the
    right, negative to the left) or calm, breeze, windy, gale; it fades over `run_time` seconds
    (default 2) and lasts until another `wind` action. Stage scenes only."""

    run_time = WIND_FADE_SECONDS
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False
    number_target = True

    def level(self) -> float:
        """The signed level the action fades to (0 when it gives none or a wrong one; validate
        reports those)."""
        names = self.config.targets()
        try:
            return wind_level(names[0]) if len(names) == 1 else 0.0
        except ValueError:
            return 0.0

    def problems(self) -> list[tuple[str, str]]:
        """One level: a number from -1 to 1 or a known name."""
        names = self.config.targets()
        if len(names) > 1:
            return [("target", "one wind per action (add a wind action per change)")]
        if not names:
            return [("target", f"how strong? write `- wind: 0.6` (0 calm .. 1 a gale; negative: to the left) or {', '.join(WIND_LEVELS)}")]
        try:
            wind_level(names[0])
        except ValueError as exc:
            close = difflib.get_close_matches(names[0], WIND_LEVELS, n=1)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            return [("target", f"{exc}{hint}")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "change_wind"):
            return [("action", f"wind is for stage scenes; a {scene_cls.__name__} scene has nothing to blow")]
        return []

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Start the fade at scene ``time``."""
        seconds = self.run_time if self.config.run_time is None else float(self.config.run_time)
        scene.change_wind(self.level(), time, seconds)
