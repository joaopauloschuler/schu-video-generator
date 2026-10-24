"""What the ``pathway`` actions draw (DESIGN.md §95.12): a signal running along the arcs wave by
wave (each arc lit as it passes, its target lit, GDP swapped for GTP, phosphorylation marks
appearing), an inhibitor engaging, a knockout or a drug with the effects downstream (↑ / ↓ on
each node that changes, from ``vidgen.cellworld.pathway.effects``), amplification (one
enzyme, many messengers) and the camera's ``focus``. A mixin of the ``pathway`` scene; every
change is remembered so ``until:`` can undo it. Things that appear part-way through an action
are made invisible before it starts (Manim adds an animation's mobjects when it begins)."""

from collections.abc import Callable
from typing import Any

import numpy as np

from vidgen.api import *

#: Opacity of a node's fill when lit, of a node turned off, and of an inhibited node.
LIT, OFF, HELD = 0.85, 0.3, 0.45
LIT_STROKE = 4.4
#: Seconds per wave of a signal.
WAVE_SECONDS = 0.75
Undo = Callable[[], list[Animation]]


class Draw(Animation):
    """A path drawn from its start; empty (invisible) from the moment it is made."""

    def __init__(self, mobject: VMobject, **kwargs: Any) -> None:
        self.full = mobject.copy()
        mobject.pointwise_become_partial(self.full, 0, 0)
        super().__init__(mobject, **kwargs)

    def interpolate_mobject(self, alpha: float) -> None:
        self.mobject.pointwise_become_partial(self.full, 0, self.rate_func(alpha))


class Appear(Animation):
    """A mobject faded in to its look; invisible from the moment it is made (``grow``: it also
    grows from that share of its size)."""

    def __init__(self, mobject: Mobject, grow: float = 1.0, **kwargs: Any) -> None:
        self.members = [m for m in mobject.family_members_with_points() if isinstance(m, VMobject)]
        self.looks = [(m.fill_rgbas.copy(), m.stroke_rgbas.copy()) for m in self.members]
        self.grow = grow
        self.center = mobject.get_center()
        self.points = [m.points.copy() for m in self.members]
        super().__init__(mobject, **kwargs)
        self._paint(0.0)

    def _paint(self, a: float) -> None:
        s = self.grow + (1 - self.grow) * a
        for m, (fill, stroke), pts in zip(self.members, self.looks, self.points):
            f, k = fill.copy(), stroke.copy()
            f[:, 3] *= a
            k[:, 3] *= a
            m.fill_rgbas, m.stroke_rgbas = f, k
            if self.grow != 1.0:
                m.points = self.center + (pts - self.center) * s

    def interpolate_mobject(self, alpha: float) -> None:
        self._paint(self.rate_func(alpha))


