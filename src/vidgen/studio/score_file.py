"""Score files (DESIGN.md §93): a piece of music written in YAML — key, tempo, time signature,
named sections, a chord progression and tracks of step patterns — read and checked into a
:class:`MusicScore` that :func:`vidgen.studio.render.render_music_score` plays.

Every mistake found is reported at once, each with where it is (``tracks.bass.steps``) and, for
a misspelt name, the nearest known one.
"""

from __future__ import annotations

import difflib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio.effects import EFFECTS, Curve, Duck, Echo, Gate, Reverb, is_off, parse_curve, parse_duck, parse_echo, parse_gate, parse_reverb
from vidgen.studio.instruments import INSTRUMENTS, Instrument
from vidgen.studio.patterns import Pattern, accent_steps, parse_accent, parse_steps
from vidgen.studio.theory import Chord, Key, note_number, parse_chord, parse_key

#: The score-file format this module reads (``version:``, optional).
FORMAT_VERSION = 1
TOP_KEYS = ("version", "title", "description", "key", "tempo", "time", "seed", "loop", "bars", "sections", "progression", "chord_bars", "tracks", "master")
SECTION_KEYS = ("name", "bars", "key", "progression", "chord_bars")
#: What a track may change in one section (``sections: {lift: {...}}``): its notes, its
#: instrument's settings and its effects (:data:`vidgen.studio.effects.EFFECTS`).
PART_KEYS = ("steps", "accent", "octave", "transpose", "settings") + tuple(EFFECTS)
TRACK_KEYS = ("instrument", "play", "rest", "only", "sections") + PART_KEYS
CHORD_KEYS = ("chord", "notes", "bass")
MASTER_KEYS = ("lowpass", "highpass")
TEMPO_RANGE = (40.0, 240.0)
MAX_BARS = 512
MAX_SECONDS = 600.0
#: Default master filter: a high-pass and a gentle low-pass over the whole piece, as the beds.
DEFAULT_LOWPASS, DEFAULT_HIGHPASS = 4500.0, 32.0
_NAME = re.compile(r"^[a-z][a-z0-9_]*\Z")  # \Z: a name with a newline at its end is not one (it names files)
_TIME = re.compile(r"^(\d{1,2})/(2|4|8)$")


@dataclass(frozen=True)
class ChordSlot:
    """A chord as it plays: from ``start`` for ``length`` samples, in ``key``; ``notes`` / ``bass_note``
    the voicing and bass note the score wrote out (MIDI), else ``None``."""

    chord: Chord
    key: Key
    start: int
    length: int
    notes: tuple[int, ...] | None = None
    bass_note: int | None = None


@dataclass(frozen=True)
class Section:
    """A named section: its first bar (0-based), length in bars, key and chords."""

    name: str
    first_bar: int
    bars: int
    key: Key
    chords: tuple[ChordSlot, ...]


@dataclass(frozen=True)
class TrackPart:
    """What a track plays in one section (its settings with that section's changes).
    ``volume_db``: a constant volume (applied to each note); ``volume_curve``: a moving one
    (applied to the track's sound, ``volume_db`` then 0); the rest are its effects (``None``:
    off)."""

    steps: Pattern | None
    accent: tuple[int, ...] | None
    octave: int | None
    transpose: int
    volume_db: float
    pan: float
    settings: Mapping[str, float]
    spread: float = 0.0
    volume_curve: Curve | None = None
    width: Curve | None = None
    lowpass: Curve | None = None
    highpass: Curve | None = None
    duck: Duck | None = None
    gate: Gate | None = None
    echo: Echo | None = None
    reverb: Reverb | None = None

    @property
    def effects(self) -> list[str]:
        """The names of the effects this part uses (beyond volume / pan)."""
        used = [n for n in ("width", "lowpass", "highpass", "duck", "gate", "echo", "reverb") if getattr(self, n) is not None]
        return (["spread"] if self.spread else []) + (["volume curve"] if self.volume_curve is not None else []) + used


