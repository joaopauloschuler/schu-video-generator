"""Overlapping speech and interruptions (DESIGN.md §69.34): the timeline maths and the mix plan
of beats that start before the beat before them ends. No manim.

A beat's ``overlap: S`` starts it ``S`` seconds before the speech of the beat before it ends
(its MP3's trailing silence cut off, :func:`~vidgen.speech.speech_bounds`); both voices are
heard, the earlier one :data:`OVERLAP_DIP_DB` lower from where the later one starts.
``interrupt: true`` cuts the earlier line where the beat starts (a :data:`INTERRUPT_FADE` fade).
Without ``overlap`` it starts inside that line's last word, :data:`INTERRUPT_WORD_SHARE` of the
way through it (the word timings stored with its MP3), so at most the word's final part is cut;
without stored timings :data:`INTERRUPT_LEAD` before that line's speech ends. Only beats after
the first of a scene may have them, so scenes still start and end as planned.

Each beat gets a :class:`BeatWindow` (:func:`beat_windows`): a beat whose next beat neither
overlaps nor interrupts it keeps ``d`` for its own animations and ``d + narration.pad`` until
the next beat, as before; one the next beat joins gets the time until the next beat starts and
no pad.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from vidgen.config import BeatConfig, VideoConfig
    from vidgen.project import Project
    from vidgen.speech import WordTime

#: How far into the earlier line's last word (a share of its length) an ``interrupt`` without
#: ``overlap`` starts, when the word's times are stored with its MP3.
INTERRUPT_WORD_SHARE = 0.7
#: Seconds an ``interrupt`` without ``overlap`` starts before the earlier line's speech ends when
#: its word times are only estimated (short, so no whole word is cut).
INTERRUPT_LEAD = 0.2
#: Seconds over which an interrupted line fades out from the cut.
INTERRUPT_FADE = 0.05
#: How much (dB) the earlier line is lowered while a later one overlaps it, so the new line
#: leads and both stay audible.
OVERLAP_DIP_DB = 3.0
#: Seconds over which that dip comes in (raised cosine), from where the later line starts.
DIP_RAMP = 0.1
#: Seconds a beat keeps at least before the next one starts, however large the overlap.
MIN_WINDOW = 0.2


@dataclass(frozen=True)
class SpokenLine:
    """A beat as the timeline sees it: its narration's length ``seconds`` (``d``), where its
    speech ends (``speech_end``, seconds from its start, at most ``d``), its own ``overlap``
    and ``interrupt`` keys (how it joins the beat before it) and its ``last_word`` (start, end;
    seconds from its start) when stored word times give it."""

    seconds: float
    speech_end: float
    overlap: float | None = None
    interrupt: bool = False
    last_word: tuple[float, float] | None = None

    @property
    def joins(self) -> bool:
        """Whether it starts before the beat before it has ended (``overlap`` or ``interrupt``)."""
        return self.overlap is not None or self.interrupt

    def lead_after(self, earlier: SpokenLine) -> float:
        """Seconds it starts before the ``earlier`` line's speech ends: its ``overlap``; for an
        interrupt without one, inside that line's last word (:data:`INTERRUPT_WORD_SHARE`), or
        :data:`INTERRUPT_LEAD` when the word's times are not stored; 0 when it does not join."""
        if self.overlap is not None:
            return self.overlap
        if not self.interrupt:
            return 0.0
        if earlier.last_word is None:
            return INTERRUPT_LEAD
        start, end = earlier.last_word
        return max(earlier.speech_end - (start + INTERRUPT_WORD_SHARE * (end - start)), 0.0)


def _rise(u: np.ndarray) -> np.ndarray:
    """Raised cosine: 0 at ``u <= 0`` rising to 1 at ``u >= 1``."""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(u, 0.0, 1.0))


@dataclass(frozen=True)
class VoiceShape:
    """The mix plan of one beat's voice, in seconds from its start: cut at ``cut`` (fading out
    over :data:`INTERRUPT_FADE`), or lowered by :data:`OVERLAP_DIP_DB` from ``dip_from`` on;
    neither: played as it is."""

    cut: float | None = None
    dip_from: float | None = None

    @property
    def plain(self) -> bool:
        """Whether the voice plays unchanged."""
        return self.cut is None and self.dip_from is None

    @property
    def length(self) -> float:
        """Seconds of the voice that are heard at all (``inf``: all of it)."""
        return math.inf if self.cut is None else self.cut + INTERRUPT_FADE

    def gain(self, seconds: np.ndarray) -> np.ndarray:
        """The linear gain at ``seconds`` from the beat's start."""
        out = np.ones(len(seconds))
        if self.dip_from is not None:
            out *= 10 ** (-OVERLAP_DIP_DB * _rise((seconds - self.dip_from) / DIP_RAMP) / 20)
        if self.cut is not None:
            out *= 1.0 - _rise((seconds - self.cut) / INTERRUPT_FADE)
        return out


def shape_voice(samples: np.ndarray, rate: int, shape: VoiceShape) -> np.ndarray:
    """``samples`` (``(n, channels)`` at ``rate``) as ``shape`` plays them: dipped, or cut with
    its fade (and the rest dropped). A plain shape returns them unchanged."""
    if shape.plain:
        return samples
    keep = len(samples) if shape.length == math.inf else min(len(samples), math.ceil(shape.length * rate))
    kept = samples[:keep]
    gain = shape.gain(np.arange(keep) / rate)
    return (kept * gain.reshape(-1, *([1] * (kept.ndim - 1)))).astype(samples.dtype)


