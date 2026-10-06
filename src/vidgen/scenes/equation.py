"""``equation``: a LaTeX formula, or a sequence of steps morphing one into the next.

Needs LaTeX (``latex`` and ``dvisvgm`` on PATH; MiKTeX on Windows). ``vidgen validate`` warns
when it is missing; rendering fails with an explanation.
"""

import logging
from typing import Any

from vidgen.api import *

log = logging.getLogger("vidgen.scenes.equation")


@scene("equation")
class Equation(NarratedScene):
    """Step *i* of ``latex`` (a string is one step) appears at beat *i*, each morphing into the
    next; with more steps than beats they are spread evenly. The caption appears with step 1.
    """

    outro = 0.5
    #: In a vertical frame the formulas grow by this factor (they are still fitted to the width).
    portrait_growth = 1.25

    class Params(SceneParams):
        latex: str | list[str]
        """Math-mode LaTeX (no $); a list is a sequence of steps, step i at beat i."""
        caption: str = ""
        """Caption under the formula."""
        size: ThemeSize = 96
        """Formula size."""
        color: ThemeColor = "text"
        """Formula color."""
        caption_color: ThemeColor = "dim"
        """Caption color."""
        caption_size: ThemeSize = "caption"
        """Caption text size."""

        @field_validator("latex")
        @classmethod
        def _not_empty(cls, v: str | list[str]) -> str | list[str]:
            steps = [v] if isinstance(v, str) else v
            if not steps or any(not s.strip() for s in steps):
                raise ValueError("latex must be a non-empty string or a list of non-empty strings")
            return v

        def steps(self) -> list[str]:
            """The LaTeX steps as a list."""
            return [self.latex] if isinstance(self.latex, str) else list(self.latex)

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        if not latex_available():
            log.warning("equation scenes need LaTeX, which was not found on PATH; rendering them will fail")
        return super().validate_project(params, project)

    def construct(self) -> None:
        p = self.params
        require_latex(f"scene '{self.spec.id}' (type equation)")
        area = self.safe_area
        size = float(self.theme.size(p.size)) * (self.portrait_growth if self.is_portrait else 1.0)
        caption = None
        if p.caption:
            caption = fit_text(p.caption, area.width, area.height * 0.2, size=p.caption_size, color=p.caption_color)
        room = area.height * 0.6
        formulas = [shrink_to_fit(self._tex(s, size), area.width, room) for s in p.steps()]
        tallest = max(f.height for f in formulas)
        # formulas share one centre line; formula box + caption are centred in the safe area
        y = area.center[1] + ((caption.height + 0.7) / 2 if caption is not None else 0.0)
        for f in formulas:
            f.move_to([area.center[0], y, 0])
        if caption is not None:
            caption.move_to([area.center[0], y - tallest / 2 - 0.7 - caption.height / 2, 0])

        def first() -> list[Animation]:
            anims: list[Animation] = [Write(formulas[0])]
            if caption is not None:
                anims.append(FadeIn(caption, shift=UP * 0.12))
            return anims

        steps: list = [first]
        steps += [(lambda i=i: TransformMatchingShapes(formulas[i - 1], formulas[i])) for i in range(1, len(formulas))]
        self.reveal(steps, fraction=0.6, cap=1.6)
        self.finish()

    def _tex(self, latex: str, size: float) -> MathTex:
        try:
            return MathTex(latex, font_size=size, color=resolve_color(self.params.color, self.theme))
        except Exception as exc:  # Manim raises plain exceptions for LaTeX errors
            detail = str(exc).strip().splitlines()
            raise VidgenError(
                f"scene '{self.spec.id}': LaTeX could not compile {latex!r}"
                + (f": {detail[0]}" if detail else "")
                + " (check the formula; it is typeset in a LaTeX math environment)"
            ) from None
