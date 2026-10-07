"""The ``callout`` beat action (DESIGN.md §44): a box, circle, arrow, label, spotlight or
magnifier drawn on any scene for one beat, pointing at targets of the scene or at coordinates of
the frame. Built from the Step 34 callout helpers (``callout_box`` ...), written against
``vidgen.api`` only, like project actions.

Labels are placed away from what they point at, inside the scene's safe area (which already
leaves out overlays drawn with ``reserve: true``; while the camera is zoomed in: inside the
view), clear of the text on screen, of other callouts and of the overlays.
"""

import logging
from typing import Any, Literal

from vidgen.api import *

log = logging.getLogger("vidgen.actions")

CalloutActionKind = Literal["box", "circle", "arrow", "label", "spotlight", "magnifier"]
#: Kinds that need an area with a size ([x, y, w, h]) when they are given coordinates.
SIZED = ("spotlight", "magnifier")
#: Distances (units) tried between a ``label`` callout and what it labels, shortest first.
LABEL_GAPS = (0.15, 0.35, 0.7)
#: Room (units) a ``label`` callout's plate keeps from other text where it can (lint's
#: ``label_spacing`` asks for 0.02 of the frame height, 0.16 units).
LABEL_CLEARANCE = 0.2
#: Mobjects whose boxes labels keep clear of (text and formulas).
TEXT_TYPES = (Text, MarkupText, Paragraph, SingleStringMathTex)
#: Other targets smaller than this share of the view are kept clear of too (a node, a bar; not
#: the axes or a map).
SMALL_TARGET = 0.2


