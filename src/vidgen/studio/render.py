"""Playing a score file (DESIGN.md §93): every track's notes synthesised with its instrument,
summed, through the master filter and set to :data:`vidgen.music.MUSIC_LEVEL`.

A loop is rendered circularly (a note that runs past the end continues at the start; the master
filter is an FFT over the whole loop), so it repeats without a seam; a one-shot (``loop:
false``) keeps its notes' tails after the last bar. Deterministic: the same score and seed give
the same samples.
"""

from __future__ import annotations

import bisect
import math
import zlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from vidgen.music import _add_panned, _circular_add, _finish, _hz, _pad_wave, _tone_filter, _xfade_window
from vidgen.sfx import RATE
from vidgen.studio.instruments import AIRY_HARMONICS, AIRY_WIDTH_CENTS, Instrument
from vidgen.studio.patterns import ACCENT_GAIN, Step, accent_steps
from vidgen.studio.score_file import ChordSlot, MusicScore, Section, Track, TrackPart
from vidgen.studio.theory import degree_interval, led_voicing

#: Seconds a one-shot keeps after its last bar for the notes' tails (cut where it falls silent).
TAIL_SECONDS = 8.0
#: Cross-fade between held chords (``play: chords``), seconds.
CHORD_FADE_SECONDS = 1.6
#: Length of a pad's periodic wave (5.5 s): long enough not to be heard repeating.
PAD_TABLE = 2**18
_LOWEST_HZ, _HIGHEST_HZ = 20.0, 12000.0


@dataclass
class _Event:
    """A note or hit of one track: from ``start`` for ``length`` samples (its held steps)."""

    start: int
    length: int
    step: Step
    gain: float


class _Canvas:
    """The stereo buffer a piece is summed into: circular for a loop, else linear with room
    before 0 (cut) and after the end (the tail)."""

    def __init__(self, score: MusicScore) -> None:
        self.wrap = score.loop
        self.before = 0 if self.wrap else int(CHORD_FADE_SECONDS * RATE)
        size = score.samples if self.wrap else self.before + score.samples + int(TAIL_SECONDS * RATE)
        self.data = np.zeros((size, 2))

    def add(self, start: int, sound: np.ndarray, pan: float) -> None:
        """A mono ``sound`` at ``start`` (piece samples), ``pan`` -1 left to 1 right."""
        if self.wrap:
            _add_panned(self.data, start, sound, pan)
            return
        self.add_stereo(start, sound[:, None] * np.array([1 - pan, 1 + pan]))

    def add_stereo(self, start: int, sound: np.ndarray) -> None:
        if self.wrap:
            for c in range(2):
                _circular_add(self.data[:, c], start, sound[:, c])
            return
        at = start + self.before
        lo, hi = max(at, 0), min(at + len(sound), len(self.data))
        if hi > lo:
            self.data[lo:hi] += sound[lo - at : hi - at]


def _db(volume_db: float) -> float:
    return 10 ** (volume_db / 20)


def _events(score: MusicScore, section: Section, part: TrackPart) -> list[_Event]:
    """The section's notes and hits from the part's steps (repeated from the section's start)."""
    assert part.steps is not None
    events: list[_Event] = []
    current: _Event | None = None
    for b in range(section.bars):
        steps = part.steps[b % len(part.steps)]
        accents = accent_steps(part.accent, len(steps)) if part.accent else None
        first = (section.first_bar + b) * score.bar
        for k, step in enumerate(steps):
            t0, t1 = first + round(k * score.bar / len(steps)), first + round((k + 1) * score.bar / len(steps))
            if step.kind == "hold":
                if current is not None:
                    current.length += t1 - t0
                continue
            if step.kind == "rest":
                current = None
                continue
            gain = ACCENT_GAIN if accents is not None and k in accents and not step.marked else step.gain
            current = _Event(t0, t1 - t0, step, gain)
            events.append(current)
    return events


