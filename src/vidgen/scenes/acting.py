"""Acting beat actions (DESIGN.md §69.11): ``say``, ``look_at``, ``turn``, ``emote``, ``pose`` and
``react`` on the characters of a scene (a ``stage``'s, or any scene's targets that are
:class:`Character` s); the moving ones are in ``moving.py`` (§69.12). Written against
``vidgen.api`` only, like project actions.

Each changes a character's state with :class:`PoseChange` (``say``: starts lip sync, and draws
an optional speech bubble with the callout helpers). A part the character lacks is skipped
(``vidgen validate`` warns, :meth:`Action.character_needs`).
"""

import logging
from dataclasses import replace
from fnmatch import fnmatchcase
from typing import Annotated, Any, ClassVar, Literal

import numpy as np

from vidgen.api import *

from .callout_action import label_avoid, label_bounds, view_region

log = logging.getLogger("vidgen.actions")

#: Distances (units) tried between a speech bubble and the speaker's head, shortest first.
BUBBLE_GAPS = (0.25, 0.45, 0.8)
#: Outline width of a speech bubble (Manim stroke width).
BUBBLE_STROKE = 3.0
#: Half the width of a bubble's tail where it meets the bubble (units).
TAIL_HALF_WIDTH = 0.14
#: Longest tail (units); it reaches at most this share of the way to the head.
TAIL_LENGTH = 0.4
TAIL_REACH = 0.6


def _declared() -> dict[str, Any]:
    """The active project's characters by name (empty without an active project)."""
    try:
        return {entry.name: entry for entry in current_project().config.characters}
    except VidgenError:
        return {}


def is_part_target(name: str) -> bool:
    """Whether a target name names a character's part (``kit.arm_left``, DESIGN.md §69.14)."""
    return "." in name


#: The parts sitting, leaning and crouching set (the arms and the head keep their poses; §69.28).
POSTURE_PARTS: tuple[str, ...] = ("body", "legs", "leg_left", "leg_left_lower", "leg_right", "leg_right_lower")


def posture_parts(state: CharacterState) -> dict[str, PartPose]:
    """The body's and legs' poses of ``state`` (:data:`POSTURE_PARTS` it has)."""
    return {part: state.parts[part] for part in POSTURE_PARTS if part in state.parts}


def is_posed(character: Character) -> bool:
    """Whether ``character`` sits, leans (DESIGN.md §69.28) or rides a vehicle (§69.52): it keeps
    its facing, body and legs then (a look turns only its head, a pose moves only its arms and
    head)."""
    return character.sitting_on is not None or character.leaning_on is not None or character.riding is not None


def _kept_posture(character: Character, state: CharacterState) -> CharacterState:
    """``state`` with ``character``'s facing, body and legs as they are now when it sits or leans."""
    if not is_posed(character):
        return state
    now = character.state()
    return CharacterState(now.facing, {**state.parts, **posture_parts(now)})


def _characters(scene: NarratedScene, targets: list[Target], name: str) -> list[Character]:
    """The targets that are characters (others are logged and skipped; parts, which a pattern
    such as ``*`` also selects, silently)."""
    others = [t.name for t in targets if not isinstance(t.mobject, Character) and not is_part_target(t.name)]
    if others:
        log.warning("scene '%s': %s acts on characters; %s is not one, skipped", scene.spec.id, name, ", ".join(others))
    return [t.mobject for t in targets if isinstance(t.mobject, Character)]


