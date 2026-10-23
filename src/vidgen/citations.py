"""On-screen citations (DESIGN.md §95.14): a scene's ``references:`` and ``figure_credit:`` drawn
on top of it like an overlay, the way the video's ``citations:`` says — a footer line
(``[1] Label · [2] Label``), the numbers alone in a corner (``[1, 2]``), or the numbers and then
an end-of-scene card listing the references. Numbers are the video's (the description lists
the same ones); a beat's ``cite:`` shows only the references it cites while it plays.

Not a registered overlay type: :func:`citation_overlay` makes one for every scene with
references or a figure credit (``vidgen.overlays.scene_overlays`` adds it), so no ``overlays:``
entry is needed and scenes without references are untouched."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from manim import BOLD, DOWN, LEFT, Mobject, RoundedRectangle, VGroup

from vidgen.config import OverlayConfig
from vidgen.overlays import Overlay, OverlayOptions
from vidgen.references import beat_numbers, credit_text, marker, scene_numbers
from vidgen.regions import Region, orientation, place, readable_text, safe_area

#: Gap (units) between the citation's text and its plate's edge; the plate's opacity.
PAD, PLATE_OPACITY = 0.12, 0.88
#: Share of the safe area's height a footer may take before its text wraps no further.
FOOTER_HEIGHT = 0.16


class Citations(Overlay):
    """A scene's citations: built once per scene render, one look per state (the numbers shown,
    or the card), all made up front."""

    #: The end card lies over the scene on purpose (the footer and marker reserve their room).
    lint_skip = ("overlay_overlap",)

    def __init__(self, *args: Any, refs: list[tuple[int, str]], cites: dict[str, tuple[int, ...]], credit: str | None,
                 show: str, card_seconds: float, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.refs, self.cites, self.credit, self.show, self.card_seconds = refs, cites, credit, show, card_seconds
        self._looks: dict[Hashable, Mobject] = {}

    def default_reserve(self) -> bool:
        """The footer and the marker keep scene layouts clear of them (the card lies over the end)."""
        return True

    def window(self) -> tuple[float, float]:
        """Its own scene, until the cut."""
        slot = self.context.scene
        return slot.start, slot.cut

    # ----- states ----------------------------------------------------------------------------------

    def _numbers_at(self, scene_time: float) -> tuple[int, ...]:
        """The numbers shown at ``scene_time``: the current beat's cites, or all when no beat of
        the scene cites."""
        if not self.cites:
            return tuple(n for n, _ in self.refs)
        current = None
        for beat in self.context.scene.beats:
            if beat.start <= scene_time + 1e-6:
                current = beat.id
        return self.cites.get(current or "", ())

    def _card_from(self) -> float:
        slot = self.context.scene
        return slot.duration - min(self.card_seconds, slot.duration / 2)

    def state(self, t: float) -> Hashable | None:
        """``("card",)`` at the end of a card scene, else the numbers shown (``None``: nothing)."""
        scene_time = t - self.context.scene.start
        if self.show == "card" and self.refs and scene_time >= self._card_from():
            return ("card",)
        numbers = self._numbers_at(scene_time)
        if not numbers and self.credit is None:
            return None
        return ("numbers", numbers)

    def pose(self, mobject: Mobject, state: Hashable) -> Mobject:
        if state not in self._looks:
            self._looks[state] = self._look(state)
        return self._looks[state]

    # ----- looks --------------------------------------------------------------------------------------

    def _plate(self, content: Mobject) -> VGroup:
        plate = RoundedRectangle(width=content.width + 2 * PAD, height=content.height + 2 * PAD, corner_radius=0.06, stroke_width=0)
        plate.set_fill(self.context.theme.background, opacity=PLATE_OPACITY).move_to(content.get_center())
        return VGroup(plate, content)

    def _look(self, state: Hashable) -> Mobject:
        safe = safe_area()
        if state == ("card",):
            width = safe.width * (1.0 if orientation() == "portrait" else 0.62)
            lines = "\n".join(f"[{n}] {label}" for n, label in self.refs)
            head = readable_text("References", Region(0, 0, width, 1.0), size="caption", color="text", weight=BOLD, align="left")
            body = readable_text(lines, Region(0, 0, width, safe.height * 0.6), size="caption", color="text", align="left")
            group = self._plate(VGroup(head, body).arrange(DOWN, aligned_edge=LEFT, buff=0.12))
            place(group, safe, fit="none", align="bottom_right")
            return group
        numbers = state[1] if isinstance(state, tuple) and len(state) > 1 else ()
        shown = [(n, label) for n, label in self.refs if n in numbers]
        if self.show == "footer":
            parts = [f"[{n}] {label}" for n, label in shown] + ([self.credit] if self.credit else [])
            text = readable_text("  ·  ".join(parts), Region(0, 0, safe.width - 2 * PAD, safe.height * FOOTER_HEIGHT), size="caption", color="text")
            group = self._plate(text)
            place(group, safe, fit="none", align="bottom")
            return group
        parts = [marker(n for n, _ in shown)] if shown else []
        parts += [self.credit] if self.credit else []
        text = readable_text("  ".join(parts), Region(0, 0, safe.width * 0.6, safe.height * FOOTER_HEIGHT), size="caption", color="text",
                             align="right")
        group = self._plate(text)
        place(group, safe, fit="none", align="bottom_right")
        return group

    def build(self) -> Mobject:
        """The look with every reference (its box is what scenes keep clear of)."""
        return self._look(("numbers", tuple(n for n, _ in self.refs)))


def citation_overlay(project: Any, spec: Any, context: Any) -> Citations | None:
    """The citations of scene ``spec`` (``None`` without references or a figure credit, or with
    ``citations: {show: none}``)."""
    settings = project.config.citations
    if settings.show == "none" or not (spec.references or spec.figure_credit is not None):
        return None
    scenes = project.config.scenes
    numbers = scene_numbers(scenes, spec.id)
    refs = sorted({(n, ref.label) for n, ref in zip(numbers, spec.references)})
    credit = credit_text(spec.figure_credit) if spec.figure_credit is not None else None
    config = OverlayConfig(type="citations", id="citations", scenes=[spec.id])
    return Citations(OverlayOptions(), config, context, id="citations", scenes=[spec.id], refs=refs, cites=beat_numbers(scenes, spec.id),
                     credit=credit, show=settings.show, card_seconds=settings.card_seconds)
