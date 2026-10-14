"""Composed music that follows the video (DESIGN.md §84). A ``compose:`` cue without ``bars`` is
composed for the real timings of the video it plays under:

- it lasts exactly as long as the cue, and every scene change falls on a bar line: each scene
  gets a whole number of bars and its own tempo, at most :data:`TEMPO_LIMIT` away from the
  mood's; when even that cannot fill the scene, the scene's last bar slows down into a held
  chord (a *hold*); a scene shorter than one bar shares its bars with the next scene;
- a scene's own ``music: {mood: ...}`` (or ``key``, ``tempo``, ``instruments``, ``seed``)
  changes the music at that scene's first bar, for that scene only;
- a beat that reveals something (the scene's own reveal, a written ``reveal`` action, a
  ``sting: reveal``) gets a small swell: the notes before it grow louder and a held note
  starts on it;
- the music pauses before a punchline (a beat's ``music_pause: true``, and on its own before a
  ``card`` scene and before the cue's last line when it is short) and comes back on a bar line;
- it ends with a cadence (V-I, slowing down, the tonic chord held) instead of the loop bar.

A beat's ``sting:`` under composed music is played by the music's own instruments, in its key
(:func:`sting_score`, :func:`composed_stings`).

:func:`plan_sections` and :func:`fit_music` are pure; :func:`cue_inputs` reads the project's
config and the combined timings, :func:`composed_stings` renders.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from vidgen.composer import (
    DEFAULT_SEED,
    INSTRUMENTS,
    MOODS,
    Piece,
    _pitches,
    _voicing,
    compose_piece,
    fit_range,
    mood_key,
    parse_chord,
    resolve_voices,
)
from vidgen.config import ComposeConfig, MusicCue, SceneMusic
from vidgen.errors import VidgenError
from vidgen.score import Note, Part, Score, Section

if TYPE_CHECKING:
    import numpy as np

    from vidgen.project import Project
    from vidgen.sfx import SfxEvent, SoundLibrary

log = logging.getLogger("vidgen.music")

#: How far (a share) a scene's tempo may move from the mood's to put its change on a bar line.
TEMPO_LIMIT = 0.08
#: The closing cadence: each beat of the last bar (the held tonic) lasts this many times a
#: beat, and the bar before slows down by this much more per beat (a ritardando).
CLOSE_STRETCH = 1.3
RIT_STEP = 0.06
#: Seconds of silence a pause leaves at least before the punchline starts.
PAUSE_LEAD = 0.4
#: The cue's last line pauses the music on its own when it has at most this many words (and its
#: scene has another beat before it); the closing chord then comes when the line ends, if at
#: least BUTTON_MIN seconds of the cue are left.
PAUSE_WORDS = 8
BUTTON_MIN = 0.3
#: A swell: the beats over which the notes before a reveal grow louder, their largest velocity
#: factor, and the held note on the reveal (beats, velocity).
SWELL_BEATS = 2.0
SWELL_GAIN = 1.2
SWELL_NOTE_BEATS = 2.0
SWELL_VELOCITY = 72
#: Seconds of a composed sting's reverb tail that are kept (faded over the last half).
STING_TAIL = 1.5
_MIN_TEMPO, _MAX_TEMPO = 20.0, 300.0
#: The roles that can hold a swell's note, by preference (sustaining instruments first).
_SWELL_ROLES = ("pad", "chords", "melody")


# ----- settings -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """The compose settings of a stretch of a cue (a cue's ``compose:``, changed by a scene's
    ``music:``)."""

    mood: str
    key: str | None = None
    tempo: float | None = None
    instruments: Mapping[str, Any] = field(default_factory=dict)
    seed: int = DEFAULT_SEED

    @property
    def meter(self) -> int:
        """Beats per bar."""
        return MOODS[self.mood].meter

    @property
    def nominal_tempo(self) -> float:
        """The tempo asked for (quarter notes per minute): ``tempo``, else the mood's."""
        return float(self.tempo or MOODS[self.mood].tempo)

    @property
    def bar_seconds(self) -> float:
        """Seconds of a bar at :attr:`nominal_tempo`."""
        return self.meter * 60.0 / self.nominal_tempo


