"""Timing rules: checks of one scene's activity file (DESIGN.md §17).

They read what the worker recorded while rendering (:mod:`vidgen.activity`): each beat's
narration times and how long its code ran, every ``play``/``wait``, and a per-frame change
signal. ``narration_speed`` also measures the beats' MP3s.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import numpy as np

from vidgen.config import AnimationOverrunRule, DeadAirRule, NarrationSpeedRule, RushedAnimationRule, TalkedOverRule
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.overlap import talked_over as talked_over_words
from vidgen.speech import SILENCE_DB, speech_bounds, spoken_characters, spoken_words  # noqa: F401  (moved to vidgen.speech in Step 40)

# ----- narration_speed --------------------------------------------------------------------------


@rule("narration_speed", scope="scene")
def narration_speed(ctx: SceneContext, settings: NarrationSpeedRule) -> Iterator[Issue]:
    """A beat spoken faster or slower than the configured words per second (words of the
    spoken text: the pronunciation applied, so "SQL" said "sequel" counts 1, not 1.5). The range
    and unit follow the video's language (DESIGN.md §54): words per second for languages with a
    known word rate, else characters (letters and digits) per second."""
    unit, min_rate, max_rate = settings.limits(ctx.language)
    for beat in ctx.beats:
        text = ctx.spoken_text(beat)
        words = spoken_words(text)
        if words < settings.min_words:
            continue
        amount = words if unit == "words" else float(spoken_characters(text))
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
        rate = amount / seconds
        if min_rate <= rate <= max_rate:
            continue
        fast = rate > max_rate
        limit = max_rate if fast else min_rate
        noun = "words" if unit == "words" else "characters"
        what = f"{amount:g} spoken {noun} in {seconds:.1f} s"
        if estimated:
            message = (
                f"estimated narration speed {rate:.2f} {noun}/s ({what}, no audio yet) is "
                f"{'above' if fast else 'below'} {limit:g}: the duration estimate is off for this text "
                "(numbers and acronyms take longer to say; check narration.words_per_second)"
            )
        elif fast:
            message = (
                f"narration speed {rate:.2f} {noun}/s ({what} of speech) is above {limit:g}: too fast "
                "to follow; shorten the text or split the beat"
            )
        else:
            message = (
                f"narration speed {rate:.2f} {noun}/s ({what} of speech) is below {limit:g}: slow or "
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
    """A beat's animations (and waits) take longer than its narration plus pad (or than the time
    until the next beat, when that one overlaps it)."""
    pad = float(ctx.activity["pad"])
    for beat in ctx.beats:
        d = beat["end"] - beat["start"]
        window = beat.get("window")
        over = beat["busy"] - (d + pad if window is None else window)
        if over <= settings.tolerance:
            continue
        if window is None:
            message = (
                f"the beat's animations take {beat['busy']:.1f} s but its narration lasts {d:.1f} s "
                f"(+{pad:g} s pad): {over:.1f} s of silence before the next beat"
            )
        else:
            message = (
                f"the beat's animations take {beat['busy']:.1f} s but the next beat, which overlaps it, "
                f"was to start after {window:.1f} s: it starts {over:.1f} s late"
            )
        yield Issue(
            f"{message}; still running when the narration ends: {_plays(ctx, beat['id'], beat['end'])}",
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


#: The animations of a walk or a jump on a platform level (DESIGN.md §86.7) or a walk on an iso
#: place (§89.9), as the play log names them.
LEVEL_MOVES = ("RouteWalk", "ArcJump", "IsoWalk")


@rule("rushed_animation", scope="scene")
def rushed_animation(ctx: SceneContext, settings: RushedAnimationRule) -> Iterator[Issue]:
    """Animations ``play_steps`` shortened below ``min_run_time`` to fit a short beat; walks and
    jumps on a platform level sped up more than ``max_speedup`` times to fit theirs."""
    yield from _rushed_moves(ctx, settings)
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


def _rushed_moves(ctx: SceneContext, settings: RushedAnimationRule) -> Iterator[Issue]:
    for play in ctx.activity["plays"]:
        seconds = play["end"] - play["start"]
        names = "+".join(play["animations"])
        if play["requested"] is None or seconds <= 0 or not any(move in names for move in LEVEL_MOVES):
            continue
        speedup = play["requested"] / seconds
        if speedup <= settings.max_speedup + 1e-6:
            continue
        beat = next((b for b in ctx.beats if b["id"] == play["beat"]), None)
        length = f"the beat ({beat['end'] - beat['start']:.1f} s of narration)" if beat else "the scene"
        yield Issue(
            f"a walk or jump on the {'iso place' if 'IsoWalk' in names else 'level'} plays {speedup:.1f} times as fast as its own pace ({names}: {seconds:.1f} s instead of "
            f"{play['requested']:.1f} s): {length} is too short for it; give the beat more narration, start the move earlier (at), "
            "or split the way over two beats",
            None,
            value=round(speedup, 3),
            limit=settings.max_speedup,
            beat=play["beat"],
            time=play["start"],
        )


# ----- talked_over ------------------------------------------------------------------------------


@rule("talked_over", scope="scene")
def talked_over(ctx: SceneContext, settings: TalkedOverRule) -> Iterator[Issue]:
    """Whole words of a line spoken while the next beat, which overlaps it, already speaks, or
    cut before they start by the next beat's interrupt."""
    from vidgen.speech import beat_word_times

    beats = ctx.beats
    for before, beat in zip(beats, beats[1:]):
        if beat.get("overlap") is None:
            continue
        if beat.get("interrupt"):
            yield from _cut_words(ctx, before, beat)
            continue
        follower = beat["start"]
        audio = ctx.audio_dir / f"{beat['id']}.mp3"
        if beat["source"] == "audio" and audio.is_file():
            follower += speech_bounds(audio)[0]
        words = beat_word_times(ctx.audio_dir, before["id"], before["text"], before["start"], before["end"], language=ctx.language)
        hidden = talked_over_words(words, follower, before["end"])
        if not hidden:
            continue
        said = " ".join(w.text for w in hidden)
        yield Issue(
            f"beat {beat['id']} starts {beat['overlap']:g} s before the line of {before['id']} ends and speaks over "
            f"its last word{'s' if len(hidden) > 1 else ''} \"{said}\": shorten the overlap (below "
            f"{max(beat['overlap'] - (hidden[0].start - follower), 0.0):.2f} s here) or use interrupt: true to cut the line",
            None,
            value=len(hidden),
            limit=0,
            beat=before["id"],
            time=round(hidden[0].start, 6),
        )


