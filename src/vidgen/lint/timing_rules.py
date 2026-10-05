"""Timing rules: checks of one scene's activity file (DESIGN.md §17).

They read what the worker recorded while rendering (:mod:`vidgen.activity`): each beat's
narration times and how long its code ran, every ``play``/``wait``, and a per-frame change
signal. ``narration_speed`` also measures the beats' MP3s.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

import av
import numpy as np

from vidgen.config import AnimationOverrunRule, DeadAirRule, NarrationSpeedRule, RushedAnimationRule
from vidgen.errors import VidgenError
from vidgen.lint.rules import Issue, SceneContext, rule

# ----- spoken words -----------------------------------------------------------------------------

_TOKEN = re.compile(r"[^\s\-–—/]+")  # hyphens, dashes and slashes separate words ("one-by-one": 3)
_EDGE = ".,;:!?\"'()[]{}…“”‘’«»"
_ACRONYM = re.compile(r"[A-Z]{2,5}s?")
_SYMBOLS = re.compile(r"[%$€£+=×&#@]")


def spoken_words(text: str) -> float:
    """How many words a narrator says for ``text`` (an estimate for counting speech rate).

    Words split at spaces, hyphens, dashes and slashes (``K-Phi-3`` is 3, ``one-by-one`` 3). In
    a token with digits every digit run counts as ``min(len, 3)`` words ("227": "two hundred
    twenty-seven"), a decimal or thousands separator before a digit as one ("point"), symbols
    ``% $ € £ + = × & # @`` as one each, and letters next to the digits as one more. An
    all-capitals acronym of 2-5 letters (``GPU``, ``NVIDIA`` is a word) counts half a word per
    letter, at least one. Everything else is one word.
    """
    total = 0.0
    for token in _TOKEN.findall(text):
        core = token.strip(_EDGE)
        if not core:
            continue
        if any(ch.isdigit() for ch in core):
            total += sum(min(len(run), 3) for run in re.findall(r"\d+", core))
            total += len(re.findall(r"[.,]\d", core))
            total += len(_SYMBOLS.findall(core))
            total += 1 if any(ch.isalpha() for ch in core) else 0
        elif _ACRONYM.fullmatch(core):
            total += max(1.0, len(core.rstrip("s")) / 2)
        elif any(ch.isalnum() for ch in core):
            total += 1
        else:
            total += len(_SYMBOLS.findall(core))
    return total


#: Speech starts/ends where the 10 ms envelope first/last exceeds this level below the peak.
SILENCE_DB = -40.0


@lru_cache(maxsize=256)
def _speech_bounds(path: Path, mtime_ns: int) -> tuple[float, float]:
    try:
        with av.open(str(path)) as container:
            stream = container.streams.audio[0]
            rate = stream.rate or 0
            chunks: list[np.ndarray] = []
            for frame in container.decode(stream):
                samples = frame.to_ndarray()
                if not frame.format.is_planar:
                    samples = samples.reshape(-1, len(frame.layout.channels)).T
                chunks.append(np.abs(samples.astype(np.float32)).max(axis=0))
                rate = frame.sample_rate or rate
    except (OSError, ValueError, IndexError, av.error.FFmpegError) as exc:
        raise VidgenError(f"cannot read audio file {path}: {exc}") from None
    if not chunks or not rate:
        raise VidgenError(f"cannot read audio file {path}: no audio samples")
    level = np.concatenate(chunks)
    window = max(1, int(rate * 0.01))
    count = len(level) // window
    if count == 0:
        return 0.0, len(level) / rate
    envelope = level[: count * window].reshape(count, window).max(axis=1)
    loud = np.nonzero(envelope > envelope.max() * 10 ** (SILENCE_DB / 20))[0]
    if loud.size == 0:
        return 0.0, len(level) / rate
    return float(loud[0] * window / rate), float((loud[-1] + 1) * window / rate)


def speech_bounds(path: Path) -> tuple[float, float]:
    """Start and end (seconds) of the speech in an audio file: the leading and trailing
    silence (below :data:`SILENCE_DB` relative to its loudest 10 ms) cut off."""
    return _speech_bounds(path, path.stat().st_mtime_ns)


# ----- narration_speed --------------------------------------------------------------------------


@rule("narration_speed", scope="scene")
def narration_speed(ctx: SceneContext, settings: NarrationSpeedRule) -> Iterator[Issue]:
    """A beat spoken faster or slower than the configured words per second."""
    for beat in ctx.beats:
        words = spoken_words(beat["text"])
        if words < settings.min_words:
            continue
        audio = ctx.audio_dir / f"{beat['id']}.mp3"
        if beat["source"] == "audio" and audio.is_file():
            start, end = speech_bounds(audio)
            seconds, estimated = end - start, False
        else:
            # No audio: d is the word-count estimate, so the rate only shows how far numbers
            # and acronyms (or narration.words_per_second itself) are from plausible speech.
            seconds, estimated = beat["end"] - beat["start"], True
        if seconds <= 0:
            continue
        rate = words / seconds
        if settings.min_rate <= rate <= settings.max_rate:
            continue
        fast = rate > settings.max_rate
        limit = settings.max_rate if fast else settings.min_rate
        what = f"{words:g} spoken words in {seconds:.1f} s"
        if estimated:
            message = (
                f"estimated narration speed {rate:.2f} words/s ({what}, no audio yet) is "
                f"{'above' if fast else 'below'} {limit:g}: the duration estimate is off for this text "
                "(numbers and acronyms take longer to say; check narration.words_per_second)"
            )
        elif fast:
            message = (
                f"narration speed {rate:.2f} words/s ({what} of speech) is above {limit:g}: too fast "
                "to follow; shorten the text or split the beat"
            )
        else:
            message = (
                f"narration speed {rate:.2f} words/s ({what} of speech) is below {limit:g}: slow or "
                "long pauses; check the audio or tighten the text"
            )
        yield Issue(
            message,
            None,
            severity="info" if estimated else None,
            value=round(rate, 3),
            limit=limit,
            group=("estimate", fast) if estimated else None,
            beat=beat["id"],
            time=beat["start"],
        )


# ----- dead_air ---------------------------------------------------------------------------------


def static_runs(activity: dict[str, Any], min_change: float) -> list[tuple[int, int]]:
    """``(first, end)`` frame ranges in which the picture does not change: frame ``first`` (the
    last change) stays on screen until frame ``end`` (the next change, or the scene's end)."""
    changes = sorted(frame for frame, fraction in activity["motion"]["changes"] if fraction >= min_change)
    marks = [0, *(f for f in changes if f > 0), int(activity["frames"])]
    return [(a, b) for a, b in zip(marks, marks[1:]) if b > a]


@rule("dead_air", scope="scene")
def dead_air(ctx: SceneContext, settings: DeadAirRule) -> Iterator[Issue]:
    """Nothing on screen changes for longer than ``max_seconds``."""
    fps = ctx.fps
    for first, end in static_runs(ctx.activity, settings.min_change):
        seconds = (end - first) / fps
        if seconds <= settings.max_seconds:
            continue
        start, stop = first / fps, end / fps
        beats = list(dict.fromkeys(b for b in (ctx.beat_at(t) for t in np.arange(start, stop, 0.1)) if b))
        during = f" during beat{'s' if len(beats) > 1 else ''} {', '.join(beats)}" if beats else " (silent scene)"
        yield Issue(
            f"nothing on screen changes for {seconds:.1f} s ({start:.1f}-{stop:.1f} s){during}: "
            "reveal, highlight or move something, or shorten the hold",
            None,
            value=round(seconds, 3),
            limit=settings.max_seconds,
            beat=ctx.beat_at(start),
            time=round(start, 6),
        )


# ----- animation_overrun ------------------------------------------------------------------------


def _plays(ctx: SceneContext, beat: str | None, after: float) -> str:
    names = [
        f"{'+'.join(p['animations']) or 'play'} ({p['start']:.1f}-{p['end']:.1f} s)"
        for p in ctx.activity["plays"]
        if p["beat"] == beat and not p["wait"] and p["end"] > after + 1e-6
    ]
    if not names:
        return "only waits"
    return ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")


@rule("animation_overrun", scope="scene")
def animation_overrun(ctx: SceneContext, settings: AnimationOverrunRule) -> Iterator[Issue]:
    """A beat's animations (and waits) take longer than its narration plus pad."""
    pad = float(ctx.activity["pad"])
    for beat in ctx.beats:
        d = beat["end"] - beat["start"]
        over = beat["busy"] - (d + pad)
        if over <= settings.tolerance:
            continue
        yield Issue(
            f"the beat's animations take {beat['busy']:.1f} s but its narration lasts {d:.1f} s "
            f"(+{pad:g} s pad): {over:.1f} s of silence before the next beat; still running when the "
            f"narration ends: {_plays(ctx, beat['id'], beat['end'])}",
            None,
            value=round(over, 3),
            limit=settings.tolerance,
            beat=beat["id"],
            time=beat["end"],
        )
    silent = ctx.activity.get("silent")
    if silent and silent.get("duration") is not None:
        over = silent["busy"] - silent["duration"]
        if over > settings.tolerance:
            yield Issue(
                f"the scene's animations take {silent['busy']:.1f} s, longer than its duration "
                f"{silent['duration']:g} s: {_plays(ctx, None, silent['duration'])}",
                None,
                value=round(over, 3),
                limit=settings.tolerance,
                time=float(silent["duration"]),
            )


# ----- rushed_animation -------------------------------------------------------------------------


@rule("rushed_animation", scope="scene")
def rushed_animation(ctx: SceneContext, settings: RushedAnimationRule) -> Iterator[Issue]:
    """Animations ``play_steps`` shortened below ``min_run_time`` to fit a short beat."""
    rushed: dict[str | None, list[dict[str, Any]]] = {}
    for play in ctx.activity["plays"]:
        if play["requested"] is not None and play["end"] - play["start"] < settings.min_run_time - 1e-6:
            rushed.setdefault(play["beat"], []).append(play)
    for beat_id, plays in rushed.items():
        shortest = min(p["end"] - p["start"] for p in plays)
        beat = next((b for b in ctx.beats if b["id"] == beat_id), None)
        length = f"the beat ({beat['end'] - beat['start']:.1f} s of narration)" if beat else "the scene"
        steps = f"{len(plays)} step{'s' if len(plays) > 1 else ''}"
        yield Issue(
            f"{steps} play in {shortest:.2f} s instead of {plays[0]['requested']:g} s "
            f"({', '.join('+'.join(p['animations']) for p in plays[:3])}{'…' if len(plays) > 3 else ''}): "
            f"{length} is too short for its steps; give it more narration or fewer steps",
            None,
            value=round(shortest, 3),
            limit=settings.min_run_time,
            beat=beat_id,
            time=plays[0]["start"],
        )