class PathwayPlay:
    """The ``pathway`` scene's runtime of its actions (needs the scene's drawing: ``nodes``,
    ``edges``, ``pathway``, ``status``…)."""

    # ----- looks ------------------------------------------------------------------------------

    def _shape_goal(self, nid: str, look: str) -> VMobject:
        s = self  # type: Any
        shape = s.nodes[nid]["shape"]
        color = s.node_color[nid]
        goal = shape.copy()
        if look == "on":
            goal.set_fill(color, opacity=LIT).set_stroke(s.hi, width=3.4, opacity=1)
        elif look == "held":
            goal.set_fill(color, opacity=0.05).set_stroke(s.bad, width=2.6, opacity=0.85)
        elif look == "off":
            goal.set_fill(color, opacity=0.03).set_stroke(color, width=2.0, opacity=OFF)
        elif look == "down":
            goal.set_fill(color, opacity=0.06).set_stroke(color, width=2.2, opacity=0.55)
        else:   # rest
            goal.set_fill(color, opacity=0.12).set_stroke(color, width=2.6, opacity=1)
        return goal

    def _label_goal(self, nid: str, look: str) -> Mobject:
        s = self  # type: Any
        label = s.nodes[nid]["label"]
        goal = label.copy()
        color = s.node_color[nid]
        if look == "on":
            goal.set_color(text_color_on(mix_colors(color, s.bg, LIT))).set_opacity(1)
        elif look == "off":
            goal.set_color(s.ink).set_opacity(OFF + 0.1)
        elif look in ("held", "down"):
            goal.set_color(s.ink).set_opacity(0.55)
        else:
            goal.set_color(s.ink).set_opacity(1)
        return goal

    def _look(self, nid: str, look: str, undo: list[Undo]) -> list[Animation]:
        """Turn a node to ``look`` (on, held, off, down, rest), remembering how it was."""
        s = self  # type: Any
        parts = s.nodes[nid]
        shape, label = parts["shape"], parts["label"]
        if not s.on_screen_parts(shape):
            return []
        before_shape, before_label = shape.copy(), label.copy()
        undo.append(lambda: [Transform(shape, before_shape), Transform(label, before_label, rate_func=_swap)])
        return [Transform(shape, self._shape_goal(nid, look)), Transform(label, self._label_goal(nid, look), rate_func=_swap)]

    def _badge_swap(self, nid: str, show: list[str], hide: list[str], undo: list[Undo]) -> list[Animation]:
        """Show and hide state badges of a node (GDP → GTP, a P mark appearing)."""
        s = self  # type: Any
        parts = s.nodes[nid]
        anims: list[Animation] = []
        for key in show:
            if key in parts["badges"] and key not in parts["shown"]:
                badge = parts["badges"][key]
                anims.append(Appear(badge, grow=1.6))
                s.add(badge)
                parts["shown"].add(key)

                def unshow(badge: Mobject = badge, key: str = key) -> list[Animation]:
                    parts["shown"].discard(key)
                    return [FadeOut(badge)]

                undo.append(unshow)
        for key in hide:
            if key in parts["shown"]:
                badge = parts["badges"][key]
                parts["shown"].discard(key)
                anims.append(FadeOut(badge))

                def reshow(badge: Mobject = badge, key: str = key) -> list[Animation]:
                    parts["shown"].add(key)
                    return [FadeIn(badge)]

                undo.append(reshow)
        return anims

    def _lit_edge(self, index: int, color: str, undo: list[Undo]) -> list[Animation]:
        s = self  # type: Any
        parts = s.edges[index]
        lit = parts["path"].copy().set_stroke(color, width=LIT_STROKE, opacity=1)
        lit.set_z_index(1)
        s.add(lit)
        head = parts["head"]
        before = head.copy()
        goal = head.copy().set_color(color)
        if isinstance(head, Circle):
            goal.set_fill(s.bg, opacity=1)
        undo.append(lambda: [FadeOut(lit), Transform(head, before)])
        return [Draw(lit, rate_func=linear), Transform(head, goal)]

    # ----- signal -----------------------------------------------------------------------------

    def signal_plan(self, targets: list[str], to: str | None, feedback: bool) -> list[list[Any]]:
        s = self  # type: Any
        return cell_pathway.signal_waves(s.pathway, targets, to, blocked=s.blocked_nodes(), feedback=feedback, path=len(targets) > 1)

    def signal_seconds(self, waves: list[list[Any]]) -> float:
        return max(1.0, WAVE_SECONDS * (len(waves) + 1))

    def run_signal(self, targets: list[str], waves: list[list[Any]]) -> tuple[list[Animation], Undo]:
        """The signal: its start nodes light, then each wave's arcs light as it passes and their
        targets change."""
        s = self  # type: Any
        undo: list[Undo] = []
        first = [a for t in dict.fromkeys(targets[:1] if len(targets) > 1 else targets) if t not in s.blocked_nodes()
                 for a in self._turn(t, 1, None, undo)]
        chain: list[Animation] = [AnimationGroup(*first)] if first else []
        for wave in waves:
            steps = []
            for step in wave:
                e = step.edge
                color = s.bad if (step.inhibits or e.sign < 0) else s.hi
                arc = self._lit_edge(e.index, color, undo)
                if step.blocked:
                    shape = s.nodes[e.target]["shape"]
                    node = [Indicate(shape, color=s.bad, scale_factor=1.12)]
                elif step.effect == 0:   # reached before: a new phosphorylated site still appears
                    site = e.site.text if e.type.name == "phosphorylates" and e.site is not None else None
                    node = self._badge_swap(e.target, [site], [], undo) if site else []
                else:
                    node = self._turn(e.target, step.effect, e, undo)
                steps.append(Succession(AnimationGroup(*arc), AnimationGroup(*node)) if node else AnimationGroup(*arc))
            chain.append(AnimationGroup(*steps))

        return ([Succession(*chain)] if chain else []), lambda: [a for x in reversed(undo) for a in x()]

    def _turn(self, nid: str, effect: int, edge: Any, undo: list[Undo]) -> list[Animation]:
        """A node reached by the signal: on (lit; GTP for a GTPase; its new P mark) or off
        (an inhibited node dims; a GTPase goes back to GDP)."""
        s = self  # type: Any
        n = s.pathway.nodes[nid]
        anims = self._look(nid, "on" if effect > 0 else "held", undo)
        show, hide = [], []
        if n.guanine:
            show, hide = (["gtp"], ["gdp"]) if effect > 0 else (["gdp"], ["gtp"])
        if edge is not None and edge.type.name == "phosphorylates" and edge.site is not None:
            show.append(edge.site.text)
        return anims + self._badge_swap(nid, show, hide, undo)

    # ----- knockout, drug, inhibitor ----------------------------------------------------------

    def effect_plan(self, now_off: list[str]) -> dict[str, str]:
        s = self  # type: Any
        return cell_pathway.effects(s.pathway, s.off_nodes() | s.held, set(now_off))

    def _effect_badge(self, nid: str, word: str) -> VGroup:
        s = self  # type: Any
        parts = s.nodes[nid]
        u = s.us
        r = 0.17 * u
        color = s.good if word == "up" else s.bad
        disc = Circle(radius=r).set_fill(color, opacity=1).set_stroke(s.bg, width=2)
        sign = 1 if word == "up" else -1
        tri = Polygon(np.array([0, sign * 0.55 * r, 0]), np.array([0.5 * r, -sign * 0.35 * r, 0]), np.array([-0.5 * r, -sign * 0.35 * r, 0]))
        tri.set_fill(text_color_on(color), opacity=1).set_stroke(width=0)
        if word == "off":
            tri = VGroup(Line(np.array([-0.45 * r, 0, 0]), np.array([0.45 * r, 0, 0])).set_stroke(text_color_on(color), width=3))
        c = parts["center"]   # at the bottom-left corner: the state badges are along the top, the arcs' ports mid-side
        badge = VGroup(disc, tri).move_to(np.array([c[0] - parts["w"] / 2 + 0.05 * u, c[1] - parts["h"] / 2, 0]))
        badge.set_z_index(4)
        return badge

    def _show_effects(self, found: dict[str, str], undo: list[Undo]) -> list[Animation]:
        """↑ / ↓ badges (and the look) on each node that changes, upstream first."""
        s = self  # type: Any
        order = cell_pathway.topological(s.pathway)
        anims: list[Animation] = []
        s.effect_badges = getattr(s, "effect_badges", {})
        for nid in sorted(found, key=order.index):
            word = found[nid]
            badge = self._effect_badge(nid, word)
            own: list[Animation] = []
            old = s.effect_badges.get(nid)
            if old is not None and old in s.mobjects:
                own.append(FadeOut(old))
            own.append(Appear(badge, grow=0.3))
            s.add(badge)
            s.effect_badges[nid] = badge

            def drop(badge: VGroup = badge, nid: str = nid, old: Any = old) -> list[Animation]:
                s.effect_badges[nid] = old
                return [FadeOut(badge)] + ([FadeIn(old)] if old is not None else [])

            undo.append(drop)
            look = {"up": "on", "down": "down", "off": "off"}[word]
            if s.pathway.nodes[nid].guanine:   # more GTP-bound, or back to GDP
                own += self._badge_swap(nid, ["gtp"], ["gdp"], undo) if word == "up" else self._badge_swap(nid, ["gdp"], ["gtp"], undo)
            anims.append(AnimationGroup(*own, *self._look(nid, look, undo)))
        return [LaggedStart(*anims, lag_ratio=0.35)] if anims else []

    def _cross(self, nid: str) -> VGroup:
        s = self  # type: Any
        parts = s.nodes[nid]
        c, w, h = parts["center"], parts["w"], parts["h"]
        a, b = w / 2 + 0.06 * s.us, h / 2 + 0.06 * s.us
        cross = VGroup(Line(c + np.array([-a, -b, 0]), c + np.array([a, b, 0])), Line(c + np.array([-a, b, 0]), c + np.array([a, -b, 0])))
        cross.set_stroke(s.bad, width=5)
        cross.set_z_index(0.5)    # over the node's shape, under its name (still readable)
        return cross

    def run_knockout(self, nid: str, show_effects: bool) -> tuple[list[Animation], Undo]:
        s = self  # type: Any
        undo: list[Undo] = []
        found = self.effect_plan([nid]) if show_effects else {}
        cross = self._cross(nid)
        s.add(cross)
        draws = [Draw(line) for line in cross]
        undo.append(lambda: [FadeOut(cross)])
        first = AnimationGroup(*self._look(nid, "off", undo), LaggedStart(*draws, lag_ratio=0.4))
        s.knocked.add(nid)
        chain = [first, *self._show_effects(found, undo)]

        def back() -> list[Animation]:
            s.knocked.discard(nid)
            return [a for u in reversed(undo) for a in u()]

        return [Succession(*chain)], back

    def free_spot_near(self, nid: str, w: float, h: float, gap: float) -> np.ndarray:
        """Where a ``w`` × ``h`` thing (a drug's pill, an amplification factor) goes beside node
        ``nid``: the place round it covering the fewest nodes, marks, labels and arcs, inside
        the frame (deterministic)."""
        s = self  # type: Any
        parts = s.nodes[nid]
        whole = VGroup(parts["shape"], *parts["badges"].values())    # with its badges
        c, nw, nh = whole.get_center(), whole.width, whole.height
        ax, ay = nw / 2 + gap + w / 2, nh / 2 + gap + h / 2
        offsets = [(0, ay), (0, -ay), (-ax, 0), (ax, 0), (-ax + w / 2, ay), (ax - w / 2, ay), (-ax + w / 2, -ay), (ax - w / 2, -ay),
                   (-ax, ay), (ax, ay), (-ax, -ay), (ax, -ay)]
        boxes, points = s._obstacles()
        boxes = boxes + list(getattr(s, "label_boxes", [])) + list(getattr(s, "placed_boxes", []))
        spot = s._spot([c + np.array([dx, dy, 0]) for dx, dy in offsets], w, h, boxes, points)
        s.placed_boxes = [*getattr(s, "placed_boxes", []), (spot[0] - w / 2, spot[1] - h / 2, spot[0] + w / 2, spot[1] + h / 2, 3.0)]
        return spot

    def run_drug(self, nid: str, name: str, show_effects: bool) -> tuple[list[Animation], Undo]:
        s = self  # type: Any
        undo: list[Undo] = []
        u = s.us
        text = s.markup(name, size=s.small0 * max(s.plan["small"] * s.scale_, readable_size() * 1.02 / s.small0), color=s.ink)
        pill = RoundedRectangle(width=text.width + 0.3 * u, height=text.height + 0.18 * u, corner_radius=(text.height + 0.18 * u) / 2 - 1e-4)
        pill.set_fill(mix_colors(s.bad, s.bg, 0.22), opacity=1).set_stroke(s.bad, width=2.4)
        text.set_color(text_color_on(mix_colors(s.bad, s.bg, 0.22)))
        spot = self.free_spot_near(nid, pill.width, pill.height, 0.25 * u)
        drug = VGroup(pill, text.move_to(pill)).move_to(spot)
        parts = s.nodes[nid]
        whole = VGroup(parts["shape"], *parts["badges"].values())    # the node with its badges
        c = whole.get_center()
        d = c - spot
        # the T-bar from the pill's edge to the node's
        direction = d / max(np.linalg.norm(d), 1e-9)
        start = spot + direction * _reach(pill.width, pill.height, direction)
        end = c - direction * (_reach(whole.width, whole.height, direction) + 0.04 * u)
        side = np.array([-direction[1], direction[0], 0])
        bar = VGroup(Line(start, end), Line(end + side * 0.14 * u, end - side * 0.14 * u)).set_stroke(s.bad, width=3.4)
        group = VGroup(drug, bar)
        group.set_z_index(6)
        s.add(drug, bar)
        appear = [Appear(drug, grow=0.5), Draw(bar[0]), Draw(bar[1])]
        undo.append(lambda: [FadeOut(group)])
        found = self.effect_plan([nid]) if show_effects else {}
        s.drugged[nid] = name
        s.drug_marks = getattr(s, "drug_marks", {})
        s.drug_marks[nid] = group
        chain = [Succession(appear[0], AnimationGroup(*appear[1:])), AnimationGroup(*self._look(nid, "off", undo)),
                 *self._show_effects(found, undo)]

        def back() -> list[Animation]:
            s.drugged.pop(nid, None)
            return [a for x in reversed(undo) for a in x()]

        return [Succession(*chain)], back

    def run_inhibit(self, nid: str, on: list[str], show_effects: bool) -> tuple[list[Animation], Undo]:
        s = self  # type: Any
        undo: list[Undo] = []
        arcs = [e for e in cell_pathway.inhibitor_arcs(s.pathway, nid) if not on or e.target in on]
        targets = [e.target for e in arcs]
        new = [t for t in targets if t not in s.off_nodes()]
        found = self.effect_plan(new) if show_effects else {}
        first = AnimationGroup(*self._look(nid, "on", undo))
        lit = AnimationGroup(*[a for e in arcs for a in self._lit_edge(e.index, s.bad, undo)])
        held = AnimationGroup(*[a for t in new for a in self._look(t, "held", undo)
                                + (self._badge_swap(t, ["gdp"], ["gtp"], undo) if s.pathway.nodes[t].guanine else [])])
        s.held |= set(new)
        chain = [first, lit, held, *self._show_effects(found, undo)]

        def back() -> list[Animation]:
            s.held -= set(new)
            return [a for x in reversed(undo) for a in x()]

        return [Succession(*chain)], back

    # ----- amplification ----------------------------------------------------------------------

    def amplify_source(self, nid: str, source: str | None) -> Any:
        """The arc the amplification runs along: from ``source``, else the node's first
        activating, non-feedback input."""
        s = self  # type: Any
        ins = [e for e in s.pathway.in_edges(nid) if e.sign > 0 and not e.feedback]
        if source is not None:
            ins = [e for e in ins if e.source == source]
        return ins[0] if ins else None

    def run_amplify(self, nid: str, source: str | None, count: int, factor: str | None) -> tuple[list[Animation], Undo]:
        s = self  # type: Any
        undo: list[Undo] = []
        edge = self.amplify_source(nid, source)
        parts = s.nodes[nid]
        c, w, h = parts["center"], parts["w"], parts["h"]
        color = s.node_color[nid]
        path = s.edges[edge.index]["path"]
        start = path.get_start()
        copies = []
        moves = []
        radius = 0.62 * max(w, h) + 0.15 * s.us
        for k in range(count):
            dot = parts["shape"].copy().scale(0.32).set_fill(color, opacity=0.9).set_stroke(color, width=1.2, opacity=1)
            dot.move_to(start)
            dot.set_z_index(5)
            angle = 2 * np.pi * k / count + np.pi / 2
            goal = c + np.array([radius * np.cos(angle) * 1.15, radius * np.sin(angle) * 0.85, 0])
            s.add(dot)
            copies.append(dot)
            trip = path.copy().add_line_to(goal)
            moves.append(Succession(Appear(dot, run_time=0.2), MoveAlongPath(dot, trip, run_time=1.0)))
        chain: list[Animation] = [LaggedStart(*moves, lag_ratio=0.12)]
        label = None
        if factor:
            text = s.markup(factor, size=max(s.small0 * s.plan["small"] * s.scale_, readable_size() * 1.02), color=s.ink, weight=BOLD)
            plate = RoundedRectangle(width=text.width + 0.2 * s.us, height=text.height + 0.12 * s.us, corner_radius=0.08 * s.us)
            plate.set_fill(s.bg, opacity=0.9).set_stroke(color, width=2)
            label = VGroup(plate, text.move_to(plate))
            label.move_to(self.free_spot_near(nid, label.width, label.height, 0.12 * s.us))
            label.set_z_index(6)
            s.add(label)
            chain.append(Appear(label, grow=0.6))
        chain.append(AnimationGroup(*[FadeOut(d) for d in copies]))
        undo.append(lambda: [FadeOut(label)] if label is not None else [])
        return [Succession(*chain)], lambda: [a for x in reversed(undo) for a in x()]

    # ----- camera -----------------------------------------------------------------------------

    def pathway_focus_view(self, targets: list[Target], padding: float, scale: float | None) -> tuple[float, np.ndarray]:
        """The camera view (width, centre) that shows ``targets`` with ``padding`` round them;
        the whole frame for ``pathway`` or when they fill it."""
        s = self  # type: Any
        fw, fh = s.frame_width, s.frame_height
        if any(t.name == "pathway" for t in targets):
            return fw, np.zeros(3)
        parts = [m for t in targets for m in (s.on_screen_parts(t) or [t.mobject])]
        group = Group(*parts)
        area = s.safe_area
        pad = 2 * padding * min(area.width, area.height)
        factor = scale if scale is not None else min(3.0, (area.width - pad) / max(group.width, 1e-6), (area.height - pad) / max(group.height, 1e-6))
        if factor <= 1.02:
            return fw, np.zeros(3)
        width, height = fw / factor, fh / factor
        wanted = group.get_center()[:2] - np.asarray(area.center[:2], dtype=float) / factor
        center = view_center_within(s.camera_bounds(), wanted, width, height)
        return width, np.array([*center, 0.0])


def _swap(t: float) -> float:
    """A label's colour changes quickly half-way through its node's change of fill, so it never
    sits half-way between two colours on a half-way fill (unreadable)."""
    return smooth(min(1.0, max(0.0, (t - 0.42) / 0.16)))


def _reach(w: float, h: float, direction: np.ndarray) -> float:
    """Distance from a box's centre to its edge along a unit ``direction``."""
    dx, dy = abs(float(direction[0])), abs(float(direction[1]))
    tx = (w / 2) / dx if dx > 1e-9 else float("inf")
    ty = (h / 2) / dy if dy > 1e-9 else float("inf")
    return min(tx, ty)
