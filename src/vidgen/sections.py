"""``sections:``: an audio-only project written without scenes (DESIGN.md §111).

An audiobook or a podcast episode has no pictures to choose, so its config may list
``sections`` instead of ``scenes``. :func:`expand_sections` turns them into scenes before the
config is validated (so every tool sees an ordinary project): a section ``{id, title, voice,
room, music, sfx, beats}`` becomes a ``text_card`` scene showing its title (a video render of the
project is a plain slideshow), the title also starting a chapter; its beats are the usual beats
(``text``, ``voice``, ``emotion``, ``sting``, ``pause``, ``overlap``, ``actions: [{sfx: ...}]``),
a plain string being a beat of that text; a ``{pause: S}`` section becomes a silent scene of S
seconds (with its own ``sfx`` and ``music``).
"""

from __future__ import annotations

import difflib
from typing import Any

from vidgen.errors import VidgenError

#: Keys of a section, and of a pause between sections.
SECTION_KEYS: tuple[str, ...] = ("id", "title", "voice", "room", "music", "sfx", "beats")
PAUSE_KEYS: tuple[str, ...] = ("id", "pause", "sfx", "music")
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
        for key in ("voice", "room"):
            if key in section:
                scene[key] = section[key]
        scene["beats"] = _beats(section["beats"])
    for key in ("music", "sfx"):
        if key in section:
            scene[key] = section[key]
    return scene


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
