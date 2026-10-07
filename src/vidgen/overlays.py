"""Overlays (DESIGN.md §41): things drawn on top of every scene, fixed to the screen — lower
thirds, a watermark, later a progress bar or captions.

The video-level ``overlays:`` list (``vidgen.config.OverlayConfig``) names registered overlay
types (``@overlay``, see ``vidgen.registry``) with their options and where they appear
(``scenes``, ``exclude``, ``from``, ``to``); a scene's ``overlays:`` turns them off or overrides
options, or adds an overlay of that scene only. An :class:`Overlay` builds its mobject once per
scene render and says, as a pure function of the time in the video, how it looks
(:meth:`Overlay.state`, :meth:`Overlay.pose`); :mod:`vidgen.overlay_layer` draws it into every
frame of the scene. Video-level times come from the planned timeline (:mod:`vidgen.videoplan`),
so an overlay looks the same on both sides of a cut.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
from manim import Mobject, VMobject
from manim.mobject.types.image_mobject import AbstractImageMobject
from pydantic import BaseModel, ConfigDict, ValidationError

from vidgen.config import OVERLAY_KEYS, OVERLAY_OVERRIDE_KEYS, OverlayConfig, SceneConfig, validation_problems
from vidgen.errors import Problem, VidgenError
from vidgen.regions import Region
from vidgen.videoplan import Chapter, SceneSlot, VideoPlan

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.registry import OverlayType
    from vidgen.theme import Theme

#: Gap (units) kept between a reserved overlay and the scene's shrunken safe area.
RESERVE_GAP = 0.2


class OverlayOptions(BaseModel):
    """Base class of an overlay type's ``Options`` model; unknown keys are an error.

    Fields may use ``ThemeColor`` / ``ThemeSize`` / ``IconName`` (checked against the project's
    theme). Field names must differ from the keys every overlay entry has (``type``, ``id``,
    ``scenes``, ``exclude``, ``from``, ``to``, ``reserve``).
    """

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)


@dataclass
class OverlayContext:
    """What an overlay knows about the video while one scene renders.

    Times are planned (:mod:`vidgen.videoplan`): ``scene`` is the scene being rendered (its
    ``start`` in the video, ``duration``, ``beats`` with times from the scene's start,
    ``chapter``), ``scenes`` all of them, ``duration`` the whole video, ``chapters`` the video's
    chapters (DESIGN.md §42) and ``chapter`` the scene's. ``fps`` is the render's frame rate.
    """

    project: Project
    theme: Theme
    plan: VideoPlan
    scene_id: str

    @property
    def fps(self) -> int:
        """Frames per second of the render."""
        return self.plan.fps

    @cached_property
    def scene(self) -> SceneSlot:
        """The scene being rendered, as planned."""
        return self.plan.scene(self.scene_id)

    @property
    def scenes(self) -> tuple[SceneSlot, ...]:
        """Every scene of the video, as planned."""
        return self.plan.scenes

    @property
    def duration(self) -> float:
        """The planned length of the whole video (seconds)."""
        return self.plan.duration

    @property
    def chapters(self) -> tuple[Chapter, ...]:
        """The video's chapters, in order (``chapter`` scenes and scenes with a ``chapter:``)."""
        return self.plan.chapters

    @property
    def chapter(self) -> Chapter | None:
        """The chapter of the scene being rendered (``None`` before the first chapter)."""
        return self.plan.chapter_of(self.scene_id)

    def video_time(self, scene_time: float) -> float:
        """A time in the scene being rendered as a time in the video."""
        return self.scene.start + scene_time

    def scene_start(self, scene_id: str) -> float:
        """Where ``scene_id`` starts in the video (seconds)."""
        return self.plan.scene_start(scene_id)


