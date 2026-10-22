"""Playing a score file (DESIGN.md §93.6-93.7): every track's notes synthesised with its
instrument, the track's effects applied to its own sound, all summed, through the master filter
and set to :data:`vidgen.music.MUSIC_LEVEL`.

A loop is rendered circularly (a note, echo or reverb tail that runs past the end continues at
the start; filters are FFTs over the whole loop), so it repeats without a seam; a one-shot
(``loop: false``) keeps its tails after the last bar. Deterministic: the same score and seed
give the same samples.
"""

from __future__ import annotations

import bisect
import math
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from vidgen.music import _add_panned, _circular_add, _finish, _hz, _pad_wave, _tone_filter, _xfade_window
from vidgen.sfx import RATE
from vidgen.studio import effects as fx
from vidgen.studio.instruments import AIRY_HARMONICS, AIRY_WIDTH_CENTS, Instrument
from vidgen.studio.patterns import ACCENT_GAIN, Pattern, Step, accent_steps
from vidgen.studio.score_file import ChordSlot, MusicScore, Section, Track, TrackPart
from vidgen.studio.theory import degree_interval, led_voicing, note_name

#: Seconds a one-shot keeps after its last bar for the notes' tails (cut where it falls silent).
TAIL_SECONDS = 8.0
#: Room before a one-shot's start for the first chord's cross-fade, seconds (longer fades are cut).
BEFORE_SECONDS = 1.6
#: Length of a pad's periodic wave (5.5 s): long enough not to be heard repeating.
PAD_TABLE = 2**18
#: The notes played: others are left out with a warning.
LOWEST_HZ, HIGHEST_HZ = 20.0, 12000.0


@dataclass
class _Event:
    """A note or hit of one track: from ``start`` for ``length`` samples (its held steps);
    ``index``: its step in the bar; ``unit``: the length of its last step."""

    start: int
    length: int
    step: Step
    gain: float
    index: int
    unit: int


class _Canvas:
    """A stereo buffer a piece (or one track) is summed into: circular for a loop, else linear
    with room before 0 (cut) and after the end (the tail)."""

    def __init__(self, score: MusicScore) -> None:
        self.wrap = score.loop
        self.before = 0 if self.wrap else int(BEFORE_SECONDS * RATE)
        size = score.samples if self.wrap else self.before + score.samples + int(TAIL_SECONDS * RATE)
        self.data = np.zeros((size, 2))

    def add(self, start: int, sound: np.ndarray, pan: float) -> None:
        """A mono or stereo ``sound`` at ``start`` (piece samples), ``pan`` -1 left to 1 right."""
        if sound.ndim == 2:
            self.add_stereo(start, sound * _pan_gains(pan))
        elif self.wrap:
            _add_panned(self.data, start, sound, pan)
        else:
            self.add_stereo(start, sound[:, None] * _pan_gains(pan))

    def add_stereo(self, start: int, sound: np.ndarray) -> None:
        if self.wrap:
            for c in range(2):
                _circular_add(self.data[:, c], start, sound[:, c])
            return
        at = start + self.before
        lo, hi = max(at, 0), min(at + len(sound), len(self.data))
        if hi > lo:
            self.data[lo:hi] += sound[lo - at : hi - at]

    def stretch(self, piece: np.ndarray) -> np.ndarray:
        """A per-sample curve over the piece (``score.samples``) over this canvas's length: its
        first value before the start, its last after the end."""
        if self.wrap:
            return piece
        return np.concatenate([np.full(self.before, piece[0]), piece, np.full(len(self.data) - self.before - len(piece), piece[-1])])


def _db(volume_db: float) -> float:
    return 10 ** (volume_db / 20)


def _pan_gains(pan: float) -> np.ndarray:
    return np.array([1 - pan, 1 + pan])


def _events(score: MusicScore, section: Section, steps: Pattern, accent: tuple[int, ...] | None) -> list[_Event]:
    """The section's notes and hits from ``steps`` (repeated from the section's start)."""
    events: list[_Event] = []
    current: _Event | None = None
    for b in range(section.bars):
        bar_steps = steps[b % len(steps)]
        accents = accent_steps(accent, len(bar_steps)) if accent else None
        first = (section.first_bar + b) * score.bar
        for k, step in enumerate(bar_steps):
            t0, t1 = first + round(k * score.bar / len(bar_steps)), first + round((k + 1) * score.bar / len(bar_steps))
            if step.kind == "hold":
                if current is not None:
                    current.length += t1 - t0
                    current.unit = t1 - t0
                continue
            if step.kind == "rest":
                current = None
                continue
            gain = ACCENT_GAIN if accents is not None and k in accents and not step.marked else step.gain
            current = _Event(t0, t1 - t0, step, gain, k, t1 - t0)
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