@dataclass(frozen=True)
class Track:
    """A track: its instrument, whether it holds the chords (``play: chords``) and its part in
    every section it plays (a section left out is a rest)."""

    name: str
    instrument: Instrument
    play_chords: bool
    parts: Mapping[str, TrackPart]


@dataclass(frozen=True)
class MusicScore:
    """A checked score file. ``beat``: samples per quarter note (rounded down to whole
    sixteenths, so the sixteenth grid is exact); ``bar``: samples per bar."""

    title: str
    description: str
    key: Key
    tempo: float
    time: tuple[int, int]
    seed: int
    loop: bool
    beat: int
    bar: int
    sections: tuple[Section, ...]
    tracks: tuple[Track, ...]
    lowpass: float
    highpass: float
    origin: str

    @property
    def bars(self) -> int:
        return sum(s.bars for s in self.sections)

    @property
    def samples(self) -> int:
        """The piece's length in samples (one pass; a one-shot adds its tail when rendered)."""
        return self.bars * self.bar

    @property
    def seconds(self) -> float:
        return self.samples / RATE

    @property
    def actual_tempo(self) -> float:
        """The tempo the beat grid plays (a hair above ``tempo`` after rounding the beat)."""
        return 60.0 * RATE / self.beat

    def section_start(self, section: Section) -> int:
        return section.first_bar * self.bar


def _close(name: str, known: Sequence[str]) -> str:
    found = difflib.get_close_matches(str(name), list(known), n=1, cutoff=0.6)
    return f"; did you mean '{found[0]}'?" if found else ""


