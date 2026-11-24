"""The frame arithmetic of chained parts (DESIGN.md §113.22).

A later part of a split beat starts from a picture of the part before it. LTX gives that picture
back as its own frame 0, so the film would show the same picture twice at the join. The later
part is therefore made :data:`CHAIN_DROP_FRAMES` frames longer at its start and those frames are
hidden behind the part before it:

- its picture is the frame the film shows ``CHAIN_DROP_FRAMES`` frames before the part's first
  film frame (with 1: the last frame of the part before it);
- its guide starts at that same film frame, so the take's frame ``i`` lines up with film frame
  ``conditioning + i``;
- it is laid in from its frame ``CHAIN_DROP_FRAMES`` on (its ``lead``).

Times are in a scene's render (seconds); frames are the film's (``fps``; exact when the model's
frame rate is the film's).
"""

from __future__ import annotations

#: Frames of a chained part's take hidden behind the part before it (LTX's frame 0 copies its picture).
CHAIN_DROP_FRAMES = 1


def frame_index(seconds: float, fps: float) -> int:
    """The film frame a placement starting at ``seconds`` starts on (rounding noise removed)."""
    return round(round(seconds * fps, 6))


def lead_frames(part: int, first_frame_source: str) -> int:
    """Frames a part's take starts before its part: :data:`CHAIN_DROP_FRAMES` for a later part
    with a starting picture (a chained part), else 0."""
    return CHAIN_DROP_FRAMES if part > 1 and first_frame_source != "none" else 0


def guide_span(start: float, length: float, lead: int, fps: float) -> tuple[float, float]:
    """``(start, length)`` of the render a part's guide is cut from: from ``lead`` frames before
    the part's first film frame to the part's end (``start`` / ``length``: the part's). It begins
    a quarter frame early, so a cut that keeps the frames from its start keeps that frame."""
    if lead == 0:
        return start, length
    begin = (frame_index(start, fps) - lead - 0.25) / fps
    return begin, start + length - begin


def picture_at(start: float, length: float, lead: int, previous_lead: int, fps: float) -> float:
    """Seconds into the previous part's take of a chained part's picture: the frame the film shows
    ``lead`` frames before this part's first frame (``start`` / ``length``: this part's, the
    previous part as long; ``previous_lead``: that take's own lead)."""
    shown = frame_index(start, fps) - lead - frame_index(start - length, fps)
    return max(0, shown + previous_lead) / fps


__all__ = ["CHAIN_DROP_FRAMES", "frame_index", "guide_span", "lead_frames", "picture_at"]
