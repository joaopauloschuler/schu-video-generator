"""A photo cold open: full-bleed photo + slow push-in + glowing streak + big title + second
line + boxed tag. Copy into <project>/extensions/ together with science_helpers.py.
(For an animated data-flow hook see ``dataflow_hook`` in software_scenes.py.)"""
import numpy as np

from vidgen.api import *

from .science_helpers import glow_dot, load_picture, run

YELLOW_HOT = "#ffd84d"


# --------------------------------------------------------------------------------------------
@scene("cold_open")
class ColdOpen(NarratedScene):
    """Full-bleed photo with a slow push-in, a glowing streak, a big title, a second line and a
    boxed tag (e.g. "THE EVIDENCE, AS REPORTED"). Beats: 1 streak, 2 title, 3 second line, 4 tag."""

    beat_count = 4
    outro = 0.5

    class Params(SceneParams):
        path: str
        title: TranslatableStr
        line2: TranslatableStr
        tag: TranslatableStr
        credit: TranslatableStr = ""

    def construct(self):
        p = self.params
        fw, fh = self.frame_width, self.frame_height
        img = load_picture(self.project.asset(p.path))
        scale = max(fw / img.width, fh / img.height) * 1.04
        img.scale(scale)
        shade = Rectangle(width=fw + 0.2, height=fh + 0.2, stroke_width=0).set_fill(BLACK, opacity=0.45)

        def push(m, dt):
            m.scale(1 + 0.012 * dt)
        img.add_updater(push)

        start, end = np.array([fw * 0.55, fh * 0.45, 0]), np.array([-fw * 0.12, -fh * 0.05, 0])
        path = Line(start, end)
        head = glow_dot(YELLOW_HOT, radius=0.08)
        head.move_to(start)
        trail = TracedPath(head.get_center, stroke_color=YELLOW_HOT, stroke_width=7, dissipating_time=0.6, stroke_opacity=[0, 1])

        title = self.text(p.title, size=78, color="text", weight=BOLD, role="heading")
        shrink_to_fit(title, self.safe_width * 0.9, fh)
        title.move_to([0, 0.5, 0])
        line2 = self.text(p.line2, size="subtitle", color="highlight")
        shrink_to_fit(line2, self.safe_width * 0.9, fh)
        line2.next_to(title, DOWN, buff=0.45)
        tag_text = self.text(p.tag, size="body", color="accent", weight=BOLD)
        tag_box = SurroundingRectangle(tag_text, buff=0.22, corner_radius=0.12, color=self.theme.color("accent"), stroke_width=4)
        tag = VGroup(tag_box, tag_text).next_to(line2, DOWN, buff=0.6)
        credit = None
        if p.credit:
            ctext = self.text(p.credit, size=21, color="text")
            ctext.move_to([self.safe_area.x1 - ctext.width / 2, self.safe_area.y0 + ctext.height / 2, 0])
            cband = BackgroundRectangle(ctext, color=BLACK, fill_opacity=0.7, buff=0.08)
            credit = VGroup(cband, ctext)

        with self.narrate(0) as d:
            self.add(img, shade, trail)
            if credit is not None:
                self.add(credit)
            self.add(head)
            self.sfx("whoosh", gain=-2)
            self.play(MoveAlongPath(head, path), run_time=run(d, 0.55, 2.4), rate_func=rate_functions.ease_in_quad)
            self.play(Flash(head.get_center(), color=YELLOW_HOT, line_length=0.5, num_lines=14, flash_radius=0.4), FadeOut(head), run_time=0.6)
        with self.narrate(1) as d:
            self.play(Write(title), run_time=run(d, 0.45, 1.6))
        with self.narrate(2) as d:
            self.play(FadeIn(line2, shift=UP * 0.2), run_time=run(d, 0.3, 1.0))
            self.play(Indicate(title, scale_factor=1.05, color=self.theme.color("highlight")), run_time=run(d, 0.3, 1.2))
        with self.narrate(3) as d:
            self.sfx("thud", gain=-4)
            self.play(FadeIn(tag, scale=1.8), run_time=0.45, rate_func=rate_functions.ease_out_back)
        self.finish()