class _Reader:
    """Collects the problems of one score file while reading it."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def mapping(self, value: Any, where: str, allowed: Sequence[str], what: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            self.add(where, f"expected a mapping of {what} ({', '.join(allowed)}), got {type(value).__name__}")
            return {}
        out: dict[str, Any] = {}
        for k, v in value.items():
            if str(k) not in allowed:
                self.add(f"{where}.{k}" if where else str(k), f"unknown key{_close(str(k), allowed)} (allowed: {', '.join(allowed)})")
            else:
                out[str(k)] = v
        return out

    def number(self, value: Any, where: str, low: float, high: float, integer: bool = False) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (integer and not float(value).is_integer()):
            self.add(where, f"expected {'a whole number' if integer else 'a number'} from {low:g} to {high:g}, got {value!r}")
            return None
        if not low <= value <= high or (isinstance(value, float) and not math.isfinite(value)):
            self.add(where, f"{value!r} is out of range ({low:g} to {high:g})")
            return None
        return float(value)

    def attempt(self, where: str, fn: Any, *args: Any) -> Any:
        """``fn(*args)``; a :class:`VidgenError` it raises becomes a problem (``None`` returned)."""
        try:
            return fn(*args)
        except VidgenError as exc:
            text = str(exc)
            self.add(where, text[len(where) + 2 :] if text.startswith(where + ": ") else text)
            return None


def load_music_score(path: Path) -> MusicScore:
    """Read and check the score file at ``path`` (:class:`VidgenError` listing every problem)."""
    if not path.is_file():
        raise VidgenError(f"score file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise VidgenError(f"{path}: not valid YAML: {exc}") from None
    return parse_music_score(data, str(path))


def parse_music_score(data: Any, origin: str = "score") -> MusicScore:
    """Check a score read from YAML (``data``) and build the :class:`MusicScore`."""
    r = _Reader()
    top = r.mapping(data, "", TOP_KEYS, "score settings") if data is not None else {}
    if data is None:
        r.add("score", "the file is empty")
    if "version" in top and top["version"] != FORMAT_VERSION:
        r.add("version", f"this schu-video-generator reads score files of version {FORMAT_VERSION}, got {top['version']!r}")
    for name in ("key", "tempo", "tracks"):
        if name not in top and data is not None:
            r.add(name, "missing" + {"key": " (e.g. key: A minor)", "tempo": " (quarter notes per minute, e.g. tempo: 112)", "tracks": ""}[name])
    key = r.attempt("key", parse_key, top["key"]) if "key" in top else None
    tempo = r.number(top["tempo"], "tempo", *TEMPO_RANGE) if "tempo" in top else None
    time = _time(r, top.get("time", "4/4"))
    seed = r.number(top.get("seed", 1), "seed", 0, 2**31 - 1, integer=True)
    loop = top.get("loop", True)
    if not isinstance(loop, bool):
        r.add("loop", f"expected true (a seamless loop, the default) or false (one pass with an ending), got {loop!r}")
    title, description = (str(top.get(k, "")) for k in ("title", "description"))
    lowpass, highpass = _master(r, top.get("master", {}))
    tracks_raw = top.get("tracks")
    if tracks_raw is not None and not isinstance(tracks_raw, Mapping):
        r.add("tracks", "expected a mapping of track name to track (e.g. kick: {instrument: kick, steps: \"x... x... x... x...\"})")
        tracks_raw = {}
    if r.problems and data is None:
        _raise(origin, r)
    # stand-ins after a problem, so the rest of the file is still checked (the problem is raised below)
    key, tempo, time = key or parse_key("C major"), tempo or 120.0, time or (4, 4)
    beat = int(RATE * 60 / tempo)
    beat -= beat % 4
    bar = beat * time[0] * 4 // time[1]
    sections = _sections(r, top, key, bar, time)
    if sections and sum(s.bars for s in sections) * bar / RATE > MAX_SECONDS:
        r.add("sections" if "sections" in top else "bars", f"the piece lasts {sum(s.bars for s in sections) * bar / RATE:.0f} s; at most {MAX_SECONDS:.0f} s")
    declared = {str(e.get("name")) for e in top.get("sections") or [] if isinstance(e, Mapping) and "progression" in e}
    unchorded = [] if "progression" in top else [s.name for s in sections if s.name not in declared]
    tracks = _tracks(r, tracks_raw or {}, sections, unchorded, loop is not False)
    if r.problems:
        _raise(origin, r)
    return MusicScore(title, description, key, tempo, time, int(seed or 0), bool(loop), beat, bar, tuple(sections), tuple(tracks), lowpass, highpass, origin)


def _raise(origin: str, r: _Reader) -> None:
    problems = list(dict.fromkeys(r.problems))  # a score progression read in every section reports once
    count = len(problems)
    lines = "\n".join(f"  - {p}" for p in problems)
    raise VidgenError(f"{origin}: {count} problem{'s' if count != 1 else ''} in the score:\n{lines}")


def _time(r: _Reader, value: Any) -> tuple[int, int] | None:
    match = _TIME.match(str(value).strip())
    if match is None or not 1 <= int(match.group(1)) <= 16:
        r.add("time", f"write the time signature like \"4/4\", \"3/4\" or \"6/8\" (beats 1-16 over 2, 4 or 8), got {value!r}")
        return None
    return int(match.group(1)), int(match.group(2))


def _master(r: _Reader, value: Any) -> tuple[float, float]:
    master = r.mapping(value, "master", MASTER_KEYS, "master settings")
    low = r.number(master.get("lowpass", DEFAULT_LOWPASS), "master.lowpass", 1000.0, 16000.0)
    high = r.number(master.get("highpass", DEFAULT_HIGHPASS), "master.highpass", 10.0, 200.0)
    return low or DEFAULT_LOWPASS, high or DEFAULT_HIGHPASS


def _sections(r: _Reader, top: dict[str, Any], key: Key, bar: int, time: tuple[int, int]) -> list[Section]:
    raw = top.get("sections")
    if raw is None:
        if "bars" not in top:
            r.add("bars", "missing: give the length in bars (bars: 16) or a list of sections (sections: [{name: intro, bars: 4}, ...])")
            return []
        entries: list[Any] = [{"name": "main", "bars": top["bars"]}]
        where_of = ["bars"]
    else:
        if "bars" in top:
            r.add("bars", "give either bars or sections (the sections' bars add up to the length), not both")
        if not isinstance(raw, list) or not raw:
            r.add("sections", "expected a list of sections, e.g. [{name: intro, bars: 4}, {name: main, bars: 16}]")
            return []
        entries, where_of = raw, [f"sections[{k}]" for k in range(len(raw))]
    sections: list[Section] = []
    first_bar = 0
    seen: set[str] = set()
    for entry, where in zip(entries, where_of):
        item = r.mapping(entry, where, SECTION_KEYS, "section settings")
        name = str(item.get("name", ""))
        if not _NAME.match(name):
            r.add(f"{where}.name", f"a section needs a name of lower-case letters, digits and _ (e.g. intro, lift), got {item.get('name')!r}")
            continue
        if name in seen:
            r.add(f"{where}.name", f"section '{name}' is already used; give each section its own name")
            continue
        seen.add(name)
        bars = r.number(item.get("bars"), f"{where}.bars" if raw is not None else "bars", 1, MAX_BARS, integer=True)
        section_key = r.attempt(f"{where}.key", parse_key, item["key"]) if "key" in item else key
        if bars is None or section_key is None:
            continue
        chords = _progression(r, item, top, where, section_key, int(bars), first_bar * bar, bar, time)
        sections.append(Section(name, first_bar, int(bars), section_key, tuple(chords)))
        first_bar += int(bars)
    if first_bar > MAX_BARS:
        r.add("sections", f"{first_bar} bars in all; at most {MAX_BARS}")
    return sections


def _progression(
    r: _Reader, item: dict[str, Any], top: dict[str, Any], where: str, key: Key, bars: int, start: int, bar: int, time: tuple[int, int]
) -> list[ChordSlot]:
    """The section's chords: its own ``progression`` or the score's, each lasting ``chord_bars``
    bars, repeated from the section's start to fill it."""
    own = "progression" in item
    raw = item["progression"] if own else top.get("progression")
    loc = f"{where}.progression" if own else "progression"
    if raw is None:
        return []
    per = item.get("chord_bars", top.get("chord_bars", 1))
    per_loc = f"{where}.chord_bars" if "chord_bars" in item else "chord_bars"
    chord_bars = r.number(per, per_loc, 0.125, 64)
    if chord_bars is None:
        return []
    beats = chord_bars * time[0]
    if abs(beats - round(beats)) > 1e-9:
        r.add(per_loc, f"{chord_bars:g} bars is not a whole number of beats in {time[0]}/{time[1]}")
        return []
    items: list[Any] = raw.replace("|", " ").replace(",", " ").split() if isinstance(raw, str) else raw
    if not isinstance(items, list) or not items:
        r.add(loc, "expected chords, e.g. \"i VI III VII\" or [Am, F, C, G] (Roman numerals of the key or chord names)")
        return []
    parsed: list[tuple[Chord, tuple[int, ...] | None, int | None]] = []
    for k, entry in enumerate(items):
        here = f"{loc}[{k}]"
        notes = bass = None
        if isinstance(entry, Mapping):
            spec = r.mapping(entry, here, CHORD_KEYS, "chord settings")
            if "chord" not in spec:
                r.add(here, "missing chord (e.g. {chord: Dm(add9), notes: [D3, A3, D4, E4, F4], bass: D2})")
                continue
            if "notes" in spec:
                notes = _note_list(r, spec["notes"], f"{here}.notes")
            if "bass" in spec:
                bass = r.attempt(f"{here}.bass", _note, spec["bass"])
            entry = spec["chord"]
        chord = r.attempt(here, parse_chord, str(entry), key, here)
        if chord is not None:
            parsed.append((chord, notes, bass))
    if len(parsed) != len(items):
        return []
    length = round(chord_bars * bar)
    end = start + bars * bar
    slots = []
    for k in range(math.ceil(bars * bar / length)):
        chord, notes, bass = parsed[k % len(parsed)]
        at = start + k * length
        slots.append(ChordSlot(chord, key, at, min(length, end - at), notes, bass))
    return slots


