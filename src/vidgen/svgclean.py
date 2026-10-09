"""Make an SVG safe and cheap to draw before Manim parses it (DESIGN.md §65). No manim import.

Generated vector pictures (``generate: {format: svg}``) and ``.svg`` files of the ``image``
scene go through :func:`sanitize_svg`, which returns a cleaned copy and what it changed:

- **Removed**: ``<script>``, ``<foreignObject>``, embedded rasters (``<image>``), ``<filter>``
  and ``filter=`` (blur, shadows), masks and clip paths (``mask=`` / ``clip-path=``: shapes they
  hid may show), ``<text>`` (generators letter poorly: put words on screen with vidgen),
  animation elements, event attributes (``onload=``...), links to other files. A document
  declaring XML entities is refused.
- **Flattened**: a gradient fill or stroke becomes the average colour of its stops (a pattern:
  the first colour drawn in it), so Manim (which cannot draw gradients) paints something close.
- **Manim's quirks** (shared with the icon loader, §22): ``currentColor`` becomes a marker
  colour the caller replaces, ``stroke="none"`` a zero stroke width (Manim would draw it white),
  and an invisible rectangle spanning the ``viewBox`` is inserted first (the picture's box).
- **Capped**: at most :data:`MAX_SHAPES` shapes (the smallest beyond it are dropped) and
  :data:`MAX_SEGMENTS` curve segments (paths are thinned to every k-th point), each with a
  warning, so a huge SVG cannot stall a render. ``simplify`` (a percentage of the picture's
  area) drops shapes smaller than that first.

:func:`theme_color` maps a colour to the nearest theme colour (``recolor: theme``).
"""

from __future__ import annotations

import colorsys
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.theme import Theme

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
#: Stands for ``currentColor`` while Manim parses an SVG (it would read it as black).
CURRENT_MARKER = "#010203"
#: Shapes drawn at most; beyond it the smallest are dropped (with a warning).
MAX_SHAPES = 1500
#: Curve segments drawn at most (all shapes); beyond it paths are thinned (with a warning).
MAX_SEGMENTS = 60_000
#: Largest SVG file loaded (bytes).
MAX_BYTES = 20_000_000
#: ``simplify: true``: shapes smaller than this percentage of the picture's area are dropped.
SIMPLIFY_DEFAULT = 0.05
#: Colour of a fill whose gradient / pattern cannot be resolved.
FALLBACK_COLOR = "#888888"

#: Elements removed with a warning (what they are, for the message).
_REMOVED = {
    "script": "scripts",
    "foreignObject": "embedded HTML (foreignObject)",
    "image": "embedded raster pictures",
    "filter": "filters (blur, shadows)",
    "mask": "masks",
    "clipPath": "clip paths",
    "text": "text",
}
#: Elements removed silently (no drawing of their own, or already flattened into colours).
_SILENT = {
    "metadata", "title", "desc", "animate", "animateMotion", "animateTransform", "animateColor", "set",
    "linearGradient", "radialGradient", "pattern", "cursor", "view", "audio", "video", "iframe", "canvas",
}
_SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
_PAINT_KEYS = ("fill", "stroke")
_URL = re.compile(r"url\(\s*['\"]?\s*([^)'\"]*?)\s*['\"]?\s*\)")
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def local(tag: Any) -> str:
    """An element's tag without its namespace (``path`` for ``{http://www.w3.org/2000/svg}path``)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _number(value: str | None, where: str) -> float:
    try:
        return float(str(value).strip().removesuffix("px"))
    except ValueError:
        raise VidgenError(f"{where}: cannot read the size {value!r} (give the <svg> a viewBox)") from None


def view_box(root: ET.Element, where: str) -> tuple[float, float, float, float]:
    """``(x, y, width, height)`` of the ``<svg>``'s ``viewBox``, else of its width and height."""
    box = root.get("viewBox")
    if box is not None:
        values = box.replace(",", " ").split()
        if len(values) == 4:
            x, y, w, h = (_number(v, where) for v in values)
            if w > 0 and h > 0:
                return x, y, w, h
        raise VidgenError(f"{where}: invalid viewBox {box!r}")
    w, h = _number(root.get("width"), where), _number(root.get("height"), where)
    if w <= 0 or h <= 0:
        raise VidgenError(f"{where}: the <svg> needs a viewBox or a positive width and height")
    return 0.0, 0.0, w, h


