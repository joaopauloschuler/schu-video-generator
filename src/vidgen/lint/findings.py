"""What ``vidgen lint`` reports: :class:`Finding` and its JSON form (docs/CONFIG.md "Lint")."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.lint.rules import Bbox


def object_json(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    """The identifying keys of a layout object: ``{id, kind, class, name, path, text, bbox}``
    (``text`` ``null`` for non-text kinds)."""
    if obj is None:
        return None
    return {
        "id": obj["id"],
        "kind": obj["kind"],
        "class": obj["class"],
        "name": obj.get("name"),
        "path": obj["path"],
        "text": obj.get("text"),
        "bbox": list(obj["bbox"]),
    }


@dataclass
class Finding:
    """One problem: where (scene, beat, times, still), which rule, how bad, about what.

    ``beats`` lists every beat end where the same rule found the same problem with the same
    object(s) (the finding is reported once, at the first: ``beat``/``time``/``still``).
    ``time`` is in the video (``None`` if not every scene has a render at the format),
    ``scene_time`` from the scene start. ``bbox`` is the region to look at in the still
    (``None`` for timing findings, whose ``still`` is the end of the beat concerned).
    ``similar`` holds further objects of the same group with the same problem (e.g. every tick
    label of an axis), reported with the first instead of one finding each; ``group`` is what
    makes findings alike (internal, not in the JSON).
    """

    scene: str
    beat: str | None
    time: float | None
    scene_time: float
    rule: str
    severity: str
    message: str
    bbox: Bbox | None
    still: Path | None
    objects: tuple[dict[str, Any], ...] = ()
    value: float | None = None
    limit: float | None = None
    beats: list[str | None] = field(default_factory=list)
    similar: list[dict[str, Any]] = field(default_factory=list)
    group: tuple[Any, ...] | None = None

    @property
    def key(self) -> tuple[str, str, str, tuple[str, ...]]:
        """Same scene, rule, severity and object ids: the same problem (merged across beats)."""
        return (self.scene, self.rule, self.severity, tuple(o["id"] for o in self.objects))

    def to_json(self) -> dict[str, Any]:
        """``{scene, beat, time, scene_time, rule, severity, object, other, similar, bbox, message,
        value, limit, beats, still}``."""
        return {
            "scene": self.scene,
            "beat": self.beat,
            "time": self.time,
            "scene_time": self.scene_time,
            "rule": self.rule,
            "severity": self.severity,
            "object": object_json(self.objects[0] if self.objects else None),
            "other": object_json(self.objects[1] if len(self.objects) > 1 else None),
            "similar": [object_json(o) for o in self.similar],
            "bbox": None if self.bbox is None else [round(v, 1) for v in self.bbox],
            "message": self.message,
            "value": self.value,
            "limit": self.limit,
            "beats": list(self.beats),
            "still": None if self.still is None else str(self.still.resolve()),
        }
