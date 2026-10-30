"""``card``: a cartoon title card (an episode title, "Later that day…", an end card)."""

import dataclasses
from typing import Any, Literal

import numpy as np

from vidgen.api import *

#: Seconds the text's bounce takes to settle (the pop of the effect symbols, DESIGN.md §69.40).
POP_RUN = 0.8
#: How much of the spring the pop uses (1: the symbols' 30 % overshoot; the text is wide, so less).
POP_STRENGTH = 0.5


@scene("card")
class Card(NarratedScene):
    """The card's colour fills the frame behind a burst of rays turning slowly, a double frame or
    nothing (``style``); the text pops in with a bounce, bold and outlined, and the subtitle
    rises under it. With two or more beats the subtitle comes in beat 2, else with the text (a
    silent card with ``duration`` works the same); further beats hold. ``sting`` plays a music
    sting as the text pops in.

    Action targets: ``text``, ``subtitle`` (when given), ``burst`` or ``frame`` (by style).
    """

    outro = 0.5
    takes_host = False   # a full-frame title card (DESIGN.md §71)
    target_patterns = ("text", "subtitle", "burst", "frame")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """``text``, ``subtitle`` (when given), ``burst`` / ``frame`` (by style)."""
        names = ["text"] + (["subtitle"] if params.subtitle else [])
        return names + ([params.style] if params.style != "plain" else [])

    class Params(SceneParams):
        text: TranslatableStr = Field(min_length=1)
        """The card's words: an episode title, "Later that day…", "The End" (wrapped to fit)."""
        subtitle: TranslatableStr = ""
        """A smaller line under the text."""
        style: Literal["burst", "frame", "plain"] = "burst"
        """burst: rays turning slowly behind the text; frame: a double frame round it; plain: the colour alone."""
        color: ThemeColor = "primary"
        """The card's colour (the burst's lighter rays are a tint of it)."""
        text_color: ThemeColor | None = None
        """Fill of the text; default white or the dark ink, whichever reads better on the card (the outline is the other)."""
        outline_color: ThemeColor | None = None
        """Outline of the text and the frame's lines; default the other of white and the dark ink."""
        spin: bool = True
        """burst only: the rays turn slowly while the card is on."""
        sting: StingSetting | None = None
        """A music sting as the text pops in: reveal, comic or sad, or {kind, gain} (a beat's own sting can come after its line instead)."""

        @field_validator("sting")
        @classmethod
        def _sting_at_start(cls, sting: StingCue | None) -> StingCue | None:
            if sting is not None and sting.at == "end":
                raise ValueError("a card's sting plays as the text pops in; for one after a line, give that beat a sting with at: end")
            return sting

    def construct(self) -> None:
        p = self.params
        width, height = float(config.frame_width), float(config.frame_height)
        layout = card_layout(width, height, style=p.style, subtitle=bool(p.subtitle))
        clear = self.safe_area if self.project.config.shorts_zones is not None else None
        if clear is not None:   # a Short: the words keep out of the app's buttons (DESIGN.md §101)
            room = clear.width
            layout = dataclasses.replace(layout, text_width=min(layout.text_width, room), subtitle_width=min(layout.subtitle_width, room))
        color = self.theme.color(p.color)
        light = burst_ray_color(color)
        fill, outline = card_text_inks(color, light) if p.style == "burst" else card_text_inks(color)
        fill = self.theme.color(p.text_color) if p.text_color is not None else fill
        outline = self.theme.color(p.outline_color) if p.outline_color is not None else outline

        self.add(Rectangle(width=width * 1.02, height=height * 1.02, stroke_width=0, fill_color=color, fill_opacity=1.0))
        backdrop = self._backdrop(layout, light, outline)

        size = 2.2 * float(self.theme.size("title"))
        text = self._outlined(fit_text(p.text, layout.text_width, layout.text_height, size=size, color=fill, weight=BOLD, role="heading"), outline)
        parts = VGroup(text)
        subtitle = None
        if p.subtitle:
            subtitle = self._outlined(
                fit_text(p.subtitle, layout.subtitle_width, layout.subtitle_height, size="subtitle", color=fill, weight=BOLD), outline
            )
            parts.add(subtitle)
        parts.arrange(DOWN, buff=layout.gap).move_to(ORIGIN if clear is None else np.array([clear.center[0], clear.center[1], 0.0]))

        steps: list = []
        own = self.target("text", text, entrance=lambda: [self._pop(text)])
        sub = self.target("subtitle", subtitle, entrance=lambda: [FadeIn(subtitle, shift=UP * 0.2)]) if subtitle is not None else None
        back = self.target(p.style, backdrop, entrance=lambda: [self._grow(backdrop)]) if backdrop is not None else None

        def first(with_subtitle: bool) -> list[Animation]:   # entrance(): never twice
            shown = [t for t in (back, own, sub if with_subtitle else None) if t is not None and not self.is_shown(t)]
            anims = [AnimationGroup(*self.entrance(t)) for t in shown]
            return [LaggedStart(*anims, lag_ratio=0.3)] if anims else []

        if sub is not None and len(self.beats) >= 2:
            steps = [lambda: first(False), lambda: self.entrance(sub)]
        else:
            steps = [lambda: first(True)]
        if p.sting is not None:
            self.sting(p.sting, 0.0)
        self.reveal(steps, fraction=0.75, cap=1.4)
        self.finish()

    def _backdrop(self, layout: CardLayout, light: str, ink: str) -> VMobject | None:
        """The burst (turning while ``spin``) or the double frame of the card's style."""
        p = self.params
        if p.style == "burst":
            burst = VGroup(*[Polygon(*[[x, y, 0.0] for x, y in ray], stroke_width=0, fill_color=light, fill_opacity=1.0)
                             for ray in burst_rays(layout.burst_radius)])
            if p.spin:
                burst.add_updater(lambda m, dt: m.rotate(BURST_SPIN * dt, about_point=ORIGIN))
            return burst
        if p.style == "frame" and layout.frame_outer is not None and layout.frame_inner is not None:
            short = min(layout.frame_inner)
            lines = VGroup(*[
                RoundedRectangle(width=w, height=h, corner_radius=0.08 * short, stroke_color=ink, stroke_width=width, fill_opacity=0.0)
                for (w, h), width in ((layout.frame_outer, 10.0), (layout.frame_inner, 4.0))
            ])
            return lines
        return None

    @staticmethod
    def _outlined(text: VMobject, ink: str) -> VGroup:
        """``text`` over a thick ``ink`` outline of its letters (scaled to their cap height). The
        outline is one layer of plain shapes behind every letter: a stroke per letter would cover
        the letter before it."""
        glyphs = text.family_members_with_points()
        cap = float(np.percentile([m.height for m in glyphs], 75)) if glyphs else text.height
        layer = VGroup(*[VMobject().set_points(m.points.copy()) for m in glyphs])
        layer.set_fill(ink, opacity=1.0).set_stroke(ink, width=card_outline_width(cap))
        return VGroup(layer, text)

    @staticmethod
    def _pop(mob: Mobject) -> Animation:
        """``mob`` grows in with a bounce (:func:`pop_scale`), exactly its size at the end."""
        start = mob.copy()

        def update(m: Mobject, alpha: float) -> None:
            scale = 1.0 if alpha >= 1.0 else max(pop_scale(alpha * POP_RUN, POP_STRENGTH), 1e-3)
            m.become(start.copy().scale(scale))

        return UpdateFromAlphaFunc(mob, update, run_time=POP_RUN, rate_func=linear)

    @staticmethod
    def _grow(mob: Mobject) -> Animation:
        """``mob`` grows from the middle of the frame. Not Manim's ``GrowFromCenter``: an
        introducer is added to the scene again as it starts, over the text that pops in with it."""
        start = mob.copy().clear_updaters()

        def update(m: Mobject, alpha: float) -> None:
            m.become(start.copy().scale(max(rate_functions.smooth(alpha), 1e-3), about_point=ORIGIN))

        return UpdateFromAlphaFunc(mob, update)