def fix_manim_quirks(root: ET.Element, current: str = CURRENT_MARKER) -> None:
    """``currentColor`` -> ``current``; ``stroke="none"`` -> also a zero stroke width (Manim
    would draw a white stroke); the same inside ``style=``."""
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if "currentColor" in value:
                element.set(key, value.replace("currentColor", current))
        if element.get("stroke") == "none":
            element.set("stroke-width", "0")
        style = _style(element)
        if style.get("stroke") == "none":
            style["stroke-width"] = "0"
            _set_style(element, style)


def insert_box(root: ET.Element, box: tuple[float, float, float, float]) -> None:
    """Insert, as the first child, a rectangle spanning ``box`` (Manim parses it as the first
    submobject; the loader makes it invisible and uses it as the picture's box)."""
    x, y, w, h = box
    root.insert(0, ET.Element(f"{{{SVG_NS}}}rect", {"x": repr(x), "y": repr(y), "width": repr(w), "height": repr(h)}))


def serialize(root: ET.Element) -> bytes:
    """The document as UTF-8 bytes with the SVG namespace as default."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(root, encoding="utf-8")


# ----- colours -----------------------------------------------------------------------------------


def parse_color(value: str | None) -> tuple[float, float, float] | None:
    """RGB in 0..1 of a CSS colour (``#abc``, ``#aabbcc``, ``rgb()``, names), ``None`` for
    ``none`` / ``transparent`` / unreadable values."""
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() in ("none", "transparent", "inherit"):
        return None
    import svgelements as se  # a dependency of Manim

    try:
        color = se.Color(text)
    except Exception:
        return None
    if color.value is None:
        return None
    return color.red / 255, color.green / 255, color.blue / 255


def to_hex(rgb: tuple[float, float, float]) -> str:
    """``#RRGGBB`` of RGB in 0..1."""
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02X}" for c in rgb)


def theme_color(color: str, theme: Theme) -> str:
    """The theme colour standing for ``color`` (``recolor: theme``).

    Greys and near-greys (saturation under 0.2) become the theme neutral (``background``,
    ``surface``, ``dim``, ``text``) of nearest lightness; other colours the theme colour
    (``primary``, ``secondary``, ``tertiary``, ``accent``, ``highlight`` and the palette) of
    nearest hue, keeping the original's lightness (its hue and saturation are the theme
    colour's), so light and dark shades stay apart.
    """
    rgb = parse_color(color)
    if rgb is None:
        return color
    h, lightness, s = colorsys.rgb_to_hls(*rgb)
    colors = theme.colors
    if s < 0.2 or lightness < 0.06 or lightness > 0.96:
        neutrals = [theme.background, colors.get("surface"), colors.get("dim"), colors.get("text")]
        options = [(c, parse_color(c)) for c in neutrals if c]
        best = min((o for o in options if o[1] is not None), key=lambda o: abs(colorsys.rgb_to_hls(*o[1])[1] - lightness))  # type: ignore[misc]
        return to_hex(best[1])  # type: ignore[arg-type]
    hues = [colors.get(n) for n in ("primary", "secondary", "tertiary", "accent", "highlight")] + list(theme.palette)
    choices = [rgb2 for rgb2 in (parse_color(c) for c in hues if c) if rgb2 is not None]
    hls = [colorsys.rgb_to_hls(*c) for c in choices]
    hls = [c for c in hls if c[2] >= 0.2] or hls

    def hue_distance(c: tuple[float, float, float]) -> float:
        d = abs(c[0] - h) % 1.0
        return min(d, 1.0 - d)

    th, _, ts = min(hls, key=hue_distance)
    return to_hex(colorsys.hls_to_rgb(th, lightness, ts))


# ----- styles ------------------------------------------------------------------------------------


