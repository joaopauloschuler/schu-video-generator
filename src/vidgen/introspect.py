"""Layout introspection: what is on screen, where, how big and in which colour, per captured frame.

:class:`LayoutRecorder` is a capture listener (:mod:`vidgen.capture`): at every captured frame
it walks the scene's mobjects and records one *object* per visible text, shape, shape group or
image, measured in output-frame pixels with the scene's camera (a moving/zoomed camera frame is
taken into account). The worker writes the result to ``build/.../layout/<scene>.json`` next to
the stills; ``vidgen lint`` reads it. Format: DESIGN.md §15 and docs/CONFIG.md.

Grouping: a text mobject (``Text``, ``MarkupText``, ``Paragraph``, ``Tex``/``MathTex``,
``DecimalNumber``) is one object, not one per glyph; the paragraphs of a ``Code`` listing are
objects of kind ``code`` and its background a shape; an icon (``vidgen.icon_mobject.Icon``) is
one object of kind ``icon`` with its name in ``icon``. A group with no text or image anywhere
inside is one ``group`` object (an axis' ticks, a network's edges); any other group is walked
into. Parts at opacity 0 are not visible: they are left out of an object's box, and an object
without visible parts is not recorded.

``font_px`` (text only) is the 75th percentile of the heights, in output pixels, of the
object's visible glyphs: about the cap height (≈ 0.7 em) for mixed-case text, the x-height for
text in lowercase letters without ascenders.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.capture import CapturedFrame, still_name

if TYPE_CHECKING:
    from manim import Mobject

    from vidgen.scene import NarratedScene

#: Version of the layout file format (bumped when keys are removed, renamed or change meaning).
LAYOUT_VERSION = 1

#: Percentile of the glyph heights reported as ``font_px``.
FONT_PERCENTILE = 75

#: Bezier parameters sampled per curve for boxes (anchors alone miss curves' extremes).
_SAMPLES = np.linspace(0.0, 1.0, 5)
_BERNSTEIN = np.stack([(1 - _SAMPLES) ** 3, 3 * (1 - _SAMPLES) ** 2 * _SAMPLES, 3 * (1 - _SAMPLES) * _SAMPLES**2, _SAMPLES**3], axis=1)

#: Pixels sampled at most per text box to find its backdrop colour.
_BACKDROP_SAMPLES = 40_000
#: RGB distance under which a pixel counts as the text's own colour (not its backdrop).
_TEXT_COLOR_DISTANCE = 60.0

#: The alignment glyphs Manim's ``Code`` appends (invisible) to its first and last line.
_CODE_SUFFIX = re.compile(r" pA\d+$", re.MULTILINE)
_MARKUP_TAG = re.compile(r"<[^>]*>")


def _hex(rgb: Iterable[float]) -> str:
    """``#RRGGBB`` for RGB components in 0..1."""
    r, g, b = (int(round(min(max(float(c), 0.0), 1.0) * 255)) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _r(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


@dataclass
class _Part:
    """One drawn leaf (a glyph, a path, an image) measured in pixels."""

    mob: Mobject
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 (stroke included)
    shape_height: float  # height of the outline alone
    opacity: float
    fill: tuple[str, float] | None
    stroke: tuple[str, float, float] | None  # colour, opacity, width in px
    z: float
    order: int

    @property
    def area(self) -> float:
        return (self.box[2] - self.box[0]) * (self.box[3] - self.box[1])


@dataclass
class _Walk:
    """State of one frame's walk over the scene."""

    scene: NarratedScene
    pixels: np.ndarray
    names: dict[int, str]
    order: dict[int, int]
    px_per_unit: float
    objects: list[dict[str, Any]] = field(default_factory=list)
    seen: set[int] = field(default_factory=set)


class LayoutRecorder:
    """Capture listener that records the layout of every captured frame of one scene."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self._ids: dict[int, tuple[Mobject, str]] = {}

    def __call__(self, scene: NarratedScene, captured: CapturedFrame) -> None:
        from manim import config

        camera = scene.camera
        self.frames.append(
            {
                "beat": captured.beat_id,
                "k": captured.k,
                "n": captured.n,
                "frame": captured.frame,
                "time": round(captured.time, 6),
                "still": f"../frames/{captured.scene_id}/{still_name(captured)}",
                "camera": {
                    "center": [_r(c, 4) for c in np.asarray(camera.frame_center)[:2]],
                    "width": _r(camera.frame_width, 4),
                    "height": _r(camera.frame_height, 4),
                    "zoom": _r(config.frame_width / camera.frame_width, 4),
                },
                "objects": self.objects(scene, captured.pixels),
            }
        )

    def objects(self, scene: NarratedScene, pixels: np.ndarray) -> list[dict[str, Any]]:
        """The visible objects of ``scene`` as drawn in ``pixels`` (its current frame)."""
        from manim.utils.family import extract_mobject_family_members

        camera = scene.camera
        drawn = extract_mobject_family_members(scene.mobjects, use_z_index=camera.use_z_index, only_those_with_points=True)
        walk = _Walk(
            scene=scene,
            pixels=pixels,
            names=_scene_names(scene),
            order={id(m): i for i, m in enumerate(drawn)},
            px_per_unit=camera.pixel_width / camera.frame_width,
        )
        for index, mob in enumerate(scene.mobjects):
            self._walk(walk, mob, [], index, in_code=False)
        return walk.objects

    def document(self, scene: NarratedScene, per_beat: int) -> dict[str, Any]:
        """The scene's layout file content (frames in frame order)."""
        from manim import config

        from vidgen.regions import safe_area

        width, height = config.pixel_width, config.pixel_height
        sx, sy = width / config.frame_width, height / config.frame_height
        safe = safe_area(scene.margin_x, scene.margin_y)
        x0, x1 = (safe.x0 + config.frame_width / 2) * sx, (safe.x1 + config.frame_width / 2) * sx
        y0, y1 = (config.frame_height / 2 - safe.y1) * sy, (config.frame_height / 2 - safe.y0) * sy
        return {
            "version": LAYOUT_VERSION,
            "scene": scene.spec.id,
            "type": scene.spec.type,
            "width": width,
            "height": height,
            "fps": config.frame_rate,
            "per_beat": per_beat,
            "px_per_unit": _r(sx, 4),
            "background": _hex(np.asarray(config.background_color.to_rgb())),
            "safe_area": [_r(x0), _r(y0), _r(x1), _r(y1)],
            "frames": sorted(self.frames, key=lambda f: (f["frame"], f["k"])),
        }

    # ----- walking ----------------------------------------------------------------------------

    def _id(self, mob: Mobject) -> str:
        """A label stable for the life of the Python object (kept alive, so ids are not reused)."""
        entry = self._ids.get(id(mob))
        if entry is None or entry[0] is not mob:
            entry = (mob, f"m{len(self._ids) + 1}")
            self._ids[id(mob)] = entry
        return entry[1]

    def _walk(self, walk: _Walk, mob: Mobject, parents: list[str], index: int, *, in_code: bool) -> None:
        from manim import Code
        from manim.mobject.types.image_mobject import AbstractImageMobject

        from vidgen.icon_mobject import Icon

        if id(mob) in walk.seen:
            return
        walk.seen.add(id(mob))
        name = walk.names.get(id(mob))
        path = [*parents, name or f"{type(mob).__name__}[{index}]"]
        text_kind = _text_kind(mob, in_code)
        if text_kind is not None:
            self._emit_text(walk, mob, path, name, text_kind)
            return
        if isinstance(mob, AbstractImageMobject):
            self._emit_parts(walk, mob, path, name, "image", [mob])
            return
        if isinstance(mob, Icon):
            self._emit_parts(walk, mob, path, name, "icon", [m for m in mob.get_family() if _drawn(m)], icon=mob.icon_name)
            return
        own = [mob] if _drawn(mob) else []
        if own and not mob.submobjects:
            self._emit_parts(walk, mob, path, name, "shape", own)
            return
        family = mob.get_family()[1:]
        if family and not any(_text_kind(m, True) is not None or isinstance(m, AbstractImageMobject) for m in family):
            self._emit_parts(walk, mob, path, name, "group", [m for m in mob.get_family() if _drawn(m)])
            return
        if own:  # a group that draws something itself and contains text
            self._emit_parts(walk, mob, path, name, "shape", own)
        inside_code = in_code or isinstance(mob, Code)
        for i, sub in enumerate(mob.submobjects):
            self._walk(walk, sub, path, i, in_code=inside_code)

    def _base(self, mob: Mobject, path: list[str], name: str | None, kind: str, parts: list[_Part]) -> dict[str, Any]:
        x0 = min(p.box[0] for p in parts)
        y0 = min(p.box[1] for p in parts)
        x1 = max(p.box[2] for p in parts)
        y1 = max(p.box[3] for p in parts)
        return {
            "id": self._id(mob),
            "kind": kind,
            "class": type(mob).__name__,
            "path": "/".join(path),
            "name": name,
            "bbox": [_r(x0), _r(y0), _r(x1), _r(y1)],
            "opacity": _r(max(p.opacity for p in parts), 3),
            "z": _r(max(p.z for p in parts), 3),
            "order": max(p.order for p in parts),
            "parts": len(parts),
        }

    def _emit_text(self, walk: _Walk, mob: Mobject, path: list[str], name: str | None, kind: str) -> None:
        parts = [p for p in (_measure(walk, m) for m in mob.family_members_with_points()) if p is not None]
        if not parts:
            return
        item = self._base(mob, path, name, kind, parts)
        colors = Counter(p.fill[0] if p.fill is not None else p.stroke[0] for p in parts if p.fill or p.stroke)
        ranked = [c for c, _ in colors.most_common()]
        heights = [p.shape_height for p in parts if p.shape_height > 0]
        item.update(
            {
                "text": _text_of(mob, kind),
                "font_px": _r(np.percentile(heights, FONT_PERCENTILE)) if heights else 0.0,
                "color": ranked[0] if ranked else None,
                "colors": ranked,
                "backdrop": _backdrop(walk.pixels, item["bbox"], ranked),
            }
        )
        walk.objects.append(item)

    def _emit_parts(
        self,
        walk: _Walk,
        mob: Mobject,
        path: list[str],
        name: str | None,
        kind: str,
        leaves: list[Mobject],
        icon: str | None = None,
    ) -> None:
        parts = [p for p in (_measure(walk, m) for m in leaves) if p is not None]
        if not parts:
            return
        item = self._base(mob, path, name, kind, parts)
        if icon is not None:
            item["icon"] = icon
        filled = [p for p in parts if p.fill is not None]
        stroked = [p for p in parts if p.stroke is not None]
        fill = max(filled, key=lambda p: p.area).fill if filled else None
        stroke = max(stroked, key=lambda p: p.area).stroke if stroked else None
        item["fill"] = None if fill is None else {"color": fill[0], "opacity": _r(fill[1], 3)}
        item["stroke"] = (
            None if stroke is None else {"color": stroke[0], "opacity": _r(stroke[1], 3), "width_px": _r(stroke[2], 2)}
        )
        walk.objects.append(item)


# ----- measuring -------------------------------------------------------------------------------


def _drawn(mob: Mobject) -> bool:
    """True if the camera draws ``mob`` itself (not only its submobjects)."""
    from manim import PMobject, VMobject
    from manim.mobject.types.image_mobject import AbstractImageMobject

    return isinstance(mob, (VMobject, AbstractImageMobject, PMobject)) and len(mob.points) > 0


def _sample(points: np.ndarray) -> np.ndarray:
    """Points along a VMobject's cubic Bezier curves (anchors, handles of odd shapes as they are)."""
    if len(points) % 4:
        return points
    curves = points.reshape(-1, 4, 3)
    return np.einsum("sk,ckd->csd", _BERNSTEIN, curves).reshape(-1, 3)


def _alpha(rgbas: np.ndarray) -> float:
    return float(np.max(rgbas[:, 3])) if len(rgbas) else 0.0


def _measure(walk: _Walk, mob: Mobject) -> _Part | None:
    """``mob``'s own drawing in pixels, or ``None`` when it is not visible (opacity 0, no points)."""
    from manim import VMobject
    from manim.mobject.types.image_mobject import AbstractImageMobject

    if not _drawn(mob):
        return None
    camera = walk.scene.camera
    fill: tuple[str, float] | None = None
    stroke: tuple[str, float, float] | None = None
    grow = 0.0
    if isinstance(mob, AbstractImageMobject):
        opacity = float(np.max(mob.get_pixel_array()[:, :, 3])) / 255 if mob.get_pixel_array().size else 0.0
        points = np.asarray(mob.points)
    elif isinstance(mob, VMobject):
        fill_alpha = _alpha(mob.get_fill_rgbas())
        width = float(mob.get_stroke_width())
        stroke_alpha = _alpha(mob.get_stroke_rgbas()) if width > 0 else 0.0
        if fill_alpha > 0:
            fill = (_hex(mob.get_fill_rgbas()[0][:3]), fill_alpha)
        if stroke_alpha > 0:
            # Manim's Cairo stroke: width * 0.01 frame units (camera.cairo_line_width_multiple)
            px = width * camera.cairo_line_width_multiple * walk.px_per_unit
            stroke = (_hex(mob.get_stroke_rgbas()[0][:3]), stroke_alpha, px)
            grow = px / 2
        opacity = max(fill_alpha, stroke_alpha)
        points = _sample(np.asarray(mob.points))
    else:  # PMobject: points drawn as dots
        opacity = _alpha(mob.rgbas)
        points = np.asarray(mob.points)
    if opacity <= 0:
        return None
    xy = camera.points_to_subpixel_coords(mob, points)
    x0, y0 = xy.min(axis=0)
    x1, y1 = xy.max(axis=0)
    return _Part(
        mob=mob,
        box=(x0 - grow, y0 - grow, x1 + grow, y1 + grow),
        shape_height=float(y1 - y0),
        opacity=opacity,
        fill=fill,
        stroke=stroke,
        z=float(mob.z_index),
        order=walk.order.get(id(mob), -1),
    )


def _backdrop(pixels: np.ndarray, bbox: list[float], text_colors: list[str]) -> str | None:
    """Most common colour in the text's box in the frame, ignoring the text's own colours.

    ``None`` when the box is entirely outside the frame.
    """
    height, width = pixels.shape[:2]
    x0, y0 = max(int(np.floor(bbox[0])), 0), max(int(np.floor(bbox[1])), 0)
    x1, y1 = min(int(np.ceil(bbox[2])), width), min(int(np.ceil(bbox[3])), height)
    if x1 <= x0 or y1 <= y0:
        return None
    region = pixels[y0:y1, x0:x1, :3]
    step = max(1, int(np.ceil(np.sqrt(region.shape[0] * region.shape[1] / _BACKDROP_SAMPLES))))
    rgb = region[::step, ::step].reshape(-1, 3).astype(np.float64)
    ink = np.array([[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in text_colors], dtype=np.float64)
    if len(ink):
        far = np.min(np.linalg.norm(rgb[:, None, :] - ink[None, :, :], axis=2), axis=1) >= _TEXT_COLOR_DISTANCE
        if far.sum() >= max(1, 0.05 * len(rgb)):
            rgb = rgb[far]
    exact = rgb.astype(np.int64) @ np.array([1 << 16, 1 << 8, 1])
    bins = (rgb.astype(np.int64) >> 3) @ np.array([1 << 10, 1 << 5, 1])  # similar colours vote together
    values, counts = np.unique(bins, return_counts=True)
    colors, counts = np.unique(exact[bins == values[np.argmax(counts)]], return_counts=True)
    best = int(colors[np.argmax(counts)])  # the most common exact colour of the winning group
    return f"#{best:06X}"


# ----- classifying -------------------------------------------------------------------------------


def _text_kind(mob: Mobject, in_code: bool) -> str | None:
    """``text`` / ``code`` / ``math`` / ``number`` for text mobjects, else ``None``."""
    from manim import DecimalNumber, MarkupText, Paragraph, SingleStringMathTex, Text

    if isinstance(mob, (Text, MarkupText, Paragraph)):
        return "code" if in_code else "text"
    if isinstance(mob, DecimalNumber):
        return "number"
    if isinstance(mob, SingleStringMathTex):
        return "math"
    return None


def _text_of(mob: Mobject, kind: str) -> str:
    """The characters a text mobject shows (markup tags removed; LaTeX source for math)."""
    from manim import DecimalNumber, MarkupText, Paragraph

    if isinstance(mob, Paragraph):
        text = mob.lines_text.original_text
        return _CODE_SUFFIX.sub("", text) if kind == "code" else text
    if isinstance(mob, MarkupText):
        return html.unescape(_MARKUP_TAG.sub("", mob.original_text))
    if isinstance(mob, DecimalNumber):
        return str(mob._get_num_string(mob.number))
    if kind == "math":
        return str(mob.tex_string)
    return str(getattr(mob, "original_text", ""))


def _scene_names(scene: NarratedScene) -> dict[int, str]:
    """``id(mobject) -> name`` for mobjects the scene named: its attributes, or ``Mobject.name``."""
    from manim import Mobject

    names: dict[int, str] = {}
    for mob in _all_mobjects(scene.mobjects):
        if mob.name != type(mob).__name__:
            names[id(mob)] = str(mob.name)
    for attr, value in vars(scene).items():
        if isinstance(value, Mobject) and not attr.startswith("_"):
            names.setdefault(id(value), attr)
    return names


def _all_mobjects(mobjects: Iterable[Mobject]) -> Iterator[Mobject]:
    for mob in mobjects:
        yield from mob.get_family()
