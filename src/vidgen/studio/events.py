"""The notes and hits of a score file as a list, without playing it: when each
track's drum hits and notes start, how long they last, their pitches, instrument, dynamic,
stroke and slur, read the way :mod:`vidgen.studio.render` plays them (the same events, holds,
slurs, voicings and notes left out). Times are seconds from the piece's start (one pass).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vidgen.sfx import RATE
from vidgen.studio.instruments import Instrument
from vidgen.studio.render import _Event, _Skipped, _slot_at, _sub_note, _track_events, _Voicer
from vidgen.studio.score_file import MusicScore, Track, TrackPart


@dataclass(frozen=True)
class ScoreEvent:
    """One drum hit or note of a track. ``time`` and ``duration`` in seconds (the held steps);
    ``pitches`` MIDI numbers (empty for a drum); ``dynamic`` / ``dynamic_end`` the dynamic mark
    in dB at its start (with ``fp`` / ``sfz``) and at its end (0: unmarked); ``gain`` the step's
    own level (1 plain, 1.5 an accent, 0.5 soft); ``stroke`` the instrument's ``stroke`` setting
    by name when it has one; ``slur``: a note slurred from the one before (not attacked again)."""

    track: str
    instrument: str
    time: float
    duration: float
    pitches: tuple[int, ...] = ()
    dynamic: float = 0.0
    dynamic_end: float = 0.0
    gain: float = 1.0
    stroke: str | None = None
    slur: bool = False


def _stroke(instrument: Instrument, settings: Mapping[str, float]) -> str | None:
    """The ``stroke`` setting in force by its name (``spiccato``), ``None`` without one."""
    setting = instrument.settings.get("stroke")
    if setting is None or not setting.choices:
        return None
    value = int(round(settings.get("stroke", setting.default)))
    return setting.choices[value] if 0 <= value < len(setting.choices) else None


def _level_at(event: _Event, offset: int) -> tuple[float, float]:
    """The dynamic (dB) at the start and the end of the step of ``event`` that starts ``offset``
    samples after it."""
    for start, a, b in event.levels:
        if start == offset:
            return a, b
    return event.levels[-1][1], event.levels[-1][2]


def _end_level(event: _Event, upto: int) -> float:
    """The dynamic at the end of the last step of ``event`` starting before ``upto`` samples."""
    before = [b for start, _, b in event.levels if start < upto]
    return before[-1] if before else event.levels[0][2]


def _track_notes(score: MusicScore, track: Track) -> list[ScoreEvent]:
    """The events of a ``steps`` track, in the order the renderer plays them."""
    voicer = _Voicer()
    skipped = _Skipped()
    out: list[ScoreEvent] = []
    for section, part, events in _track_events(score, track):
        instrument = track.instrument_of(part)
        for event in events:
            settings = part.settings if not event.step.changes else {**part.settings, **dict(event.step.changes)}
            first, _ = _level_at(event, 0)
            first += event.step.burst
            common = {"track": track.name, "instrument": instrument.name, "gain": round(event.gain, 6), "stroke": _stroke(instrument, settings)}
            if instrument.kind == "drum":
                out.append(ScoreEvent(time=event.start / RATE, duration=event.length / RATE, dynamic=first,
                                      dynamic_end=_end_level(event, event.length), **common))
                continue
            slot = _slot_at(section, event.start) if section.chords else None
            pitches = tuple(skipped.audible(track.name, section.name, voicer.pitches(event.step, slot, part)))
            if not pitches:
                continue
            slurred = event.slurred if instrument.kind != "pad" else []
            ends = [start for start, _ in slurred] + [event.length]
            out.append(ScoreEvent(time=event.start / RATE, duration=ends[0] / RATE, pitches=pitches, dynamic=first,
                                  dynamic_end=_end_level(event, ends[0]), **common))
            for (start, step), end in zip(slurred, ends[1:]):
                at = _slot_at(section, event.start + start) if section.chords else None
                level, _ = _level_at(event, start)
                played = {**settings, **dict(step.changes)}
                out.append(ScoreEvent(time=(event.start + start) / RATE, duration=(end - start) / RATE,
                                      pitches=tuple(voicer.pitches(step, at, part))[:1], dynamic=level,
                                      dynamic_end=_end_level(event, end), slur=True,
                                      **{**common, "stroke": _stroke(instrument, played)}))
    return out


def _chord_notes(score: MusicScore, track: Track) -> list[ScoreEvent]:
    """The chords of a ``play: chords`` track: each held for its length; the same chord twice in
    a row is one (as :func:`vidgen.studio.render._render_held_chords` holds it)."""
    voicer = _Voicer()
    skipped = _Skipped()
    out: list[ScoreEvent] = []
    for section in score.sections:
        part: TrackPart | None = track.parts.get(section.name)
        if part is None:
            voicer.previous = None
            continue
        held: list[tuple[int, int, tuple[int, ...], int | None]] = []
        for slot in section.chords:
            notes = tuple(skipped.audible(track.name, section.name, voicer.chord(slot, part)))
            if held and held[-1][2] == notes and held[-1][3] == _sub_note(slot):
                start, length, _, sub = held[-1]
                held[-1] = (start, length + slot.length, notes, sub)
            else:
                held.append((slot.start, slot.length, notes, _sub_note(slot)))
        name = track.instrument_of(part).name
        out += [ScoreEvent(track.name, name, start / RATE, length / RATE, notes) for start, length, notes, _ in held if notes]
    return out


def track_kind(track: Track) -> str:
    """``drum`` (hits), ``note`` (notes), ``pad`` (held notes and chords of a pad) or ``chords``
    (a ``play: chords`` track)."""
    if track.play_chords:
        return "chords"
    return track.instrument.kind


def score_events(score: MusicScore) -> dict[str, list[ScoreEvent]]:
    """Every track's hits and notes (track name -> events by time), in the score's track order."""
    out: dict[str, list[ScoreEvent]] = {}
    for track in score.tracks:
        events = _chord_notes(score, track) if track.play_chords else _track_notes(score, track)
        out[track.name] = sorted(events, key=lambda e: e.time)
    return out


def score_facts(score: MusicScore) -> dict[str, Any]:
    """The score's grid and form as a page is given it: ``tempo`` (BPM), ``time``
    (``[4, 4]``), ``beat`` and ``bar`` (seconds), ``seconds`` (one pass), ``loop`` and
    ``sections`` (``{name, start, end}`` in seconds)."""
    return {
        "tempo": score.tempo, "time": list(score.time), "beat": score.beat / RATE, "bar": score.bar / RATE,
        "seconds": score.seconds, "loop": score.loop,
        "sections": [{"name": s.name, "start": score.section_start(s) / RATE, "end": (score.section_start(s) + s.bars * score.bar) / RATE}
                     for s in score.sections],
    }


__all__ = ["ScoreEvent", "score_events", "score_facts", "track_kind"]
