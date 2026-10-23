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
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass

import numpy as np

from vidgen.music import _add_panned, _circular_add, _finish, _hz, _level_gain, _pad_wave, _tone_filter, _xfade_window
from vidgen.sfx import RATE, _highpass, _lowpass
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
    return _events_and_last(score, section, steps, accent, None)[0]


def _events_and_last(
    score: MusicScore, section: Section, steps: Pattern, accent: tuple[int, ...] | None, carry: _Event | None
) -> tuple[list[_Event], _Event | None]:
    """:func:`_events` and the note still sounding at the section's end (``None`` after a rest).
    ``carry``: the note sounding when the section starts (the section before's last); holds
    (``-``) before the section's first note or rest extend it (DESIGN.md §93.13)."""
    events: list[_Event] = []
    current: _Event | None = carry
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
    return events, current


def _slot_at(section: Section, t: int) -> ChordSlot:
    starts = [s.start for s in section.chords]
    return section.chords[max(bisect.bisect_right(starts, t) - 1, 0)]


class _Voicer:
    """The pitches of a track's notes; chords voice-led from the previous one."""

    def __init__(self) -> None:
        self.previous: tuple[int, ...] | None = None
        self.voiced: tuple[ChordSlot, TrackPart, tuple[int, ...]] | None = None

    def chord(self, slot: ChordSlot, part: TrackPart) -> tuple[int, ...]:
        if slot.notes is not None:
            notes = slot.notes
        else:
            notes = led_voicing(slot.chord, part.octave if part.octave is not None else 3, self.previous)
        self.previous = notes
        return tuple(n + part.transpose for n in notes)

    def voicing(self, slot: ChordSlot, part: TrackPart) -> tuple[int, ...]:
        """The chord as ``*`` plays it, voiced once per chord (``v1``-``v9`` pick from it)."""
        if self.voiced is None or self.voiced[0] is not slot or self.voiced[1] is not part:
            self.voiced = (slot, part, tuple(sorted(self.chord(slot, part))))
        return self.voiced[2]

    def pitches(self, step: Step, slot: ChordSlot | None, part: TrackPart) -> tuple[int, ...]:
        octave = part.octave if part.octave is not None else 3
        if step.kind == "note":
            return (step.value + part.transpose,)
        assert slot is not None
        if step.kind == "stack":
            return tuple(p for s in step.parts for p in self.pitches(s, slot, part))
        if step.kind == "chord":
            return self.chord(slot, part)
        if step.kind == "voice":
            notes = self.voicing(slot, part)
            k = step.value - 1
            return (notes[k % len(notes)] + 12 * (k // len(notes) + step.octaves),)
        if step.kind == "hit":
            note = slot.bass_note if slot.bass_note is not None else 12 * (octave + 1) + slot.chord.bass
            return (note + 12 * step.octaves + part.transpose,)
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


def _track_events(score: MusicScore, track: Track) -> list[tuple[Section, TrackPart, list[_Event]]]:
    """Each section's part and notes of a ``steps`` track. A note held (``-``) at the start of
    the next section the track plays in (right after it) goes on sounding — around the loop's end
    into the first section's leading holds too; it keeps the sound of the section it started in."""
    out: list[tuple[Section, TrackPart, list[_Event]]] = []
    carry: _Event | None = None
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            carry = None
            continue
        assert part.steps is not None
        events, carry = _events_and_last(score, section, part.steps, part.accent, carry)
        out.append((section, part, events))
    if score.loop and carry is not None and out[0][0] is score.sections[0]:
        first, part, _ = out[0]
        assert part.steps is not None
        _events_and_last(score, first, part.steps, part.accent, carry)  # only its leading holds matter: they extend `carry`
    return out


def _render_hits(canvas_for: CanvasFor, score: MusicScore, track: Track, skipped: _Skipped) -> None:
    """A drum or note track: each event synthesised alone and added at its time."""
    instrument = track.instrument
    voicer = _Voicer()
    drums: dict[tuple[object, ...], np.ndarray] = {}
    for section, part, events in _track_events(score, track):
        canvas = canvas_for(section.name)
        level = instrument.level * _db(part.volume_db)
        for event in events:
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


def _sub_note(slot: ChordSlot | None) -> int | None:
    """The pad's sub: the chord's written bass note, else its bass in octave 2."""
    if slot is None:
        return None
    return slot.bass_note if slot.bass_note is not None else 36 + slot.chord.bass


def _pad_layers(
    instrument: Instrument, settings: Mapping[str, float], notes: tuple[int, ...], sub_note: int | None, seed: str
) -> tuple[np.ndarray, np.ndarray | None]:
    """``(PAD_TABLE, 2)`` waves: the pad's periodic wave of ``notes`` (an airy layer an octave up
    and a sub on ``sub_note`` when its settings ask), independent phases per channel (wide) but
    the same sub in both (centred, as the beds') — with ``sub_width`` > 0 the right side's sub is
    cross-faded towards its own phases (1: each side its own, Step 185's sound); and, when the pad
    swells (``swell`` > 0), the airy layer on its own (``None`` otherwise)."""
    tone = settings["tone"]
    out = np.zeros((PAD_TABLE, 2))
    airy = np.zeros((PAD_TABLE, 2)) if settings["swell"] > 0 else None
    sub: np.ndarray | None = None
    for c in range(2):
        rng = np.random.default_rng(zlib.crc32(f"{seed}:{c}".encode("utf-8")))
        out[:, c] = _pad_wave(list(notes), PAD_TABLE, rng, instrument.harmonics, settings["detune"], tone)
        if settings["air"] > 0:
            upper = [n + 12 for n in (notes[1:] or notes)]
            layer = settings["air"] * _pad_wave(upper, PAD_TABLE, rng, AIRY_HARMONICS, AIRY_WIDTH_CENTS, tone)
            if airy is None:
                out[:, c] += layer
            else:
                airy[:, c] = layer
        if settings["sub"] > 0 and sub_note is not None:
            width = settings["sub_width"]
            if sub is None:
                sub = settings["sub"] * _pad_wave([sub_note], PAD_TABLE, rng, (1.0, 0.15), 4.0, tone)
                out[:, c] += sub
            elif width == 0:
                out[:, c] += sub
            else:
                own = settings["sub"] * _pad_wave([sub_note], PAD_TABLE, rng, (1.0, 0.15), 4.0, tone)
                out[:, c] += own if width == 1 else (1 - width) * sub + width * own
    return out, airy


def _pad_sound(score: MusicScore, settings: Mapping[str, float], waves: tuple[np.ndarray, np.ndarray | None], first: int, n: int) -> np.ndarray:
    """``n`` samples of a pad's waves from piece sample ``first`` on; the airy layer swelling
    from silence to full and back every ``swell`` bars (counted from the piece's start)."""
    wave, airy = waves
    at = first + np.arange(n)
    sound = wave[at % PAD_TABLE]
    if airy is not None:
        sound = sound + airy[at % PAD_TABLE] * (0.5 - 0.5 * np.cos(2 * np.pi * at / (settings["swell"] * score.bar)))[:, None]
    return sound


def _add_pad_note(canvas: _Canvas, score: MusicScore, track: Track, part: TrackPart, pitches: list[int], slot: ChordSlot | None, event: _Event, level: float) -> None:
    """A held pad note or chord: the pad's wave with an ``attack`` fade-in and a ``release``
    fade-out after its held steps."""
    s = part.settings
    attack, release = max(int(s["attack"] * RATE), 1), max(int(s["release"] * RATE), 1)
    n = event.length + release
    t = np.arange(n)
    env = np.clip((t + 0.5) / attack, 0.0, 1.0) * np.where(t < event.length, 1.0, np.cos(0.5 * np.pi * np.clip((t - event.length) / release, 0, 1)))
    seed = f"studio:{score.seed}:{track.name}:{tuple(pitches)}"
    waves = _pad_layers(track.instrument, s, tuple(pitches), _sub_note(slot), seed)
    sound = _pad_sound(score, s, waves, event.start, n) * env[:, None] * (level * event.gain) * _pan_gains(part.pan)
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
        held: list[tuple[int, int, tuple[int, ...], int | None]] = []
        for slot in section.chords:
            notes = tuple(skipped.audible(track.name, section.name, voicer.chord(slot, part)))
            if held and held[-1][2] == notes and held[-1][3] == _sub_note(slot):
                start, length, _, sub = held[-1]
                held[-1] = (start, length + slot.length, notes, sub)
            else:
                held.append((slot.start, slot.length, notes, _sub_note(slot)))
        level = track.instrument.level * _db(part.volume_db)
        canvas = canvas_for(section.name)
        for start, length, notes, sub in held:
            if not notes:
                continue
            fade = 2 * (min(int(part.settings["fade"] * RATE), length) // 2)
            env = _xfade_window(length, fade)
            first = start - fade // 2
            waves = _pad_layers(track.instrument, part.settings, notes, sub, f"studio:{score.seed}:{track.name}:span{span}")
            span += 1
            sound = _pad_sound(score, part.settings, waves, first, length + fade)
            canvas.add_stereo(first, sound * env[:, None] * level * _pan_gains(part.pan))


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


def _hit_times(score: MusicScore, tracks: Mapping[str, Track], name: str) -> list[tuple[int, float]]:
    """When track ``name`` sounds (its hits and notes; its chords for ``play: chords``), or
    every beat for ``beat``, with each hit's level (1 a plain hit, 1.5 an accent, 0.5 soft)."""
    if name == "beat":
        return [(t, 1.0) for t in range(0, score.samples, score.beat)]
    track = tracks[name]
    times: list[tuple[int, float]] = []
    for section in score.sections:
        part = track.parts.get(section.name)
        if part is None:
            continue
        if part.steps is None:
            times.extend((s.start, 1.0) for s in section.chords)
        else:
            times.extend((e.start, e.gain) for e in _events(score, section, part.steps, part.accent))
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
        for t, level in _hit_times(score, tracks, part.duck.to):
            if a <= t < b:
                this = dip * level if part.duck.follow and level != 1.0 else dip
                if score.loop:
                    _circular_add(dips, t, this)
                else:
                    end = min(t + len(this), score.samples)
                    dips[t:end] += this[: end - t]
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


@dataclass(frozen=True)
class TrackStem:
    """One track played alone (DESIGN.md §94.6, Step 196): ``data`` float64 ``(n, 2)``, read-only,
    on the piece's canvas — ``score.samples`` for a loop; for a one-shot :data:`BEFORE_SECONDS`
    of room before the start (``before`` samples), the piece, and :data:`TAIL_SECONDS` of tail —
    before the master filter and the level. ``skipped``: the notes left out (outside 20 Hz-12
    kHz) per ``(track, section)``, for the warnings."""

    name: str
    data: np.ndarray
    before: int
    skipped: Mapping[tuple[str, str], tuple[int, ...]]

    @property
    def piece(self) -> np.ndarray:
        """The stem from the piece's start (a one-shot's tail included)."""
        return self.data[self.before :]


def render_track_stem(score: MusicScore, name: str) -> TrackStem:
    """Track ``name`` of ``score`` played alone, as :func:`render_music_score` plays it (the
    same notes and effects; see :func:`mix_track_stems` on rounding). A track's sound depends on the score's shared data (key,
    tempo, time, seed, loop, sections, chords), its own spec and, when it ducks, the hits of the
    track it ducks under — nothing else."""
    tracks = {t.name: t for t in score.tracks}
    track = tracks[name]
    skipped = _Skipped()
    alone = _Canvas(score)
    if _uses_bus(track):
        alone.data += _render_bus(score, track, tracks, skipped)
    elif track.play_chords:
        _render_held_chords(lambda section: alone, score, track, skipped)
    else:
        _render_hits(lambda section: alone, score, track, skipped)
    alone.data.setflags(write=False)
    return TrackStem(name, alone.data, alone.before, {k: tuple(v) for k, v in skipped.notes.items()})


@dataclass(frozen=True)
class MixFacts:
    """How a mix of stems was finished: the linear ``gain`` that set the whole piece to -28 LUFS
    and its length in samples (``samples``; a one-shot cut where its tail falls silent) — what a
    listening mix of some of its tracks reuses, so it plays at the piece's level and length."""

    gain: float
    samples: int


def _master_filter(x: np.ndarray, score: MusicScore, threads: int) -> np.ndarray:
    """:func:`vidgen.music._tone_filter` with the score's master settings — with ``threads`` > 1
    each channel on its own thread (numpy's FFT lets go of the GIL), bit for bit the same."""
    if threads <= 1:
        return _tone_filter(x, score.lowpass, score.highpass)
    from concurrent.futures import ThreadPoolExecutor

    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    response = _highpass(freqs, score.highpass, 2) * _lowpass(freqs, score.lowpass, 2)
    with ThreadPoolExecutor(min(threads, x.shape[1])) as pool:
        channels = list(pool.map(lambda c: np.fft.irfft(np.fft.rfft(x[:, c]) * response, len(x)), range(x.shape[1])))
    return np.stack(channels, axis=1)


def mix_track_stems(
    score: MusicScore, stems: Iterable[TrackStem], warnings: list[str] | None = None, whole: MixFacts | None = None, threads: int = 1
) -> tuple[np.ndarray, MixFacts]:
    """The stems summed in the order given, through the master filter and set to -28 LUFS (its
    own loudness measured, as :func:`render_music_score` does): float32 ``(n, 2)``, read-only,
    and how it was finished. Every track's stem in the score's order gives
    :func:`render_music_score`'s samples but for the order floats were added in plain tracks
    (at most 1 float32 step in a few samples; the same 16-bit audio). ``whole``: the
    facts of the whole piece's mix — then the stems (some of the tracks: a listening mix) are
    set to its gain and cut at its length with the same fades (a one-shot keeps its tails),
    so leaving a track out never makes the rest louder. One stem at a time is held besides the
    sum (``stems`` may be a generator). ``threads``: the master filter and the loudness on that
    many threads (the same samples)."""
    canvas = _Canvas(score)
    skipped = _Skipped()
    for stem in stems:
        canvas.data += stem.data
        for where, notes in stem.skipped.items():
            skipped.notes.setdefault(where, []).extend(notes)
    if warnings is not None:
        warnings.extend(skipped.warnings())
    if canvas.wrap:
        x = _master_filter(canvas.data, score, threads)
    else:
        rest = canvas.data[canvas.before :]
        filtered = _master_filter(np.concatenate([rest, np.zeros((RATE, 2))]), score, threads)[: len(rest)]
        x = _one_shot_end(filtered, score.samples) if whole is None else _cut(filtered, whole.samples)
    if whole is not None:
        return _finish(x, whole.gain), whole
    gain = _level_gain(x, threads)
    return _finish(x, gain), MixFacts(gain, len(x))


def _cut(x: np.ndarray, end: int) -> np.ndarray:
    """A one-shot's listening mix cut at the whole piece's ``end`` with :func:`_one_shot_end`'s fades."""
    y = np.concatenate([x[:end], np.zeros((max(end - len(x), 0), 2))])
    fade_in, fade_out = int(0.005 * RATE), int(0.05 * RATE)
    y[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    y[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return y


def render_music_score(score: MusicScore, warnings: list[str] | None = None) -> np.ndarray:
    """The score's audio: float32 ``(n, 2)`` at 48 kHz, -28 LUFS integrated, read-only. A loop
    is exactly ``score.samples`` long; a one-shot adds the tails after its last bar. Notes
    outside 20 Hz-12 kHz are left out and, when ``warnings`` is given, described in it.

    A plain track's notes are added straight into the piece (a track with effects as one sum),
    so :func:`mix_track_stems` of the same tracks differs from this only in the order floats
    were added: at most 1 float32 step in a few samples of a piece (DESIGN.md §94.14). These
    samples are kept as they were (the beds' and projects' music must not change)."""
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


def render_music_stems(score: MusicScore, on_stem: Callable[[str, np.ndarray], None], warnings: list[str] | None = None) -> tuple[np.ndarray, float]:
    """The score played track by track (for ``vidgen music check``, §93.9): every track is
    rendered alone and handed to ``on_stem(name, sound)`` (float64 ``(n, 2)``, its one pass of
    ``score.samples``, *before* the master filter and the final level), then summed. Returns
    the mix (:func:`mix_track_stems`: :func:`render_music_score`'s within rounding) and the
    linear gain that set it to -28 LUFS
    (to apply to the stems' measures, with the master filter's response). One track's buffer at
    a time, so memory stays that of a render."""

    def stems() -> Iterator[TrackStem]:
        for track in score.tracks:
            stem = render_track_stem(score, track.name)
            on_stem(track.name, stem.data[stem.before : stem.before + score.samples])
            yield stem

    out, facts = mix_track_stems(score, stems(), warnings)
    return out, facts.gain