def _note(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127:
        return value
    return note_number(str(value))


def _note_list(r: _Reader, value: Any, where: str) -> tuple[int, ...] | None:
    if not isinstance(value, list) or not value:
        r.add(where, "expected a list of notes, e.g. [D3, A3, D4, F4]")
        return None
    notes = [r.attempt(f"{where}[{k}]", _note, v) for k, v in enumerate(value)]
    return None if None in notes else tuple(sorted(notes))  # type: ignore[arg-type]


def _section_names(r: _Reader, value: Any, where: str, names: Sequence[str]) -> set[str]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list):
        r.add(where, f"expected a list of section names ({', '.join(names)})")
        return set()
    out = set()
    for name in items:
        if str(name) not in names:
            r.add(where, f"no section '{name}'{_close(str(name), names)} (sections: {', '.join(names)})")
        else:
            out.add(str(name))
    return out


def _tracks(r: _Reader, raw: Mapping[str, Any], sections: list[Section], unchorded: list[str], loop: bool) -> list[Track]:
    """The tracks; ``unchorded``: the sections without a progression (an error where a pitched
    track plays); ``loop``: the piece loops (a hold may go on round its end)."""
    if not raw:
        r.add("tracks", "a score needs at least one track")
    names = [s.name for s in sections]
    tracks = []
    for name, value in raw.items():
        where = f"tracks.{name}"
        if not _NAME.match(str(name)):
            r.add(where, "a track name is lower-case letters, digits and _ (e.g. bass, lead_2)")
            continue
        spec = r.mapping(value, where, TRACK_KEYS, "track settings")
        track = _track(r, str(name), spec, where, sections, names, loop)
        if track is not None:
            tracks.append(track)
    track_names = [str(n) for n in raw]
    for t in tracks:
        for to in sorted({p.duck.to for p in t.parts.values() if p.duck is not None}):
            if to == t.name:
                r.add(f"tracks.{t.name}.duck", "a track cannot duck under itself; name the kick (duck: kick) or beat")
            elif to != "beat" and to not in track_names:
                r.add(f"tracks.{t.name}.duck", f"no track '{to}'{_close(to, track_names + ['beat'])} (tracks: {', '.join(track_names)}; or beat: every beat)")
    pitched = [t.name for t in tracks if t.instrument.kind != "drum" and set(t.parts) & set(unchorded)]
    if pitched:
        r.add("progression", f"missing: tracks {', '.join(pitched)} play notes of the chords; give a progression (e.g. progression: \"i VI III VII\") "
              f"for the score or for sections {', '.join(unchorded)}")
    return tracks