@action("callout")
class CalloutAction(Action):
    """Point at a target, or at a spot of the frame (``area``), for this beat: a ``box``, a
    ``circle``, an ``arrow`` from a label, a ``label`` beside it, a ``spotlight`` (the rest of
    the view darkened) or a ``magnifier`` (an enlarged inset of a picture). It goes when the next
    beat starts (``until: <beat>``: when that beat starts; ``keep: true``: stays to the end of the
    scene). Works on every scene type, with or without targets."""

    class Options(ActionOptions):
        kind: CalloutActionKind = "box"
        """box, circle, arrow (a label with an arrow to it), label (a label beside it), spotlight (the rest of the view darkened) or magnifier (an enlarged inset of a picture)."""
        label: TranslatableStr = ""
        """Short text on a plate in the callout's colour (required for kind: label)."""
        area: list[float] | None = None
        """[x, y, w, h] or a point [x, y] from the top-left corner: fractions 0-1 of the target (of its picture when it shows one), or without a target of the frame (within); default: the whole target."""
        within: Literal["frame", "safe"] = "frame"
        """Without a target: area is a fraction of the visible frame or of its safe area (units: fraction)."""
        units: Literal["fraction", "px"] = "fraction"
        """area in fractions, or in pixels (of the target's picture, or of the output frame)."""
        color: ThemeColor = "highlight"
        """Colour of the mark and the label plate (theme token or hex)."""
        label_size: ThemeSize = "caption"
        """Size of the label (never below the readable size)."""
        side: Literal["auto", "top", "bottom", "left", "right"] = "auto"
        """Where the label (or the inset) goes; auto: where there is room."""
        curved: bool = False
        """arrow: a curved arrow."""
        zoom: float = Field(default=2.0, gt=1.0, le=8.0)
        """magnifier: how much larger the inset shows the area (less when it would not fit)."""
        keep: bool = False
        """Stay until the scene ends instead of going when the next beat starts."""
        name: str | None = None
        """A target name for the callout, so later actions can use it (dim: name, highlight: name)."""

        @model_validator(mode="after")
        def _check(self) -> "CalloutAction.Options":
            a = self.area
            if a is not None:
                if len(a) not in (2, 4):
                    raise ValueError(f"area is [x, y, w, h] or [x, y], got {len(a)} numbers")
                if any(v < 0 for v in a):
                    raise ValueError("area: coordinates cannot be negative")
                if len(a) == 4 and (a[2] <= 0 or a[3] <= 0):
                    raise ValueError("area: the width and height must be more than 0")
                if self.units == "fraction" and (any(v > 1 for v in a) or (len(a) == 4 and (a[0] + a[2] > 1.0001 or a[1] + a[3] > 1.0001))):
                    raise ValueError(f"area: {a} does not fit in 0-1 (fractions; use units: px for pixels)")
                if self.kind in SIZED and len(a) != 4:
                    raise ValueError(f"a {self.kind} needs an area with a size: [x, y, w, h]")
            if self.kind == "label" and not self.label.strip():
                raise ValueError("kind: label needs a label text")
            if self.kind == "magnifier" and a is None:
                raise ValueError("a magnifier needs the area of the picture to enlarge: [x, y, w, h]")
            if self.curved and self.kind != "arrow":
                raise ValueError("curved: only arrows can be curved")
            if "zoom" in self.model_fields_set and self.kind != "magnifier":
                raise ValueError("zoom: only for a magnifier")
            if "within" in self.model_fields_set and (a is None or self.units == "px"):
                raise ValueError("within: only with an area in fractions (px are pixels of the output frame)")
            return self

    run_time = 0.8
    reversible = True
    needs_target = False
    until_next_beat = True
    after_camera = True   # due with a zoom: drawn once the camera is in, built for that view

    def problems(self) -> list[tuple[str, str]]:
        """A target or an area is needed (a magnifier needs the target showing the picture);
        ``keep`` and ``until`` contradict each other."""
        found: list[tuple[str, str]] = []
        o = self.options
        if not self.config.targets() and o.area is None:
            found.append(("target", "a callout needs a target or an area ([x, y, w, h] or [x, y] of the frame)"))
        if o.kind == "magnifier" and not self.config.targets():
            found.append(("target", "a magnifier needs the target showing the picture (e.g. image) and an area of it"))
        if self.config.targets() and "within" in o.model_fields_set:
            found.append(("within", "with a target, area is a fraction of the target; within is for areas of the frame"))
        if o.keep and self.config.until is not None:
            found.append(("keep", "keep: stays to the scene's end, until: goes at a beat; give one of them"))
        return found

    def provides(self) -> list[str]:
        """The callout's ``name``, when given."""
        return [self.options.name] if self.options.name else []

    def default_until(self, later: Any) -> str | None:
        """The next beat, unless ``keep``."""
        return None if self.options.keep else super().default_until(later)

    # ----- apply / revert ----------------------------------------------------------------------

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Build the callout for the current camera view and draw it."""
        o = self.options
        view, scale = _view(scene)
        bounds = _bounds(scene, view, scale)
        picture = _picture(targets)
        whole = _region([m for t in targets for m in _parts(scene, t)]) if targets else None
        try:
            area = self._area(view, bounds, whole, picture)
        except VidgenError as exc:
            raise VidgenError(f"scene '{scene.spec.id}' {self.config.describe()}: {exc}") from None
        avoid = _avoid(scene, view, scale, targets, area)
        common: dict[str, Any] = {
            "color": o.color, "label_size": o.label_size, "side": o.side, "bounds": bounds, "avoid": avoid, "scale": scale, "theme": scene.theme,
        }
        if o.kind == "magnifier":
            if picture is None or isinstance(picture, ClipMobject):
                what = "a moving picture" if picture is not None else "no picture"
                raise VidgenError(f"scene '{scene.spec.id}' {self.config.describe()}: a magnifier needs a still picture, the target shows {what}")
            made = callout_magnifier(o.area, o.label, image=picture, units=o.units, zoom=o.zoom, **common)
        elif o.kind == "arrow":
            made = callout_arrow(area, o.label, curved=o.curved, prefer_off=whole, **common)
        elif o.kind == "spotlight":
            made = callout_spotlight(area, o.label, cover=view, **common)
        elif o.kind == "label":
            made = _label(area, o.label, prefer_off=whole, **common)
        else:
            made = callout(o.kind, area, o.label, **common)
        top = max((m.z_index for m in scene.get_mobject_family_members()), default=0)
        made.set_z_index(top + (1 if o.kind == "spotlight" else 2))  # over the scene; a shade under other callouts
        self.made = made
        if o.name:
            tag = made.tag if made.kind != "label" else made.mark
            on_fill = [(tag.text, tag.plate)] if getattr(tag, "is_label", False) else []
            scene.target(o.name, made, entrance=made.draw, on_fill=on_fill)
        return made.draw()

    def revert(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        """Fade the callout out."""
        made = getattr(self, "made", None)
        return [fade_out(part) for part in scene.on_screen_parts(made)] if made is not None else []

    def _area(self, view: Region, bounds: Region, whole: Region | None, picture: Mobject | None) -> Region:
        """What the callout points at: ``area`` of the target's picture / box or of the view,
        else the targets' box."""
        o = self.options
        if o.area is None:
            assert whole is not None
            return whole
        if whole is not None:
            within: Any = picture if picture is not None else whole
            return callout_area(o.area, within, units=o.units)
        if o.units == "px":  # pixels of the output frame (of the view when zoomed in)
            return callout_area(o.area, view, units="px", pixels=(int(config.pixel_width), int(config.pixel_height)))
        return callout_area(o.area, view if o.within == "frame" else bounds)


# ----- helpers -------------------------------------------------------------------------------------


