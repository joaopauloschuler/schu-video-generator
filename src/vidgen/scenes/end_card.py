"""``end_card``: closing message, follow-up lines (links, credits) and an optional logo."""

from typing import Any

from vidgen.api import *
from .image import check_image, load_image


@scene("end_card")
class EndCard(NarratedScene):
    """Beat 1 reveals the logo and title, beat 2 the lines (both in beat 1 if there is only
    one); further beats hold. The scene ends with a slower fade-out.
    """

    outro = 1.0

    class Params(SceneParams):
        title: str = ""
        """Closing message; at least one of title, lines, logo."""
        lines: list[str] = []
        """Links, credits; short lines shrink together instead of wrapping."""
        logo: str | None = None
        """Image file in the project."""
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
            if not (self.title or self.lines or self.logo):
                raise ValueError("give at least one of title, lines or logo")
            return self

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        problems = super().validate_project(params, project)
        return problems + (check_image(project, params.logo, "logo") if params.logo else [])

    def construct(self) -> None:
        p = self.params
        width = self.safe_width * (1.0 if self.is_portrait else 0.86)
        head = Group()
        if p.logo:
            problems = check_image(self.project, p.logo, "logo")
            if problems:
                raise VidgenError(f"scene '{self.spec.id}': {problems[0]}")
            logo = load_image(self.project.asset(p.logo))
            shrink_to_fit(logo.scale_to_fit_height(self.safe_height * 0.2), width, None)
            head.add(logo)
        if p.title:
            head.add(fit_text(p.title, width, self.safe_height * 0.35, size=p.title_size, color=p.title_color, weight=BOLD, font=self.theme.font_for("heading")))
        head.arrange(DOWN, buff=0.45)
        rows = self._lines(width)
        rows.arrange(DOWN, buff=0.28)
        card = Group(*[g for g in (head, rows) if len(g)]).arrange(DOWN, buff=0.85)
        shrink_to_fit(card, self.safe_width, self.safe_height).move_to(ORIGIN)

        steps: list = []
        if len(head):
            steps.append(LaggedStart(*[FadeIn(m, shift=UP * 0.15) for m in head], lag_ratio=0.3))
        if len(rows):
            steps.append(FadeIn(rows, shift=UP * 0.15, lag_ratio=0.3))
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
