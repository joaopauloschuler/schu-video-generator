"""Music theory for score files (DESIGN.md §93): note names, keys and modes, chords written as
Roman numerals or chord names, chord tones by degree, and close voicings."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from vidgen.errors import VidgenError

#: Scale steps (semitones above the tonic) of the modes a key may name.
MODES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
}
_NATURALS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
_NOTE = re.compile(r"^([A-G])([#b]?)(\d)$")
_PITCH = re.compile(r"^([A-G])([#b]?)")
_ROMAN = re.compile(r"^([b#]?)(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)")
_ROMAN_DEGREES = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}
#: Chord-name suffix words, longest first, and what each does to the chord (see :func:`_suffix`).
_SUFFIX_WORDS = (
    "maj13", "maj11", "maj9", "maj7", "add#11", "add11", "add13", "add9", "add2", "add4", "add6", "sus2", "sus4",
    "dim7", "dim", "aug", "min", "69", "6/9", "13", "11", "#11", "b13", "b9", "#9", "b5", "#5", "no3", "no5",
    "sus", "maj", "M7", "m", "9", "7", "6", "5", "°7", "°", "ø7", "ø", "+", "Δ",
)


def pitch_class(name: str) -> int:
    """``C`` 0 ... ``B`` 11, with ``#`` / ``b`` (``F#`` 6, ``Bb`` 10)."""
    letter, accidental = name[0], name[1:]
    return (_NATURALS[letter] + {"": 0, "#": 1, "b": -1}[accidental]) % 12


def note_number(text: str) -> int:
    """A note name with its octave as a MIDI number (``C4`` = 60, middle C; ``A4`` = 69)."""
    match = _NOTE.match(text.strip())
    if match is None:
        raise VidgenError(f"{text!r} is not a note: write a capital letter, an optional # or b and an octave, e.g. A4, C#5, Bb3 (C4 is middle C)")
    letter, accidental, octave = match.groups()
    return 12 * (int(octave) + 1) + _NATURALS[letter] + {"": 0, "#": 1, "b": -1}[accidental]


def note_name(midi: int, flats: bool = False) -> str:
    """A MIDI number as a note name (60 ``C4``)."""
    names = _FLAT_NAMES if flats else _SHARP_NAMES
    return f"{names[midi % 12]}{midi // 12 - 1}"


@dataclass(frozen=True)
class Key:
    """A key: its name (``A minor``), tonic pitch class and mode."""

    name: str
    tonic: int
    mode: str

    @property
    def scale(self) -> tuple[int, ...]:
        """The pitch classes of the key's scale, degree 1 to 7."""
        return tuple((self.tonic + step) % 12 for step in MODES[self.mode])

    @property
    def flats(self) -> bool:
        """Whether notes of this key are spelled with flats (F major, D minor, Bb...)."""
        offset = {"major": 0, "minor": 3, "dorian": -2, "phrygian": -4, "lydian": -5, "mixolydian": -7}[self.mode]
        return (self.tonic + offset) % 12 in (5, 10, 3, 8, 1, 6) or "b" in self.name.split()[0]


def parse_key(text: str) -> Key:
    """``A minor``, ``Am``, ``F# major``, ``Bb`` (a bare note is major), ``D dorian``."""
    words = str(text).replace("-", " ").split()
    if not words or _PITCH.match(words[0]) is None or len(words) > 2:
        raise VidgenError(f"key {text!r}: write a note and a mode, e.g. 'A minor', 'F# major', 'Bb', 'Em', 'D dorian' (modes: {', '.join(MODES)})")
    tonic_text = _PITCH.match(words[0]).group(0)  # type: ignore[union-attr]
    rest = words[0][len(tonic_text) :]
    if rest not in ("", "m") or (rest == "m" and len(words) > 1):
        raise VidgenError(f"key {text!r}: write a note and a mode, e.g. 'A minor', 'F# major', 'Bb', 'Em', 'D dorian'")
    mode = "minor" if rest == "m" else (words[1].lower() if len(words) > 1 else "major")
    mode = {"maj": "major", "min": "minor", "aeolian": "minor", "ionian": "major"}.get(mode, mode)
    if mode not in MODES:
        close = difflib.get_close_matches(mode, list(MODES), n=1, cutoff=0.6)
        guess = f"; did you mean '{tonic_text} {close[0]}'?" if close else ""
        raise VidgenError(f"key {text!r}: unknown mode {words[-1]!r}{guess} (modes: {', '.join(MODES)})")
    return Key(f"{tonic_text} {mode}", pitch_class(tonic_text), mode)


