"""The characters a video declares under ``characters:`` (DESIGN.md §69). No manim.

Looking a character up by name, the unknown-character message shared by ``vidgen validate`` and
the build, the theme check of each character's colours, the checks of ``look: {svg: FILE}``
(§69.2: problems, and warnings naming the actions its parts do not allow), the checks of the
characters' own poses and expressions (§69.3), the lines ``vidgen character`` prints, and who
speaks a beat and what the acting actions need (§69.11).
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from vidgen.cartoon.poses import EXPRESSION_PARTS, POSE_PARTS, chosen_shape, merged_table, unknown_name_message
from vidgen.config import BeatConfig, CharacterEntry, PartPoseEntry, SceneConfig, VideoConfig
from vidgen.errors import Problem, VidgenError
from vidgen.theme import Theme
from vidgen.voices import DEFAULT_VOICE

if TYPE_CHECKING:
    from vidgen.project import Project


def character_names(config: VideoConfig) -> list[str]:
    """The names of ``characters:``, in order."""
    return [entry.name for entry in config.characters]


def unknown_character_message(name: str, known: Iterable[str]) -> str:
    """``unknown character 'anna'; did you mean 'ana'? characters: ana, ben``."""
    known = list(known)
    if not known:
        return f"unknown character '{name}': the video declares no characters (add them under characters:)"
    close = difflib.get_close_matches(name, known, n=1, cutoff=0.6)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    return f"unknown character '{name}'{hint} characters: {', '.join(known)}"


def find_character(config: VideoConfig, name: str) -> CharacterEntry:
    """The ``characters:`` entry called ``name``; raises :class:`VidgenError` when there is none."""
    for entry in config.characters:
        if entry.name == name:
            return entry
    raise VidgenError(unknown_character_message(name, character_names(config)))


def character_color_problems(config: VideoConfig, theme: Theme) -> list[Problem]:
    """``colors`` values of ``characters:`` that are not theme colours."""
    problems = []
    for k, entry in enumerate(config.characters):
        for part, color in entry.colors.model_dump().items():
            try:
                theme.color(color)
            except VidgenError as exc:
                problems.append(Problem(f"characters[{k}].colors.{part}", str(exc)))
    return problems


def character_lines(entry: CharacterEntry, theme: Theme, root: Path | None = None) -> list[str]:
    """What ``vidgen character NAME`` prints: the voice, every ``look`` value and every colour
    (a token with the colour it resolves to in ``theme``); for an ``svg`` look, the file and
    (with the project folder ``root``) its parts and shapes."""
    look = entry.look
    if look.svg is not None:
        lines = [f"character {entry.name}  (voice: {entry.voice or 'none'})", f"  look:   svg {look.svg}"]
        if root is not None:
            from vidgen.cartoon.svg_look import read_character_svg

            shapes = read_character_svg(root / look.svg, where=look.svg).part_shapes()
            described = [part if names == [names[0]] else f"{part} ({', '.join(names)})" for part, names in shapes.items()]
            lines.append(f"  parts:  {', '.join(described)}")
        return [*lines, "  colors: the SVG's own"]
    accessories = ", ".join(look.accessories) or "none"
    seed = "none" if look.seed is None else str(look.seed)
    colors = []
    for part, value in entry.colors.model_dump().items():
        resolved = theme.color(value)
        colors.append(f"{part} {value}" if resolved.lower() == value.lower() else f"{part} {value} ({resolved})")
    return [
        f"character {entry.name}  (voice: {entry.voice or 'none'})",
        f"  look:   body {look.body}, head_size {look.head_size:g}, eyes {look.eyes}, nose {look.nose}, hair {look.hair}, "
        f"ears {look.ears}, accessories {accessories}, seed {seed}",
        f"  colors: {', '.join(colors)}",
    ]


#: What each acting action needs of a character: one of the alternatives, each a tuple of parts
#: (``"arm_left"``) or part shapes (``"eyes.closed"``). An action names its entry with
#: :meth:`Action.character_needs <vidgen.actions.Action.character_needs>`; ``vidgen validate``
#: warns about each use on a character without those parts (:func:`acting_warnings`).
ACTION_NEEDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "say": (("mouth",),),
    "blink": (("eyes.closed",),),
    "look_at": (("head",),),
    "emote": (("eyes",), ("brows",), ("mouth",)),
    "gesture: point": (("arm_left",), ("arm_right",)),
    "gesture: wave": (("arm_left",), ("arm_right",)),
    "gesture: shrug": (("arm_left", "arm_right"),),
    "gesture: nod": (("head",),),
    "gesture: shake_head": (("head",),),
}


def _has(part_shapes: Mapping[str, Sequence[str]], need: str) -> bool:
    part, _, shape = need.partition(".")
    return part in part_shapes and (not shape or shape in part_shapes[part])


def missing_needs(part_shapes: Mapping[str, Sequence[str]], action: str) -> str | None:
    """What a character with these parts (part -> shape names) lacks for :data:`ACTION_NEEDS`
    entry ``action`` (``"arm_left or arm_right"``), or ``None`` when it can do it."""
    alternatives = ACTION_NEEDS[action]
    if any(all(_has(part_shapes, need) for need in option) for option in alternatives):
        return None
    return " or ".join(" and ".join(n.replace(".", "_") for n in option) for option in alternatives)


def unavailable_actions(part_shapes: Mapping[str, Sequence[str]]) -> list[tuple[str, str]]:
    """``(action, what it needs)`` for each :data:`ACTION_NEEDS` action a character with these
    parts (part -> shape names) cannot do, e.g. ``("gesture: wave", "arm_left or arm_right")``."""
    return [(action, needs) for action in ACTION_NEEDS if (needs := missing_needs(part_shapes, action)) is not None]


def _svg_looks(config: VideoConfig) -> Iterable[tuple[int, CharacterEntry, str]]:
    for k, entry in enumerate(config.characters):
        if entry.look.svg is not None:
            yield k, entry, entry.look.svg


def character_look_problems(config: VideoConfig, root: Path) -> list[Problem]:
    """``look.svg`` files (relative to ``root``) that are missing or cannot be split into parts."""
    from vidgen.cartoon.svg_look import read_character_svg

    problems = []
    for k, _, svg in _svg_looks(config):
        try:
            read_character_svg(root / svg, where=svg)
        except VidgenError as exc:
            problems.append(Problem(f"characters[{k}].look.svg", str(exc)))
    return problems


def character_look_warnings(config: VideoConfig, root: Path) -> list[str]:
    """Warnings about ``look.svg`` characters: what the sanitiser removed, ids that look like
    misspelt part names, guessed pivots, ``colors`` (not used), a mouth with one shape and the
    actions the parts do not allow. Files with problems (:func:`character_look_problems`) are skipped."""
    from vidgen.cartoon.svg_look import pivot_warnings, read_character_svg

    warnings: list[str] = []
    for _, entry, svg in _svg_looks(config):
        where = f"character '{entry.name}' ({svg})"
        try:
            split = read_character_svg(root / svg, where=where)
        except VidgenError:
            continue
        warnings.extend((*split.report.warnings, *split.warnings, *pivot_warnings(split, where)))
        if entry.colors.model_fields_set:
            warnings.append(f"{where}: colors are not used by an svg look (the SVG's own colours are drawn)")
        shapes = split.part_shapes()
        if len(shapes.get("mouth", ())) == 1:
            warnings.append(f"{where}: the mouth has one shape, so it will not move while the character speaks (add mouth_A, mouth_E, mouth_O, ...)")
        missing = unavailable_actions(shapes)
        if missing:
            listed = "; ".join(f"{action} (needs {needs})" for action, needs in missing)
            warnings.append(f"{where}: actions unavailable: {listed}")
    return warnings


#: Shape names of a generated character's parts (``cartoon/generator.py``); the first is the rest shape.
GENERATED_SHAPES: dict[str, list[str]] = {
    "body": ["default"], "legs": ["default"], "arm_left": ["default"], "arm_right": ["default"], "head": ["default"],
    "eyes": ["open", "closed"], "brows": ["default", "angry", "sad"], "mouth": ["smile", "open", "A", "E", "O", "U", "M", "F", "L", "W"],
}


def character_part_shapes(entry: CharacterEntry, root: Path) -> dict[str, list[str]]:
    """Part name -> shape names of ``entry`` without drawing it (an svg look is read from
    ``root``; raises :class:`VidgenError` when the file cannot be split)."""
    if entry.look.svg is not None:
        from vidgen.cartoon.svg_look import read_character_svg

        return read_character_svg(root / entry.look.svg, where=entry.look.svg).part_shapes()
    shapes = {part: list(names) for part, names in GENERATED_SHAPES.items()}
    if {"glasses", "hat"} & set(entry.look.accessories):
        shapes["accessory"] = ["default"]
    return shapes


def _own_pose_parts(config: VideoConfig, root: Path) -> Iterable[tuple[str, str, CharacterEntry, str, PartPoseEntry, dict[str, list[str]]]]:
    """(location, kind, entry, part, setting, the character's part shapes) of every part of the
    characters' own poses and expressions; characters whose svg cannot be read are skipped."""
    for k, entry in enumerate(config.characters):
        if not entry.poses and not entry.expressions:
            continue
        try:
            shapes = character_part_shapes(entry, root)
        except VidgenError:
            continue
        for kind, table in (("pose", entry.poses), ("expression", entry.expressions)):
            for name, parts in table.items():
                for part, setting in parts.items():
                    yield f"characters[{k}].{kind}s.{name}.{part}", kind, entry, part, setting, shapes


def character_pose_problems(config: VideoConfig, root: Path) -> list[Problem]:
    """Shapes of the characters' own poses and expressions that the character does not have
    (none of a list of choices)."""
    problems = []
    for where, _, entry, part, setting, shapes in _own_pose_parts(config, root):
        choices = setting.shape_choices()
        if part in shapes and choices and chosen_shape(setting, shapes[part]) is None:
            problems.append(Problem(
                f"{where}.shape",
                f"character '{entry.name}': part '{part}' has no shape {' or '.join(map(repr, choices))} (shapes: {', '.join(shapes[part])})",
            ))
    return problems


def character_pose_warnings(config: VideoConfig, root: Path) -> list[str]:
    """Parts named by the characters' own poses and expressions that the character does not have
    (those settings do nothing)."""
    return [
        f"{where}: character '{entry.name}' has no {part}; this setting does nothing"
        for where, _, entry, part, _, shapes in _own_pose_parts(config, root)
        if part not in shapes
    ]


def pose_lines(entry: CharacterEntry) -> list[str]:
    """What ``vidgen character NAME`` prints about poses: the known pose and expression names
    (the character's own marked ``*``)."""
    lines = []
    for kind, own in (("pose", entry.poses), ("expression", entry.expressions)):
        names = [f"{name}*" if name in own else name for name in merged_table(kind, own)]
        lines.append(f"  {kind}s: {', '.join(names)}")
    return lines


def pose_name_problem(config: VideoConfig, character: str, kind: str, name: str) -> str | None:
    """Why ``name`` is not a ``pose`` / ``expression`` (``kind``) that ``character`` knows (built-in
    or its own; the message lists the known names), or ``None``. Also ``None`` for a character the
    video does not declare: the :data:`~vidgen.scene.CharacterName` check reports that."""
    entry = next((e for e in config.characters if e.name == character), None)
    if entry is None:
        return None
    table = merged_table(kind, getattr(entry, f"{kind}s"))
    return None if name in table else unknown_name_message(kind, name, table, entry.name)


#: The order of a character's part targets (``kit.body`` ... ``kit.mouth``).
TARGET_PART_ORDER: tuple[str, ...] = POSE_PARTS + EXPRESSION_PARTS


def part_target_names(names: Iterable[str]) -> list[str]:
    """``<character>.<part>`` for each part of each of the active project's characters among
    ``names`` (DESIGN.md §69.14); none without an active project, nor for a character that is
    not declared or whose svg cannot be read (validate reports those)."""
    from vidgen import runtime

    if not runtime.has_context():
        return []
    project = runtime.current_project()
    entries = {entry.name: entry for entry in project.config.characters}
    out: list[str] = []
    for name in names:
        if name not in entries:
            continue
        try:
            parts = character_part_shapes(entries[name], project.root)
        except VidgenError:
            continue
        out += [f"{name}.{part}" for part in TARGET_PART_ORDER if part in parts]
    return out


def check_character_name(name: str) -> str:
    """``name`` when the active project declares it (or no project is active); else ``ValueError``
    with the unknown-character message. The validator of :data:`vidgen.scene.CharacterName`."""
    from vidgen import runtime

    if runtime.has_context():
        known = character_names(runtime.current_project().config)
        if name not in known:
            raise ValueError(unknown_character_message(name, known))
    return name


# ----- who speaks (DESIGN.md §69.11) ----------------------------------------------------------------


def beat_voice(scene: SceneConfig, beat: BeatConfig) -> str:
    """The name of the voice that says ``beat``: its ``voice``, else its scene's, else
    ``default`` (the base voice)."""
    return beat.voice or scene.voice or DEFAULT_VOICE


def speaking_characters(config: VideoConfig, voice: str, names: Iterable[str]) -> list[str]:
    """The characters among ``names`` whose ``voice`` is ``voice`` (a character without a voice
    never speaks)."""
    voices = {entry.name: entry.voice for entry in config.characters}
    return [name for name in names if voices.get(name) is not None and voices.get(name) == voice]


def say_problem(config: VideoConfig, name: str) -> str | None:
    """Why character ``name`` cannot ``say`` anything (it has no ``voice``), or ``None``; also
    ``None`` for a name the video does not declare (the target check reports that)."""
    entry = next((e for e in config.characters if e.name == name), None)
    if entry is None or entry.voice is not None:
        return None
    return f"character '{name}' has no voice, so it cannot say anything (give it voice: in characters:)"


def shared_voice_warnings(config: VideoConfig) -> list[str]:
    """Characters that share a voice: a beat in that voice moves all their mouths on a stage
    unless a ``say`` action picks who speaks."""
    owners: dict[str, list[str]] = {}
    for entry in config.characters:
        if entry.voice is not None:
            owners.setdefault(entry.voice, []).append(entry.name)
    return [
        f"characters {', '.join(repr(n) for n in names)} have the same voice '{voice}': beats in that voice move all their "
        "mouths on a stage; add a say action to such beats to pick who speaks"
        for voice, names in owners.items() if len(names) > 1
    ]


def acting_warnings(project: Project) -> list[str]:
    """Each beat action that acts on a character lacking the parts it needs
    (:meth:`Action.character_needs <vidgen.actions.Action.character_needs>`, :data:`ACTION_NEEDS`):
    for that character the action does nothing (or less). Actions with problems are skipped
    (``vidgen validate`` reports those)."""
    from fnmatch import fnmatchcase

    from vidgen import extensions, registry

    config = project.config
    if not config.characters:
        return []
    warnings: list[str] = []
    shapes: dict[str, dict[str, list[str]] | None] = {}

    def parts_of(entry: CharacterEntry) -> dict[str, list[str]] | None:
        if entry.name not in shapes:
            try:
                shapes[entry.name] = character_part_shapes(entry, project.root)
            except VidgenError:
                shapes[entry.name] = None
        return shapes[entry.name]

    try:
        with extensions.project_session(project):
            known = registry.action_names()
            for i, scene in enumerate(config.scenes):
                for j, beat in enumerate(scene.beats):
                    for k, act in enumerate(beat.actions):
                        act = act.resolved(known)
                        kind = registry.find_action(act.action)
                        if kind is None:
                            continue
                        try:
                            options = kind.cls.Options.model_validate(act.options)
                        except ValueError:
                            continue
                        need = kind.cls(options, act).character_needs()
                        if need is None:
                            continue
                        for entry in config.characters:
                            if not any(fnmatchcase(entry.name, pattern) for pattern in act.targets()):
                                continue
                            parts = parts_of(entry)
                            missing = None if parts is None else missing_needs(parts, need)
                            if missing is not None:
                                warnings.append(
                                    f"scenes[{i}].beats[{j}].actions[{k}]: character '{entry.name}' cannot {need} (needs {missing}); "
                                    "the action does nothing for it"
                                )
    except VidgenError:
        return warnings
    return warnings
