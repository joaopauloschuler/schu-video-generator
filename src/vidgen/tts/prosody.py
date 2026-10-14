"""Applying an emotion's prosody to synthesised speech (DESIGN.md §72): pauses at punctuation
lengthened or shortened by the word timings, a soft-limited gain (numpy) and a pitch shift that
keeps the length (an ffmpeg filter). No PyTorch.

The pauses are edited where the speech is quiet: in the middle of each punctuation token's time
(Kokoro gives ``,`` and ``.`` their own timed token, the pause it speaks there). Every time after
an edit moves with it (:func:`shift_time`), so the word timings and the viseme track stay on the
edited audio.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

#: Tokens whose time is a pause: punctuation inside a line.
PAUSE_MARKS = frozenset(",;:.!?…—–")
#: Marks that end a sentence (the others end a clause).
SENTENCE_MARKS = frozenset(".!?…")
#: A narrator's usual pause (seconds) after a sentence and at a comma: what ``pauses`` scales
#: when Kokoro's own pause is shorter.
SENTENCE_PAUSE = 0.4
CLAUSE_PAUSE = 0.2
#: Shortest pause edited (seconds): shorter punctuation tokens are left alone.
MIN_PAUSE_SECONDS = 0.02
#: Where the soft limiter starts bending (and the level it approaches): fractions of full scale.
LIMIT_KNEE = 0.7
LIMIT_CEILING = 0.98

#: An edit of the audio: at ``at`` seconds (of the unedited audio) ``delta`` seconds are inserted
#: (silence, > 0) or cut (< 0, centred on ``at``).
Edit = tuple[float, float]


def inner_pauses(timed: Sequence[tuple[str, float, float]]) -> list[tuple[float, float, str]]:
    """``(start, end, mark)`` of each punctuation token followed by a word, from timed tokens
    ``(text, start, end)`` in order (the pause after the last word is the beat's padding, not
    edited)."""
    spans: list[tuple[float, float, str]] = []
    for k, (text, start, end) in enumerate(timed):
        mark = text.strip()
        if not mark or not set(mark) <= PAUSE_MARKS or end - start < MIN_PAUSE_SECONDS:
            continue
        if any(any(c.isalnum() for c in later) for later, _, _ in timed[k + 1:]):
            spans.append((start, end, mark))
    return spans


def natural_pause(mark: str) -> float:
    """Seconds a narrator pauses at ``mark``: :data:`SENTENCE_PAUSE` after a sentence,
    :data:`CLAUSE_PAUSE` at a comma (Kokoro's own pauses are often shorter)."""
    return SENTENCE_PAUSE if set(mark) & SENTENCE_MARKS else CLAUSE_PAUSE


def scale_pauses(samples: np.ndarray, pauses: Sequence[tuple[float, float, str]], factor: float, rate: int) -> tuple[np.ndarray, list[Edit]]:
    """``samples`` with each pause ``(start, end, mark)`` (seconds) changed by ``factor`` and the
    edits made: above 1 silence is inserted at its middle, ``factor - 1`` times the longer of the
    pause and :func:`natural_pause` (so Kokoro's short pauses lengthen audibly); below 1 the middle
    of the pause is cut, keeping ``factor`` of it."""
    if factor == 1.0 or not pauses:
        return samples, []
    pieces: list[np.ndarray] = []
    edits: list[Edit] = []
    cursor = 0
    for start, end, mark in sorted(pauses):
        middle = (start + end) / 2
        delta = (factor - 1.0) * (max(end - start, natural_pause(mark)) if factor > 1 else end - start)
        at = int(round(middle * rate))
        if at < cursor or at > len(samples):
            continue
        if delta > 0:
            pieces += [samples[cursor:at], np.zeros(int(round(delta * rate)), dtype=samples.dtype)]
            cursor = at
        else:
            half = int(round(-delta * rate / 2))
            pieces.append(samples[cursor:max(at - half, cursor)])
            cursor = min(at + half, len(samples))
        edits.append((middle, delta))
    pieces.append(samples[cursor:])
    return np.concatenate(pieces), edits


def shift_time(seconds: float, edits: Sequence[Edit]) -> float:
    """Where ``seconds`` of the unedited audio is after ``edits`` (a time inside a cut goes to
    where the cut starts)."""
    moved = seconds
    for at, delta in edits:
        if delta >= 0:
            if seconds > at:
                moved += delta
        else:
            start, end = at + delta / 2, at - delta / 2
            if seconds >= end:
                moved += delta
            elif seconds > start:
                moved -= seconds - start
    return moved


def apply_gain(samples: np.ndarray, gain_db: float) -> np.ndarray:
    """``samples`` (floats, -1..1) ``gain_db`` louder; above :data:`LIMIT_KNEE` of full scale a
    soft limiter bends the peaks towards :data:`LIMIT_CEILING` (a boost never clips)."""
    if gain_db == 0.0:
        return samples
    scaled = samples.astype(np.float32) * np.float32(10.0 ** (gain_db / 20.0))
    if gain_db < 0:
        return scaled
    size = np.abs(scaled)
    room = LIMIT_CEILING - LIMIT_KNEE
    bent = LIMIT_KNEE + room * np.tanh((size - LIMIT_KNEE) / room)
    return np.where(size > LIMIT_KNEE, np.sign(scaled) * bent, scaled).astype(np.float32)


def tempo_filter(factor: float) -> str | None:
    """An ffmpeg audio filter making speech ``factor`` times faster with its pitch kept
    (``atempo``, 0.5-2); ``None`` for 1. Kokoro speeds itself up instead; OpenRouter's audio
    uses this (DESIGN.md §73)."""
    if factor == 1.0:
        return None
    return f"atempo={min(2.0, max(0.5, factor)):.6f}"


def pitch_filter(semitones: float, rate: int) -> str | None:
    """An ffmpeg audio filter raising the pitch by ``semitones`` while keeping the length
    (``asetrate`` + ``aresample`` + ``atempo``); ``None`` for 0."""
    if semitones == 0.0:
        return None
    shifted = int(round(rate * 2.0 ** (semitones / 12.0)))
    return f"asetrate={shifted},aresample={rate},atempo={rate / shifted:.6f}"
