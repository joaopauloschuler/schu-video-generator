"""Built-in overlays (DESIGN.md §41): ``lower_third`` and ``watermark``.

Overlays are drawn on top of the scenes, fixed to the screen (the scene's camera moves and fades
do not touch them); they are listed in the video's ``overlays:`` (docs/CONFIG.md "Overlays").
"""

from collections.abc import Hashable, Sequence
from typing import Any, Literal

from vidgen.api import *

from .image import check_image, load_image

#: In portrait the lower third sits this share of the safe height above the safe area's bottom
#: (phone apps put their own controls over the bottom of a vertical video).
PORTRAIT_LIFT = 0.12
#: How far (units) a lower third slides while it comes in and goes.
SLIDE = 0.5

Corner = Literal["top_left", "top_right", "bottom_left", "bottom_right"]
Placement = Literal["bottom_left", "bottom", "bottom_right", "top_left", "top", "top_right"]


@overlay("lower_third")
class LowerThird(Overlay):
    """A name and title on a plate in the lower third of the frame (the way a speaker or a place
    is introduced), sliding in at a moment of a scene and out after ``duration`` seconds.

    It belongs to a scene (``scene``, default the first scene the entry is drawn on) and starts
    ``at`` seconds into it or at one of its beats; it goes by the end of that scene unless
    ``across_cuts`` lets it run on over the next scenes. Placed in the safe area (raised a little
    in 9:16), at least the readable text size.
    """

    class Options(OverlayOptions):
        name: str = Field(min_length=1)
        """The main line (a person's or a place's name)."""
        title: str | None = None
        """The second line (role, affiliation, context)."""
        icon: IconName | None = None
        """An icon left of the text."""
        scene: str | None = None
        """The scene it belongs to (its time `at` is counted from that scene's start); default the first scene the overlay is drawn on."""
        at: float | str = 0.5
        """When it starts: seconds after its scene's start, or a beat id of that scene (the beat's start)."""
        duration: float = Field(5.0, gt=0)
        """Seconds it is shown, its slide in and out included."""
        across_cuts: bool = False
        """Keep it on over the following scenes until `duration` is over (default: it goes by the end of its scene)."""
        align: Placement = "bottom_left"
        """Where in the safe area: bottom_left, bottom, bottom_right, top_left, top, top_right."""
        max_width: float = Field(0.6, gt=0, le=1)
        """Widest it may be, as a share of the safe area's width (9:16: the whole width)."""
        color: ThemeColor = "primary"
        """Accent bar and icon colour."""
        background: ThemeColor = "surface"
        """Plate colour."""
        background_opacity: float = Field(0.92, ge=0, le=1)
        """Plate opacity."""
        name_color: ThemeColor = "text"
        """Name colour."""
        title_color: ThemeColor = "dim"
        """Title colour."""
        name_size: ThemeSize = "body"
        """Name size."""
        title_size: ThemeSize = "caption"
        """Title size."""
        enter: float = Field(0.5, ge=0)
        """Seconds of its slide in."""
        exit: float = Field(0.4, ge=0)
        """Seconds of its slide out."""

        @field_validator("at")
        @classmethod
        def _at(cls, value: float | str) -> float | str:
            if isinstance(value, str):
                if not value or not all(ch.isalnum() or ch == "_" for ch in value):
                    raise ValueError(f"at: a number of seconds or a beat id, got {value!r}")
            elif value < 0:
                raise ValueError("at must not be negative")
            return value

    @classmethod
    def validate_project(cls, options: Any, project: Any, scenes: Sequence[str]) -> list[str]:
        """``scene`` must be a scene the overlay is drawn on; ``at`` a beat of it."""
        ids = [s.id for s in project.config.scenes]
        if options.scene is not None and options.scene not in ids:
            return [f"scene: unknown scene '{options.scene}' (scenes: {', '.join(ids)})"]
        if options.scene is not None and options.scene not in scenes:
            return [f"scene: the overlay is not drawn on scene '{options.scene}' (see its scenes / exclude, or the scene's overlays)"]
        anchor = options.scene or (scenes[0] if scenes else None)
        if anchor is None or not isinstance(options.at, str):
            return []
        beats = [b.id for b in project.scene(anchor).beats]
        if options.at not in beats:
            return [f"at: scene '{anchor}' has no beat '{options.at}' (beats: {', '.join(beats) or 'none'})"]
        return []

    def window(self) -> tuple[float, float]:
        """From ``at`` in its scene for ``duration`` seconds (by the scene's end, unless
        ``across_cuts``)."""
        o = self.options
        anchor = o.scene or (self.scenes[0] if self.scenes else self.context.scene_id)
        slot = self.context.plan.scene(anchor)
        at = next((b.start for b in slot.beats if b.id == o.at), 0.0) if isinstance(o.at, str) else float(o.at)
        start = slot.start + at
        end = start + o.duration
        return start, end if o.across_cuts else min(end, slot.end)

    def build(self) -> Mobject:
        o = self.options
        safe = safe_area()
        portrait = orientation() == "portrait"
        area = Region(safe.x0, safe.y0 + PORTRAIT_LIFT * safe.height, safe.x1, safe.y1) if portrait else safe
        pad_x, pad_y, bar_w, gap = 0.3, 0.2, 0.09, 0.25
        width = area.width * (1.0 if portrait else o.max_width) - 2 * pad_x - bar_w
        lines = [readable_text(o.name, Region(0, 0, width, 2.0), size=o.name_size, color=o.name_color, weight=BOLD, align="left", role="heading")]
        if o.title:
            lines.append(readable_text(o.title, Region(0, 0, width, 1.6), size=o.title_size, color=o.title_color, align="left"))
        block = VGroup(*lines).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        parts: list[Mobject] = [block]
        if o.icon:
            mark = icon(o.icon, color=o.color, height=min(max(block.height, 0.45), 0.9))
            parts.insert(0, mark)
            if block.width + mark.width + gap > width:
                block.scale_to_fit_width(max(width - mark.width - gap, 0.5))
        content = VGroup(*parts).arrange(RIGHT, buff=gap)
        plate = Rectangle(width=content.width + 2 * pad_x + bar_w, height=content.height + 2 * pad_y)
        plate.set_fill(resolve_color(o.background), opacity=o.background_opacity).set_stroke(width=0)
        bar = Rectangle(width=bar_w, height=plate.height).set_fill(resolve_color(o.color), opacity=1).set_stroke(width=0)
        right = "right" in o.align
        bar.align_to(plate, RIGHT if right else LEFT)
        content.move_to(plate).shift((LEFT if right else RIGHT) * bar_w / 2)
        group = VGroup(plate, bar, content)
        place(group, area, fit="none", align=o.align)
        return group

    def state(self, t: float) -> Hashable | None:
        """Progress of the slide (0..1, 1 while fully in)."""
        start, end = self.interval()
        p = self.transition(t, start, end, self.options.enter, self.options.exit)
        return round(p, 3) if p > 0 else None

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        p = float(state)  # type: ignore[arg-type]
        if p >= 1:
            return mobject
        align = self.options.align
        direction = LEFT if "left" in align else RIGHT if "right" in align else DOWN if align == "bottom" else UP
        return with_opacity(mobject, p).shift(direction * (1 - p) * SLIDE)

    def settled(self, state: Hashable) -> bool:
        """Fully in (not sliding)."""
        return float(state) >= 1  # type: ignore[arg-type]


