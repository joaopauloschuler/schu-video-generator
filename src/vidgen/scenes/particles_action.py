"""The ``particles`` beat action (DESIGN.md §69.9): rain, snow, sparkles, dust, confetti, smoke,
bubbles, leaves or wind streaks over any scene type from ``at`` of a beat, written against ``vidgen.api`` only, like
project actions. The ``stage`` scene's ``particles`` param shows the same fields for the whole
scene."""

import difflib
from typing import Any

from vidgen.api import *


@action("particles")
class Particles(Action):
    """Rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks (wind lines, seen
    only while a stage's wind blows) over the scene from `at` of the beat: `- particles: snow`. They fade out when the next beat starts (`until: <beat>`: when
    that beat starts; `keep: true`: at the end of the scene); `run_time` is the fade out. Works
    on every scene type; seeded, so every render is the same. Options: density, area [x, y, w,
    h] of the visible frame from its top-left corner, color (one or a list), seed, puddles (rain
    on a stage: it ends on the ground with splashes, stops on open umbrellas and trees, plays a
    rain sound with foley), settle and settled (snow on a stage: it lands on the ground and the
    props and a white layer grows there)."""

    class Options(ParticleSettings, ActionOptions):
        kind: ParticleKindName | None = None
        """The particles, when not written as `- particles: KIND`: rain, snow, sparkles, dust, confetti, smoke, bubbles, leaves or streaks."""
        keep: bool = False
        """true: they stay to the end of the scene."""

    run_time = 0.6
    reversible = True
    until_next_beat = True
    needs_target = False
    needs_visible = False
    scene_targets = False

    def kind(self) -> str:
        """The kind: ``kind``, else the action's single target."""
        names = self.config.targets()
        return self.options.kind or (names[0] if len(names) == 1 else "")

    def problems(self) -> list[tuple[str, str]]:
        """One kind, given once and known; ``keep`` and ``until`` not both."""
        names = self.config.targets()
        o = self.options
        if o.kind is not None and names:
            return [("kind", "the kind is given twice: write `- particles: KIND` or `kind: KIND`")]
        if len(names) > 1:
            return [("target", "one kind per particles action (add an action per kind)")]
        if o.kind is None and not names:
            return [("target", f"which particles? write `- particles: KIND` ({', '.join(PARTICLE_KINDS)})")]
        found: list[tuple[str, str]] = []
        if o.kind is None and names[0] not in PARTICLE_KINDS:
            close = difflib.get_close_matches(names[0], PARTICLE_KINDS, n=1)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            found.append(("target", f"unknown particles '{names[0]}'{hint} (kinds: {', '.join(PARTICLE_KINDS)})"))
        if o.puddles and self.kind() != "rain":
            found.append(("puddles", "puddles grow under rain only (- particles: rain, on a stage)"))
        settle = settle_problem(self.kind(), o)
        if settle is not None:
            found.append(settle)
        if o.keep and self.config.until is not None:
            found.append(("keep", "keep: stays to the scene's end, until: goes at a beat; give one of them"))
        return found

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        """Rain, snow, leaves and streaks stay out of a stage's room (DESIGN.md §69.42)."""
        if getattr(params, "room", None) is not None and self.kind() in OUTDOOR_PARTICLES:
            return [("target", f"{self.kind()} stays outdoors; a room has none inside (sparkles, dust, confetti, smoke and bubbles work)")]
        return []

    def default_until(self, later: Any) -> str | None:
        """The next beat, unless ``keep``."""
        return None if self.options.keep else super().default_until(later)

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Start the field (it fades itself in, so there is nothing to play)."""
        self.field = particle_field(scene, self.kind(), self.options)
        scene.add(self.field)
        return []

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Fade the field out (it keeps moving meanwhile)."""
        field = getattr(self, "field", None)
        return [fade_out(field)] if field is not None and field in scene.mobjects else []
