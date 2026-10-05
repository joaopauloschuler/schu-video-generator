"""Icons as Manim objects: :func:`icon` and the :class:`Icon` group (DESIGN.md §22).

An icon is built from its SVG (:mod:`vidgen.icons` finds it) with Manim's ``SVGMobject`` and
then normalised:

- **Box**: the icon's height and width are those of the SVG's ``viewBox`` (Lucide's 24 x 24
  design grid, padding included), held by an invisible first part, so icons of one size line
  up and centre alike whatever they draw.
- **Colour**: every visible fill and stroke gets ``color`` (a theme token or ``#hex``).
  ``currentColor`` is how Lucide marks "the icon colour"; with ``color=None`` only those parts
  are recoloured (to the theme ``text`` colour) and colours written in a project SVG are kept.
- **Strokes**: SVG stroke widths are in viewBox units (Lucide: 2 of 24), so they are converted to
  Manim's stroke width for the icon's size; :meth:`Icon.scale` scales strokes too, so an icon
  looks the same at any size and resolution. Round caps/joins of the SVG are kept.
"""

from __future__ import annotations

import atexit
import hashlib
import shutil
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Any

from manim import ORIGIN, SVGMobject, VGroup, VMobject
from manim.constants import CapStyleType, LineJointType

from vidgen.errors import VidgenError
from vidgen.helpers import resolve_color
from vidgen.icons import IconInfo, find_icon
from vidgen.runtime import current_theme
from vidgen.theme import Theme

#: Icon box height in Manim units per point of a size token: 1.5 em of the bundled Inter
#: (cap height 0.0101 units per point / 0.727), the way UI kits pair 24 px icons with 16 px text.
ICON_UNITS_PER_POINT = 0.0208

#: Manim's Cairo camera draws ``stroke_width`` as ``stroke_width * 0.01`` frame units.
_STROKE_UNIT = 0.01

_SVG_NS = "http://www.w3.org/2000/svg"
#: Stands for ``currentColor`` while Manim parses the SVG (it would read it as black).
_CURRENT = "#010203"
_CAPS = {"round": CapStyleType.ROUND, "butt": CapStyleType.BUTT, "square": CapStyleType.SQUARE}
_JOINS = {"round": LineJointType.ROUND, "bevel": LineJointType.BEVEL, "miter": LineJointType.MITER}


class Icon(VGroup):
    """A named icon: an invisible box (``submobjects[0]``) followed by the drawn parts.

    ``icon_name`` and ``icon_origin`` (``builtin`` | ``project``) say which icon it is (the
    layout dump reports it as one object of kind ``icon``). Unlike other mobjects, scaling an
    Icon scales its stroke widths too (``scale_stroke=True`` by default), so ``place()``,
    ``scale()`` and ``.animate.scale()`` keep its proportions.
    """

    def __init__(self, *parts: VMobject, icon_name: str, icon_origin: str) -> None:
        super().__init__(*parts)
        self.icon_name = icon_name
        self.icon_origin = icon_origin

    def scale(self, scale_factor: float, scale_stroke: bool = True, **kwargs: Any) -> Icon:
        """Scale the icon; strokes scale with it unless ``scale_stroke=False``."""
        super().scale(scale_factor, scale_stroke=scale_stroke, **kwargs)
        return self

    @property
    def box(self) -> VMobject:
        """The invisible part spanning the icon's design box."""
        return self.submobjects[0]

    @property
    def parts(self) -> list[VMobject]:
        """The drawn parts."""
        return self.submobjects[1:]


@lru_cache(maxsize=1)
def _work_dir() -> Path:
    """A private folder for the prepared SVGs of this process (Manim writes a temporary file next
    to every SVG it parses, so files are never shared between processes)."""
    folder = Path(tempfile.mkdtemp(prefix="vidgen-icons-"))
    atexit.register(shutil.rmtree, folder, True)
    return folder


def _number(value: str | None, where: str) -> float:
    try:
        return float(str(value).strip().removesuffix("px"))
    except ValueError:
        raise VidgenError(f"{where}: cannot read the size {value!r} (give the <svg> a viewBox)") from None


def _view_box(root: ET.Element, where: str) -> tuple[float, float, float, float]:
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