def _track(r: _Reader, name: str, spec: dict[str, Any], where: str, sections: list[Section], names: list[str], loop: bool) -> Track | None:
    if "instrument" not in spec:
        r.add(where, f"missing instrument (instruments: {', '.join(INSTRUMENTS)})")
        return None
    instrument = INSTRUMENTS.get(str(spec["instrument"]))
    if instrument is None:
        r.add(f"{where}.instrument", f"unknown instrument '{spec['instrument']}'{_close(str(spec['instrument']), list(INSTRUMENTS))} (instruments: {', '.join(INSTRUMENTS)})")
        return None
    play = spec.get("play")
    if play is not None and play != "chords":
        r.add(f"{where}.play", f"the only value is 'chords' (hold the progression's chords), got {play!r}; for a rhythm use steps")
    play_chords = play == "chords"
    if play_chords and instrument.kind != "pad":
        pads = ", ".join(n for n, i in INSTRUMENTS.items() if i.kind == "pad")
        r.add(f"{where}.play", f"{instrument.name} cannot hold chords ({pads} can); play chords in steps with '*', e.g. steps: \"*... *...\"")
    if play_chords and "steps" in spec:
        r.add(where, "give steps or play: chords, not both")
    if "rest" in spec and "only" in spec:
        r.add(where, "give rest (sections where it is silent) or only (the sections it plays in), not both")
    silent = _section_names(r, spec["rest"], f"{where}.rest", names) if "rest" in spec else set()
    if "only" in spec:
        silent = set(names) - _section_names(r, spec["only"], f"{where}.only", names)
    overrides = r.mapping(spec.get("sections", {}), f"{where}.sections", names, "section names") if spec.get("sections") is not None else {}
    base = _part(r, spec, where, instrument, None)
    if base is None:
        return None
    parts: dict[str, TrackPart] = {}
    for section in sections:
        if section.name in silent:
            if section.name in overrides:
                r.add(f"{where}.sections.{section.name}", "the track rests in this section (rest / only), so these changes never play")
            continue
        part = base
        if section.name in overrides:
            change = overrides[section.name]
            if isinstance(change, str) and change.strip() == "rest":
                r.add(f"{where}.sections.{section.name}", f"to silence the track here, list the section in rest: (rest: [{section.name}])")
                continue
            part = _part(r, r.mapping(change, f"{where}.sections.{section.name}", PART_KEYS, "changes for the section"), f"{where}.sections.{section.name}", instrument, base)
            if part is None:
                continue
        if not play_chords and part.steps is None:
            r.add(where, f"no steps for section '{section.name}': give steps (e.g. steps: \"x... x... x... x...\"), play: chords (pads), or rest: [{section.name}]")
            continue
        parts[section.name] = part
    _check_lead_holds(r, where, sections, parts, overrides, loop)
    return Track(name, instrument, play_chords, parts)


