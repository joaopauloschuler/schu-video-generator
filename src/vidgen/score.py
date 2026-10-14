"""Composed music as notes (DESIGN.md §82): a :class:`Score` of parts played by General MIDI
instruments, timed in beats. Pure data and arithmetic; :mod:`vidgen.synth` plays it, and
:func:`write_midi` exports it as a Standard MIDI File (both need the ``music`` extra).

A *beat* is a quarter note throughout (MIDI's convention, whatever the time signature):
``tempo`` is in quarter notes per minute and a bar of 6/8 lasts 3 beats.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError

#: Ticks per beat of the exported MIDI file.
TICKS_PER_BEAT = 480
#: Bumped when the meaning of a score's fields changes, so cached renders are not reused.
FORMAT_VERSION = 1
#: Tonic names of the key signatures, by sharps (negative: flats) from -7 to 7.
_MAJOR_KEYS = ("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#")
_MINOR_KEYS = ("Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#")
_KEY = re.compile(r"^([A-G][#b]?) (major|minor)$")
_PITCH_CLASSES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise VidgenError(f"score: {message}")


@dataclass(frozen=True)
class Note:
    """One note: ``start`` and ``length`` in beats, ``pitch`` a MIDI key (a drum part: the GM
    percussion key, e.g. 36 kick, 38 snare, 42 closed hi-hat), ``velocity`` 1-127."""

    start: float
    length: float
    pitch: int
    velocity: int = 90

    def __post_init__(self) -> None:
        _check(self.start >= 0 and math.isfinite(self.start), f"note start {self.start} must be 0 or more beats")
        _check(self.length > 0 and math.isfinite(self.length), f"note length {self.length} must be above 0 beats")
        _check(0 <= self.pitch <= 127, f"note pitch {self.pitch} must be 0-127")
        _check(1 <= self.velocity <= 127, f"note velocity {self.velocity} must be 1-127")

    @property
    def end(self) -> float:
        """The beat where the note stops."""
        return self.start + self.length


@dataclass(frozen=True)
class Part:
    """One instrument's notes. ``program``: the General MIDI program 0-127 (0 piano, 24 nylon
    guitar, 48 strings, 73 flute...) or, for ``drums``, the drum kit (0 standard, 8 room,
    16 power, 24 electronic, 25 analogue, 32 jazz, 40 brushes, 48 orchestral). ``volume`` in dB,
    ``pan`` -1 (left) to 1 (right), ``reverb`` the share sent to the reverb, 0-1."""

    name: str
    notes: tuple[Note, ...]
    program: int = 0
    drums: bool = False
    volume: float = 0.0
    pan: float = 0.0
    reverb: float = 0.2

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(self.notes))
        _check(bool(self.name), "a part needs a name")
        _check(0 <= self.program <= 127, f"part {self.name!r}: program {self.program} must be 0-127")
        _check(-60 <= self.volume <= 12, f"part {self.name!r}: volume {self.volume} dB must be -60 to 12")
        _check(-1 <= self.pan <= 1, f"part {self.name!r}: pan {self.pan} must be -1 to 1")
        _check(0 <= self.reverb <= 1, f"part {self.name!r}: reverb {self.reverb} must be 0 to 1")

    @property
    def end(self) -> float:
        """The beat where the part's last note stops (0 without notes)."""
        return max((n.end for n in self.notes), default=0.0)


@dataclass(frozen=True)
class Section:
    """A named stretch of the score from beat ``start`` (to the next section or the end);
    ``tempo`` (quarter notes per minute) changes the tempo from there on."""

    name: str
    start: float
    tempo: float | None = None

    def __post_init__(self) -> None:
        _check(self.start >= 0, f"section {self.name!r}: start {self.start} must be 0 or more beats")
        _check(self.tempo is None or 20 <= self.tempo <= 300, f"section {self.name!r}: tempo {self.tempo} must be 20-300")


