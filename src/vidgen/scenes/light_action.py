"""The ``light`` beat action (DESIGN.md §69.31): a ``stage``'s light fades to a preset or a tint,
starting at ``at`` of the beat; written against ``vidgen.api`` only, like project actions. It draws
nothing itself (``animates = False``): the runner cues it when its beat starts, and the stage
fades its colour grade, stars and shadows over ``run_time`` seconds from then, whatever plays
meanwhile."""

import difflib
from typing import Any

from vidgen.api import *


@action("light")
class Light(Action):
    """Change a stage's light from `at` of the beat: `- light: night` (day, morning, sunset,
    night, indoor) or `tint` + `strength` for a colour of its own; it fades over `run_time`
    seconds (default 2) and lasts until another `light` action. Stage scenes only."""

    class Options(ActionOptions):
        tint: ThemeColor | None = None
        """Instead of a preset: the light's colour (a theme token or #hex), the set's colours multiplied towards it."""
        strength: float = Field(DEFAULT_STRENGTH, ge=0.0, le=1.0)
        """With tint: how strongly (0 = no change, 1 = multiplied by the tint)."""

    run_time = LIGHT_FADE_SECONDS
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False

    def setting(self) -> str | CustomLight:
        """The preset written as the action's target, or the tint as a :class:`CustomLight`."""
        if self.options.tint is not None:
            return CustomLight(tint=self.options.tint, strength=self.options.strength)
        names = self.config.targets()
        return names[0] if names else ""

    def problems(self) -> list[tuple[str, str]]:
        """One preset or a tint, not both; a known preset."""
        names = self.config.targets()
        if self.options.tint is not None:
            return [("tint", "the light is given twice: write `- light: PRESET` or `tint:`")] if names else []
        if len(names) > 1:
            return [("target", "one light per action (add a light action per change)")]
        if not names:
            return [("target", f"which light? write `- light: PRESET` ({', '.join(LIGHT_PRESETS)}) or give tint")]
        if names[0] not in LIGHT_PRESETS:
            close = difflib.get_close_matches(names[0], LIGHT_PRESETS, n=1)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            return [("target", f"unknown light '{names[0]}'{hint} (presets: {', '.join(LIGHT_PRESETS)}, or tint)")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "change_light"):
            return [("action", f"light is for stage scenes; a {scene_cls.__name__} scene has no set to light")]
        return []

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Start the fade at scene ``time``."""
        seconds = self.run_time if self.config.run_time is None else float(self.config.run_time)
        scene.change_light(self.setting(), time, seconds)