def cue_settings(compose: ComposeConfig) -> Settings:
    """The settings of a cue's ``compose:``."""
    return Settings(compose.mood, compose.key, compose.tempo, compose.instrument_settings(), compose.seed)


def scene_settings(base: Settings, setting: bool | SceneMusic) -> Settings:
    """``base`` changed by a scene's ``music:``: another ``mood`` starts from that mood's defaults
    (the cue's seed kept); ``key``, ``tempo``, ``seed`` replace, ``instruments`` add to the
    cue's (same mood) or replace them (another mood)."""
    if not isinstance(setting, SceneMusic) or not setting.compose_keys:
        return base
    start = base if setting.mood in (None, base.mood) else Settings(str(setting.mood), seed=base.seed)
    instruments = dict(start.instruments) if start is base else {}
    instruments.update(setting.instrument_settings())
    given = {k: getattr(setting, k) for k in ("key", "tempo", "seed") if getattr(setting, k) is not None}
    return replace(start, instruments=instruments, **given)


# ----- sections: bars and tempo from the timings ----------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """Where a stretch of the cue starts on a bar line (seconds from the cue's start): a scene's
    change (its id) and its settings. ``button``: the last stretch, after the cue's last line,
    is the closing chord alone, struck as the line ends and held to the end at any tempo."""

    scene: str
    start: float
    settings: Settings
    button: bool = False


@dataclass(frozen=True)
class FitSection:
    """A stretch of whole bars from one bar line to the next planned one: the scenes it covers
    (the first starts on its first bar line), its start and length in seconds from the cue's
    start, its bars, beats per bar, tempo, the settings' tempo, and ``stretch``: per beat, how
    many beats long it lasts at ``tempo`` (1; more where it slows down)."""

    scenes: tuple[str, ...]
    start: float
    seconds: float
    bars: int
    meter: int
    tempo: float
    nominal: float
    stretch: tuple[float, ...]
    settings: Settings

    @property
    def beats(self) -> int:
        """The section's beats (quarter notes)."""
        return self.bars * self.meter

    @property
    def tempo_change(self) -> float:
        """How far its tempo is from the settings' (a share: 0.05 = 5 % faster)."""
        return self.tempo / self.nominal - 1


def _profile(bars: int, meter: int, closing: bool) -> list[float]:
    """Each beat's stretch at the section's tempo: 1, except, when ``closing``, the last bar (the
    held tonic) and a ritardando in the bar before it."""
    stretch = [1.0] * (bars * meter)
    if closing:
        for k in range(meter):
            stretch[-1 - k] = CLOSE_STRETCH
        if bars >= 2:
            for k in range(meter):
                stretch[(bars - 2) * meter + k] = 1.0 + RIT_STEP * (k + 1)
    return stretch


def _hold(stretch: list[float], extra: float, meter: int, tempo: float) -> list[float]:
    """``stretch`` with ``extra`` beats added over its last bar, more on each later beat (the
    music slows into a held chord); no beat slower than 20 BPM (the rest spills over the
    section's other beats)."""
    out = list(stretch)
    cap = tempo / _MIN_TEMPO
    beats = list(range(len(out) - min(meter, len(out)), len(out)))
    for _ in range(len(out) + 1):
        free = [i for i in beats if out[i] < cap - 1e-9]
        if extra <= 1e-12:
            break
        if not free:
            if len(beats) == len(out):
                break
            beats = list(range(len(out)))
            continue
        weights = {i: k + 1 for k, i in enumerate(beats) if i in free}
        total = sum(weights.values())
        spilled = 0.0
        for i, weight in weights.items():
            add = extra * weight / total
            room = cap - out[i]
            out[i] += min(add, room)
            spilled += max(0.0, add - room)
        extra = spilled
    return out


