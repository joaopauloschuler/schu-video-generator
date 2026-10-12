"""Cartoon rules: checks of the characters in one still's layout dump (DESIGN.md §69.12, §69.17).

They read the keys the layout dump gives a ``character`` object (``facing``, ``speaking``,
``face``, ``viseme``, ``looked_at``, ``passage``, ``walked_in``), the ``bubble`` key of a speech
bubble's objects, the ``effect`` objects (symbols over heads, §69.40) and the frame's
``narrating``. Like every still rule they see beat-end stills
only (mid-action stills are skipped by the runner).
"""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations
from typing import Any

import numpy as np

from vidgen.config import (
    BubbleOverlapRule,
    CharacterOverlapRule,
    FacingAwayRule,
    HiddenSpeakerRule,
    MouthWithoutVoiceRule,
    OffStageRule,
    WalkOverlapRule,
)
from vidgen.lint.layout_rules import area, describe, intersection, is_text, object_box
from vidgen.lint.rules import Bbox, Issue, StillContext, rule

#: Points per side of the grid on which :func:`_covered_share` samples a face.
_FACE_SAMPLES = 12


def _figures(ctx: StillContext) -> list[dict[str, Any]]:
    return [obj for obj in ctx.objects if obj["kind"] == "character"]


def _in_view(ctx: StillContext, obj: dict[str, Any]) -> bool:
    return intersection(object_box(obj), (0, 0, ctx.width, ctx.height)) is not None


def _side_share(a: Bbox, b: Bbox) -> float | None:
    """How much of the narrower box's width two overlapping boxes share (``None``: apart)."""
    box = intersection(a, b)
    if box is None:
        return None
    return (box[2] - box[0]) / max(min(a[2] - a[0], b[2] - b[0]), 1e-9)


def _face_x(obj: dict[str, Any]) -> float:
    box = obj.get("face") or obj["bbox"]
    return (float(box[0]) + float(box[2])) / 2


def _covered_share(box: Bbox, covers: list[Bbox]) -> float:
    """Share of ``box`` inside any of ``covers`` (sampled on a grid)."""
    xs = np.linspace(box[0], box[2], _FACE_SAMPLES)
    ys = np.linspace(box[1], box[3], _FACE_SAMPLES)
    gx, gy = np.meshgrid(xs, ys)
    hit = np.zeros(gx.shape, dtype=bool)
    for c in covers:
        hit |= (gx >= c[0]) & (gx <= c[2]) & (gy >= c[1]) & (gy <= c[3])
    return float(hit.mean())


@rule("walk_overlap")
def walk_overlap(ctx: StillContext, settings: WalkOverlapRule) -> Iterator[Issue]:
    """A character's walk (``walk_to``, ``enter``) ends on another character."""
    figures = _figures(ctx)
    beat = ctx.frame.get("beat")
    for k, walker in enumerate(figures):
        if beat is None or walker.get("walked_in") != beat:
            continue
        for j, other in enumerate(figures):
            if other is walker or (j < k and other.get("walked_in") == beat):
                continue  # a pair that both walked is reported once
            share = _side_share(object_box(walker), object_box(other))
            if share is None or share < settings.min_overlap:
                continue
            yield Issue(
                f"{describe(walker)} ends its walk on {describe(other)} ({share:.0%} of the narrower one's width); "
                "walk it to another mark or x, or move the other character first",
                intersection(object_box(walker), object_box(other)),
                (walker, other),
                value=round(share, 3),
                limit=settings.min_overlap,
            )


#: Shots (DESIGN.md §69.29) whose subjects need only their face in view (the frame cuts the rest).
FACE_SHOTS = frozenset({"medium", "over_shoulder", "closeup"})


def _off_shot(ctx: StillContext, settings: OffStageRule, shot: dict[str, Any]) -> Iterator[Issue]:
    """``off_stage`` in a shot: each character it frames is in view (its face in a medium,
    over-the-shoulder or close-up shot, else its whole box); the near character of an
    over-the-shoulder shot and characters the shot does not frame may be cut by the frame."""
    kind = str(shot.get("kind"))
    subjects = set(shot.get("subjects") or ())
    for obj in _figures(ctx):
        if obj.get("passage") or obj.get("name") not in subjects:
            continue
        what, box = ("face", tuple(float(v) for v in obj["face"])) if kind in FACE_SHOTS and obj.get("face") else ("box", object_box(obj))
        seen = intersection(box, (0, 0, ctx.width, ctx.height))
        hidden = 1.0 if seen is None else 1 - area(seen) / max(area(box), 1e-9)
        if hidden < settings.min_hidden:
            continue
        yield Issue(
            f"{describe(obj)} is out of the {kind} shot that frames it ({hidden:.0%} of its {what} outside the view); "
            "frame it in a later beat or another shot, or keep it from walking out during the shot",
            box,
            (obj,),
            value=round(hidden, 3),
            limit=settings.min_hidden,
        )


