"""Characters drawn from an SVG file, ``look: {svg: FILE}`` (DESIGN.md §69.2).

The SVG is sanitised with :func:`vidgen.svgclean.sanitize_svg`, then split into character parts
by element ids:

- ``id="<part>"`` (a :data:`~vidgen.cartoon.character.PART_NAMES` name: ``head``, ``mouth``,
  ``arm_left``, ...) is that part's rest shape; ``id="<part>_<shape>"`` (``mouth_A``,
  ``eyes_closed``, ``arm_left_up``) is another shape of the part, usually hidden in the file
  (``display="none"``). The rest shape of ``eyes`` is called ``open`` and that of ``mouth``
  ``smile``, as on generated characters; other rest shapes are called ``rest``.
- An element with a part id takes everything inside it, except elements with another part's id
  (so ``eyes`` may sit inside ``head``); ``<part>_...`` ids inside the part's own element are
  just pieces of it. Shapes outside every named part belong to ``body``; shapes hidden in the
  file outside the named parts are not drawn.
- ``data-pivot="x y"`` on a part's element sets its pivot, in the SVG's ``viewBox`` coordinates;
  without it the pivot is guessed from the part's box (:func:`default_pivot`).
- Parts are drawn in the file's order; the figure is drawn facing right.
- Arms and legs may come in two segments (DESIGN.md §69.26): ``arm_left`` is then the upper arm
  and ``arm_left_lower`` the forearm and hand (pivot: the elbow); legs either as one ``legs`` or
  as ``leg_left`` / ``leg_right``, each with an optional ``leg_left_lower`` (pivot: the knee).
  A limb in one piece keeps working: its bend is shown folded.
- ``id="tail"`` (optional, DESIGN.md §69.48) hangs from ``body`` and is drawn where the file
  puts it; it swings on a spring as the figure sets off and stops, swishes while idle and turns
  as a whole about its pivot (``data-pivot``: where it leaves the body) and trails in the wind
  (§69.32) like a generated character's tail.

Splitting (:func:`split_character_svg`) needs no manim, so ``vidgen validate`` can report
problems and the actions a character cannot do (:mod:`vidgen.cartoon.cast`).
:func:`svg_character_parts` builds the :class:`~vidgen.cartoon.character.CharacterPart` list
(imports manim when called).
"""

from __future__ import annotations

import copy
import difflib
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vidgen.errors import VidgenError
from vidgen.svgclean import CleanSvg, local, sanitize_svg, serialize

if TYPE_CHECKING:
    from vidgen.cartoon.character import CharacterPart

#: Every part name (:data:`vidgen.cartoon.character.PART_NAMES`, kept here without manim) but the
#: generator's ``cheeks`` and ``bristles`` (DESIGN.md §69.59), whose rest shape draws nothing.
SVG_PART_NAMES: tuple[str, ...] = (
    "body", "legs", "leg_left", "leg_left_lower", "leg_right", "leg_right_lower",
    "arm_left", "arm_left_lower", "arm_right", "arm_right_lower", "head", "eyes", "brows", "mouth", "accessory", "tail",
    "antenna", "cape",
)
#: Legs drawn one each (``legs`` is both in one piece; a file has one kind).
SVG_SINGLE_LEGS: tuple[str, ...] = ("leg_left", "leg_left_lower", "leg_right", "leg_right_lower")
#: Parts whose default pivot is the top of their box (the hips, an elbow, a knee).
_HANGING_PARTS = ("legs", *SVG_SINGLE_LEGS, "arm_left_lower", "arm_right_lower")
#: The only part an imported character must have (shapes outside the named parts make it).
SVG_REQUIRED_PARTS: tuple[str, ...] = ("body",)
#: Names of the rest shapes (the element with the plain part id); other parts: ``rest``.
REST_SHAPE_NAMES: dict[str, str] = {"eyes": "open", "mouth": "smile"}
#: Parts whose pivot a figure should set with ``data-pivot`` (they turn; a guess may look wrong).
TURNING_PARTS: tuple[str, ...] = ("head", "arm_left", "arm_right", "legs", *SVG_SINGLE_LEGS, "arm_left_lower", "arm_right_lower", "tail")
#: Elements kept in every part's document (definitions, not drawn where they stand).
_DEFINITIONS = {"defs", "symbol"}
_OWNER = "data-vidgen-owner"
#: Owner of shapes hidden in the file outside any part's element (drawn in no part).
_HIDDEN = "-/-"
_DRAWN = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "use"}


@dataclass(frozen=True)
class SvgShape:
    """One shape of one part: ``data``, an SVG document drawing only it (same ``viewBox`` and
    invisible box as the file), and ``element_id`` (``""`` for loose shapes in ``body``)."""

    part: str
    shape: str
    data: bytes
    element_id: str


