"""The ``readback`` lint rule (DESIGN.md §57): beats whose audio was heard differently from
their text by ``vidgen readback``. It only reads the transcripts that command cached (it never
runs speech to text), so it finds nothing until ``vidgen readback`` has run."""

from __future__ import annotations

from collections.abc import Iterator

from vidgen.config import ReadbackRule
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