@dataclass(frozen=True)
class Score:
    """A piece of music: ``tempo`` (quarter notes per minute), ``time_signature`` (numerator,
    denominator), ``key`` (``"<tonic> major|minor"``, e.g. ``"F# minor"``, ``"Bb major"``), its
    parts and sections, and its ``length`` in beats (default: the last note's end rounded up
    to a whole bar). ``balance``: the renderer first sets every part to the same loudness, so a
    part's ``volume`` is its level against the others whatever its instrument's own level in the
    SoundFont (a SoundFont's instruments differ by up to ~40 dB)."""

    tempo: float
    parts: tuple[Part, ...]
    time_signature: tuple[int, int] = (4, 4)
    key: str = "C major"
    sections: tuple[Section, ...] = field(default=())
    length: float | None = None
    balance: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(self.parts))
        object.__setattr__(self, "sections", tuple(sorted(self.sections, key=lambda s: s.start)))
        object.__setattr__(self, "time_signature", tuple(self.time_signature))
        _check(20 <= self.tempo <= 300, f"tempo {self.tempo} must be 20-300 quarter notes per minute")
        numerator, denominator = self.time_signature
        _check(1 <= numerator <= 32 and denominator in (1, 2, 4, 8, 16, 32), f"time signature {numerator}/{denominator} is not valid")
        self.key_signature()  # checks the key
        names = [p.name for p in self.parts]
        _check(len(set(names)) == len(names), f"part names must differ: {names}")
        _check(self.length is None or self.length > 0, f"length {self.length} must be above 0 beats")

    @property
    def bar_beats(self) -> float:
        """Beats (quarter notes) per bar."""
        numerator, denominator = self.time_signature
        return numerator * 4 / denominator

    @property
    def length_beats(self) -> float:
        """The score's length in beats: ``length``, else the last note's end rounded up to a
        whole bar (at least one bar)."""
        if self.length is not None:
            return self.length
        last = max((p.end for p in self.parts), default=0.0)
        return max(1, math.ceil(last / self.bar_beats - 1e-9)) * self.bar_beats

    @property
    def length_seconds(self) -> float:
        """The score's length in seconds."""
        return self.seconds_at(self.length_beats)

    def tempo_changes(self) -> list[tuple[float, float]]:
        """``(beat, tempo)`` from beat 0 on, one entry per tempo change, in order."""
        changes = [(0.0, float(self.tempo))]
        for section in self.sections:
            if section.tempo is None:
                continue
            if section.start <= changes[-1][0]:
                changes[-1] = (changes[-1][0], float(section.tempo))
            else:
                changes.append((section.start, float(section.tempo)))
        return changes

    def seconds_at(self, beat: float) -> float:
        """The time in seconds of ``beat`` (following the tempo changes)."""
        seconds = 0.0
        changes = self.tempo_changes()
        for k, (start, tempo) in enumerate(changes):
            stop = changes[k + 1][0] if k + 1 < len(changes) else math.inf
            if beat <= start:
                break
            seconds += (min(beat, stop) - start) * 60.0 / tempo
        return seconds

    def key_signature(self) -> tuple[int, bool]:
        """``(sharps, minor)``: the number of sharps of ``key`` (negative: flats) and whether it
        is minor. :class:`VidgenError` for a key that has no standard signature (e.g. D# major)."""
        return key_signature(self.key)

    @property
    def tonic(self) -> int:
        """The key's tonic as a pitch class (0 = C ... 11 = B)."""
        return tonic_pitch_class(self.key.split()[0])

    def to_dict(self) -> dict[str, Any]:
        """The score as plain JSON data (what :meth:`fingerprint` hashes)."""
        return asdict(self)

    def fingerprint(self) -> str:
        """SHA-256 (hex) of the score's content and :data:`FORMAT_VERSION`."""
        text = json.dumps({"format": FORMAT_VERSION, "score": self.to_dict()}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def key_signature(key: str) -> tuple[int, bool]:
    """``(sharps, minor)`` of a key written ``"<tonic> major|minor"``; :class:`VidgenError` for
    another form or a key without a standard signature (e.g. D# major)."""
    match = _KEY.match(key)
    _check(match is not None, f"key {key!r} must be '<tonic> major' or '<tonic> minor' (e.g. 'F# minor', 'Bb major')")
    assert match is not None
    tonic, mode = match.groups()
    names = _MINOR_KEYS if mode == "minor" else _MAJOR_KEYS
    _check(tonic in names, f"key {key!r} has no standard key signature")
    return names.index(tonic) - 7, mode == "minor"


def tonic_pitch_class(name: str) -> int:
    """A note name (``C``, ``F#``, ``Bb``) as a pitch class (0 = C ... 11 = B)."""
    offset = {"#": 1, "b": -1}.get(name[1:], 0)
    return (_PITCH_CLASSES[name[0]] + offset) % 12


def _ticks(beat: float) -> int:
    return round(beat * TICKS_PER_BEAT)


def midi_volume(volume_db: float) -> int:
    """A part's ``volume`` (dB) as MIDI controller 7 (General MIDI: 40 log10(value / 127) dB;
    gains above 0 dB are written as 127)."""
    return max(0, min(127, round(127 * 10 ** (volume_db / 40))))


def midi_pan(pan: float) -> int:
    """A part's ``pan`` (-1 to 1) as MIDI controller 10 (0 left, 64 centre, 127 right)."""
    return max(0, min(127, round(64 + 63.5 * pan)))


def to_symusic(score: Score, parts: tuple[Part, ...] | None = None, controls: bool = True) -> Any:
    """A ``symusic.Score`` (ticks, :data:`TICKS_PER_BEAT` per beat) of ``score`` with ``parts``
    (default all): tempo changes, time and key signature, section markers, one track per part.
    ``controls`` adds each part's volume, pan and reverb send as MIDI controllers 7, 10 and 91
    (symusic's own render ignores them; :mod:`vidgen.synth` applies them itself)."""
    from vidgen.synth import require_symusic

    symusic = require_symusic()
    out = symusic.Score(TICKS_PER_BEAT)
    for beat, tempo in score.tempo_changes():
        out.tempos.append(symusic.Tempo(_ticks(beat), qpm=tempo))
    numerator, denominator = score.time_signature
    out.time_signatures.append(symusic.TimeSignature(0, numerator, denominator))
    sharps, minor = score.key_signature()
    out.key_signatures.append(symusic.KeySignature(0, sharps, int(minor)))
    for section in score.sections:
        out.markers.append(symusic.TextMeta(_ticks(section.start), section.name))
    for part in score.parts if parts is None else parts:
        track = symusic.Track(part.name, program=part.program, is_drum=part.drums)
        if controls:
            for number, value in ((7, midi_volume(part.volume)), (10, midi_pan(part.pan)), (91, round(127 * part.reverb))):
                track.controls.append(symusic.ControlChange(0, number, value))
        for note in part.notes:
            track.notes.append(symusic.Note(_ticks(note.start), max(1, _ticks(note.length)), note.pitch, note.velocity))
        out.tracks.append(track)
    return out


def write_midi(score: Score, path: Path) -> Path:
    """Write ``score`` as a Standard MIDI File (type 1) to ``path``; returns ``path``. Needs the
    ``music`` extra."""
    path.parent.mkdir(parents=True, exist_ok=True)
    to_symusic(score).dump_midi(str(path))
    return path
