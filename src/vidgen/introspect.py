"""Layout introspection: what is on screen, where, how big and in which colour, per captured frame.

:class:`LayoutRecorder` is a capture listener (:mod:`vidgen.capture`): at every captured frame
it walks the scene's mobjects and records one *object* per visible text, shape, shape group or
image, measured in output-frame pixels with the scene's camera (a moving/zoomed camera frame is
taken into account). The worker writes the result to ``build/.../layout/<scene>.json`` next to
the stills; ``vidgen lint`` reads it. Format: DESIGN.md §15 and docs/CONFIG.md.

Grouping: a text mobject (``Text``, ``MarkupText``, ``Paragraph``, ``Tex``/``MathTex``,
``DecimalNumber``) is one object, not one per glyph; the paragraphs of a ``Code`` listing are
objects of kind ``code`` and its background a shape; an icon (``vidgen.icon_mobject.Icon``) is
one object of kind ``icon`` with its name in ``icon``, a vector picture
(``vidgen.vector_mobject.VectorPicture``, an SVG) one object of kind ``vector``, and a cartoon
character (``vidgen.cartoon.character.Character``) one object of kind ``character`` named after
the character (its box covers every part; plus ``facing``, ``speaking``, ``face`` and the other
keys the cartoon lint rules read, :func:`_character_keys`), a host
(``vidgen.cartoon.host_drawing.HostFigure``) one object of kind ``host`` named after its
character (its box covers the floor line too; the same keys plus ``side`` (where it stands
now), ``below`` and, while it points, ``pointing_at``), a host's pointer line one object of kind
``pointer`` named after the host, the objects of a speech bubble carry
``bubble`` (the speaker's name), and a stage prop (``vidgen.cartoon.props.Prop``) one
object of kind ``prop`` named after the prop (a held one also ``held_by`` and ``hand``; its box
is not part of its holder's; one with shapes also ``shape``, an umbrella's ``closed`` or
``open``); an effect symbol over a head (``vidgen.cartoon.effect_symbols.EffectSymbol``) one
object of kind ``effect`` named after the symbol, with ``effect`` (the symbol) and ``effect_of``
(the character); a motion effect (``vidgen.cartoon.motion_effect_shapes.MotionEffect``: dust,
speed lines, impact stars, a whoosh) one object of kind ``motion_effect`` named after its kind,
with ``motion_effect`` (the kind) and ``effect_of`` (the character or prop); a particle field
(``vidgen.particle_field.ParticleField``) is one object of kind ``particles`` named after its
kind; a stage's shadows and stars (``vidgen.cartoon.shading``) and puddles are left out. A group with no
text or image anywhere
inside is one ``group`` object (an axis' ticks, a network's edges); any other group is walked
into. Parts at opacity 0 are not visible: they are left out of an object's box, and an object
without visible parts is not recorded.

``font_px`` (text only) is the 75th percentile of the heights, in output pixels, of the
object's visible glyphs: about the cap height (≈ 0.7 em) for mixed-case text, the x-height for
text in lowercase letters without ascenders. A rotated line of text (an axis title turned 90°)
is measured across its direction; ``rotation`` gives the angle in degrees (0 when level).
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
    xy: np.ndarray | None = None  # sampled outline points in pixels

    @property
    def area(self) -> float:
        return (self.box[2] - self.box[0]) * (self.box[3] - self.box[1])


@dataclass
class _Walk:
    """State of one frame's walk over the scene."""

    scene: NarratedScene
    camera: Any  # what measures points: the scene's camera, or the overlays' whole-frame camera
    pixels: np.ndarray
    names: dict[int, str]
    order: dict[int, int]
    px_per_unit: float
    objects: list[dict[str, Any]] = field(default_factory=list)
    seen: set[int] = field(default_factory=set)
    overlay: str | None = None  # the overlay id while walking an overlay


