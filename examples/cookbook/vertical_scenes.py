"""Example 9:16 scenes for a short. Needs vertical.py in the same extensions/ folder.

- ``short_hook``: the first 1-2 s: a picture pushes in, a tag and a big claim slam in, then a chip
  lands at ``chip_at`` (share of the beat). Small image credit under the top band. (1 beat)
- ``short_end``: a loopable last line over a dimmed picture, a "Full video on my channel" prompt
  and a small note such as "debated claim · sources in description". (1 beat)

Both keep their content between ``self.top`` and ``self.bottom`` (see VScene), so burned-in
karaoke captions never cover them.
"""
from vidgen.api import *

from .vertical import AMBER, CYAN, VScene, cover, load_picture, run


@scene("short_hook")
class ShortHook(VScene):
    beat_count = 1
    outro = 0.0

    class Params(SceneParams):
        image: str
        tag: TranslatableStr
        title: TranslatableStr
        chip: TranslatableStr = ""
        chip_at: float = 0.5
        credit: TranslatableStr = ""

    def construct(self):
        p = self.params
        cr = self.credit(p.credit) if p.credit else None
        y = (cr.get_bottom()[1] - 0.1) if cr else self.top
        tag = self.chip(p.tag, CYAN, None, size="body")
        title = self.big(p.title, AMBER)
        head = VGroup(tag, title).arrange(DOWN, buff=0.2)
        head.move_to([0, y - head.height / 2, 0])
        chip = self.chip(p.chip, CYAN, None, size="subtitle") if p.chip else None
        img = load_picture(self.project.asset(p.image))
        room_top = head.get_bottom()[1] - 0.25
        room_bottom = self.bottom + ((chip.height + 0.25) if chip else 0)
        img.scale(min((room_top - room_bottom) / img.height, self.safe_width / img.width))
        img.move_to([0, (room_top + room_bottom) / 2, 0])
        frame = SurroundingRectangle(img, buff=0.04, color=CYAN, stroke_width=4)
        if chip:
            chip.move_to([0, self.bottom + chip.height / 2, 0])
        with self.narrate(0) as d:
            self.sfx("whoosh", gain=-6)
            self.play(FadeIn(img, scale=1.2), Create(frame), *([FadeIn(cr)] if cr else []), run_time=0.35)
            img.add_updater(lambda m, dt: m.scale(1 + 0.03 * dt))
            self.sfx("thud", gain=-4)
            self.play(FadeIn(tag, shift=DOWN * 0.2), FadeIn(title, scale=1.6),
                      run_time=0.35, rate_func=rate_functions.ease_out_back)
            if chip:
                self.wait(max(0.05, d * p.chip_at - 0.7))
                self.sfx("pop", gain=-6)
                self.play(FadeIn(chip, shift=UP * 0.25), run_time=run(d, 0.1, 0.35))
        self.finish()


@scene("short_end")
class ShortEnd(VScene):
    beat_count = 1
    outro = 0.0

    class Params(SceneParams):
        image: str
        line1: TranslatableStr
        line2: TranslatableStr = ""
        prompt: TranslatableStr = "Full video on my channel"
        note: TranslatableStr = "debated claim · sources in description"

    def construct(self):
        p = self.params
        bg = cover(load_picture(self.project.asset(p.image)), self.frame_width, self.frame_height, 1.05)
        bg.set_opacity(0.35)
        l1 = self.big(p.line1, "text")
        lines = VGroup(l1, self.big(p.line2, AMBER)) if p.line2 else VGroup(l1)
        lines.arrange(DOWN, buff=0.15)
        lines = self.plate(lines)
        lines.move_to([0, self.top - lines.height / 2, 0])
        prompt = self.chip(p.prompt, CYAN, "play", size="subtitle")
        note = self.text(p.note, size="small", color="text")
        note.move_to([0, self.bottom + note.height / 2, 0])
        prompt.next_to(note, UP, buff=0.25)
        with self.narrate(0) as d:
            self.add(bg)
            bg.add_updater(lambda m, dt: m.scale(1 + 0.02 * dt))
            self.play(FadeIn(lines, shift=UP * 0.3), run_time=0.35)
            self.wait(max(0.05, d * 0.35 - 0.35))
            self.sfx("chime", gain=-6)
            self.play(FadeIn(prompt, scale=1.2), FadeIn(note), run_time=run(d, 0.1, 0.4))
        self.finish()