class _Acting(Action):
    """An action on characters: its targets must be characters of the scene. Changes it makes
    with :meth:`_change` are undone part by part with :meth:`_undo`."""

    #: The :data:`ACTION_NEEDS` entry it needs of each character (``None``: nothing).
    needs: ClassVar[str | None] = None

    def __init__(self, options: ActionOptions, config: Any) -> None:
        super().__init__(options, config)
        #: (character, part -> pose before, facing before or ``None``) per change, for :meth:`_undo`
        self.saved: list[tuple[Character, dict[str, PartPose], str | None]] = []

    def character_needs(self) -> str | None:
        return self.needs

    def _target_characters(self, scene_cls: type[NarratedScene], params: Any) -> tuple[list[str], list[tuple[str, str]]]:
        """The declared characters the targets name in a scene of ``scene_cls`` with ``params``,
        and a problem for each target name that is something else (a prop, or a part named
        on its own: ``kit.arm_left``; a pattern such as ``*`` skips the parts)."""
        declared = _declared()
        names = scene_cls.target_names(params)
        found: list[str] = []
        problems: list[tuple[str, str]] = []
        for pattern in self.config.targets():
            if is_part_target(pattern) and pattern in names:
                problems.append(("target", f"'{pattern}' is a character's part; {self.config.action} acts on whole characters"))
            for name in [n for n in names if fnmatchcase(n, pattern) and not is_part_target(n)]:
                if name in declared:
                    found.append(name)
                elif declared:
                    problems.append(("target", f"'{name}' is not a character; {self.config.action} acts on characters"))
        return list(dict.fromkeys(found)), problems

    def _named_problems(self, scene_cls: type[NarratedScene], params: Any, kind: str, name: str | None, key: str) -> list[tuple[str, str]]:
        """Problems of a pose / expression ``name`` (option ``key``) for every target character."""
        names, problems = self._target_characters(scene_cls, params)
        if name is not None:
            config = current_project().config
            for character in names:
                problem = pose_name_problem(config, character, kind, name)
                if problem is not None:
                    problems.append((key, problem))
        return problems

    def _change(self, character: Character, state: CharacterState) -> Animation:
        """A :class:`PoseChange` to ``state``, remembering what it changes for :meth:`_undo`."""
        before = character.state()
        parts = {p: before.parts[p] for p, pose in state.parts.items() if before.parts.get(p) != pose}
        facing = before.facing if state.facing != before.facing else None
        self.saved.append((character, parts, facing))
        return PoseChange(character, state=state)

    def _undo(self) -> list[Animation]:
        """Put back what :meth:`_change` changed (other parts keep what happened since)."""
        anims: list[Animation] = []
        saved, self.saved = self.saved, []
        for character, parts, facing in saved:
            now = character.state()
            anims.append(PoseChange(character, state=CharacterState(facing or now.facing, {**now.parts, **parts})))
        return anims


# ----- say -----------------------------------------------------------------------------------------