def _check_lead_holds(r: _Reader, where: str, sections: list[Section], parts: Mapping[str, TrackPart], overrides: Mapping[str, Any], loop: bool) -> None:
    """Steps starting with ``-`` hold on the note sounding when the section starts: the track
    must play in the section just before (round the loop's end for the first section)."""
    for k, section in enumerate(sections):
        part = parts.get(section.name)
        if part is None or not part.steps or part.steps[0][0].kind != "hold":
            continue
        before = sections[k - 1] if k > 0 else (sections[-1] if loop else None)
        if before is not None and before.name in parts:
            continue
        here = f"{where}.sections.{section.name}.steps" if isinstance(overrides.get(section.name), Mapping) and "steps" in overrides[section.name] else f"{where}.steps"
        if before is None:
            r.add(here, f"starts with '-' in section '{section.name}', which starts the piece (loop: false): a hold needs a note before it "
                  "(start with a note or x)")
        else:
            r.add(here, f"starts with '-' in section '{section.name}' (holding on the note the track plays when it starts), but the track rests in "
                  f"'{before.name}' just before: start with a note or x")


def _part(r: _Reader, spec: dict[str, Any], where: str, instrument: Instrument, base: TrackPart | None) -> TrackPart | None:
    """A track's part from its settings (``base`` None) or a section's changes to ``base``."""
    count = len(r.problems)
    steps = base.steps if base else None
    if "steps" in spec:
        steps = r.attempt(f"{where}.steps", parse_steps, spec["steps"], f"{where}.steps", True)
        if steps is not None and instrument.kind == "drum" and any(s.pitched for bar in steps for s in bar):
            r.add(f"{where}.steps", f"{instrument.name} has no pitch: use x, X, o, '.' and '-' (no degrees, voicing notes, notes, '*' or ' / , octave marks)")
    accent = base.accent if base else None
    if "accent" in spec:
        accent = r.attempt(f"{where}.accent", parse_accent, spec["accent"], f"{where}.accent")
    if accent is not None and steps is not None:
        for k, bar in enumerate(steps):
            if accent_steps(accent, len(bar)) is None:
                r.add(f"{where}.accent", f"groups {'+'.join(map(str, accent))} ({sum(accent)} steps) do not fill bar {k + 1} of the steps ({len(bar)} steps) a whole number of times")
                break
    octave = base.octave if base else instrument.octave
    if "octave" in spec:
        if instrument.kind == "drum":
            r.add(f"{where}.octave", f"{instrument.name} has no pitch")
        else:
            value = r.number(spec["octave"], f"{where}.octave", 0, 8, integer=True)
            octave = int(value) if value is not None else octave
    transpose = base.transpose if base else 0
    if "transpose" in spec:
        value = r.number(spec["transpose"], f"{where}.transpose", -36, 36, integer=True)
        transpose = int(value) if value is not None else transpose
        if instrument.kind == "drum":
            r.add(f"{where}.transpose", f"{instrument.name} has no pitch")
    volume = base.volume_db if base else 0.0
    volume_curve = base.volume_curve if base else None
    if "volume" in spec:
        curve = parse_curve(r, spec["volume"], f"{where}.volume", -60, 24)
        volume, volume_curve = (curve.constant or 0.0, None) if curve is not None and curve.constant is not None else (0.0, curve)
    pan = base.pan if base else 0.0
    if "pan" in spec:
        pan = r.number(spec["pan"], f"{where}.pan", -1, 1) or 0.0
    spread = base.spread if base else 0.0
    if "spread" in spec:
        spread = r.number(spec["spread"], f"{where}.spread", 0, 1) or 0.0
    effects = _effects(r, spec, where, base)
    settings = dict(base.settings) if base else {k: s.default for k, s in instrument.settings.items()}
    if "settings" in spec:
        given = r.mapping(spec["settings"], f"{where}.settings", list(instrument.settings), f"{instrument.name} settings")
        for k, v in given.items():
            s = instrument.settings[k]
            value = r.number(v, f"{where}.settings.{k}", s.low, s.high)
            if value is not None:
                settings[k] = value
    if len(r.problems) > count:
        return None
    return TrackPart(steps, accent, octave, transpose, volume, pan, settings, spread, volume_curve, **effects)


