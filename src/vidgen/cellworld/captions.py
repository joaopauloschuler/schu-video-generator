"""Step captions of the cell-biology processes (DESIGN.md §95.16): each step of a process has a
textbook caption (``TFIIH unwinds the DNA at the start site (+1): a transcription bubble of
~13 bp; …``); in a tall frame (a phone) the full text is dense, so a caption can be shown short —
its first clause, the statement itself, with the details after a colon, a semicolon or a dash
left to the narration. No manim."""

from __future__ import annotations

from typing import Literal, Union

#: What a process action's ``notes`` option takes: true / full (the whole caption), short (its
#: first clause), auto (short in a tall frame, full in a wide one), false (none).
NoteMode = Union[bool, Literal["auto", "full", "short"]]
#: Clause breaks, in the order they are tried.
BREAKS = (": ", "; ", " — ", " – ")
#: A first clause shorter than this (plain characters) takes the next one with it.
MIN_CLAUSE = 32


def _plain_len(text: str) -> int:
    depth, n = 0, 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif depth == 0:
            n += 1
    return n


def _clauses(note: str) -> list[tuple[str, str]]:
    """The caption cut at its clause breaks outside parentheses and markup: (clause, the break
    after it)."""
    out: list[tuple[str, str]] = []
    depth = 0
    start = 0
    k = 0
    while k < len(note):
        ch = note[k]
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth = max(0, depth - 1)
        elif depth == 0:
            hit = next((b for b in BREAKS if note.startswith(b, k)), None)
            if hit is not None:
                out.append((note[start:k], hit))
                k += len(hit)
                start = k
                continue
        k += 1
    out.append((note[start:], ""))
    return out


def short_note(note: str) -> str:
    """The caption's first clause (with the next when the first is very short), or the whole
    caption when it has no break."""
    parts = _clauses(note)
    text, joint = parts[0]
    k = 1
    while _plain_len(text) < MIN_CLAUSE and k < len(parts):
        text = text + joint + parts[k][0]
        joint = parts[k][1]
        k += 1
    return text.rstrip(" ,")


def note_text(note: str | None, mode: NoteMode, tall: bool) -> str | None:
    """The caption to show for ``note`` with the ``notes`` option ``mode`` in a frame that is
    ``tall`` (portrait) or not; ``None`` for no caption."""
    if not note or mode is False:
        return None
    if mode == "short" or (mode == "auto" and tall):
        return short_note(note)
    return note


__all__ = ["BREAKS", "NoteMode", "note_text", "short_note"]
