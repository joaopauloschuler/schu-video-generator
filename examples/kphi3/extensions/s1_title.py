"""Scene 1: a dense network loses most of its connections, then the title card (was S1Title)."""

import random

from vidgen.api import *


def color_glyphs(text: Text, source: str, part: str, color: str) -> None:
    """Color the glyphs of ``part`` in ``text`` (built from ``source``).

    ``Text`` has one submobject per non-space character. Unlike ``t2c``, this keeps Pango's
    shaping of the whole line (``t2c`` splits it into runs), exactly like the original video.
    """
    if not part:
        return
    start = source.replace(" ", "").find(part.replace(" ", ""))
    text[start:start + len(part.replace(" ", ""))].set_color(resolve_color(color))


@scene("kphi_title")
class KphiTitle(NarratedScene):
    """Beat 1: 100 connections, all but ``kept_percent`` fade while the counter drops.
    Beat 2: the network dims behind the title, subtitle, report kind and authors."""

    beat_count = 2

    class Params(SceneParams):
        title: str
        highlight: str = ""
        subtitle: str = ""
        kind: str = ""
        authors: list[str] = []
        connections_label: str = "connections"
        kept_percent: int = Field(23, ge=0, le=100)

        @model_validator(mode="after")
        def _highlight_in_title(self) -> SceneParams:
            if self.highlight not in self.title:
                raise ValueError(f"highlight {self.highlight!r} is not part of the title")
            return self

    def construct(self) -> None:
        p = self.params
        rng = random.Random(7)
        n = 10
        ins = column(n, -3.2, 0.62)
        outs = column(n, 3.2, 0.62)
        pairs = dense_pairs(n, n)
        net = edges(ins, outs, pairs, "base", width=1.4, opacity=0.55)

        kept = set(rng.sample(range(len(pairs)), round(len(pairs) * p.kept_percent / 100)))
        removed = VGroup(*[e for k, e in enumerate(net) if k not in kept])
        remaining = VGroup(*[e for k, e in enumerate(net) if k in kept])

        pct = ValueTracker(100)
        label = T(p.connections_label, 26, "dim").to_edge(DOWN, buff=0.45)
        num = counter(pct, "{:.0f}%", size=44, weight=BOLD, anchor=lambda: label, edge=UP)

        with self.narrate(0) as d:
            self.play(FadeIn(ins, lag_ratio=0.05), FadeIn(outs, lag_ratio=0.05), run_time=0.8)
            self.play(Create(net, lag_ratio=0.004), FadeIn(label), FadeIn(num), run_time=0.30 * d)
            self.play(FadeOut(removed, lag_ratio=0.01),
                      remaining.animate.set_color(resolve_color("k3")).set_stroke(width=2.4, opacity=0.9),
                      pct.animate.set_value(p.kept_percent), run_time=0.40 * d)

        title = T(p.title, 56, weight=BOLD)
        color_glyphs(title, p.title, p.highlight, "k3")
        head = VGroup(title)
        sub = T(p.subtitle, 42) if p.subtitle else None
        kind = T(p.kind, 26, "dim") if p.kind else None
        head.add(*[m for m in (sub, kind) if m is not None])
        head.arrange(DOWN, buff=0.28).move_to(UP * 1.0)
        authors = VGroup(*[T(a, 24) for a in p.authors])
        if p.authors:
            authors.arrange(DOWN, buff=0.18).next_to(head, DOWN, buff=0.8)

        net_rest = VGroup(ins, outs, remaining)
        with self.narrate(1):
            num.clear_updaters()
            self.play(FadeOut(num), FadeOut(label), net_rest.animate.set_opacity(0.12), run_time=0.8)
            self.play(Write(title), run_time=1.6)
            extras = [FadeIn(sub, shift=UP * 0.2)] if sub is not None else []
            extras += [FadeIn(kind)] if kind is not None else []
            if extras:
                self.play(*extras, run_time=0.8)
            if p.authors:
                self.play(FadeIn(authors, shift=UP * 0.2, lag_ratio=0.3), run_time=1.2)
        self.wait(0.3)
        self.clear_all()
