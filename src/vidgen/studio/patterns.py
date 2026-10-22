"""Step patterns of score files (DESIGN.md §93): one bar per ``|``, each bar split into equal
steps, one symbol per step.

``x`` a hit (on a pitched instrument: the chord's bass note; ``x'`` an octave up, ``x,`` down),
``X`` an accented hit, ``o`` a soft hit, ``.`` a rest, ``-`` holds the note before it one step longer, ``*`` the whole chord,
``1``-``9`` a chord degree (1 root, 3 third, 5 fifth, 7 seventh, 8 octave, 9 ninth; ``'`` after
it an octave up, ``,`` an octave down), ``v1``-``v9`` a note of the chord's voicing counted from
the lowest (the written ``notes`` or the voicing ``*`` plays; past the top it starts again an
octave up; ``'`` / ``,`` as for degrees), a note name with its octave (``A4``, ``C#5``, ``Bb3``).
``+`` joins notes, degrees and voicing notes into one step played together (``v2+v3+v4``,
``C4+E4+G4``). ``!`` after a hit accents it, ``?`` makes it soft. Spaces only help reading:
``x... x...`` is ``x...x...``.
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
    r"|v(?P<voice>[1-9])(?P<voice_octaves>[',]*)(?P<voice_mod>[!?]?)"
    r"|(?P<char>[xXo*.\-])(?P<char_octaves>[',]*)(?P<char_mod>[!?]?)"
    r"|(?P<plus>\+)"
    r"|(?P<space>\s+)"
)
#: Step kinds that ``+`` can join.
_JOINABLE = ("note", "degree", "voice", "stack")


@dataclass(frozen=True)
class Step:
    """One step: ``kind`` ``rest``, ``hold``, ``hit`` (the bass note or the drum), ``chord``,
    ``degree`` (``value`` the degree, ``octaves`` up or down), ``voice`` (``value`` the note of
    the chord's voicing from the lowest, 1-based; ``octaves``), ``note`` (``value`` a MIDI
    number) or ``stack`` (``parts``: notes played together); ``gain`` 1, :data:`ACCENT_GAIN` or
    :data:`SOFT_GAIN`; ``marked``: written with ``X``, ``o``, ``!`` or ``?`` (an ``accent:``
    pattern leaves it alone)."""

    kind: str
    value: int = 0
    octaves: int = 0
    gain: float = 1.0
    marked: bool = False
    parts: tuple[Step, ...] = ()

    @property
    def sounds(self) -> bool:
        return self.kind not in ("rest", "hold")

    @property
    def pitched(self) -> bool:
        """Whether the step names a pitch (a drum cannot play it): ``x'`` (the bass an octave up) does."""
        return self.kind in ("chord", "degree", "note", "voice", "stack") or (self.kind == "hit" and self.octaves != 0)


def _join(before: Step, after: Step) -> Step:
    """``before+after`` as one stack; a marked part sets the stack's gain."""
    parts = before.parts if before.kind == "stack" else (Step(before.kind, before.value, before.octaves),)
    gain, marked = (after.gain, True) if after.marked else (before.gain, before.marked)
    return Step("stack", 0, 0, gain if marked else 1.0, marked, parts + (Step(after.kind, after.value, after.octaves),))


Pattern = tuple[tuple[Step, ...], ...]


def _gain(mark: str, default: float = 1.0) -> tuple[float, bool]:
    if mark == "!":
        return ACCENT_GAIN, True
    if mark == "?":
        return SOFT_GAIN, True
    return default, default != 1.0


def parse_steps(value: str | list[str], where: str, lead_hold: bool = False) -> Pattern:
    """A pattern (a string, or a list of strings that follow each other) as bars of steps.
    ``lead_hold``: it may start with ``-`` (a track's steps: the note sounding when its section
    starts goes on; the score checks there is one)."""
    text = " | ".join(value) if isinstance(value, list) else value
    if not isinstance(text, str) or not text.strip():
        raise VidgenError(f"{where}: write the steps as a string, e.g. \"x... x... x... x...\" (one bar of sixteenths)")
    bars: list[list[Step]] = [[]]
    pos = 0
    joining = False  # a '+' waits for the note it joins
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None:
            bad = text[pos]
            hint = " (notes start with a capital letter: A4, not a4)" if bad in "abcdefg" else ""
            hint = hint or (" (a degree is one digit, 1 to 9; write 3' for the tenth)" if bad == "0" else "")
            hint = hint or (" (a voicing note is v and one digit, v1 the lowest: v1 to v9)" if bad == "v" else "")
            raise VidgenError(
                f"{where}: unknown symbol {bad!r} at {pos + 1} in {text!r}{hint}; use x X o . - * 1-9 (degrees), v1-v9 (voicing notes), "
                "notes like A4, + to play notes together, | between bars"
            )
        pos = match.end()
        if match["space"]:
            continue
        step: Step | None = None
        if match["plus"]:
            if joining or not bars[-1] or bars[-1][-1].kind not in _JOINABLE:
                raise VidgenError(f"{where}: '+' at {pos} in {text!r} must join two notes, degrees or voicing notes (e.g. v2+v3+v4, C4+E4)")
            joining = True
            continue
        if match["bar"]:
            if joining:
                raise VidgenError(f"{where}: '+' before '|' in {text!r}: '+' joins two notes in one step")
            bars.append([])
        elif match["note"]:
            gain, marked = _gain(match["note_mod"])
            step = Step("note", note_number(match["note"]), 0, gain, marked)
        elif match["degree"]:
            gain, marked = _gain(match["degree_mod"])
            octaves = match["octaves"].count("'") - match["octaves"].count(",")
            step = Step("degree", int(match["degree"]), octaves, gain, marked)
        elif match["voice"]:
            gain, marked = _gain(match["voice_mod"])
            octaves = match["voice_octaves"].count("'") - match["voice_octaves"].count(",")
            step = Step("voice", int(match["voice"]), octaves, gain, marked)
        elif match["char"]:
            char, mod, marks = match["char"], match["char_mod"], match["char_octaves"]
            if char in ".-" and mod:
                raise VidgenError(f"{where}: {char + mod!r}: only a hit can be accented (!) or soft (?)")
            if char in ".-*" and marks:
                raise VidgenError(f"{where}: {char + marks!r}: only a hit (x X o), a degree or a voicing note takes ' or , (an octave up or down)")
            if char == ".":
                step = Step("rest")
            elif char == "-":
                step = Step("hold")
            elif char == "*":
                step = Step("chord", 0, 0, *_gain(mod))
            else:
                default = {"x": 1.0, "X": ACCENT_GAIN, "o": SOFT_GAIN}[char]
                step = Step("hit", 0, marks.count("'") - marks.count(","), *_gain(mod, default))
        if step is None:
            continue
        if joining:
            if step.kind not in _JOINABLE[:3]:
                raise VidgenError(
                    f"{where}: {text[match.start()]!r} at {match.start() + 1} in {text!r} cannot follow '+', which joins notes, degrees or "
                    "voicing notes (e.g. v2+v3+v4, C4+E4)"
                )
            bars[-1][-1] = _join(bars[-1][-1], step)
            joining = False
        else:
            bars[-1].append(step)
    if joining:
        raise VidgenError(f"{where}: {text!r} ends with '+' (it joins two notes in one step)")
    if any(not bar for bar in bars):
        raise VidgenError(f"{where}: an empty bar in {text!r} (two '|' in a row, or one at an end)")
    if bars[0][0].kind == "hold" and not lead_hold:
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
