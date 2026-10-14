"""Original music composed from a mood (DESIGN.md §83): ``music: {compose: {mood, key, tempo,
instruments, seed, bars}}`` becomes a :class:`~vidgen.score.Score` that :mod:`vidgen.synth` plays.
Pure and seeded: the same settings give the same notes.

A piece is a number of 4-bar *phrases* in a fixed form (A A B A, then C for the second
contrast): a phrase is a *question* (ending on the dominant: a half cadence) or an *answer*
(ending on the tonic: an authentic cadence), and the last bar turns back (tonic, then V7) so the
piece loops. Each section letter picks its own chord progression from the mood's, and its own
*motif* (rhythm cells and a melodic shape) that comes back varied. The melody puts chord tones on
the strong beats and fills between them with steps of the chord's scale; nothing is taken from a
known tune.
"""

from __future__ import annotations

import math
import random
import re
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from vidgen.errors import VidgenError
from vidgen.score import Note, Part, Score, Section, key_signature, tonic_pitch_class

#: The parts a composed piece can have, in score order.
ROLES: tuple[str, ...] = ("melody", "chords", "pad", "bass", "drums")
#: Volume (dB), pan and reverb send of a role the mood does not have by default.
_ROLE_DEFAULTS: dict[str, tuple[float, float, float]] = {
    "melody": (0.0, 0.1, 0.3),
    "chords": (-5.0, -0.3, 0.25),
    "pad": (-10.0, 0.25, 0.35),
    "bass": (-5.0, 0.0, 0.12),
    "drums": (-9.0, 0.0, 0.12),
}
#: Bounds of the settings.
TEMPO_RANGE = (40.0, 200.0)
BARS_RANGE = (4, 128)
DEFAULT_SEED = 1


# ----- instruments ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Instrument:
    """A General MIDI instrument by a friendly name: ``program`` (a drum kit's number when
    ``drums``), the range it plays well (MIDI keys) and what it sounds like."""

    name: str
    program: int
    low: int
    high: int
    words: str
    drums: bool = False


def _kit(name: str, program: int, words: str) -> Instrument:
    return Instrument(name, program, 0, 127, words, drums=True)


#: Friendly instrument names (``instruments: {melody: flute}``) → General MIDI. Not offered:
#: pizzicato strings (45) and xylophone (13), which symusic 0.5.9 plays as a 5 ms click with
#: GeneralUser GS 2.0.3, and bright piano (1), which sounds the same as the piano there.
INSTRUMENTS: dict[str, Instrument] = {
    i.name: i
    for i in (
        Instrument("piano", 0, 21, 108, "acoustic grand piano: warm and clear, each note fading slowly"),
        Instrument("electric_piano", 4, 28, 103, "electric piano: mellow, bell-like, smooth sustain"),
        Instrument("harpsichord", 6, 29, 89, "harpsichord: plucked, thin, old-fashioned, no loud or soft"),
        Instrument("celesta", 8, 60, 108, "celesta: small soft bells, sparkly and magical"),
        Instrument("glockenspiel", 9, 72, 108, "glockenspiel: bright metal bars, high and ringing"),
        Instrument("music_box", 10, 60, 96, "music box: tiny plucked metal tines, delicate"),
        Instrument("vibraphone", 11, 53, 89, "vibraphone: soft mallets on metal bars, a warm ring with a slow shimmer"),
        Instrument("marimba", 12, 45, 96, "marimba: soft mallets on wooden bars, round and short"),
        Instrument("accordion", 21, 53, 89, "accordion: reedy, folk-like, held notes"),
        Instrument("guitar", 24, 40, 83, "nylon-string acoustic guitar: soft, warm, plucked"),
        Instrument("steel_guitar", 25, 40, 83, "steel-string acoustic guitar: brighter, for strumming"),
        Instrument("clean_guitar", 27, 40, 86, "clean electric guitar: smooth and light"),
        Instrument("bass", 32, 28, 60, "plucked upright bass: round, woody low notes"),
        Instrument("electric_bass", 33, 28, 62, "electric bass played with the fingers: firm, smooth low notes"),
        Instrument("synth_bass", 38, 24, 62, "synthesizer bass: electronic and punchy"),
        Instrument("violin", 40, 55, 100, "solo violin: singing, expressive"),
        Instrument("viola", 41, 48, 88, "solo viola: darker and warmer than a violin"),
        Instrument("cello", 42, 36, 76, "solo cello: warm, deep, singing"),
        Instrument("contrabass", 43, 28, 60, "bowed double bass: dark, low, held"),
        Instrument("tremolo_strings", 44, 28, 100, "strings in tremolo: a nervous, shimmering hush (suspense)"),
        Instrument("harp", 46, 24, 103, "concert harp: plucked, glassy, flowing"),
        Instrument("strings", 48, 28, 100, "string section: full, smooth, held"),
        Instrument("slow_strings", 49, 28, 100, "slow string section: very soft attack, gentle swells"),
        Instrument("choir", 52, 48, 84, "choir singing 'aah': soft wordless voices"),
        Instrument("trumpet", 56, 52, 84, "trumpet: bright, heroic brass"),
        Instrument("trombone", 57, 40, 72, "trombone: broad, round brass, can be comic"),
        Instrument("tuba", 58, 28, 58, "tuba: big, low, round brass (oom-pah)"),
        Instrument("muted_trumpet", 59, 52, 82, "muted trumpet: nasal, soft and sly"),
        Instrument("horn", 60, 41, 77, "French horn: warm, noble, soft-edged brass"),
        Instrument("brass", 61, 40, 84, "brass section: bold chords"),
        Instrument("alto_sax", 65, 49, 81, "alto saxophone: smooth, jazzy"),
        Instrument("oboe", 68, 58, 91, "oboe: reedy, plaintive, pastoral"),
        Instrument("bassoon", 70, 34, 75, "bassoon: low reedy woodwind, often comic"),
        Instrument("clarinet", 71, 50, 91, "clarinet: smooth, woody and agile; playful or gentle"),
        Instrument("piccolo", 72, 74, 108, "piccolo: very high, bright, chirpy"),
        Instrument("flute", 73, 60, 96, "flute: airy, light, gentle"),
        Instrument("recorder", 74, 60, 93, "recorder: simple, pure, childlike"),
        Instrument("pan_flute", 75, 60, 96, "pan flute: breathy and airy"),
        Instrument("ocarina", 79, 60, 91, "ocarina: round, pure, whistle-like"),
        Instrument("warm_pad", 89, 36, 96, "warm synthesizer pad: soft, wide, held background"),
        Instrument("kalimba", 108, 60, 91, "kalimba (thumb piano): soft plucked metal tines"),
        Instrument("steel_drums", 114, 52, 88, "steel drums: bright, sunny, Caribbean"),
        _kit("drums", 0, "standard drum kit: kick, snare, hi-hat, cymbals, woodblocks, shakers"),
        _kit("room_drums", 8, "room drum kit: a slightly more natural, roomy standard kit"),
        _kit("jazz_drums", 32, "jazz drum kit: lighter, softer kick and snare"),
        _kit("soft_drums", 40, "brush kit: brushes on the snare, soft and gentle"),
        _kit("orchestral_drums", 48, "orchestral percussion: concert bass drum, snare drum, cymbals"),
    )
}


# ----- keys and chords ------------------------------------------------------------------------------

_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_MINOR = (0, 2, 3, 5, 7, 8, 10)
_LETTERS = "CDEFGAB"
_NATURALS = (0, 2, 4, 5, 7, 9, 11)
_ROMANS = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}
_CHORD = re.compile(
    r"^(?P<acc>[b#]?)(?P<roman>VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)(?P<quality>°|ø|\+)?"
    r"(?P<ext>maj7|7|6|9|sus2|sus4|add9)?(?:/(?P<inversion>[35]))?$"
)


