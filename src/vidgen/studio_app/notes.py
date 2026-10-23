"""Listening notes (DESIGN.md §94.16): short notes pinned to a moment of the piece while it plays
("this part drags", "goosebumps at the lift"), kept in the session's ``notes.json``.

A note records the moment where it was made — seconds, bar and beat, the section and the bar
within it, and the version playing. Notes belong to the session, not to one version: when the
piece changes, an open note stays at the same place **in its section** (the same bar of the
section and the same point in the bar), so it follows the music when a section before it grows
or shrinks; when its section became shorter or is gone it is moved to the nearest bar left and
the note says so (``moved``).
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic

#: ``notes.json``'s ``format``.
NOTES_FORMAT = 1
#: The longest note (characters).
MAX_NOTE_CHARS = 500
#: A note's id: ``n1``, ``n2``...
NOTE_ID = re.compile(r"^n[1-9][0-9]{0,4}\Z")
#: A note's states.
STATUSES = ("open", "resolved")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def clean_text(text: Any) -> str:
    """A note's words, spaces folded; :class:`VidgenError` when empty or too long."""
    if not isinstance(text, str):
        raise VidgenError("a note is text")
    text = " ".join(text.split())
    if not text:
        raise VidgenError("a note needs a few words")
    if len(text) > MAX_NOTE_CHARS:
        raise VidgenError(f"a note is at most {MAX_NOTE_CHARS} characters")
    return text


def beats_per_bar(outline: Mapping[str, Any]) -> int:
    """The beats of a bar (the time signature's top: 4 in 4/4, 6 in 6/8)."""
    try:
        return max(1, int(str(outline.get("time", "4/4")).split("/")[0]))
    except ValueError:
        return 4


def locate(outline: Mapping[str, Any], seconds: float) -> dict[str, Any]:
    """Where moment ``seconds`` is in a piece (its outline: sections with ``start``, ``bars``,
    ``first_bar``, and ``bar_seconds``): ``{seconds, bar, beat, section, bar_in_section, frac}``
    — bar and beat 1-based, ``frac`` the point within the bar (0..1). A moment past the last
    bar (a one-pass piece's tail) is the last bar's end."""
    sections = list(outline.get("sections") or [])
    if not sections:
        raise VidgenError("this score has no sections to pin a note to")
    bar_seconds = float(outline["bar_seconds"])
    seconds = max(0.0, float(seconds))
    found = sections[0]
    for s in sections:
        if s["start"] <= seconds + 1e-6:
            found = s
    into = (seconds - found["start"]) / bar_seconds
    index = min(int(math.floor(into + 1e-9)), found["bars"] - 1)
    frac = min(max(into - index, 0.0), 0.999)
    beats = beats_per_bar(outline)
    return {
        "seconds": round(found["start"] + (index + frac) * bar_seconds, 3),
        "bar": found["first_bar"] + index,
        "beat": min(beats, 1 + int(frac * beats)),
        "section": found["name"],
        "bar_in_section": index + 1,
        "frac": round(frac, 4),
    }


def place(outline: Mapping[str, Any], note: Mapping[str, Any]) -> dict[str, Any]:
    """Where ``note`` sits in another version of the piece (its outline): the same bar of its
    section and the same point in the bar; ``moved`` says in words when the bar number changed
    (sections before it changed length), its section is shorter now, or gone."""
    sections = list(outline.get("sections") or [])
    bar_seconds = float(outline["bar_seconds"])
    same = next((s for s in sections if s["name"] == note["section"]), None)
    moved = None
    if same is not None:
        index = note["bar_in_section"] - 1
        if index >= same["bars"]:
            index = same["bars"] - 1
            moved = f"the {same['name']} is {same['bars']} bar{'s' if same['bars'] != 1 else ''} now: moved to its last bar"
        seconds = same["start"] + (index + note["frac"]) * bar_seconds
        where = locate(outline, seconds)
    else:  # its section is gone: the same bar of the piece, or the last one
        total = sum(s["bars"] for s in sections)
        bar = min(note["bar"], total)
        first = next(s for s in reversed(sections) if s["first_bar"] <= bar)
        seconds = first["start"] + (bar - first["first_bar"] + note["frac"]) * bar_seconds
        where = locate(outline, seconds)
        moved = f"the {note['section']} is gone: kept at bar {where['bar']} (in the {where['section']})"
    if moved is None and where["bar"] != note["bar"]:
        moved = f"was bar {note['bar']} on v{note['version']}; the sections before it changed length"
    return {**where, "moved": moved}


class NoteBook:
    """A session's ``notes.json``: the notes in the order made, each ``{id, text, seconds, bar,
    beat, section, bar_in_section, frac, version, created, status, answers}``; ``answers`` are
    agents' explanations ``{proposal, version, by, text, status}``."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / "notes.json"
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            doc = {}
        except (OSError, ValueError) as exc:
            raise VidgenError(f"cannot read {self.path}: {exc}") from None
        self.notes: list[dict[str, Any]] = list(doc.get("notes", []))
        self.next = int(doc.get("next", 1))

    def save(self) -> None:
        doc = {"format": NOTES_FORMAT, "next": self.next, "notes": self.notes}
        write_text_atomic(self.path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    def get(self, note_id: str) -> dict[str, Any]:
        found = next((n for n in self.notes if n["id"] == note_id), None)
        if found is None:
            raise VidgenError(f"no note {note_id!r} in this session")
        return found

    def add(self, outline: Mapping[str, Any], version: int, seconds: float, text: Any) -> dict[str, Any]:
        """Pin a note at moment ``seconds`` of ``version`` (its outline)."""
        note = {"id": f"n{self.next}", "text": clean_text(text), **locate(outline, seconds), "version": version,
                "created": _now(), "status": "open", "answers": []}
        self.next += 1
        self.notes.append(note)
        self.save()
        return note

    def update(self, note_id: str, text: Any = None, status: str | None = None) -> dict[str, Any]:
        """Change a note's words and / or its status (``open`` / ``resolved``)."""
        note = self.get(note_id)
        if text is not None:
            note["text"] = clean_text(text)
        if status is not None:
            if status not in STATUSES:
                raise VidgenError(f"a note's status is one of {', '.join(STATUSES)}, got {status!r}")
            note["status"] = status
        self.save()
        return note

    def delete(self, note_id: str) -> None:
        self.notes.remove(self.get(note_id))
        self.save()

    def answer(self, note_id: str, answer: Mapping[str, Any]) -> None:
        """Attach an agent's explanation to a note (not saved: call :meth:`save`)."""
        self.get(note_id)["answers"].append(dict(answer))

    def set_answers(self, proposal: str, status: str) -> None:
        """Mark proposal ``proposal``'s explanations kept or discarded (not saved)."""
        for note in self.notes:
            for a in note["answers"]:
                if a.get("proposal") == proposal:
                    a["status"] = status

    def shown(self, outline: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        """The notes placed in a version (its outline; ``None``: as made), each with ``at``."""
        out = []
        for note in self.notes:
            at = place(outline, note) if outline is not None else {**{k: note[k] for k in ("seconds", "bar", "beat", "section")}, "moved": None}
            out.append({**note, "at": at})
        return out

    def open_notes(self) -> list[dict[str, Any]]:
        return [n for n in self.notes if n["status"] == "open"]