@dataclass(frozen=True)
class BeatWindow:
    """How long a beat lasts on the scene's clock: ``body`` seconds for its own animations and
    actions (what ``narrate`` yields), ``window`` from its start to the next beat's start
    (``body`` + the pad, or ``body`` when the next beat joins it), ``heard`` seconds of its voice
    (``d``, or up to the cut of an interruption; the end in the timings), its voice's
    :class:`VoiceShape` and ``next_lead``, the seconds the next beat starts before its speech
    ends (0 when the next beat does not join it)."""

    body: float
    rest: float
    heard: float
    shape: VoiceShape = VoiceShape()
    next_lead: float = 0.0

    @property
    def window(self) -> float:
        """Seconds from the beat's start to the next beat's start."""
        return self.body + self.rest

    @property
    def joined(self) -> bool:
        """Whether the next beat starts before this one has ended (overlap or interrupt)."""
        return not self.shape.plain


def beat_windows(lines: Sequence[SpokenLine], pad: float, fps: float | None = None) -> list[BeatWindow]:
    """Each beat's :class:`BeatWindow` from the scene's ``lines`` in order and
    ``narration.pad``. A beat the next one does not join: ``body = d``, ``rest = pad``, heard
    whole. One it joins: the window ends :meth:`SpokenLine.lead_after` before its speech ends
    (at least :data:`MIN_WINDOW`; with ``fps``, in whole frames, where the next beat really
    starts), no pad; an interrupt cuts its voice there, an overlap dips it."""
    out = []
    for k, line in enumerate(lines):
        follower = lines[k + 1] if k + 1 < len(lines) else None
        if follower is None or not follower.joins:
            out.append(BeatWindow(line.seconds, pad, line.seconds))
            continue
        window = max(line.speech_end - follower.lead_after(line), MIN_WINDOW)
        if fps:
            window = max(round(window * fps), 1) / fps
        lead = line.speech_end - window
        if follower.interrupt:
            heard = min(window, line.seconds)
            out.append(BeatWindow(window, 0.0, heard, VoiceShape(cut=heard), lead))
        else:
            out.append(BeatWindow(window, 0.0, line.seconds, VoiceShape(dip_from=window), lead))
    return out


def beat_speech_end(project: Project, beat_id: str, seconds: float) -> float:
    """Where a beat's speech ends (seconds from its start): its MP3's speech without the
    trailing silence, else (no MP3, or one that cannot be read) ``seconds``."""
    from vidgen.errors import VidgenError
    from vidgen.speech import speech_bounds

    mp3 = project.audio_dir / f"{beat_id}.mp3"
    if not mp3.is_file():
        return seconds
    try:
        return min(speech_bounds(mp3)[1], seconds)
    except VidgenError:
        return seconds


def has_joins(beats: Sequence[BeatConfig]) -> bool:
    """Whether a beat of ``beats`` overlaps or interrupts the one before it."""
    return any(b.overlap is not None or b.interrupt for b in beats)


def beat_lines(project: Project, beats: Sequence[BeatConfig], seconds: Callable[[BeatConfig], float]) -> list[SpokenLine]:
    """The :class:`SpokenLine` of each of a scene's ``beats``, ``seconds(beat)`` being its ``d``;
    the speech end is read from the MP3 only for a beat the next one joins, its last word only
    for one the next beat interrupts without an ``overlap``."""
    lines = []
    for k, beat in enumerate(beats):
        d = seconds(beat)
        follower = beats[k + 1] if k + 1 < len(beats) else None
        joined = follower is not None and (follower.overlap is not None or follower.interrupt)
        end = beat_speech_end(project, beat.id, d) if joined else d
        cut_inside = follower is not None and follower.interrupt and follower.overlap is None
        lines.append(SpokenLine(d, end, beat.overlap, beat.interrupt, beat_last_word(project, beat) if cut_inside else None))
    return lines


def beat_last_word(project: Project, beat: BeatConfig) -> tuple[float, float] | None:
    """``(start, end)`` of the last word the TTS said for ``beat`` (seconds from its start), from
    the word timings stored with its MP3; ``None`` without them."""
    from vidgen.speech import stored_word_times

    words = stored_word_times(project.audio_dir, beat.id, project.spoken(beat).spoken)
    return (words[-1].start, words[-1].end) if words else None


def talked_over(words: Sequence[WordTime], start: float, end: float) -> list[WordTime]:
    """The ``words`` (times on any clock) spoken entirely between ``start`` (where another voice
    starts speaking over them) and ``end`` (where their own line stops): hidden by an overlap."""
    return [w for w in words if w.start >= start - 1e-6 and w.end <= end + 1e-6]


def overlap_warnings(config: VideoConfig) -> list[str]:
    """``vidgen validate`` warnings: a beat that overlaps or interrupts a line of its own voice
    (one voice cannot speak two lines at once)."""
    from vidgen.voices import beat_voice_names

    voices = beat_voice_names(config)
    out = []
    for scene in config.scenes:
        for k in range(1, len(scene.beats)):
            beat, before = scene.beats[k], scene.beats[k - 1]
            if (beat.overlap is not None or beat.interrupt) and voices.get(beat.id) == voices.get(before.id):
                key = "interrupt" if beat.interrupt else "overlap"
                voice = voices.get(beat.id) or "default"
                out.append(
                    f"scene '{scene.id}' beat '{beat.id}': {key} on a line of the same voice '{voice}' as the beat before "
                    "(both lines would sound at once in one voice); give one of them another voice"
                )
    return out