@dataclass(frozen=True)
class Key:
    """A key: its name (``"D major"``), tonic pitch class and letter (0-6 for C-B), and mode."""

    name: str
    tonic: int
    letter: int
    minor: bool

    @property
    def scale(self) -> tuple[int, ...]:
        """The pitch classes of the key's scale (natural minor in minor), degree 0 to 6."""
        return tuple((self.tonic + step) % 12 for step in (_MINOR if self.minor else _MAJOR))

    def spell(self, degree: int, pitch_class: int) -> str:
        """The note name of ``pitch_class`` written on scale degree ``degree`` (``F#``, ``Bb``)."""
        letter = (self.letter + degree) % 7
        accidental = {0: "", 1: "#", 2: "##", 11: "b", 10: "bb"}.get((pitch_class - _NATURALS[letter]) % 12)
        return _NAMES[pitch_class] if accidental is None else _LETTERS[letter] + accidental


@dataclass(frozen=True)
class Chord:
    """A chord of a key from its Roman numeral (``symbol``): its tones as ``(scale degree, pitch
    class)``, root first, its lowest pitch class (``bass``) and its name in letters (``Bm7``)."""

    symbol: str
    name: str
    tones: tuple[tuple[int, int], ...]
    bass: int

    @property
    def root(self) -> int:
        return self.tones[0][1]

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        return tuple(pc for _, pc in self.tones)

    def scale(self, key: Key) -> tuple[int, ...]:
        """The key's scale with the chord's tones put on their degrees (e.g. the raised leading
        tone over V in a minor key): the notes a melody passes through over this chord."""
        pcs = list(key.scale)
        for degree, pc in self.tones:
            pcs[degree] = pc
        return tuple(pcs)


def parse_key(text: str, minor: bool) -> Key:
    """``"D"``, ``"D major"`` or ``"F# minor"`` as a :class:`Key` (a bare note takes the mode
    ``minor``); :class:`VidgenError` for anything else or a key without a standard signature."""
    words = text.split()
    name = f"{words[0]} {'minor' if minor else 'major'}" if len(words) == 1 else " ".join(words)
    try:
        _, is_minor = key_signature(name)
    except VidgenError:
        raise VidgenError(f"key {text!r} must be a note with major or minor, e.g. 'D major', 'F# minor', 'Bb' (standard key signatures only)") from None
    tonic = name.split()[0]
    return Key(name, tonic_pitch_class(tonic), _LETTERS.index(tonic[0]), is_minor)


def parse_chord(symbol: str, key: Key) -> Chord:
    """A Roman numeral of ``key`` as a :class:`Chord`. Upper case is major, lower case minor; then
    ``°`` (diminished), ``ø`` (half-diminished 7th) or ``+`` (augmented); ``7`` (dominant or minor
    7th), ``maj7``, ``6``, ``9``, ``sus2``, ``sus4`` or ``add9``; ``/3`` or ``/5`` puts that tone
    in the bass; ``b`` / ``#`` in front lowers / raises the root (``bVII``)."""
    match = _CHORD.match(symbol)
    if match is None:
        raise VidgenError(f"compose: chord {symbol!r} is not a Roman numeral such as I, vi, V7, ii7, bVII, IV/3")
    roman, quality, ext = match["roman"], match["quality"], match["ext"]
    degree = _ROMANS[roman.lower()]
    root = (key.scale[degree] + {"b": -1, "#": 1, "": 0}[match["acc"]]) % 12
    upper = roman.isupper()
    third, fifth = {"°": (3, 6), "ø": (3, 6), "+": (4, 8)}.get(quality or "", (4 if upper else 3, 7))
    intervals = [(0, 0), (2, third), (4, fifth)]
    if ext == "sus2":
        intervals[1] = (1, 2)
    elif ext == "sus4":
        intervals[1] = (3, 5)
    if ext in ("7", "9") or quality == "ø":
        intervals.append((6, 9 if quality == "°" else 10))
    elif ext == "maj7":
        intervals.append((6, 11))
    elif ext == "6":
        intervals.append((5, 9))
    if ext == "9":
        intervals = [i for i in intervals if i[0] != 4] + [(1, 2)]
    elif ext == "add9":
        intervals.append((1, 2))
    tones = tuple(((degree + step) % 7, (root + semis) % 12) for step, semis in intervals)
    bass = tones[{"3": 1, "5": 2}[match["inversion"]]] if match["inversion"] else tones[0]
    return Chord(symbol, _chord_name(key, degree, root, upper, quality, ext, bass), tones, bass[1])


def _chord_name(key: Key, degree: int, root: int, upper: bool, quality: str | None, ext: str | None, bass: tuple[int, int]) -> str:
    minor = not upper and quality is None
    if quality == "°":
        kind = "dim7" if ext == "7" else "dim"
    elif quality == "ø":
        kind = "m7b5"
    elif quality == "+":
        kind = "aug"
    elif ext in ("sus2", "sus4"):
        kind = ext
    else:
        kind = ("m" if minor else "") + {None: "", "7": "7", "maj7": "maj7", "6": "6", "9": "9", "add9": "add9"}[ext]
    name = key.spell(degree, root) + kind
    if bass[1] != root:
        name += "/" + key.spell(bass[0], bass[1])
    return name


# ----- moods ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Progression:
    """A 4-bar question (ending on V) and its 4-bar answer (ending on I); each bar is one to four
    Roman numerals separated by spaces (several: the bar is shared)."""

    question: tuple[str, str, str, str]
    answer: tuple[str, str, str, str]


@dataclass(frozen=True)
class RoleDefault:
    """A mood's default instrument for a role, with its volume (dB), pan and reverb send."""

    instrument: str
    volume: float
    pan: float
    reverb: float


@dataclass(frozen=True)
class Mood:
    """A mood's musical defaults. ``cells``: one-bar melody rhythms (durations in beats, ``rX`` a
    rest); ``half`` / ``full``: the last bar of a question / answer; ``turn``: the piece's last
    bar (a tonic note, then a pickup back to the start). ``articulation``: the share of each melody
    note's slot it sounds (1 legato, 0.55 staccato). ``bass_low`` / ``chords_low``: the lowest
    root of the bass / lowest note of the chords' voicings (MIDI keys)."""

    name: str
    family: str
    character: str
    use: str
    key: str
    tempo: float
    meter: int
    bars: int
    themes: tuple[Progression, ...]
    contrasts: tuple[Progression, ...]
    melody_range: tuple[int, int]
    melody_words: str
    cells: tuple[str, ...]
    half: str
    full: str
    turn: str
    articulation: float
    chords: str
    bass: str
    drums: str
    roles: Mapping[str, RoleDefault]
    bed: str
    bass_low: int = 36
    chords_low: int = 55

    @property
    def minor(self) -> bool:
        return self.key.endswith("minor")


def _p(question: str, answer: str) -> Progression:
    q, a = (tuple(part.strip() for part in text.split("|")) for text in (question, answer))
    return Progression(q, a)  # type: ignore[arg-type]


def _roles(**roles: tuple[str, float, float, float]) -> dict[str, RoleDefault]:
    return {role: RoleDefault(*value) for role, value in roles.items()}


#: Chord accompaniment patterns, in words.
CHORD_PATTERNS: dict[str, str] = {
    "pad": "held chords, one per chord change",
    "block": "struck chords on beats 1 and 3",
    "arpeggio": "broken chords in flowing eighth notes, up and down",
    "broken": "Alberti-style broken chords in eighth notes (low, high, middle, high)",
    "oompah": "short chords on the off-beats (beats 2 and 4; 2 and 3 in 3/4)",
    "ostinato": "a repeated staccato eighth-note figure on the root, fifth and octave",
    "strum": "strummed chords in a syncopated pop rhythm",
}
#: Bass patterns, in words.
BASS_PATTERNS: dict[str, str] = {
    "sustain": "each chord's root held",
    "half": "roots on beats 1 and 3 (beat 1 in 3/4)",
    "root_fifth": "root on beat 1, fifth on beat 3 (oom-pah)",
    "walking": "a walking line in quarter notes leading into each next chord",
    "pulse": "steady eighth notes on the root",
    "pop": "a syncopated root, fifth and octave pattern",
}