class Overlay:
    """Base class of an overlay type (register with ``@overlay("name")``).

    One instance is made per scene render; ``self.options`` is the validated ``Options`` (with
    the scene's overrides), ``self.config`` the entry (``OverlayConfig``), ``self.context`` the
    :class:`OverlayContext`, ``self.id`` the entry's id, ``self.scenes`` the ids of the scenes the
    entry is drawn on (in video order) and ``self.span`` its ``from`` / ``to`` in video seconds
    (``math.inf`` without an end).

    Subclasses implement :meth:`build` (the overlay at its full look, in its place: the frame is
    the whole screen, never moved by the scene's camera) and, when it changes over time,
    :meth:`window`, :meth:`state` and :meth:`pose`. ``state`` must be a pure function of the
    time in the video, so the overlay is the same on both sides of a cut.
    """

    #: Options of this overlay type (keys besides ``type``/``id``/``scenes``/``exclude``/``from``/
    #: ``to``/``reserve``).
    Options: ClassVar[type[OverlayOptions]] = OverlayOptions
    #: Lint rules that do not apply to its objects (a watermark faint on purpose: ``contrast``).
    lint_skip: ClassVar[tuple[str, ...]] = ()
    #: Drawing order between overlays: higher layers are drawn over lower ones.
    layer: ClassVar[int] = 0
    #: Whether it makes way for the scene's other overlays: built after them, with
    #: :attr:`clear_of` holding the boxes of those that reserve room (bottom captions), which
    #: :meth:`clear_area` keeps it clear of (a lower third moves above the captions).
    yields: ClassVar[bool] = False

    def __init__(
        self,
        options: OverlayOptions,
        config: OverlayConfig,
        context: OverlayContext,
        *,
        id: str,
        scenes: Sequence[str] = (),
        span: tuple[float, float] = (0.0, math.inf),
    ) -> None:
        self.options = options
        self.config = config
        self.context = context
        self.id = id
        self.scenes = tuple(scenes)
        self.span = span
        #: Boxes of the scene's reserving overlays, set before :meth:`build` when it :attr:`yields`.
        self.clear_of: list[Region] = []

    @classmethod
    def validate_project(cls, options: Any, project: Project, scenes: Sequence[str]) -> list[str]:
        """Project-aware checks run by ``vidgen validate`` (e.g. an image file exists, a beat id
        is a beat of the scene); ``scenes`` are the ids the entry is drawn on. One message per
        problem, starting with the option name (``"image: file not found: ..."``)."""
        return []

    def shown_in(self, start: float, end: float) -> bool:
        """Whether it shows at all between video times ``start`` and ``end`` (a scene's slot that
        its interval reaches). ``False`` leaves it out of that scene's render: nothing drawn and
        nothing ``reserve``d there (a chapter indicator hidden on chapter cards). Asked only of
        :attr:`timed` overlays. Default: ``True``."""
        return True

    def window(self) -> tuple[float, float] | None:
        """The video seconds ``(start, end)`` it is shown in (within ``span``), or ``None`` for
        the whole span (the default)."""
        return None

    def default_reserve(self) -> bool:
        """Whether scenes keep clear of it when its entry does not say (``reserve`` unset).
        Default ``False``; captions along the top or bottom edge say ``True``."""
        return False

    @property
    def reserves(self) -> bool:
        """Whether the scenes it is drawn on keep their layouts clear of it: the entry's (or the
        scene's override's) ``reserve``, else :meth:`default_reserve`."""
        return self.config.reserve if self.config.reserve is not None else self.default_reserve()

    def build(self) -> Mobject | None:
        """The overlay at its full look and place (called once per scene render)."""
        raise NotImplementedError

    def state(self, t: float) -> Hashable | None:
        """How it looks at video time ``t`` (inside its span and window): any hashable value,
        frames with equal states are drawn once; ``None`` hides it. Default: always the same."""
        return "on"

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        """The mobject to draw for ``state`` (default: the built one). Return a modified copy;
        never change ``mobject`` itself."""
        return mobject

    def settled(self, state: Hashable) -> bool:
        """Whether ``state`` is its full look rather than a transition (sliding in, fading out):
        ``vidgen lint`` checks only settled overlays, as it checks only settled beat ends.
        Default: always."""
        return True

    # ----- helpers for subclasses ------------------------------------------------------------

    def clear_area(self, area: Region, mobject: Mobject) -> Region:
        """``area`` without the boxes of :attr:`clear_of` that ``mobject`` (placed in ``area``)
        comes within :data:`RESERVE_GAP` of (each cut away with :func:`avoid`); ``area`` itself
        when nothing is in the way. Place the mobject again in the result."""
        mine = mobject_region(mobject)
        if mine is None:
            return area
        for box in self.clear_of:
            if avoid(mine, box) is not mine:   # it comes near the box
                area = avoid(area, box)
        return area

    def interval(self) -> tuple[float, float]:
        """Where it is shown in the video: ``span`` intersected with :meth:`window`."""
        start, end = self.span
        window = self.window()
        if window is not None:
            start, end = max(start, window[0]), min(end, window[1])
        return start, end

    @property
    def timed(self) -> bool:
        """Whether it depends on where the scene is in the video (a bounded span or a window)."""
        return self.span != (0.0, math.inf) or self.window() is not None

    @staticmethod
    def transition(t: float, start: float, end: float, enter: float, exit: float) -> float:
        """Progress 0..1 of an element shown from ``start`` to ``end`` that takes ``enter``
        seconds to come in and ``exit`` to go: 1 in between, eased (smooth) at both ends."""
        from manim import smooth

        p = 1.0
        if enter > 0 and t < start + enter:
            p = min(p, max(0.0, (t - start) / enter))
        if exit > 0 and t > end - exit:
            p = min(p, max(0.0, (end - t) / exit))
        return float(smooth(p))


