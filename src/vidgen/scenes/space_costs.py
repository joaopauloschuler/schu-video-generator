"""What the pictures of a ``space`` scene cost (DESIGN.md §123.14): one table of seconds a frame at
1280x720 on 2 cores with software GL, measured in Steps 381–391 (docs/COOKBOOK-SPACE.md §4 prints the
same rows; a test reads both), and an estimate for a scene's combination of parts, which the lint rule
``space_scene`` reports when it is costly. A guide for budgeting, not a promise: the measurements are
single frames of the recipes, and a scene's own camera changes them."""

from typing import Any

from vidgen.api import *

#: name -> (seconds a frame at 1280x720, the row of the cookbook's table that states it).
COSTS: dict[str, tuple[float, str]] = {
    "air": (0.2, "| the air alone (the dome) | 0.2 |"),
    "sea": (1.2, "| a sea under the air (a skim) | 1.2 |"),
    "land": (1.4, "| ground under the air (a range from 2,500 m) | 1.4 |"),
    "clouds": (1.9, "| cloud decks under the air (fair, from below) | 1.9 |"),
    "clouds-layers": (2.7, "| between three decks (layers) | 2.7 |"),
    "land+sea": (2.05, "| ground and a sea (a coast) | 2.05 |"),
    "land+clouds": (2.5, "| ground under cumulus | 2.5 |"),
    "sea+clouds": (3.0, "| a sea under cumulus | 3.0 |"),
    "land+sea+clouds": (3.5, "| ground, a sea and clouds (not measured: the sum less the dome) | 3.5 |"),
    "handover": (3.4, "| a descent through the handover (400 km to 2.5 km over sea or decks) | 3.4 |"),
    "plane": (0.12, "| a plane on top (a third of the frame) | +0.12 |"),
    "reentry": (0.37, "| a re-entry's glow on top | +0.37 |"),
    "hull": (0.7, "| a bare hull in a SpaceView (filling the frame, with a sky, a world and a star) | 0.7 |"),
    "hull-dressed": (1.0, "| a dressed hull filling the frame from 2.5 km | 1.0 |"),
    "hull-pass": (1.55, "| hull-pass beside a dressed 3.2 km hull | 1.55 |"),
    "into-bay": (1.6, "| into-bay | 1.6 |"),
    "stern-burn": (2.1, "| stern-burn with eight bells | 2.1 |"),
    "hull-reveal": (1.1, "| hull-reveal (the hull overhead) | 1.1 |"),
    "scale-zoom": (0.8, "| scale-zoom | 0.8 |"),
}
#: Factors of a quality other than standard (the clouds' fine is far dearer; a rough rule).
QUALITY = {"fast": 0.75, "standard": 1.0, "fine": 2.0}


def cost(name: str) -> float:
    return COSTS[name][0]


def frame_seconds(p: Any) -> float:
    """The expected seconds a frame at 1280x720 of a ``space`` scene's params (the table's rows combined:
    the dearest stretch of the scene); 0 for an orbital scene of Phase AN's parts (the cookbook's other rows)."""
    if p.world is not None:
        w = p.world
        parts = [k for k, on in (("land", w.land_spec), ("sea", w.sea_spec), ("clouds", w.cloud_spec)) if on is not None]
        key = "+".join(parts) if parts else "air"
        if key == "clouds" and w.cloud_spec.sky == "layers":
            key = "clouds-layers"
        seconds = cost(key)
        if any(m.move in ("descend", "ascend", "rise") for m in p.camera) and (w.sea_spec is not None or w.cloud_spec is not None):
            seconds = max(seconds, cost("handover"))
        seconds *= QUALITY.get(w.quality, 1.0)
        for c in p.craft:
            seconds += cost("plane")
            if c.effects is not None and c.effects_spec().reentry:
                seconds += cost("reentry")
    else:
        hulls = [c for c in p.craft if c.maker == "hull"]
        if not hulls:
            return 0.0
        seconds = cost("hull-dressed" if any(c.dress is not False for c in hulls) else "hull")
        for m in p.camera:
            if m.move in COSTS:
                seconds = max(seconds, cost(m.move))
    blur = p.finish.motion_blur if p.finish is not False and "finish" in p.model_fields_set else False
    samples = 5 if blur is True else blur if isinstance(blur, int) and not isinstance(blur, bool) else (blur or {}).get("samples", 1) if isinstance(blur, dict) else 1
    return round(seconds * max(1, samples), 3)


__all__ = ["COSTS", "QUALITY", "cost", "frame_seconds"]
