"""The author guide for AI agents (``vidgen guide``).

The guide is package data in ``data/guide/``: a short entry page, ``AGENTS.md`` (the repository's
``AGENTS.md`` is a copy of it), and one Markdown file per topic (``scenes.md``, ``web.md``, ...).
Each topic file starts with a marker line ``<!-- topic: NAME (also: ALIAS, ALIAS) -->``.
``vidgen guide`` prints the entry page, ``vidgen guide TOPIC`` one topic.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from vidgen.errors import VidgenError

#: The folder of the packaged guide.
GUIDE_DIR = Path(__file__).resolve().parent / "data" / "guide"
#: The short entry page (the repository's ``AGENTS.md`` is a copy of this file).
GUIDE_FILE = GUIDE_DIR / "AGENTS.md"
#: The topics in the order ``vidgen guide --list`` shows them; topic NAME is the file ``NAME.md``.
TOPIC_NAMES: tuple[str, ...] = (
    "start", "workflow", "pacing", "social", "scenes", "design", "actions", "cartoons", "platform", "iso",
    "biology", "genetics", "science", "orbits", "space-scenes", "three-d", "web", "particle-physics",
    "overlays", "audio", "examples", "outputs", "troubleshooting",
)

_MARKER = re.compile(r"^<!-- topic: ([a-z][a-z0-9-]*)(?: \(also: ([^)]*)\))? -->$", re.MULTILINE)


@dataclass(frozen=True)
class GuideTopic:
    """One topic of the guide: its ``name``, other names it answers to, ``##`` title, text and file."""

    name: str
    title: str
    aliases: tuple[str, ...]
    text: str
    path: Path


def topic_file(name: str) -> Path:
    """The packaged file of the topic called ``name`` (its exact name, not an alias)."""
    return GUIDE_DIR / f"{name}.md"


def entry_page_text() -> str:
    """The short entry page (``AGENTS.md``): what ``vidgen guide`` prints with no topic."""
    return _read(GUIDE_FILE)


def all_topics_text() -> str:
    """Every topic's text, in order, joined into one Markdown text (without the marker lines);
    the entry page is not part of it."""
    return "\n".join(topic.text for topic in guide_topics())


def guide_topics() -> list[GuideTopic]:
    """The guide's topics in order."""
    topics = []
    for name in TOPIC_NAMES:
        path = topic_file(name)
        raw = _read(path)
        match = _MARKER.match(raw)
        if match is None or match[1] != name or len(_MARKER.findall(raw)) != 1:
            raise VidgenError(f"the guide file {path} must start with its one marker <!-- topic: {name} ... -->")
        text = raw[match.end() :].strip("\n") + "\n"
        heading = re.search(r"^## (.+)$", text, re.MULTILINE)
        aliases = tuple(a.strip() for a in (match[2] or "").split(",") if a.strip())
        topics.append(GuideTopic(name, heading[1].strip() if heading else name, aliases, text, path))
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
    lines.append("vidgen guide TOPIC prints one topic, vidgen guide alone the short entry page. Read only the topics your video needs.")
    return lines


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # a broken install
        raise VidgenError(f"cannot read the guide {path}: {exc}") from None