@dataclass(frozen=True)
class DrumPattern:
    """A one-bar drum pattern in 4/4 (``hits``: beat, GM drum key, velocity), the phrase-end fill
    that replaces it from ``fill_from`` on, whether a cymbal marks each new section, and the
    keys a 3/4 bar uses (kick on 1, ``backbeat`` on 2 and 3, ``tick`` in eighths)."""

    words: str
    hits: tuple[tuple[float, int, int], ...]
    fill: tuple[tuple[float, int, int], ...]
    fill_from: float
    crash: bool
    backbeat: int
    tick: int | None


def _eighths(key: int, on: int, off: int, beats: int = 4) -> tuple[tuple[float, int, int], ...]:
    return tuple((k / 2, key, on if k % 2 == 0 else off) for k in range(2 * beats))


#: Drum patterns, by name.
DRUM_PATTERNS: dict[str, DrumPattern] = {
    "light": DrumPattern(
        "kick on 1 and 3, a soft side stick on 2 and 4, quiet hi-hat eighths",
        ((0, 36, 70), (2, 36, 60), (1, 37, 50), (3, 37, 50), *_eighths(42, 40, 30)),
        ((3, 37, 55), (3.5, 37, 48), (3.75, 37, 44)), 3.0, False, 37, 42,
    ),
    "shaker": DrumPattern(
        "a soft shaker (cabasa) in eighth notes, a light kick on 1, claves on the 'and' of 2 and on 4",
        ((0, 36, 55), (1.5, 75, 35), (3, 75, 35), *_eighths(69, 62, 46)),
        ((3, 75, 40), (3.5, 75, 36), (3.75, 75, 42)), 3.0, False, 75, 69,
    ),
    "pop": DrumPattern(
        "a pop beat: kick on 1, the 'and' of 2 and 3, snare on 2 and 4, hi-hat eighths, a cymbal at each new section",
        ((0, 36, 85), (1.5, 36, 60), (2, 36, 78), (1, 38, 80), (3, 38, 80), *_eighths(42, 55, 40)),
        ((3, 38, 70), (3.25, 38, 60), (3.5, 38, 76), (3.75, 38, 86)), 3.0, True, 38, 42,
    ),
    "toybox": DrumPattern(
        "high and low woodblocks answering each other, a soft kick on 1 and 3, a faint shaker",
        ((0, 36, 62), (2, 36, 52), (1, 76, 60), (3, 76, 60), (1.5, 77, 45), (3.5, 77, 45), *_eighths(69, 40, 30)),
        ((3, 76, 62), (3.25, 77, 52), (3.5, 76, 62), (3.75, 77, 58)), 3.0, False, 76, 69,
    ),
    "heartbeat": DrumPattern(
        "a low bass drum like a heartbeat (two beats on 1 and on 3), a snare drum rising at each phrase end",
        ((0, 36, 80), (0.5, 36, 55), (2, 36, 74), (2.5, 36, 50)),
        ((3, 38, 38), (3.25, 38, 44), (3.5, 38, 52), (3.75, 38, 62)), 3.0, False, 36, None,
    ),
    "march": DrumPattern(
        "a march: bass drum on 1 and 3, snare on 2 and 4 with a short pickup, a cymbal at each new section, a snare roll at phrase ends",
        ((0, 36, 80), (2, 36, 70), (1, 38, 70), (3, 38, 70), (3.5, 38, 50), (3.75, 38, 56)),
        tuple((2 + k / 4, 38, 45 + 3 * k) for k in range(8)), 2.0, True, 38, None,
    ),
    "brushes": DrumPattern(
        "brushes: a soft kick on 1, brushed snare on 2 and 4, a pedal hi-hat",
        ((0, 36, 50), (1, 38, 40), (3, 38, 40), (1, 44, 34), (3, 44, 34)),
        ((3, 38, 45), (3.5, 38, 38)), 3.0, False, 38, None,
    ),
}


