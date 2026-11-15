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

A track's steps may carry marks (DESIGN.md §120.7). ``[...]`` before a step holds items separated
by spaces, each in force until changed: a dynamic (``pp`` to ``fff``, or dB with a sign), a
hairpin ``<`` / ``>`` running to the next dynamic, ``fp`` / ``sfz``, a setting of the instrument
(``stroke=pizzicato``, or its named value alone: ``pizzicato``) and ``default``. ``( ... )`` is
a slur: the notes inside after the first are not attacked again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from vidgen.errors import VidgenError
from vidgen.studio.theory import note_number

#: Gain of an accented and a soft hit against a normal one (+3.5 dB, -6 dB).
ACCENT_GAIN = 1.5
SOFT_GAIN = 0.5

#: Dynamic marks in dB against an unmarked note (which is ``mf``).
DYNAMICS = {"ppp": -20.0, "pp": -15.0, "p": -10.0, "mp": -5.0, "mf": 0.0, "f": 4.0, "ff": 7.0, "fff": 10.0}
#: ``sfz``: dB above the level in force at the note's start.
SFZ_DB = 7.0
#: The range of a dynamic written as a number of dB.
DYNAMIC_RANGE = (-40.0, 12.0)
_LEVEL_TEXT = r"ppp|pp|p|mp|mf|fff|ff|f|[+-]\d+(?:\.\d+)?"
_DYNAMIC = re.compile(rf"(?P<level>{_LEVEL_TEXT})?(?P<hairpin>[<>])?")
_FORTE_PIANO = re.compile(r"(?P<loud>fff|ff|f|mf)(?P<soft>ppp|pp|p|mp)")
_SETTING_ITEM = re.compile(r"[a-z][a-z0-9_]*(=[^\s=\[\]]+)?")

_TOKEN = re.compile(
    r"(?P<bar>\|)"
    r"|\[(?P<mark>[^\[\]]*)\]"
    r"|(?P<slur>[()])"
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
    pattern leaves it alone).

    From the marks (DESIGN.md §120.7): ``level`` / ``level_end``: the dynamic in dB at the
    step's start and end (0: unmarked; they differ under a hairpin); ``burst``: dB above
    ``level`` at the note's start (``fp``, ``sfz``); ``slur``: the note is slurred from the one
    before (not attacked again); ``marks``: the setting items written before the step, as
    written; ``changes``: the instrument settings in force that differ from the part's (the
    score resolves ``marks`` into them)."""

    kind: str
    value: int = 0
    octaves: int = 0
    gain: float = 1.0
    marked: bool = False
    parts: tuple[Step, ...] = ()
    level: float = 0.0
    level_end: float = 0.0
    burst: float = 0.0
    slur: bool = False
    marks: tuple[str, ...] = ()
    changes: tuple[tuple[str, float], ...] = ()

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
    return Step("stack", 0, 0, gain if marked else 1.0, marked, parts + (Step(after.kind, after.value, after.octaves),), marks=before.marks)


Pattern = tuple[tuple[Step, ...], ...]


def _gain(mark: str, default: float = 1.0) -> tuple[float, bool]:
    if mark == "!":
        return ACCENT_GAIN, True
    if mark == "?":
        return SOFT_GAIN, True
    return default, default != 1.0


def _level_db(text: str) -> float | None:
    """The dB of a dynamic's name or signed number; ``None`` when it is out of range."""
    db = DYNAMICS[text] if text in DYNAMICS else float(text)
    return db if DYNAMIC_RANGE[0] <= db <= DYNAMIC_RANGE[1] else None


