"""Story actions of a ``stage`` (DESIGN.md §100.7, §100.9, §100.10): ``alarm`` and ``shutters`` on
the set, ``materialise`` / ``dematerialise`` and ``hold_hands`` / ``let_go_hands`` on characters.
Written against ``vidgen.api`` only, like project actions; the stage does the work
(:class:`~vidgen.scenes.stage_story.StoryStaging`)."""

from typing import Any, ClassVar

from vidgen.api import *

from .acting import _Acting, _characters, _declared


@action("alarm")
class Alarm(Action):
    """An alarm goes off on a stage (`- alarm: start`) or stops (`- alarm: stop`) at `at` of the
    beat: the set darkens and a red light pulses over it (rises and falls every `period`
    seconds, like a beacon sweeping by; `color` for another), and a siren sounds while it runs
    (foley). What the light never darkens (a portal, a hologram, a screen) keeps shining. Stage
    scenes only."""

    class Options(ActionOptions):
        color: ThemeColor = ALARM_COLOR
        """The alarm light's colour (a theme token or #hex)."""
        period: float = Field(ALARM_PERIOD, ge=0.4, le=6.0)
        """Seconds of one pulse of the light (dark, bright, dark)."""

    run_time = 0.1
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False

    def problems(self) -> list[tuple[str, str]]:
        names = self.config.targets()
        if len(names) != 1 or names[0] not in ("start", "stop"):
            return [("target", "write `- alarm: start` or `- alarm: stop`")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "alarm"):
            return [("action", f"alarm is for stage scenes; a {scene_cls.__name__} scene has no set to light")]
        return []

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Start or stop the alarm at scene ``time``."""
        scene.alarm(self.config.targets()[0] == "start", time, resolve_color(self.options.color, scene.theme), self.options.period)


@action("shutters")
class Shutters(Action):
    """Steel shutters slam down over the windows of an indoor iso place (`- shutters: close`,
    with a slam) or roll up again (`- shutters: open`) at `at` of the beat. `iso: {shutters:
    true}` starts with them down. Stage scenes on an indoor iso place with windows only."""

    run_time = SHUTTER_CLOSE_SECONDS
    needs_target = False
    needs_visible = False
    scene_targets = False
    animates = False

    def problems(self) -> list[tuple[str, str]]:
        names = self.config.targets()
        if len(names) != 1 or names[0] not in ("close", "open"):
            return [("target", "write `- shutters: close` or `- shutters: open`")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        iso = getattr(params, "iso", None)
        if iso is None or iso.place != "indoor":
            return [("action", "shutters close over the windows of an indoor iso place (a stage with iso: {place: indoor})")]
        if not window_faces(iso.parsed()):
            return [("action", "this room has no window that shows into it: put a % in a back wall of the map")]
        return []

    def cue(self, scene: NarratedScene, time: float) -> None:
        """Close or open the shutters from scene ``time``."""
        scene.move_shutters(self.config.targets()[0] == "close", time)


class _Appear(_Acting):
    """``materialise`` / ``dematerialise``: the target characters appear or vanish as a
    hologram does (a flickering wireframe, then solid; or the other way)."""

    #: Whether it vanishes.
    out: ClassVar[bool] = False
    run_time = MATERIALISE_SECONDS

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "materialise"):
            return [("action", f"{self.config.action} is for the characters of a stage")]
        return self._target_characters(scene_cls, params)[1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        seconds = float(self.config.run_time or self.run_time)
        return [scene.materialise(c, out=self.out, run_time=seconds) for c in _characters(scene, targets, self.config.action)]


@action("materialise")
class MaterialiseAction(_Appear):
    """The target character appears as a hologram does (`- materialise: guide`): its outlines
    first, a flickering wireframe, then it fills in and stands solid (over `run_time`, default
    2.2 s; a rising shimmer and a chime, foley). A character whose first such action is this one
    waits unseen at its spot until then. Best on a `hologram: true` character. Stage scenes only."""

    out = False


@action("dematerialise")
class DematerialiseAction(_Appear):
    """The target character vanishes as a hologram does (`- dematerialise: guide`): its fills
    fade, a flickering wireframe is left, then nothing (a falling swoosh, foley); `materialise`
    brings it back. Stage scenes only."""

    out = True


@action("hold_hands")
class HoldHands(_Acting):
    """The target character takes `with`'s hand (`- {hold_hands: ana, with: ben}`): each one's
    hand nearer the other reaches for the other's, and they stay holding hands wherever they
    stand or walk (walk both in the same beat, to spots side by side) until `let_go_hands`. Their
    holding arms take no other action meanwhile. Stage scenes only."""

    class Options(ActionOptions):
        with_: str = Field(alias="with", pattern=r"^[A-Za-z0-9_]+$")
        """The other character."""

    run_time = 0.4
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "hold_hands"):
            return [("action", "hold_hands is for the characters of a stage")]
        names, problems = self._target_characters(scene_cls, params)
        other = self.options.with_
        on_stage = [c.name for c in params.characters]
        if other not in on_stage:
            problems.append(("with", f"'{other}' is not a character of this scene ({', '.join(on_stage)})"))
        if other in names:
            problems.append(("with", f"'{other}' cannot hold its own hand; target the other character"))
        if len(names) > 1:
            problems.append(("target", "one character takes the other's hand: target one (- {hold_hands: ana, with: ben})"))
        declared = _declared()
        for name in [*names, other]:
            entry = declared.get(name)
            if entry is not None and entry.look.svg is not None:
                problems.append(("target", f"'{name}' is drawn from an SVG; holding hands needs a generated character's arms"))
        return problems

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        for character in _characters(scene, targets, "hold_hands"):
            scene.hold_hands(character.name, self.options.with_)
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return 0.0


@action("let_go_hands")
class LetGoHands(_Acting):
    """The target character lets go of the hand it holds (`- let_go_hands: ana`; the other one
    lets go too): their arms come back to their sides."""

    run_time = 0.4
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        if not hasattr(scene_cls, "let_go_hands"):
            return [("action", "let_go_hands is for the characters of a stage")]
        return self._target_characters(scene_cls, params)[1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        names = [c.name for c in _characters(scene, targets, "let_go_hands")]
        anims: list[Animation] = []
        for character, hand in scene.let_go_hands(names):
            rest = {part: PartPose() for part in character.reached_parts(hand, character.hand_point(hand))}
            state = character.state()
            anims.append(self._change(character, CharacterState(state.facing, {**state.parts, **rest})))
        return anims
