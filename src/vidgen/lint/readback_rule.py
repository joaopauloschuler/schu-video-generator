"""The lint rules on speech to text (DESIGN.md §57, §78).

- ``readback``: beats whose audio was heard differently from their text by ``vidgen readback``.
  It only reads the transcripts that command cached (it never runs speech to text), so it finds
  nothing until ``vidgen readback`` has run.
- ``unclear_speech``: words heard with low confidence, after an unusual pause or differently from
  the text (:mod:`vidgen.speech_flags`). It runs only when asked (``vidgen lint --readback``),
  because the runner then transcribes the beats that have no cached transcript (slow).
"""

from __future__ import annotations

from collections.abc import Iterator

from vidgen.config import ReadbackRule, UnclearSpeechRule
from vidgen.lint.rules import Issue, SceneContext, rule

#: Differences quoted in a finding's message (the rest are counted).
SHOWN_EDITS = 3


@rule("readback", scope="scene")
def readback(ctx: SceneContext, settings: ReadbackRule) -> Iterator[Issue]:
    """A beat whose transcribed audio differs from its text by more than ``max_wer``."""
    starts = {beat["id"]: beat["start"] for beat in ctx.beats}
    for beat_id, result in ctx.readback.items():
        if result.wer <= settings.max_wer:
            continue
        shown = "; ".join(edit.describe() for edit in result.edits[:SHOWN_EDITS])
        more = f" and {len(result.edits) - SHOWN_EDITS} more" if len(result.edits) > SHOWN_EDITS else ""
        fix = f"; fix: {result.suggestions[0]}" if result.suggestions else ""
        yield Issue(
            f"the audio is heard differently from the text: {result.errors} of {result.words} words "
            f"({result.wer:.0%}): {shown}{more}{fix} (details: `vidgen readback --beat {beat_id}`)",
            None,
            value=round(result.wer, 4),
            limit=settings.max_wer,
            beat=beat_id,
            time=float(starts.get(beat_id, 0.0)),
        )


@rule("unclear_speech", scope="scene")
def unclear_speech(ctx: SceneContext, settings: UnclearSpeechRule) -> Iterator[Issue]:
    """A word heard with low confidence, after an unusual pause or differently from the text (with ``--readback``)."""
    starts = {beat["id"]: beat["start"] for beat in ctx.beats}
    for beat_id, flags in ctx.speech_flags.items():
        for flag in flags:
            at = "" if flag.start is None else f" at {flag.start:.2f} s into the beat"
            value: float | None = None
            limit: float | None = None
            if "low_probability" in flag.reasons and flag.probability is not None:
                value = round(flag.probability, 3)
                limit = settings.min_probability if flag.level == "unclear" else settings.doubtful_probability
            elif "gap" in flag.reasons and flag.gap is not None:
                value, limit = round(flag.gap, 3), settings.max_gap
            yield Issue(
                f"{flag.level} speech{at}: {flag.detail}; fix: {flag.suggestion}",
                None,
                severity=None if flag.level == "unclear" else "info",
                value=value,
                limit=limit,
                beat=beat_id,
                time=float(starts.get(beat_id, 0.0)) + (flag.start or 0.0),
            )