def _slot_at(section: Section, t: int) -> ChordSlot:
    starts = [s.start for s in section.chords]
    return section.chords[max(bisect.bisect_right(starts, t) - 1, 0)]


class _Voicer:
    """The pitches of a track's notes; chords voice-led from the previous one."""

    def __init__(self) -> None:
        self.previous: tuple[int, ...] | None = None

    def chord(self, slot: ChordSlot, part: TrackPart) -> tuple[int, ...]:
        if slot.notes is not None:
            notes = slot.notes
        else:
            notes = led_voicing(slot.chord, part.octave if part.octave is not None else 3, self.previous)
        self.previous = notes
        return tuple(n + part.transpose for n in notes)

    def pitches(self, step: Step, slot: ChordSlot | None, part: TrackPart) -> tuple[int, ...]:
        octave = part.octave if part.octave is not None else 3
        if step.kind == "note":
            return (step.value + part.transpose,)
        assert slot is not None
        if step.kind == "chord":
            return self.chord(slot, part)
        if step.kind == "hit":
            note = slot.bass_note if slot.bass_note is not None else 12 * (octave + 1) + slot.chord.bass
            return (note + part.transpose,)
        root = 12 * (octave + 1) + slot.chord.root
        return (root + degree_interval(slot.chord, slot.key, step.value) + 12 * step.octaves + part.transpose,)


def _audible(midi: int) -> bool:
    return _LOWEST_HZ <= _hz(midi) <= _HIGHEST_HZ


def _render_hits(canvas: _Canvas, score: MusicScore, track: Track) -> None:
    """A drum or note track: each event synthesised alone and added at its time."""
    instrument = track.instrument
    voicer = _Voicer()
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            continue
        level = instrument.level * _db(part.volume_db)
        for event in _events(score, section, part):
            held = event.length / RATE
            if instrument.kind == "drum":
                assert instrument.make is not None
                canvas.add(event.start, instrument.make(part.settings, held) * (level * event.gain), part.pan)
                continue
            slot = _slot_at(section, event.start) if section.chords else None
            pitches = [p for p in voicer.pitches(event.step, slot, part) if _audible(p)]
            if not pitches:
                continue
            if instrument.kind == "pad":
                _add_pad_note(canvas, score, track, part, pitches, slot, event, level)
                continue
            assert instrument.make is not None
            n = int((held + part.settings["ring"]) * RATE)
            scale = level * event.gain / math.sqrt(len(pitches))
            for p in pitches:
                canvas.add(event.start, instrument.make(_hz(p), n, part.settings) * scale, part.pan)


def _pad_layers(instrument: Instrument, settings: Mapping[str, float], notes: tuple[int, ...], bass_pc: int | None, seed: str) -> np.ndarray:
    """``(PAD_TABLE, 2)``: the pad's periodic wave of ``notes`` (an airy layer an octave up and a
    sub on ``bass_pc`` in octave 2 when its settings ask), independent phases per channel."""
    tone = settings["tone"]
    out = np.zeros((PAD_TABLE, 2))
    for c in range(2):
        rng = np.random.default_rng(zlib.crc32(f"{seed}:{c}".encode("utf-8")))
        out[:, c] = _pad_wave(list(notes), PAD_TABLE, rng, instrument.harmonics, instrument.width_cents, tone)
        if settings["air"] > 0:
            upper = [n + 12 for n in (notes[1:] or notes)]
            out[:, c] += settings["air"] * _pad_wave(upper, PAD_TABLE, rng, AIRY_HARMONICS, AIRY_WIDTH_CENTS, tone)
        if settings["sub"] > 0 and bass_pc is not None:
            out[:, c] += settings["sub"] * _pad_wave([36 + bass_pc], PAD_TABLE, rng, (1.0, 0.15), 4.0, tone)
    return out


def _pan_gains(pan: float) -> np.ndarray:
    return np.array([1 - pan, 1 + pan])