@overlay("watermark")
class Watermark(Overlay):
    """A logo (an image from the project's assets), an icon or a short text in a corner of the
    frame, faint and fixed, over the whole video or the part ``scenes`` / ``from`` / ``to`` give.

    It sits in the frame's margin (``inset`` from the edges), so scene layouts need not avoid it;
    it is faint on purpose, so lint does not check its contrast.
    """

    lint_skip = ("contrast",)

    class Options(OverlayOptions):
        image: str | None = None
        """Image file relative to the project (e.g. assets/logo.png)."""
        text: str | None = None
        """A short text instead of an image."""
        icon: IconName | None = None
        """An icon instead of an image."""
        corner: Corner = "bottom_right"
        """top_left, top_right, bottom_left or bottom_right."""
        opacity: float = Field(0.6, gt=0, le=1)
        """Opacity of the whole watermark."""
        size: float = Field(0.06, gt=0, le=0.5)
        """Height of an image or icon, as a share of the frame's shorter side."""
        text_size: ThemeSize = "caption"
        """Size of a text watermark."""
        color: ThemeColor = "text"
        """Colour of a text or icon watermark."""
        inset: float = Field(0.025, ge=0, le=0.3)
        """Distance from the frame's edges, as a share of the frame's shorter side."""
        fade: float = Field(0.0, ge=0)
        """Seconds it fades in / out where `from` / `to` start and end it (0: no fade)."""

        @model_validator(mode="after")
        def _one_source(self) -> "Watermark.Options":
            given = [name for name in ("image", "text", "icon") if getattr(self, name)]
            if len(given) != 1:
                raise ValueError(f"give exactly one of image, text, icon (got {', '.join(given) or 'none'})")
            return self

    @classmethod
    def validate_project(cls, options: Any, project: Any, scenes: Sequence[str]) -> list[str]:
        """The image file must exist and be a supported picture."""
        return check_image(project, options.image, "image") if options.image else []

    def build(self) -> Mobject:
        o = self.options
        short = min(config.frame_width, config.frame_height)
        if o.image:
            mark: Mobject = load_image(self.context.project.asset(o.image))
            mark.scale_to_fit_height(o.size * short)
            if mark.width > 0.3 * config.frame_width:
                mark.scale_to_fit_width(0.3 * config.frame_width)
        elif o.icon:
            mark = icon(o.icon, color=o.color, height=o.size * short)
        else:
            mark = T(o.text or "", o.text_size, o.color)
        mark = with_opacity(mark, o.opacity)
        place(mark, frame_region().inset(o.inset * short, o.inset * short), fit="none", align=o.corner)
        return mark

    def state(self, t: float) -> Hashable | None:
        """Its fade (0..1) near a bounded ``from`` / ``to``; else always ``on``."""
        fade = self.options.fade
        start, end = self.span
        if fade <= 0 or (start <= 0 and end == float("inf")):
            return "on"
        p = self.transition(t, start, end, fade if start > 0 else 0.0, fade if end != float("inf") else 0.0)
        return round(p, 3) if p > 0 else None

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        if self.settled(state):
            return mobject
        return with_opacity(mobject, float(state))  # type: ignore[arg-type]

    def settled(self, state: Hashable) -> bool:
        """Not fading."""
        return state == "on" or float(state) >= 1  # type: ignore[arg-type]
