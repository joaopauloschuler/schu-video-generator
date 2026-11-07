"""``sections:``: an audio-only project written without scenes (DESIGN.md §111).

An audiobook or a podcast episode has no pictures to choose, so its config may list
``sections`` instead of ``scenes``. :func:`expand_sections` turns them into scenes before the
config is validated (so every tool sees an ordinary project): a section ``{id, title, voice,
room, music, sfx, ambience, beats}`` becomes a ``text_card`` scene showing its title (a video
render of the project is a plain slideshow), the title also starting a chapter; its beats are
the usual beats (``text``, ``voice``, ``emotion``, ``sting``, ``pause``, ``overlap``,
``ambience``, ``actions: [{sfx: ...}]``), a plain string being a beat of that text; a ``{pause:
S}`` section becomes a silent scene of S seconds (with its own ``sfx``, ``music``, ``ambience``
and ``room``, DESIGN.md §112).
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

from vidgen.errors import Problem, VidgenError

#: Keys of a section, and of a pause between sections.
SECTION_KEYS: tuple[str, ...] = ("id", "title", "voice", "room", "music", "sfx", "ambience", "beats")
PAUSE_KEYS: tuple[str, ...] = ("id", "pause", "sfx", "music", "ambience", "room")
#: The scene type a section becomes.
SECTION_TYPE = "text_card"
#: The card text of a pause (a silent scene must show something in a video render).
PAUSE_TEXT = "…"


def _unknown_key(where: str, key: Any, known: tuple[str, ...]) -> VidgenError:
    close = difflib.get_close_matches(str(key), known, n=1)
    hint = f"; did you mean '{close[0]}'?" if close else ""
    return VidgenError(f"{where}: unknown key '{key}'{hint} (a section has {', '.join(known)})")


def _beats(raw: Any) -> Any:
    """A section's beats: a plain string is a beat of that text."""
    if not isinstance(raw, list):
        return raw
    return [{"text": item} if isinstance(item, str) else item for item in raw]


def _scene(n: int, section: Any, title: str, source: str) -> dict[str, Any]:
    where = f"{source}: sections[{n}]"
    if not isinstance(section, dict):
        raise VidgenError(f"{where}: a section is a mapping {{title, beats}} or a pause {{pause: S}}")
    pause = "pause" in section
    if pause and "beats" in section:
        raise VidgenError(f"{where}: a pause section has no beats; for silence after a line add `- pause: S` to the beats list")
    known = PAUSE_KEYS if pause else SECTION_KEYS
    for key in section:
        if key not in known:
            raise _unknown_key(where, key, known)
    scene: dict[str, Any] = {"id": section.get("id", f"s{n + 1}"), "type": SECTION_TYPE}
    if pause:
        scene["params"] = {"text": PAUSE_TEXT}
        scene["duration"] = section["pause"]
    else:
        if not section.get("beats"):
            raise VidgenError(f"{where}: a section needs beats (its lines); for silence write a pause section {{pause: S}}")
        heading = section.get("title")
        scene["params"] = {"text": heading if isinstance(heading, str) and heading.strip() else title}
        if heading is not None:
            scene["chapter"] = heading
        if "voice" in section:
            scene["voice"] = section["voice"]
        scene["beats"] = _beats(section["beats"])
    for key in ("room", "music", "sfx", "ambience"):
        if key in section:
            scene[key] = section[key]
    return scene


#: A scene location in a message, and what a section calls the keys it was made from.
_LOCATION = re.compile(r"\bscenes\[(\d+)\](\.params\.text|\.chapter|\.duration)?(?![\w.\[])")
_LOCATION_ANY = re.compile(r"\bscenes\[(\d+)\]")
_SECTION_KEY = {".params.text": ".title", ".chapter": ".title", ".duration": ".pause"}


def _section_name(index: str, sources: Sequence[int | str] | None) -> str:
    """The section scene ``index`` was made from (``sections[k]``), or the key that added it."""
    k = int(index)
    source: int | str = sources[k] if sources is not None and k < len(sources) else k
    return f"sections[{source}]" if isinstance(source, int) else source


def section_location(text: str, sources: Sequence[int | str] | None = None) -> str:
    """``text`` (a config location or a message) with its scene locations named as the sections
    they were made from: ``scenes[2].beats[0]`` -> ``sections[2].beats[0]``,
    ``scenes[2].chapter`` -> ``sections[2].title``, ``scenes[2].duration`` -> ``sections[2].pause``
    (one scene per section). ``sources``: each scene's section index, or the key that added it
    (``cold_open``, ``credits``; :func:`vidgen.delivery.scene_sources`); default the same index."""
    text = _LOCATION.sub(lambda m: f"{_section_name(m[1], sources)}{_SECTION_KEY.get(m[2] or '', m[2] or '')}", text)
    return _LOCATION_ANY.sub(lambda m: _section_name(m[1], sources), text)


def section_problems(problems: Iterable[Problem], sources: Sequence[int | str] | None = None) -> list[Problem]:
    """``problems`` located in the ``sections:`` they come from (:func:`section_location`)."""
    return [replace(p, location=section_location(p.location, sources), message=section_location(p.message, sources)) for p in problems]


def section_error(exc: VidgenError, sources: Sequence[int | str] | None = None) -> VidgenError:
    """``exc`` (raised validating a project written with ``sections:``) with its locations named
    as sections."""
    return VidgenError(section_location(str(exc), sources), problems=section_problems(exc.problems, sources), details=exc.details)


def expand_sections(data: Any, source: str = "video.yaml") -> Any:
    """The raw config ``data`` with its ``sections`` turned into ``scenes`` (see the module doc);
    a config without ``sections`` is returned as it is. :class:`VidgenError` for a config with
    both, an empty list, an unknown key (with a did-you-mean) or a section without beats."""
    if not isinstance(data, dict) or "sections" not in data:
        return data
    if "scenes" in data:
        raise VidgenError(f"{source}: give scenes or sections, not both (sections are the scenes of an audio-only project)")
    sections = data["sections"]
    if not isinstance(sections, list) or not sections:
        raise VidgenError(f"{source}: sections: a list of sections ({{title, beats}}) and pauses ({{pause: S}})")
    title = data.get("title") if isinstance(data.get("title"), str) and data.get("title") else PAUSE_TEXT
    scenes = [_scene(n, section, title, source) for n, section in enumerate(sections)]
    return {**{k: v for k, v in data.items() if k != "sections"}, "scenes": scenes}
