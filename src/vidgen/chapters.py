"""The video's chapters as the config marks them (DESIGN.md §42).

A chapter starts at a ``chapter`` scene (its ``title`` and ``number`` params) or at any scene
with a ``chapter:`` field (a title, or ``{title, number}``); on a ``chapter`` scene the field
renames the chapter in lists and indicators. This module reads the config only; where chapters
start and end in the video comes from the planned timeline (``vidgen.videoplan.VideoPlan.chapters``,
public as ``vidgen.api.video_chapters``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.config import ChapterConfig, SceneConfig

#: The built-in scene type that starts a chapter by itself.
CHAPTER_SCENE_TYPE = "chapter"


@dataclass(frozen=True)
class ChapterMark:
    """Where the config starts a chapter: its ``title``, ``number`` as written (``None``: not
    numbered), the ``scene`` id and position (``scene_index``) it starts at, and whether that
    scene is a ``chapter`` card (``card``)."""

    title: str
    number: str | None
    scene: str
    scene_index: int
    card: bool


def _number_text(number: object) -> str | None:
    return None if number is None or isinstance(number, bool) else str(number)


def scene_chapter(spec: SceneConfig) -> ChapterMark | None:
    """The chapter ``spec`` starts, if any (``scene_index`` 0; :func:`chapter_marks` sets it)."""
    card = spec.type == CHAPTER_SCENE_TYPE
    field = spec.chapter
    if isinstance(field, str):
        number = spec.params.get("number") if card else None
        return ChapterMark(field, _number_text(number), spec.id, 0, card)
    if isinstance(field, ChapterConfig):
        number = field.number if field.number is not None else (spec.params.get("number") if card else None)
        return ChapterMark(field.title, _number_text(number), spec.id, 0, card)
    title = spec.params.get("title") if card else None
    if isinstance(title, str) and title.strip():
        return ChapterMark(title, _number_text(spec.params.get("number")), spec.id, 0, True)
    return None


def chapter_marks(scenes: Sequence[SceneConfig]) -> list[ChapterMark]:
    """Every chapter start of ``scenes``, in order."""
    out = []
    for i, spec in enumerate(scenes):
        mark = scene_chapter(spec)
        if mark is not None:
            out.append(ChapterMark(mark.title, mark.number, mark.scene, i, mark.card))
    return out


def chapter_problems(scenes: Sequence[SceneConfig]) -> list[str]:
    """What is wrong with the chapters of ``scenes`` (one message each): the same chapter twice
    (title and number), integer numbers that do not increase, a chapter card followed at once by
    another chapter start (the card would be a chapter of its own)."""
    marks = chapter_marks(scenes)
    problems: list[str] = []
    seen: dict[tuple[str, str | None], ChapterMark] = {}
    repeated: set[str] = set()
    for mark in marks:
        key = (mark.title.strip().casefold(), mark.number)
        first = seen.get(key)
        if first is not None:
            repeated.add(mark.scene)
            problems.append(
                f"scenes[{mark.scene_index}] ('{mark.scene}') starts chapter '{mark.title}' again (already started at "
                f"scene '{first.scene}'); a chapter card starts its chapter by itself, so the scenes after it need no 'chapter'"
            )
        else:
            seen[key] = mark
    numbered = [(m, int(m.number)) for m in marks if m.number is not None and m.number.lstrip("-").isdigit() and m.scene not in repeated]
    for (prev, a), (mark, b) in zip(numbered, numbered[1:]):
        if b <= a:
            problems.append(
                f"scenes[{mark.scene_index}] ('{mark.scene}'): chapter number {b} after chapter number {a} "
                f"(scene '{prev.scene}'); chapter numbers must increase"
            )
    for prev, mark in zip(marks, marks[1:]):
        if prev.card and mark.scene_index == prev.scene_index + 1 and not mark.card:
            problems.append(
                f"scenes[{mark.scene_index}] ('{mark.scene}') starts chapter '{mark.title}' right after the chapter card "
                f"'{prev.scene}' ('{prev.title}'), which would be a chapter of its own; to name the card's chapter "
                f"differently, give the card the 'chapter'"
            )
    return problems