def _cut_words(ctx: SceneContext, before: dict[str, Any], beat: dict[str, Any]) -> Iterator[Issue]:
    """The ``talked_over`` issue of an interrupt that cuts the line ``before`` ahead of whole
    words (its ``end`` is the cut). Only for a line with audio: an estimate has no words to cut."""
    from vidgen.speech import audio_duration, beat_word_times

    audio = ctx.audio_dir / f"{before['id']}.mp3"
    if before["source"] != "audio" or not audio.is_file():
        return
    cut = before["end"]
    words = beat_word_times(ctx.audio_dir, before["id"], before["text"], before["start"], before["start"] + audio_duration(audio), language=ctx.language)
    hidden = talked_over_words(words, cut, math.inf)
    if not hidden:
        return
    said = " ".join(w.text for w in hidden)
    lead = float(beat["overlap"])
    yield Issue(
        f"beat {beat['id']} interrupts the line of {before['id']} {lead:g} s before its speech ends and cuts "
        f"its last word{'s' if len(hidden) > 1 else ''} \"{said}\" before {'they start' if len(hidden) > 1 else 'it starts'}: "
        f"start it later (overlap below {max(lead - (hidden[0].start - cut), 0.0):.2f} s here) so at most the end of the last word is cut",
        None,
        value=len(hidden),
        limit=0,
        beat=before["id"],
        time=round(hidden[0].start, 6),
    )