class _Skipped:
    """Notes left out because they are outside :data:`LOWEST_HZ`-:data:`HIGHEST_HZ`, per track
    and section, for the warnings."""

    def __init__(self) -> None:
        self.notes: dict[tuple[str, str], list[int]] = {}

    def audible(self, track: str, section: str, pitches: tuple[int, ...]) -> list[int]:
        kept = [p for p in pitches if LOWEST_HZ <= _hz(p) <= HIGHEST_HZ]
        if len(kept) < len(pitches):
            self.notes.setdefault((track, section), []).extend(p for p in pitches if p not in kept)
        return kept

    def warnings(self) -> list[str]:
        out = []
        for (track, section), notes in self.notes.items():
            low, high = min(notes), max(notes)
            which = note_name(low) if low == high else f"{note_name(low)} to {note_name(high)}"
            out.append(
                f"tracks.{track}: {len(notes)} note{'s' if len(notes) != 1 else ''} in section '{section}' left out ({which}, "
                f"{_hz(low):.0f}{'' if low == high else f'-{_hz(high):.0f}'} Hz; vidgen plays {LOWEST_HZ:.0f} Hz to {HIGHEST_HZ / 1000:.0f} kHz): "
                "change the track's octave or transpose"
            )
        return out


CanvasFor = Callable[[str], _Canvas]


def _render_hits(canvas_for: CanvasFor, score: MusicScore, track: Track, skipped: _Skipped) -> None:
    """A drum or note track: each event synthesised alone and added at its time."""
    instrument = track.instrument
    voicer = _Voicer()
    drums: dict[tuple[object, ...], np.ndarray] = {}
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            continue
        assert part.steps is not None
        canvas = canvas_for(section.name)
        level = instrument.level * _db(part.volume_db)
        for event in _events(score, section, part.steps, part.accent):
            held = event.length / RATE
            pan = float(np.clip(part.pan + (part.spread if event.index % 2 else -part.spread), -1, 1))
            if instrument.kind == "drum":
                assert instrument.make is not None
                key = (tuple(sorted(part.settings.items())), event.length)
                if key not in drums:
                    drums[key] = instrument.make(part.settings, held)
                canvas.add(event.start, drums[key] * (level * event.gain), pan)
                continue
            slot = _slot_at(section, event.start) if section.chords else None
            pitches = skipped.audible(track.name, section.name, voicer.pitches(event.step, slot, part))
            if not pitches:
                continue
            if instrument.kind == "pad":
                _add_pad_note(canvas, score, track, part, pitches, slot, event, level)
                continue
            assert instrument.make is not None
            n = int((held + part.settings.get("ring", 0.0)) * RATE)
            scale = level * event.gain / math.sqrt(len(pitches))
            for p in pitches:
                canvas.add(event.start, instrument.make(_hz(p), n, part.settings) * scale, pan)


def _pad_layers(instrument: Instrument, settings: Mapping[str, float], notes: tuple[int, ...], bass_pc: int | None, seed: str) -> np.ndarray:
    """``(PAD_TABLE, 2)``: the pad's periodic wave of ``notes`` (an airy layer an octave up and a
    sub on ``bass_pc`` in octave 2 when its settings ask), independent phases per channel."""
    tone = settings["tone"]
    out = np.zeros((PAD_TABLE, 2))
    for c in range(2):
        rng = np.random.default_rng(zlib.crc32(f"{seed}:{c}".encode("utf-8")))
        out[:, c] = _pad_wave(list(notes), PAD_TABLE, rng, instrument.harmonics, settings["detune"], tone)
        if settings["air"] > 0:
            upper = [n + 12 for n in (notes[1:] or notes)]
            out[:, c] += settings["air"] * _pad_wave(upper, PAD_TABLE, rng, AIRY_HARMONICS, AIRY_WIDTH_CENTS, tone)
        if settings["sub"] > 0 and bass_pc is not None:
            out[:, c] += settings["sub"] * _pad_wave([36 + bass_pc], PAD_TABLE, rng, (1.0, 0.15), 4.0, tone)
    return out


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


