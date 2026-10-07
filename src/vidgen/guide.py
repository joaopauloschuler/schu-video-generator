"""The author guide for AI agents (``vidgen guide``, DESIGN.md §59).

The guide is one Markdown file shipped as package data (``data/guide/AGENTS.md``; the
repository's ``AGENTS.md`` is a copy of it). Topics are its ``##`` sections, each introduced by a
marker line ``<!-- topic: NAME (also: ALIAS, ALIAS) -->``; ``vidgen guide TOPIC`` prints one.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from vidgen.errors import VidgenError

#: The packaged guide (the repository's ``AGENTS.md`` is a copy of this file).
GUIDE_FILE = Path(__file__).resolve().parent / "data" / "guide" / "AGENTS.md"

_MARKER = re.compile(r"^<!-- topic: ([a-z][a-z0-9-]*)(?: \(also: ([^)]*)\))? -->$", re.MULTILINE)


@dataclass(frozen=True)
class GuideTopic:
    """One section of the guide: its ``name``, other names it answers to, ``##`` title and text."""

    name: str
    title: str
    aliases: tuple[str, ...]
    text: str


def guide_text() -> str:
    """The whole guide as Markdown, without the topic marker lines."""
    return _strip_markers(_raw())


def guide_topics() -> list[GuideTopic]:
    """The guide's topics in order."""
    raw = _raw()
    markers = list(_MARKER.finditer(raw))
    topics = []
    for i, match in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(raw)
        text = raw[match.end() : end].strip("\n") + "\n"
        heading = re.search(r"^## (.+)$", text, re.MULTILINE)
        aliases = tuple(a.strip() for a in (match[2] or "").split(",") if a.strip())
        topics.append(GuideTopic(match[1], heading[1].strip() if heading else match[1], aliases, text))
    return topics


def find_topic(name: str) -> GuideTopic:
    """The topic called ``name`` (or one of its aliases; case-insensitive); an unknown name is a
    :class:`VidgenError` with suggestions and the list of topics."""
    wanted = name.strip().lower()
    topics = guide_topics()
    for topic in topics:
        if wanted == topic.name or wanted in topic.aliases:
            return topic
    names = [t.name for t in topics] + [a for t in topics for a in t.aliases]
    close = difflib.get_close_matches(wanted, names, n=3, cutoff=0.6)
    hint = f"; did you mean {' or '.join(repr(c) for c in close)}?" if close else ""
    known = ", ".join(t.name for t in topics)
    raise VidgenError(f"unknown guide topic '{name}'{hint} (topics: {known}; `vidgen guide --list`)")


def topic_lines(topics: list[GuideTopic]) -> list[str]:
    """``vidgen guide --list``: one line per topic, its name, title and aliases."""
    width = max(len(t.name) for t in topics)
    lines = []
    for topic in topics:
        also = f"  (also: {', '.join(topic.aliases)})" if topic.aliases else ""
        lines.append(f"{topic.name:<{width}}  {topic.title}{also}")
    lines.append("")
    lines.append("vidgen guide TOPIC prints one topic; vidgen guide the whole guide.")
    return lines


def _raw() -> str:
    try:
        return GUIDE_FILE.read_text(encoding="utf-8")
    except OSError as exc:  # a broken install
        raise VidgenError(f"cannot read the guide {GUIDE_FILE}: {exc}") from None


def _strip_markers(text: str) -> str:
    return _MARKER.sub("", text).replace("\n\n\n", "\n\n")
