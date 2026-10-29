"""Shorts rules (DESIGN.md §101): a vertical Short (the config's ``shorts:``) checked for what the
phone app covers and for its length.

``shorts_safe_area`` reads a still's layout dump: the header's ``shorts`` box (px, the part of the
frame the app leaves clear, written only for a Short), the text objects (the scene's and the
overlays') and the characters' ``face`` boxes. An overlay object's ``reach`` (captions: the box of
every caption of the line being spoken) stands for the overlay when faces are checked, so a face
that a longer caption of the same line covers is found from any still of it. ``shorts_length`` is a scene rule: it reads the
video's planned length (``SceneContext.video_seconds``), set on the video's last scene only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from vidgen.config import ShortsLengthRule, ShortsSafeAreaRule
from vidgen.lint.layout_rules import area, describe, has_letters_or_digits, intersection, is_overlay, is_text, object_box
from vidgen.lint.rules import Bbox, Issue, SceneContext, StillContext, rule


def _sides(box: Bbox, clear: Bbox, tolerance: float) -> list[str]:
    """The sides of ``clear`` that ``box`` reaches past by more than ``tolerance`` (px)."""
    past = {"left": clear[0] - box[0], "top": clear[1] - box[1], "right": box[2] - clear[2], "bottom": box[3] - clear[3]}
    return [side for side, px in past.items() if px > tolerance]


def _covered(box: Bbox, clear: Bbox) -> float:
    """Share of ``box`` outside ``clear``."""
    inside = intersection(box, clear)
    return 1.0 - (area(inside) if inside is not None else 0.0) / max(area(box), 1e-9)


def _faces(ctx: StillContext) -> list[dict[str, Any]]:
    """Characters on screen whose face shows (not hidden by a clear shot)."""
    frame = (0.0, 0.0, float(ctx.width), float(ctx.height))
    out = []
    for obj in ctx.objects:
        face = obj.get("face")
        if obj["kind"] != "character" or obj.get("hidden") or not face:
            continue
        if intersection(tuple(float(v) for v in face), frame) is not None:   # type: ignore[arg-type]
            out.append(obj)
    return out


@rule("shorts_safe_area", mid_beat=True)
def shorts_safe_area(ctx: StillContext, settings: ShortsSafeAreaRule) -> Iterator[Issue]:
    """In a Short, text or a face where the phone app covers the frame, or an overlay (a caption,
    the hook) over a face."""
    if "shorts" not in ctx.layout:
        return
    clear: Bbox = tuple(float(v) for v in ctx.layout["shorts"])   # type: ignore[assignment]
    tolerance = settings.tolerance * ctx.short_side
    for obj in ctx.objects:
        if not is_text(obj) or not has_letters_or_digits(obj):
            continue
        box = object_box(obj)
        if intersection(box, (0, 0, ctx.width, ctx.height)) is None:
            continue
        sides = _sides(box, clear, tolerance)
        if sides:
            yield Issue(
                f"{describe(obj)} reaches the {' and '.join(sides)} of the frame, where the Shorts app puts its "
                "buttons and texts; move it inwards (overlays keep out of it on their own)",
                box,
                (obj,),
                group=("shorts_text", obj.get("overlay")) if is_overlay(obj) else None,
            )
    overlays: dict[str, list[Bbox]] = {}
    reaching: set[str] = set()
    for obj in ctx.objects:
        if is_overlay(obj):   # its reach: where it goes around this moment (all captions of the line)
            box = tuple(float(v) for v in obj["reach"]) if obj.get("reach") else object_box(obj)
            overlays.setdefault(str(obj["overlay"]), []).append(box)   # type: ignore[arg-type]
            if obj.get("reach"):
                reaching.add(str(obj["overlay"]))
    for figure in _faces(ctx):
        face: Bbox = tuple(float(v) for v in figure["face"])   # type: ignore[assignment]
        under = _covered(face, clear)
        if under >= settings.min_face:
            yield Issue(
                f"the face of {describe(figure)} is {under:.0%} under the Shorts app's buttons and texts; "
                "frame it higher or further left (a shot, a zoom, where it stands)",
                face,
                (figure,),
                value=round(under, 3),
                limit=settings.min_face,
            )
        for overlay, boxes in overlays.items():
            union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
            shared = intersection(face, union)
            share = area(shared) / max(area(face), 1e-9) if shared is not None else 0.0
            if share >= settings.min_cover:
                yield Issue(
                    f"overlay '{overlay}' covers {share:.0%} of the face of {describe(figure)}"
                    f"{' (while this line is shown)' if overlay in reaching else ''}; "
                    "frame the shot so the face is above the captions (or move the overlay)",
                    shared,
                    (figure,),
                    value=round(share, 3),
                    limit=settings.min_cover,
                    group=("shorts_face", overlay),
                )


@rule("shorts_length", scope="scene", default="error")
def shorts_length(ctx: SceneContext, settings: ShortsLengthRule) -> Iterator[Issue]:
    """A Short longer than its ``max_seconds`` (checked on the video's last scene)."""
    if ctx.video_seconds is None or ctx.shorts_max is None or ctx.video_seconds <= ctx.shorts_max + 1e-6:
        return
    yield Issue(
        f"the Short is {ctx.video_seconds:.1f} s long, over its {ctx.shorts_max:g} s (shorts.max_seconds); "
        "leave out beats or scenes (cut:), or shorten the end card",
        None,
        value=round(ctx.video_seconds, 2),
        limit=ctx.shorts_max,
    )
