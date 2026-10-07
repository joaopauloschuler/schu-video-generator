"""The ``sfx`` beat action (DESIGN.md §47): a sound effect at ``at`` of the beat, written against
``vidgen.api`` only, like project actions. It draws nothing (``animates = False``): the runner
cues it when its beat starts, at the frame it is due, so the sound lands exactly there whatever
the scene animates then; the render pipeline mixes it."""

from typing import Any, Literal

from vidgen.api import *


@action("sfx")
class SoundEffect(Action):
    """Play a sound effect at `at` of the beat: `- sfx: whoosh` (a built-in sound, or the
    project's assets/sfx/<name>.wav; `vidgen list-sfx` describes them). It plays exactly then,
    whatever the scene animates; `gain` in dB, `pan`, `align: end` to end the sound there,
    `params` (duration, pitch, intensity) for a built-in sound. Mixed about 7 dB under the
    narration at gain 0; not heard with --no-audio."""

    class Options(ActionOptions):
        sound: str | None = None
        """The sound, when it is not written as `- sfx: NAME`."""
        gain: float = Field(default=0.0, ge=-60, le=12)
        """Level change in dB (0: the sound's own level, about 7 dB under narration)."""
        pan: float = Field(default=0.0, ge=-1, le=1)
        """-1 left, 0 centre, 1 right."""
        align: Literal["start", "end"] = "start"
        """start: the sound starts at `at`; end: it ends there (a riser landing on a reveal)."""
        params: SfxParams = Field(default_factory=SfxParams)
        """duration, pitch, intensity of a built-in sound (vidgen list-sfx)."""

    run_time = 0.1
    needs_target = False
    scene_targets = False
    animates = False

    def sound(self) -> str | None:
        """The sound's name: ``sound``, else the action's single target."""
        names = self.config.targets()
        return self.options.sound or (names[0] if len(names) == 1 else None)

    def problems(self) -> list[tuple[str, str]]:
        """One sound, given once; known to the project; params that fit it."""
        names = self.config.targets()
        o = self.options
        if o.sound is not None and names:
            return [("sound", "the sound is given twice: write `- sfx: NAME` or `sound: NAME`")]
        if len(names) > 1:
            return [("target", "one sound per sfx action (add an action per sound)")]
        if o.sound is None and not names:
            return [("target", "which sound? write `- sfx: NAME` (vidgen list-sfx lists them)")]
        found: list[tuple[str, str]] = []
        if self.config.run_time is not None:
            found.append(("run_time", "a sound plays for its own length; set params.duration instead"))
        key = "sound" if o.sound is not None else "target"
        for name, message in sound_library().problems(self.sound() or "", self._params()):
            found.append((key if name == "sound" else name, message))
        return found

    def _params(self) -> dict[str, Any]:
        return self.options.params.model_dump(exclude_none=True)

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Record the sound at ``time``."""
        o = self.options
        scene.sfx(self.sound() or "", time, gain=o.gain, pan=o.pan, align=o.align, **self._params())
