"""Cartoon rules: checks of the characters in one still's layout dump (DESIGN.md §69.12, §69.17).

They read the keys the layout dump gives a ``character`` object (``facing``, ``speaking``,
``face``, ``viseme``, ``looked_at``, ``passage``, ``walked_in``), the ``bubble`` key of a speech
bubble's objects, the ``effect`` objects (symbols over heads, §69.40) and the frame's
``narrating``. Like every still rule they see beat-end stills
only (mid-action stills are skipped by the runner). ``look_alike`` is a scene rule: it reads the
config's characters (``SceneContext.character_pairs``, §69.49), not a still.
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
    LookAlikeRule,
    MouthWithoutVoiceRule,
    OffscreenActionRule,
    OffStageRule,
    PropOverlapRule,
    SmallSpeakerRule,
    WalkOverlapRule,
)
from vidgen.lint.layout_rules import area, describe, intersection, is_text, object_box
from vidgen.lint.rules import Bbox, Issue, SceneContext, StillContext, rule

#: Points per side of the grid on which :func:`_covered_share` samples a face.
_FACE_SAMPLES = 12
#: Characters whose depths (the layout dump's ``depth``, 0 when absent) differ by this much or
#: more stand one behind the other, not on each other (DESIGN.md §69.44).
DEPTH_APART = 0.15


def _apart_in_depth(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return abs(float(a.get("depth", 0.0)) - float(b.get("depth", 0.0))) >= DEPTH_APART


def _riding_together(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Whether two characters ride the same vehicle (one behind the other in a car or a bus,
    DESIGN.md §69.52), or hold hands (side by side on purpose, §100.10)."""
    if a.get("hand_in_hand") == b.get("name") or b.get("hand_in_hand") == a.get("name"):
        return True
    return a.get("riding") is not None and a.get("riding") == b.get("riding")


def _figures(ctx: StillContext) -> list[dict[str, Any]]:
    """The characters of a still (not those a shot with ``clear`` hides, DESIGN.md §100.6)."""
    return [obj for obj in ctx.objects if obj["kind"] == "character" and not obj.get("hidden")]


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


def face_grid(box: Bbox) -> tuple[np.ndarray, np.ndarray]:
    """The points (x and y arrays, :data:`_FACE_SAMPLES` per side, row by row) on which a face's
    box is sampled."""
    xs = np.linspace(box[0], box[2], _FACE_SAMPLES)
    ys = np.linspace(box[1], box[3], _FACE_SAMPLES)
    return np.meshgrid(xs, ys)


def _covered_share(box: Bbox, covers: list[Bbox], masks: list[str] = ()) -> float:
    """Share of ``box`` inside any of ``covers`` (sampled on a grid), or under any of ``masks``
    (which grid points a picture's opaque pixels cover, the layout dump's ``covers``)."""
    gx, gy = face_grid(box)
    hit = np.zeros(gx.shape, dtype=bool)
    for c in covers:
        hit |= (gx >= c[0]) & (gx <= c[2]) & (gy >= c[1]) & (gy <= c[3])
    for mask in masks:
        if len(mask) == hit.size:
            hit |= (np.frombuffer(mask.encode("ascii"), dtype=np.uint8) == ord("1")).reshape(hit.shape)
    return float(hit.mean())


@rule("walk_overlap")
def walk_overlap(ctx: StillContext, settings: WalkOverlapRule) -> Iterator[Issue]:
    """A character's walk (``walk_to``, ``enter``) ends on another character at about its depth."""
    figures = _figures(ctx)
    beat = ctx.frame.get("beat")
    for k, walker in enumerate(figures):
        if beat is None or walker.get("walked_in") != beat:
            continue
        for j, other in enumerate(figures):
            if other is walker or (j < k and other.get("walked_in") == beat) or _apart_in_depth(walker, other) or _riding_together(walker, other):
                continue  # a pair that both walked is reported once; one behind the other is fine
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
    """Two characters stand on each other at rest (a walk that ends so is ``walk_overlap``'s); not
    two at depths :data:`DEPTH_APART` or more apart (one stands behind the other), nor two riding
    the same vehicle."""
    beat = ctx.frame.get("beat")
    resting = [obj for obj in _figures(ctx) if not obj.get("passage") and (beat is None or obj.get("walked_in") != beat)
               and _in_view(ctx, obj)]   # not two waiting off stage to enter (Step 246)
    for a, b in combinations(resting, 2):
        if _apart_in_depth(a, b) or _riding_together(a, b):
            continue
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


def _standing_props(ctx: StillContext) -> list[dict[str, Any]]:
    """The props standing on the floor: not held, not lifted or hung on a wall (``raised``), not
    lying flat (a rug: furniture stands on it)."""
    return [obj for obj in ctx.objects if obj["kind"] == "prop" and not obj.get("held_by") and not obj.get("raised") and not obj.get("flat")]