@dataclass(frozen=True)
class SvgCharacter:
    """An SVG split into parts: ``shapes`` in draw order (by part, then rest shape first),
    ``pivots`` (part -> ``viewBox`` point) set by ``data-pivot``, the sanitiser's ``report`` and
    ``warnings`` about the parts (ignored ids, empty parts)."""

    shapes: tuple[SvgShape, ...]
    pivots: dict[str, tuple[float, float]]
    report: CleanSvg
    warnings: tuple[str, ...] = ()

    def part_shapes(self) -> dict[str, list[str]]:
        """Part name -> its shape names (rest first), in draw order."""
        out: dict[str, list[str]] = {}
        for shape in self.shapes:
            out.setdefault(shape.part, []).append(shape.shape)
        return out


def part_key(element_id: str) -> tuple[str, str] | None:
    """``(part, shape)`` named by an element id (``mouth`` -> ``("mouth", "smile")``,
    ``mouth_A`` -> ``("mouth", "A")``), ``None`` for an id that names no part."""
    for part in sorted(SVG_PART_NAMES, key=len, reverse=True):
        if element_id == part:
            return part, REST_SHAPE_NAMES.get(part, "rest")
        if element_id.startswith(part + "_") and len(element_id) > len(part) + 1:
            return part, element_id[len(part) + 1:]
    return None


def _near_miss(element_id: str) -> str | None:
    """The part name an id probably meant (``Mouth``, ``arm-left``, ``eye``), else ``None``."""
    simple = element_id.lower().replace("-", "_")
    if part_key(simple) is not None and simple != element_id:
        return part_key(simple)[0]  # type: ignore[index]
    close = difflib.get_close_matches(simple, SVG_PART_NAMES, n=1, cutoff=0.8)
    return close[0] if close else None


def _pivot(value: str, where: str, element_id: str) -> tuple[float, float]:
    numbers = value.replace(",", " ").split()
    try:
        x, y = (float(n) for n in numbers)
    except ValueError:
        raise VidgenError(f"{where}: data-pivot of '{element_id}' must be two numbers \"x y\", not {value!r}") from None
    return x, y


def _hidden(element: ET.Element) -> bool:
    style = {k.strip(): v.strip() for k, _, v in (item.partition(":") for item in (element.get("style") or "").split(";"))}
    return element.get("display") == "none" or style.get("display") == "none" or element.get("visibility") == "hidden" or style.get("visibility") == "hidden"


def _show(element: ET.Element) -> None:
    """Drop ``display: none`` / ``visibility: hidden`` from ``element`` (other shapes are hidden in the file)."""
    for key in ("display", "visibility"):
        element.attrib.pop(key, None)
    style = element.get("style")
    if style is not None:
        kept = [item for item in style.split(";") if item.partition(":")[0].strip() not in ("display", "visibility")]
        if any(item.strip() for item in kept):
            element.set("style", ";".join(kept))
        else:
            del element.attrib["style"]


def _mark_owners(
    element: ET.Element,
    owner: str,
    hidden: bool,
    found: dict[str, tuple[str, str, ET.Element]],
    order: list[str],
    warnings: list[str],
    where: str,
) -> None:
    """Mark every drawn element under ``element`` with the ``part/shape`` it belongs to
    (``owner``; ``""`` outside the named parts: ``body/rest``), or :data:`_HIDDEN`; ``found``
    collects each part element (id, key, element) by ``part/shape``."""
    for child in element:
        kind = local(child.tag)
        if kind in _DEFINITIONS:
            continue
        own, is_hidden = owner, hidden or _hidden(child)
        element_id = child.get("id") or ""
        key = part_key(element_id) if element_id else None
        if key is not None and key[0] != owner.split("/")[0]:
            name = f"{key[0]}/{key[1]}"
            if name in found:
                raise VidgenError(f"{where}: two elements are the {key[1]} shape of {key[0]} ('{found[name][0]}' and '{element_id}')")
            if key[1] != REST_SHAPE_NAMES.get(key[0], "rest") and not is_hidden:
                warnings.append(
                    f"{where}: '{element_id}' is another shape of {key[0]}, shown only when swapped in, but the file shows it "
                    "(hide it with display=\"none\", or rename it if it is a piece of the part)"
                )
            found[name] = (element_id, key, child)
            own, is_hidden = name, False
        if kind in _DRAWN:
            mark = _HIDDEN if is_hidden else own or "body/rest"
            child.set(_OWNER, mark)
            if mark != _HIDDEN and mark not in order:
                order.append(mark)
        if kind != "use":
            _mark_owners(child, own, is_hidden, found, order, warnings, where)


