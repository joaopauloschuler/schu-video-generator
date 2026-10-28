"""``decay_chain``: a chain of decays drawn as a tree — each unstable particle with its mean life
τ and decay length cτ from PDG 2024 (a resonance with its width Γ), arrows to its products, the
branching fraction of the decay when the model lists it, and each decay checked by the
conservation checker (Phase Y, Step 241; DESIGN §99.12). Left to right in 16:9, top to bottom in
9:16; one decay per beat."""

from typing import Any, Literal

import numpy as np

from vidgen.api import *

from . import feynman_draw as fd

br = particle_physics.branching

#: Symbol and lifetime text, relative to the readable size.
SYMBOL_SCALE = 2.0
NOTE_SCALE = 1.1
#: Gap between a node and its arrows (scene units).
ARROW_BUFF = 0.18
#: A small chain grows up to this factor to fill the frame.
MAX_GROW = 1.6
#: Families drawn in the accent colour, the rest by kind.
_FAMILY_COLORS = {"lepton": "tertiary", "quark": "primary", "meson": "primary", "baryon": "primary", "gauge boson": "accent", "scalar boson": "secondary"}


def chain_of(params: Any) -> Any:
    """The model's chain of the params (raises ``VidgenError``)."""
    return br.chain(list(params.decays))


def _percent(f: float) -> str:
    """99.988 %, 0.0123 %: the fraction in percent with up to five significant figures."""
    v = f * 100
    text = f"{v:.5g}" if v >= 1 else f"{v:.3g}"
    return f"{text} %"