class _Dynamics:
    """The dynamics of a pattern while it is read: the level in force and an open hairpin."""

    def __init__(self, where: str, text: str) -> None:
        self.where, self.text = where, text
        self.level = 0.0
        #: An open hairpin: where it began (in bars), its level there and its sign.
        self.hairpin: tuple[float, float, str] | None = None
        #: The steps under the open hairpin: their bar, index in it, start and end (in bars).
        self.under: list[tuple[list[Step], int, float, float]] = []

    def fail(self, message: str) -> VidgenError:
        return VidgenError(f"{self.where}: {message} in {self.text!r}")

    def _arrive(self, at: float, level: float, item: str) -> None:
        """A level written at ``at`` (bars): an open hairpin ends there."""
        if self.hairpin is not None:
            start, first, sign = self.hairpin
            if at <= start:
                raise self.fail(f"[{item}] stands on the step where the hairpin '{sign}' begins: write it where the hairpin ends")
            if level == first or (level > first) != (sign == "<"):
                other = ">" if sign == "<" else "<"
                raise self.fail(f"the hairpin '{sign}' {'grows' if sign == '<' else 'falls'}, but it runs from {first:+g} dB to [{item}] "
                                f"({level:+g} dB): write '{other}' or another level")
            for bar, k, a, b in self.under:
                bar[k] = replace(bar[k], level=first + (level - first) * (a - start) / (at - start), level_end=first + (level - first) * (b - start) / (at - start))
            self.hairpin, self.under = None, []
        self.level = level

    def read(self, item: str, at: float, sounding: bool) -> float | None:
        """One item of a mark standing at ``at`` (bars). Returns ``None`` when it is no dynamic
        (a setting item: the caller keeps it), else the burst in dB it gives the note it stands
        before (0 for all but ``fp`` and ``sfz``; ``sounding``: a note follows)."""
        forte_piano = _FORTE_PIANO.fullmatch(item)
        if forte_piano or item == "sfz":
            if not sounding:
                raise self.fail(f"[{item}] shapes the start of a note: write it before a note or hit, not before '-', '.' or the end")
            if item == "sfz":
                if self.hairpin is not None:
                    raise self.fail(f"[sfz] under the hairpin '{self.hairpin[2]}': give the level the hairpin reaches first (e.g. [f sfz])")
                return SFZ_DB
            loud, soft = DYNAMICS[forte_piano["loud"]], DYNAMICS[forte_piano["soft"]]
            self._arrive(at, loud, item)
            self.level = soft
            return loud - soft
        match = _DYNAMIC.fullmatch(item)
        if match is None or not item:
            return None
        if match["level"]:
            level = _level_db(match["level"])
            if level is None:
                raise self.fail(f"[{item}]: a dynamic in dB is from {DYNAMIC_RANGE[0]:g} to {DYNAMIC_RANGE[1]:+g}")
            self._arrive(at, level, item)
        if match["hairpin"]:
            if self.hairpin is not None:
                raise self.fail(f"[{item}]: the hairpin '{self.hairpin[2]}' before it has no end yet: write the level it reaches first (e.g. [f {match['hairpin']}])")
            self.hairpin = (at, self.level, match["hairpin"])
        return 0.0

    def cover(self, bar: list[Step], k: int, start: float, end: float) -> None:
        """The step ``bar[k]`` from ``start`` to ``end`` (bars) gets the level in force."""
        if self.level:
            bar[k] = replace(bar[k], level=self.level, level_end=self.level)
        if self.hairpin is not None:
            self.under.append((bar, k, start, end))


def _mark_items(body: str, where: str, text: str) -> list[str]:
    items = body.split()
    if not items:
        raise VidgenError(f"{where}: an empty mark '[]' in {text!r}: write a dynamic ([p], [ff], [p <]), a setting ([stroke=pizzicato]) or [default]")
    return items


