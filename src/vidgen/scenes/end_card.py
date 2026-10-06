"""``end_card``: closing message, follow-up lines (links, credits), an optional logo and icon."""

from typing import Any

from vidgen.api import *
from .image import check_image, load_image


@scene("end_card")
class EndCard(NarratedScene):
    """Beat 1 reveals the logo, icon and title, beat 2 the lines (both in beat 1 if there is only
    one); further beats hold. The scene ends with a slower fade-out.

    Action targets: ``logo``, ``icon``, ``title``, ``line<N>`` (1-based; those present).
    """

    outro = 1.0
    target_patterns = ("logo", "icon", "title", "line<N>")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """The parts the card has: ``logo``, ``icon``, ``title``, ``line<N>``."""
        names = [n for n, there in (("logo", params.logo), ("icon", params.icon), ("title", params.title)) if there]
        return names + [f"line{k}" for k in range(1, len(params.lines) + 1)]
    #: Height of the icon in Manim units (the frame's shorter side is 8).
    icon_height = 1.1

    class Params(SceneParams):
        header_synonyms = False   # "title" is the main text here, not a header band
        title: str = ""
        """Closing message; at least one of title, lines, logo, icon."""
        lines: list[str] = []
        """Links, credits; short lines shrink together instead of wrapping."""
        logo: str | None = None
        """Image file in the project."""
        icon: IconName | None = None
        """Icon above the title (below the logo, if both)."""
        icon_color: ThemeColor = "primary"
        """Icon color."""
        title_color: ThemeColor = "highlight"
        """Title color."""
        color: ThemeColor = "text"
        """Lines color."""
        title_size: ThemeSize = "title"
        """Title text size."""
        size: ThemeSize = "body"
        """Lines text size."""

        @model_validator(mode="after")
        def _something(self) -> SceneParams:
            if not (self.title or self.lines or self.logo or self.icon):
                raise ValueError("give at least one of title, lines, logo or icon")
            return self

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        return problems + (check_image(project, params.logo, "logo") if params.logo else [])

    def construct(self) -> None:
        p = self.params
        width = self.safe_width * (1.0 if self.is_portrait else 0.86)
        head = Group()
        names: list[str] = []
        if p.logo:
            problems = check_image(self.project, p.logo, "logo")
            if problems:
                raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
            logo = load_image(self.project.asset(p.logo))
            shrink_to_fit(logo.scale_to_fit_height(self.safe_height * 0.2), width, None)
            head.add(logo)
            names.append("logo")
        if p.icon:
            head.add(icon(p.icon, color=p.icon_color, height=self.icon_height, theme=self.theme))
            names.append("icon")
        if p.title:
            names.append("title")
            head.add(fit_text(p.title, width, self.safe_height * 0.35, size=p.title_size, color=p.title_color, weight=BOLD, font=self.theme.font_for("heading")))
        head.arrange(DOWN, buff=0.45)
        rows = self._lines(width)
        rows.arrange(DOWN, buff=0.28)
        card = Group(*[g for g in (head, rows) if len(g)]).arrange(DOWN, buff=0.85)
        shrink_to_fit(card, self.safe_width, self.safe_height).move_to(ORIGIN)

        heads = [self.target(name, m, entrance=lambda m=m: [FadeIn(m, shift=UP * 0.15)]) for name, m in zip(names, head)]
        lines = [self.target(f"line{k}", m, entrance=lambda m=m: [FadeIn(m, shift=UP * 0.15)]) for k, m in enumerate(rows, start=1)]

        def lagged(targets: list[Target], lag: float) -> list[Animation]:  # entrance(): never twice
            anims = [AnimationGroup(*self.entrance(t)) for t in targets if not self.is_shown(t)]
            return [LaggedStart(*anims, lag_ratio=lag)] if anims else []

        steps: list = []
        if heads:
            steps.append(lambda: lagged(heads, 0.3))
        if lines:
            steps.append(lambda: lagged(lines, 0.3))
        self.reveal(steps, fraction=0.65, cap=1.4)
        self.finish()

    def _lines(self, width: float) -> VGroup:
        """One row per line. Short lines (links) are scaled down together instead of wrapping,
        so they keep one common size; long ones wrap."""
        p = self.params
        natural = [self.text(normalize_text(line), size=p.size, color=p.color) for line in p.lines]
        widest = max((m.width for m in natural), default=0.0)
        if widest <= width * 1.35:
            rows = VGroup(*natural)
            if widest > width:
                for m in natural:
                    m.scale(width / widest)
            return rows
        return VGroup(*[fit_text(line, width, size=p.size, color=p.color) for line in p.lines])