@lru_cache(maxsize=256)
def _prepare(path: Path, mtime_ns: int) -> tuple[Path, float, str | None, str | None]:
    """Write a copy of the SVG that Manim can parse faithfully; returns ``(copy, viewBox height,
    stroke-linecap, stroke-linejoin)``. The copy starts with an invisible rectangle spanning the
    viewBox (the icon's box), ``currentColor`` is replaced by a marker colour and
    ``stroke="none"`` by a zero stroke width (Manim would draw it white)."""
    del mtime_ns
    where = str(path)
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        raise VidgenError(f"cannot read icon {where}: {exc}") from None
    root = tree.getroot()
    if root.tag not in ("svg", f"{{{_SVG_NS}}}svg"):
        raise VidgenError(f"{where}: not an SVG file")
    x, y, w, h = _view_box(root, where)
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if "currentColor" in value:
                element.set(key, value.replace("currentColor", _CURRENT))
        if element.get("stroke") == "none":
            element.set("stroke-width", "0")
    box = ET.Element(f"{{{_SVG_NS}}}rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(h)})
    root.insert(0, box)
    ET.register_namespace("", _SVG_NS)
    data = ET.tostring(root, encoding="utf-8")
    copy = _work_dir() / f"{hashlib.sha1(data).hexdigest()}.svg"
    if not copy.exists():
        copy.write_bytes(data)
    return copy, h, root.get("stroke-linecap"), root.get("stroke-linejoin")


def _is_current(color: Any) -> bool:
    return color.to_hex().upper() == _CURRENT


def _style(parts: list[VMobject], color: Any, current: Any, stroke_width: float | None, units_per_svg: float) -> None:
    """Recolour ``parts`` (all visible paint to ``color``; with ``None``, only ``currentColor``
    paint, to ``current``) and convert their SVG stroke widths to Manim's (see module doc)."""
    for part in parts:
        if part.get_fill_opacity() > 0:
            if color is not None:
                part.set_fill(color=color)
            elif _is_current(part.get_fill_color()):
                part.set_fill(color=current)
        width = float(part.get_stroke_width())
        if width <= 0 or part.get_stroke_opacity() <= 0:
            part.set_stroke(width=0)
            continue
        stroke: dict[str, Any] = {"width": (width if stroke_width is None else stroke_width) * units_per_svg / _STROKE_UNIT}
        if color is not None:
            stroke["color"] = color
        elif _is_current(part.get_stroke_color()):
            stroke["color"] = current
        part.set_stroke(**stroke)


def build_icon(
    info: IconInfo, height: float, color: Any, stroke_width: float | None = None, *, current: Any = "#FFFFFF"
) -> Icon:
    """The :class:`Icon` for ``info``, its box ``height`` units high, centred on the origin.

    ``color`` is a Manim colour (or hex) for every visible part, or ``None`` to recolour only the
    SVG's ``currentColor`` parts to ``current``. ``stroke_width`` (viewBox units, Lucide's
    default 2) replaces the SVG's stroke widths.
    """
    if height <= 0:
        raise VidgenError(f"icon '{info.name}': size must be positive")
    if stroke_width is not None and stroke_width < 0:
        raise VidgenError(f"icon '{info.name}': stroke_width must not be negative")
    copy, view_height, cap, join = _prepare(info.path, info.path.stat().st_mtime_ns)
    svg = SVGMobject(str(copy), height=None, should_center=False)
    box, *parts = svg.submobjects
    box.set_fill(opacity=0).set_stroke(width=0, opacity=0)
    if not parts:
        raise VidgenError(f"{info.path}: the SVG draws nothing")
    factor = height / view_height
    _style(parts, color, current, stroke_width, factor)
    for part in parts:
        if cap in _CAPS:
            part.cap_style = _CAPS[cap]
        if join in _JOINS:
            part.joint_type = _JOINS[join]
    result = Icon(box, *parts, icon_name=info.name, icon_origin=info.origin)
    VGroup.scale(result, factor)  # strokes were already set for the final size
    return result.move_to(ORIGIN)


def icon_height(size: str | float, theme: Theme) -> float:
    """Box height in Manim units of a size token or a number of points."""
    return theme.size(size) * ICON_UNITS_PER_POINT


def icon(
    name: str,
    size: str | float = "body",
    color: Any = "text",
    stroke_width: float | None = None,
    *,
    height: float | None = None,
    theme: Theme | None = None,
) -> Icon:
    """An icon of the active project (its ``assets/icons``) or of the built-in set.

    ``size`` is a theme size token or a number of points, like text: the icon suits text of that
    size (its box is 1.5 em high, ``ICON_UNITS_PER_POINT``); ``height`` gives the box height in
    Manim units instead. ``color`` is a theme token, ``#hex`` or Manim colour; ``None`` keeps a
    multi-coloured project SVG's own colours (``currentColor`` becomes ``text``).
    ``stroke_width`` is in the icon's own units (Lucide: 2 of 24; 1.5 is lighter, 2.5 bolder).
    Unknown names raise :class:`VidgenError` with suggestions. Centred on the origin.
    """
    theme = theme or current_theme()
    info = find_icon(name)
    box = height if height is not None else icon_height(size, theme)
    current = resolve_color("text", theme)
    return build_icon(info, box, None if color is None else resolve_color(color, theme), stroke_width, current=current)
