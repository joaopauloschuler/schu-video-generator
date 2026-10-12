"""The characters a video declares under ``characters:`` (DESIGN.md §69). No manim.

Looking a character up by name, the unknown-character message shared by ``vidgen validate`` and
the build, the theme check of each character's colours, the checks of ``look: {svg: FILE}``
(§69.2: problems, and warnings naming the actions its parts do not allow) and the lines
``vidgen character`` prints.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from vidgen.config import CharacterEntry, VideoConfig
from vidgen.errors import Problem, VidgenError
from vidgen.theme import Theme


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
#: (``"arm_left"``) or part shapes (``"eyes.closed"``). Steps 70-79 implement the actions.
ACTION_NEEDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "say (lip sync)": (("mouth",),),
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


def unavailable_actions(part_shapes: Mapping[str, Sequence[str]]) -> list[tuple[str, str]]:
    """``(action, what it needs)`` for each :data:`ACTION_NEEDS` action a character with these
    parts (part -> shape names) cannot do, e.g. ``("gesture: wave", "arm_left or arm_right")``."""
    out = []
    for action, alternatives in ACTION_NEEDS.items():
        if not any(all(_has(part_shapes, need) for need in option) for option in alternatives):
            needs = " or ".join(" and ".join(n.replace(".", "_") for n in option) for option in alternatives)
            out.append((action, needs))
    return out


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


def check_character_name(name: str) -> str:
    """``name`` when the active project declares it (or no project is active); else ``ValueError``
    with the unknown-character message. The validator of :data:`vidgen.scene.CharacterName`."""
    from vidgen import runtime

    if runtime.has_context():
        known = character_names(runtime.current_project().config)
        if name not in known:
            raise ValueError(unknown_character_message(name, known))
    return name