def with_opacity(mobject: Mobject, factor: float) -> Mobject:
    """A copy of ``mobject`` with every part's opacity (fill, stroke, image alpha) times
    ``factor``."""
    copy = mobject.copy()
    for part in copy.get_family():
        if isinstance(part, VMobject):
            for getter, setter in ((part.get_fill_rgbas, "fill_rgbas"), (part.get_stroke_rgbas, "stroke_rgbas")):
                rgbas = np.array(getter(), dtype=float)
                if len(rgbas):
                    rgbas[:, 3] *= factor
                    setattr(part, setter, rgbas)
        elif isinstance(part, AbstractImageMobject):
            pixels = np.array(part.pixel_array, dtype=float)
            pixels[:, :, 3] *= factor
            part.pixel_array = pixels.astype(np.uint8)
    return copy


def check_overlay_class(name: str, cls: object) -> None:
    """Raise :class:`VidgenError` unless ``cls`` is a usable overlay class."""
    if not (isinstance(cls, type) and issubclass(cls, Overlay)):
        raise VidgenError(f"@overlay({name!r}) must decorate a subclass of Overlay, got {cls!r}")
    where = f"overlay type '{name}' ({cls.__qualname__})"
    options = cls.Options
    if not (isinstance(options, type) and issubclass(options, OverlayOptions)):
        raise VidgenError(f"{where}: 'Options' must be a subclass of OverlayOptions")
    clash = sorted({f.alias or n for n, f in options.model_fields.items()} & set(OVERLAY_KEYS))
    if clash:
        raise VidgenError(f"{where}: option names {', '.join(clash)} are reserved (every overlay has {', '.join(OVERLAY_KEYS)})")
    if cls.build is Overlay.build:
        raise VidgenError(f"{where}: implement build(self)")
    if not isinstance(cls.layer, int):
        raise VidgenError(f"{where}: layer must be an int")


# ----- entries: which overlay is drawn on which scene ------------------------------------------------


@dataclass
class OverlayEntry:
    """An overlay of the config: a video-level entry, or (``local``) one a scene adds for itself.

    ``location`` is its config path (``overlays[1]``, ``scenes[3].overlays.speaker``).
    """

    id: str
    location: str
    config: OverlayConfig
    kind: OverlayType | None
    local: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def selects(self, spec: SceneConfig) -> bool:
        """Whether the entry is drawn on ``spec`` as far as the config says (scene lists and the
        scene's own ``overlays:`` setting; not yet whether its time range reaches the scene)."""
        if self.local is not None:
            return spec.id == self.local
        cfg = self.config
        if cfg.scenes != "all" and spec.id not in cfg.scenes:
            return False
        if spec.id in cfg.exclude or spec.overlays is False:
            return False
        return not (isinstance(spec.overlays, dict) and spec.overlays.get(self.id) is False)

    def override(self, spec: SceneConfig) -> dict[str, Any] | None:
        """The scene's overrides of this (video-level) entry, if any."""
        if self.local is None and isinstance(spec.overlays, dict):
            value = spec.overlays.get(self.id)
            if isinstance(value, dict):
                return value
        return None