def _add_pad_note(canvas: _Canvas, score: MusicScore, track: Track, part: TrackPart, pitches: list[int], slot: ChordSlot | None, event: _Event, level: float) -> None:
    """A held pad note or chord: the pad's wave with an ``attack`` fade-in and a ``release``
    fade-out after its held steps."""
    s = part.settings
    attack, release = max(int(s["attack"] * RATE), 1), max(int(s["release"] * RATE), 1)
    n = event.length + release
    t = np.arange(n)
    env = np.clip((t + 0.5) / attack, 0.0, 1.0) * np.where(t < event.length, 1.0, np.cos(0.5 * np.pi * np.clip((t - event.length) / release, 0, 1)))
    seed = f"studio:{score.seed}:{track.name}:{tuple(pitches)}"
    wave = _pad_layers(track.instrument, s, tuple(pitches), slot.chord.bass if slot else None, seed)
    sound = wave[(event.start + t) % PAD_TABLE] * env[:, None] * (level * event.gain) * _pan_gains(part.pan)
    canvas.add_stereo(event.start, sound)


def _render_held_chords(canvas: _Canvas, score: MusicScore, track: Track) -> None:
    """A ``play: chords`` track: each chord held for its length, cross-faded into the next
    (:data:`CHORD_FADE_SECONDS`); the same chord twice in a row is held on."""
    voicer = _Voicer()
    span = 0
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            voicer.previous = None
            continue
        held: list[tuple[int, int, tuple[int, ...], int]] = []
        for slot in section.chords:
            notes = voicer.chord(slot, part)
            if held and held[-1][2] == notes and held[-1][3] == slot.chord.bass:
                start, length, _, bass = held[-1]
                held[-1] = (start, length + slot.length, notes, bass)
            else:
                held.append((slot.start, slot.length, notes, slot.chord.bass))
        level = track.instrument.level * _db(part.volume_db)
        for start, length, notes, bass in held:
            fade = 2 * (min(int(CHORD_FADE_SECONDS * RATE), length) // 2)
            env = _xfade_window(length, fade)
            first = start - fade // 2
            wave = _pad_layers(track.instrument, part.settings, notes, bass, f"studio:{score.seed}:{track.name}:span{span}")
            span += 1
            idx = (first + np.arange(length + fade)) % PAD_TABLE
            canvas.add_stereo(first, wave[idx] * env[:, None] * level * _pan_gains(part.pan))


def _one_shot_end(x: np.ndarray, bar_end: int) -> np.ndarray:
    """A one-shot cut where its tail falls silent (at least to its last bar), with short fades."""
    loudest = float(np.abs(x).max()) or 1.0
    audible = np.flatnonzero(np.abs(x).max(axis=1) > loudest * 1e-4)
    end = max(bar_end, int(audible[-1]) + 1 if len(audible) else bar_end)
    end = min(len(x), end + int(0.05 * RATE))
    y = x[:end].copy()
    fade_in, fade_out = int(0.005 * RATE), int(0.05 * RATE)
    y[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    y[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return y


def render_music_score(score: MusicScore) -> np.ndarray:
    """The score's audio: float32 ``(n, 2)`` at 48 kHz, -28 LUFS integrated, read-only. A loop
    is exactly ``score.samples`` long; a one-shot adds the tails after its last bar."""
    canvas = _Canvas(score)
    for track in score.tracks:
        if track.play_chords:
            _render_held_chords(canvas, score, track)
        else:
            _render_hits(canvas, score, track)
    if canvas.wrap:
        return _finish(_tone_filter(canvas.data, score.lowpass, score.highpass))
    x = canvas.data[canvas.before :]
    padded = np.concatenate([x, np.zeros((RATE, 2))])
    filtered = _tone_filter(padded, score.lowpass, score.highpass)[: len(x)]
    return _finish(_one_shot_end(filtered, score.samples))