def _render_held_chords(canvas_for: CanvasFor, score: MusicScore, track: Track, skipped: _Skipped) -> None:
    """A ``play: chords`` track: each chord held for its length, cross-faded into the next over
    the ``fade`` setting; the same chord twice in a row is held on."""
    voicer = _Voicer()
    span = 0
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            voicer.previous = None
            continue
        held: list[tuple[int, int, tuple[int, ...], int]] = []
        for slot in section.chords:
            notes = tuple(skipped.audible(track.name, section.name, voicer.chord(slot, part)))
            if held and held[-1][2] == notes and held[-1][3] == slot.chord.bass:
                start, length, _, bass = held[-1]
                held[-1] = (start, length + slot.length, notes, bass)
            else:
                held.append((slot.start, slot.length, notes, slot.chord.bass))
        level = track.instrument.level * _db(part.volume_db)
        canvas = canvas_for(section.name)
        for start, length, notes, bass in held:
            if not notes:
                continue
            fade = 2 * (min(int(part.settings["fade"] * RATE), length) // 2)
            env = _xfade_window(length, fade)
            first = start - fade // 2
            wave = _pad_layers(track.instrument, part.settings, notes, bass, f"studio:{score.seed}:{track.name}:span{span}")
            span += 1
            idx = (first + np.arange(length + fade)) % PAD_TABLE
            canvas.add_stereo(first, wave[idx] * env[:, None] * level * _pan_gains(part.pan))


# ----- the track's effects ---------------------------------------------------------------------


def _uses_bus(track: Track) -> bool:
    return any(p.volume_curve is not None or any(getattr(p, n) is not None for n in fx.BUS_EFFECTS) for p in track.parts.values())


def _piece_curve(score: MusicScore, track: Track, get: Callable[[TrackPart], fx.Curve | None], default: float) -> np.ndarray | None:
    """A per-sample curve over the piece from each section's part (``default`` where the part
    has none, the neighbouring sections' values where the track rests), smoothed; ``None``
    when no part has one."""
    if all(get(p) is None for p in track.parts.values()):
        return None
    out = np.full(score.samples, np.nan)
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            continue
        a, n = score.section_start(section), section.bars * score.bar
        curve = get(part)
        out[a : a + n] = curve.samples(n, score.bar) if curve is not None else default
    known = np.flatnonzero(~np.isnan(out))
    out = np.interp(np.arange(score.samples), known, out[known]) if len(known) < len(out) else out
    return fx.smooth(out, fx.SMOOTH_SECONDS, score.loop)


def _filter_curve(score: MusicScore, track: Track, kind: str) -> tuple[np.ndarray, np.ndarray] | None:
    """The track's ``lowpass`` / ``highpass`` cutoff over the piece (smoothed in octaves; where
    no section sets one, the nearest section's) and how much of the sound passes unfiltered
    (1 in the sections that play without the filter, smoothed); ``None`` when no part filters."""
    if all(getattr(p, kind) is None for p in track.parts.values()):
        return None
    cutoff = np.full(score.samples, np.nan)
    unfiltered = np.zeros(score.samples)
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            continue
        a, n = score.section_start(section), section.bars * score.bar
        curve = getattr(part, kind)
        if curve is None:
            unfiltered[a : a + n] = 1.0
        else:
            cutoff[a : a + n] = curve.samples(n, score.bar, octaves=True)
    known = np.flatnonzero(~np.isnan(cutoff))
    cutoff = np.interp(np.arange(score.samples), known, cutoff[known])
    return np.exp(fx.smooth(np.log(cutoff), fx.SMOOTH_SECONDS, score.loop)), fx.smooth(unfiltered, fx.SMOOTH_SECONDS, score.loop)


def _hit_times(score: MusicScore, tracks: Mapping[str, Track], name: str) -> list[int]:
    """When track ``name`` sounds (its hits and notes; its chords for ``play: chords``), or
    every beat for ``beat``."""
    if name == "beat":
        return list(range(0, score.samples, score.beat))
    track = tracks[name]
    times: list[int] = []
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            continue
        if part.steps is None:
            times.extend(s.start for s in section.chords)
        else:
            times.extend(e.start for e in _events(score, section, part.steps, part.accent))
    return times


def _duck_gain(score: MusicScore, track: Track, tracks: Mapping[str, Track]) -> np.ndarray | None:
    """The track's side-chain gain over the piece: a dip at every hit of the track it ducks to,
    in the sections where it ducks."""
    if all(p.duck is None for p in track.parts.values()):
        return None
    dips = np.zeros(score.samples)
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None or part.duck is None:
            continue
        a, b = score.section_start(section), score.section_start(section) + section.bars * score.bar
        dip = fx.duck_dip(part.duck.depth, part.duck.release, 2 * score.beat)
        for t in _hit_times(score, tracks, part.duck.to):
            if a <= t < b:
                if score.loop:
                    _circular_add(dips, t, dip)
                else:
                    end = min(t + len(dip), score.samples)
                    dips[t:end] += dip[: end - t]
    return np.clip(1.0 - dips, 0.0, 1.0)


def _gate_gain(score: MusicScore, track: Track) -> np.ndarray | None:
    """The track's gate over the piece: open on the gate pattern's hits in the sections that
    gate it, ``floor`` between them; 1 elsewhere."""
    if all(p.gate is None for p in track.parts.values()):
        return None
    gain = np.ones(score.samples)
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None or part.gate is None:
            continue
        a, n = score.section_start(section), section.bars * score.bar
        opened = np.zeros(n)
        for e in _events(score, section, part.gate.steps, None):
            window = fx.gate_window(max(e.length - round((1 - part.gate.duty) * e.unit), 1), 1.0 if e.gain >= 1 else fx.GATE_SOFT)
            at, end = e.start - a, min(e.start - a + len(window), n)
            opened[at:end] = np.maximum(opened[at:end], window[: end - at])
        gain[a : a + n] = part.gate.floor + (1 - part.gate.floor) * opened
    return fx.smooth(gain, fx.GATE_ATTACK, score.loop)  # no click where a gated section starts or ends


def _bus_group(part: TrackPart) -> tuple[object, ...]:
    return (part.echo, part.reverb)


def _render_bus(score: MusicScore, track: Track, tracks: Mapping[str, Track], skipped: _Skipped) -> np.ndarray:
    """A track with effects, on its own buffer: its notes summed per echo / reverb setting (so
    each section's notes get their own), the echoes and reverb added, then its filters, gate,
    ducking, volume curve and width along the piece."""
    groups: dict[tuple[object, ...], _Canvas] = {}

    def canvas_for(name: str) -> _Canvas:
        return groups.setdefault(_bus_group(track.parts[name]), _Canvas(score))

    (_render_held_chords if track.play_chords else _render_hits)(canvas_for, score, track, skipped)
    shape = next(iter(groups.values()))  # every group's canvas has the piece's layout
    bus = np.zeros_like(shape.data)
    for k, ((echo, reverb), canvas) in enumerate(groups.items()):
        x = canvas.data
        if isinstance(echo, fx.Echo):
            x = fx.echo(x, echo, score.beat, canvas.wrap)
        if isinstance(reverb, fx.Reverb):
            x = fx.reverb(x, reverb, canvas.wrap, f"studio:{score.seed}:{track.name}:reverb{k}")
        bus += x
    for kind in ("lowpass", "highpass"):
        found = _filter_curve(score, track, kind)
        if found is not None:
            cutoff, unfiltered = (shape.stretch(c) for c in found)
            filtered = fx.swept_filter(bus, cutoff, kind)
            bus = filtered if not unfiltered.any() else filtered * (1 - unfiltered[:, None]) + bus * unfiltered[:, None]
    gain = np.ones(len(bus))
    for curve in (_gate_gain(score, track), _duck_gain(score, track, tracks)):
        if curve is not None:
            gain *= shape.stretch(curve)
    volume = _piece_curve(score, track, lambda p: p.volume_curve, 0.0)
    if volume is not None:
        gain *= shape.stretch(10 ** (volume / 20))
    bus = bus * gain[:, None]
    width = _piece_curve(score, track, lambda p: p.width, 1.0)
    return fx.widen(bus, shape.stretch(width)) if width is not None else bus


# ----- the piece -------------------------------------------------------------------------------


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


def render_music_score(score: MusicScore, warnings: list[str] | None = None) -> np.ndarray:
    """The score's audio: float32 ``(n, 2)`` at 48 kHz, -28 LUFS integrated, read-only. A loop
    is exactly ``score.samples`` long; a one-shot adds the tails after its last bar. Notes
    outside 20 Hz-12 kHz are left out and, when ``warnings`` is given, described in it."""
    canvas = _Canvas(score)
    tracks = {t.name: t for t in score.tracks}
    skipped = _Skipped()
    for track in score.tracks:
        if _uses_bus(track):
            canvas.data += _render_bus(score, track, tracks, skipped)
        elif track.play_chords:
            _render_held_chords(lambda name: canvas, score, track, skipped)
        else:
            _render_hits(lambda name: canvas, score, track, skipped)
    if warnings is not None:
        warnings.extend(skipped.warnings())
    if canvas.wrap:
        return _finish(_tone_filter(canvas.data, score.lowpass, score.highpass))
    x = canvas.data[canvas.before :]
    padded = np.concatenate([x, np.zeros((RATE, 2))])
    filtered = _tone_filter(padded, score.lowpass, score.highpass)[: len(x)]
    return _finish(_one_shot_end(filtered, score.samples))