def _default_ids(configs: Sequence[OverlayConfig]) -> list[str]:
    """``id`` or the type (``<type><n>``, 1-based, when several entries without an id share it)."""
    counts: dict[str, int] = {}
    for cfg in configs:
        if cfg.id is None:
            counts[cfg.type] = counts.get(cfg.type, 0) + 1
    seen: dict[str, int] = {}
    ids = []
    for cfg in configs:
        if cfg.id is not None:
            ids.append(cfg.id)
            continue
        seen[cfg.type] = seen.get(cfg.type, 0) + 1
        ids.append(cfg.type if counts[cfg.type] == 1 else f"{cfg.type}{seen[cfg.type]}")
    return ids


def overlay_entries(project: Project) -> tuple[list[OverlayEntry], list[Problem]]:
    """Every overlay of the config (video-level, then the scenes' own) with the structural
    problems found: unknown types, duplicate ids, unknown scene ids, misplaced keys."""
    from vidgen import registry

    config = project.config
    scene_ids = [s.id for s in config.scenes]
    problems: list[Problem] = []
    entries: list[OverlayEntry] = []

    def unknown_scene(where: str, sid: str) -> None:
        problems.append(Problem(where, f"unknown scene '{sid}' (scenes: {', '.join(scene_ids)})"))

    for i, (cfg, oid) in enumerate(zip(config.overlays, _default_ids(config.overlays))):
        where = f"overlays[{i}]"
        kind = registry.find_overlay(cfg.type)
        if kind is None:
            problems.append(Problem(f"{where}.type", registry.unknown_overlay_message(cfg.type)))
        for sid in [] if cfg.scenes == "all" else cfg.scenes:
            if sid not in scene_ids:
                unknown_scene(f"{where}.scenes", sid)
        for sid in cfg.exclude:
            if sid not in scene_ids:
                unknown_scene(f"{where}.exclude", sid)
        for key, value in (("from", cfg.from_), ("to", cfg.to)):
            if isinstance(value, str) and value not in scene_ids:
                unknown_scene(f"{where}.{key}", value)
        if isinstance(cfg.from_, float) and isinstance(cfg.to, float) and cfg.to <= cfg.from_:
            problems.append(Problem(f"{where}.to", f"must be after from ({cfg.to:g} <= {cfg.from_:g} s)"))
        if any(e.id == oid for e in entries):
            problems.append(Problem(f"{where}.id", f"two overlays are called '{oid}'; give them different ids"))
        entries.append(OverlayEntry(oid, where, cfg, kind))

    video_ids = {e.id for e in entries}
    for j, spec in enumerate(config.scenes):
        if not isinstance(spec.overlays, dict):
            continue
        for key, value in spec.overlays.items():
            where = f"scenes[{j}].overlays.{key}"
            if key in video_ids:
                if isinstance(value, dict):
                    bad = [k for k in value if k in OVERLAY_KEYS and k not in OVERLAY_OVERRIDE_KEYS]
                    if bad:
                        problems.append(
                            Problem(where, f"a scene can override options and {', '.join(OVERLAY_OVERRIDE_KEYS)} of an overlay, not {', '.join(bad)}")
                        )
                continue
            if not isinstance(value, dict) or "type" not in value:
                known = ", ".join(sorted(video_ids)) or "none"
                problems.append(
                    Problem(where, f"unknown overlay '{key}' (overlays: {known}); give it a type to add an overlay to this scene only")
                )
                continue
            bad = [k for k in value if k in ("id", "scenes", "exclude", "from", "to")]
            if bad:
                problems.append(Problem(where, f"an overlay of one scene has no {', '.join(bad)}"))
                continue
            try:
                cfg = OverlayConfig.model_validate({**value, "id": key})
            except ValidationError as exc:
                problems.extend(validation_problems(exc, ("scenes", j, "overlays", key), OverlayConfig, noun="key"))
                continue
            kind = registry.find_overlay(cfg.type)
            if kind is None:
                problems.append(Problem(f"{where}.type", registry.unknown_overlay_message(cfg.type)))
            entries.append(OverlayEntry(key, where, cfg, kind, local=spec.id))
    for entry in entries:
        entry.raw = entry.config.options
    return entries, problems


