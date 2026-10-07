"""Timing rules: checks of one scene's activity file (DESIGN.md §17).

They read what the worker recorded while rendering (:mod:`vidgen.activity`): each beat's
narration times and how long its code ran, every ``play``/``wait``, and a per-frame change
signal. ``narration_speed`` also measures the beats' MP3s.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np

from vidgen.config import AnimationOverrunRule, DeadAirRule, NarrationSpeedRule, RushedAnimationRule
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.speech import SILENCE_DB, speech_bounds, spoken_words  # noqa: F401  (moved to vidgen.speech in Step 40)

# ----- narration_speed --------------------------------------------------------------------------


@rule("narration_speed", scope="scene")
def narration_speed(ctx: SceneContext, settings: NarrationSpeedRule) -> Iterator[Issue]:
    """A beat spoken faster or slower than the configured words per second (words of the
    spoken text: the pronunciation applied, so "SQL" said "sequel" counts 1, not 1.5)."""
    for beat in ctx.beats:
        words = spoken_words(ctx.spoken_text(beat))
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
    last change) stays on screen until frame ``end`` (the next change, or the scene's end — or
    where a crossfade into the next scene starts blending it away, DESIGN.md §49)."""
    frames = int(activity["frames"])
    end = frames - int(activity.get("overlap_out", 0))
    changes = sorted(frame for frame, fraction in activity["motion"]["changes"] if fraction >= min_change and frame < end)
    marks = [0, *(f for f in changes if f > 0), end]
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
