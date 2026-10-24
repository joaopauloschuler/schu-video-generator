"""Playing transport plans in a ``molecule`` scene (DESIGN.md §95.10): the renderer of the plans
of :mod:`vidgen.cellworld.transport`. One :class:`PlanPlayer` animation runs a whole plan: the
proteins morph between their states (each piece of a glyph to its counterpart in the next state,
pieces without one fading out or in), particles follow their planned paths (fading in where they
come from the bulk, out where they react), captions change with the phases, a voltage readout,
an inset plot of the membrane potential and the membrane's charges follow the plan's trace.
Everything the animation shows is in the scene before it starts (Manim draws an animation's
family as it was when it began)."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vidgen.api import *

Prim, Move, Plan = MoleculePrim, cell_transport.Move, cell_transport.Plan

#: Captions sit on a plate this opaque.
NOTE_PLATE = 0.86


def smooth(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _look(p: Prim) -> tuple[Any, ...]:
    """What makes two prims counterparts in a morph: their text, or their fill, tone and stroke."""
    return ("text", p.text) if p.text else (p.fill, p.tone, p.stroke, round(p.px, 3), round(p.nm, 4))


def match_prims(old: Sequence[Prim], new: Sequence[Prim]) -> list[tuple[int | None, int | None]]:
    """Pairs of indices of ``old`` and ``new`` prims that are the same piece in two states (the
    same look, in order); a prim without a counterpart is paired with ``None``."""
    pending: dict[tuple[Any, ...], list[int]] = {}
    for k, p in enumerate(old):
        pending.setdefault(_look(p), []).append(k)
    pairs: list[tuple[int | None, int | None]] = []
    for j, p in enumerate(new):
        queue = pending.get(_look(p))
        pairs.append((queue.pop(0), j) if queue else (None, j))
    pairs += [(k, None) for queue in pending.values() for k in queue]
    return pairs


@dataclass
class Live:
    """A molecule as planned to be drawn: its prims (placed, nm) and their mobjects, in the same
    order, and each mobject's full opacities (``rest``, by id)."""

    prims: list[Prim]
    mobs: list[Mobject]
    rest: dict[int, list[tuple[Mobject, float, float]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for mob in self.mobs:
            self.rest.setdefault(id(mob), _opacities(mob))


def _opacities(mob: Mobject) -> list[tuple[Mobject, float, float]]:
    out = []
    for m in mob.get_family():
        if isinstance(m, VMobject) and len(m.points):
            out.append((m, float(m.get_fill_opacity()), float(m.get_stroke_opacity())))
    return out


def _fade(items: list[tuple[Mobject, float, float]], factor: float) -> None:
    for m, fill, stroke in items:
        m.set_fill(opacity=fill * factor, family=False)
        m.set_stroke(opacity=stroke * factor, family=False)


@dataclass
class Segment:
    """One molecule's morph during a phase: pieces that change shape (``morphs``: the live
    mobject, its start and end copies), fade out (``outs``) or in (``ins``)."""

    morphs: list[tuple[VMobject, VMobject, VMobject]] = field(default_factory=list)
    shifts: list[tuple[Mobject, np.ndarray, np.ndarray]] = field(default_factory=list)
    outs: list[list[tuple[Mobject, float, float]]] = field(default_factory=list)
    ins: list[list[tuple[Mobject, float, float]]] = field(default_factory=list)
    dead: list[Mobject] = field(default_factory=list)
    owner: str = ""

    def play(self, t: float) -> None:
        u = smooth(t)
        for mob, start, end in self.morphs:
            mob.interpolate(start, end, u)
        for mob, a, b in self.shifts:
            mob.move_to(a + (b - a) * u)
        for items in self.outs:
            _fade(items, 1.0 - u)
        for items in self.ins:
            _fade(items, u)


def plan_morph(live: Live, new_prims: list[Prim], make: Callable[[Sequence[Prim]], list[Mobject]], group: Mobject) -> Segment:
    """The morph of ``live`` (as planned so far) to ``new_prims`` (placed, nm): counterparts
    change shape (texts move), the others fade; ``live`` becomes the new state and new pieces
    are added to ``group`` (unseen until the morph shows them)."""
    seg = Segment()
    new_mobs = make(new_prims)
    now = make(live.prims)              # the shapes as the earlier morphs leave them
    mobs: list[Mobject | None] = [None] * len(new_prims)
    for k, j in match_prims(live.prims, new_prims):
        if k is not None and j is not None:
            old_mob, new_mob = live.mobs[k], new_mobs[j]
            if new_prims[j].text:
                seg.shifts.append((old_mob, now[k].get_center(), new_mob.get_center()))
            else:
                start, end = now[k].copy(), new_mob.copy()
                start.align_points(end)
                seg.morphs.append((old_mob, start, end))  # type: ignore[arg-type]
            mobs[j] = old_mob
        elif j is not None:
            mob = new_mobs[j]
            items = _opacities(mob)
            live.rest[id(mob)] = items
            _fade(items, 0.0)
            group.add(mob)
            seg.ins.append(items)
            mobs[j] = mob
        elif k is not None:
            seg.outs.append(live.rest.get(id(live.mobs[k]), _opacities(live.mobs[k])))
            seg.dead.append(live.mobs[k])
    live.prims = list(new_prims)
    live.mobs = [m for m in mobs if m is not None]
    return seg


@dataclass
class Track:
    """A particle's mobject and its moves, by phase: ``(phase index, move)``; ``visible``: whether
    it is on screen when the plan starts."""

    mob: Mobject
    moves: list[tuple[int, Move]]
    visible: bool
    opacities: list[tuple[Mobject, float, float]] = field(default_factory=list)


class Hold(Animation):
    """Marks a mobject of the scene as changing during another animation (a :class:`PlanPlayer`
    changes it), so the renderer draws it every frame; it does nothing itself."""

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def interpolate_mobject(self, alpha: float) -> None:
        pass


class PlanPlayer(Animation):
    """Plays a :class:`~vidgen.cellworld.transport.Plan`: phase by phase (each its share of the
    time), the molecules' morphs, the particles' moves, the captions; ``extra`` callbacks get the
    plan's progress (0–1) every frame (a voltage readout, an inset plot). Its mobject is a group
    of the scene (the particles); the other mobjects it changes are held by :class:`Hold`."""

    def __init__(self, group: Mobject, plan: Plan, to_scene: Callable[[tuple[float, float]], np.ndarray], tracks: dict[str, Track],
                 segments: dict[int, list[Segment]], notes: list[Mobject | None], extra: Sequence[Callable[[float], None]] = (),
                 previous: Mobject | None = None, **kwargs: Any) -> None:
        super().__init__(group, rate_func=linear, **kwargs)
        self.plan, self.to_scene, self.tracks, self.segments, self.notes, self.extra = plan, to_scene, tracks, segments, notes, list(extra)
        self.previous = _opacities(previous) if previous is not None else []
        total = sum(p.weight for p in plan.phases) or 1.0
        edges = [0.0]
        for p in plan.phases:
            edges.append(edges[-1] + p.weight / total)
        self.edges = edges
        self.note_items = [(_opacities(n) if n is not None else []) for n in notes]
        for items in self.note_items:
            _fade(items, 0.0)
        self.done: set[int] = set()
        self.dead_parents: list[Mobject] = []

    def create_starting_mobject(self) -> Mobject:
        return self.mobject

    def interpolate_mobject(self, alpha: float) -> None:
        edges = self.edges
        for k in range(len(self.plan.phases)):
            a, b = edges[k], edges[k + 1]
            local = 1.0 if alpha >= b else 0.0 if alpha <= a else (alpha - a) / (b - a)
            if alpha <= a and k not in self.done:
                continue
            for seg in self.segments.get(k, []):
                seg.play(local)
            if local >= 1.0:
                self.done.add(k)
        for pid, track in self.tracks.items():
            self._place(track, alpha)
        for k, items in enumerate(self.note_items):
            if not items:
                continue
            a, b = edges[k], edges[k + 1]
            span = b - a
            ramp = min(0.12, span * 0.25)
            if alpha < a or alpha > b or span <= 0:
                factor = 0.0
            else:
                factor = min(1.0, (alpha - a) / ramp if ramp > 0 else 1.0, (b - alpha) / ramp if ramp > 0 and k < len(self.note_items) - 1 else 1.0)
            _fade(items, max(0.0, factor))
        _fade(self.previous, max(0.0, 1.0 - alpha / 0.04))
        for callback in self.extra:
            callback(alpha)

    def _place(self, track: Track, alpha: float) -> None:
        """A particle's place and opacity at ``alpha``: on its current move's path, else where its
        last move ended (or its first starts)."""
        point = None
        factor = 1.0 if track.visible else 0.0
        for phase, move in track.moves:
            a, b = self.edges[phase], self.edges[phase + 1]
            start = a + (b - a) * move.t0
            end = a + (b - a) * move.t1
            if alpha < start:
                if point is None:
                    point = move.path[0]
                break
            t = 1.0 if alpha >= end or end <= start else (alpha - start) / (end - start)
            point = _along(move.path, smooth(t))
            if move.appear:
                factor = min(1.0, t / 0.2)
            if move.vanish:
                factor = 0.0 if t >= 1.0 else factor if t < 0.75 else min(factor, (1.0 - t) / 0.25)
        if point is None:
            return
        track.mob.move_to(self.to_scene(point))
        _fade(track.opacities, factor)

    def clean_up_from_scene(self, scene: Any) -> None:
        super().clean_up_from_scene(scene)
        for segs in self.segments.values():
            for seg in segs:
                for mob in seg.dead:
                    for parent in self.dead_parents:
                        if mob in parent.submobjects:
                            parent.remove(mob)


def _along(path: Sequence[tuple[float, float]], t: float) -> tuple[float, float]:
    """The point ``t`` (0–1) of the way along a polyline, by length."""
    if len(path) == 1 or t <= 0:
        return path[0]
    lengths = [math.dist(a, b) for a, b in zip(path, path[1:])]
    total = sum(lengths)
    if total <= 1e-12:
        return path[-1]
    goal = t * total
    for (a, b), d in zip(zip(path, path[1:]), lengths):
        if goal <= d:
            u = goal / d if d > 0 else 1.0
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        goal -= d
    return path[-1]


class Digits:
    """A number readout made of digit glyphs made once and shown or hidden (a text cannot be
    swapped during an animation): ``prefix`` then a sign and up to ``places`` digits, ``suffix``."""

    def __init__(self, scene: NarratedScene, prefix: str, suffix: str, places: int, size: Any) -> None:
        self.head = scene.markup(prefix, size=size, color="text")
        self.tail = scene.markup(suffix, size=size, color="text")
        self.glyphs = [[scene.text(ch, size=size, color="text") for ch in "0123456789"] for _ in range(places)]
        self.signs = {s: scene.text(s, size=size, color="text") for s in ("−", "+")}
        w = max(g.width for row in self.glyphs for g in row)
        self.digit_w = w * 1.05
        self.sign_w = max(m.width for m in self.signs.values()) * 1.1
        self.places = places
        self.group = VGroup(self.head, *self.signs.values(), *[g for row in self.glyphs for g in row], self.tail)

    def width(self) -> float:
        return self.head.width + 0.08 + self.sign_w + self.digit_w * self.places + 0.08 + self.tail.width

    def place(self, left: np.ndarray) -> None:
        y = float(left[1])
        x = float(left[0])
        self.head.move_to([x + self.head.width / 2, y, 0.0])
        x += self.head.width + 0.08
        for m in self.signs.values():
            m.move_to([x + self.sign_w / 2, y, 0.0])
        x += self.sign_w
        for row in self.glyphs:
            for g in row:
                g.move_to([x + self.digit_w / 2, y, 0.0])
            x += self.digit_w
        self.tail.move_to([x + 0.08 + self.tail.width / 2, y, 0.0])

    def show(self, value: float) -> None:
        n = int(round(value))
        text = str(abs(n)).rjust(self.places)[-self.places:]
        for sign, m in self.signs.items():
            m.set_opacity(1.0 if (sign == "−" and n < 0) or (sign == "+" and n > 0) else 0.0)
        for row, ch in zip(self.glyphs, text):
            for k, g in enumerate(row):
                g.set_opacity(1.0 if ch != " " and int(ch) == k else 0.0)


def voltage_at(trace: Sequence[tuple[float, float]], alpha: float) -> float:
    """The trace's value (mV) at ``alpha`` (a share of the plan)."""
    if alpha <= trace[0][0]:
        return trace[0][1]
    for (a, va), (b, vb) in zip(trace, trace[1:]):
        if alpha <= b:
            return va + (vb - va) * ((alpha - a) / (b - a) if b > a else 1.0)
    return trace[-1][1]


__all__ = ["Digits", "Hold", "Live", "PlanPlayer", "Segment", "Track", "match_prims", "plan_morph", "smooth", "voltage_at"]
