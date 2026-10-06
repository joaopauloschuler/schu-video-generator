"""``chapter``: a section divider with an optional number, a title, a subtitle and an icon."""

from typing import Any

from vidgen.api import *


@scene("chapter")
class Chapter(NarratedScene):
    """An accent rule draws in, the number (and icon) and the title slide in from either side of
    it, then the subtitle rises. In a wide frame with a number or icon they stand left of a
    vertical rule and the title right of it; otherwise everything is stacked and centred.

    With two or more beats the subtitle comes in beat 2, else everything in beat 1 (a silent
    scene with ``duration`` works the same); further beats hold. The chapter's name is the
    ``title`` param.

    Action targets: ``icon``, ``number``, ``title``, ``subtitle`` (those present).
    """

    outro = 0.5
    target_patterns = ("icon", "number", "title", "subtitle")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """The parts the card has: ``icon``, ``number``, ``title``, ``subtitle``."""
        present = {"icon": params.icon, "number": params.number_text() is not None, "title": True, "subtitle": params.subtitle}
        return [name for name, there in present.items() if there]

    class Params(SceneParams):
        title: str = Field(min_length=1)
        """The chapter's name (wrapped to fit)."""
        number: int | str | None = None
        """Chapter number: an integer (shown with number_format, e.g. 02) or text such as 'II' or 'Part 2'."""
        number_format: str = "{:02d}"
        """Python format for an integer number: '{:02d}' gives 02, '{}' gives 2, 'Part {}' gives Part 2."""
        subtitle: str = ""
        """Line under the title."""
        icon: IconName | None = None
        """Optional icon (above the number, or in its place)."""
        rule: bool = True
        """Draw the accent rule between number and title."""
        number_color: ThemeColor = "primary"
        """Number color."""
        rule_color: ThemeColor = "primary"
        """Rule color."""
        icon_color: ThemeColor = "primary"
        """Icon color."""
        title_color: ThemeColor = "text"
        """Title color."""
        subtitle_color: ThemeColor = "dim"
        """Subtitle color."""
        number_size: ThemeSize | None = None
        """Number size; default 2.4x the theme's title size (1.6x for text such as 'Part 2')."""
        title_size: ThemeSize = "title"
        """Title text size."""
        subtitle_size: ThemeSize = "subtitle"
        """Subtitle text size."""

        @field_validator("number_format")
        @classmethod
        def _format(cls, fmt: str) -> str:
            try:
                fmt.format(7)
            except (ValueError, IndexError, KeyError) as exc:
                raise ValueError(f"invalid number format {fmt!r}: {exc}") from None
            return fmt

        def number_text(self) -> str | None:
            """The number as shown, or ``None``."""
            if self.number is None or isinstance(self.number, str):
                return self.number or None
            return self.number_format.format(self.number)

    #: Height of the icon in Manim units (the frame's shorter side is 8).
    icon_height = 1.1
    #: Gap between the left column, the rule and the title block in the side-by-side layout.
    side_gap = 0.55
    #: Length of the rule in the stacked layout (Manim units).
    rule_length = 1.6

    def construct(self) -> None:
        p = self.params
        area = self.safe_area
        number = p.number_text()
        side = not self.is_portrait and (number is not None or p.icon is not None)
        left = VGroup()
        mark = icon(p.icon, color=p.icon_color, height=self.icon_height, theme=self.theme) if p.icon else None
        if mark is not None:
            left.add(mark)
        numeral = None
        if number is not None:
            scale = 2.4 if isinstance(p.number, int) else 1.6
            size = float(self.theme.size(p.number_size)) if p.number_size is not None else scale * float(self.theme.size("title"))
            limit = area.width * (0.36 if side else 1.0)
            numeral = fit_text(number, limit, area.height * 0.3, size=size, color=p.number_color, weight=BOLD, role="heading")
            left.add(numeral)
        left.arrange(DOWN, buff=0.3)

        width = area.width * (1.0 if self.is_portrait else 0.86)
        if side:
            width -= left.width + 2 * self.side_gap
        align = "left" if side else "center"
        title = fit_text(
            p.title, width, area.height * 0.4, size=p.title_size, color=p.title_color, weight=BOLD, role="heading", align=align
        )
        text = VGroup(title)
        subtitle = None
        if p.subtitle:
            subtitle = fit_text(p.subtitle, width, area.height * 0.2, size=p.subtitle_size, color=p.subtitle_color, align=align)
            text.add(subtitle)
        text.arrange(DOWN, buff=0.3, aligned_edge=LEFT if side else ORIGIN)

        color = self.theme.color(p.rule_color)
        if side:
            height = max(left.height, text.height) + 0.3
            rule = Line(UP * height / 2, DOWN * height / 2, color=color, stroke_width=5)
            card = VGroup(left, rule, text).arrange(RIGHT, buff=self.side_gap)
            out, back = LEFT, RIGHT  # the number slides in from the left, the title from the right
            # (without rule: an unseen spacer, never added to the scene)
        else:
            rule = Line(LEFT * self.rule_length / 2, RIGHT * self.rule_length / 2, color=color, stroke_width=5)
            stack = ([left] if len(left) else []) + ([rule] if p.rule else []) + [text]
            card = VGroup(*stack).arrange(DOWN, buff=0.4)
            out, back = UP, DOWN  # the number comes down to the rule, the title up to it
        place(card, area, max_scale=1.0)

        shift = 0.35
        head: list[Target] = []
        if mark is not None:
            head.append(self.target("icon", mark, entrance=lambda: [FadeIn(mark, shift=-out * shift, scale=0.8)]))
        if numeral is not None:
            head.append(self.target("number", numeral, entrance=lambda: [FadeIn(numeral, shift=-out * shift)]))
        head.append(self.target("title", title, entrance=lambda: [FadeIn(title, shift=-back * shift)]))
        sub = self.target("subtitle", subtitle, entrance=lambda: [FadeIn(subtitle, shift=UP * 0.15)]) if subtitle is not None else None

        def reveal_head(with_subtitle: bool) -> list[Animation]:  # entrance(): never twice
            parts = [t for t in head + ([sub] if with_subtitle and sub is not None else []) if not self.is_shown(t)]
            anims = [AnimationGroup(*self.entrance(t)) for t in parts]
            lines = [GrowFromCenter(rule) if not side else Create(rule)] if p.rule and rule not in self.mobjects else []
            return [LaggedStart(*lines, *anims, lag_ratio=0.25)] if lines or anims else []

        if sub is not None and len(self.beats) >= 2:
            steps: list = [lambda: reveal_head(False), lambda: self.entrance(sub)]
        else:
            steps = [lambda: reveal_head(True)]
        self.reveal(steps, fraction=0.75, cap=1.6)
        self.finish()