def _scene_options(entry: OverlayEntry, spec: SceneConfig, theme: Theme | None) -> tuple[OverlayConfig, OverlayOptions | None, list[Problem]]:
    """The entry's config with the scene's overrides, its validated options (``None`` when
    invalid) and the problems (locations relative to the entry or override)."""
    assert entry.kind is not None
    override = entry.override(spec)
    config = entry.config
    raw = dict(entry.raw)
    if override is not None:
        raw.update({k: v for k, v in override.items() if k not in OVERLAY_KEYS})
        if "reserve" in override:
            config = config.model_copy(update={"reserve": bool(override["reserve"])})
    try:
        options = entry.kind.cls.Options.model_validate(raw, context={"theme": theme})
    except ValidationError as exc:
        return config, None, validation_problems(exc, (), entry.kind.cls.Options, noun="option")
    return config, options, []


def _where(entry: OverlayEntry, spec: SceneConfig, index: int) -> str:
    """Where problems of the entry's options on scene ``index`` belong: its override, if the
    scene has one, else the entry."""
    return f"scenes[{index}].overlays.{entry.id}" if entry.override(spec) is not None else entry.location


def _validate_options(entry: OverlayEntry, raw: dict[str, Any], theme: Theme | None) -> tuple[OverlayOptions | None, list[Problem]]:
    assert entry.kind is not None
    try:
        return entry.kind.cls.Options.model_validate(raw, context={"theme": theme}), []
    except ValidationError as exc:
        return None, validation_problems(exc, (), entry.kind.cls.Options, noun="option")


def overlay_problems(project: Project, theme: Theme | None) -> list[Problem]:
    """Everything ``vidgen validate`` checks about overlays: entries (:func:`overlay_entries`),
    each type's options as written and with every scene's overrides, and the type's
    :meth:`Overlay.validate_project`."""
    entries, problems = overlay_entries(project)
    specs = list(project.config.scenes)

    def add(where: str, found: list[Problem]) -> None:
        for problem in found:
            problems.append(Problem(f"{where}.{problem.location}" if problem.location else where, problem.message))

    for entry in entries:
        if entry.kind is None:
            continue
        scenes = [s.id for s in specs if entry.selects(s)]
        options, found = _validate_options(entry, entry.raw, theme)
        add(entry.location, found)
        written = {(p.location, p.message) for p in found}
        if options is not None:
            add(entry.location, _type_checks(entry, options, project, scenes))
        for j, spec in enumerate(specs):
            override = entry.override(spec)
            if override is None or not entry.selects(spec):
                continue
            merged, found = _validate_options(entry, {**entry.raw, **{k: v for k, v in override.items() if k not in OVERLAY_KEYS}}, theme)
            where = f"scenes[{j}].overlays.{entry.id}"
            add(where, [p for p in found if (p.location, p.message) not in written])
            if merged is not None and merged != options:
                add(where, _type_checks(entry, merged, project, scenes))
    return problems


def _type_checks(entry: OverlayEntry, options: OverlayOptions, project: Project, scenes: Sequence[str]) -> list[Problem]:
    """The type's ``validate_project`` messages as problems (``"<option>: <text>"`` → location
    ``<option>``)."""
    assert entry.kind is not None
    where = f"validate_project of overlay type '{entry.kind.name}' ({entry.kind.origin})"
    try:
        result = entry.kind.cls.validate_project(options, project, tuple(scenes))
    except VidgenError as exc:
        return [Problem("", f"{where} failed: {exc}")]
    if not isinstance(result, list) or not all(isinstance(p, str) for p in result):
        return [Problem("", f"{where} must return a list of strings, got {result!r}")]
    out = []
    for message in result:
        head, sep, rest = message.partition(": ")
        out.append(Problem(head, rest) if sep and head.isidentifier() else Problem("", message))
    return out


def check_overlays(project: Project, theme: Theme | None) -> None:
    """Raise one :class:`VidgenError` listing every overlay problem (used before rendering)."""
    problems = overlay_problems(project, theme)
    if problems:
        lines = ["invalid overlays", *(f"  {p}" for p in problems)]
        raise VidgenError("\n".join(lines), problems=problems)