def _fit(scenes: tuple[str, ...], start: float, seconds: float, settings: Settings, closing: bool, limit: float, button: bool = False) -> FitSection:
    """The bars and tempo that fill ``seconds`` with the tempo nearest the settings' within
    ``limit``; a hold when even the slowest is too fast; one bar at whatever tempo it takes when
    even one bar at the fastest is too long (and always for a ``button``)."""
    nominal, meter = settings.nominal_tempo, settings.meter
    best: tuple[int, float, list[float]] | None = None
    bars = 1
    while not button:
        profile = _profile(bars, meter, closing)
        tempo = 60.0 * sum(profile) / seconds
        if tempo > nominal * (1 + limit) + 1e-9:
            break
        if best is None or abs(tempo / nominal - 1) < abs(best[1] / nominal - 1):
            best = (bars, tempo, profile)
        bars += 1
    if best is None:
        profile = [1.0] * meter if button else _profile(1, meter, closing)
        best = (1, min(_MAX_TEMPO, max(_MIN_TEMPO, 60.0 * sum(profile) / seconds)), profile)
    bars, tempo, profile = best
    if not button and tempo < nominal * (1 - limit) - 1e-9:
        tempo = nominal * (1 - limit)
        profile = _hold(profile, seconds * tempo / 60.0 - sum(profile), meter, tempo)
    return FitSection(scenes, start, seconds, bars, meter, tempo, nominal, tuple(profile), settings)


def plan_sections(slots: Sequence[Slot], seconds: float, limit: float = TEMPO_LIMIT) -> tuple[FitSection, ...]:
    """The sections of a cue ``seconds`` long whose stretches start at ``slots`` (the first at 0,
    in order): one per slot, a slot too short for one bar at the fastest tempo joined with the
    next (the last, or the one before a ``button``, with the one before); the last section closes
    (cadence; a ``button``, only the last slot, is that closing bar alone). Pure."""
    if not slots or seconds <= 0 or abs(slots[0].start) > 1e-9 or any(s.button for s in slots[:-1]):
        raise VidgenError("music: a fitted piece needs a first stretch at 0 s, a length above 0 s and a button only last")
    ends = [s.start for s in slots[1:]] + [seconds]
    button = slots[-1].button

    def too_short(group: list[int]) -> bool:
        head = slots[group[0]].settings
        closes = group[-1] == len(slots) - 1 and not button
        bar = head.meter * (CLOSE_STRETCH if closes else 1.0) * 60.0 / (head.nominal_tempo * (1 + limit))
        return ends[group[-1]] - slots[group[0]].start < bar

    groups: list[list[int]] = []
    i = 0
    stop = len(slots) - 1 if button else len(slots)
    while i < stop:
        group = [i]
        while too_short(group) and group[-1] + 1 < stop:
            group.append(group[-1] + 1)
        if too_short(group) and groups:
            groups[-1] += group
        else:
            groups.append(group)
        i = group[-1] + 1
    if button:
        groups.append([len(slots) - 1])
    out = []
    for k, group in enumerate(groups):
        head = slots[group[0]]
        length = ends[group[-1]] - head.start
        last = k == len(groups) - 1
        out.append(_fit(tuple(slots[j].scene for j in group), head.start, length, head.settings, last, limit, button and last))
    return tuple(out)


@dataclass(frozen=True)
class TempoMap:
    """Beats ↔ seconds of a fitted piece: ``changes`` as ``(beat, tempo)`` from beat 0."""

    changes: tuple[tuple[float, float], ...]

    @classmethod
    def of(cls, sections: Sequence[FitSection]) -> TempoMap:
        """The tempo of every beat of ``sections`` (their tempo over each beat's stretch)."""
        changes: list[tuple[float, float]] = []
        beat = 0.0
        for section in sections:
            for k, stretch in enumerate(section.stretch):
                tempo = section.tempo / stretch
                if not changes or abs(changes[-1][1] - tempo) > 1e-9:
                    changes.append((beat + k, tempo))
            beat += section.beats
        return cls(tuple(changes))

    def seconds_at(self, beat: float) -> float:
        """The time of ``beat``."""
        seconds = 0.0
        for k, (start, tempo) in enumerate(self.changes):
            stop = self.changes[k + 1][0] if k + 1 < len(self.changes) else math.inf
            if beat <= start:
                break
            seconds += (min(beat, stop) - start) * 60.0 / tempo
        return seconds

    def beat_at(self, seconds: float) -> float:
        """The beat at ``seconds`` (the inverse of :meth:`seconds_at`)."""
        at = 0.0
        for k, (start, tempo) in enumerate(self.changes):
            stop = self.changes[k + 1][0] if k + 1 < len(self.changes) else math.inf
            span = (stop - start) * 60.0 / tempo
            if seconds <= at + span:
                return start + (seconds - at) * tempo / 60.0
            at += span
        return self.changes[-1][0]


