"""``metabolism``: energy metabolism at university level (DESIGN.md §95.13) — glycolysis (ten
steps, the investment and payoff phases, ATP and NADH counted per glucose), pyruvate oxidation
(into the matrix, pyruvate dehydrogenase), the citric acid cycle as a cycle diagram (eight steps,
3 NADH, 1 FADH₂, 1 GTP and 2 CO₂ per turn), the mitochondrial electron transport chain
(complexes I–IV, ubiquinone, cytochrome c, protons pumped into the intermembrane space, O₂ →
H₂O) with ATP synthase driven by the gradient, and the light reactions in the thylakoid membrane
(PSII with water splitting, plastoquinone, cytochrome b₆f, plastocyanin, PSI, ferredoxin, FNR,
ATP synthase with CF₁ in the stroma). ``advance`` animates the flows. The data and rules are
``vidgen.cellworld.energy`` (no manim); ATP synthase is Step 204's glyph."""

import math
import random
from dataclasses import replace
from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .bio_draw import driven, plate, small_size, text_block

en = cell_energy

#: Seconds per pathway step, per chain component, and for ATP synthase.
STEP_SECONDS, HOP_SECONDS, SYNTHASE_SECONDS = 0.9, 0.75, 2.6
#: Protons drawn on the P side at most (more are counted, not drawn).
MAX_PROTONS = 30
NODE_STROKE = 2.4


@lru_cache(maxsize=32)
def _setting(process: str, cell: str, compartment: str | None, membrane: str | None, protons_to: str | None,
             chain: tuple[str, ...] | None, link: bool) -> Any:
    return en.check_setting(process, cell, compartment, membrane, protons_to, chain, link)


