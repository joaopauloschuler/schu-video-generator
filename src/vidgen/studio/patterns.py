"""Step patterns of score files (DESIGN.md §93): one bar per ``|``, each bar split into equal
steps, one symbol per step.

``x`` a hit (on a pitched instrument: the chord's bass note), ``X`` an accented hit, ``o`` a
soft hit, ``.`` a rest, ``-`` holds the note before it one step longer, ``*`` the whole chord,
``1``-``9`` a chord degree (1 root, 3 third, 5 fifth, 7 seventh, 8 octave, 9 ninth; ``'`` after
it an octave up, ``,`` an octave down), a note name with its octave (``A4``, ``C#5``, ``Bb3``).
``!`` after a hit accents it, ``?`` makes it soft. Spaces only help reading: ``x... x...`` is
``x...x...``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vidgen.errors import VidgenError
from vidgen.studio.theory import note_number

#: Gain of an accented and a soft hit against a normal one (+3.5 dB, -6 dB).
ACCENT_GAIN = 1.5
SOFT_GAIN = 0.5

_TOKEN = re.compile(
    r"(?P<bar>\|)"
    r"|(?P<note>[A-G][#b]?\d)(?P<note_mod>[!?]?)"
    r"|(?P<degree>[1-9])(?P<octaves>[',]*)(?P<degree_mod>[!?]?)"
    r"|(?P<char>[xXo*.\-])(?P<char_mod>[!?]?)"
    r"|(?P<space>\s+)"
)


@dataclass(frozen=True)
class Step:
    """One step: ``kind`` ``rest``, ``hold``, ``hit`` (the bass note or the drum), ``chord``,
    ``degree`` (``value`` the degree, ``octaves`` up or down) or ``note`` (``value`` a MIDI
    number); ``gain`` 1, :data:`ACCENT_GAIN` or :data:`SOFT_GAIN`; ``marked``: written with
    ``X``, ``o``, ``!`` or ``?`` (an ``accent:`` pattern leaves it alone)."""

    kind: str
    value: int = 0
    octaves: int = 0
    gain: float = 1.0
    marked: bool = False

    @property
    def sounds(self) -> bool:
        return self.kind not in ("rest", "hold")

    @property
    def pitched(self) -> bool:
        return self.kind in ("chord", "degree", "note")


Pattern = tuple[tuple[Step, ...], ...]


def _gain(mark: str, default: float = 1.0) -> tuple[float, bool]:
    if mark == "!":
        return ACCENT_GAIN, True
    if mark == "?":
        return SOFT_GAIN, True
    return default, default != 1.0


def parse_steps(value: str | list[str], where: str) -> Pattern:
    """A pattern (a string, or a list of strings that follow each other) as bars of steps."""
    text = " | ".join(value) if isinstance(value, list) else value
    if not isinstance(text, str) or not text.strip():
        raise VidgenError(f"{where}: write the steps as a string, e.g. \"x... x... x... x...\" (one bar of sixteenths)")
    bars: list[list[Step]] = [[]]
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None:
            bad = text[pos]
            hint = " (notes start with a capital letter: A4, not a4)" if bad in "abcdefg" else ""
            hint = hint or (" (a degree is one digit, 1 to 9; write 3' for the tenth)" if bad == "0" else "")
            raise VidgenError(
                f"{where}: unknown symbol {bad!r} at {pos + 1} in {text!r}{hint}; use x X o . - * 1-9 (degrees), notes like A4, | between bars"
            )
        pos = match.end()
        if match["bar"]:
            bars.append([])
        elif match["note"]:
            gain, marked = _gain(match["note_mod"])
            bars[-1].append(Step("note", note_number(match["note"]), 0, gain, marked))
        elif match["degree"]:
            gain, marked = _gain(match["degree_mod"])
            octaves = match["octaves"].count("'") - match["octaves"].count(",")
            bars[-1].append(Step("degree", int(match["degree"]), octaves, gain, marked))
        elif match["char"]:
            char, mod = match["char"], match["char_mod"]
            if char in ".-" and mod:
                raise VidgenError(f"{where}: {char + mod!r}: only a hit can be accented (!) or soft (?)")
            if char == ".":
                bars[-1].append(Step("rest"))
            elif char == "-":
                bars[-1].append(Step("hold"))
            elif char == "*":
                bars[-1].append(Step("chord", 0, 0, *_gain(mod)))
            else:
                default = {"x": 1.0, "X": ACCENT_GAIN, "o": SOFT_GAIN}[char]
                bars[-1].append(Step("hit", 0, 0, *_gain(mod, default)))
    if any(not bar for bar in bars):
        raise VidgenError(f"{where}: an empty bar in {text!r} (two '|' in a row, or one at an end)")
    if bars[0][0].kind == "hold":
        raise VidgenError(f"{where}: {text!r} starts with '-' (a hold needs a note before it)")
    flat = [s for bar in bars for s in bar]
    for before, step in zip(flat, flat[1:]):
        if step.kind == "hold" and before.kind == "rest":
            raise VidgenError(f"{where}: '-' after '.' in {text!r}: a rest cannot be held (write '.' again)")
    return tuple(tuple(bar) for bar in bars)


def parse_accent(text: str | int, where: str) -> tuple[int, ...]:
    """``3+3+2`` as group lengths (each at least 1)."""
    parts = str(text).replace(" ", "").split("+")
    if not all(p.isdigit() and int(p) > 0 for p in parts):
        raise VidgenError(f"{where}: write the accent groups as step counts joined by '+', e.g. \"3+3+2\" (accents on steps 1, 4 and 7 of every 8)")
    return tuple(int(p) for p in parts)


def accent_steps(groups: tuple[int, ...], steps: int) -> set[int] | None:
    """The accented step indices of a bar of ``steps`` steps (the groups repeated), or ``None``
    when the groups do not fit the bar a whole number of times."""
    cycle = sum(groups)
    if steps % cycle:
        return None
    starts = [sum(groups[:k]) for k in range(len(groups))]
    return {c + s for c in range(0, steps, cycle) for s in starts}
