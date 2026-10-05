"""Scene 6: horizontal bars of non-embedding parameters with the saving arrow (was S6Params)."""

from vidgen.api import *


class ParamRow(SceneParams):
    """One bar: label, value (millions), theme color, optional percentage shown after the value."""

    label: str
    value: float = Field(gt=0)
    color: ThemeColor = "base"
    percent: str = ""


@scene("kphi_params")
class KphiParams(NarratedScene):
    """One bar per beat (``rows[i]`` at beat ``i``); the last beat also draws the saving
    between the first and the last bar."""

    beat_count = 3

    class Params(SceneParams):
        title: str = "Non-embedding parameters"
        rows: list[ParamRow] = Field(min_length=3, max_length=3)
        unit: str = "M"
        saving: str = "−77% parameters"

    def construct(self) -> None:
        p = self.params
        title = T(p.title, 36, weight=BOLD).to_edge(UP, buff=0.6)
        x0, scale = -2.6, 7.3 / max(r.value for r in p.rows)
        bars, labels, vals = [], [], []
        for k, row in enumerate(p.rows):
            y = 1.3 * (1 - k)
            lab = T(row.label, 28, row.color).move_to([x0 - 0.35, y, 0], aligned_edge=RIGHT)
            bar = Rectangle(width=row.value * scale, height=0.7, stroke_width=0, fill_color=resolve_color(row.color),
                            fill_opacity=0.9)
            bar.move_to([x0, y, 0], aligned_edge=LEFT)
            txt = f"{row.value:g}{p.unit}" + (f"   ({row.percent})" if row.percent else "")
            val = T(txt, 28, weight=BOLD).next_to(bar, RIGHT, buff=0.25)
            bars.append(bar)
            labels.append(lab)
            vals.append(val)

        last = len(p.rows) - 1
        for k in range(len(p.rows)):
            with self.narrate(k) as d:
                if k == 0:
                    self.play(FadeIn(title), run_time=0.6)
                self.play(FadeIn(labels[k], shift=RIGHT * 0.2), run_time=0.5)
                self.play(GrowFromEdge(bars[k], LEFT), run_time=min(2.0, 0.35 * d))
                self.play(FadeIn(vals[k], shift=LEFT * 0.2), run_time=0.5)
                if k == last:
                    self.show_saving(bars[0], bars[last], p.saving)
        self.clear_all()

    def show_saving(self, big: Rectangle, small: Rectangle, text: str) -> None:
        """Dashed guides down from both bar ends, a double arrow between them and the label."""
        base_end = big.get_right()[0]
        small_end = small.get_right()[0]
        y = -2.35
        dim = resolve_color("dim")
        gap = DoubleArrow([small_end, y, 0], [base_end, y, 0], buff=0, color=resolve_color("highlight"),
                          stroke_width=4, tip_length=0.2)
        guide1 = DashedLine([base_end, big.get_bottom()[1], 0], [base_end, y, 0], color=dim, stroke_width=2)
        guide2 = DashedLine([small_end, small.get_bottom()[1], 0], [small_end, y, 0], color=dim, stroke_width=2)
        saved = T(text, 40, "highlight", weight=BOLD).next_to(gap, DOWN, buff=0.2)
        self.play(Create(guide1), Create(guide2), GrowFromCenter(gap), run_time=0.8)
        self.play(Write(saved), run_time=0.8)