def _view(scene: NarratedScene) -> tuple[Region, float]:
    """The part of the scene the camera shows and its size relative to the whole frame (1 =
    not zoomed; 0.5 = zoomed in twice)."""
    frame = getattr(scene.camera, "frame", None)
    if frame is None:
        return frame_region(), 1.0
    w, h = float(frame.width), float(frame.height)
    x, y = (float(v) for v in frame.get_center()[:2])
    return Region(x - w / 2, y - h / 2, x + w / 2, y + h / 2), w / scene.frame_width


def _bounds(scene: NarratedScene, view: Region, scale: float) -> Region:
    """Where labels may go: the scene's safe area, or the zoomed view minus its margins."""
    if abs(scale - 1) < 1e-6 and abs(view.center[0]) < 1e-6 and abs(view.center[1]) < 1e-6:
        return scene.safe_area
    return view.inset(scene.margin_x * scale, scene.margin_y * scale)


def _parts(scene: NarratedScene, target: Target) -> list[Mobject]:
    """What a callout on ``target`` surrounds: its outline (a bar with its value), else its
    parts on screen (else all of it)."""
    if target.outline is not None:
        return [target.outline]
    return scene.on_screen_parts(target) or [target.mobject]


def _region(mobs: list[Mobject]) -> Region:
    """The box around ``mobs`` (those with points; all of them when none has)."""
    boxes = [callout_area(m) for m in mobs if m.has_points() or m.submobjects]
    boxes = boxes or [callout_area(m) for m in mobs]
    return Region(min(b.x0 for b in boxes), min(b.y0 for b in boxes), max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def _picture(targets: list[Target]) -> Mobject | None:
    """The largest picture (image or clip) shown by the targets, or ``None``."""
    images = [m for t in targets for m in t.mobject.get_family() if isinstance(m, ImageMobject)]
    return max(images, key=lambda m: m.width * m.height) if images else None


def _holds(box: Region, area: Region) -> bool:
    """Whether ``box`` holds the middle of ``area`` (a group that the area is part of)."""
    x, y = area.center[:2]
    return box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1


def _avoid(scene: NarratedScene, view: Region, scale: float, targets: list[Target], area: Region) -> list[Region]:
    """Boxes labels keep clear of: the text on screen, callouts on screen, the scene's other
    small targets on screen (not those holding ``area``) and the overlays (drawn over the frame;
    mapped into a zoomed view)."""
    boxes: list[Region] = []

    def walk(m: Mobject) -> None:
        if isinstance(m, TEXT_TYPES):
            if m.has_points() or m.submobjects:
                boxes.append(callout_area(m).inset(-0.05 * scale))
            return
        if isinstance(m, Callout):
            boxes.append(m.extent())
            return
        for sub in m.submobjects:
            walk(sub)

    for mob in scene.mobjects:
        walk(mob)
    shown = {id(m) for m in scene.get_mobject_family_members()}
    for t in scene.targets:
        if not any(id(p) in shown for p in t.mobject.get_family()):
            continue
        if isinstance(t.mobject, Callout):  # its parts are on screen, not the group
            boxes.append(t.mobject.extent())
        elif t not in targets:  # other parts of the scene (a node, a bar), not big ones (axes, a map)
            box = _region(scene.on_screen_parts(t))
            if box.width * box.height < SMALL_TARGET * view.width * view.height and not _holds(box, area):
                boxes.append(box)
    layer = getattr(scene, "overlay_layer", None)
    if layer is not None:
        cx, cy = view.center[:2]
        for mob in layer.mobjects:
            if mob is not None:
                r = callout_area(mob)
                boxes.append(Region(cx + r.x0 * scale, cy + r.y0 * scale, cx + r.x1 * scale, cy + r.y1 * scale))
    return boxes


def _overlaps(a: Region, b: Region) -> bool:
    return a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1


def _label(
    area: Region, text: str, *, color: Any, label_size: Any, side: Any, bounds: Region, avoid: list[Region], scale: float, theme: Any,
    prefer_off: Region | None = None,
) -> Callout:
    """A label beside ``area`` without a mark (``kind: label``)."""
    tag = callout_label(text, color=color, size=label_size, scale=scale, theme=theme)
    # without a mark, a label must not stand nearer another bar, value or title than its own
    rivals = [a for a in avoid if not _overlaps(a, area)]
    spot = label_spot(
        (tag.width, tag.height), area, bounds=bounds, avoid=avoid, gaps=[g * scale for g in LABEL_GAPS], side=side,
        prefer_off=prefer_off, clearance=LABEL_CLEARANCE * scale, rivals=rivals, straight=True,
    )
    tag.move_to(spot.center)
    return Callout("label", area, tag)