#: The built-in moods: four for explainers, four for cartoons.
MOODS: dict[str, Mood] = {
    m.name: m
    for m in (
        Mood(
            "calm", "explainer", "calm, warm and unhurried",
            "calm explainers, reflective or serious topics, long narration",
            "D major", 72, 4, 16,
            themes=(_p("I | vi | IV | V", "I | vi | ii7 V | I"), _p("I | iii | IV | Vsus4 V", "I | iii | IV V | I")),
            contrasts=(_p("IV | I/3 | ii7 | V", "IV | I/3 | ii7 V | I"), _p("vi | IV | I | V", "vi | IV | V | I")),
            melody_range=(69, 86), melody_words="a slow, singing tune in half and quarter notes, legato",
            cells=("2 2", "3 1", "1 1 2", "2 1 1", "1.5 .5 2"), half="3 r1", full="4", turn="2 r1 1",
            articulation=0.95, chords="arpeggio", bass="sustain", drums="brushes",
            roles=_roles(melody=("piano", 0, 0.1, 0.3), chords=("harp", -4, -0.35, 0.3), pad=("slow_strings", -9, 0.3, 0.4), bass=("cello", -5, 0.0, 0.2)),
            bed="calm", bass_low=38,
        ),
        Mood(
            "focused", "explainer", "focused and forward-moving, steady but not dramatic",
            "tech and product explainers, step-by-step walkthroughs, data stories",
            "A minor", 96, 4, 16,
            themes=(_p("i | VI | III | VII V", "i | VI | iv V | i"), _p("i | iv | VI | V", "i | iv | VI V | i")),
            contrasts=(_p("VI | VII | III | V", "VI | VII | iv V | i"), _p("iv | VI | III | V", "iv | VI | V | i")),
            melody_range=(64, 81), melody_words="a sparse tune of quarter and half notes with a few eighths",
            cells=("1 1 2", "2 1 1", "1 .5 .5 2", "1.5 .5 1 1", "r1 1 1 1"), half="3 r1", full="3 r1", turn="2 r1 1",
            articulation=0.85, chords="arpeggio", bass="pulse", drums="light",
            roles=_roles(melody=("vibraphone", 0, 0.15, 0.3), chords=("guitar", -4, -0.3, 0.2), pad=("warm_pad", -10, 0.25, 0.35),
                         bass=("electric_bass", -5, 0.0, 0.1), drums=("soft_drums", -10, 0.0, 0.12)),
            bed="pulse", bass_low=33,
        ),
        Mood(
            "curious", "explainer", "curious and light, a little quirky, asking questions",
            "science and how-it-works explainers, puzzles, discoveries",
            "F major", 108, 4, 16,
            themes=(_p("I | II | IV | V", "I | II | IV V | I"), _p("I | vi | II | V", "I | vi | ii7 V | I")),
            contrasts=(_p("IV | bVII | I | V", "IV | bVII | ii V | I"), _p("ii7 | iii | IV | V", "ii7 | iii | IV V | I")),
            melody_range=(65, 84), melody_words="short, detached (staccato) notes in eighths and quarters with little rests",
            cells=(".5 .5 1 r1 1", "1 .5 .5 1 1", ".5 .5 .5 .5 2", "1 r.5 .5 2", "1 1 .5 .5 1"), half="2 r2", full="2 r2", turn="1 r1 .5 .5 1",
            articulation=0.6, chords="oompah", bass="root_fifth", drums="shaker",
            roles=_roles(melody=("flute", 0, 0.15, 0.25), chords=("harp", -5, -0.3, 0.2), bass=("bass", -5, 0.0, 0.1), drums=("drums", -11, 0.0, 0.1)),
            bed="bright",
        ),
        Mood(
            "upbeat", "explainer", "upbeat, optimistic and friendly",
            "launches, tutorials, upbeat social clips, positive results",
            "G major", 116, 4, 16,
            themes=(_p("I | V | vi | IV V", "I | V | IV V | I"), _p("I | IV | vi | V", "I | IV | ii V | I")),
            contrasts=(_p("IV | I/3 | IV | V", "IV | I/3 | ii V | I"), _p("IV | V | iii | vi V", "IV | V | ii7 V | I")),
            melody_range=(67, 86), melody_words="a bouncy, syncopated tune in eighths and quarters",
            cells=("1 .5 .5 1 1", ".5 .5 1 .5 .5 1", "1.5 .5 1.5 .5", "1 1 .5 .5 1", ".5 1 .5 2"), half="3 r1", full="2 r2", turn="2 r.5 .5 .5 .5",
            articulation=0.8, chords="strum", bass="pop", drums="pop",
            roles=_roles(melody=("marimba", 0, 0.1, 0.25), chords=("steel_guitar", -4, -0.35, 0.18), pad=("strings", -11, 0.3, 0.3),
                         bass=("electric_bass", -4, 0.0, 0.08), drums=("drums", -6, 0.0, 0.1)),
            bed="bright",
        ),
        Mood(
            "playful", "cartoon", "playful, bouncy and mischievous",
            "cartoons and children's stories, comic or light-hearted scenes",
            "C major", 132, 4, 24,
            themes=(_p("I | IV | I | V7", "I | IV | V7 | I"), _p("I | vi | ii | V7", "I | vi | ii V7 | I")),
            contrasts=(_p("IV | I | II7 | V7", "IV | I | ii V7 | I"), _p("vi | II7 | ii | V7", "vi | II7 | V7 | I")),
            melody_range=(69, 88), melody_words="hopping staccato eighths and quarters with rests, little runs",
            cells=(".5 .5 .5 .5 1 1", "1 .5 .5 1 r1", ".5 .5 1 .5 .5 1", "1 1 .5 .5 r1", ".75 .25 .75 .25 2"), half="2 r2", full="1 r1 1 r1", turn="1 r1 .5 .5 .5 .5",
            articulation=0.55, chords="oompah", bass="root_fifth", drums="toybox",
            roles=_roles(melody=("clarinet", 0, 0.2, 0.2), chords=("marimba", -5, -0.3, 0.2), bass=("tuba", -4, 0.0, 0.12), drums=("drums", -8, 0.0, 0.1)),
            bed="cartoon", bass_low=34,
        ),
        Mood(
            "sleepy", "cartoon", "sleepy, tender and dreamy, a waltz-time lullaby",
            "bedtime stories, night scenes, soft or sentimental moments, endings",
            "F major", 66, 3, 16,
            themes=(_p("I | vi | IV | V", "I | vi | ii V7 | I"), _p("I | iii | IV | V7", "I | iii | IV V7 | I")),
            contrasts=(_p("IV | I | ii7 | V", "IV | I | ii7 V7 | I"), _p("vi | iii | IV | V", "vi | iii | IV V7 | I")),
            melody_range=(72, 86), melody_words="a gentle tune in quarter, dotted and half notes",
            cells=("2 1", "3", "1 1 1", "1.5 .5 1", "1 2"), half="3", full="3", turn="2 .5 .5",
            articulation=1.0, chords="arpeggio", bass="half", drums="brushes",
            roles=_roles(melody=("celesta", 0, 0.15, 0.4), chords=("harp", -4, -0.3, 0.35), pad=("slow_strings", -9, 0.25, 0.45), bass=("bass", -7, 0.0, 0.2)),
            bed="lullaby",
        ),
        Mood(
            "tense", "cartoon", "tense and suspenseful, sneaking and waiting",
            "suspense, a chase about to start, sneaking, a mystery, a problem before its solution",
            "D minor", 104, 4, 16,
            themes=(_p("i | i | VI | V", "i | VI | iv V | i"), _p("i | bII | i | V", "i | bII | V | i")),
            contrasts=(_p("iv | i | VI | V", "iv | i | iv V | i"), _p("VI | iv | ii° | V", "VI | iv | ii° V | i")),
            melody_range=(62, 77), melody_words="a low, sparse tune of long notes and short sighs",
            cells=("2 2", "3 1", "1 1 2", "r1 3", "1.5 .5 2"), half="3 r1", full="3 r1", turn="2 r1 1",
            articulation=0.9, chords="ostinato", bass="half", drums="heartbeat",
            roles=_roles(melody=("clarinet", 0, 0.15, 0.3), chords=("piano", -3, -0.25, 0.2), pad=("tremolo_strings", -8, 0.3, 0.35),
                         bass=("contrabass", -5, 0.0, 0.15), drums=("orchestral_drums", -7, 0.0, 0.2)),
            bed="pulse", bass_low=33, chords_low=48,
        ),
        Mood(
            "triumphant", "cartoon", "triumphant and heroic, a bright fanfare",
            "victories, solved problems, grand reveals, finales",
            "Bb major", 112, 4, 16,
            themes=(_p("I | IV | I | V", "I | IV | V | I"), _p("I | vi | IV | V", "I | vi | IV V | I")),
            contrasts=(_p("bVI | bVII | I | V", "bVI | bVII | IV V | I"), _p("vi | iii | IV | V", "vi | iii | IV V | I")),
            melody_range=(65, 84), melody_words="a fanfare of dotted rhythms and held notes",
            cells=("1.5 .5 2", "1 .5 .5 1 1", ".75 .25 .75 .25 2", "1 1 2", "2 1.5 .5"), half="3 r1", full="3 r1", turn="2 r1 .5 .5",
            articulation=0.85, chords="block", bass="root_fifth", drums="march",
            roles=_roles(melody=("trumpet", 0, 0.1, 0.3), chords=("brass", -4, -0.3, 0.3), pad=("strings", -8, 0.3, 0.35),
                         bass=("tuba", -5, 0.0, 0.15), drums=("orchestral_drums", -6, 0.0, 0.25)),
            bed="bright", bass_low=34,
        ),
    )
}


# ----- settings ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Voice:
    """A part of a composed piece: its role, instrument, volume (dB), pan and reverb send."""

    role: str
    instrument: Instrument
    volume: float
    pan: float
    reverb: float


def unknown_name(kind: str, name: str, known: Sequence[str]) -> str:
    """``unknown mood 'calmm'; did you mean 'calm'? moods: calm, focused, ...``."""
    from vidgen.cartoon.poses import unknown_name_message

    return unknown_name_message(kind, name, known)


def _instrument_choice(role: str, value: Any) -> tuple[str | None, dict[str, float]]:
    """``(instrument name or None, overrides)`` of one ``instruments:`` entry."""
    if isinstance(value, str):
        return value, {}
    if isinstance(value, Mapping):
        extra = {k: float(value[k]) for k in ("volume", "pan", "reverb") if value.get(k) is not None}
        return value.get("instrument"), extra
    raise VidgenError(f"instruments.{role}: give an instrument name, none, or {{instrument, volume, pan, reverb}}")


def resolve_voices(mood: Mood, instruments: Mapping[str, Any] | None = None) -> tuple[Voice, ...]:
    """The parts of a piece: the mood's defaults changed by ``instruments`` (role → name, ``none``
    / ``None`` to leave the role out, or ``{instrument, volume, pan, reverb}``); in
    :data:`ROLES` order. :class:`VidgenError` for an unknown role or instrument, or a drum kit
    outside ``drums`` (and the reverse)."""
    voices: dict[str, Voice] = {
        role: Voice(role, INSTRUMENTS[d.instrument], d.volume, d.pan, d.reverb) for role, d in mood.roles.items()
    }
    for role, value in (instruments or {}).items():
        if role not in ROLES:
            raise VidgenError(f"instruments: {unknown_name('role', role, ROLES)}")
        if value is None or value == "none":
            voices.pop(role, None)
            continue
        name, extra = _instrument_choice(role, value)
        base = voices.get(role)
        if name is not None and name not in INSTRUMENTS:
            raise VidgenError(f"instruments.{role}: {unknown_name('instrument', name, list(INSTRUMENTS))} (vidgen list-music)")
        if name is None and base is None:
            raise VidgenError(f"instruments.{role}: mood '{mood.name}' has no {role} by default; name an instrument")
        instrument = INSTRUMENTS[name] if name is not None else base.instrument  # type: ignore[union-attr]
        if instrument.drums != (role == "drums"):
            hint = "a drum kit (drums, soft_drums, ...)" if role == "drums" else "an instrument, not a drum kit"
            raise VidgenError(f"instruments.{role}: {instrument.name} does not fit; {role} needs {hint}")
        if base is None:
            volume, pan, reverb = _ROLE_DEFAULTS[role]
            base = Voice(role, instrument, volume, pan, reverb)
        for name_, value_ in extra.items():
            bounds = {"volume": (-60, 12), "pan": (-1, 1), "reverb": (0, 1)}[name_]
            if not bounds[0] <= value_ <= bounds[1]:
                raise VidgenError(f"instruments.{role}.{name_}: {value_:g} must be {bounds[0]} to {bounds[1]}")
        voices[role] = replace(base, instrument=instrument, **extra)
    return tuple(voices[role] for role in ROLES if role in voices)