@action("say")
class Say(_Acting):
    """The target character says this beat: its mouth follows the beat's viseme track (lip sync,
    in step with the audio from the beat's start) until the next beat starts (``until: <beat>``:
    until that beat starts). ``bubble: true`` shows the beat's text in a speech bubble above
    its head, ``bubble: "Hi!"`` a short version. A beat with a say action is spoken by the
    characters it names; without one, a stage's characters whose voice says the beat speak."""

    class Options(ActionOptions):
        bubble: bool | TranslatableStr = False
        """true: a speech bubble with the beat's text; a text: a bubble with that (shorter) text; false: none."""
        color: ThemeColor = "#FFFFFF"
        """Fill of the bubble (theme token or hex); its text and outline take the colour that reads on it."""
        size: ThemeSize = "caption"
        """Size of the bubble's text (never below the readable size)."""

    run_time = 0.4
    reversible = True
    until_next_beat = True
    needs = "say"

    def problems(self) -> list[tuple[str, str]]:
        if isinstance(self.options.bubble, str) and not self.options.bubble.strip():
            return [("bubble", "the bubble's text is empty (use bubble: true for the beat's text, or false)")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        names, problems = self._target_characters(scene_cls, params)
        config = current_project().config if names else None
        return problems + [("target", p) for name in names if (p := say_problem(config, name)) is not None]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Start lip sync on each character; draw the bubbles."""
        self.speakers: list[tuple[Character, Any]] = []
        self.bubbles: list[Callout] = []
        for character in _characters(scene, targets, "say"):
            scene.speak(character)
            self.speakers.append((character, character.lip_sync_track))
        text = self.options.bubble
        if text is True:
            beat = scene.current_beat
            text = beat.text if beat is not None else ""
        if not text:
            return []
        anims: list[Animation] = []
        for character, _ in self.speakers:
            bubble = self._bubble(scene, character, str(text), targets)
            self.bubbles.append(bubble)
            anims += bubble.draw()
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Stop the lip sync it started (not a later one; once its line ends when the next
        beat overlaps it) and fade the bubbles out."""
        for character, track in getattr(self, "speakers", []):
            scene.end_lip_sync(character, track)
        return [fade_out(part) for bubble in getattr(self, "bubbles", []) for part in scene.on_screen_parts(bubble)]

    def _bubble(self, scene: NarratedScene, speaker: Character, text: str, targets: list[Target]) -> Callout:
        view, scale = view_region(scene)
        head = speaker.parts["head"] if speaker.has_part("head") else speaker
        anchor = callout_area(head)
        avoid = label_avoid(scene, view, scale, targets, anchor)
        avoid += [b.extent() for b in self.bubbles]
        avoid += [callout_area(m) for m in scene.mobjects if isinstance(m, EffectSymbol) and m.family_members_with_points()]   # §69.40
        made = speech_bubble(
            text, anchor, color=self.options.color, size=self.options.size, bounds=label_bounds(scene, view, scale),
            avoid=avoid, scale=scale, theme=scene.theme,
        )
        top = max((m.z_index for m in scene.get_mobject_family_members()), default=0)
        made.set_z_index(top + 2)
        follow_speaker(made.mark, speaker)
        made.mark.speech_bubble_of = speaker.name  # the layout dump's ``bubble`` (lint bubble_overlap)
        return made


def follow_speaker(bubble: Mobject, speaker: Character) -> None:
    """Keep ``bubble`` where it is relative to ``speaker``'s feet, on every frame, so it moves
    with a character that walks or jumps (an updater on the bubble)."""
    offset = bubble.get_center() - speaker.feet()
    bubble.add_updater(lambda m: m.move_to(speaker.feet() + offset))


def speech_bubble(
    text: str, anchor: Region, *, color: Any, size: Any, bounds: Region, avoid: list[Region], scale: float, theme: Any,
) -> Callout:
    """A speech bubble: ``text`` on a rounded plate (:func:`callout_label`) above ``anchor`` (a
    speaker's head) where there is room (inside ``bounds``, clear of ``avoid``), with a tail
    towards it; plate and tail are one outlined shape in the text's colour."""
    label = callout_label(text, color=color, size=size, scale=scale, theme=theme)
    spot = label_spot(
        (label.width, label.height), anchor, bounds=bounds, avoid=avoid, gaps=[g * scale for g in BUBBLE_GAPS], side="top", straight=True,
    )
    label.move_to(spot.center)
    plate = label.plate
    ink = label.text.family_members_with_points()[0].get_fill_color()
    tip = np.array([anchor.center[0], anchor.y1 if spot.y0 >= anchor.y1 - 1e-6 else anchor.center[1], 0.0])
    tail = Polygon(*bubble_tail(np.array(spot.center), (spot.width, spot.height), tip, scale))
    shape = Union(plate, tail)
    shape.set_fill(plate.get_fill_color(), opacity=1).set_stroke(ink, width=BUBBLE_STROKE * scale)
    bubble = VGroup(shape, label.text)
    bubble.callout_fade = True
    return Callout("label", anchor, bubble)


def bubble_tail(center: np.ndarray, size: tuple[float, float], tip: np.ndarray, scale: float = 1.0) -> list[np.ndarray]:
    """The three corners of a bubble's tail: a base on the edge of the plate (``center``,
    ``size`` = width, height) facing ``tip`` (just inside the plate, so the two join), and a
    point towards ``tip``, at most :data:`TAIL_LENGTH` long and :data:`TAIL_REACH` of the way."""
    w, h = size
    direction = tip - center
    direction[2] = 0.0
    length = float(np.linalg.norm(direction))
    u = direction / length if length > 1e-9 else np.array([0.0, -1.0, 0.0])
    tx = (w / 2) / abs(u[0]) if abs(u[0]) > 1e-9 else np.inf
    ty = (h / 2) / abs(u[1]) if abs(u[1]) > 1e-9 else np.inf
    edge = center + u * min(tx, ty)
    normal = np.array([-u[1], u[0], 0.0])
    half = min(TAIL_HALF_WIDTH * scale, 0.3 * min(w, h))
    inside = edge - u * 0.6 * half
    reach = min(TAIL_LENGTH * scale, TAIL_REACH * max(float(np.linalg.norm(tip - edge)), 0.0))
    # counterclockwise, like the plate: Union joins two paths only when they turn the same way
    return [inside + normal * half, inside - normal * half, edge + u * max(reach, half)]


# ----- looking and turning ---------------------------------------------------------------------------


def _head_point(mob: Mobject) -> np.ndarray:
    """Where a character looks from / is looked at: the middle of its head (else of its box)."""
    if isinstance(mob, Character) and mob.has_part("head"):
        return np.array(mob.parts["head"].get_center())
    return np.array(mob.get_center())


@action("look_at")
class LookAt(_Acting):
    """The target character looks at ``to``: another character or a prop (by its name), a mark of
    the stage or an x from 0 (left) to 1 (right), or ``camera`` (the viewer). It turns that way
    (not while it sits or leans) and tilts its head up or down towards it; ``camera`` turns the
    eyes to the viewer. It stays so (``until: <beat>`` turns it back)."""

    class Options(ActionOptions):
        to: str | Annotated[float, Field(ge=0.0, le=1.0)]
        """What it looks at: a character or prop of the scene, a mark (left, centre, right, ... or the stage's own), an x from 0 (left edge) to 1 (right edge) of the stage, or camera."""

    run_time = 0.5
    reversible = True
    needs = "look_at"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        _, problems = self._target_characters(scene_cls, params)
        to = self.options.to
        if to == "camera" or (isinstance(to, str) and to in scene_cls.target_names(params)):
            return problems
        try:
            scene_cls.camera_place(params, to)
        except ValueError as exc:
            return problems + [("to", f"not a character or prop of the scene, nor camera; {exc}")]
        return problems

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Turn each character towards ``to`` and tilt its head."""
        anims = []
        #: (character, what it looked at before) per character, for :meth:`revert`
        self.looked_before: list[tuple[Character, str | None]] = []
        for character in _characters(scene, targets, "look_at"):
            look = self._look(scene, character)
            if look is not None:
                anims.append(self._change(character, looked_state(character, look)))
                self.looked_before.append((character, character.looked_at))
                character.looked_at = self.options.to if isinstance(self.options.to, str) else None
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to where it looked before."""
        for character, before in getattr(self, "looked_before", []):
            character.looked_at = before
        return self._undo()

    def _look(self, scene: NarratedScene, character: Character) -> LookPose | None:
        to = self.options.to
        if to == "camera":
            return camera_look(character.facing)
        start = _head_point(character)
        found = scene.find_targets(to) if isinstance(to, str) else []
        if found:
            if found[0].mobject is character:
                return None
            point = _head_point(found[0].mobject)
        else:
            left, right = scene.camera_bounds()[:2]
            point = np.array([left + scene.camera_place(scene.params, to) * (right - left), start[1], 0.0])
        dx = float(point[0] - start[0])
        if is_posed(character):   # it sits or leans: it does not turn round, only tilts its head
            dx = abs(dx) if character.facing == "right" else -abs(dx)
        return look_pose(dx, float(point[1] - start[1]), character.facing)


def looked_state(character: Character, look: LookPose) -> CharacterState:
    """``character``'s state now with ``look`` applied: its facing, its head's angle, its eyes'
    shift (parts it lacks are skipped)."""
    parts = dict(character.state().parts)
    if character.has_part("head"):
        parts["head"] = replace(parts["head"], angle=look.head_angle)
    if character.has_part("eyes"):
        parts["eyes"] = replace(parts["eyes"], shift=look.eyes_shift)
    return CharacterState(look.facing, parts)


@action("turn")
class Turn(_Acting):
    """The target character turns round (``to: left`` / ``right``: faces that way; ``front``:
    faces the viewer, its front view with the head straight and the eyes ahead, narrowing as it
    turns and swapping its shapes half-way; an
    SVG character has no front view and keeps its side). It stays so (``until: <beat>`` turns it
    back)."""

    class Options(ActionOptions):
        to: Literal["left", "right", "front"] | None = None
        """left, right or front (towards the viewer); default: the other way (from the front: the side it faced before)."""

    run_time = 0.4
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._target_characters(scene_cls, params)[1]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Mirror each character that does not face ``to`` yet, or turn it between its side and
        its front (halfway through)."""
        anims = []
        for character in _characters(scene, targets, "turn"):
            facing = self.options.to or (character.side_facing if character.facing == "front" else "left" if character.facing == "right" else "right")
            if facing == "front" and not character.has_front_view:
                continue   # an SVG character keeps its side (vidgen validate warns)
            if facing == "front" and facing != character.facing:   # a look's head angle would tilt it sideways
                anims.append(self._change(character, looked_state(character, camera_look("front"))))
            elif facing != character.facing:
                state = character.state()
                anims.append(self._change(character, CharacterState(facing, dict(state.parts))))
        return anims

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Face the way it did before."""
        return self._undo()


# ----- expressions and poses -------------------------------------------------------------------------


@action("emote")
class Emote(_Acting):
    """The target character changes its expression to ``to`` (neutral, happy, sad, angry,
    surprised, worried, thinking, laughing, blushing, tongue_out, crying, dizzy, frightened, or its
    own); eyes, brows and mouth move one after another. It
    keeps it (``until: <beat>``: back to the expression before)."""

    class Options(ActionOptions):
        to: str = Field(pattern=r"^[A-Za-z0-9_]+$")
        """The expression: neutral, happy, sad, angry, surprised, worried, thinking, laughing, blushing, tongue_out, crying, dizzy, frightened, or the character's own."""

    run_time = 0.5
    reversible = True
    needs = "emote"

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._named_problems(scene_cls, params, "expression", self.options.to, "to")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`PoseChange` to the expression on each character."""
        return [self._change(c, c.posed_state(expression=self.options.to)) for c in _characters(scene, targets, "emote")]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the expression before."""
        return self._undo()


@action("pose")
class PoseAction(_Acting):
    """The target character takes pose ``to`` (stand, pointing, waving, thinking, shrug,
    arms_crossed, sitting, or its own); body, legs, arms and head move one after another (only
    arms and head while it sits or leans). It keeps it (``until: <beat>``: back to the pose
    before)."""

    class Options(ActionOptions):
        to: str = Field(pattern=r"^[A-Za-z0-9_]+$")
        """The pose: stand, pointing, waving, thinking, shrug, arms_crossed, sitting, or the character's own."""

    run_time = 0.8
    reversible = True

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return self._named_problems(scene_cls, params, "pose", self.options.to, "to")

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`PoseChange` to the pose on each character."""
        return [self._change(c, _kept_posture(c, c.posed_state(pose=self.options.to))) for c in _characters(scene, targets, "pose")]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the pose before."""
        return self._undo()


@action("react")
class React(_Acting):
    """The target character reacts while another one speaks: an ``expression`` and / or a
    ``pose`` for this beat, undone when the next beat starts (``until: <beat>``: when that beat
    starts)."""

    class Options(ActionOptions):
        expression: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]+$")
        """An expression: neutral, happy, sad, angry, surprised, worried, thinking, laughing, blushing, tongue_out, crying, dizzy, frightened, or the character's own."""
        pose: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]+$")
        """A pose: stand, pointing, waving, thinking, shrug, arms_crossed, sitting, or the character's own."""

    run_time = 0.6
    reversible = True
    until_next_beat = True

    def character_needs(self) -> str | None:
        return "emote" if self.options.expression is not None else None

    def problems(self) -> list[tuple[str, str]]:
        if self.options.expression is None and self.options.pose is None:
            return [("expression", "react needs an expression or a pose (or both)")]
        return []

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = self._named_problems(scene_cls, params, "expression", self.options.expression, "expression")
        return problems + [p for p in self._named_problems(scene_cls, params, "pose", self.options.pose, "pose") if p[0] == "pose"]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """A :class:`PoseChange` to the expression and pose on each character."""
        o = self.options
        return [self._change(c, _kept_posture(c, c.posed_state(pose=o.pose, expression=o.expression))) for c in _characters(scene, targets, "react")]

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Back to the expression and pose before."""
        return self._undo()
