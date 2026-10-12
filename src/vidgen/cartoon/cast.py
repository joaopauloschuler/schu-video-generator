"""The characters a video declares under ``characters:`` (DESIGN.md §69). No manim.

Looking a character up by name, the unknown-character message shared by ``vidgen validate`` and
the build, and the theme check of each character's colours.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable

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


def check_character_name(name: str) -> str:
    """``name`` when the active project declares it (or no project is active); else ``ValueError``
    with the unknown-character message. The validator of :data:`vidgen.scene.CharacterName`."""
    from vidgen import runtime

    if runtime.has_context():
        known = character_names(runtime.current_project().config)
        if name not in known:
            raise ValueError(unknown_character_message(name, known))
    return name