def parse_steps(value: str | list[str], where: str, lead_hold: bool = False, expressive: bool = False) -> Pattern:
    """A pattern (a string, or a list of strings that follow each other) as bars of steps.
    ``lead_hold``: it may start with ``-`` (a track's steps: the note sounding when its section
    starts goes on; the score checks there is one). ``expressive``: marks ``[...]`` and slurs
    ``( )`` are read (a track's steps); elsewhere they are an error."""
    text = " | ".join(value) if isinstance(value, list) and all(isinstance(v, str) for v in value) else value
    if not isinstance(text, str) or not text.strip():
        raise VidgenError(f"{where}: write the steps as a string, e.g. \"x... x... x... x...\" (one bar of sixteenths)")
    bars: list[list[Step]] = [[]]
    pos = 0
    joining = False  # a '+' waits for the note it joins
    pending: list[str] = []  # the items of the marks before the next step
    slurred: int | None = None  # notes read inside an open slur
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None:
            bad = text[pos]
            hint = " (notes start with a capital letter: A4, not a4)" if bad in "abcdefg" else ""
            hint = hint or (" (a degree is one digit, 1 to 9; write 3' for the tenth)" if bad == "0" else "")
            hint = hint or (" (a voicing note is v and one digit, v1 the lowest: v1 to v9)" if bad == "v" else "")
            hint = hint or (" (a mark is closed by ']' and holds no brackets: [p], [ff stroke=spiccato])" if bad in "[]" else "")
            raise VidgenError(
                f"{where}: unknown symbol {bad!r} at {pos + 1} in {text!r}{hint}; use x X o . - * 1-9 (degrees), v1-v9 (voicing notes), "
                "notes like A4, + to play notes together, | between bars"
                + (", [..] for marks (dynamics, settings) and ( ) for a slur" if expressive else "")
            )
        pos = match.end()
        if match["space"]:
            continue
        if (match["mark"] is not None or match["slur"]) and not expressive:
            raise VidgenError(f"{where}: {match[0]!r} in {text!r}: marks and slurs belong to a track's steps; here use x X o . - only")
        if (match["mark"] is not None or match["slur"]) and joining:
            raise VidgenError(f"{where}: {match[0]!r} after '+' in {text!r}: write a mark or a slur before the first note of a step, not inside it")
        step: Step | None = None
        if match["mark"] is not None:
            pending += _mark_items(match["mark"], where, text)
            continue
        if match["slur"] == "(":
            if slurred is not None:
                raise VidgenError(f"{where}: '(' at {pos} in {text!r} inside a slur that is still open: close the first with ')'")
            slurred = 0
            continue
        if match["slur"] == ")":
            if slurred is None:
                raise VidgenError(f"{where}: ')' at {pos} in {text!r} closes no slur: a slur is written (A4 - C5 -)")
            if slurred < 2:
                raise VidgenError(f"{where}: the slur closed at {pos} in {text!r} holds {'one note' if slurred else 'no note'}: a slur joins two or more notes, (A4 - C5 -)")
            if pending:
                raise VidgenError(f"{where}: [{' '.join(pending)}] before ')' in {text!r}: write the mark after the ')'")
            slurred = None
            continue
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
        if slurred is not None and (joining or step.kind in ("rest", "chord")):
            what = "a rest" if step.kind == "rest" else "a chord"
            raise VidgenError(f"{where}: {what} inside the slur at {match.start() + 1} in {text!r}: a slur joins single notes; close it with ')' before")
        if joining:
            if step.kind not in _JOINABLE[:3]:
                raise VidgenError(
                    f"{where}: {text[match.start()]!r} at {match.start() + 1} in {text!r} cannot follow '+', which joins notes, degrees or "
                    "voicing notes (e.g. v2+v3+v4, C4+E4)"
                )
            bars[-1][-1] = _join(bars[-1][-1], step)
            joining = False
        else:
            if pending:
                step, pending = replace(step, marks=tuple(pending)), []
            if slurred is not None and step.sounds:
                step = replace(step, slur=slurred > 0)
                slurred += 1
            bars[-1].append(step)
    if joining:
        raise VidgenError(f"{where}: {text!r} ends with '+' (it joins two notes in one step)")
    if slurred is not None:
        raise VidgenError(f"{where}: a slur opened with '(' is not closed in {text!r}: write ')' after its last note or hold")
    if any(not bar for bar in bars):
        raise VidgenError(f"{where}: an empty bar in {text!r} (two '|' in a row, or one at an end)")
    if bars[0][0].kind == "hold" and not lead_hold:
        raise VidgenError(f"{where}: {text!r} starts with '-' (a hold needs a note before it)")
    flat = [s for bar in bars for s in bar]
    for before, step in zip(flat, flat[1:]):
        if step.kind == "hold" and before.kind == "rest":
            raise VidgenError(f"{where}: '-' after '.' in {text!r}: a rest cannot be held (write '.' again)")
    if expressive:
        _read_dynamics(bars, pending, where, text)
    return tuple(tuple(bar) for bar in bars)


def _read_dynamics(bars: list[list[Step]], trailing: list[str], where: str, text: str) -> None:
    """The dynamics among the steps' marks, resolved in place: every step gets its level at
    its start and end and its burst; a step's ``marks`` keep the items that are no dynamics.
    ``trailing``: the items of a mark after the last step (the end of a hairpin)."""
    dynamics = _Dynamics(where, text)
    for b, bar in enumerate(bars):
        for k, step in enumerate(bar):
            start, end = b + k / len(bar), b + (k + 1) / len(bar)
            kept, burst = [], 0.0
            for item in step.marks:
                found = dynamics.read(item, start, step.sounds)
                if found is None:
                    if not _SETTING_ITEM.fullmatch(item):
                        raise dynamics.fail(f"[{item}] is not a mark: write a dynamic (pp p mp mf f ff, -6, p<, fp, sfz), a setting (stroke=pizzicato) or default")
                    kept.append(item)
                else:
                    burst += found
            if step.marks:
                bar[k] = replace(step, marks=tuple(kept), burst=burst)
            dynamics.cover(bar, k, start, end)
    for item in trailing:
        if dynamics.read(item, float(len(bars)), False) is None:
            raise dynamics.fail(f"[{item}] at the end belongs to no step: only a dynamic that ends a hairpin may stand there")
    if dynamics.hairpin is not None:
        raise dynamics.fail(f"the hairpin '{dynamics.hairpin[2]}' has no end: write the level it reaches in a mark after it (e.g. [f]; it may stand at the very end)")


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