def find_mood(name: str) -> Mood:
    """The mood ``name``; :class:`VidgenError` with a did-you-mean otherwise."""
    if name not in MOODS:
        raise VidgenError(f"{unknown_name('mood', name, list(MOODS))} (vidgen list-music)")
    return MOODS[name]


def mood_key(mood: Mood, key: str | None) -> Key:
    """The piece's key: ``key`` (a note, or a note with the mood's mode), else the mood's."""
    if key is None:
        return parse_key(mood.key, mood.minor)
    found = parse_key(key, mood.minor)
    if found.minor != mood.minor:
        mode = "minor" if mood.minor else "major"
        tonic = key.split()[0]
        raise VidgenError(f"key {key!r}: mood '{mood.name}' is written for a {mode} key; write '{tonic} {mode}' (or just '{tonic}')")
    return found


def settings_problems(
    mood: str, key: str | None = None, tempo: float | None = None, instruments: Mapping[str, Any] | None = None, bars: int | None = None
) -> list[str]:
    """What is wrong with these compose settings (empty: they compose)."""
    problems: list[str] = []
    try:
        found = find_mood(mood)
    except VidgenError as exc:
        return [str(exc)]
    for check in (lambda: mood_key(found, key), lambda: resolve_voices(found, instruments)):
        try:
            check()
        except VidgenError as exc:
            problems.append(str(exc))
    if tempo is not None and not TEMPO_RANGE[0] <= tempo <= TEMPO_RANGE[1]:
        problems.append(f"tempo {tempo:g} must be {TEMPO_RANGE[0]:g} to {TEMPO_RANGE[1]:g} BPM")
    if bars is not None and (bars % 4 or not BARS_RANGE[0] <= bars <= BARS_RANGE[1]):
        problems.append(f"bars {bars} must be a multiple of 4 from {BARS_RANGE[0]} to {BARS_RANGE[1]}")
    return problems


# ----- the plan: phrases, sections, chords --------------------------------------------------------


@dataclass(frozen=True)
class _Span:
    start: float  # beat within the bar
    length: float
    chord: Chord


@dataclass(frozen=True)
class _Bar:
    index: int
    start: float  # beat of the piece
    spans: tuple[_Span, ...]
    phrase: int
    position: int  # 0-3 within the phrase
    letter: str
    role: str  # question | answer
    occurrence: int  # earlier phrases of the same letter and role
    final: bool
    section_start: bool  # first bar of a phrase whose letter differs from the phrase before

    def chord_at(self, beat: float) -> Chord:
        """The chord sounding at ``beat`` (within the bar)."""
        current = self.spans[0]
        for span in self.spans:
            if span.start <= beat + 1e-9:
                current = span
        return current.chord

    def span_end(self, beat: float) -> float:
        """Where the chord sounding at ``beat`` stops (beat within the bar)."""
        for span in self.spans:
            if span.start <= beat + 1e-9 < span.start + span.length:
                return span.start + span.length
        return self.spans[-1].start + self.spans[-1].length