@dataclass(frozen=True)
class Chord:
    """A chord: as written (``symbol``), in letters (``name``), its root pitch class, its tones
    as semitones above the root (0 first, ascending, under 12) and its bass pitch class."""

    symbol: str
    name: str
    root: int
    intervals: tuple[int, ...]
    bass: int

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        return tuple((self.root + i) % 12 for i in self.intervals)


def _suffix(text: str, minor: bool, where: str) -> tuple[set[int], bool]:
    """The tones (semitones above the root) a chord suffix such as ``m7``, ``maj9``,
    ``7sus4``, ``(add9)``, ``m7b5`` or ``dim`` gives (``minor``: a lower-case numeral's triad),
    and whether the chord is minor."""
    third, fifth, seventh = (3 if minor else 4), 7, None
    extra: set[int] = set()
    dim = False
    rest = text.replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
    first = True
    while rest:
        word = next((w for w in _SUFFIX_WORDS if rest.startswith(w)), None)
        if word is None or (word == "m" and not first):
            raise VidgenError(
                f"{where}: cannot read {rest!r} in the chord: use m, maj7, m7, 7, 6, 9, add9, sus2, sus4, 7sus4, dim, m7b5, aug, "
                "#11, b9 (e.g. Am7, Fmaj7, Dm(add9), G7sus4, Bdim; Roman numerals: i, VI, iv7, V7, bVII, vii°)"
            )
        rest = rest[len(word) :]
        if word in ("m", "min"):
            if not first:
                raise VidgenError(f"{where}: 'm' (minor) must come right after the chord's root")
            third, minor = 3, True
        elif word in ("dim", "°"):
            third, fifth, dim, minor = 3, 6, True, True
        elif word in ("dim7", "°7"):
            third, fifth, seventh, dim, minor = 3, 6, 9, True, True
        elif word in ("ø", "ø7"):
            third, fifth, seventh, minor = 3, 6, 10, True
        elif word in ("aug", "+"):
            third, fifth = 4, 8
        elif word == "maj":
            pass
        elif word in ("maj7", "M7", "Δ"):
            seventh = 11
        elif word in ("maj9", "maj11", "maj13"):
            seventh = 11
            extra |= {2} | ({5} if word == "maj11" else set()) | ({9} if word == "maj13" else set())
        elif word == "7":
            seventh = 9 if dim else 10
        elif word in ("9", "11", "13"):
            seventh = seventh if seventh is not None else 10
            extra |= {2} | ({5} if word == "11" else set()) | ({9} if word == "13" else set())
        elif word == "6":
            extra.add(9)
        elif word in ("69", "6/9"):
            extra |= {9, 2}
        elif word == "5":
            third = None  # type: ignore[assignment]
        elif word in ("sus2",):
            third = 2
        elif word in ("sus4", "sus"):
            third = 5
        elif word in ("add9", "add2"):
            extra.add(2)
        elif word in ("add11", "add4"):
            extra.add(5)
        elif word in ("add13", "add6"):
            extra.add(9)
        elif word in ("add#11", "#11"):
            extra.add(6)
        elif word == "b9":
            extra.add(1)
        elif word == "#9":
            extra.add(3)
        elif word == "b13":
            extra.add(8)
        elif word == "b5":
            fifth = 6
        elif word == "#5":
            fifth = 8
        elif word == "no3":
            third = None  # type: ignore[assignment]
        elif word == "no5":
            fifth = None  # type: ignore[assignment]
        first = False
    tones = {0} | extra | {t for t in (third, fifth, seventh) if t is not None}
    return tones, minor


