"""Skeleton of a custom vidgen scene. Copy to <project>/extensions/ together with fx.py, rename
the scene (``@scene("...")`` must be unique in the project) and fill it in."""
from vidgen.api import *

from .fx import AMBER, CYAN, heading, run   # see fx.py


@scene("my_scene")                      # the `type:` used in video.yaml
class MyScene(NarratedScene):
    """One line per beat in the docstring: 1 ..., 2 ..., 3 ..."""

    beat_count = 3                      # must equal the number of beats in video.yaml
    outro = 0.4                         # fade-out seconds (held instead when a transition follows)

    class Params(SceneParams):          # every on-screen string is a param (translatable, editable)
        heading: TranslatableStr
        image: str = ""                 # a project-relative path such as "assets/x.png"
        note: TranslatableStr = ""      # a small source tag, e.g. "after Smith et al. 2013, fig. 3"

    def construct(self):
        p = self.params
        head = heading(self, p.heading)                     # placed in the header region
        note = self.text(p.note, size="small", color="dim")
        note.move_to([0, self.safe_area.y0 + note.height / 2, 0])   # bottom of the safe area

        dot = Circle(0.5, stroke_color=CYAN).set_fill(CYAN, 0.2)
        with self.narrate(0) as d:                          # d = the beat's audio length (s)
            self.play(FadeIn(head), FadeIn(note), run_time=0.4)
            self.sfx("pop", gain=-7)                        # starts with the next play()
            self.play(GrowFromCenter(dot), run_time=run(d, 0.3, 1.0))

        with self.narrate(1) as d:
            self.play(dot.animate.shift(RIGHT * 3), run_time=run(d, 0.4, 1.5))
            # keep something moving in long beats (avoids lint dead_air):
            self.play(Indicate(dot, color=AMBER), run_time=max(0.5, d - 2.0))

        with self.narrate(2) as d:
            self.sfx("chime", gain=-6)
            self.play(Flash(dot.get_center(), color=AMBER), run_time=0.5)
        self.finish()


# Patterns
# - Count up:   tr = ValueTracker(0); num = always_redraw(lambda: self.text(f"{int(tr.get_value())}", size=54)
#                   .next_to(icon_mob, RIGHT))  # position INSIDE the lambda!
#               self.play(tr.animate.set_value(443), rate_func=rate_functions.ease_out_cubic)
#               num.clear_updaters()   # before the scene ends
# - Continuous motion: self.play(t.animate.set_value(8), UpdateFromFunc(group, fn))  -> lint sees motion
#   (an updater alone on an object not in play() can be flagged as dead air)
# - Dim everything for a big statement: FadeIn(Rectangle(width=FW, height=FH).set_fill(DEEP, 0.86))
#   but FadeOut texts under it, or lint reports text overlaps.
# - Never animate a sub-part of a pill/card (Indicate(card[0])): Manim re-adds it on top and hides
#   the text. Animate the whole group, or draw a SurroundingRectangle on top.
# - Images: picture(self.project.asset(p.image), height=2.5)  (the path is relative to the project
#   root, so write "assets/x.png" in video.yaml).
