from vidgen.api import *
from .geometry import gear


class Ring(SceneParams):
    teeth: int = Field(ge=8, le=60)
    label: str = ""
    color: ThemeColor = "primary"


@scene("gear_pair")
class GearPair(NarratedScene):
    """Beat 1: both gears appear. Beat 2: the pedals turn once and the wheel follows."""

    beat_count = (2, 3)
    outro = 0.5

    class Params(SceneParams):
        front: Ring
        rear: Ring
        caption: str = ""
        icon: IconName | None = "bicycle"
        """Icon left of the ratio caption: built-in or assets/icons (`vidgen list-icons`)."""

    def construct(self):
        p = self.params
        front = gear(p.front.teeth, color=p.front.color)
        rear = gear(p.rear.teeth, color=p.rear.color)
        pair = VGroup(front, rear).arrange(DOWN if self.is_portrait else RIGHT, buff=1.0)
        place(pair, self.region("center"), max_scale=1.0)  # layout regions adapt to 16:9 and 9:16
        labels = VGroup(
            self.text(p.front.label or f"{p.front.teeth} teeth", size="caption", color=p.front.color).next_to(front, DOWN),
            self.text(p.rear.label or f"{p.rear.teeth} teeth", size="caption", color=p.rear.color).next_to(rear, DOWN),
        )
        ratio = p.front.teeth / p.rear.teeth
        header = self.region("header")
        caption = readable_text(p.caption or f"ratio {ratio:.2f} : 1", header, size="body", color="highlight", role="heading")
        if p.icon:  # assets/icons/bicycle.svg is a project icon; built-ins: `vidgen list-icons`
            caption = VGroup(icon(p.icon, size="body", color="highlight"), caption).arrange(RIGHT, buff=0.25)
        place(caption, header, fit="none", align="top")

        with self.narrate(0) as d:
            self.play(FadeIn(front), FadeIn(rear), FadeIn(labels), run_time=min(1.0, 0.5 * d))
        with self.narrate(1) as d:
            spin = max(d - 0.5, 0.5)
            self.play(
                Rotate(front, -TAU, about_point=front.get_center()),
                Rotate(rear, -TAU * ratio, about_point=rear.get_center()),
                FadeIn(caption),
                run_time=spin,
                rate_func=linear,
            )
        if len(self.beats) > 2:
            with self.narrate(2):
                self.play(Indicate(caption))
        self.finish()