@rule("prop_overlap")
def prop_overlap(ctx: StillContext, settings: PropOverlapRule) -> Iterator[Issue]:
    """Two props standing on the floor at depths less than :data:`DEPTH_APART` apart are drawn
    over each other (a door and the sofa against the wall); not a prop in front of another (depths
    further apart), one lifted onto another or hung on the wall above it, or a rug under them."""
    for a, b in combinations(_standing_props(ctx), 2):
        if _apart_in_depth(a, b):
            continue
        share = _side_share(object_box(a), object_box(b))
        if share is None or share < settings.min_overlap:
            continue
        yield Issue(
            f"{describe(a)} and {describe(b)} stand on each other at the same depth ({share:.0%} of the narrower one's width); "
            "move one along the floor (another `at`, or a door's x in the room's `doors`), or put one in front of the other "
            f"(a `depth` at least {DEPTH_APART} nearer)",
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
    prop nearer the camera, a foreground layer; not an effect symbol or a motion effect, nor the
    vehicle it rides, whose windows show it, DESIGN.md §69.52): the viewer cannot see who talks."""
    for speaker in _figures(ctx):
        if not speaker.get("speaking") or not speaker.get("face"):
            continue
        iso = speaker.get("features") is not None   # on an iso place: its eyes and mouth (DESIGN.md §89.11)
        face = tuple(float(v) for v in speaker["features" if iso else "face"])
        fronts = [
            obj for obj in ctx.objects
            if obj["order"] > speaker["order"] and not is_text(obj) and obj["kind"] not in ("particles", "effect", "motion_effect")
            and obj.get("bubble") is None and obj.get("name_tag") is None and intersection(object_box(obj), face) is not None
            and not (obj["kind"] == "prop" and speaker.get("riding") is not None and obj.get("name") == speaker.get("riding"))
        ]
        if not fronts:
            continue
        name = speaker.get("name")
        masked = [o for o in fronts if iso and name in (o.get("covers") or {})]
        boxes = [object_box(o) for o in fronts if o not in masked and not (iso and o.get("scenery") and o["kind"] == "image")]
        share = _covered_share(face, boxes, [o["covers"][name] for o in masked])
        limit = settings.min_hidden_features if iso else settings.min_hidden
        if share < limit:
            continue
        front = max(fronts, key=lambda o: (o["covers"][name].count("1") if o in masked else 0, area(intersection(object_box(o), face) or (0, 0, 0, 0))))
        if iso:
            pieces = [str(n) for n in front.get("pieces") or []]
            what = describe(front) if front not in masked else ("the place's " + ", ".join(pieces[:3]) if pieces else "the place")
            message = (f"{describe(speaker)} speaks with {share:.0%} of its eyes and mouth hidden behind {what} (something of "
                       "the place in front of it); walk it to a spot where nothing stands in front of it, or give the beat a "
                       "shot that frames it from where it shows")
        else:
            message = (f"{describe(speaker)} speaks with {share:.0%} of its face hidden behind {describe(front)}; move it or what "
                       "is in front of it, or bring it nearer the camera (a smaller depth)")
        yield Issue(message, face, (speaker, front), value=round(share, 3), limit=limit)


@rule("small_speaker")
def small_speaker(ctx: StillContext, settings: SmallSpeakerRule) -> Iterator[Issue]:
    """A speaking character's face is too small on screen to read it and its lip sync (as seen,
    so a shot that frames it closer counts; DESIGN.md §86.10): a closer shot or larger characters
    (``character_size``) fix it."""
    limit = settings.min_face * ctx.short_side
    for speaker in _figures(ctx):
        if not speaker.get("speaking") or not speaker.get("face") or not _in_view(ctx, speaker):
            continue
        face = tuple(float(v) for v in speaker["face"])
        height = face[3] - face[1]
        if height >= limit:
            continue
        if speaker.get("name_tag") and int(ctx.frame.get("line_words", settings.max_tagged_words + 1)) <= settings.max_tagged_words:
            continue   # on an iso place its name tag shows who says this short line (DESIGN.md §89.11)
        name = speaker.get("name")
        yield Issue(
            f"{describe(speaker)} speaks with its face {height / ctx.short_side:.2%} of the frame's shorter side tall "
            f"(below {settings.min_face:.2%}): too small to read its face and lip sync; frame it closer for the beat "
            f"(shot: closeup {name}, or medium {name}) or make the characters larger (character_size: large)",
            face,
            (speaker,),
            value=round(height / ctx.short_side, 4),
            limit=settings.min_face,
        )


@rule("offscreen_action")
def offscreen_action(ctx: StillContext, settings: OffscreenActionRule) -> Iterator[Issue]:
    """On an iso place (DESIGN.md §89.11): an action of the still's beat that the camera never
    mostly did not show while it played (the layout dump's ``iso_actions``: what acted and the
    share of its frames with at least half of it in view): a walk, a small thing handed about, a
    change of the place."""
    for done in ctx.frame.get("iso_actions") or []:
        seen = float(done.get("seen", 1.0))
        if seen >= settings.min_seen:
            continue
        who, action = done.get("who"), done.get("action")
        shown = next((o for o in ctx.objects if o["kind"] in ("character", "prop") and o.get("name") == who), None)
        acted = shown or {"id": f"iso:{who}", "kind": "iso_object", "class": "IsoObject", "name": who, "path": str(who), "bbox": [0.0, 0.0, 0.0, 0.0]}
        yield Issue(
            f"the {action} of '{who}' happens off screen (in view on {seen:.0%} of its frames); "
            f"show it: a wider shot (shot: wide), pan or follow to it (- pan: {who}), or do it in a beat whose shot shows it",
            None,
            (acted,),
            value=round(seen, 3),
            limit=settings.min_seen,
            group=("offscreen_action", who, action),
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


@rule("look_alike", scope="scene")
def look_alike(ctx: SceneContext, settings: LookAlikeRule) -> Iterator[Issue]:
    """Two generated characters of the video look too alike to tell apart at a glance."""
    for pair in ctx.character_pairs:
        if pair.score >= settings.min_contrast:
            continue
        yield Issue(
            pair.message(settings.min_contrast),
            None,
            value=round(pair.score, 3),
            limit=settings.min_contrast,
            beat=ctx.beat_at(0.0),
        )