def _parents(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _shape_document(root: ET.Element, owner: str, element_id: str) -> bytes:
    """The document drawing only ``owner``'s shapes, its element ``element_id``
    and the groups around it shown even if the file hides them."""
    doc = copy.deepcopy(root)
    parents = _parents(doc)
    for element in list(doc.iter()):
        mark = element.get(_OWNER)
        if mark is None:
            continue
        if mark == owner:
            del element.attrib[_OWNER]
        else:
            parents[element].remove(element)
    if element_id:
        node: ET.Element | None = next(e for e in doc.iter() if e.get("id") == element_id)
        while node is not None:
            _show(node)
            node = parents.get(node)
    return serialize(doc)


def split_character_svg(data: bytes, *, where: str) -> SvgCharacter:
    """Sanitise ``data`` and split it into parts by element ids (see the module doc). Raises
    :class:`VidgenError` for an unusable SVG, a repeated part id or a bad ``data-pivot``."""
    report = sanitize_svg(data, where=where, current="#000000")
    root = ET.fromstring(report.data)
    box = root[0]  # sanitize_svg's invisible viewBox rectangle: in every part's document
    root.remove(box)
    found: dict[str, tuple[str, tuple[str, str], ET.Element]] = {}
    order: list[str] = []
    warnings: list[str] = []
    _mark_owners(root, "", False, found, order, warnings, where)
    root.insert(0, box)
    for element in root.iter():
        element_id = element.get("id")
        if element_id and part_key(element_id) is None:
            meant = _near_miss(element_id)
            if meant is not None:
                warnings.append(f"{where}: id '{element_id}' is not a part name (did you mean '{meant}'?); it is drawn with the part around it")
    pivots: dict[str, tuple[float, float]] = {}
    for name, (element_id, key, element) in found.items():
        value = element.get("data-pivot")
        if value is not None and (key[1] == REST_SHAPE_NAMES.get(key[0], "rest") or key[0] not in pivots):
            pivots[key[0]] = _pivot(value, where, element_id)
    for name, (element_id, _, _) in found.items():
        if name not in order:
            warnings.append(f"{where}: '{element_id}' draws nothing; it is ignored")
    parts_in_order = list(dict.fromkeys(name.split("/")[0] for name in order))
    shapes = []
    for part in parts_in_order:
        names = [n for n in order if n.split("/")[0] == part]
        rest = f"{part}/{REST_SHAPE_NAMES.get(part, 'rest')}"
        if rest in names:
            names.remove(rest)
            names.insert(0, rest)
        for name in names:
            element_id = found[name][0] if name in found else ""
            shapes.append(SvgShape(part, name.split("/", 1)[1], _shape_document(root, name, element_id), element_id))
    if not any(s.part == "body" for s in shapes):
        raise VidgenError(f"{where}: no body: give the body's element id=\"body\" (shapes outside the named parts also make the body)")
    single = [part for part in SVG_SINGLE_LEGS if part in parts_in_order]
    if "legs" in parts_in_order and single:
        raise VidgenError(
            f"{where}: 'legs' and {', '.join(single)}: draw the legs as one element id=\"legs\" or as leg_left / leg_right "
            "(each with an optional _lower), not both"
        )
    return SvgCharacter(tuple(shapes), {p: v for p, v in pivots.items() if p in parts_in_order}, report, tuple(warnings))


def read_character_svg(path: Path, *, where: str) -> SvgCharacter:
    """:func:`split_character_svg` of the file ``path``; a missing file raises :class:`VidgenError`."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise VidgenError(f"{where}: file not found (looked for {path})") from None
    except OSError as exc:
        raise VidgenError(f"{where}: cannot read it ({exc})") from None
    return split_character_svg(data, where=where)


def pivot_warnings(svg: SvgCharacter, where: str) -> list[str]:
    """Turning parts (:data:`TURNING_PARTS`) without ``data-pivot``, as one message (or none)."""
    guessed = [p for p in TURNING_PARTS if p in svg.part_shapes() and p not in svg.pivots]
    if not guessed:
        return []
    return [f"{where}: no data-pivot on {', '.join(guessed)}: the pivot is guessed from the part's box (add data-pivot=\"x y\" in viewBox coordinates)"]


# ----- manim side ------------------------------------------------------------------------------


def default_pivot(part: str, box: tuple[float, float, float, float], body_center_x: float) -> tuple[float, float]:
    """The pivot of a part without ``data-pivot``, from its box ``(left, bottom, right, top)`` in
    character units: ``head`` and ``body`` the bottom centre, ``legs``, a single leg and a lower
    segment the top centre (hip, knee, elbow), an arm the top corner nearer the body's centre (the
    shoulder), a ``tail`` the bottom corner nearer it (where it leaves the body), face parts and
    ``accessory`` the centre."""
    left, bottom, right, top = box
    if part in ("head", "body"):
        return (left + right) / 2, bottom
    if part in _HANGING_PARTS:
        return (left + right) / 2, top
    if part in ("arm_left", "arm_right", "tail"):
        nearer = left if abs(left - body_center_x) < abs(right - body_center_x) else right
        return nearer, top if part != "tail" else bottom
    return (left + right) / 2, (bottom + top) / 2


def _boxes(groups: dict[tuple[str, str], object]) -> Iterator[tuple[tuple[str, str], tuple[float, float, float, float]]]:
    for key, group in groups.items():
        left, bottom, _ = group.get_corner([-1, -1, 0])  # type: ignore[attr-defined]
        right, top, _ = group.get_corner([1, 1, 0])  # type: ignore[attr-defined]
        yield key, (float(left), float(bottom), float(right), float(top))


def svg_character_parts(path: Path, *, where: str) -> list[CharacterPart]:
    """The character parts of the SVG file ``path`` (see the module doc), in character units:
    the feet (the bottom of the rest shapes, under the middle of the legs, else of ``body``) at
    the origin, the top of the rest shapes at 1. Stroke widths are set for a character
    :data:`~vidgen.cartoon.character.REFERENCE_HEIGHT` tall. Warnings are logged."""
    import logging

    import numpy as np
    from manim import VGroup

    from vidgen.cartoon.character import REFERENCE_HEIGHT, CharacterPart
    from vidgen.cartoon.primitives import trailing
    from vidgen.vector_mobject import set_svg_stroke, svg_shapes

    svg = read_character_svg(path, where=where)
    log = logging.getLogger("vidgen.scenes")
    for message in (*svg.report.warnings, *svg.warnings, *pivot_warnings(svg, where)):
        log.warning("%s", message)
    vx, vy, _, vh = svg.report.view_box
    groups: dict[tuple[str, str], VGroup] = {}
    manim_per_svg = 1.0
    for shape in svg.shapes:
        box, drawn = svg_shapes(shape.data, where)
        # Manim flips y about the centre of each document's drawing: move every document so its
        # viewBox's top-left corner is the origin (x right, y up, in Manim's units of the SVG).
        group = VGroup(*drawn).shift(-box.get_corner([-1, 1, 0]))
        manim_per_svg = float(box.height) / vh
        groups[(shape.part, shape.shape)] = group

    part_shapes = svg.part_shapes()
    rest = {k: v for k, v in groups.items() if k[1] == part_shapes[k[0]][0]}
    boxes = dict(_boxes(rest))
    bottom = min(b[1] for b in boxes.values())
    top = max(b[3] for b in boxes.values())
    if top - bottom <= 0:
        raise VidgenError(f"{where}: the figure has no height")
    leg_boxes = [box for (part, _), box in boxes.items() if part == "legs" or part in SVG_SINGLE_LEGS]
    feet_boxes = leg_boxes or [boxes[("body", part_shapes["body"][0])]]
    feet_x = (min(b[0] for b in feet_boxes) + max(b[2] for b in feet_boxes)) / 2
    feet = np.array([feet_x, bottom, 0.0])
    unit = 1.0 / (top - bottom)

    def to_character(point_svg: tuple[float, float]) -> tuple[float, float]:
        x, y = (point_svg[0] - vx) * manim_per_svg, -(point_svg[1] - vy) * manim_per_svg
        return (x - feet[0]) * unit, (y - feet[1]) * unit

    for group in groups.values():
        group.shift(-feet).scale(unit, about_point=np.zeros(3))
        for member in group.submobjects:
            set_svg_stroke(member, manim_per_svg * unit * REFERENCE_HEIGHT)
    char_boxes = dict(_boxes({k: groups[k] for k in rest}))
    body_box = char_boxes[("body", part_shapes["body"][0])]
    body_center_x = (body_box[0] + body_box[2]) / 2
    parts = []
    for order, (part, names) in enumerate(part_shapes.items()):
        rest_key = (part, names[0])
        pivot = to_character(svg.pivots[part]) if part in svg.pivots else default_pivot(part, char_boxes[rest_key], body_center_x)
        parent = _parent_of(part, part_shapes)
        if part == "tail":   # it trails in the wind about its pivot, like a generated tail
            for name in names:
                trailing(groups[(part, name)], pivot, "tail")
        parts.append(CharacterPart(part, {name: groups[(part, name)] for name in names}, pivot, parent=parent, order=order * 10))
    return parts


def _parent_of(part: str, present: dict[str, list[str]]) -> str | None:
    """The default parent of ``part`` (head for face parts, body for the rest), or ``body`` when
    the file has no head."""
    from vidgen.cartoon.character import DEFAULT_PARENTS

    parent = DEFAULT_PARENTS[part]
    while parent is not None and parent not in present:
        parent = DEFAULT_PARENTS[parent]
    return parent