def _style(element: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in (element.get("style") or "").split(";"):
        key, sep, value = item.partition(":")
        if sep and key.strip():
            out[key.strip()] = value.strip()
    return out


def _set_style(element: ET.Element, style: dict[str, str]) -> None:
    if style:
        element.set("style", ";".join(f"{k}:{v}" for k, v in style.items()))
    elif "style" in element.attrib:
        del element.attrib["style"]


def _href(element: ET.Element) -> str | None:
    return element.get(f"{{{XLINK_NS}}}href") or element.get("href")


# ----- the report --------------------------------------------------------------------------------


@dataclass(frozen=True)
class CleanSvg:
    """A sanitised SVG: ``data`` (UTF-8, its first child the invisible box), its ``view_box``,
    how many ``shapes`` and curve ``segments`` it draws, ``warnings`` (what was removed or cut,
    for the author) and ``notes`` (what ``simplify`` dropped)."""

    data: bytes
    view_box: tuple[float, float, float, float]
    shapes: int
    segments: int
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass
class _Shape:
    element: ET.Element
    parent: ET.Element
    area: float
    segments: int


def simplify_percent(value: bool | float | None) -> float:
    """The ``simplify`` param as a percentage of the picture's area (0: off)."""
    if value is True:
        return SIMPLIFY_DEFAULT
    if not value:
        return 0.0
    return float(value)


# ----- gradients and patterns --------------------------------------------------------------------


def _paint_servers(root: ET.Element) -> dict[str, str]:
    """``id -> colour`` of every gradient (average of its stops, following ``href`` to the
    gradient holding them) and pattern (the first colour drawn in it)."""
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
    out: dict[str, str] = {}

    def stops(gradient: ET.Element, depth: int = 0) -> list[tuple[float, float, float]]:
        found = []
        for stop in gradient:
            if local(stop.tag) != "stop":
                continue
            value = _style(stop).get("stop-color") or stop.get("stop-color") or "#000000"
            rgb = parse_color(value)
            if rgb is not None:
                found.append(rgb)
        href = _href(gradient)
        if not found and href and href.startswith("#") and depth < 8 and href[1:] in by_id:
            return stops(by_id[href[1:]], depth + 1)
        return found

    for ident, element in by_id.items():
        kind = local(element.tag)
        if kind in ("linearGradient", "radialGradient"):
            colours = stops(element)
            if colours:
                out[ident] = to_hex(tuple(sum(c[i] for c in colours) / len(colours) for i in range(3)))  # type: ignore[arg-type]
        elif kind == "pattern":
            for inner in element.iter():
                rgb = parse_color(_style(inner).get("fill") or inner.get("fill"))
                if rgb is not None and local(inner.tag) in _SHAPES:
                    out[ident] = to_hex(rgb)
                    break
    return out


def _flatten_paint(value: str, servers: dict[str, str]) -> tuple[str, bool]:
    """``value`` with ``url(#id)`` replaced by the server's colour; whether it had a url."""
    match = _URL.search(value)
    if match is None:
        return value, False
    target = match.group(1)
    colour = servers.get(target[1:]) if target.startswith("#") else None
    return colour or FALLBACK_COLOR, True


# ----- geometry ----------------------------------------------------------------------------------


def _floats(element: ET.Element, *names: str) -> list[float]:
    out = []
    for name in names:
        match = _NUMBER.match((element.get(name) or "0").strip())
        out.append(float(match.group(0)) if match else 0.0)
    return out


def _corners(element: ET.Element) -> tuple[list[tuple[float, float]], int] | None:
    """Points spanning a basic shape and its segment count (``None`` for a path)."""
    kind = local(element.tag)
    if kind == "rect":
        x, y, w, h = _floats(element, "x", "y", "width", "height")
        return [(x, y), (x + w, y), (x, y + h), (x + w, y + h)], 4
    if kind == "circle":
        cx, cy, r = _floats(element, "cx", "cy", "r")
        return [(cx - r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx + r, cy - r)], 4
    if kind == "ellipse":
        cx, cy, rx, ry = _floats(element, "cx", "cy", "rx", "ry")
        return [(cx - rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry), (cx + rx, cy - ry)], 4
    if kind == "line":
        x1, y1, x2, y2 = _floats(element, "x1", "y1", "x2", "y2")
        return [(x1, y1), (x2, y2)], 1
    if kind in ("polyline", "polygon"):
        numbers = [float(n) for n in _NUMBER.findall(element.get("points") or "")]
        points = list(zip(numbers[0::2], numbers[1::2]))
        return points, max(len(points) - 1, 0) + (kind == "polygon")
    return None


def _measure(element: ET.Element, matrix: Any) -> tuple[float, int]:
    """Area of the shape's box after ``matrix`` (svgelements ``Matrix``) and its segments."""
    import svgelements as se

    basic = _corners(element)
    if basic is None:
        try:
            path = se.Path(element.get("d") or "")
        except Exception:
            return 0.0, 0
        segments = sum(1 for s in path if not isinstance(s, se.Move))
        try:
            box = (path * matrix).bbox() if len(path) else None
        except Exception:
            box = None
        if box is None:
            return 0.0, segments
        return (box[2] - box[0]) * (box[3] - box[1]), segments
    points, segments = basic
    if not points:
        return 0.0, 0
    moved = [matrix.point_in_matrix_space(p) for p in points]
    xs, ys = [p[0] for p in moved], [p[1] for p in moved]
    return (max(xs) - min(xs)) * (max(ys) - min(ys)), segments


def _thin_path(d: str, k: int) -> str:
    """Path data keeping every ``k``-th point of each subpath (and its last), as straight lines."""
    import svgelements as se

    path = se.Path(d)
    out = se.Path()
    run: list[Any] = []

    def flush() -> None:
        for i, seg in enumerate(run):
            if (i + 1) % k == 0 or i == len(run) - 1:
                out.line(seg.end)
        run.clear()

    for seg in path:
        if isinstance(seg, se.Move):
            flush()
            out.move(seg.end)
        elif isinstance(seg, se.Close):
            flush()
            out.closed()
        else:
            run.append(seg)
    flush()
    return out.d()


def _thin_points(points: str, k: int) -> str:
    numbers = _NUMBER.findall(points)
    pairs = list(zip(numbers[0::2], numbers[1::2]))
    kept = [p for i, p in enumerate(pairs) if i % k == 0 or i == len(pairs) - 1]
    return " ".join(f"{x},{y}" for x, y in kept)


# ----- sanitising --------------------------------------------------------------------------------


def _walk(parent: ET.Element, matrix: Any) -> Iterator[tuple[ET.Element, ET.Element, Any]]:
    import svgelements as se

    for child in list(parent):
        own = matrix
        transform = child.get("transform")
        if transform:
            try:
                own = se.Matrix(transform) * matrix
            except Exception:
                own = matrix
        yield child, parent, own
        yield from _walk(child, own)


def sanitize_svg(
    data: bytes,
    *,
    where: str,
    simplify: bool | float | None = False,
    max_shapes: int = MAX_SHAPES,
    max_segments: int = MAX_SEGMENTS,
    current: str = CURRENT_MARKER,
) -> CleanSvg:
    """The cleaned SVG of ``data`` (see the module doc). ``where`` names it in messages;
    ``simplify`` (``True`` or a percentage of the picture's area) drops smaller shapes.
    Raises :class:`VidgenError` for a document that is not a usable SVG."""
    import svgelements as se

    if len(data) > MAX_BYTES:
        raise VidgenError(f"{where}: the SVG is {len(data) / 1e6:.0f} MB; vidgen loads SVGs up to {MAX_BYTES // 1_000_000} MB")
    if re.search(rb"<!ENTITY", data, re.IGNORECASE):
        raise VidgenError(f"{where}: the SVG declares XML entities, which vidgen does not load")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise VidgenError(f"{where}: not a readable SVG ({exc})") from None
    if local(root.tag) != "svg":
        raise VidgenError(f"{where}: not an SVG file (its root is <{local(root.tag)}>)")
    box = view_box(root, where)
    servers = _paint_servers(root)

    removed: dict[str, int] = {}
    flattened = 0
    links = 0
    for element, parent, _ in list(_walk(root, se.Matrix())):
        kind = local(element.tag)
        href = _href(element)
        if kind in _REMOVED or kind in _SILENT or (kind == "use" and href is not None and not href.startswith("#")):
            if kind in _REMOVED:
                removed[_REMOVED[kind]] = removed.get(_REMOVED[kind], 0) + 1
            elif kind == "use":
                links += 1
            if element in list(parent):
                parent.remove(element)
    for element in root.iter():
        for key in list(element.attrib):
            name = local(key)
            if name.lower().startswith("on"):
                del element.attrib[key]
            elif name in ("filter", "mask", "clip-path"):
                del element.attrib[key]
                what = {"filter": "filters (blur, shadows)", "mask": "masks", "clip-path": "clip paths"}[name]
                removed.setdefault(what, 0)
            elif name == "href" and local(element.tag) != "use" and not element.attrib[key].startswith("#"):
                del element.attrib[key]
                links += 1
        for key in _PAINT_KEYS:
            value = element.get(key)
            if value is not None:
                new, had = _flatten_paint(value, servers)
                if had:
                    element.set(key, new)
                    flattened += 1
        style = _style(element)
        if style:
            changed = False
            for prop in list(style):
                if prop in ("filter", "mask", "clip-path"):
                    del style[prop]
                    changed = True
                elif prop in _PAINT_KEYS:
                    new, had = _flatten_paint(style[prop], servers)
                    if had:
                        style[prop] = new
                        flattened += 1
                        changed = True
                elif "url(" in style[prop]:
                    del style[prop]
                    changed = True
            if changed:
                _set_style(element, style)
    fix_manim_quirks(root, current)

    shapes = [_Shape(e, p, *_measure(e, m)) for e, p, m in _walk(root, se.Matrix()) if local(e.tag) in _SHAPES]
    warnings: list[str] = []
    notes: list[str] = []
    for what in sorted(removed):
        if what == "text":
            warnings.append(f"{where}: its text was removed (generators letter poorly: put words on screen with a caption, title or callout)")
        elif what in ("masks", "clip paths"):
            warnings.append(f"{where}: {what} removed (shapes they hid may show)")
        else:
            warnings.append(f"{where}: {what} removed")
    if links:
        warnings.append(f"{where}: links to other files removed")
    if flattened:
        warnings.append(f"{where}: {flattened} gradient / pattern fill(s) flattened to one colour")

    def drop(victims: list[_Shape]) -> None:
        for shape in victims:
            if shape.element in list(shape.parent):
                shape.parent.remove(shape.element)
        gone = {id(s) for s in victims}
        shapes[:] = [s for s in shapes if id(s) not in gone]

    percent = simplify_percent(simplify)
    if percent > 0:
        limit = percent / 100 * box[2] * box[3]
        small = [s for s in shapes if s.area < limit]
        if small:
            drop(small)
            notes.append(f"{where}: simplify dropped {len(small)} shape(s) smaller than {percent:g}% of the picture")
    if len(shapes) > max_shapes:
        count = len(shapes)
        smallest = sorted(shapes, key=lambda s: s.area)[: count - max_shapes]
        drop(smallest)
        warnings.append(
            f"{where}: {count} shapes, more than the {max_shapes} vidgen draws: the {len(smallest)} smallest were dropped "
            "(set simplify: true, or a percentage of the picture's area, to drop small details yourself)"
        )
    total = sum(s.segments for s in shapes)
    if total > max_segments:
        k = math.ceil(total / max_segments)
        for shape in shapes:
            kind = local(shape.element.tag)
            if kind == "path" and shape.segments > 2:
                shape.element.set("d", _thin_path(shape.element.get("d") or "", k))
            elif kind in ("polyline", "polygon") and shape.segments > 2:
                shape.element.set("points", _thin_points(shape.element.get("points") or "", k))
            else:
                continue
            shape.segments = max(1, math.ceil(shape.segments / k))
        warnings.append(
            f"{where}: {total} curve segments, more than the {max_segments} vidgen draws: paths keep 1 point in {k} "
            "(set simplify: true to drop small details instead)"
        )
        total = sum(s.segments for s in shapes)
    if not shapes:
        raise VidgenError(f"{where}: the SVG draws nothing vidgen can show (after removing {', '.join(sorted(removed)) or 'nothing'})")
    insert_box(root, box)
    return CleanSvg(serialize(root), box, len(shapes), total, tuple(warnings), tuple(notes))


__all__ = [
    "CURRENT_MARKER",
    "MAX_SEGMENTS",
    "MAX_SHAPES",
    "SIMPLIFY_DEFAULT",
    "CleanSvg",
    "fix_manim_quirks",
    "insert_box",
    "parse_color",
    "sanitize_svg",
    "serialize",
    "simplify_percent",
    "theme_color",
    "to_hex",
    "view_box",
]