@rule("off_stage")
def off_stage(ctx: StillContext, settings: OffStageRule) -> Iterator[Issue]:
    """A character is partly outside the view (not while it enters or exits, nor while the
    camera is zoomed in); in a shot, a character the shot frames is out of it."""
    shot = ctx.frame.get("shot")
    if shot and shot.get("kind") != "wide":
        yield from _off_shot(ctx, settings, shot)
        return
    if ctx.zoomed:
        return
    width, height = ctx.width, ctx.height
    for obj in _figures(ctx):
        if obj.get("passage"):
            continue
        box = object_box(obj)
        seen = intersection(box, (0, 0, width, height))
        if seen is None:
            continue  # wholly outside: waiting off stage
        hidden = 1 - area(seen) / max(area(box), 1e-9)
        if hidden < settings.min_hidden:
            continue
        outside = {"left": -box[0], "top": -box[1], "right": box[2] - width, "bottom": box[3] - height}
        sides = [side for side, px in outside.items() if px > 0]
        yield Issue(
            f"{describe(obj)} is partly off stage at the {' and '.join(sides)} edge ({hidden:.0%} of its box "
            "outside the view); put it on a mark inside the view (another `at` or `walk_to`), or pan the camera to it",
            box,
            (obj,),
            value=round(hidden, 3),
            limit=settings.min_hidden,
        )


@rule("character_overlap")
def character_overlap(ctx: StillContext, settings: CharacterOverlapRule) -> Iterator[Issue]:
    """Two characters stand on each other at rest (a walk that ends so is ``walk_overlap``'s)."""
    beat = ctx.frame.get("beat")
    resting = [obj for obj in _figures(ctx) if not obj.get("passage") and (beat is None or obj.get("walked_in") != beat)]
    for a, b in combinations(resting, 2):
        share = _side_share(object_box(a), object_box(b))
        if share is None or share < settings.min_overlap:
            continue
        yield Issue(
            f"{describe(a)} and {describe(b)} stand on each other ({share:.0%} of the narrower one's width); "
            "put them on marks further apart, or walk one of them away",
            intersection(object_box(a), object_box(b)),
            (a, b),
            value=round(share, 3),
            limit=settings.min_overlap,
        )


def _bubbles(ctx: StillContext) -> dict[str, list[dict[str, Any]]]:
    """Speaker name -> the objects of its speech bubble (plate first: the largest)."""
    found: dict[str, list[dict[str, Any]]] = {}
    for obj in ctx.objects:
        if obj.get("bubble") is not None:
            found.setdefault(str(obj["bubble"]), []).append(obj)
    return {name: sorted(objs, key=lambda o: -area(object_box(o))) for name, objs in found.items()}


def _union(objs: list[dict[str, Any]]) -> Bbox:
    boxes = [object_box(o) for o in objs]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


@rule("bubble_overlap")
def bubble_overlap(ctx: StillContext, settings: BubbleOverlapRule) -> Iterator[Issue]:
    """A speech bubble covers a character's face, another speech bubble or an effect symbol."""
    bubbles = _bubbles(ctx)
    for speaker, objs in bubbles.items():
        box = _union(objs)
        for symbol in (obj for obj in ctx.objects if obj["kind"] == "effect"):
            covered = intersection(box, object_box(symbol))
            share = 0.0 if covered is None else area(covered) / max(area(object_box(symbol)), 1e-9)
            if covered is None or share < settings.min_overlap:
                continue
            yield Issue(
                f"the speech bubble of character '{speaker}' covers the {describe(symbol)} ({share:.0%} of the symbol); "
                "put the effect in another beat, give the say a shorter bubble text, or put the characters further apart",
                covered,
                (objs[0], symbol),
                value=round(share, 3),
                limit=settings.min_overlap,
            )
    for speaker, objs in bubbles.items():
        box = _union(objs)
        for figure in _figures(ctx):
            if not figure.get("face"):
                continue
            face = tuple(float(v) for v in figure["face"])
            covered = intersection(box, face)
            share = 0.0 if covered is None else area(covered) / max(area(face), 1e-9)
            if covered is None or share < settings.min_overlap:
                continue
            whose = "its speaker's own face" if figure.get("name") == speaker else f"the face of {describe(figure)}"
            yield Issue(
                f"the speech bubble of character '{speaker}' covers {whose} ({share:.0%} of the face); "
                "give the say a shorter bubble text, or put the characters further apart",
                covered,
                (objs[0], figure),
                value=round(share, 3),
                limit=settings.min_overlap,
            )
    for (a, a_objs), (b, b_objs) in combinations(bubbles.items(), 2):
        box_a, box_b = _union(a_objs), _union(b_objs)
        covered = intersection(box_a, box_b)
        if covered is None:
            continue
        share = area(covered) / max(min(area(box_a), area(box_b)), 1e-9)
        if share < settings.min_overlap:
            continue
        yield Issue(
            f"the speech bubbles of character '{a}' and character '{b}' overlap ({share:.0%} of the smaller one); "
            "let them speak in different beats, shorten the bubble texts, or put the characters further apart",
            covered,
            (a_objs[0], b_objs[0]),
            value=round(share, 3),
            limit=settings.min_overlap,
        )