@scene("decay_chain")
class DecayChain(NarratedScene):
    """A decay chain (``decays: ["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu"]``) as a tree:
    each unstable particle with its mean life τ and cτ (PDG 2024; a resonance: Γ and τ = ħ/Γ),
    arrows to its products, the branching fraction of the decay when listed (``branching``), and
    every decay checked for charge, baryon and lepton numbers and energy (a forbidden decay is an
    error with the reason). One decay per beat; left to right (16:9) or top to bottom (9:16).

    Action targets: ``title``, ``caption``, ``chain``, ``decay<N>`` (its arrows, products and
    labels), ``particle:<n>`` (the n-th particle, 1 = the first parent) and
    ``particle:<particle>`` (a particle appearing once), ``lifetime:<particle>``."""

    outro = 0.5
    target_patterns = ("title", "caption", "chain", "decay<N>", "particle:<n>", "particle:<particle>", "lifetime:<particle>")

    class Params(SceneParams):
        decays: list[str] = Field(min_length=1)
        """The decays in order: the first one's parent starts the chain, each later decay's parent is a product not yet decayed ("pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e anti-nu_mu")."""
        title: TranslatableStr = ""
        """Title above the chain."""
        caption: TranslatableStr = ""
        """Note under the chain; default: the source of the values."""
        lifetimes: bool = True
        """Write τ and cτ (a resonance: Γ and τ) under each particle that decays."""
        branching: bool = True
        """Write the branching fraction of each decay the model lists (PDG 2024; the Higgs boson: LHC Higgs XS WG prediction)."""
        stable: bool = False
        """Also mark the final particles that are stable ("stable")."""
        reveal: Literal["decays", "all"] = "decays"
        """decays: the first particle, then one decay per beat; all: everything in beat 1."""
        title_size: ThemeSize = "heading"
        """Title size."""
        title_color: ThemeColor = "text"
        """Title colour."""
        caption_color: ThemeColor = "dim"
        """Caption colour."""

        @model_validator(mode="after")
        def _check(self) -> "DecayChain.Params":
            try:
                chain_of(self)
            except VidgenError as exc:
                raise ValueError(str(exc)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        ch = chain_of(params)
        names = (["title"] if params.title else []) + ["caption", "chain"] + [f"decay{k}" for k in range(1, len(ch.decays) + 1)]
        names += [f"particle:{i}" for i in range(1, len(ch.nodes) + 1)]
        keys = [n.particle.key for n in ch.nodes]
        names += [f"particle:{k}" for k in dict.fromkeys(keys) if keys.count(k) == 1]
        decaying = [n.particle.key for n in ch.nodes if n.decay is not None]
        names += [f"lifetime:{k}" for k in dict.fromkeys(decaying) if decaying.count(k) == 1] if params.lifetimes else []
        return names

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """A particle's name (for the narration lint), the title."""
        if name == "title":
            return str(params.title) or None
        kind, _, key = name.partition(":")
        if kind == "particle":
            ch = chain_of(params)
            for i, n in enumerate(ch.nodes, start=1):
                if key in (str(i), n.particle.key):
                    return n.particle.name
        return None

    # ----- building ----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self._chain = ch = chain_of(p)
        area = self.safe_area
        self._title = None
        if p.title:
            self._title = chart_title(p.title, size=p.title_size, color=p.title_color, area=area)
            area = area.below(self._title, gap=0.3)
        caption = str(p.caption) or self._source()
        self._caption = chart_caption(caption, area, color=p.caption_color)
        area = area.above(self._caption, gap=0.25)
        small = readable_size(margin=1.08)
        self._nodes = [self._node(i, small) for i in range(len(ch.nodes))]
        self._layout(area)
        self._arrows = self._draw_arrows(small)
        self._register()
        self.reveal(self._steps(), fraction=0.7, cap=1.2)
        self.finish()

    def _source(self) -> str:
        kinds = set()
        for proc in self._chain.decays:
            try:
                kinds.add(br.branching(proc.initial[0].particle.key).kind)
            except VidgenError:
                pass
        text = "lifetimes and widths: PDG 2024" + (" (Γ_H: SM prediction)" if any(n.particle.key == "H" and n.decay is not None for n in self._chain.nodes) else "")
        if self.params.branching and any(f is not None for f in self._chain.fractions):
            text += " · branching fractions: PDG 2024" + (" (H: SM prediction, LHC Higgs XS WG)" if "theory" in kinds else "")
        return text

    def _color(self, node: Any) -> str:
        p = node.particle
        if "nu" in p.key:
            return self.theme.color("dim")
        return self.theme.color(_FAMILY_COLORS.get(p.family, "text"))

    def _node(self, i: int, small: float) -> dict[str, Any]:
        """A particle's symbol, its outline (when it decays) and its lifetime lines."""
        n = self._chain.nodes[i]
        color = self._color(n)
        symbol = fd.particle_label(self, n.particle, n.leg.off_shell, small * SYMBOL_SCALE, color)
        box = None
        if n.decay is not None:
            box = RoundedRectangle(width=symbol.width + 0.4, height=symbol.height + 0.3, corner_radius=0.12)
            box.set_stroke(color, width=2.5).set_fill(color, opacity=0.1).move_to(symbol)
        lines = []
        if n.decay is not None and self.params.lifetimes:
            lines = n.lifetime_lines()
        elif n.decay is None and self.params.stable and n.particle.stable:
            lines = ["stable"]
        note = VGroup(*[self.text(t, size=small * NOTE_SCALE, color="dim") for t in lines]).arrange(DOWN, buff=0.08) if lines else VGroup()
        return {"symbol": symbol, "box": box, "note": note, "color": color}

    def _size(self, i: int) -> tuple[float, float]:
        """A node's width and height with its note under it."""
        d = self._nodes[i]
        core = d["box"] if d["box"] is not None else d["symbol"]
        w = max(core.width, d["note"].width)
        h = core.height + (d["note"].height + 0.12 if len(d["note"]) else 0.0)
        return w, h

    def _layout(self, area: Any) -> None:
        """A tidy tree: depth along the flow (x in 16:9, down in 9:16), leaves spread across it,
        each parent centred on its children; scaled down when it does not fit."""
        ch = self._chain
        depth = [0] * len(ch.nodes)
        for i, n in enumerate(ch.nodes):
            if n.parent is not None:
                depth[i] = depth[n.parent] + 1
        sizes = [self._size(i) for i in range(len(ch.nodes))]
        across: dict[int, float] = {}
        portrait = self.is_portrait
        gap = 0.45

        def extent(i: int) -> float:   # a node's size across the flow
            return sizes[i][0] if portrait else sizes[i][1]

        def width(i: int) -> float:   # a subtree's size across the flow: its own, or its children's side by side
            kids = ch.children(i)
            return max(extent(i), sum(width(k) for k in kids) + gap * (len(kids) - 1)) if kids else extent(i)

        def place(i: int, start: float) -> None:
            kids = ch.children(i)
            w = width(i)
            across[i] = start + w / 2
            if kids:
                inner = sum(width(k) for k in kids) + gap * (len(kids) - 1)
                at = start + (w - inner) / 2
                for k in kids:
                    place(k, at)
                    at += width(k) + gap

        place(0, 0.0)
        levels = max(depth) + 1
        along_size = [max((sizes[i][1] if portrait else sizes[i][0]) for i in range(len(ch.nodes)) if depth[i] == d) for d in range(levels)]
        span_across = max(width(0), 0.1)
        flow_room = (area.height if portrait else area.width)
        cross_room = (area.width if portrait else area.height)
        min_gap = 1.3   # room for an arrow between two levels
        # as large as the room allows (up to MAX_GROW), the arrows taking what is left along the flow
        scale = min(MAX_GROW, flow_room / (sum(along_size) + min_gap * (levels - 1)), cross_room / span_across)
        step_gap = min((flow_room - sum(along_size) * scale) / max(levels - 1, 1), 3.4) if levels > 1 else 0.0
        total_along = sum(along_size) * scale + step_gap * (levels - 1)
        starts = []
        pos = 0.0
        for d in range(levels):
            starts.append(pos + along_size[d] * scale / 2)
            pos += along_size[d] * scale + step_gap
        c = area.center
        for i in range(len(ch.nodes)):
            a = starts[depth[i]] - total_along / 2
            b = (across[i] - span_across / 2) * scale
            centre = np.array([c[0] + b, c[1] - a, 0.0]) if portrait else np.array([c[0] + a, c[1] - b, 0.0])
            d = self._nodes[i]
            group = VGroup(*[m for m in (d["box"], d["symbol"]) if m is not None])
            if scale != 1.0:
                group.scale(scale)
                d["note"].scale(scale)
            w, h = sizes[i][0] * scale, sizes[i][1] * scale
            core_h = group.height
            group.move_to(centre + np.array([0.0, h / 2 - core_h / 2, 0.0]))
            if len(d["note"]):
                d["note"].next_to(group, DOWN, buff=0.12 * scale)
            d["core"] = group

    def _draw_arrows(self, small: float) -> list[VGroup]:
        """Per decay: an arrow from the parent to each product, and its branching fraction."""
        ch = self._chain
        portrait = self.is_portrait
        out = []
        for k in range(len(ch.decays)):
            parent = next(i for i, n in enumerate(ch.nodes) if n.decay == k)
            kids = [i for i, n in enumerate(ch.nodes) if n.made_by == k]
            src = self._nodes[parent]["core"]
            group = VGroup()
            note = self._nodes[parent]["note"]
            start = (VGroup(src, note).get_bottom() if len(note) else src.get_bottom()) if portrait else src.get_right()
            if not portrait and len(self._nodes[parent]["note"]):
                start = np.array([src.get_right()[0], src.get_center()[1], 0.0])
            for i in kids:
                dst = self._nodes[i]["core"]
                end = dst.get_top() if portrait else dst.get_left()
                arrow = Arrow(start, end, buff=ARROW_BUFF, stroke_width=3, max_tip_length_to_length_ratio=0.12, max_stroke_width_to_length_ratio=8)
                group.add(arrow.set_color(self.theme.color("dim")))
            fraction = ch.fractions[k]
            if self.params.branching and fraction is not None:
                label = self.text(_percent(fraction), size=small * NOTE_SCALE, color="text")
                arrows = list(group)
                if portrait:   # right of the rightmost arrow, half-way down it, clear of it
                    a = max(arrows, key=lambda m: m.get_end()[0])
                    s, e = a.get_start(), a.get_end()
                    mid = (s + e) / 2
                    label.move_to(mid)
                    ys = (label.get_bottom()[1], label.get_top()[1])
                    reach = max(np.interp(y, sorted((s[1], e[1])), [s[0], e[0]] if s[1] < e[1] else [e[0], s[0]]) for y in ys)
                    label.align_to(np.array([reach + 0.12, 0, 0]), LEFT)
                else:   # above the topmost arrow, half-way along it, clear of it
                    a = max(arrows, key=lambda m: m.get_end()[1])
                    s, e = a.get_start(), a.get_end()
                    label.move_to((s + e) / 2)
                    xs = (label.get_left()[0], label.get_right()[0])
                    reach = max(np.interp(x, [s[0], e[0]], [s[1], e[1]]) for x in xs)
                    label.align_to(np.array([0, reach + 0.1, 0]), DOWN)
                group.add(label)
            out.append(group)
        return out

    def _register(self) -> None:
        ch = self._chain
        self._parts: dict[str, Any] = {}
        if self._title is not None:
            self.target("title", self._title, entrance=lambda: [FadeIn(self._title)])
        self.target("caption", self._caption, entrance=lambda: [FadeIn(self._caption)])
        node_mobs = []
        for i, d in enumerate(self._nodes, start=1):
            mob = VGroup(d["core"], d["note"])
            node_mobs.append(mob)
            names = [f"particle:{i}"]
            keys = [n.particle.key for n in ch.nodes]
            if keys.count(ch.nodes[i - 1].particle.key) == 1:
                names.append(f"particle:{ch.nodes[i - 1].particle.key}")
            self.target(names, mob, entrance=lambda m=d["core"]: [FadeIn(m, scale=0.8)])
        decaying = [n.particle.key for n in ch.nodes if n.decay is not None]
        for i, n in enumerate(ch.nodes):
            note = self._nodes[i]["note"]
            if n.decay is not None and len(note) and decaying.count(n.particle.key) == 1:
                self.target(f"lifetime:{n.particle.key}", note, entrance=lambda m=note: [FadeIn(m)])
        self._decay_targets = []
        for k, arrows in enumerate(self._arrows):
            parent = next(i for i, n in enumerate(ch.nodes) if n.decay == k)
            kids = [i for i, n in enumerate(ch.nodes) if n.made_by == k]
            mob = VGroup(arrows, *[node_mobs[i] for i in kids])
            self._decay_targets.append(self.target(f"decay{k + 1}", mob, entrance=lambda k=k, parent=parent, kids=kids: self._decay_entrance(k, parent, kids)))
        self.target("chain", VGroup(*node_mobs, *self._arrows), entrance=lambda: [a for k in range(len(self._arrows)) for a in self.entrance(f"decay{k + 1}")])

    def _decay_entrance(self, k: int, parent: int, kids: list[int]) -> list[Animation]:
        """The parent (if not on screen) and its lifetime, the arrows growing, the products."""
        anims: list[Animation] = []
        core = self._nodes[parent]["core"]
        if not self.on_screen_parts(core):
            anims.append(FadeIn(core, scale=0.8))
        note = self._nodes[parent]["note"]
        if len(note) and not self.on_screen_parts(note):
            anims.append(FadeIn(note))
        arrows = self._arrows[k]
        grow = [GrowArrow(a) for a in arrows if isinstance(a, Arrow)] + [FadeIn(m) for m in arrows if not isinstance(m, Arrow)]
        products = []
        for i in kids:
            products.append(FadeIn(self._nodes[i]["core"], shift=(DOWN if self.is_portrait else RIGHT) * 0.2))
            if len(self._nodes[i]["note"]) and self._chain.nodes[i].decay is None:
                products.append(FadeIn(self._nodes[i]["note"]))
        return [Succession(AnimationGroup(*anims), AnimationGroup(*grow), AnimationGroup(*products))] if anims else \
            [Succession(AnimationGroup(*grow), AnimationGroup(*products))]

    def _steps(self) -> list[Any]:
        frame = [m for m in (self._title,) if m is not None]
        root = self._nodes[0]["core"]

        def first() -> list[Animation]:
            out = [FadeIn(m) for m in frame if not self.on_screen_parts(m)] + [FadeIn(self._caption)]
            if not self.on_screen_parts(root):
                out.append(FadeIn(root, scale=0.8))
            return out

        decays = [(lambda k=k: self.entrance(self._decay_targets[k])) for k in range(len(self._arrows))]
        if self.params.reveal == "all":
            return [lambda: first() + [a for step in decays for a in step()]]
        return [first, *decays]


__all__ = ["DecayChain", "chain_of"]
