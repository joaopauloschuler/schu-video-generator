"""The ``3d`` scene's lint rules (DESIGN.md §114.12): ``three_d_off_frame`` and ``three_d_hidden``,
from the framing the scene adds to each still of its layout dump (``three_d``: every object's
projected sphere, the share of it outside the frame and the share nearer objects cover, and
the objects the beat is about). Only the objects the beat is about are judged: one its object or
camera actions name, or a stand-in saying the line."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from vidgen.config import ThreeDHiddenRule, ThreeDOffFrameRule
from vidgen.lint.rules import Issue, StillContext, rule


def _about(ctx: StillContext) -> list[dict[str, Any]]:
    data = ctx.frame.get("three_d")
    if not data or ctx.zoomed:   # a zoom on the view cuts the picture on purpose
        return []
    spoken = set(data.get("spoken", []))
    return [o for o in data.get("objects", []) if o["id"] in spoken]


def _box(obj: dict[str, Any], ctx: StillContext) -> tuple[float, float, float, float]:
    if obj.get("box") is None:
        return (0.0, 0.0, float(ctx.width), float(ctx.height))
    x0, y0, x1, y1 = obj["box"]
    return (max(x0, 0.0), max(y0, 0.0), min(x1, float(ctx.width)), min(y1, float(ctx.height)))


@rule("three_d_off_frame", mid_beat=True)
def three_d_off_frame(ctx: StillContext, settings: ThreeDOffFrameRule) -> Iterator[Issue]:
    """In a 3d scene, an object the beat is about is mostly outside the frame (or behind the camera)."""
    for obj in _about(ctx):
        if obj["off"] >= settings.max_off:
            where = "behind the camera" if obj.get("box") is None else f"{obj['off']:.0%} outside the frame"
            yield Issue(f"3d object '{obj['id']}' is {where} while the beat is about it; move the camera (camera_fly_to: {obj['id']}) or the object",
                        _box(obj, ctx), value=obj["off"], limit=settings.max_off, group=("three_d_off_frame", obj["id"]))


@rule("three_d_hidden", mid_beat=True)
def three_d_hidden(ctx: StillContext, settings: ThreeDHiddenRule) -> Iterator[Issue]:
    """In a 3d scene, an object the beat is about is mostly hidden behind a nearer one."""
    for obj in _about(ctx):
        if obj["off"] < 1.0 and obj["hidden"] >= settings.max_hidden:
            yield Issue(f"3d object '{obj['id']}' is {obj['hidden']:.0%} hidden behind '{obj['by']}' while the beat is about it; "
                        "orbit the camera (camera_orbit) or move one of them",
                        _box(obj, ctx), value=obj["hidden"], limit=settings.max_hidden, group=("three_d_hidden", obj["id"]))