@scene("metabolism")
class Metabolism(NarratedScene):
    """Energy metabolism: ``process: glycolysis`` (ten steps from glucose to 2 pyruvate, the
    investment and payoff phases, ATP used and made, NADH; ``link: true`` adds pyruvate
    oxidation in the matrix), ``link_reaction``, ``tca`` (the citric acid cycle as a ring of its
    eight intermediates with the enzymes, NADH, FADH₂, GTP and CO₂ per turn), ``etc`` (complexes
    I–IV, ubiquinone and cytochrome c in the inner mitochondrial membrane, protons pumped into the
    intermembrane space, O₂ reduced to water, ATP synthase) and ``light_reactions`` (PSII, water
    splitting, plastoquinone, cytochrome b₆f, plastocyanin, PSI, ferredoxin, FNR making NADPH, ATP
    synthase). Tallies count the products. The action ``advance`` moves a token through the
    steps, or electrons along the chain with protons crossing, or the gradient through ATP
    synthase. Checked: the compartment a pathway runs in, the membrane a chain sits in, the side
    protons are pumped to, the components' order.

    Action targets: ``title``, the process (``glycolysis``, ``tca``, ``etc``…), each metabolite
    (``pyruvate``…) and enzyme step (``step:<key>``), each component (``complex_i``…),
    ``membrane``, ``tally``."""

    outro = 0.5
    target_patterns = ("title", "<process>", "<metabolite>", "step:<key>", "<component>", "membrane", "tally")
    metabolism_actions = True
    mid_still_actions = frozenset({"advance"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        process: str
        """glycolysis, link_reaction, tca (the citric acid cycle), etc (electron transport chain and ATP synthase), light_reactions."""
        cell: Literal["animal", "plant", "bacterium"] | None = None
        """Whose metabolism: animal (default), plant (default for light_reactions) or bacterium (no mitochondria: the chain in the plasma membrane, the cycle in the cytosol)."""
        compartment: str | None = Field(None, alias="in")
        """glycolysis / link_reaction / tca: where it runs (checked: glycolysis in the cytosol, the others in the mitochondrial matrix)."""
        membrane: str | None = None
        """etc / light_reactions: the membrane (checked: inner_mitochondrial, thylakoid; bacterial for a bacterium)."""
        protons_to: str | None = None
        """etc / light_reactions: where protons are pumped (checked: intermembrane_space, thylakoid_lumen, periplasm)."""
        components: list[str] = Field(default_factory=list, max_length=8)
        """etc / light_reactions: the components drawn, in electron order (default all; ATP synthase may be left out)."""
        link: bool = False
        """glycolysis / tca: add pyruvate oxidation (pyruvate into the matrix, pyruvate dehydrogenase → acetyl-CoA)."""
        tallies: bool = True
        """Count the products (ATP, NADH, FADH₂, GTP, CO₂; protons pumped)."""
        names: Literal["auto", "full", "short"] = "auto"
        """Metabolite names: full (glucose 6-phosphate), short (G6P) or auto (full where they fit)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "caption"
        """Label size (never below the readable minimum)."""

        def setting(self) -> Any:
            return _setting(self.process, self.cell, self.compartment, self.membrane, self.protons_to, tuple(self.components) or None, self.link)

        def pathway(self) -> Any:
            return en.pathway(self.setting().process, self.link)

        @model_validator(mode="after")
        def _check(self) -> "Metabolism.Params":
            try:
                self.setting()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        s = params.setting()
        names = (["title"] if params.title else []) + [s.process]
        if s.process in ("etc", "light_reactions"):
            names += list(s.chain) + ["membrane"]
        else:
            p = params.pathway()
            names += [n.key for n in p.nodes] + [f"step:{st.key}" for st in p.steps]
        return names + (["tally"] if params.tallies else [])

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """``advance`` in beat and ``at`` order: a pathway runs one way (the cycle turns on); ATP
        synthase needs protons pumped before."""
        from .cycle_actions import _beat_order

        s = params.setting()
        state = en.FlowState()
        problems: list[tuple[str, str]] = []
        for i in _beat_order(spec, uses):
            use = uses[i]
            if use.kind.name != "advance":
                continue
            o = use.action.options
            if s.process in ("etc", "light_reactions"):
                problem = en.chain_advance_problem(s, state, o.to, o.source)
                if problem:
                    problems.append((f"{use.location}.to", problem))
                    continue
                key = en.component_key(s.process, o.to) if o.to else None
                if key == "atp_synthase":
                    state.gradient = 0
                else:
                    state.gradient += en.chain_effects(s, en.electron_path(s, o.source))["given"]
                continue
            p = params.pathway()
            problem = en.pathway_advance_problem(p, state, o.to)
            if problem:
                problems.append((f"{use.location}.to", problem))
                continue
            k = en.step_index(p, o.to) if o.to else len(p.steps) - 1
            state.step = k if k < len(p.steps) - 1 or not p.cyclic else -1
        return problems

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        th = self.theme
        self.bg = th.background
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.hi = th.color("highlight")
        self.good = th.color("tertiary")
        self.bad = th.color("accent")
        self.small = small_size(self, p.size)
        self.setting_ = p.setting()
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.3)
        self.parts: dict[str, Mobject] = {}
        self.state = en.FlowState()
        self.enzyme_mobs: dict[str, Mobject] = {}
        if self.setting_.process in ("etc", "light_reactions"):
            self._build_chain(body)
        else:
            self._build_pathway(body)
        if title is not None:
            self.target("title", title, entrance=lambda: [FadeIn(title)])
        for name, mob in self.parts.items():
            self.target(name, mob)

        def first() -> list[Animation]:
            return ([FadeIn(title)] if title is not None else []) + [FadeIn(self.everything)]

        self.reveal([first], fraction=0.8, cap=1.2)
        self.finish()

    # ----- tallies ------------------------------------------------------------------------------

    def _tally_rows(self) -> list[tuple[str, str, int, int]]:
        """(key, label markup, lowest, highest) of the counters this process shows."""
        s = self.setting_
        if s.process == "glycolysis":
            rows = [("ATP", "ATP (net)", -2, 2), ("NADH", "NADH", 0, 2), ("pyruvate", "pyruvate", 0, 2)]
            if s.link:
                rows += [("CO2", "CO<sub>2</sub>", 0, 2), ("acetyl", "acetyl-CoA", 0, 2)]
                rows[1] = ("NADH", "NADH", 0, 4)
            return rows
        if s.process == "link_reaction":
            return [("NADH", "NADH", 0, 2), ("CO2", "CO<sub>2</sub>", 0, 2), ("acetyl", "acetyl-CoA", 0, 2)]
        if s.process == "tca":
            rows = [("NADH", "NADH", 0, 12), ("FADH2", "FADH<sub>2</sub>", 0, 4), ("GTP", "GTP", 0, 4), ("CO2", "CO<sub>2</sub>", 0, 12)]
            return rows
        if s.process == "etc":
            return [("H", "H<sup>+</sup> pumped", 0, 60), ("H2O", "H<sub>2</sub>O", 0, 6), ("ATP", "ATP", 0, 30)]
        return [("H", "H<sup>+</sup> into lumen", 0, 60), ("O2", "O<sub>2</sub>", 0, 12), ("NADPH", "NADPH", 0, 6), ("ATP", "ATP", 0, 30)]

    def _build_tallies(self, area: Any, horizontal: bool) -> VGroup:
        """Counters: a label and a number per product; every number they may show is made now
        and shown by opacity (texts made during an animation are not drawn)."""
        self.tally_values: dict[str, int] = {}
        self.tally_digits: dict[str, dict[int, Mobject]] = {}
        rows = []
        for key, label, lo, hi in self._tally_rows():
            name = self.markup(label, size=self.small, color=self.dim_ink)
            digits = {}
            for v in range(lo, hi + 1):
                text = f"{v:+d}".replace("-", "−") if key == "ATP" and lo < 0 else str(v)
                if key == "O2":      # counted in halves: ½ O₂ per water split (two electrons)
                    text = (str(v // 2) if v // 2 or v % 2 == 0 else "") + ("½" if v % 2 else "")
                digits[v] = self.markup(f"<b>{text}</b>", size=self.small * 1.25, color=self.ink)
            self.tally_digits[key] = digits
            self.tally_values[key] = 0
            num = VGroup(*digits.values())
            rows.append((name, num))
        head = self.markup("<b>per glucose</b>" if self.setting_.process in ("glycolysis", "link_reaction")
                           else "<b>per turn</b>" if self.setting_.process == "tca"
                           else "<b>so far</b>", size=self.small, color=self.ink)
        items = []
        for name, num in rows:
            w = max(d.width for d in num)
            for d in num:
                d.move_to(ORIGIN, aligned_edge=RIGHT)
            items.append(VGroup(name, num).arrange(RIGHT, buff=0.25 + w * 0.2))
        if horizontal:
            body = VGroup(*items).arrange(RIGHT, buff=0.45)
            if body.width > area.width:
                body = VGroup(*items).arrange_in_grid(cols=2, buff=(0.4, 0.15), col_alignments="ll")
            group = VGroup(head, body).arrange(DOWN, buff=0.15, aligned_edge=LEFT)
        else:
            column = VGroup(*items).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
            x = max(it[0].get_right()[0] for it in items) + 0.3 + max(it[1].width for it in items)
            for it in items:         # the numbers right-aligned in one column
                it[1].shift(RIGHT * (x - it[1].get_right()[0]))
            group = VGroup(head, column).arrange(DOWN, buff=0.25, aligned_edge=LEFT)
        if group.width > area.width or group.height > area.height:
            group.scale(min(area.width / group.width, area.height / group.height))
        group.move_to(area.center)
        self._show_tallies()
        self.parts["tally"] = group
        return group

    def _show_tallies(self) -> None:
        for key, digits in self.tally_digits.items():
            v = self.tally_values[key]
            for value, mob in digits.items():
                mob.set_opacity(1.0 if value == v else 0.0)

    def _count(self, key: str, delta: int) -> None:
        if key in self.tally_values:
            lo, hi = min(self.tally_digits[key]), max(self.tally_digits[key])
            self.tally_values[key] = max(lo, min(hi, self.tally_values[key] + delta))

    # ----- pathways -----------------------------------------------------------------------------

    def _build_pathway(self, body: Any) -> None:
        p = self.params
        s = self.setting_
        path = p.pathway()
        self.path = path
        tally_area = None
        under_last = p.tallies and not self.is_portrait and path.process == "glycolysis" and path.link
        if p.tallies and not under_last:
            if self.is_portrait:
                tally_area = Region(body.x0, body.y0, body.x1, body.y0 + 1.6)
                body = Region(body.x0, tally_area.y1 + 0.25, body.x1, body.y1)
            else:
                tally_area = Region(body.x1 - (2.0 if path.cyclic else 2.8), body.y0, body.x1, body.y1)
                body = Region(body.x0, body.y0, tally_area.x0 - 0.3, body.y1)
        if path.cyclic:
            drawing = self._ring_layout(body)
        else:
            drawing = self._chain_layout(body)
        if under_last:     # glycolysis with pyruvate oxidation: the counters under the short last column
            last = [self.node_mobs[k] for k in ("pyruvate_m", "acetyl_coa")]
            x0 = min(m.get_left()[0] for m in last)
            tally_area = Region(x0, body.y0, body.x1, min(m.get_bottom()[1] for m in last) - 0.35)
        parts = [drawing]
        if tally_area is not None:
            parts.append(self._build_tallies(tally_area, self.is_portrait or under_last))
        self.token = Dot(radius=0.11, color=self.hi).set_z_index(6)
        self.token.set_opacity(0.0)
        self.token.move_to(self.node_mobs[path.nodes[0].key].get_center())
        parts.append(self.token)
        self.everything = VGroup(*parts)
        self.parts[s.process] = drawing
        compartment = self.markup(("cytosol" if s.process == "glycolysis" and not s.link else
                                   "cytosol → mitochondrial matrix" if s.link and s.process == "glycolysis" else
                                   "mitochondrial matrix" if s.compartment == "matrix" else "cytosol"),
                                  size=self.small * 0.95, color=self.dim_ink)
        compartment.move_to(np.array([body.x0 + compartment.width / 2, body.y0 + compartment.height / 2, 0.0]))
        if not any(_overlaps(compartment, m) for m in drawing.submobjects):
            self.everything.add(compartment)

    def _node(self, key: str, width_limit: float | None) -> VGroup:
        """A metabolite: its name (full, or short when it does not fit) in a rounded box, its
        carbon count small and dim after it."""
        n = self.path.node(key)
        names = self.params.names
        text = self.markup(n.markup if names != "short" else n.short, size=self.small, color=self.ink)
        if names == "auto" and width_limit is not None and text.width > width_limit:
            text = self.markup(n.short, size=self.small, color=self.ink)
        parts: list[Mobject] = [text]
        if n.carbons and not (self.is_portrait and not self.path.cyclic):    # a tall frame's columns are narrow
            parts.append(self.markup(f"{n.carbons}C", size=self.small * 0.92, color=self.dim_ink))
        inner = VGroup(*parts).arrange(RIGHT, buff=0.14)
        box = RoundedRectangle(width=inner.width + 0.26, height=text.height + 0.2, corner_radius=0.1)
        color = self.theme.palette_color(0)
        box.set_fill(color, opacity=0.1).set_stroke(color, width=NODE_STROKE)
        return VGroup(box, inner.move_to(box))

    def _step_labels(self, st: Any) -> tuple[Mobject, Mobject | None]:
        """A step's enzyme (its abbreviation unless ``names: full`` or the name is short; ×2
        after the cleavage) and its cofactors (the carrier and what it becomes: ATP → ADP,
        NAD⁺ → NADH), each on one line."""
        times = " ×2" if st.times == 2 and self.path.process == "glycolysis" else ""
        name = st.enzyme
        short = en.ENZYME_SHORT.get(st.key, name)
        if self.params.names == "short" or (self.params.names == "auto" and len(name) > 10):
            name = short
        enzyme = self.markup(f"<i>{name}</i>{times}", size=self.small, color=self.dim_ink)
        if not (st.inputs or st.outputs):
            return enzyme, None
        ins = [i.split(" + ")[0] for i in st.inputs[:1]]
        outs = [o.split(" + ")[0] for o in st.outputs]
        left, right = " + ".join(ins), " + ".join(outs)
        text = f"{left} → {right}" if left and right else (f"− {left}" if left else f"+ {right}")
        return enzyme, self.markup(text, size=self.small, color=self.theme.palette_color(1))

    def _chain_layout(self, body: Any) -> VGroup:
        """Glycolysis as two columns, snaking (investment phase down, payoff phase up, the
        triose step between their bottoms; pyruvate oxidation down a third from the top, or on
        up the second in a portrait frame); each arrow with its enzyme on the left and its
        cofactors on the right, one line each. Pyruvate oxidation alone: one column."""
        path = self.path
        nodes = [n.key for n in path.nodes]
        if path.process == "glycolysis":
            cols = [nodes[:5], nodes[5:11]] + ([nodes[11:]] if path.link else [])
            if path.link and self.is_portrait:
                cols = [nodes[:5], nodes[5:]]
        else:
            cols = [nodes]
        ncol = len(cols)
        gap = 0.3
        self.node_mobs = {k: self._node(k, 2.4) for k in nodes}
        col_of = {k: c for c, col in enumerate(cols) for k in col}
        labels = {st.key: self._step_labels(st) for st in path.steps}
        vertical = {c: [st for st in path.steps if col_of[st.source] == c and col_of[st.target] == c] for c in range(ncol)}
        node_h = max(m.height for m in self.node_mobs.values())
        # each column: its enzymes left of the arrows, the cofactors right of them, the nodes centred
        # on them; in a portrait frame the second column has both on its right, the enzyme over the
        # cofactors (the frame is too narrow for four label columns)
        stacked = {c: self.is_portrait and c == 1 for c in range(ncol)}
        for key, (enzyme, cof) in labels.items():
            st = next(s for s in path.steps if s.key == key)
            if stacked[col_of[st.source]] and cof is not None and col_of[st.source] == col_of[st.target]:
                labels[key] = (VGroup(enzyme, cof).arrange(DOWN, buff=0.04, aligned_edge=LEFT), None)
                self.enzyme_mobs[key] = enzyme
        left = [max([self.node_mobs[k].width / 2 for k in cols[c]] + ([] if stacked[c] else
                    [labels[st.key][0].width + 0.12 for st in vertical[c]])) for c in range(ncol)]
        right = [max([self.node_mobs[k].width / 2 for k in cols[c]] +
                     [labels[st.key][1].width + 0.12 for st in vertical[c] if labels[st.key][1] is not None] +
                     ([labels[st.key][0].width + 0.12 for st in vertical[c]] if stacked[c] else [])) for c in range(ncol)]
        between = {}
        for c, col in enumerate(cols):
            for a, b in zip(col, col[1:]):
                st = next(s for s in path.steps if s.source == a and s.target == b)
                between[a] = max(0.42, max(m.height for m in labels[st.key] if m is not None) + 0.16)

        def col_height(col: list[str]) -> float:
            return len(col) * node_h + sum(between[k] for k in col[:-1])

        heights = [col_height(c) for c in cols]
        top_room = self.small / 48 * 0.9 + 0.25 if path.process == "glycolysis" else 0.0      # the phase names
        if path.process == "glycolysis" and ncol == 3:         # and the carrier's name below them
            top_room += self.small / 48 * 0.9 + 0.1
        bottom_room = self.small / 48 * 0.9 + 0.15 if ncol > 1 else 0.0                      # the triose step's name
        width = sum(left) + sum(right) + gap * (ncol - 1)
        scale = min(1.0, (body.height - top_room - bottom_room) / max(heights), body.width / width)
        if scale < 1.0:
            for mob in [*self.node_mobs.values(), *[m for pair in labels.values() for m in pair if m is not None]]:
                mob.scale(scale)
            node_h *= scale
            between = {k: v * scale for k, v in between.items()}
            left, right = [w * scale for w in left], [w * scale for w in right]
            heights = [col_height(c) for c in cols]
            width = sum(left) + sum(right) + gap * (ncol - 1)
        tallest = max(heights)
        top = body.y1 - top_room - max(0.0, (body.height - top_room - bottom_room - tallest) / 2)
        bottom = top - tallest
        x = body.center[0] - width / 2
        centers = []
        for c, col in enumerate(cols):
            cx = x + left[c]
            centers.append(cx)
            x = cx + right[c] + gap
            if c % 2 == 1:          # the second column runs upwards from the bottom
                y = bottom + node_h / 2
                for k in col:
                    self.node_mobs[k].move_to(np.array([cx, y, 0.0]))
                    y += node_h / 2 + between.get(k, 0.0) + node_h / 2
            else:     # the first column ends level with the second's start (the step between them runs across)
                y = (bottom + heights[c] - node_h / 2) if (c == 0 and ncol > 1) else top - node_h / 2
                for k in col:
                    self.node_mobs[k].move_to(np.array([cx, y, 0.0]))
                    y -= node_h / 2 + between.get(k, 0.0) + node_h / 2
        self.step_mobs: dict[str, VGroup] = {}
        self.arrows: list[VMobject] = []
        group = VGroup(*self.node_mobs.values())
        for st in path.steps:
            a, b = self.node_mobs[st.source][0], self.node_mobs[st.target][0]
            ca, cb = a.get_center(), b.get_center()
            enzyme, cof = labels[st.key]
            if abs(ca[0] - cb[0]) < 1e-6:
                start = a.get_bottom() if cb[1] < ca[1] else a.get_top()
                end = b.get_top() if cb[1] < ca[1] else b.get_bottom()
                line = Line(start, end, buff=0.04)
                mid = (start[1] + end[1]) / 2
                side = 1 if stacked[col_of[st.source]] else -1
                pad = 0.55 if st.key == "mpc" else 0.12       # clear of the membrane drawn across the arrow
                enzyme.move_to(np.array([ca[0] + side * (pad + enzyme.width / 2), mid, 0.0]))
                if cof is not None:
                    cof.move_to(np.array([ca[0] + 0.12 + cof.width / 2, mid, 0.0]))
            else:      # across between two columns: the enzyme above, the cofactors below
                line = Line(a.get_right(), b.get_left(), buff=0.06)
                enzyme.next_to(line, DOWN if st.key == "tpi" else UP, buff=0.08)
                if st.key == "mpc" and enzyme.width < line.get_length() / 2 - 0.2:   # on the matrix side, clear of the membrane
                    enzyme.shift(RIGHT * (line.get_center()[0] + 0.15 - enzyme.get_left()[0]))
                if cof is not None:
                    cof.next_to(line, DOWN, buff=0.08)
            line.set_stroke(self.dim_ink, width=2.6)
            head = Triangle().set_fill(self.dim_ink, opacity=1).set_stroke(width=0).scale(0.08)
            d = line.get_end() - line.get_start()
            head.rotate(math.atan2(d[1], d[0]) - math.pi / 2).move_to(line.get_end())
            step = VGroup(VGroup(line, head), enzyme, *([cof] if cof is not None else []))
            self.enzyme_mobs.setdefault(st.key, enzyme)
            self.step_mobs[st.key] = step
            self.arrows.append(line)
            self.parts[f"step:{st.key}"] = step
            group.add(step)
        for key, mob in self.node_mobs.items():
            self.parts[key] = mob
        if path.process == "glycolysis":       # the two phases, named over their columns
            for c, name in ((0, "investment phase"), (1, "payoff phase ×2")):
                col_nodes = [self.node_mobs[k] for k in cols[c] if k not in ("pyruvate_m", "acetyl_coa")]
                text = self.markup(f"<i>{name}</i>", size=self.small, color=self.dim_ink)
                y = max(m.get_top()[1] for m in col_nodes) + 0.12 + text.height / 2
                if len(cols[c]) > len(col_nodes):    # pyruvate oxidation goes on up: name the phase beside its top
                    top_node = self.node_mobs["pyruvate"]
                    x, y = top_node.get_left()[0] - 0.15 - text.width / 2, top_node.get_center()[1]
                    y = max(y, group[-1].get_top()[1] + 0.2 + text.height / 2)     # above the investment phase's name
                elif path.link and c == 1:      # above the carrier's name over the arrow on the right
                    x = centers[c]
                    y = max(y, self.enzyme_mobs["mpc"].get_top()[1] + 0.08 + text.height / 2)
                else:
                    x = centers[c]
                text.move_to(np.array([min(max(x, body.x0 + text.width / 2), body.x1 - text.width / 2), y, 0.0]))
                group.add(text)
        if path.link:
            group.add(self._link_membrane())
        return group

    def _link_membrane(self) -> Mobject:
        """The inner mitochondrial membrane (two lines) across the pyruvate carrier's arrow."""
        st = next(s for s in self.path.steps if s.key == "mpc")
        a, b = self.node_mobs[st.source], self.node_mobs[st.target]
        horizontal = abs(a.get_center()[1] - b.get_center()[1]) < 1e-6
        mid = (a[0].get_right() + b[0].get_left()) / 2 if horizontal else (a[0].get_bottom() + b[0].get_top()) / 2
        length = 0.9
        lines = VGroup()
        for off in (-0.06, 0.06):
            if horizontal:
                lines.add(Line(mid + UP * length / 2 + RIGHT * off, mid + DOWN * length / 2 + RIGHT * off))
            else:
                lines.add(Line(mid + LEFT * length / 2 + UP * off, mid + RIGHT * length / 2 + UP * off))
        lines.set_stroke(mix_colors(self.theme.color("secondary"), self.ink, 0.7), width=2.4)
        return lines

    def _ring_label(self, st: Any, width: float) -> tuple[Mobject, Mobject | None]:
        """A step of the cycle: the enzyme (its abbreviation when the name does not fit) and
        what it makes or takes up (→ NADH + CO₂; + H₂O), or ``None``."""
        name = st.enzyme
        if self.params.names == "short" or (self.params.names == "auto" and self.markup(name, size=self.small).width > width):
            name = en.ENZYME_SHORT.get(st.key, name)
        enzyme = self.markup(f"<i>{name}</i>", size=self.small, color=self.dim_ink)
        made = [o for o in st.outputs if o != "CoA"]
        used = [i for i in st.inputs if i.startswith("H<sub>2</sub>O")]
        if not (made or used):
            return enzyme, None
        text = ("→ " + " + ".join(made)) if made else "+ " + " + ".join(used)
        return enzyme, self.markup(text, size=self.small, color=self.theme.palette_color(1))

    def _ring_layout(self, body: Any) -> VGroup:
        """The citric acid cycle: its eight intermediates on an ellipse, clockwise, acetyl-CoA
        joining oxaloacetate at the top; each step's enzyme inside its arc, what it makes outside."""
        path = self.path
        keys = [n.key for n in path.nodes]
        order = keys[1:] + keys[:1]           # citrate … oxaloacetate
        portrait = self.is_portrait
        self.node_mobs = {k: self._node(k, 2.2 if not portrait else 1.5) for k in keys}
        # landscape: enzymes inside the ring, products outside; portrait (narrow): the reverse,
        # the enzymes' abbreviations beside the arcs
        labels = {st.key: self._ring_label(st, 1.9 if not portrait else 1.0) for st in path.steps}
        prod_w = max((p.width for _, p in labels.values() if p is not None), default=0.0)
        node_w = max(m.width for m in self.node_mobs.values())
        node_h = max(m.height for m in self.node_mobs.values())
        entry = node_h + 0.45 + (node_h + 0.75 if path.link else 0.0)
        prod_h = max((p.height for _, p in labels.values() if p is not None), default=0.0)
        if portrait:     # the sides' nodes reach the edges; labels below the bottom ones
            lab_h = max(VGroup(e, *([p] if p is not None else [])).arrange(DOWN, buff=0.04).height for e, p in labels.values())
            rx = max(1.4, min(body.width / 2 - node_w / 2 - 0.1, 2.6))
            ry = max(min((body.height - entry - node_h / 2 - lab_h - 0.5) / 2, rx * 1.6), 1.2)
            center = np.array([body.center[0], body.y0 + lab_h + 0.35 + ry, 0.0])
        else:
            rx = min((body.width / 2 - prod_w - 0.95), 3.3)
            rx = max(rx, (node_w + 0.3) / (2 * math.sin(math.pi / 8)))
            ry = max(min((body.height - entry - prod_h - 0.45) / 2, rx * 0.75), 1.2)
            center = np.array([body.center[0], body.y0 + prod_h + 0.3 + ry, 0.0])

        def on(theta: float) -> np.ndarray:
            return center + np.array([rx * math.cos(theta), ry * math.sin(theta), 0.0])

        # citrate just right of the top, oxaloacetate just left; in a tall frame oxaloacetate on top
        start = math.pi / 2 - math.pi / 8 if not self.is_portrait else math.pi / 4
        angles = {k: start - j * 2 * math.pi / 8 for j, k in enumerate(order)}
        for k, a in angles.items():
            self.node_mobs[k].move_to(on(a))
        group = VGroup(*self.node_mobs.values())
        self.step_mobs = {}
        self.arrows = []
        placed: list[Mobject] = []
        for st in path.steps:
            a0, a1 = angles[st.source], angles[st.target]
            if a1 > a0:
                a1 -= 2 * math.pi
            pts = [on(a0 + (a1 - a0) * t / 40) for t in range(41)]
            na, nb = self.node_mobs[st.source][0], self.node_mobs[st.target][0]
            free = [p for p in pts if not _inside(p, na, 0.06) and not _inside(p, nb, 0.06)]
            arc = VMobject().set_points_smoothly(free if len(free) >= 2 else pts[18:23]).set_stroke(self.dim_ink, width=2.6)
            d = arc.points[-1] - arc.points[-2]
            head = Triangle().set_fill(self.dim_ink, opacity=1).set_stroke(width=0).scale(0.08)
            head.rotate(math.atan2(d[1], d[0]) - math.pi / 2).move_to(arc.points[-1])
            mid = (a0 + a1) / 2
            out = np.array([math.cos(mid) / rx, math.sin(mid) / ry, 0.0])
            out = out / np.linalg.norm(out)
            enzyme, made = labels[st.key]
            boxes = list(self.node_mobs.values()) + placed
            self.enzyme_mobs[st.key] = enzyme
            if made is not None and st.key == "citrate_synthase":
                made = None
            if portrait:      # one label outside: the abbreviation over what the step makes
                label = VGroup(enzyme, *([made] if made is not None else [])).arrange(DOWN, buff=0.04, aligned_edge=LEFT)
                _clear_of(label, on(mid), out, 0.15, boxes)
                safe = self.safe_area
                label.shift(LEFT * max(0.0, label.get_right()[0] - safe.x1) + RIGHT * max(0.0, safe.x0 - label.get_left()[0]))
                placed.append(label)
                items: list[Mobject] = [VGroup(arc, head), label]
            else:             # the enzyme inside the ring, what it makes outside
                _clear_of(enzyme, on(mid), -out, 0.18, boxes)
                placed.append(enzyme)
                items = [VGroup(arc, head), enzyme]
                if made is not None:
                    _clear_of(made, on(mid), out, 0.2, boxes + [enzyme])
                    placed.append(made)
                    items.append(made)
            step = VGroup(*items)
            self.step_mobs[st.key] = step
            self.arrows.append(arc)
            self.parts[f"step:{st.key}"] = step
            group.add(step)
        # acetyl-CoA (and pyruvate before it) joins at the middle of citrate synthase's arc (as drawn,
        # between the boxes), from above; or from above right when a box is in the way down
        cs_arc = self.arrows[[st.key for st in path.steps].index("citrate_synthase")]

        def above(p: np.ndarray) -> list[Mobject]:
            return [n[0] for n in self.node_mobs.values()
                    if n[0].get_left()[0] - 0.1 < p[0] < n[0].get_right()[0] + 0.1 and n[0].get_top()[1] > p[1]]

        join = cs_arc.point_from_proportion(0.5)
        for prop in (0.55, 0.6, 0.65, 0.7, 0.75):       # nearer citrate, until nothing is in the way down
            if not above(join):
                break
            join = cs_arc.point_from_proportion(prop)
        boxes_above = above(join)
        acetyl = self._entry("acetyl-CoA", 2, self.theme.palette_color(1))
        x = join[0] if not boxes_above else max(b.get_right()[0] for b in boxes_above) + 0.1 + acetyl.width / 2
        x = min(x, self.safe_area.x1 - acetyl.width / 2)
        acetyl.move_to(np.array([x, max(n.get_top()[1] for n in self.node_mobs.values()) + 0.3 + acetyl.height / 2, 0.0]))
        start_at = acetyl.get_bottom() if not boxes_above else acetyl.get_corner(DL) + RIGHT * 0.15
        down = Arrow(start_at, join + UP * 0.03, buff=0.03, stroke_width=2.6, max_tip_length_to_length_ratio=0.3,
                     color=self.dim_ink)
        self.acetyl = acetyl
        group.add(acetyl, down)
        if path.link:
            pnode = self._entry("pyruvate", 3, self.theme.palette_color(0))
            pnode.move_to(acetyl.get_top() + UP * (0.7 + pnode.height / 2))
            a2 = Arrow(pnode.get_bottom(), acetyl.get_top(), buff=0.04, stroke_width=2.6, max_tip_length_to_length_ratio=0.3, color=self.dim_ink)
            enzyme, made = self._ring_label(en.LINK_STEPS[1], 2.4)
            lab = VGroup(enzyme, *([made] if made is not None else [])).arrange(RIGHT, buff=0.2).next_to(a2, RIGHT, buff=0.15)
            group.add(pnode, a2, lab)
        if not portrait:       # the products outside may reach past the side: fit it in, scaling only if need be
            if group.width > body.width:
                group.scale(body.width / group.width)
            group.shift(RIGHT * (max(0.0, body.x0 - group.get_left()[0]) - max(0.0, group.get_right()[0] - body.x1)))
        return group

    def _entry(self, name: str, carbons: int, color: str) -> VGroup:
        text = self.markup(name, size=self.small, color=self.ink)
        c = self.markup(f"{carbons}C", size=self.small * 0.92, color=self.dim_ink)
        inner = VGroup(text, c).arrange(RIGHT, buff=0.14)
        box = RoundedRectangle(width=inner.width + 0.26, height=text.height + 0.2, corner_radius=0.1)
        box.set_fill(color, opacity=0.12).set_stroke(color, width=NODE_STROKE)
        return VGroup(box, inner.move_to(box))

    # ----- the chains ---------------------------------------------------------------------------

    def _build_chain(self, body: Any) -> None:
        """The membrane across the frame, the components along it in electron order, ATP synthase
        apart. In a portrait frame the membrane is folded back on itself, as in a crista or a
        thylakoid: the chain goes right along the top membrane (its P side below) and back along
        the bottom one (P side above), the P space between them."""
        p = self.params
        s = self.setting_
        known = en.components(s.process)
        chain = [known[k] for k in s.chain]
        portrait = self.is_portrait
        tally_area = None
        if p.tallies:
            if portrait:
                tally_area = Region(body.x0, body.y0, body.x1, body.y0 + 1.7)
                body = Region(body.x0, tally_area.y1 + 0.2, body.x1, body.y1)
            else:
                tally_area = Region(body.x1 - 2.6, body.y0, body.x1, body.y1)
                body = Region(body.x0, body.y0, tally_area.x0 - 0.25, body.y1)
        # a key to the short labels drawn in the glyphs, under the drawing
        key = self._chain_key(chain, body.width)
        key.move_to(np.array([body.x0 + key.width / 2, body.y0 + key.height / 2, 0.0]))
        area = Region(body.x0, key.get_top()[1] + 0.2, body.x1, body.y1)
        rows = self._rows(chain) if portrait else [chain]
        gap = 0.55

        def after(row: list[Any], k: int) -> float:
            """The gap after the ``k``-th component: ATP synthase stands apart from the chain."""
            return 1.4 if "atp_synthase" in (row[k].key, row[k + 1].key) else gap

        def length(row: list[Any]) -> float:
            return sum(c.width for c in row) + sum(after(row, k) for k in range(len(row) - 1)) + 0.6

        self.frame: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        if not portrait:
            total = length(chain)
            m = min(0.6, (area.width - 0.2) / total, area.height / 8.4)
            y_m = area.y0 + 4.4 * m + max(0.0, (area.height - 8.4 * m) / 2)
            x = area.center[0] - (total - 0.6) * m / 2
            lines = [(y_m, RIGHT, UP, x)]
            self.p_box = (area.x0 + 0.1, y_m + 1.0 * m, area.x1 - 0.1, area.y1 - 0.5)
        else:
            fold = 0.0
            m = min(0.6, area.height / (4.3 + 4.2 + 4.6))
            m = min(m, (area.width - 0.3) / (max(length(r) for r in rows) + 2.6))
            # the P space between the two membranes: taller when the frame has room (its name and
            # the carriers reaching into it), as long as the fold still fits beside the rows
            room = area.width - 0.45 - max(length(r) for r in rows) * m - m / 2
            sep = max(4.2 * m, min(5.6 * m, area.height - 8.9 * m, 2 * room))
            fold = sep / 2 + m / 2                 # the fold's radius (half the P space) plus the bilayer
            y0m = area.center[1] + (8.9 * m + sep) / 2 - 4.3 * m      # the drawing centred in its area
            y1m = y0m - sep
            x_left = area.x0 + 0.3
            x_fold = area.x1 - fold - 0.15
            lines = [(y0m, RIGHT, DOWN, x_left), (y1m, LEFT, UP, x_fold - 0.25)]
            self.p_box = (area.x0 + 0.1, y1m + 1.0 * m, x_fold, y0m - 1.0 * m)
            self.fold = (x_fold, (y0m + y1m) / 2, (y0m - y1m) / 2)
        self.m = m
        for (y, A, U, x), row in zip(lines, rows):
            a = 0.0
            for k, c in enumerate(row):
                P = np.array([x, y, 0.0]) + A * (a + c.width * m / 2)
                self.frame[c.key] = (P, A, U)
                a += (c.width + (after(row, k) if k + 1 < len(row) else 0.0)) * m
        membrane = self._membrane(area, lines)
        self.parts["membrane"] = membrane
        self.comp_mobs: dict[str, VGroup] = {}
        self.anchors: dict[str, dict[str, np.ndarray]] = {}
        for c in chain:
            mob, anchors = self._component(c)
            self.comp_mobs[c.key] = mob
            self.anchors[c.key] = anchors
            self.parts[c.key] = mob
        labels = self._side_labels(area, lines)
        group = VGroup(membrane, *self.comp_mobs.values(), labels, key)
        parts = [group]
        if tally_area is not None:
            parts.append(self._build_tallies(tally_area, portrait))
        self.protons = VGroup()
        self.proton_count = 0
        self.dynamic = VGroup()
        parts += [self.protons, self.dynamic]
        self.everything = VGroup(*parts)
        self.parts[s.process] = group
        self.rng = random.Random(f"metabolism:{self.spec.id}")

    def _rows(self, chain: list[Any]) -> list[list[Any]]:
        """The chain in two rows for the folded membrane: up to the first carrier on the P side
        (cytochrome c, plastocyanin), which starts the second; else halved."""
        at = next((k for k, c in enumerate(chain) if c.span == "p" and k > 0), None)
        if at is None:
            at = max(1, len(chain) // 2)
        if at >= len(chain):
            return [chain]
        rows = [chain[:at], chain[at:]]
        if rows[1][-1].key == "atp_synthase" and len(rows[1]) > 1:    # ATP synthase on the shorter row, apart
            if sum(c.width for c in rows[0]) <= sum(c.width for c in rows[1][:-1]) + 0.6:
                rows = [[rows[1][-1], *rows[0]], rows[1][:-1]]
        return rows

    def _membrane(self, area: Any, lines: list[tuple[float, np.ndarray, np.ndarray, float]]) -> VGroup:
        """The bilayer as a band with its two faces; folded (a half ring) in portrait frames."""
        th = self.theme
        m = self.m
        fill = mix_colors(th.color("secondary"), self.bg, 0.22)
        ink = mix_colors(th.color("secondary"), self.ink, 0.65)
        parts = VGroup()
        if len(lines) == 1:
            y = lines[0][0]
            band = Rectangle(width=area.width, height=m).move_to(np.array([area.center[0], y, 0.0]))
            parts.add(band.set_fill(fill, opacity=1).set_stroke(width=0))
            for s_ in (-1, 1):
                parts.add(Line(np.array([area.x0, y + s_ * m / 2, 0.0]), np.array([area.x1, y + s_ * m / 2, 0.0])).set_stroke(ink, width=2.4))
            return parts
        x_fold, y_c, r = self.fold
        for y, *_ in lines:
            band = Rectangle(width=x_fold - area.x0, height=m).move_to(np.array([(area.x0 + x_fold) / 2, y, 0.0]))
            parts.add(band.set_fill(fill, opacity=1).set_stroke(width=0))
            for s_ in (-1, 1):
                parts.add(Line(np.array([area.x0, y + s_ * m / 2, 0.0]), np.array([x_fold, y + s_ * m / 2, 0.0])).set_stroke(ink, width=2.4))
        ring = AnnularSector(inner_radius=r - m / 2, outer_radius=r + m / 2, angle=PI, start_angle=-PI / 2, arc_center=np.array([x_fold, y_c, 0.0]))
        parts.add(ring.set_fill(fill, opacity=1).set_stroke(width=0))
        for rr in (r - m / 2, r + m / 2):
            parts.add(Arc(radius=rr, start_angle=-PI / 2, angle=PI, arc_center=np.array([x_fold, y_c, 0.0])).set_stroke(ink, width=2.4))
        return parts

    def _side_labels(self, area: Any, lines: list[tuple[float, np.ndarray, np.ndarray, float]]) -> VGroup:
        """The compartments' names: the P side and the N side (both N spaces in portrait)."""
        s = self.setting_
        m = self.m

        def name(key: str) -> str:
            return CELL_COMPARTMENTS[key].label if key in CELL_COMPARTMENTS else key.replace("_", " ")

        out = VGroup()
        if len(lines) == 1:
            y_m = lines[0][0]
            p_lab = self.markup(f"{name(s.p_side)} (P side)", size=self.small, color=self.dim_ink)
            n_lab = self.markup(f"{name(s.n_side)} (N side)", size=self.small, color=self.dim_ink)
            p_lab.move_to(np.array([area.x0 + p_lab.width / 2 + 0.05, min(area.y1 - p_lab.height / 2, y_m + 3.9 * m), 0.0]))
            n_lab.move_to(np.array([area.x0 + n_lab.width / 2 + 0.05, max(area.y0 + n_lab.height / 2, y_m - 4.1 * m), 0.0]))
            self.p_box = (self.p_box[0], self.p_box[1], self.p_box[2], p_lab.get_bottom()[1] - 0.12)
            self.avoid = [p_lab, n_lab]
            return VGroup(p_lab, n_lab)
        (y0m, *_), (y1m, *_) = lines
        x_fold = self.fold[0]
        for text, y, right in ((f"{name(s.n_side)} (N side)", y0m + 3.9 * m, area.x1), (f"{name(s.p_side)} (P side)", (y0m + y1m) / 2, x_fold),
                               (f"{name(s.n_side)} (N side)", y1m - 4.3 * m, area.x1)):
            # on the right, clear of ATP synthase and of water splitting at the chain's start; the
            # P space's name, if a carrier reaches into it there, smaller or at the left end
            for size, at_left in ((1.0, False), (1.0, True), (0.85, False), (0.85, True), (1.0, False)):
                lab = text_block(self, text, area.width * 0.42, self.small * size, color=self.dim_ink,
                                 align=LEFT if at_left else RIGHT)
                x = area.x0 + 0.1 + lab.width / 2 if at_left else right - lab.width / 2 - 0.1
                lab.move_to(np.array([x, min(y, area.y1 - lab.height / 2), 0.0]))
                if not any(_overlaps(lab, mob) for mob in self.comp_mobs.values()):
                    break
            out.add(lab)
        self.avoid = list(out)
        return out

    def _chain_key(self, chain: list[Any], width: float) -> VGroup:
        """What the short labels in the glyphs stand for (I: NADH dehydrogenase · Q: ubiquinone…)."""
        items = []
        for c in chain:
            if c.key in ("atp_synthase", "psii", "psi"):     # named in full in their glyphs
                continue
            name = c.name
            if name.startswith("complex ") and "(" in name:
                name = name[name.index("(") + 1: name.rindex(")")]
            else:
                name = name.split(" (")[0]
            items.append(f"<b>{c.label}</b> {name}")
        size = max(readable_size() * 1.02, self.small * 0.9)
        return text_block(self, "  ·  ".join(items), width, size, color=self.dim_ink)

    def _shape(self, along: float, across: float, center: np.ndarray, color: str, corner: float = 0.25) -> VMobject:
        r = RoundedRectangle(width=along, height=across, corner_radius=min(corner, along / 2.2, across / 2.2)).move_to(center)
        return r.set_fill(mix_colors(color, self.bg, 0.55), opacity=1).set_stroke(color, width=2.2)

    def _component(self, c: Any) -> tuple[VGroup, dict[str, np.ndarray]]:
        """A component's glyph at its place and its anchor points (``e``: where its electrons
        sit; ``n`` / ``p``: its faces). Its frame: ``A`` along the membrane, ``U`` towards the P
        side (the membranes run horizontally)."""
        m = self.m
        P, A, U = self.frame[c.key]
        th = self.theme
        colors = {"complex_i": th.palette_color(0), "complex_ii": th.palette_color(3), "complex_iii": th.palette_color(1),
                  "complex_iv": th.palette_color(2), "psii": th.palette_color(3), "b6f": th.palette_color(1), "psi": th.palette_color(0),
                  "fnr": th.palette_color(2)}
        color = colors.get(c.key, mix_colors(self.ink, self.bg, 0.6))
        anchors = {"e": P.copy(), "n": P - U * 0.8 * m, "p": P + U * 0.8 * m}
        parts: list[Mobject] = []
        label_at: np.ndarray | None = P.copy()
        if c.key == "complex_i":     # L-shaped: the membrane arm and the matrix arm with NADH's site
            arm = self._shape(c.width * m, 0.95 * m, P, color)
            per = self._shape(0.85 * m, 2.3 * m, P + A * 0.75 * m - U * 1.35 * m, color)
            parts += [per, arm]
            anchors["e"] = P + A * 0.75 * m - U * 2.1 * m
            anchors["n"] = P + A * 0.75 * m - U * 2.6 * m
            anchors["out"] = P - A * 0.4 * m
        elif c.key == "complex_ii":
            head = self._shape(c.width * m, 1.3 * m, P - U * 1.2 * m, color, 0.5)
            anchor = self._shape(0.6 * m, 0.95 * m, P, color)
            parts += [anchor, head]
            anchors["e"] = P - U * 1.2 * m
            anchors["n"] = P - U * 2.0 * m
            label_at = P - U * 1.2 * m
        elif c.span == "pool":
            q = Ellipse(width=c.width * m, height=0.62 * m).move_to(P)
            q.set_fill(mix_colors(th.color("highlight"), self.bg, 0.6), opacity=1).set_stroke(th.color("highlight"), width=2)
            parts.append(q)
        elif c.span == "span":
            if c.key in ("complex_iii", "b6f"):    # a dimer, with its cytochrome head on the P side
                parts += [self._shape(c.width * m * 0.48, 1.7 * m, P - A * c.width * m * 0.26, color),
                          self._shape(c.width * m * 0.48, 1.7 * m, P + A * c.width * m * 0.26, color)]
                head = Circle(radius=0.32 * m).move_to(P + U * 0.95 * m).set_fill(mix_colors(color, self.bg, 0.4), opacity=1)
                parts.append(head.set_stroke(color, width=2))
            else:
                parts.append(self._shape(c.width * m, 1.75 * m, P, color))
            if c.key == "psii":   # the oxygen-evolving complex on the lumen side
                oec = Circle(radius=0.26 * m).move_to(P + U * 1.05 * m - A * 0.5 * m)
                oec.set_fill(th.palette_color(1), opacity=1).set_stroke(width=0)
                parts.append(oec)
                anchors["water"] = oec.get_center()
            anchors["n"] = P - U * 0.95 * m
            anchors["p"] = P + U * 0.95 * m
        elif c.span == "p":
            ball = Circle(radius=c.width * m / 2).move_to(P + U * 0.95 * m)
            ball.set_fill(mix_colors(color, self.bg, 0.4), opacity=1).set_stroke(color, width=2)
            parts.append(ball)
            anchors["e"] = ball.get_center()
            label_at = ball.get_center()
        elif c.span == "n":
            at = P - U * 0.95 * m
            ball = Ellipse(width=c.width * m, height=0.8 * m).move_to(at) if c.key == "fnr" else Circle(radius=c.width * m / 2).move_to(at)
            ball.set_fill(mix_colors(color, self.bg, 0.4), opacity=1).set_stroke(color, width=2)
            parts.append(ball)
            anchors["e"] = at
            anchors["n"] = at - U * 0.6 * m
            label_at = at
        elif c.span == "synthase":   # Step 204's glyph: +y is its P side
            glyph = molecule_glyph(MoleculeSpec("atp_synthase", "synthesis", membrane=self.setting_.membrane, bare=True))
            unit = m / 5.0      # 5 nm of bilayer = the band
            px = 100.0 / (1080.0 / min(self.frame_width, self.frame_height))
            mob = glyph_mobjects(glyph.prims, CellColors(self.bg, self.ink), unit, P, px,
                                 lambda t, h: self.markup(t, size=self.small).scale_to_fit_height(max(h, 0.05)))
            turn = math.atan2(U[1], U[0]) - math.pi / 2
            if abs(turn) > 1e-6:
                mob.rotate(turn, about_point=P)
                for sub in mob:
                    if isinstance(sub, MarkupText):
                        sub.rotate(-turn)
            parts.append(mob)
            anchors["p"] = P + U * 0.9 * m + A * 2.75 * unit
            anchors["e"] = P + A * 2.75 * unit
            anchors["n"] = P - U * (12.6 * unit + 0.4 * m)
            anchors["f1"] = P - U * 12.6 * unit
            anchors["rotor"] = P - U * 5.4 * unit
            label_at = None
            name = self.markup("<b>ATP synthase</b>", size=self.small, color=self.ink)
            if self.is_portrait:      # the P space between the folds is narrow: beneath F₁
                name.move_to(anchors["n"] - U * (0.35 * m + _extent(name, U)))
                name.shift(RIGHT * max(0.0, self.safe_area.x0 + 0.05 - name.get_left()[0]))
            else:
                name.move_to(P + U * (0.75 * m + _extent(name, U)) + A * 0.3 * m)
            parts.append(name)
        group = VGroup(*parts)
        if label_at is not None:
            text = self.markup(f"<b>{c.label}</b>", size=self.small, color=self.ink)
            limit = max(c.width * m * 0.9, 0.3)
            if text.width > limit and c.span not in ("pool", "p", "n"):
                text.scale(limit / text.width)
            text.move_to(label_at)
            group.add(text)
        anchors.setdefault("out", anchors["e"])
        return group, anchors

    # ----- the actions --------------------------------------------------------------------------

    def advance_seconds(self, to: str | None, source: str | None) -> float:
        s = self.setting_
        if s.process in ("etc", "light_reactions"):
            key = en.component_key(s.process, to) if to else None
            if key == "atp_synthase":
                return SYNTHASE_SECONDS
            path = en.electron_path(s, source)
            n = path.index(key) + 1 if key in path else len(path)
            return max(1.5, HOP_SECONDS * n + 0.8)
        k0 = self.state.step
        k1 = en.step_index(self.path, to) if to else len(self.path.steps) - 1
        n = (k1 - k0) if k1 > k0 else (k1 - k0 + len(self.path.steps))
        return max(1.2, STEP_SECONDS * n)

    def run_advance(self, to: str | None, source: str | None) -> list[Animation]:
        if self.setting_.process in ("etc", "light_reactions"):
            key = en.component_key(self.setting_.process, to) if to else None
            if key == "atp_synthase":
                return self._run_synthase()
            return self._run_electrons(key, source)
        return self._run_pathway(to)

    def _run_pathway(self, to: str | None) -> list[Animation]:
        path = self.path
        k0 = self.state.step
        k1 = en.step_index(path, to) if to else len(path.steps) - 1
        steps = list(range(k0 + 1, k1 + 1)) if k1 > k0 else list(range(k0 + 1, len(path.steps))) + list(range(0, k1 + 1))
        self.state.step = k1 if (k1 < len(path.steps) - 1 or not path.cyclic) else -1
        arrows = [self.arrows[k] for k in steps]
        names = [self.enzyme_mobs[path.steps[k].key] for k in steps]
        glyphs = [[g for g in m.family_members_with_points() if isinstance(g, VMobject)] for m in names]
        rest = [[g.fill_rgbas.copy() for g in gs] for gs in glyphs]
        token = self.token
        n = len(steps)
        start_tallies = dict(getattr(self, "tally_values", {}))
        changes = []
        for k in steps:
            st = path.steps[k]
            made = [(key, value * st.times) for key, value in st.tally]
            made += [("pyruvate", 2)] if st.target == "pyruvate" else []
            made += [("acetyl", 2)] if st.target == "acetyl_coa" else []
            changes.append(made)

        def frame(alpha: float) -> None:
            x = alpha * n
            j = min(int(x), n - 1)
            t = x - j
            token.set_opacity(1.0 if alpha < 0.999 else 0.0)
            token.move_to(arrows[j].point_from_proportion(min(1.0, t)))
            for i, name in enumerate(names):
                if i == j and alpha < 0.999:
                    name.set_color(self.hi)
                else:
                    for g, rgba in zip(glyphs[i], rest[i]):
                        g.fill_rgbas = rgba.copy()
            if hasattr(self, "tally_values"):
                self.tally_values.update(start_tallies)
                done = n if alpha >= 0.999 else j + (1 if t > 0.6 else 0)
                for i in range(done):
                    for key, delta in changes[i]:
                        self._count(key, delta)
                self._show_tallies()

        moving = VGroup(token, *names)
        if hasattr(self, "tally_digits"):
            moving.add(*[d for digits in self.tally_digits.values() for d in digits.values()])
        target = self.node_mobs[path.steps[k1].target]
        return [Succession(driven(moving, frame, rate_func=linear), Indicate(target[0], color=self.hi, scale_factor=1.06))]

    def _run_electrons(self, to: str | None, source: str | None) -> list[Animation]:
        s = self.setting_
        path = list(en.electron_path(s, source))
        if to is not None and to in path:
            path = path[: path.index(to) + 1]
        known = en.components(s.process)
        m = self.m
        pts = []
        first = self.anchors[path[0]]
        if s.process == "light_reactions" and "water" in first:
            pts.append(first["water"])
        for key in path:
            if key == "complex_i":
                pts += [self.anchors[key]["e"], self.anchors[key]["out"]]
            else:
                pts.append(self.anchors[key]["e"])
        electrons = VGroup(*[self._electron() for _ in range(2)])
        for e in electrons:
            e.move_to(pts[0]).set_opacity(0.0)
        self.add(electrons)
        # protons: taken from the N side, given to the P side, per component on the way
        moves: list[tuple[Mobject, np.ndarray, np.ndarray, float, float, bool]] = []
        hop = 1.0 / max(1, len(pts) - 1)
        fresh = VGroup()
        for key in path:
            c = known[key]
            idx = max(i for i, k in enumerate(self._pt_keys(path, s)) if k == key)
            when = idx * hop
            P, A, U = self.frame[key]
            for j in range(c.takes + c.consumes):
                dot = self._proton()
                a = P + A * (j - (c.takes + c.consumes - 1) / 2) * 0.28 * m - U * 2.9 * m
                moves.append((dot, a, P, when - 0.6 * hop, when, False))
                fresh.add(dot)
            for j in range(c.gives):
                dot = self._proton()
                a = P + U * 0.3 * m
                b = self._p_spot()
                moves.append((dot, a, b, when, when + 0.8 * hop, True))
                fresh.add(dot)
        for dot, a, *_ in moves:
            dot.move_to(a).set_opacity(0.0)
        self.add(fresh)
        # light: a photon reaches each photosystem just before its electrons leave it
        photons: list[tuple[VMobject, float]] = []
        for key in path:
            if known[key].photon:
                idx = self._pt_keys(path, s).index(key) + (1 if key == "psii" and "water" in self.anchors[key] else 0)
                photons.append((self._photon(key), max(0.0, idx * hop - 0.5 * hop)))
        for ph, _ in photons:
            ph.set_stroke(opacity=0.0)
            ph[1].set_fill(opacity=0.0)
            self.add(ph)
            fresh.add(ph)
        effects = en.chain_effects(s, tuple(path))
        reactions = self._reactions(path, source)
        for r in reactions:
            r.set_opacity(0.0)
        self.add(*reactions)
        old = list(self.dynamic)
        start = {k: v for k, v in getattr(self, "tally_values", {}).items()}
        given = effects["given"]
        water = 1 if "complex_iv" in path else 0
        o2 = 1 if s.process == "light_reactions" and path[0] == "psii" else 0
        nadph = 1 if "fnr" in path else 0

        def frame(alpha: float) -> None:
            for i, e in enumerate(electrons):
                lag = 0.12 * i
                xx = max(0.0, min(len(pts) - 1, (alpha - lag) / (1 - lag) * (len(pts) - 1))) if len(pts) > 1 else 0
                jj = min(int(xx), len(pts) - 2) if len(pts) > 1 else 0
                tt = xx - jj
                e.move_to(pts[jj] + (pts[jj + 1] - pts[jj]) * smooth(tt) if len(pts) > 1 else pts[0])
                e.set_opacity(0.0 if alpha >= 0.999 else min(1.0, alpha * 12))
            for dot, a, b, t0, t1, stays in moves:
                if alpha < t0:
                    dot.set_opacity(0.0)
                    continue
                u = min(1.0, (alpha - t0) / max(1e-6, t1 - t0))
                dot.move_to(a + (b - a) * smooth(u))
                dot.set_opacity(1.0 if stays or u < 1.0 else 0.0)
            for ph, t0 in photons:
                u = (alpha - t0) / max(1e-6, 0.6 * hop)
                o = 0.0 if u < 0 or u > 1.6 else min(1.0, u * 3, (1.6 - u) * 3)
                ph[0].set_stroke(opacity=o)
                ph[1].set_fill(opacity=o).set_stroke(opacity=0)
            for k, r in enumerate(reactions):
                r.set_opacity(min(1.0, max(0.0, (alpha - r.when) * 6)))
            for mob in old:
                mob.set_opacity(max(0.0, 1 - alpha * 4))
            if hasattr(self, "tally_values"):
                self.tally_values.update(start)
                self._count("H", int(round(given * alpha)))
                if alpha > 0.95:
                    self._count("H2O", water)
                    self._count("O2", o2)
                    self._count("NADPH", nadph)
                self._show_tallies()

        self.proton_count += given
        moving = VGroup(electrons, fresh, *reactions, *old)
        if hasattr(self, "tally_digits"):
            moving.add(*[d for digits in self.tally_digits.values() for d in digits.values()])
        for dot, a, b, t0, t1, stays in moves:
            if stays:
                self.protons.add(dot)
        self.dynamic.remove(*old)
        self.dynamic.add(*reactions)
        self.state.gradient += given
        return [driven(moving, frame, rate_func=linear)]

    def _pt_keys(self, path: list[str], s: Any) -> list[str]:
        """The component of each point of the electrons' path."""
        out = []
        if s.process == "light_reactions" and "water" in self.anchors[path[0]]:
            out.append(path[0])
        for key in path:
            out += [key, key] if key == "complex_i" else [key]
        return out

    def _reactions(self, path: list[str], source: str | None) -> list[Mobject]:
        """The reactions shown as the electrons pass: NADH oxidised at complex I (or succinate at
        complex II), water made at complex IV; water split at PSII, NADPH made at FNR."""
        s = self.setting_
        known = en.components(s.process)
        out = []
        keys = self._pt_keys(path, s)
        n = max(1, len(keys) - 1)
        for key in path:
            c = known[key]
            if not c.reaction or key == "atp_synthase":
                continue
            text = self.markup(c.reaction, size=self.small * 0.92, color=self.theme.palette_color(1))
            anchor = self.anchors[key]
            U = self.frame[key][2]
            if c.reaction_side == "p":
                spot = anchor.get("water", anchor["p"]) + U * (0.45 * self.m + _extent(text, U))
            else:
                spot = anchor["n"] - U * (0.25 * self.m + _extent(text, U))
            text.move_to(spot)
            safe = self.safe_area
            if text.get_left()[0] < safe.x0:
                text.shift(RIGHT * (safe.x0 - text.get_left()[0]))
            if text.get_right()[0] > safe.x1:
                text.shift(LEFT * (text.get_right()[0] - safe.x1))
            for _ in range(30):         # beside the compartments' names, not over them
                hit = next((lab for lab in self.avoid if _overlaps(text, lab)), None)
                if hit is None:
                    break
                step = RIGHT if hit.get_center()[0] < text.get_center()[0] else LEFT
                if not safe.x0 <= (text.get_left() + step * 0.1)[0] <= safe.x1 - text.width:
                    break
                text.shift(step * 0.1)
            back = plate(text, self.bg, 0.05, 0.8)
            group = VGroup(back, text)
            group.when = keys.index(key) / n - 0.05   # type: ignore[attr-defined]
            out.append(group)
        return out

    def _photon(self, key: str) -> VGroup:
        """A wavy arrow (light, hν) onto component ``key``'s P face, slanting in."""
        target = self.comp_mobs[key]
        _, A, U = self.frame[key]
        end = target.get_center() + U * _extent(target, U) - A * 0.1 * self.m
        start = end + (U * 1.6 - A * 1.3) * self.m
        d = end - start
        length = float(np.linalg.norm(d))
        u = d / length
        n = np.array([-u[1], u[0], 0.0])
        pts = [start + d * (k / 60) * 0.88 + n * 0.12 * self.m * math.sin(k / 60 * 6 * math.pi) for k in range(61)]
        wave = VMobject().set_points_smoothly(pts).set_stroke(self.hi, width=3)
        tip = pts[-1]
        head = Polygon(end, tip + n * 0.1 * self.m - u * 0.02, tip - n * 0.1 * self.m - u * 0.02).set_fill(self.hi, opacity=1).set_stroke(width=0)
        head.set_stroke(width=0)
        return VGroup(wave, head).set_z_index(7)

    def _electron(self) -> VGroup:
        dot = Circle(radius=0.12).set_fill(self.hi, opacity=1).set_stroke(self.bg, width=1.5)
        text = self.markup("e<sup>−</sup>", size=self.small * 0.7, color=text_color_on(self.hi)).move_to(dot)
        if text.width > 0.2:
            text.scale(0.2 / text.width)
        return VGroup(dot, text).set_z_index(8)

    def _proton(self) -> VGroup:
        color = self.bad
        dot = Circle(radius=0.1).set_fill(color, opacity=1).set_stroke(self.bg, width=1.2)
        text = self.markup("H<sup>+</sup>", size=self.small * 0.6, color=text_color_on(color)).move_to(dot)
        if text.width > 0.17:
            text.scale(0.17 / text.width)
        return VGroup(dot, text).set_z_index(7)

    def _p_spot(self) -> np.ndarray:
        """A free place on the P side for a pumped proton."""
        x0, y0, x1, y1 = self.p_box
        for _ in range(40):
            p = np.array([self.rng.uniform(x0, x1), self.rng.uniform(y0, y1), 0.0])
            if all(np.linalg.norm(p - d.get_center()) > 0.24 for d in self.protons) and \
                    not any(_inside(p, mob, 0.12) for mob in [*self.comp_mobs.values(), *self.avoid]):
                return p
        return p

    def _run_synthase(self) -> list[Animation]:
        s = self.setting_
        a = self.anchors["atp_synthase"]
        per = en.H_PER_ATP.get(s.membrane, 3.0)
        atp = max(1, int(self.state.gradient // per))
        used = min(len(self.protons), max(1, int(round(atp * per))))
        movers = sorted(self.protons, key=lambda d: np.linalg.norm(d.get_center() - a["p"]))[:used]
        paths = []
        _, A, U = self.frame["atp_synthase"]
        for k, dot in enumerate(movers):
            paths.append((dot, dot.get_center(), a["p"], a["e"], a["n"] - U * 0.3 * self.m, k / max(1, used) * 0.6))
        text = self.markup(f"{atp} ADP + {atp} P<sub>i</sub> → {atp} ATP" if atp > 1 else "ADP + P<sub>i</sub> → ATP", size=self.small * 0.92,
                           color=self.theme.palette_color(1))
        text.move_to(a["f1"] - A * (2.2 * self.m + _extent(text, A)))
        safe = self.safe_area
        if text.get_right()[0] > safe.x1:
            text.shift(LEFT * (text.get_right()[0] - safe.x1))
        if text.get_left()[0] < safe.x0:
            text.shift(RIGHT * (safe.x0 - text.get_left()[0]))
        reaction = VGroup(plate(text, self.bg, 0.05, 0.8), text)
        reaction.set_opacity(0.0)
        self.add(reaction)
        rotor = Arc(radius=0.55 * self.m, start_angle=0, angle=1.6 * math.pi, arc_center=a["rotor"]).set_stroke(self.ink, width=2.4)
        rotor_tip = Triangle().set_fill(self.ink, opacity=1).set_stroke(width=0).scale(0.06).move_to(rotor.get_end())
        spin = VGroup(rotor, rotor_tip)
        rotor.set_stroke(opacity=0.0)
        rotor_tip.set_fill(opacity=0.0)
        self.add(spin)
        start = dict(getattr(self, "tally_values", {}))
        old = list(self.dynamic)
        center = a["rotor"]

        def frame(alpha: float) -> None:
            for dot, p0, p1, p2, p3, lag in paths:
                u = min(1.0, max(0.0, (alpha - lag) / 0.4))
                if u < 0.4:
                    pos = p0 + (p1 - p0) * smooth(u / 0.4)
                elif u < 0.8:
                    pos = p1 + (p2 - p1) * ((u - 0.4) / 0.4)
                else:
                    pos = p2 + (p3 - p2) * ((u - 0.8) / 0.2)
                dot.move_to(pos)
                dot.set_opacity(0.0 if u >= 1.0 else 1.0)
            on = 1.0 if 0.02 < alpha < 0.98 else 0.0
            rotor.set_stroke(opacity=on)
            rotor_tip.set_fill(opacity=on)
            spin.rotate(-0.25, about_point=center)
            reaction.set_opacity(min(1.0, max(0.0, (alpha - 0.5) * 4)))
            for mob in old:
                mob.set_opacity(max(0.0, 1 - alpha * 4))
            if hasattr(self, "tally_values"):
                self.tally_values.update(start)
                self._count("ATP", int(round(atp * min(1.0, max(0.0, (alpha - 0.3) / 0.6)))))
                self._show_tallies()

        moving = VGroup(*movers, reaction, spin, *old)
        if hasattr(self, "tally_digits"):
            moving.add(*[d for digits in self.tally_digits.values() for d in digits.values()])
        self.protons.remove(*movers)
        self.dynamic.remove(*old)
        self.dynamic.add(reaction)
        self.state.gradient = max(0, self.state.gradient - used)
        return [driven(moving, frame, rate_func=linear)]


def _extent(mob: Mobject, direction: np.ndarray) -> float:
    """How far ``mob`` reaches from its centre along an axis ``direction``."""
    return float(abs(direction[0]) * mob.width / 2 + abs(direction[1]) * mob.height / 2)


def _clear_of(mob: Mobject, at: np.ndarray, direction: np.ndarray, gap: float, obstacles: list[Mobject]) -> None:
    """Put ``mob`` beside ``at`` towards ``direction`` (its near edge ``gap`` away), moved on
    along it until it covers none of ``obstacles``."""
    d = direction / (np.linalg.norm(direction) or 1.0)
    reach = abs(d[0]) * mob.width / 2 + abs(d[1]) * mob.height / 2
    for k in range(40):
        mob.move_to(at + d * (gap + reach + 0.06 * k))
        if not any(_overlaps(mob, o) for o in obstacles):
            return


def _inside(p: np.ndarray, mob: Mobject, pad: float) -> bool:
    return bool(mob.get_left()[0] - pad < p[0] < mob.get_right()[0] + pad and mob.get_bottom()[1] - pad < p[1] < mob.get_top()[1] + pad)


def _overlaps(a: Mobject, b: Mobject) -> bool:
    return bool(a.get_left()[0] < b.get_right()[0] and b.get_left()[0] < a.get_right()[0]
                and a.get_bottom()[1] < b.get_top()[1] and b.get_bottom()[1] < a.get_top()[1])