def form(phrases: int) -> list[tuple[str, str]]:
    """``(letter, question | answer)`` per phrase: blocks of A A B A (the second block's contrast
    is C), the rest A, then B A or A A; the last phrase is always an answer."""
    out: list[tuple[str, str]] = []
    for block in range(phrases // 4):
        contrast = "B" if block % 2 == 0 else "C"
        out += [("A", "question"), ("A", "answer"), (contrast, "question"), ("A", "answer")]
    rest = phrases % 4
    out += {0: [], 1: [("A", "answer")], 2: [("A", "question"), ("A", "answer")], 3: [("A", "question"), ("B", "question"), ("A", "answer")]}[rest]
    return out


_SPLITS = {4: {1: (4,), 2: (2, 2), 3: (2, 1, 1), 4: (1, 1, 1, 1)}, 3: {1: (3,), 2: (2, 1), 3: (1, 1, 1)}}


def _plan(mood: Mood, key: Key, bars: int, rng: random.Random) -> list[_Bar]:
    phrases = form(bars // 4)
    chosen: dict[str, Progression] = {}
    for letter in ("A", "B", "C"):
        pool = mood.themes if letter == "A" else mood.contrasts
        if letter == "C" and "B" in chosen and len(pool) > 1:
            pool = tuple(p for p in pool if p != chosen["B"])
        chosen[letter] = rng.choice(pool)
    seen: dict[tuple[str, str], int] = {}
    tonic = "i" if key.minor else "I"
    out: list[_Bar] = []
    for p, (letter, role) in enumerate(phrases):
        occurrence = seen.get((letter, role), 0)
        seen[(letter, role)] = occurrence + 1
        progression = getattr(chosen[letter], role)
        for position, text in enumerate(progression):
            index = 4 * p + position
            final = index == bars - 1
            symbols = [tonic, "V7"] if final else text.split()
            lengths = _SPLITS[mood.meter][len(symbols)]
            spans, at = [], 0.0
            for symbol, length in zip(symbols, lengths):
                spans.append(_Span(at, float(length), parse_chord(symbol, key)))
                at += length
            new_section = position == 0 and (p == 0 or phrases[p - 1][0] != letter)
            out.append(_Bar(index, float(index * mood.meter), tuple(spans), p, position, letter, role, occurrence, final, new_section))
    return out


# ----- the melody ---------------------------------------------------------------------------------


def parse_cell(text: str, beats: int) -> tuple[tuple[float, float], ...]:
    """A rhythm cell (``"1 .5 .5 r1 1"``: durations in beats, ``r`` a rest) as ``(onset,
    length)`` notes; :class:`VidgenError` unless it fills exactly ``beats``."""
    notes, at = [], 0.0
    for token in text.split():
        length = float(token[1:] if token.startswith("r") else token)
        if not token.startswith("r"):
            notes.append((at, length))
        at += length
    if abs(at - beats) > 1e-9 or not notes:
        raise VidgenError(f"compose: rhythm cell {text!r} must fill {beats} beats with at least one note")
    return tuple(notes)


def _vary(cell: tuple[tuple[float, float], ...], rng: random.Random) -> tuple[tuple[float, float], ...]:
    """``cell`` with its longest note (a beat or more) split in two, or two short notes merged."""
    longest = max(range(len(cell)), key=lambda k: (cell[k][1], -k))
    onset, length = cell[longest]
    if length >= 1 and (rng.random() < 0.7 or len(cell) < 2):
        half = length / 2
        return cell[:longest] + ((onset, half), (onset + half, half)) + cell[longest + 1 :]
    for k in range(len(cell) - 1):
        a, b = cell[k], cell[k + 1]
        if abs(a[0] + a[1] - b[0]) < 1e-9:
            return cell[:k] + ((a[0], a[1] + b[1]),) + cell[k + 2 :]
    return cell


def _strong(meter: int) -> tuple[float, ...]:
    """The strong beats of a bar: 1 and 3 in 4/4, 1 in 3/4."""
    return (0.0, 2.0) if meter == 4 else (0.0,)


def _pitches(pitch_classes: Sequence[int], low: int, high: int) -> list[int]:
    return [p for p in range(low, high + 1) if p % 12 in pitch_classes]


@dataclass
class _Slot:
    bar: _Bar
    onset: float  # within the bar
    length: float
    anchor: bool
    pitch: int = -1

    @property
    def chord(self) -> Chord:
        return self.bar.chord_at(self.onset)


def _rhythms(bars: list[_Bar], mood: Mood, rng: random.Random) -> list[list[tuple[float, float]]]:
    """The melody's rhythm cell of each bar: per letter a motif of three cells (bar 1, bar 2, and
    the answer's bar 3); a question's bar 3 repeats bar 1's cell; a return of a letter varies
    bar 2; the phrases end with the cadence cells, the piece with the turn."""
    meter = mood.meter
    cells = [parse_cell(c, meter) for c in mood.cells]
    motifs: dict[str, tuple[Any, Any, Any]] = {}
    out = []
    for bar in bars:
        if bar.letter not in motifs:
            first, second, third = rng.sample(range(len(cells)), 3)
            motifs[bar.letter] = (cells[first], cells[second], cells[third])
        motif = motifs[bar.letter]
        if bar.final:
            cell = parse_cell(mood.turn, meter)
        elif bar.position == 3:
            cell = parse_cell(mood.half if bar.role == "question" else mood.full, meter)
        elif bar.position == 0:
            cell = motif[0]
        elif bar.position == 1:
            cell = motif[1] if bar.occurrence == 0 else _vary(motif[1], rng)
        else:
            cell = motif[0] if bar.role == "question" else motif[2]
            if bar.occurrence > 0:
                cell = _vary(cell, rng)
        out.append(list(cell))
    return out


def _target(bar: _Bar, onset: float, meter: int, low: int, high: int) -> float:
    """Where the melody aims at ``onset``: an arch over the phrase (a question rises and stays
    up, an answer comes down towards the tonic), contrast sections higher or lower."""
    t = (bar.position * meter + onset) / (4 * meter)
    span = high - low
    centre = low + 0.45 * span + {"A": 0.0, "B": 0.15 * span, "C": -0.1 * span}[bar.letter]
    amplitude = 0.3 * span
    shape = math.sin(math.pi * t) - 0.2 if bar.role == "question" else math.sin(0.8 * math.pi * t) - t
    return centre + amplitude * shape


def _choose(candidates: list[int], target: float, previous: int | None, rng: random.Random) -> list[int]:
    """``candidates`` ranked: near ``target``, within a sixth of ``previous``, not repeating it."""
    def cost(p: int) -> float:
        value = abs(p - target) + 0.3 * rng.random()
        if previous is not None:
            value += 1.5 if p == previous else 0.0
            value += 6.0 if abs(p - previous) > 9 else 0.0
        return value

    return sorted(candidates, key=cost)


def _melody(bars: list[_Bar], mood: Mood, key: Key, low: int, high: int, rng: random.Random) -> list[_Slot]:
    meter = mood.meter
    strong = _strong(meter)
    offsets = {letter: rng.choice(((0, 4), (0, -3), (2, 5), (0, 2, 4), (-2, 3), (4, 0))) for letter in "ABC"}
    slots: list[_Slot] = []
    previous: int | None = None
    previous_bar: tuple[Any, ...] | None = None

    def place(bar: _Bar, cell: Sequence[tuple[float, float]], previous: int | None) -> tuple[list[_Slot], list[list[int]]]:
        """The bar's slots with its anchors pitched (each anchor's ranked choices too)."""
        bar_slots = [_Slot(bar, onset, length, k == 0 or any(abs(onset - s) < 1e-9 for s in strong)) for k, (onset, length) in enumerate(cell)]
        shape = offsets[bar.letter] if bar.occurrence == 0 else tuple(-o for o in offsets[bar.letter])
        choices = []
        for k, slot in enumerate(s for s in bar_slots if s.anchor):
            cadence = k == 0 and (bar.position == 3 or bar.final)
            if cadence and (bar.role == "answer" or bar.final):
                ref = previous if previous is not None else (low + high) / 2
                ranked = sorted(_pitches((key.tonic,), low, high), key=lambda p: abs(p - ref) + (0.5 if p > ref else 0.0))
            else:
                target = previous if cadence and previous is not None else _target(bar, slot.onset, meter, low, high) + shape[k % len(shape)]
                ranked = _choose(_pitches(slot.chord.pitch_classes, low, high), target, previous, rng)
            slot.pitch = ranked[0]
            choices.append(ranked)
            previous = slot.pitch
        return bar_slots, choices

    for bar, cell in zip(bars, _rhythms(bars, mood, rng)):
        bar_slots, choices = place(bar, cell, previous)
        if (tuple(cell), bar_slots[0].pitch) == previous_bar:  # the same as the bar before: change it
            if len(choices[0]) > 1:
                bar_slots[0].pitch = choices[0][1]
            else:
                cell = list(_vary(tuple(cell), rng))
                bar_slots, choices = place(bar, cell, previous)
        previous_bar = (tuple(cell), bar_slots[0].pitch)
        previous = [s for s in bar_slots if s.anchor][-1].pitch
        slots += bar_slots
    _fill(slots, key, low, high)
    return slots


def _fill(slots: list[_Slot], key: Key, low: int, high: int) -> None:
    """Pitch the weak slots between two anchors: steps of the chord's scale along the line from
    one anchor to the next (the last ones lead back to the first), a chord tone for a leap."""
    anchors = [i for i, s in enumerate(slots) if s.anchor]
    for n, a in enumerate(anchors):
        b = anchors[n + 1] if n + 1 < len(anchors) else anchors[0] + len(slots)
        run = list(range(a + 1, b))
        if not run:
            continue
        start, goal = slots[a].pitch, slots[b % len(slots)].pitch
        previous = start
        for j, index in enumerate(run, start=1):
            slot = slots[index]
            aim = start + (goal - start) * j / (len(run) + 1)
            pool = _pitches(slot.chord.scale(key), low, high)
            if abs(aim - previous) > 4:
                pool = _pitches(slot.chord.pitch_classes, low, high)
            avoid = {previous} | ({goal} if j == len(run) else set())
            choices = [p for p in pool if p not in avoid] or pool
            slot.pitch = min(choices, key=lambda p: (abs(p - aim), p))
            previous = slot.pitch


# ----- accompaniment, bass, drums -----------------------------------------------------------------


def fit_range(low: int, high: int, instrument: Instrument) -> tuple[int, int]:
    """``low``-``high`` moved by octaves to lie best in the instrument's range, then clipped to it."""
    def overlap(shift: int) -> int:
        return min(high + shift, instrument.high) - max(low + shift, instrument.low)

    shift = max(range(-36, 37, 12), key=lambda s: (overlap(s), -abs(s)))
    return max(low + shift, instrument.low), min(high + shift, instrument.high)


def _voicing(chord: Chord, low: int, previous: tuple[int, ...] | None) -> tuple[int, ...]:
    """Close-position voicing of ``chord`` from ``low`` up (a 9th chord drops nothing more), the
    inversion nearest the ``previous`` voicing."""
    pcs = chord.pitch_classes
    options = []
    for rotation in range(len(pcs)):
        order = pcs[rotation:] + pcs[:rotation]
        for lift in (0, 12):
            first = next(p for p in range(low + lift, low + lift + 12) if p % 12 == order[0])
            notes = [first]
            for pc in order[1:]:
                notes.append(next(p for p in range(notes[-1] + 1, notes[-1] + 13) if p % 12 == pc))
            options.append(tuple(notes))
    if previous is None:
        return min(options, key=lambda v: (v[0] != min(v) or v[0] % 12 != chord.root, v[-1]))
    return min(options, key=lambda v: (sum(min(abs(n - m) for m in previous) for n in v), v[-1]))


def _humanize(velocity: float, rng: random.Random, spread: int = 4) -> int:
    return max(1, min(127, round(velocity) + rng.randint(-spread, spread)))


def _chord_events(pattern: str, meter: int, variant: int) -> list[tuple[float, float, Any, float]]:
    """``(onset, length, which, level)`` of one bar of a chord pattern; ``which`` is ``all``, an
    index into the arpeggio tones, or ``root`` / ``fifth`` / ``octave``."""
    beats = float(meter)
    if pattern == "block":
        return [(s, 2.0 if meter == 4 else 3.0, "all", 1.0 if s == 0 else 0.85) for s in _strong(meter)]
    if pattern == "arpeggio":
        shapes = {4: ((0, 1, 2, 3, 2, 1, 2, 1), (0, 2, 1, 3, 2, 3, 1, 2), (0, 1, 2, 1, 3, 2, 1, 2)), 3: ((0, 1, 2, 3, 2, 1), (0, 2, 1, 3, 1, 2), (0, 1, 3, 2, 3, 1))}[meter]
        shape = shapes[variant % len(shapes)]
        return [(k / 2, 1.0, idx, 1.0 if k == 0 else 0.8 if k % 2 == 0 else 0.7) for k, idx in enumerate(shape)]
    if pattern == "broken":
        shape = (0, 2, 1, 2) * meter
        return [(k / 2, 0.5, shape[k], 1.0 if k == 0 else 0.75) for k in range(2 * meter)]
    if pattern == "oompah":
        return [(s, 0.35, "all", 0.9) for s in ((1.0, 3.0) if meter == 4 else (1.0, 2.0))]
    if pattern == "ostinato":
        figure = ("root", "fifth", "octave", "fifth") if variant % 2 == 0 else ("root", "octave", "fifth", "octave")
        return [(k / 2, 0.3, figure[k % 4], 1.0 if k % 2 == 0 else 0.75) for k in range(2 * meter)]
    if pattern == "strum":
        if meter == 3:
            return [(0.0, 1.0, "all", 1.0), (1.0, 1.0, "all", 0.8), (2.0, 1.0, "all", 0.8)]
        return [(0.0, 1.5, "all", 1.0), (1.5, 1.0, "all", 0.8), (2.5, 0.5, "all", 0.75), (3.0, 1.0, "all", 0.85)]
    return [(0.0, beats, "all", 1.0)]  # pad


def _accompaniment(bars: list[_Bar], pattern: str, low: int, velocity: float, rng: random.Random, meter: int) -> list[Note]:
    """The chord part: ``pattern`` per bar; a chord change inside an event's span cuts it, and a
    chord starting off the pattern's onsets is struck there."""
    notes: list[Note] = []
    previous: tuple[int, ...] | None = None
    voicings: dict[tuple[int, float], tuple[int, ...]] = {}
    for bar in bars:
        for span in bar.spans:
            previous = voicings[(bar.index, span.start)] = _voicing(span.chord, low, previous)
        variant = "ABC".index(bar.letter)
        events = [(span.start, span.length, "all", 1.0) for span in bar.spans] if pattern == "pad" else _chord_events(pattern, meter, variant)
        onsets = {round(e[0], 6) for e in events}
        if pattern not in ("pad", "arpeggio", "broken", "ostinato"):
            events += [(s.start, min(s.length, 1.0), "all", 0.9) for s in bar.spans if round(s.start, 6) not in onsets]
        for onset, length, which, level in events:
            span = next(s for s in reversed(bar.spans) if s.start <= onset + 1e-9)
            voicing = voicings[(bar.index, span.start)]
            length = min(length, bar.span_end(onset) - onset) if pattern != "pad" else length
            if which == "all":
                pitches = list(voicing)
            elif isinstance(which, int):
                tones = (*voicing, voicing[0] + 12)
                pitches = [tones[which % len(tones)]]
            else:
                root = next(p for p in range(low - 7, low + 5) if p % 12 == span.chord.root)
                pitches = [root + {"root": 0, "fifth": 7, "octave": 12}[which]]
            for n, pitch in enumerate(pitches):
                stagger = 0.015 * n if pattern == "strum" else 0.0
                notes.append(Note(bar.start + onset + stagger, max(0.05, length - stagger), pitch, _humanize(velocity * level, rng)))
    return notes


def _bass_events(pattern: str, meter: int) -> list[tuple[float, float, str]]:
    if pattern == "half":
        return [(s, 1.9 if meter == 4 else 2.9, "root") for s in _strong(meter)]
    if pattern == "root_fifth":
        return [(0.0, 0.9, "root"), (2.0, 0.9, "fifth")] if meter == 4 else [(0.0, 0.9, "root")]
    if pattern == "walking":
        return [(float(k), 0.95, ("root", "third", "fifth", "approach")[k] if meter == 4 else ("root", "fifth", "approach")[k]) for k in range(meter)]
    if pattern == "pulse":
        return [(k / 2, 0.42, "root") for k in range(2 * meter)]
    if pattern == "pop":
        if meter == 3:
            return [(0.0, 1.2, "root"), (1.5, 0.4, "root"), (2.0, 0.9, "fifth")]
        return [(0.0, 1.2, "root"), (1.5, 0.4, "root"), (2.0, 0.9, "fifth"), (3.0, 0.45, "octave"), (3.5, 0.4, "root")]
    return [(0.0, float(meter), "root")]  # sustain


def _bass(bars: list[_Bar], pattern: str, low: int, high: int, velocity: float, rng: random.Random, meter: int) -> list[Note]:
    """The bass part: roots in ``low`` to ``low + 11`` (the chord's bass note for an inversion),
    fifths, thirds and octaves above them, an approach note a semitone under the next root."""
    def root_pitch(pc: int) -> int:
        return next(p for p in range(low, low + 12) if p % 12 == pc)

    notes: list[Note] = []
    for i, bar in enumerate(bars):
        events = _bass_events(pattern, meter)
        onsets = {round(e[0], 6) for e in events}
        events += [(s.start, min(s.length, 0.9 if pattern != "sustain" else s.length), "root") for s in bar.spans if round(s.start, 6) not in onsets]
        starts = {round(s.start, 6) for s in bar.spans}
        for onset, length, which in sorted(events):
            chord = bar.chord_at(onset)
            root = root_pitch(chord.bass)
            if round(onset, 6) in starts and which != "root" and onset > 0:
                which = "root"
            if which == "fifth":
                pitch = root_pitch(chord.root) + 7
            elif which == "third":
                pitch = root_pitch(chord.root) + (chord.tones[1][1] - chord.root) % 12
            elif which == "octave":
                pitch = root + 12
            elif which == "approach":
                following = bars[(i + 1) % len(bars)].chord_at(0.0)
                pitch = root_pitch(following.bass) - 1
                pitch += 2 if pitch < low else 0
            else:
                pitch = root
            while pitch > high:
                pitch -= 12
            length = min(length, bar.span_end(onset) - onset)
            level = 1.0 if onset == 0 else 0.85
            notes.append(Note(bar.start + onset, max(0.05, length), pitch, _humanize(velocity * level, rng)))
    return notes


def _drums(bars: list[_Bar], pattern: DrumPattern, rng: random.Random, meter: int) -> list[Note]:
    """The drum part: the pattern per bar, its fill in each phrase's last bar, a cymbal (key 49)
    at each new section when the pattern has one."""
    notes: list[Note] = []
    for bar in bars:
        if meter == 3:
            hits = [(0.0, 36, 65), (1.0, pattern.backbeat, 45), (2.0, pattern.backbeat, 38)]
            if pattern.tick is not None:
                hits += list(_eighths(pattern.tick, 32, 24, 3))
        else:
            hits = list(pattern.hits)
            if bar.position == 3:
                hits = [h for h in hits if h[0] < pattern.fill_from] + list(pattern.fill)
        if pattern.crash and bar.section_start:
            hits.append((0.0, 49, 72))
        level = 1.08 if bar.letter != "A" else 1.0
        for onset, drum, velocity in hits:
            notes.append(Note(bar.start + onset, 0.25, drum, _humanize(velocity * level, rng, 5)))
    return notes


# ----- the piece ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Piece:
    """A composed piece: its score and what was chosen (key, tempo, bars, parts, the chord names of
    each bar, the form of each phrase, and ``harmony``: every chord as ``(beat, beats, chord)``)."""

    score: Score
    mood: Mood
    key: Key
    tempo: float
    bars: int
    seed: int
    voices: tuple[Voice, ...]
    chords: tuple[tuple[str, ...], ...]
    phrases: tuple[str, ...]
    harmony: tuple[tuple[float, float, Chord], ...]

    @property
    def seconds(self) -> float:
        """The piece's length (one pass, without the reverb's tail)."""
        return self.score.length_seconds

    def chord_at(self, beat: float) -> Chord:
        """The chord sounding at ``beat`` (from the piece's start)."""
        return next(chord for start, length, chord in reversed(self.harmony) if start <= beat + 1e-9)


#: The register the pad starts from (MIDI key of its lowest note).
_PAD_LOW = 50
#: Velocities of the parts before accents and humanizing.
_VELOCITY = {"melody": 92, "chords": 74, "pad": 62, "bass": 88}


def compose_piece(
    mood: str,
    key: str | None = None,
    tempo: float | None = None,
    instruments: Mapping[str, Any] | None = None,
    seed: int = DEFAULT_SEED,
    bars: int | None = None,
) -> Piece:
    """Compose ``bars`` bars (default: the mood's) in ``mood``, seeded by ``seed`` (the same
    settings give the same notes). :class:`VidgenError` for invalid settings."""
    problems = settings_problems(mood, key, tempo, instruments, bars)
    if problems:
        raise VidgenError("compose: " + "; ".join(problems))
    found = MOODS[mood]
    the_key = mood_key(found, key)
    count = bars or found.bars
    rng = random.Random(zlib.crc32(f"vidgen-compose:{mood}:{seed}".encode("utf-8")))
    plan = _plan(found, the_key, count, rng)
    voices = resolve_voices(found, instruments)
    meter = found.meter
    parts = []
    for voice in voices:
        part_rng = random.Random(zlib.crc32(f"vidgen-compose:{mood}:{seed}:{voice.role}".encode("utf-8")))
        if voice.role == "melody":
            low, high = fit_range(*found.melody_range, voice.instrument)
            notes = _melody_notes(_melody(plan, found, the_key, low, high, part_rng), found, part_rng)
        elif voice.role == "chords":
            low, _ = fit_range(found.chords_low, found.chords_low + 24, voice.instrument)
            notes = _accompaniment(plan, found.chords, low, _VELOCITY["chords"], part_rng, meter)
        elif voice.role == "pad":
            low, _ = fit_range(_PAD_LOW, _PAD_LOW + 20, voice.instrument)
            notes = _accompaniment(plan, "pad", low, _VELOCITY["pad"], part_rng, meter)
        elif voice.role == "bass":
            low, high = fit_range(found.bass_low, found.bass_low + 19, voice.instrument)
            notes = _bass(plan, found.bass, low, high, _VELOCITY["bass"], part_rng, meter)
        else:
            notes = _drums(plan, DRUM_PATTERNS[found.drums], part_rng, meter)
        length = count * meter
        notes = [n if n.end <= length else Note(n.start, length - n.start, n.pitch, n.velocity) for n in notes if n.start < length]
        parts.append(
            Part(voice.role, tuple(notes), program=voice.instrument.program, drums=voice.instrument.drums, volume=voice.volume, pan=voice.pan, reverb=voice.reverb)
        )
    sections = tuple(Section(f"{b.letter}{b.occurrence + 1} {b.role}", b.start) for b in plan if b.position == 0)
    score = Score(
        tempo=float(tempo or found.tempo), parts=tuple(parts), time_signature=(meter, 4), key=the_key.name,
        sections=sections, length=float(count * meter), balance=True,
    )
    chords = tuple(tuple(s.chord.name for s in b.spans) for b in plan)
    phrases = tuple(f"{b.letter} {b.role}" for b in plan if b.position == 0)
    harmony = tuple((b.start + s.start, s.length, s.chord) for b in plan for s in b.spans)
    return Piece(score, found, the_key, score.tempo, count, seed, voices, chords, phrases, harmony)


def compose(
    mood: str,
    key: str | None = None,
    tempo: float | None = None,
    instruments: Mapping[str, Any] | None = None,
    seed: int = DEFAULT_SEED,
    bars: int | None = None,
) -> Score:
    """The :class:`~vidgen.score.Score` of :func:`compose_piece`."""
    return compose_piece(mood, key, tempo, instruments, seed, bars).score


def _melody_notes(slots: list[_Slot], mood: Mood, rng: random.Random) -> list[Note]:
    """The melody's notes: ``articulation`` of each slot (a cadence held), accents on the bar's
    first beat and the strong beats."""
    notes = []
    strong = _strong(mood.meter)
    for slot in slots:
        held = slot.bar.position == 3 and slot.onset == 0
        length = slot.length if held else max(0.12, slot.length * mood.articulation)
        accent = 1.0 if slot.onset == 0 else 0.93 if slot.onset in strong else 0.84
        notes.append(Note(slot.bar.start + slot.onset, length, slot.pitch, _humanize(_VELOCITY["melody"] * accent, rng)))
    return notes


# ----- descriptions -------------------------------------------------------------------------------


_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(pitch: int) -> str:
    """A MIDI key as a note name with its octave (60 = C4)."""
    return f"{_NAMES[pitch % 12]}{pitch // 12 - 1}"


def progression_text(progression: tuple[str, ...], key: Key) -> str:
    """``I–vi–IV–V (D–Bm–G–A)``: a 4-bar progression in numerals and in the key's letters."""
    numerals = " | ".join(progression)
    letters = " | ".join(" ".join(parse_chord(s, key).name for s in bar.split()) for bar in progression)
    return f"{numerals} ({letters})"


def describe(mood: Mood) -> str:
    """What ``mood`` sounds like with its defaults, in words (for an author who cannot listen)."""
    key = parse_key(mood.key, mood.minor)
    voices = {v.role: v for v in resolve_voices(mood)}
    seconds = mood.bars * mood.meter * 60 / mood.tempo
    low, high = fit_range(*mood.melody_range, voices["melody"].instrument)
    text = [
        f"{mood.character[0].upper()}{mood.character[1:]}: {mood.tempo:g} BPM, {mood.meter}/4, {mood.key}; {mood.bars} bars "
        f"({seconds:.0f} s) of 4-bar phrases in the form A A B A (a question ending on V, its answer ending on I, a "
        "contrast, the answer again), looping seamlessly (the last bar turns from the tonic to V7 back to the start).",
        f"Melody: {voices['melody'].instrument.name}, {note_name(low)} to {note_name(high)}, {mood.melody_words}; a motif that comes back varied.",
    ]
    if "chords" in voices:
        text.append(f"Chords: {voices['chords'].instrument.name}, {CHORD_PATTERNS[mood.chords]}.")
    if "pad" in voices:
        text.append(f"Pad: {voices['pad'].instrument.name}, held chords, quiet.")
    if "bass" in voices:
        text.append(f"Bass: {voices['bass'].instrument.name}, {BASS_PATTERNS[mood.bass]}.")
    text.append(f"Drums: {voices['drums'].instrument.name}, {DRUM_PATTERNS[mood.drums].words}." if "drums" in voices else "No drums.")
    themes = "; ".join(progression_text(p.question, key) for p in mood.themes)
    contrasts = "; ".join(progression_text(p.question, key) for p in mood.contrasts)
    text.append(f"Chords of A (one chosen per seed): {themes}. Of B: {contrasts}.")
    return " ".join(text)


def mood_entries() -> list[dict[str, Any]]:
    """Every mood described for ``vidgen list-music``: ``{name, family, description, use, key,
    tempo, meter, bars, loop_seconds, instruments, fallback_bed}``."""
    return [
        {
            "name": mood.name,
            "family": mood.family,
            "description": describe(mood),
            "use": mood.use,
            "key": mood.key,
            "tempo": mood.tempo,
            "meter": f"{mood.meter}/4",
            "bars": mood.bars,
            "loop_seconds": round(mood.bars * mood.meter * 60 / mood.tempo, 3),
            "instruments": {v.role: v.instrument.name for v in resolve_voices(mood)},
            "fallback_bed": mood.bed,
        }
        for mood in MOODS.values()
    ]


def instrument_entries() -> list[dict[str, Any]]:
    """Every instrument name for ``vidgen list-music``: ``{name, program, drums, low, high,
    description}`` (``low`` / ``high`` note names; ``None`` for drum kits)."""
    return [
        {
            "name": i.name,
            "program": i.program,
            "drums": i.drums,
            "low": None if i.drums else note_name(i.low),
            "high": None if i.drums else note_name(i.high),
            "description": i.words,
        }
        for i in INSTRUMENTS.values()
    ]
