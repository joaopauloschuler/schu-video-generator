"""What a ``web`` page shows, as layout objects (DESIGN.md §118.12). No browser here.

``data/web/layout.js`` reads the page after a frame's screenshot: every element that holds visible
text (its box, size as drawn, colour, what is behind it, opacity, what clips it) in page pixels,
and the text the page declares with ``window.vidgen.layout(t, ctx)`` (a canvas's text). This module
turns one reading into text objects of the layout dump (DESIGN.md §15), in frame pixels, so the
layout lint rules (``off_frame``, ``text_overlap``, ``min_font``, ``contrast``...) check them as
they check vidgen's own text, plus ``clipped`` / ``cut`` for ``web_clipped``.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

log = logging.getLogger("vidgen.web")

#: The ``class`` of a page's text in the layout dump.
WEB_TEXT_CLASS = "WebText"
#: What ``data-vidgen-lint`` (or a declared item's ``lint``) says to opt out of every rule.
ALL_RULES = "all"
_SIDES = ("left", "top", "right", "bottom")
_warned: set[str] = set()


def lint_opt_out(value: Any) -> list[str]:
    """The rules a ``data-vidgen-lint`` value opts out of: ``off`` -> ``["all"]``,
    ``off:text_overlap,contrast`` (or spaces) -> those names; anything else -> none."""
    text = str(value or "").strip()
    if text == "off":
        return [ALL_RULES]
    if not text.startswith("off:"):
        if text:
            _warn_once(f"data-vidgen-lint={text!r} is not 'off' or 'off:<rule>,<rule>'; the element is checked")
        return []
    names = [n for n in re.split(r"[\s,]+", text[4:]) if n]
    from vidgen.config import LINT_RULES

    unknown = [n for n in names if n not in LINT_RULES]
    if unknown:
        _warn_once(f"data-vidgen-lint names no lint rule {', '.join(unknown)} (see vidgen lint --help for the rules)")
    return [n for n in names if n in LINT_RULES] or ([] if unknown else [ALL_RULES])


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        log.warning("web page: %s", message)


def declared_problem(item: Any, index: int) -> str | None:
    """Why the ``index``-th item ``window.vidgen.layout(t, ctx)`` returned is not usable, or ``None``:
    it needs ``text`` and ``box: {x, y, width, height}`` (page px); ``id``, ``size`` (font size in
    px), ``font``, ``color``, ``background`` and ``lint`` are optional."""
    where = f"layout(t, ctx)[{index}]"
    if not isinstance(item, Mapping):
        return f"{where} is not an object"
    if not isinstance(item.get("text"), str) or not item["text"].strip():
        return f"{where} has no text"
    box = item.get("box")
    if not isinstance(box, Mapping) or any(not isinstance(box.get(k), (int, float)) or not math.isfinite(box[k]) for k in ("x", "y", "width", "height")):
        return f"{where} needs box: {{x, y, width, height}} in page pixels"
    if box["width"] <= 0 or box["height"] <= 0:
        return f"{where} has an empty box"
    if item.get("size") is not None and (not isinstance(item["size"], (int, float)) or item["size"] <= 0):
        return f"{where}: size must be the font size in pixels"
    return None


def _scaled(box: Sequence[float], origin: tuple[float, float], scale: tuple[float, float]) -> list[float]:
    (ox, oy), (sx, sy) = origin, scale
    return [round(ox + box[0] * sx, 1), round(oy + box[1] * sy, 1), round(ox + box[2] * sx, 1), round(oy + box[3] * sy, 1)]


def _object(name: str, text: str, bbox: list[float], cap_px: float, font_px: float, color: str | None, colors: list[str],
            opacity: float, backdrop: str | None, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"web:{name}", "kind": "text", "class": WEB_TEXT_CLASS, "path": f"web/{name}", "name": name, "bbox": bbox,
        "opacity": round(opacity, 3), "z": 0.0, "order": 0, "parts": 1, "text": text,
        "font_px": round(cap_px, 1), "cap_px": round(cap_px, 1), "font_size_px": round(font_px, 1), "rotation": 0.0,
        "color": color, "colors": colors, "backdrop": backdrop, "source": "web", **extra,
    }


def page_text_objects(reading: Mapping[str, Any], page_box: Sequence[float], frame: tuple[int, int],
                      opacity: float = 1.0) -> list[dict[str, Any]]:
    """The text objects of one reading of the page: boxes and sizes mapped from the page's pixels to
    the frame's (``page_box``: where the page is drawn, ``[x0, y0, x1, y1]`` frame px; ``frame``:
    the frame's width and height), opacities times the page's own (``opacity``: a dimmed view).
    A cut by the page's box is kept only on sides where the page does not reach the frame's edge
    (there it is ``off_frame``'s)."""
    width, height = float(reading.get("width") or 1), float(reading.get("height") or 1)
    x0, y0, x1, y1 = (float(v) for v in page_box)
    origin, scale = (x0, y0), ((x1 - x0) / width, (y1 - y0) / height)
    inner = {"left": x0 > 0.5, "top": y0 > 0.5, "right": x1 < frame[0] - 0.5, "bottom": y1 < frame[1] - 0.5}
    out: list[dict[str, Any]] = []
    for item in reading.get("texts", []):
        extra: dict[str, Any] = {"tag": item.get("tag"), "visible": _scaled(item["visible"], origin, scale)}
        if item.get("background_unknown"):
            extra["backdrop_unknown"] = item["background_unknown"]
        if item.get("clipped"):
            clipped = item["clipped"]
            extra["clipped"] = {"by": clipped["by"], "overflow": clipped.get("overflow"),
                                "sides": {s: round(px * (scale[0] if s in ("left", "right") else scale[1]), 1) for s, px in clipped["sides"].items()}}
        cut = {s: round(px * (scale[0] if s in ("left", "right") else scale[1]), 1) for s, px in (item.get("cut") or {}).items() if inner[s]}
        if cut:
            extra["cut"] = cut
        off = lint_opt_out(item.get("lint")) if item.get("lint") is not None else []
        if off:
            extra["lint_off"] = off
        out.append(_object(str(item["name"]), str(item["text"]), _scaled(item["box"], origin, scale), float(item["cap_px"]) * scale[1],
                           float(item["font_px"]) * scale[1], item.get("color"), list(item.get("colors") or []),
                           float(item.get("opacity", 1.0)) * opacity, item.get("background"), **extra))
    seen = {o["name"] for o in out}
    for index, item in enumerate(reading.get("declared", [])):
        problem = declared_problem(item, index)
        if problem is not None:
            _warn_once(problem)
            continue
        box = item["box"]
        page = [float(box["x"]), float(box["y"]), float(box["x"]) + float(box["width"]), float(box["y"]) + float(box["height"])]
        name = str(item.get("id") or " ".join(item["text"].split()[:3]))
        base, count = name, 1
        while name in seen:
            count += 1
            name = f"{base} ({count})"
        seen.add(name)
        size = float(item["size"]) if item.get("size") is not None else None
        cap = float(item.get("cap") or 0.0) if size is not None else (page[3] - page[1]) * 0.7
        color = item.get("color") if isinstance(item.get("color"), str) and str(item["color"]).startswith("#") else None
        background = item.get("background") if isinstance(item.get("background"), str) and str(item["background"]).startswith("#") else None
        alpha = float(item.get("color_alpha") or 1.0) if color is not None else 1.0
        extra = {"declared": True, "visible": _scaled([max(page[0], 0), max(page[1], 0), min(page[2], width), min(page[3], height)], origin, scale)}
        if background is None:
            extra["backdrop_unknown"] = "not declared"
        off = lint_opt_out(item.get("lint")) if item.get("lint") is not None else []
        if off:
            extra["lint_off"] = off
        cut = {s: round(px * (scale[0] if s in ("left", "right") else scale[1]), 1)
               for s, px in _beyond(page, (0.0, 0.0, width, height)).items() if inner[s]}
        if cut:
            extra["cut"] = cut
        out.append(_object(name, " ".join(item["text"].split()), _scaled(page, origin, scale), cap * scale[1],
                           (size or cap / 0.7) * scale[1], color, [color] if color else [], alpha * opacity, background, **extra))
    return out


def _beyond(box: Sequence[float], clip: Sequence[float]) -> dict[str, float]:
    past = {"left": clip[0] - box[0], "top": clip[1] - box[1], "right": box[2] - clip[2], "bottom": box[3] - clip[3]}
    return {s: px for s, px in past.items() if px > 0.5}


def page_summary(reading: Mapping[str, Any], page_box: Sequence[float], frame_index: int) -> dict[str, Any]:
    """The ``web`` entry of a still in the layout dump: where the page is (frame px), its size
    (page px), the frame it was read at, how many texts it shows, hides or declares, its canvases."""
    return {
        "box": [round(float(v), 1) for v in page_box], "size": [reading.get("width"), reading.get("height")],
        "frame": frame_index, "texts": len(reading.get("texts", [])), "declared": len(reading.get("declared", [])),
        "hidden": int(reading.get("hidden", 0)), "canvases": int(reading.get("canvases", 0)),
    }


def sides_text(sides: Mapping[str, float]) -> str:
    """``right`` / ``left and bottom``, in the order left, top, right, bottom."""
    return " and ".join(s for s in _SIDES if s in sides)


__all__ = ["ALL_RULES", "WEB_TEXT_CLASS", "declared_problem", "lint_opt_out", "page_summary", "page_text_objects", "sides_text"]