def scene_overlays(project: Project, spec: SceneConfig, theme: Theme, plan: VideoPlan) -> list[Overlay]:
    """The overlays drawn on scene ``spec``, built for rendering it (ordered by ``layer``, then
    config order). Raises :class:`VidgenError` for invalid overlays."""
    entries, problems = overlay_entries(project)
    if problems:
        check_overlays(project, theme)
    out: list[Overlay] = []
    context = OverlayContext(project, theme, plan, spec.id)
    specs = list(project.config.scenes)
    index = specs.index(spec)
    for entry in entries:
        if entry.kind is None or not entry.selects(spec):
            continue
        config, options, found = _scene_options(entry, spec, theme)
        if options is None:
            where = _where(entry, spec, index)
            lines = [f"scene '{spec.id}': invalid overlay '{entry.id}'", *(f"  {where}.{p}" for p in found)]
            raise VidgenError("\n".join(lines))
        span = (plan.resolve(config.from_, end=False) or 0.0, plan.resolve(config.to, end=True))
        overlay = entry.kind.cls(
            options,
            config,
            context,
            id=entry.id,
            scenes=[s.id for s in specs if entry.selects(s)],
            span=(span[0], math.inf if span[1] is None else span[1]),
        )
        if overlay.timed:
            start, end = overlay.interval()
            slot = context.scene
            # drawn until the cut: the next scene's overlays take over in a crossfade (§49)
            if end <= slot.start or start >= slot.cut or not overlay.shown_in(max(start, slot.start), min(end, slot.cut)):
                continue  # its time range does not reach this scene, or it is hidden all along
        out.append(overlay)
    return sorted(out, key=lambda o: o.layer)


def build_overlays(overlays: Sequence[Overlay]) -> list[Mobject | None]:
    """Each overlay's built mobject (same order as ``overlays``): those that :attr:`~Overlay.yields`
    are built last, knowing the boxes of the others that reserve room (:attr:`Overlay.clear_of`)."""
    mobjects: list[Mobject | None] = [None] * len(overlays)
    boxes: list[Region] = []
    for k, overlay in enumerate(overlays):
        if not overlay.yields:
            mob = mobjects[k] = overlay.build()
            box = mobject_region(mob) if overlay.reserves and mob is not None else None
            if box is not None:
                boxes.append(box)
    for k, overlay in enumerate(overlays):
        if overlay.yields:
            overlay.clear_of = list(boxes)
            mobjects[k] = overlay.build()
    return mobjects


# ----- reserved space ----------------------------------------------------------------------------


def avoid(area: Region, box: Region, gap: float = RESERVE_GAP) -> Region:
    """``area`` shrunk to stay clear of ``box`` (plus ``gap``): of the four cuts (above, below,
    left or right of the box) the one keeping the most area. ``area`` itself when they do not
    overlap."""
    if box.x1 + gap <= area.x0 or box.x0 - gap >= area.x1 or box.y1 + gap <= area.y0 or box.y0 - gap >= area.y1:
        return area
    cuts = [
        Region(area.x0, min(max(box.y1 + gap, area.y0), area.y1), area.x1, area.y1),   # above the box
        Region(area.x0, area.y0, area.x1, max(min(box.y0 - gap, area.y1), area.y0)),   # below it
        Region(min(max(box.x1 + gap, area.x0), area.x1), area.y0, area.x1, area.y1),   # right of it
        Region(area.x0, area.y0, max(min(box.x0 - gap, area.x1), area.x0), area.y1),   # left of it
    ]
    return max(cuts, key=lambda r: r.width * r.height)


def mobject_region(mobject: Mobject) -> Region | None:
    """The bounding box of ``mobject`` as a :class:`Region` (``None`` without points)."""
    if not mobject.get_family() or all(len(m.points) == 0 for m in mobject.get_family()):
        return None
    x0, y0 = mobject.get_corner(np.array([-1.0, -1.0, 0.0]))[:2]
    x1, y1 = mobject.get_corner(np.array([1.0, 1.0, 0.0]))[:2]
    return Region(float(x0), float(y0), float(x1), float(y1))