# ----- the fitted piece -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Pause:
    """A punchline beat the music pauses before: its start and end, seconds from the cue's start."""

    start: float
    end: float


@dataclass(frozen=True)
class FittedMusic:
    """A piece fitted to a cue: its score, sections, tempo map, swells (beats) and pauses (beats
    from, to)."""

    score: Score
    sections: tuple[FitSection, ...]
    tempo_map: TempoMap
    swells: tuple[float, ...]
    pauses: tuple[tuple[float, float], ...]

    @property
    def closing_seconds(self) -> float:
        """When the closing chord (the last bar) starts, seconds from the cue's start."""
        return self.tempo_map.seconds_at(self.score.length_beats - self.sections[-1].meter)

    def summary(self, offset: float) -> dict[str, Any]:
        """``{sections: [{scenes, start, bars, tempo, mood}], swells, pauses, closing}`` in video
        seconds (``offset``: the cue's start)."""
        def at(beat: float) -> float:
            return round(offset + self.tempo_map.seconds_at(beat), 3)

        return {
            "sections": [
                {"scenes": list(s.scenes), "start": round(offset + s.start, 3), "bars": s.bars, "tempo": round(s.tempo, 2), "mood": s.settings.mood}
                for s in self.sections
            ],
            "swells": [at(b) for b in self.swells],
            "pauses": [[at(a), at(b)] for a, b in self.pauses],
            "closing": round(offset + self.closing_seconds, 3),
        }


def _blocks(sections: Sequence[FitSection]) -> list[list[FitSection]]:
    """Runs of consecutive sections with the same settings (each is composed as one piece)."""
    blocks: list[list[FitSection]] = []
    for section in sections:
        if blocks and blocks[-1][-1].settings == section.settings:
            blocks[-1].append(section)
        else:
            blocks.append([section])
    return blocks


def _bar_lines(sections: Sequence[FitSection]) -> list[float]:
    lines, beat = [], 0.0
    for section in sections:
        lines += [beat + k * section.meter for k in range(section.bars)]
        beat += section.beats
    return lines + [beat]


def _pause_windows(pauses: Sequence[Pause], tempo_map: TempoMap, bar_lines: Sequence[float], closing: float) -> list[tuple[float, float]]:
    """Each pause as beats: from the last beat at least :data:`PAUSE_LEAD` before the punchline
    to the first bar line after it ends (the closing chord at the latest)."""
    windows = []
    for pause in pauses:
        first = float(math.floor(tempo_map.beat_at(max(0.0, pause.start - PAUSE_LEAD)) + 1e-6))
        end = tempo_map.beat_at(pause.end)
        back = min(next((b for b in bar_lines if b >= end - 1e-6), closing), closing)
        if back > first:
            windows.append((first, back))
    return windows


def _swell_beats(reveals: Sequence[float], tempo_map: TempoMap, closing: float, pauses: Sequence[tuple[float, float]]) -> list[float]:
    """The beats nearest the reveals, not on the first beat, the closing bar or in (or a beat
    before) a pause, at least :data:`SWELL_BEATS` apart."""
    out: list[float] = []
    for seconds in sorted(reveals):
        beat = float(round(tempo_map.beat_at(seconds)))
        if beat < 1 or beat >= closing or any(a - 1 <= beat < b for a, b in pauses):
            continue
        if out and beat - out[-1] < SWELL_BEATS:
            continue
        out.append(beat)
    return out