def _effects(r: _Reader, spec: dict[str, Any], where: str, base: TrackPart | None) -> dict[str, Any]:
    """The part's bus effects: the base's, changed by ``spec`` (an off value switches one off)."""
    out = {name: getattr(base, name) if base else None for name in ("width", "lowpass", "highpass", "duck", "gate", "echo", "reverb")}
    curves = {"width": (0.0, 2.0), "lowpass": (40.0, 16000.0), "highpass": (20.0, 8000.0)}
    parsers = {"duck": parse_duck, "gate": parse_gate, "echo": parse_echo, "reverb": parse_reverb}
    for name in out:
        if name not in spec:
            continue
        value, here = spec[name], f"{where}.{name}"
        if is_off(value):
            out[name] = None
        elif name in curves:
            out[name] = parse_curve(r, value, here, *curves[name])
        else:
            out[name] = parsers[name](r, value, here)
    return out


def score_outline(score: MusicScore) -> dict[str, Any]:
    """What a score holds, for ``vidgen music render``: its facts, its sections (start in
    seconds, bars, key, chord names) and its tracks (instrument, the sections they play)."""
    return {
        "title": score.title,
        "key": score.key.name,
        "tempo": score.tempo,
        "time": f"{score.time[0]}/{score.time[1]}",
        "bars": score.bars,
        "loop": score.loop,
        "seed": score.seed,
        "seconds": round(score.seconds, 3),
        "sections": [
            {
                "name": s.name,
                "start": round(score.section_start(s) / RATE, 3),
                "bars": s.bars,
                "key": s.key.name,
                "chords": [c.chord.name for c in s.chords],
            }
            for s in score.sections
        ],
        "tracks": [
            {
                "name": t.name,
                "instrument": t.instrument.name,
                "plays": "chords" if t.play_chords else "steps",
                "sections": list(t.parts),
                "effects": list(dict.fromkeys(e for p in t.parts.values() for e in p.effects)),
            }
            for t in score.tracks
        ],
    }