class LayoutRecorder:
    """Capture listener that records the layout of every captured frame of one scene."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self._ids: dict[int, tuple[Mobject, str]] = {}

    def __call__(self, scene: NarratedScene, captured: CapturedFrame) -> None:
        from manim import config

        camera = scene.camera
        objects = self.objects(scene, captured.pixels)
        layer = scene.overlay_layer
        shown = layer.posed(captured.frame) if layer is not None else []
        if shown:
            objects += self.overlay_objects(scene, captured.pixels, [(o, m) for o, m, _ in shown], len(objects))
        self.frames.append(
            {
                "beat": captured.beat_id,
                "k": captured.k,
                "n": captured.n,
                **({"mid": captured.mid} if captured.mid is not None else {}),
                "frame": captured.frame,
                "time": round(captured.time, 6),
                **_narrating(scene, captured),
                "still": f"../frames/{captured.scene_id}/{still_name(captured)}",
                "camera": {
                    "center": [_r(c, 4) for c in np.asarray(camera.frame_center)[:2]],
                    "width": _r(camera.frame_width, 4),
                    "height": _r(camera.frame_height, 4),
                    "zoom": _r(config.frame_width / camera.frame_width, 4),
                },
                **({"shot": dict(scene.camera_shot)} if getattr(scene, "camera_shot", None) else {}),
                **(scene.layout_keys(captured.beat_id) if hasattr(scene, "layout_keys") else {}),
                "objects": objects,
                "overlays": [
                    {"id": overlay.id, "type": overlay.config.type, "settled": settled, "skip": list(overlay.lint_skip)}
                    for overlay, _, settled in shown
                ],
            }
        )

    def objects(self, scene: NarratedScene, pixels: np.ndarray) -> list[dict[str, Any]]:
        """The visible objects of ``scene`` as drawn in ``pixels`` (its current frame)."""
        from manim.utils.family import extract_mobject_family_members

        camera = scene.camera
        drawn = extract_mobject_family_members(scene.mobjects, use_z_index=camera.use_z_index, only_those_with_points=True)
        walk = _Walk(
            scene=scene,
            camera=camera,
            pixels=pixels,
            names=_scene_names(scene),
            order={id(m): i for i, m in enumerate(drawn)},
            px_per_unit=camera.pixel_width / camera.frame_width,
        )
        for index, mob in enumerate(scene.mobjects):
            self._walk(walk, mob, [], index, in_code=False)
        self._iso_covers(walk)
        return walk.objects

    def _iso_covers(self, walk: _Walk) -> None:
        """On an iso place (DESIGN.md §89.11): each picture of the place drawn over a character's
        eyes and mouth (its ``features``) gets ``covers`` (character name -> which points of a
        :func:`~vidgen.lint.cartoon_rules.face_grid` over them its opaque pixels cover, ``1`` /
        ``0`` per point), so lint ``hidden_speaker`` measures what hides the face, not the
        picture's box."""
        from vidgen.lint.cartoon_rules import face_grid

        figures = [o for o in walk.objects if o["kind"] == "character" and o.get("features")]
        if not figures:
            return
        mobs = {label: mob for mob, label in self._ids.values()}
        for obj in walk.objects:
            mob = mobs.get(obj["id"])
            if obj["kind"] != "image" or not obj.get("scenery") or mob is None or not getattr(mob, "iso_tile", False):
                continue
            pixels = mob.get_pixel_array()
            corners = walk.camera.points_to_subpixel_coords(mob, mob.points)
            (left, top), (right, bottom) = corners[0], corners[3]
            for figure in figures:
                box = tuple(float(v) for v in figure["features"])
                if obj["order"] <= figure["order"] or intersection_box(tuple(obj["bbox"]), box) is None:
                    continue
                gx, gy = face_grid(box)
                height, width = pixels.shape[:2]
                u = np.floor((gx - left) / max(right - left, 1e-9) * width).astype(int)
                v = np.floor((gy - top) / max(bottom - top, 1e-9) * height).astype(int)
                inside = (u >= 0) & (u < width) & (v >= 0) & (v < height)
                hit = np.zeros(gx.shape, dtype=bool)
                hit[inside] = pixels[v[inside], u[inside], 3] >= 128
                obj.setdefault("covers", {})[figure["name"]] = "".join("1" if h else "0" for h in hit.ravel())
                if hit.any():   # the pieces of the place drawn there (by their boxes on screen)
                    near = obj.setdefault("pieces", [])
                    for name, (x0, y0, x1, y1) in getattr(mob, "iso_pieces", ()):
                        (a, b), (c, d) = walk.camera.points_to_subpixel_coords(mob, np.array([[x0, y1, 0.0], [x1, y0, 0.0]]))
                        if name not in near and intersection_box((a, b, c, d), box) is not None:
                            near.append(name)

    def overlay_objects(self, scene: NarratedScene, pixels: np.ndarray, shown: list[tuple[Any, Mobject]], first: int) -> list[dict[str, Any]]:
        """The visible objects of the overlays ``shown`` (``(overlay, mobject)`` as drawn), drawn
        after (over) every scene object: paths start with ``overlay:<id>``, each object has the
        key ``overlay`` (the id); measured with the overlays' whole-frame camera."""
        from manim.utils.family import extract_mobject_family_members

        layer = scene.overlay_layer
        assert layer is not None
        camera = layer.camera
        drawn = extract_mobject_family_members([m for _, m in shown], use_z_index=camera.use_z_index, only_those_with_points=True)
        objects: list[dict[str, Any]] = []
        for overlay, mob in shown:
            walk = _Walk(
                scene=scene,
                camera=camera,
                pixels=pixels,
                names={},
                order={id(m): first + 1000 + i for i, m in enumerate(drawn)},
                px_per_unit=camera.pixel_width / camera.frame_width,
                overlay=overlay.id,
            )
            self._walk(walk, mob, [f"overlay:{overlay.id}"], 0, in_code=False)
            for obj in walk.objects:
                obj["overlay"] = overlay.id
            objects += walk.objects
        return objects

    def document(self, scene: NarratedScene, per_beat: int) -> dict[str, Any]:
        """The scene's layout file content (frames in frame order)."""
        from manim import config

        width, height = config.pixel_width, config.pixel_height
        sx, sy = width / config.frame_width, height / config.frame_height
        safe = scene.safe_area
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
        first = len(walk.objects)
        self._walk_one(walk, mob, parents, index, in_code=in_code)
        speaker = getattr(mob, "speech_bubble_of", None)
        if isinstance(speaker, str):  # a speech bubble: its plate and text say whose it is
            for obj in walk.objects[first:]:
                obj["bubble"] = speaker
        tagged = getattr(mob, "name_tag_of", None)
        if isinstance(tagged, str):  # a name tag over a speaker on an iso place (§89.11)
            for obj in walk.objects[first:]:
                obj["name_tag"] = tagged

    def _walk_one(self, walk: _Walk, mob: Mobject, parents: list[str], index: int, *, in_code: bool) -> None:
        from manim import Code
        from manim.mobject.types.image_mobject import AbstractImageMobject

        from vidgen.cartoon.character import Character
        from vidgen.cartoon.effect_symbols import EffectSymbol
        from vidgen.cartoon.host_drawing import HostFigure
        from vidgen.cartoon.iso_pictures import IsoPuddles
        from vidgen.cartoon.living_drawing import PropGlow, PropSteam
        from vidgen.cartoon.motion_effect_shapes import MotionEffect
        from vidgen.cartoon.nature_drawing import FallenFruit, Flock
        from vidgen.cartoon.small_props_drawing import WaterDrops
        from vidgen.cartoon.props import Prop
        from vidgen.cartoon.shading import StageShadows, StarField
        from vidgen.cartoon.weather_drawing import FogBand, LightningBolt, Rainbow, SnowBlanket, SnowCap
        from vidgen.icon_mobject import Icon
        from vidgen.particle_field import ParticleField, Puddles
        from vidgen.vector_mobject import VectorPicture

        # a stage's shadows, stars, puddles, glows, steam, birds, fallen fruit, poured water,
        # settled snow, fog, lightning and rainbows: not placed by authors (§69.31, §69.39, §69.54,
        # §69.55, §69.56, §69.60, §69.61; an iso place's puddles §90.2)
        unplaced = (StageShadows, StarField, Puddles, IsoPuddles, PropGlow, PropSteam, Flock, FallenFruit, WaterDrops, SnowBlanket, SnowCap, FogBand, LightningBolt, Rainbow)
        if id(mob) in walk.seen or isinstance(mob, unplaced):
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
            if getattr(mob, "scenery", False) and walk.objects and walk.objects[-1]["id"] == self._id(mob):
                walk.objects[-1]["scenery"] = True   # a piece of the set (a level's tiles, §86.10): cut by the frame on purpose
            return
        if isinstance(mob, Icon):
            self._emit_parts(walk, mob, path, name, "icon", [m for m in mob.get_family() if _drawn(m)], icon=mob.icon_name)
            return
        if isinstance(mob, HostFigure):  # the host and its floor line: one object (DESIGN.md §71)
            self._emit_parts(walk, mob, path, mob.host_name, "host", [m for m in mob.get_family() if _drawn(m)])
            if walk.objects and walk.objects[-1]["id"] == self._id(mob):
                keys = {**_character_keys(walk, mob.character), "side": mob.side, "below": mob.layout.below}
                if mob.pointing_at is not None:
                    keys["pointing_at"] = mob.pointing_at
                walk.objects[-1].update(keys)
            return
        if getattr(mob, "host_pointer_of", None) is not None:  # a host's pointer line (DESIGN.md §71.1)
            self._emit_parts(walk, mob, path, mob.host_pointer_of, "pointer", [mob])
            return
        if isinstance(mob, Character):  # one figure, not one object per part
            self._emit_parts(walk, mob, path, name or mob.name, "character", [m for m in mob.get_family() if _drawn(m)])
            if walk.objects and walk.objects[-1]["id"] == self._id(mob):
                walk.objects[-1].update(_character_keys(walk, mob))
            return
        if isinstance(mob, Prop):  # one prop, also an SVG one (not a vector picture inside)
            self._emit_parts(walk, mob, path, name or mob.name, "prop", [m for m in mob.get_family() if _drawn(m)])
            if walk.objects and walk.objects[-1]["id"] == self._id(mob):
                if mob.held_by is not None:
                    walk.objects[-1].update({"held_by": mob.held_by, "hand": mob.hand})
                if mob.shape is not None:
                    walk.objects[-1]["shape"] = mob.shape
                walk.objects[-1].update(_prop_keys(mob))
            return
        if isinstance(mob, EffectSymbol):  # one symbol over a head (§69.40)
            self._emit_parts(walk, mob, path, name or mob.kind, "effect", [m for m in mob.get_family() if _drawn(m)])
            if walk.objects and walk.objects[-1]["id"] == self._id(mob):
                walk.objects[-1].update({"effect": mob.kind, "effect_of": mob.effect_of})
            return
        if isinstance(mob, MotionEffect):  # dust, speed lines, stars or a whoosh (§69.41)
            self._emit_parts(walk, mob, path, name or mob.kind, "motion_effect", [m for m in mob.get_family() if _drawn(m)])
            if walk.objects and walk.objects[-1]["id"] == self._id(mob):
                walk.objects[-1].update({"motion_effect": mob.kind, "effect_of": mob.effect_of})
            return
        if isinstance(mob, ParticleField):  # one field of particles, named after its kind
            self._emit_parts(walk, mob, path, name or mob.name, "particles", [m for m in mob.get_family() if _drawn(m)])
            return
        if isinstance(mob, VectorPicture):  # one picture, not one object per path
            self._emit_parts(walk, mob, path, name, "vector", [m for m in mob.get_family() if _drawn(m)])
            return
        own = [mob] if _drawn(mob) else []
        if own and not mob.submobjects:
            self._emit_parts(walk, mob, path, name, "shape", own)
            return
        family = mob.get_family()[1:]
        if family and not any(_text_kind(m, True) is not None or isinstance(m, AbstractImageMobject) for m in family):
            self._emit_parts(walk, mob, path, name, "group", [m for m in mob.get_family() if _drawn(m)])
            if _scenery(mob) and walk.objects and walk.objects[-1]["id"] == self._id(mob):
                walk.objects[-1]["scenery"] = True   # a cell's world in µm (§95): cropped by a zoomed view on purpose
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
        text = _text_of(mob, kind)
        rotation, heights = _glyph_heights(parts, kind != "math" and "\n" not in text.strip())
        item.update(
            {
                "text": text,
                "font_px": _r(np.percentile(heights, FONT_PERCENTILE)) if heights else 0.0,
                "rotation": rotation,
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


def intersection_box(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float, float] | None:
    """The overlap of two boxes ``(x0, y0, x1, y1)`` (``None``: apart)."""
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def _character_keys(walk: _Walk, figure: Any) -> dict[str, Any]:
    """What the cartoon lint rules read about a character (DESIGN.md §69.17): ``facing``,
    ``speaking`` and, when they apply, ``face`` (its head's box), ``viseme`` (what its lip sync
    shows), ``looked_at``, ``passage`` (``enter`` / ``exit`` under way), ``walked_in`` and
    ``holding`` (hand -> prop name, §69.27), ``sitting_on`` / ``leaning_on`` (a prop name, §69.28),
    ``riding`` (the vehicle it rides, §69.52), ``hand_in_hand`` (whose hand it holds, §100.10),
    ``hidden`` (a shot with ``clear`` hides it, §100.6),
    ``depth`` (how far back it stands on a stage, when not at the front, §69.44)."""
    keys: dict[str, Any] = {"facing": figure.facing, "speaking": figure.lip_sync_track is not None}
    depth = float(getattr(figure, "stage_depth", 0.0))
    if depth > 0:
        keys["depth"] = round(depth, 4)
    if figure.has_part("head"):
        boxes = [p.box for p in (_measure(walk, m) for m in figure.parts["head"].get_family()) if p is not None]
        if boxes:
            keys["face"] = [_r(min(b[0] for b in boxes)), _r(min(b[1] for b in boxes)), _r(max(b[2] for b in boxes)), _r(max(b[3] for b in boxes))]
    optional = {"viseme": figure.spoken_viseme, "looked_at": figure.looked_at, "passage": figure.passage, "walked_in": figure.walked_in,
                "holding": dict(figure.holding) or None, "sitting_on": figure.sitting_on, "leaning_on": figure.leaning_on,
                "riding": figure.riding, "hand_in_hand": getattr(figure, "hand_in_hand", None),
                "hidden": True if getattr(figure, "hidden_by_shot", False) else None}
    keys.update({key: value for key, value in optional.items() if value is not None})
    if getattr(figure, "iso_feet", None) is not None:   # on an iso place (DESIGN.md §89.11)
        keys.update(_iso_character_keys(walk, figure))
    return keys


def _iso_character_keys(walk: _Walk, figure: Any) -> dict[str, Any]:
    """What lint reads about a character on an iso place (DESIGN.md §89.11): ``features`` (the box
    of its eyes and mouth: what must show for the viewer to see who speaks) and ``name_tag``
    (its name tag shows: it speaks while small on screen)."""
    keys: dict[str, Any] = {}
    parts = [figure.parts[name] for name in ("eyes", "mouth") if figure.has_part(name)]
    boxes = [p.box for part in parts for p in (_measure(walk, m) for m in part.get_family()) if p is not None]
    if boxes:
        keys["features"] = [_r(min(b[0] for b in boxes)), _r(min(b[1] for b in boxes)), _r(max(b[2] for b in boxes)), _r(max(b[3] for b in boxes))]
    if getattr(figure, "name_tagged", False):
        keys["name_tag"] = True
    return keys


def _prop_keys(prop: Any) -> dict[str, Any]:
    """What ``prop_overlap`` reads about a prop (DESIGN.md §69.51): ``prop`` (its kind: a
    built-in prop's name or ``svg``), ``depth`` (how far back it stands, when not at the front, as
    for a character), ``raised`` (lifted, or hanging on a wall) and ``flat`` (lying flat on the
    floor, a rug), each only when true."""
    from vidgen.cartoon.props import FLAT_PROPS

    keys: dict[str, Any] = {"prop": prop.kind}
    depth = float(getattr(prop, "stage_depth", 0.0))
    if depth > 0:
        keys["depth"] = round(depth, 4)
    if prop.raised:
        keys["raised"] = True
    if prop.kind in FLAT_PROPS:
        keys["flat"] = True
    return keys


def _narrating(scene: NarratedScene, captured: CapturedFrame) -> dict[str, bool]:
    """``{"narrating": ...}``: whether the still's beat is being narrated at its time (its audio, or
    the estimate, between its start and ``start + d``; not in the pad), for a still taken once
    the beat has ended (a beat-end still); ``{}`` for others."""
    for timing in scene.beat_log:
        if timing.beat_id == captured.beat_id:
            return {"narrating": timing.start <= captured.time < timing.end}
    return {}


# ----- measuring -------------------------------------------------------------------------------


def _scenery(mob: Mobject) -> bool:
    """True if ``mob`` is marked ``scenery`` (cropped by the camera on purpose), or is a group of
    such pieces only (empty groups beside them aside)."""
    if getattr(mob, "scenery", False):
        return True
    drawn = [sub for sub in mob.submobjects if sub.family_members_with_points()]
    return bool(drawn) and not _drawn(mob) and all(_scenery(sub) for sub in drawn)


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
    camera = walk.camera
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
        xy=xy,
    )


#: Smallest angle (degrees) at which a line of text counts as rotated; and how much longer than
#: wide the spread of its glyphs must be to tell its direction.
_MIN_ROTATION = 8.0
_LINE_ASPECT = 3.0


def _glyph_heights(parts: list[_Part], one_line: bool) -> tuple[float, list[float]]:
    """The rotation of a line of text (degrees, counter-clockwise; 0 when level, or when it
    cannot be told: several lines, fewer than 4 glyphs) and its glyphs' heights measured across
    that direction, so a rotated label is not measured sideways."""
    level = [p.shape_height for p in parts if p.shape_height > 0]
    glyphs = [p for p in parts if p.xy is not None and len(p.xy)]
    if not one_line or len(glyphs) < 4:
        return 0.0, level
    centers = np.array([[(p.box[0] + p.box[2]) / 2, (p.box[1] + p.box[3]) / 2] for p in glyphs])
    values, vectors = np.linalg.eigh(np.cov(centers.T))
    if values[1] <= 0 or values[1] < _LINE_ASPECT**2 * max(values[0], 1e-9):
        return 0.0, level
    dx, dy = vectors[:, 1]
    angle = float(np.degrees(np.arctan2(-dy, dx)))   # pixel y runs down
    angle = (angle + 90.0) % 180.0 - 90.0            # a direction, not an arrow
    if abs(angle) < _MIN_ROTATION:
        return 0.0, level
    normal = np.array([-dy, dx])
    heights = [float(np.ptp(p.xy @ normal)) for p in glyphs]
    return round(angle, 1), [h for h in heights if h > 0]


def _backdrop(pixels: np.ndarray, bbox: list[float], text_colors: list[str]) -> str | None:
    """Most common colour in the text's box in the frame, ignoring the text's own colours.

    ``None`` when the box is entirely outside the frame.
    """
    height, width = pixels.shape[:2]
    left, top, right, bottom = bbox[:4]
    pad = (bottom - top) * 0.5 - (right - left)
    if pad > 0:  # a narrow glyph ('I', 'l', '1'): its box is nearly all anti-aliased ink, so look beside it too
        left, right = left - pad / 2, right + pad / 2
    x0, y0 = max(int(np.floor(left)), 0), max(int(np.floor(top)), 0)
    x1, y1 = min(int(np.ceil(right)), width), min(int(np.ceil(bottom)), height)
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