def _swelled(notes: Sequence[Note], swells: Sequence[float]) -> list[Note]:
    """``notes`` louder towards each swell: from 1 to :data:`SWELL_GAIN` over the
    :data:`SWELL_BEATS` before it, :data:`SWELL_GAIN` for the beat on it."""
    out = []
    for note in notes:
        gain = 1.0
        for beat in swells:
            if beat - SWELL_BEATS <= note.start < beat:
                gain = max(gain, 1 + (SWELL_GAIN - 1) * (note.start - beat + SWELL_BEATS) / SWELL_BEATS)
            elif beat <= note.start < beat + 1:
                gain = max(gain, SWELL_GAIN)
        out.append(note if gain == 1.0 else replace(note, velocity=min(127, round(note.velocity * gain))))
    return out


def _swell_note(piece: Piece, part: Part, role: str, beat: float, length: float) -> Note | None:
    """The held note a swell adds on ``beat`` (of ``piece``) to ``part`` (its ``role``): a tone of
    the chord sounding there near the top of the treble staff, in the instrument's range, not one
    the part strikes on that beat already."""
    voice = next(v for v in piece.voices if v.role == role)
    chord = piece.chord_at(beat)
    struck = {n.pitch for n in part.notes if abs(n.start - beat) < 1e-9}
    pitches = [p for p in _pitches(chord.pitch_classes, max(voice.instrument.low, 60), min(voice.instrument.high, 84)) if p not in struck]
    if not pitches:
        return None
    return Note(beat, length, min(pitches, key=lambda p: (abs(p - 74), p)), SWELL_VELOCITY)


def _cut(notes: Sequence[Note], windows: Sequence[tuple[float, float]]) -> list[Note]:
    """``notes`` silent in ``windows``: a note starting in one is dropped, a note sounding into
    one ends where it starts."""
    out = []
    for note in notes:
        kept: Note | None = note
        for a, b in windows:
            if kept is None:
                break
            if a <= kept.start < b:
                kept = None
            elif kept.start < a < kept.end:
                kept = replace(kept, length=a - kept.start)
        if kept is not None:
            out.append(kept)
    return out


def fit_music(sections: Sequence[FitSection], reveals: Sequence[float] = (), pauses: Sequence[Pause] = ()) -> FittedMusic:
    """The piece of ``sections`` (:func:`plan_sections`): each run of sections with the same
    settings composed as one piece (:func:`~vidgen.composer.compose_piece`, ending ``open``, the
    last ``cadence``), with swells at ``reveals`` and silences for ``pauses`` (seconds from the
    cue's start), timed by section tempo changes. Pure and seeded."""
    tempo_map = TempoMap.of(sections)
    lines = _bar_lines(sections)
    total = lines[-1]
    closing = total - sections[-1].meter
    windows = _pause_windows(pauses, tempo_map, lines, closing)
    swells = _swell_beats(reveals, tempo_map, closing, windows)
    blocks = _blocks(sections)
    parts: dict[tuple[Any, ...], tuple[str, list[Note]]] = {}
    first_piece: Piece | None = None
    offset = 0.0
    for k, block in enumerate(blocks):
        settings = block[0].settings
        bars = sum(s.bars for s in block)
        piece = compose_piece(
            settings.mood, settings.key, settings.tempo, dict(settings.instruments), settings.seed, bars, "cadence" if k == len(blocks) - 1 else "open"
        )
        first_piece = first_piece or piece
        span = bars * settings.meter
        local = [b - offset for b in swells if offset <= b < offset + span]
        holder = next((role for role in _SWELL_ROLES if any(v.role == role for v in piece.voices)), None)
        for part, voice in zip(piece.score.parts, piece.voices):
            notes = _swelled(part.notes, local)
            if voice.role == holder:
                notes += [n for n in (_swell_note(piece, part, voice.role, b, min(SWELL_NOTE_BEATS, span - b)) for b in local) if n is not None]
            key = (voice.role, part.program, part.drums, part.volume, part.pan, part.reverb)
            if key not in parts:
                taken = sum(1 for name, _ in parts.values() if name.split()[0] == voice.role)
                parts[key] = (voice.role if not taken else f"{voice.role} {taken + 1}", [])
            parts[key][1].extend(replace(n, start=n.start + offset) for n in notes)
        offset += span
    assert first_piece is not None
    score_parts = tuple(
        Part(name, tuple(sorted(_cut(notes, windows), key=lambda n: (n.start, n.pitch))), program=key[1], drums=key[2], volume=key[3], pan=key[4], reverb=key[5])
        for key, (name, notes) in parts.items()
    )
    score = Score(
        tempo=tempo_map.changes[0][1], parts=score_parts, time_signature=(sections[0].meter, 4), key=first_piece.key.name,
        sections=_score_sections(sections), length=float(total), balance=True,
    )
    return FittedMusic(score, tuple(sections), tempo_map, tuple(swells), tuple(windows))