def _listener(speaker: dict[str, Any], others: list[dict[str, Any]]) -> tuple[dict[str, Any], str] | None:
    """Whom ``speaker`` talks to and why: the character it last looked at, else the nearest one;
    ``None`` when it addresses the viewer (looked at the camera) or no one else is in view."""
    looked = speaker.get("looked_at")
    if looked == "camera" or not others:
        return None
    for other in others:
        if other.get("name") == looked:
            return other, "the one it last looked at"
    x = _face_x(speaker)
    return min(others, key=lambda o: abs(_face_x(o) - x)), "the nearest character"


@rule("facing_away")
def facing_away(ctx: StillContext, settings: FacingAwayRule) -> Iterator[Issue]:
    """A speaking character faces away from the character it talks to (the one it last looked
    at, else the nearest one)."""
    figures = [obj for obj in _figures(ctx) if _in_view(ctx, obj)]
    tolerance = 0.02 * ctx.short_side
    for speaker in figures:
        if not speaker.get("speaking") or speaker.get("facing") not in ("left", "right"):
            continue
        found = _listener(speaker, [o for o in figures if o is not speaker])
        if found is None:
            continue
        listener, why = found
        dx = _face_x(listener) - _face_x(speaker)
        if abs(dx) < tolerance or (dx > 0) == (speaker["facing"] == "right"):
            continue
        side = "left" if dx < 0 else "right"
        yield Issue(
            f"{describe(speaker)} speaks facing {speaker['facing']}, away from {describe(listener)} ({why}, on its "
            f"{side}); turn it (turn, or look_at: {listener.get('name')}) or swap their marks",
            object_box(speaker),
            (speaker, listener),
            value=round(abs(dx) / ctx.short_side, 4),
        )


@rule("hidden_speaker")
def hidden_speaker(ctx: StillContext, settings: HiddenSpeakerRule) -> Iterator[Issue]:
    """A speaking character's face is hidden by something drawn in front of it (a character or
    prop nearer the camera, a foreground layer; not an effect symbol): the viewer cannot see who
    talks."""
    for speaker in _figures(ctx):
        if not speaker.get("speaking") or not speaker.get("face"):
            continue
        face = tuple(float(v) for v in speaker["face"])
        fronts = [
            obj for obj in ctx.objects
            if obj["order"] > speaker["order"] and not is_text(obj) and obj["kind"] not in ("particles", "effect")
            and obj.get("bubble") is None and intersection(object_box(obj), face) is not None
        ]
        if not fronts:
            continue
        share = _covered_share(face, [object_box(o) for o in fronts])
        if share < settings.min_hidden:
            continue
        front = max(fronts, key=lambda o: area(intersection(object_box(o), face) or (0, 0, 0, 0)))
        yield Issue(
            f"{describe(speaker)} speaks with {share:.0%} of its face hidden behind {describe(front)}; move it or what "
            "is in front of it, or bring it nearer the camera (a smaller depth)",
            face,
            (speaker, front),
            value=round(share, 3),
            limit=settings.min_hidden,
        )


@rule("mouth_without_voice")
def mouth_without_voice(ctx: StillContext, settings: MouthWithoutVoiceRule) -> Iterator[Issue]:
    """A character's lip sync shows a speech shape while no narration is heard."""
    if ctx.frame.get("narrating") is not False:
        return  # narration heard, or a still the dump cannot tell
    for obj in _figures(ctx):
        viseme = obj.get("viseme")
        if viseme is None or viseme == "rest":
            continue
        yield Issue(
            f"{describe(obj)} moves its mouth (lip sync shows '{viseme}') while no narration is heard; run vidgen tts "
            "again so the beat's viseme track matches its audio, or in a custom scene start lip sync with "
            "clock=self.beat_clock() and stop it when the beat ends",
            object_box(obj),
            (obj,),
        )
