"""The ``iso_labels`` rule (DESIGN.md §90.10): the labels of an ``iso_diagram`` checked against
what they name, from the geometry the scene adds to each still of its layout dump (the
``iso_diagram`` key: labels with their boxes, block and plate outlines, connector paths, in
output pixels). Text size and contrast are ``min_font``'s and ``contrast``'s, as for any text."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import combinations
from typing import Any

import numpy as np

from vidgen.config import IsoLabelsRule
from vidgen.iso_labels import clip_area, convex_hull, hull_gap, overlap_area, polyline_gap
from vidgen.lint.rules import Issue, StillContext, rule

#: A label's plate hides a connector when this many of its path's points lie under it.
LINE_POINTS = 2


def _what(label: dict[str, Any]) -> str:
    kind = {"block": "block", "layer": "layer", "stack": "stack", "group": "group", "edge": "connector"}[label["kind"]]
    return f"label '{label['text']}' (of {kind} '{label['owner']}')"


def _area(box: tuple[float, float, float, float]) -> float:
    return max(box[2] - box[0], 0.0) * max(box[3] - box[1], 0.0)


def _text_objects(ctx: StillContext, label: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """The layout's text object of ``label`` (same text, inside its box), for ``lint_ignore``."""
    x0, y0, x1, y1 = label["box"]
    for obj in ctx.objects:
        if obj["kind"] == "text" and obj.get("text") == label["text"]:
            a, b, c, d = obj["bbox"]
            if x0 - 1 <= (a + c) / 2 <= x1 + 1 and y0 - 1 <= (b + d) / 2 <= y1 + 1:
                return (obj,)
    return ()


def _own_blocks(label: dict[str, Any], stacks: dict[str, list[str]], edges: dict[str, dict[str, Any]]) -> set[str]:
    """The blocks a label names (it may lie on them): its block or layer, a stack's layers."""
    if label["kind"] in ("block", "layer"):
        return {label["owner"]}
    if label["kind"] == "stack":
        return set(stacks.get(label["owner"], []))
    return set()


def _owner_gap(label: dict[str, Any], box: tuple[float, float, float, float], outlines: dict[str, np.ndarray],
               plates: dict[str, np.ndarray], stacks: dict[str, list[str]], edges: dict[str, dict[str, Any]]) -> float | None:
    """How far (px) ``label`` is from what it names, or ``None`` when that is not on screen."""
    kind, owner = label["kind"], label["owner"]
    if kind in ("block", "layer"):
        hull = outlines.get(owner)
    elif kind == "stack":
        shown = [outlines[n] for n in stacks.get(owner, []) if n in outlines]
        hull = convex_hull(np.vstack(shown)) if shown else None
    elif kind == "group":
        hull = plates.get(owner)
    else:
        edge = edges.get(owner)
        return polyline_gap(box, np.asarray(edge["points"], dtype=float)) if edge else None
    return hull_gap(box, hull) if hull is not None else None


@rule("iso_labels")
def iso_labels(ctx: StillContext, settings: IsoLabelsRule) -> Iterator[Issue]:
    """An ``iso_diagram`` label covers a block it does not name, overlaps another label, hides
    a connector, or stands far from what it names without a leader line."""
    data = ctx.frame.get("iso_diagram")
    if not data:
        return
    labels = data.get("labels", [])
    outlines = {b["id"]: np.asarray(b["outline"], dtype=float) for b in data.get("blocks", []) if len(b["outline"]) >= 3}
    plates = {p["id"]: np.asarray(p["outline"], dtype=float) for p in data.get("plates", []) if len(p["outline"]) >= 3}
    stacks = {s["id"]: list(s["layers"]) for s in data.get("stacks", [])}
    edges = {e["ref"]: e for e in data.get("edges", [])}
    zoom = max(float(data.get("zoom", 1.0)), 1.0)
    for label in labels:
        box = tuple(float(v) for v in label["box"])
        size = max(_area(box), 1e-9)
        objects = _text_objects(ctx, label)
        own = _own_blocks(label, stacks, edges)
        for name, hull in outlines.items():
            if name in own:
                continue
            share = clip_area(box, hull) / size
            if share >= settings.min_cover:
                yield Issue(f"{_what(label)} covers block '{name}' ({share:.0%} of the label); it reads as that block's label",
                            box, objects, value=round(share, 3), limit=settings.min_cover)
        if not label.get("on_top"):
            for ref, edge in edges.items():
                if label["kind"] == "edge" and ref == label["owner"]:
                    continue
                points = np.asarray(edge["points"], dtype=float)
                inside = int(np.count_nonzero((points[:, 0] >= box[0]) & (points[:, 0] <= box[2]) & (points[:, 1] >= box[1]) & (points[:, 1] <= box[3])))
                if inside >= LINE_POINTS:
                    yield Issue(f"{_what(label)} hides part of connector {ref}", box, objects, value=inside, limit=LINE_POINTS)
        if not label.get("leader") and not label.get("on_top"):
            gap = _owner_gap(label, box, outlines, plates, stacks, edges)
            # judged at the diagram's own scale: a focus magnifies the gap with everything else
            limit = settings.max_gap * ctx.short_side * zoom
            if gap is not None and gap > limit:
                yield Issue(f"{_what(label)} is {gap:.0f} px from what it names (at most {limit:.0f} px without a leader line)",
                            box, objects, value=round(gap / zoom / ctx.short_side, 4), limit=settings.max_gap)
    for a, b in combinations(labels, 2):
        box_a, box_b = (tuple(float(v) for v in x["box"]) for x in (a, b))
        shared = overlap_area(box_a, box_b)
        smaller = max(min(_area(box_a), _area(box_b)), 1e-9)
        if shared / smaller >= settings.min_overlap:
            box = (max(box_a[0], box_b[0]), max(box_a[1], box_b[1]), min(box_a[2], box_b[2]), min(box_a[3], box_b[3]))
            yield Issue(f"{_what(a)} and {_what(b)} overlap ({shared / smaller:.0%} of the smaller)", box,
                        _text_objects(ctx, a) + _text_objects(ctx, b), value=round(shared / smaller, 3), limit=settings.min_overlap)