def _score_sections(sections: Sequence[FitSection]) -> tuple[Section, ...]:
    """A marker with the tempo at each section's start (its scene ids) and at each tempo change
    inside (``hold`` where it slows, ``a tempo`` where it comes back)."""
    out: list[Section] = []
    beat = 0.0
    for section in sections:
        previous = None
        for k, stretch in enumerate(section.stretch):
            tempo = section.tempo / stretch
            if k == 0:
                out.append(Section(" ".join(section.scenes), beat, tempo))
            elif previous is not None and abs(tempo - previous) > 1e-9:
                out.append(Section("hold" if stretch > 1 else "a tempo", beat + k, tempo))
            previous = tempo
        beat += section.beats
    return tuple(out)


# ----- from the project's config and timings --------------------------------------------------------


def is_fitted(cue: MusicCue) -> bool:
    """Whether ``cue`` is composed for the video (``compose:`` without ``bars``)."""
    return cue.compose is not None and cue.compose.bars is None


def _type_reveal_beats(spec: Any) -> set[int]:
    """The beats (indices) in which the scene type's own reveal shows a step (as host directing
    maps them, :func:`~vidgen.layout.distribute`); none when the type is not registered (the
    built-ins are loaded; a project's types only in its session) or its params do not validate."""
    from vidgen import registry
    from vidgen.extensions import load_builtins
    from vidgen.layout import distribute

    load_builtins()
    entry = registry.find(spec.type)
    if entry is None or not spec.beats:
        return set()
    try:
        steps = entry.cls.reveal_steps(entry.cls.parse_params(spec.params, scene_id=spec.id))
    except (VidgenError, ValueError, TypeError):
        return set()
    plan = distribute(len(steps), len(spec.beats)) if steps else []
    return {j for j, step in enumerate(plan) if step}


def cue_inputs(
    project: Project, timings: Mapping[str, Any], cue: MusicCue, first: int, last: int, start: float, end: float
) -> tuple[list[Slot], list[float], list[Pause]]:
    """The slots, reveal times and pauses (seconds from the cue's ``start``; it ends at ``end``)
    of ``cue`` over scenes ``first`` to ``last`` (combined ``timings``): a scene changes at its
    start, or in the middle of the transition into it; a pause before the cue's last line ends
    with a ``button`` slot where the line ends."""
    assert cue.compose is not None
    base = cue_settings(cue.compose)
    specs, scenes = project.config.scenes, timings["scenes"]
    slots: list[Slot] = []
    reveals: list[float] = []
    pauses: list[Pause] = []
    lines: list[tuple[int, Any, dict[str, Any]]] = []
    for i in range(first, last + 1):
        spec, scene = specs[i], scenes[i]
        overlap = float((scene.get("transition") or {}).get("overlap", 0.0))
        change = 0.0 if i == first else scene["start"] + overlap / 2 - start
        slots.append(Slot(spec.id, change, scene_settings(base, spec.music)))
        timed = {b["id"]: b for b in scene["beats"]}
        revealing = _type_reveal_beats(spec)
        for j, beat in enumerate(spec.beats):
            window = timed.get(beat.id)
            if window is None:
                continue
            a, b = window["start"] - start, window["end"] - start
            if j in revealing:
                reveals.append(a)
            reveals += [a + act.at * (b - a) for act in beat.actions if act.action == "reveal"]
            if beat.music_pause:
                pauses.append(Pause(a, b))
            lines.append((i, beat, window))
        reveals += [e["time"] - start for e in scene.get("sfx", []) if e.get("sound") == "sting_reveal"]
        if spec.type == "card" and i > first and (not spec.beats or spec.beats[0].music_pause is None):
            opening = timed.get(spec.beats[0].id) if spec.beats else None
            pauses.append(Pause(change, (opening["end"] if opening else scene["start"] + scene["duration"]) - start))
    if lines:
        i, beat, window = lines[-1]
        a, b = window["start"] - start, window["end"] - start
        short = len(beat.text.split()) <= PAUSE_WORDS and len(specs[i].beats) >= 2 and beat.music_pause is None
        if i == last and (short or beat.music_pause) and end - start - b >= BUTTON_MIN and b - slots[-1].start > 0:
            # the music stops before the last line and its closing chord comes when the line ends
            pauses = [p for p in pauses if p.start != a] + [Pause(a, b)]
            slots.append(Slot(specs[i].id + " (end)", b, slots[-1].settings, button=True))
    return slots, reveals, pauses