def parse_chord(symbol: str, key: Key, where: str = "progression") -> Chord:
    """A chord written as a Roman numeral of ``key`` (``i``, ``VI``, ``iv7``, ``V7sus4``,
    ``bVII``, ``vii°``; upper case major, lower case minor) or as a chord name (``Am``,
    ``Fmaj7``, ``Dm(add9)``, ``C/E``); ``/`` and a note puts that note in the bass, and after a
    numeral ``/3``, ``/5`` or ``/7`` puts that chord tone there."""
    text = str(symbol).strip()
    body, slash = text, None
    if "/" in text and not text.endswith("6/9"):
        body, slash = text.rsplit("/", 1)
    roman = _ROMAN.match(body)
    if roman is not None:
        accidental, numeral = roman.group(1), roman.group(2)
        degree = _ROMAN_DEGREES[numeral.lower()]
        root = (key.scale[degree] + {"": 0, "b": -1, "#": 1}[accidental]) % 12
        suffix = body[roman.end() :]
        if suffix.startswith("m") and not suffix.startswith("maj"):
            raise VidgenError(f"{where}: {text!r}: a Roman numeral shows minor by lower case (vi, not VIm)")
        tones, minor = _suffix(suffix, numeral.islower(), f"{where}: {text!r}")
        flats = key.flats or accidental == "b"
        name = (_FLAT_NAMES if flats else _SHARP_NAMES)[root] + ("m" if numeral.islower() and not suffix.startswith(("°", "ø", "dim")) else "") + suffix
    else:
        match = _PITCH.match(body)
        if match is None:
            raise VidgenError(
                f"{where}: {text!r} is not a chord: write a Roman numeral of the key (i, VI, iv7, V, bVII) or a chord name "
                "(Am, F, Cmaj7, G7sus4, Dm(add9), C/E)"
            )
        root = pitch_class(match.group(0))
        tones, minor = _suffix(body[match.end() :], False, f"{where}: {text!r}")
        flats = "b" in match.group(0)
        name = body
    intervals = tuple(sorted(tones))
    bass = root
    if slash is not None:
        if roman is not None and slash in ("3", "5", "7"):
            wanted = {"3": (4, 3, 5, 2), "5": (7, 6, 8), "7": (10, 11, 9)}[slash]
            found = next((i for i in wanted if i in tones), None)
            if found is None:
                raise VidgenError(f"{where}: {text!r}: the chord has no {slash}th to put in the bass")
            bass = (root + found) % 12
            name += "/" + (_FLAT_NAMES if flats else _SHARP_NAMES)[bass]
        elif _PITCH.fullmatch(slash):
            bass = pitch_class(slash)
            if roman is not None:
                name += "/" + slash
        else:
            raise VidgenError(f"{where}: {text!r}: after '/' write the bass note (C/E, Am/G; after a numeral also /3, /5, /7)")
    return Chord(text, name, root, intervals, bass)


#: Which semitones above the root can play each chord degree, in order of preference.
_DEGREE_TONES = {1: (0,), 2: (2, 1), 3: (4, 3), 4: (5, 6), 5: (7, 6, 8), 6: (9, 8), 7: (10, 11, 9)}
_DEGREE_DEFAULT = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 10}


def degree_interval(chord: Chord, key: Key, degree: int) -> int:
    """Semitones above the chord's root for chord degree ``degree`` (1 root, 3 third, 5 fifth,
    7 seventh, 2 / 9 ninth, 4 fourth, 6 sixth, 8 octave): the chord's own tone when it has one
    (a suspended chord's 3 is its 2nd or 4th), else the key's scale tone, else the plain
    interval."""
    octave, base = divmod(degree - 1, 7)
    base += 1
    tones = set(chord.intervals)
    fifth = next((t for t in _DEGREE_TONES[5] if t in tones), None)
    third = next((t for t in _DEGREE_TONES[3] if t in tones), None)
    taken = {fifth, third}
    candidates = [t for t in _DEGREE_TONES[base] if t in tones and (t not in taken or base in (3, 5))]
    if base == 3 and not candidates:
        candidates = [t for t in (5, 2) if t in tones]
    if base == 7 and fifth != 6:
        candidates = [t for t in candidates if t != 9]
    if candidates:
        interval = candidates[0]
    else:
        scale = {(pc - chord.root) % 12 for pc in key.scale}
        interval = next((t for t in _DEGREE_TONES[base] if t in scale), _DEGREE_DEFAULT[base])
    return interval + 12 * octave


def close_voicing(chord: Chord, octave: int) -> tuple[int, ...]:
    """The chord in close position, root first, its root in ``octave`` (MIDI numbers)."""
    base = 12 * (octave + 1) + chord.root
    return tuple(base + i for i in chord.intervals)


def led_voicing(chord: Chord, octave: int, previous: tuple[int, ...] | None) -> tuple[int, ...]:
    """The chord in close position with its lowest note in ``octave`` (C to B): root position
    first, then the inversion whose average pitch is nearest the previous chord's."""
    if previous is None:
        return close_voicing(chord, octave)
    target = sum(previous) / len(previous)
    best: tuple[int, ...] | None = None
    for k in range(len(chord.intervals)):
        rotated = chord.intervals[k:] + tuple(i + 12 for i in chord.intervals[:k])
        low = 12 * (octave + 1) + (chord.root + chord.intervals[k]) % 12
        notes = tuple(low + i - chord.intervals[k] for i in rotated)
        if best is None or abs(sum(notes) / len(notes) - target) < abs(sum(best) / len(best) - target) - 1e-9:
            best = notes
    assert best is not None
    return best
