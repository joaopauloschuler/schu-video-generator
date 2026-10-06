"""``stat``: one big number that counts up, with a label, a context line and a comparison."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

MINUS = "−"


def format_number(value: float, decimals: int, thousands: str = ",", decimal_mark: str = ".") -> str:
    """``value`` with ``decimals`` decimals, ``thousands`` between digit groups and
    ``decimal_mark`` before the decimals; negatives get a typographic minus
    (``format_number(-12345.6, 1, ".", ",")`` -> ``"−12.345,6"``)."""
    text = f"{abs(value):,.{decimals}f}"
    if round(abs(value), decimals) == 0:
        value = 0.0
    text = text.replace(",", "\0").replace(".", decimal_mark).replace("\0", thousands)
    return (MINUS if value < 0 else "") + text


def needed_decimals(values: list[float], most: int = 2) -> int:
    """How many decimals (up to ``most``) the values need to be shown exactly."""
    decimals = 0
    for v in values:
        text = f"{abs(float(v)):.{most}f}".rstrip("0")
        decimals = max(decimals, len(text.split(".")[1]) if "." in text else 0)
    return decimals


class StatComparison(SceneParams):
    """The value to compare with: ``{value, label?, kind?, ...}`` or just a number."""

    also_accepts = (float,)

    value: float
    """The other value (same prefix, suffix and unit as the stat)."""
    label: str = ""
    """Words after the other value, e.g. 'last year'."""
    kind: Literal["versus", "before"] = "versus"
    """versus: 'vs 12%'; before: the stat counts up from this value ('from 12%')."""
    word: str | None = None
    """Word before the other value; default 'vs' (versus) or 'from' (before); '' for none."""
    delta: Literal["difference", "percent", "none"] = "difference"
    """The change shown in a coloured chip with an arrow: the difference (+19%), the percent change (+158%), or none."""
    better: Literal["higher", "lower", "neither"] = "higher"
    """Which direction is good: colours the chip with good_color / bad_color (neither: neutral_color)."""

    @model_validator(mode="before")
    @classmethod
    def _from_number(cls, data: Any) -> Any:
        return {"value": data} if isinstance(data, (int, float)) and not isinstance(data, bool) else data

    @model_validator(mode="after")
    def _percent_of_zero(self) -> "StatComparison":
        if self.delta == "percent" and self.value == 0:
            raise ValueError("delta: percent needs a non-zero value (use delta: difference)")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        """A plain number is also a comparison (JSON Schema ``anyOf`` number | object)."""
        return {"anyOf": [{"type": "number"}, handler(core_schema)]}


@scene("stat")
class Stat(NarratedScene):
    """Beat 1 reveals the icon, the value (counting up) and the label; beat 2 the comparison and
    the context line (everything in beat 1 when there is only one); further beats hold.

    Action targets: ``icon``, ``value``, ``label``, ``comparison``, ``context`` (those present).
    """

    outro = 0.5
    target_patterns = ("icon", "value", "label", "comparison", "context")

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        """The parts the stat has, top to bottom."""
        present = {"icon": params.icon, "value": True, "label": params.label, "comparison": params.comparison, "context": params.context}
        return [name for name, there in present.items() if there]

    class Params(SceneParams):
        value: float
        """The number shown."""
        label: str = ""
        """What the number is, under it (e.g. 'of developers use AI tools')."""
        context: str = ""
        """A smaller line at the bottom: period, population, source."""
        prefix: str = ""
        """Before the number, same size (e.g. '$')."""
        suffix: str = ""
        """After the number, same size (e.g. '%', 'x', 'k')."""
        unit: str = ""
        """After the number, smaller, on its baseline (e.g. 'ms', 'users')."""
        decimals: int | None = Field(default=None, ge=0, le=6)
        """Decimals shown (also while counting); default: what value and comparison need, up to 2."""
        thousands: str = Field(default=",", max_length=2)
        """Thousands separator: ',', '.', ' ', \"'\" or '' for none."""
        decimal_mark: str = Field(default=".", min_length=1, max_length=1)
        """Decimal mark: '.' or ','."""
        count: bool = True
        """Count up to the value in beat 1; false: the value fades in."""
        count_from: float | None = None
        """Where the count starts; default 0, or the comparison value with kind: before."""
        comparison: StatComparison | None = None
        """Optional value to compare with: a number or {value, label, kind, word, delta, better}."""
        icon: IconName | None = None
        """Optional icon above the number."""
        icon_color: ThemeColor = "primary"
        """Icon color."""
        color: ThemeColor = "primary"
        """Color of the number (prefix, suffix and unit too)."""
        label_color: ThemeColor = "text"
        """Label color."""
        context_color: ThemeColor = "dim"
        """Context line color."""
        comparison_color: ThemeColor = "dim"
        """Color of the comparison text ('vs 12% last year')."""
        good_color: ThemeColor = "tertiary"
        """Change chip color when the change goes the better way."""
        bad_color: ThemeColor = "accent"
        """Change chip color when the change goes the worse way."""
        neutral_color: ThemeColor = "dim"
        """Change chip color for no change or better: neither."""
        size: ThemeSize | None = None
        """Number size; default 3x the theme's title size (shrunk to fit the frame)."""
        label_size: ThemeSize = "subtitle"
        """Label text size."""
        context_size: ThemeSize = "caption"
        """Context line text size."""
        comparison_size: ThemeSize = "body"
        """Comparison text size."""

        @model_validator(mode="after")
        def _separators(self) -> SceneParams:
            if self.thousands and self.thousands == self.decimal_mark:
                raise ValueError(f"thousands and decimal_mark are both {self.decimal_mark!r}")
            if any(c.isdigit() for c in self.thousands + self.decimal_mark):
                raise ValueError("thousands and decimal_mark cannot be digits")
            return self

    #: Default number size relative to the theme's ``title`` size.
    value_scale = 3.0
    #: Unit size relative to the number size.
    unit_ratio = 0.42
    #: Space above each part (Manim units; x ``portrait_growth`` in a vertical frame).
    gaps = {"value": 0.35, "label": 0.4, "comparison": 0.45, "context": 0.4}
    #: In a vertical frame the gaps grow by this factor (the frame has height to spare).
    portrait_growth = 1.3
    #: Height of the icon in Manim units (the frame's shorter side is 8).
    icon_height = 1.1
    #: Share of the count spent fading the number in.
    fade_share = 0.25

    # ----- formatting ----------------------------------------------------------------------------

    @property
    def decimals(self) -> int:
        """Decimals of every number shown (given, or what the values need)."""
        p = self.params
        if p.decimals is not None:
            return p.decimals
        values = [p.value] + ([p.comparison.value] if p.comparison else [])
        return needed_decimals(values)

    def number(self, value: float) -> str:
        """``value`` formatted with the scene's decimals and separators (no prefix/suffix)."""
        p = self.params
        return format_number(value, self.decimals, p.thousands, p.decimal_mark)

    def written(self, value: float) -> str:
        """``value`` as a line of text: prefix, number, suffix and unit (``$1,200 users``)."""
        p = self.params
        return f"{p.prefix}{self.number(value)}{p.suffix}" + (f" {p.unit}" if p.unit else "")

    def start_value(self) -> float:
        """Where the count starts."""
        p = self.params
        if p.count_from is not None:
            return p.count_from
        if p.comparison is not None and p.comparison.kind == "before":
            return p.comparison.value
        return 0.0

    def change(self) -> tuple[str, str, int]:
        """``(delta text, colour token, direction)`` of the comparison chip; direction is
        1 (up), -1 (down) or 0."""
        p = self.params
        c = p.comparison
        assert c is not None
        diff = round(p.value - c.value, 9)
        direction = (diff > 0) - (diff < 0)
        sign = "+" if direction > 0 else MINUS if direction < 0 else ""
        if c.delta == "percent":
            pct = abs(diff) / abs(c.value) * 100
            text = format_number(pct, 0 if pct >= 10 else 1, p.thousands, p.decimal_mark) + "%"
        else:
            text = f"{p.prefix}{self.number(abs(diff))}{p.suffix}" + (f" {p.unit}" if p.unit else "")
        good = {"higher": direction, "lower": -direction, "neither": 0}[c.better]
        color = p.good_color if good > 0 else p.bad_color if good < 0 else p.neutral_color
        return sign + text, color, direction

    # ----- building ------------------------------------------------------------------------------

    def value_line(self, value: float, size: float) -> VGroup:
        """The number line for ``value``: ``VGroup(text, unit?)``, the unit on the text's baseline."""
        p = self.params
        main = self.text(f"{p.prefix}{self.number(value)}{p.suffix}", size=size, color=p.color, weight=BOLD, role="heading")
        line = VGroup(main)
        if p.unit:
            unit = self.text(p.unit, size=size * self.unit_ratio, color=p.color, weight=BOLD, role="heading")
            unit.next_to(main, RIGHT, buff=size * 0.004)
            unit.shift(UP * (_baseline(main) - _baseline(unit)))
            line.add(unit)
        return line

    def comparison_row(self, width: float) -> VGroup:
        """The change chip (arrow and delta in a pill) and the 'vs 12% last year' text, side by
        side, or stacked when that is wider than ``width``."""
        p = self.params
        c = p.comparison
        assert c is not None
        size = float(self.theme.size(p.comparison_size))
        row = VGroup()
        if c.delta != "none":
            delta, token, direction = self.change()
            color = self.theme.color(token)
            text = self.text(delta, size=size, color=color, weight=BOLD)
            chip = VGroup(text)
            if direction:
                cap = self.text("H", size=size).height
                arrow = Triangle().set_fill(color, opacity=1).set_stroke(width=0).scale_to_fit_height(cap * 0.85)
                if direction < 0:
                    arrow.rotate(PI)
                arrow.next_to(text, LEFT, buff=cap * 0.45).set_y(text.get_y())
                chip = VGroup(arrow, text)
            pad = self.text("H", size=size).height
            pill = RoundedRectangle(width=chip.width + 1.6 * pad, height=chip.height + 1.1 * pad, corner_radius=(chip.height + 1.1 * pad) / 2)
            # on the theme's surface, not a tint of the colour: a tint costs the delta its contrast
            pill.set_fill(self.theme.color("surface"), opacity=1).set_stroke(color, width=2.5, opacity=0.7).move_to(chip)
            row.add(VGroup(pill, *chip))
        word = c.word if c.word is not None else ("vs" if c.kind == "versus" else "from")
        words = " ".join(w for w in (word, self.written(c.value), c.label) if w)
        row.add(fit_text(words, width, size=p.comparison_size, color=p.comparison_color))
        row.arrange(RIGHT, buff=0.3)
        if row.width > width:
            row.arrange(DOWN, buff=0.22)
        return row

    def construct(self) -> None:
        p = self.params
        area = self.safe_area
        width = area.width * (1.0 if self.is_portrait else 0.86)
        wanted = float(self.theme.size(p.size)) if p.size is not None else self.value_scale * float(self.theme.size("title"))
        start = self.start_value() if p.count else p.value
        widest = max((self.value_line(v, wanted) for v in (start, p.value)), key=lambda m: m.width)
        size = wanted * min(1.0, area.width * 0.92 / widest.width, area.height * 0.42 / widest.height)
        value = self.value_line(p.value, size)

        parts: list[tuple[str, Mobject]] = []
        if p.icon:
            parts.append(("icon", icon(p.icon, color=p.icon_color, height=self.icon_height, theme=self.theme)))
        parts.append(("value", value))
        if p.label:
            parts.append(("label", fit_text(p.label, width, area.height * 0.22, size=p.label_size, color=p.label_color)))
        if p.comparison is not None:
            parts.append(("comparison", self.comparison_row(width)))
        if p.context:
            parts.append(("context", fit_text(p.context, width, area.height * 0.14, size=p.context_size, color=p.context_color)))
        card = VGroup(*[m for _, m in parts])
        for (_, above), (name, below) in zip(parts, parts[1:]):
            below.next_to(above, DOWN, buff=self.gaps[name] * (self.portrait_growth if self.is_portrait else 1.0))
        natural = card.width
        place(card, area, max_scale=1.0)
        size *= card.width / natural if natural > 0 else 1.0
        final = value.copy()  # the layout shows the final value; the count starts elsewhere

        targets: dict[str, Target] = {}
        for name, mob in parts:
            entrance = {"icon": lambda m=mob: [FadeIn(m, scale=0.6)], "value": lambda: self._value_entrance(value, final, start, size)}.get(
                name, lambda m=mob: [FadeIn(m, shift=UP * 0.15)]
            )
            targets[name] = self.target(name, mob, entrance=entrance)
        if start != p.value:  # registered at full look; until its entrance it shows the start value
            self._show_value(value, self.value_line(start, size), final.get_top(), final.get_x())

        def lagged(names: list[str], lag: float) -> list[Animation]:  # entrance(): never twice
            anims = [AnimationGroup(*self.entrance(targets[n])) for n in names if n in targets and not self.is_shown(targets[n])]
            return [LaggedStart(*anims, lag_ratio=lag)] if anims else []

        steps: list = [lambda: lagged(["icon", "value", "label"], 0.25)]
        if "comparison" in targets or "context" in targets:
            steps.append(lambda: lagged(["comparison", "context"], 0.3))
        self.reveal(steps, fraction=0.75, cap=2.0)
        self.finish()

    # ----- the count -----------------------------------------------------------------------------

    @staticmethod
    def _show_value(line: VGroup, shown: VGroup, top: np.ndarray, x: float) -> None:
        """Make ``line`` look like ``shown`` (same top edge and centre ``x`` as the final value)."""
        shown.move_to(np.array([x, 0.0, 0.0]) + UP * (top[1] - shown.get_top()[1] + shown.get_y()))
        for part, new in zip(line, shown):
            part.become(new)
            part.original_text = new.original_text  # become() keeps the old string (layout dump)

    def _value_entrance(self, line: VGroup, final: VGroup, start: float, size: float) -> list[Animation]:
        """The number fading in while it counts from ``start`` to the final value (``final``, as
        laid out), easing out so the last digits settle; a plain fade when there is no count."""
        end = self.params.value
        if start == end:
            return [FadeIn(line, shift=UP * 0.15, scale=0.94)]
        top, x = final.get_top(), final.get_x()

        def count(m: Mobject, alpha: float) -> None:
            eased = rate_functions.ease_out_cubic(alpha)
            shown = final.copy() if alpha >= 1 else self.value_line(start + (end - start) * eased, size)
            self._show_value(m, shown, top + DOWN * 0.15 * (1 - eased), x)
            m.set_opacity(min(1.0, alpha / self.fade_share))

        return [UpdateFromAlphaFunc(line, count, rate_func=linear)]


def _baseline(line: Mobject) -> float:
    """Approximate baseline of a line of text: the median bottom of its glyphs."""
    glyphs = [g for g in line.submobjects if g.has_points()] or [line]
    return float(np.median([g.get_bottom()[1] for g in glyphs]))