def fitted_music(project: Project, timings: Mapping[str, Any], cue: MusicCue, first: int, last: int, start: float, end: float) -> FittedMusic:
    """The music of a fitted ``cue`` from ``start`` to ``end`` (video seconds) over scenes
    ``first`` to ``last`` (:func:`cue_inputs`, :func:`plan_sections`, :func:`fit_music`)."""
    slots, reveals, pauses = cue_inputs(project, timings, cue, first, last, start, end)
    return fit_music(plan_sections(slots, end - start), reveals, pauses)


# ----- stings with the music's instruments ----------------------------------------------------------

#: The built-in sting sounds (:data:`vidgen.sfx.STING_SOUNDS`) by kind.
_STING_KINDS = {"sting_reveal": "reveal", "sting_comic": "comic", "sting_sad": "sad"}


def sting_score(kind: str, settings: Settings) -> Score:
    """A one- or two-bar sting in the music's key, instruments and tempo: ``reveal`` (a pickup
    on the dominant, then the tonic chord held with a cymbal), ``comic`` (two tom hits and a
    cymbal, the bass and a short tonic chord on the last) or ``sad`` (the melody falling three
    semitones onto the tonic, the last note long). Pure."""
    mood = MOODS[settings.mood]
    key = mood_key(mood, settings.key)
    voices = {v.role: v for v in resolve_voices(mood, settings.instruments)}
    tonic_chord = parse_chord("i" if key.minor else "I", key)
    parts: list[Part] = []

    def add(role: str, notes: list[Note]) -> None:
        if role in voices and notes:
            v = voices[role]
            parts.append(Part(role, tuple(notes), program=v.instrument.program, drums=v.instrument.drums, volume=v.volume, pan=v.pan, reverb=v.reverb))

    def tonic_near(low: int, high: int, aim: float) -> int:
        """The tonic in ``low``-``high`` nearest ``aim`` (``low`` without one)."""
        return min(_pitches((key.tonic,), low, high) or [low], key=lambda p: abs(p - aim))

    melody = voices.get("melody")
    m_low, m_high = fit_range(*mood.melody_range, melody.instrument) if melody else (60, 84)
    middle = (m_low + m_high) / 2
    bass_root = tonic_near(*fit_range(mood.bass_low, mood.bass_low + 11, voices["bass"].instrument), mood.bass_low) if "bass" in voices else 36
    chord_low = fit_range(mood.chords_low, mood.chords_low + 24, voices["chords"].instrument)[0] if "chords" in voices else mood.chords_low
    chord = _voicing(tonic_chord, chord_low + 5, None)
    if kind == "reveal":
        tonic = tonic_near(m_low + 5, m_high, middle)  # room for the pickup a fourth below
        add("melody", [Note(0.0, 0.45, tonic - 5, 96), Note(0.5, 2.5, tonic, 104)])
        add("chords", [Note(0.5, 2.5, p, 96) for p in chord])
        add("pad", [Note(0.5, 2.5, p, 80) for p in _voicing(tonic_chord, 55, None)])
        add("bass", [Note(0.5, 2.5, bass_root, 100)])
        kit = voices.get("drums")
        if kit is not None:
            add("drums", [Note(0.5, 0.25, 36, 96), Note(0.5, 0.25, 49, 92)])
    elif kind == "comic":
        drums = voices.get("drums")
        kit = drums.instrument if drums is not None else INSTRUMENTS["drums"]
        hits = (Note(0.0, 0.25, 48, 100), Note(0.5, 0.25, 45, 108), Note(1.0, 0.25, 36, 100), Note(1.0, 0.25, 49, 104))
        parts.append(Part("drums", hits, program=kit.program, drums=True, volume=drums.volume if drums else 0.0, reverb=0.15))
        add("bass", [Note(1.0, 0.45, bass_root, 100)])
        add("chords", [Note(1.0, 0.35, p, 92) for p in chord])
    elif kind == "sad":
        tonic = tonic_near(m_low, m_high - 3, m_low + 3)  # low in the range, room for the minor third above
        add("melody", [Note(float(k), 0.8, tonic + 3 - k, 96 - 4 * k) for k in range(3)] + [Note(3.0, 2.5, tonic, 84)])
        add("bass", [Note(3.0, 2.5, bass_root, 90)])
    else:
        raise VidgenError(f"sting: unknown kind {kind!r} (reveal, comic, sad)")
    if not parts:
        raise VidgenError(f"sting: mood '{settings.mood}' with these instruments has no part to play a {kind} sting")
    return Score(tempo=settings.nominal_tempo, parts=tuple(parts), time_signature=(mood.meter, 4), key=key.name, balance=True)


