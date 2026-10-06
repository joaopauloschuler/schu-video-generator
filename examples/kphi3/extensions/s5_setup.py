"""Scene 5: experimental setup - model, dataset, kphi-3, hardware (was S5Setup)."""

from vidgen.api import *

from .common import GOLD_FILL, decoder_layer


@scene("kphi_setup")
class KphiSetup(NarratedScene):
    """Beat 1: phi-3 baseline. Beat 2: dataset counter and filtered phrases. Beat 3: dense
    layers become grouped subnetworks. Beat 4: one GPU and the training blocks filling up."""

    beat_count = 4

    class Params(SceneParams):
        pairs_before: float = 2.58
        pairs_after: float = 2.52
        filtered: list[str] = Field(default=["“I am an AI”", "“I cannot”", "“I do not”", "“I don't have”"],
                                    min_length=4, max_length=4)
        channels_per_group: int = 256
        gpu: str = "L4"
        blocks: int = Field(57, ge=1, le=80)
        days: str = "≈ 3 days"

    def construct(self) -> None:
        p = self.params
        # --- model (left)
        src = VGroup(T("Microsoft", 20, "dim"), T("phi-3-mini-4k-instruct", 28, weight=BOLD)
                     ).arrange(DOWN, buff=0.08).move_to([-3.6, 2.9, 0])
        l1 = decoder_layer(1).move_to([-3.6, 1.15, 0])
        l2 = decoder_layer(1).move_to([-3.6, -0.05, 0])
        arrow = Arrow(src.get_bottom(), l1.get_top(), buff=0.1, color=resolve_color("dim"), stroke_width=3)
        name = T("phi-3 baseline", 28, "base", weight=BOLD).move_to([-3.6, -1.05, 0])
        sub = T("2 decoder layers · trained from scratch", 22, "dim").next_to(name, DOWN, buff=0.12)

        with self.narrate(0):
            self.play(FadeIn(src, shift=DOWN * 0.2), run_time=0.8)
            self.play(GrowArrow(arrow), run_time=0.5)
            self.play(FadeIn(l1, shift=UP * 0.2), FadeIn(l2, shift=UP * 0.2), run_time=1.0)
            self.play(FadeIn(name), FadeIn(sub), run_time=0.8)

        # --- data (right)
        ds = VGroup(T("LaMini dataset", 28, weight=BOLD), T("instruction → response pairs", 22, "dim")
                    ).arrange(DOWN, buff=0.08).move_to([3.5, 2.9, 0])
        cnt = ValueTracker(p.pairs_before)
        num = counter(cnt, "{:.2f} M", size=56, weight=BOLD, anchor=[3.5, 1.65, 0])
        bads = VGroup(*[T(b, 22, "accent") for b in p.filtered]).arrange_in_grid(2, 2, buff=(0.5, 0.25)
                                                                                ).move_to([3.5, 0.45, 0])
        strikes = VGroup(*[Line(b.get_left(), b.get_right(), color=resolve_color("accent"), stroke_width=3) for b in bads])
        filt = T("filtered out", 20, "dim").next_to(bads, DOWN, buff=0.18)

        with self.narrate(1) as d:
            self.play(FadeIn(ds, shift=DOWN * 0.2), FadeIn(num), run_time=1.0)
            self.play(FadeIn(bads, lag_ratio=0.25), run_time=1.4)
            self.play(Create(strikes, lag_ratio=0.25), FadeIn(filt), cnt.animate.set_value(p.pairs_after),
                      run_time=0.35 * d)

        # --- kphi-3
        k1 = decoder_layer(2).move_to(l1)
        k2 = decoder_layer(2).move_to(l2)
        kname = T("kphi-3", 28, "k3", weight=BOLD).move_to(name)
        ksub = VGroup(T("every dense layer → grouped subnetwork", 20, "dim"),
                      T(f"{p.channels_per_group} channels per group", 20, "dim")
                      ).arrange(DOWN, buff=0.06).next_to(kname, DOWN, buff=0.12)

        with self.narrate(2):
            self.play(Indicate(VGroup(l1[3], l1[4], l2[3], l2[4]), color=resolve_color("highlight")), run_time=1.0)
            self.play(Transform(l1, k1), Transform(l2, k2), Transform(name, kname), Transform(sub, ksub),
                      run_time=1.5)

        # --- hardware
        gold = resolve_color("highlight")
        chip = RoundedRectangle(width=1.2, height=0.9, corner_radius=0.08, stroke_color=gold,
                                fill_color=GOLD_FILL, fill_opacity=1)
        pins = VGroup(*[Line(UP * 0.0, UP * 0.15, color=gold, stroke_width=2).move_to(
            chip.get_top() + RIGHT * (x - 0.4) + UP * 0.075) for x in np.linspace(0, 0.8, 6)])
        pins2 = pins.copy().move_to(chip.get_bottom() + DOWN * 0.075)
        chip_t = T(p.gpu, 24, "highlight", weight=BOLD).move_to(chip)
        gpu = VGroup(chip, pins, pins2, chip_t).move_to([-5.4, -2.75, 0])
        gpu_t = T(f"1 × NVIDIA {p.gpu} GPU", 24).next_to(gpu, RIGHT, buff=0.3)
        cells = VGroup(*[Rectangle(width=0.1, height=0.4, stroke_width=0.8, stroke_color=resolve_color("dim"),
                                   fill_color=resolve_color("k3"), fill_opacity=0) for _ in range(p.blocks)]
                       ).arrange(RIGHT, buff=0.025).move_to([2.6, -2.75, 0])
        bar_t = T(f"{p.blocks} training blocks  ·  {p.days}", 20, "dim").next_to(cells, DOWN, buff=0.15)

        with self.narrate(3) as d:
            self.play(FadeIn(gpu, shift=UP * 0.2), FadeIn(gpu_t), FadeIn(cells), FadeIn(bar_t), run_time=0.8)
            self.play(LaggedStart(*[c.animate.set_fill(opacity=0.9) for c in cells], lag_ratio=0.05),
                      run_time=max(1.5, d - 1.2))
        self.clear_all()