def _cue_of_scene(project: Project, index: int) -> MusicCue | None:
    from vidgen.music import cue_scene_range

    ids = [s.id for s in project.config.scenes]
    for cue in project.config.music_cues:
        first, last = cue_scene_range(cue, ids)
        if first <= index <= last:
            return cue
    return None


def composed_stings(project: Project, timings: Mapping[str, Any], events: Sequence[SfxEvent], library: SoundLibrary) -> dict[int, np.ndarray]:
    """The audio of each built-in music sting among ``events`` (video times; combined
    ``timings``) that plays under composed music, by its index: :func:`sting_score` in the
    settings of its scene, rendered with the project's SoundFont (cached in ``build/music``),
    its reverb tail cut to :data:`STING_TAIL`, at the loudness of the built-in sting it
    replaces. Empty without composed music or the ``music`` extra; a project's own sting file is
    kept."""
    import numpy as np

    from vidgen import loudness, soundfont, synth
    from vidgen.music import fallback_bed
    from vidgen.sfx import RATE, stereo, synthesize

    scenes = timings["scenes"]
    if not any(c.compose is not None for c in project.config.music_cues) or not scenes:
        return {}
    out: dict[int, np.ndarray] = {}
    made: dict[tuple[str, str], np.ndarray] = {}
    for n, event in enumerate(events):
        kind = _STING_KINDS.get(event.sound)
        if kind is None or library.file(event.sound) is not None:
            continue
        index = max((i for i, s in enumerate(scenes) if s["start"] <= event.time + 1e-9), default=0)
        cue = _cue_of_scene(project, index)
        if cue is None or cue.compose is None or fallback_bed(cue) is not None:
            continue
        settings = cue_settings(cue.compose)
        if is_fitted(cue):
            settings = scene_settings(settings, project.config.scenes[index].music)
        tag = (kind, repr(settings))
        if tag not in made:
            score = sting_score(kind, settings)
            audio = synth.render_score(score, soundfont.resolve(project.config.soundfont, project.root), project.build_dir / "music")
            keep = min(len(audio), round((score.length_seconds + STING_TAIL) * RATE))
            audio = np.array(audio[:keep], dtype=np.float32)
            fade = round(STING_TAIL / 2 * RATE)
            audio[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
            target = loudness.integrated_loudness(stereo(synthesize(event.sound)))
            level = loudness.integrated_loudness(audio)
            made[tag] = (audio * np.float32(10 ** ((target - level) / 20))).astype(np.float32) if math.isfinite(level) else audio
        out[n] = made[tag]
    if out:
        log.info("music: %d sting(s) played with the composed music's instruments", len(out))
    return out
