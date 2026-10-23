"""Drawing helpers shared by the ``cell_cycle`` and ``metabolism`` scenes (DESIGN.md §95.13):
captions wrapped by width, regulation rows in SBGN-like notation (nodes with activation arrows
and inhibition T-bars, P and Ub marks on the arcs), small labels on plates, and an animation
driven by a function of its progress. Written against ``vidgen.api``."""

import re
from collections.abc import Callable
from typing import Any

import numpy as np

from vidgen.api import *


def small_size(scene: Any, token: str = "caption") -> float:
    """A small text size: the theme's ``token`` size, never below the readable minimum."""
    return max(float(scene.theme.size(token)), readable_size() * 1.02)


def text_block(scene: Any, text: str, width: float, size: float, color: Any = "text", weight: str = NORMAL,
               align: Any = LEFT) -> VGroup:
    """Markup wrapped at spaces to ``width`` (measured; lines aligned ``align``), shrunk only if
    one word is wider than that."""
    words = text.split(" ")
    rows: list[Mobject] = []

    def balanced(s: str, opened: list[str]) -> tuple[str, list[str]]:
        """``s`` after the tags ``opened`` before it, with the tags still open closed at its end."""
        stack = list(opened)
        for m in re.finditer(r"<(/?)([a-z]+)[^>]*>", s):
            if m.group(1):
                if stack and stack[-1] == m.group(2):
                    stack.pop()
            else:
                stack.append(m.group(2))
        full = "".join(f"<{t}>" for t in opened) + s + "".join(f"</{t}>" for t in reversed(stack))
        return full, stack

    line, opened = "", []
    made: Mobject | None = None
    for w in words:
        trial = f"{line} {w}" if line else w
        mob = scene.markup(balanced(trial, opened)[0], size=size, color=color, weight=weight)
        if line and mob.width > width:
            rows.append(made if made is not None else mob)
            opened = balanced(line, opened)[1]
            line = w
            made = scene.markup(balanced(w, opened)[0], size=size, color=color, weight=weight)
        else:
            line, made = trial, mob
    if line:
        rows.append(made if made is not None else scene.markup(balanced(line, opened)[0], size=size, color=color, weight=weight))
    group = VGroup(*rows).arrange(DOWN, buff=0.08 * size / 24, aligned_edge=align)
    if group.width > width:
        group.scale(width / group.width)
    return group


def plate(mob: Mobject, color: str, pad: float = 0.08, opacity: float = 0.85) -> RoundedRectangle:
    """A rounded plate in ``color`` behind ``mob``."""
    p = RoundedRectangle(width=mob.width + 2 * pad, height=mob.height + 1.4 * pad, corner_radius=min(0.08, mob.height / 2))
    p.set_fill(color, opacity=opacity).set_stroke(width=0).move_to(mob)
    return p


def arrow_head(tip: np.ndarray, direction: np.ndarray, size: float, color: str) -> Polygon:
    d = direction / (np.linalg.norm(direction) or 1.0)
    n = np.array([-d[1], d[0], 0.0])
    head = Polygon(tip, tip - d * size + n * size * 0.5, tip - d * size - n * size * 0.5)
    return head.set_fill(color, opacity=1).set_stroke(color, width=1)


class Row:
    """A regulation row drawn: ``nodes`` (each a VGroup of box and label), ``arcs`` (each a
    VGroup of line, head and mark), ``group`` (all)."""

    def __init__(self, nodes: list[VGroup], arcs: list[VGroup], group: VGroup) -> None:
        self.nodes, self.arcs, self.group = nodes, arcs, group


def regulation_row(scene: Any, row: Any, size: float, width: float, ink: str, bad: str, bg: str, box: str) -> Row:
    """A checkpoint's row (``vidgen.cellworld.cycle.Row``): nodes in rounded boxes, arcs
    between them (→ activates, ⊣ inhibits; a P or Ub disc on the arc), wrapped onto more lines
    when it is wider than ``width``."""
    u = size / 24
    labels = [scene.markup(n, size=size, color=ink) for n in row.nodes]
    boxes = []
    for lab in labels:
        b = RoundedRectangle(width=lab.width + 0.24 * u, height=lab.height + 0.2 * u, corner_radius=0.1 * u)
        b.set_fill(box, opacity=0.12).set_stroke(box, width=2.2)
        boxes.append(VGroup(b, lab.move_to(b)))
    arc_len = 0.62 * u
    total = sum(b.width for b in boxes) + arc_len * (len(boxes) - 1)
    indent = 0.0 if total <= width else 0.42 * u      # wrapped lines start after the connector's turn
    lines: list[list[int]] = [[]]
    x = indent
    for k, b in enumerate(boxes):
        need = b.width + (arc_len if lines[-1] else 0.0)
        if lines[-1] and x + need > width:
            lines.append([])
            x = indent
            need = b.width
        lines[-1].append(k)
        x += need
    y = 0.0
    for line in lines:
        x = indent
        for k in line:
            boxes[k].move_to(np.array([x + boxes[k].width / 2, y, 0.0]))
            x += boxes[k].width + arc_len
        y -= max(boxes[k].height for k in line) + 0.5 * u
    arcs = []
    for k, arc in enumerate(row.arcs):
        a, b = boxes[k], boxes[k + 1]
        same = any(k in line and k + 1 in line for line in lines)
        color = bad if arc.kind == "-|" else ink
        if same:
            start = a.get_right() + RIGHT * 0.05 * u
            end = b.get_left() + LEFT * 0.05 * u
            path = VMobject().set_points_as_corners([start, end])
        else:   # an elbow: out of the line's end, back under it, into the next line's start
            start = a.get_right() + RIGHT * 0.05 * u
            out = start + RIGHT * 0.18 * u
            between = (a.get_bottom()[1] + b.get_top()[1]) / 2
            end = b.get_left() + LEFT * 0.05 * u
            path = VMobject().set_points_as_corners([start, out, np.array([out[0], between, 0.0]),
                                                     np.array([indent / 2, between, 0.0]), np.array([indent / 2, end[1], 0.0]), end])
        path.set_stroke(color, width=2.6)
        d = path.points[-1] - path.points[-2]
        d = d / (np.linalg.norm(d) or 1.0)
        if arc.kind == "-|":
            n = np.array([-d[1], d[0], 0.0])
            head: VMobject = Line(end + n * 0.13 * u, end - n * 0.13 * u).set_stroke(color, width=3.6)
        else:
            head = arrow_head(end, d, 0.16 * u, color)
        parts: list[Mobject] = [path, head]
        if arc.mark:
            t = scene.markup(arc.mark, size=size * 0.7, color=ink)
            disc = Circle(radius=max(t.width, t.height) / 2 + 0.05 * u).set_fill(bg, opacity=1).set_stroke(scene.theme.color("highlight"), width=2)
            mid = path.point_from_proportion(0.5)
            disc.move_to(mid + UP * 0.2 * u if same else (path.points[8] + path.points[11]) / 2)
            parts += [disc, t.move_to(disc)]
        arcs.append(VGroup(*parts))
    group = VGroup(*boxes, *arcs)
    return Row(boxes, arcs, group)


def driven(group: Mobject, fn: Callable[[float], None], **kwargs: Any) -> Animation:
    """An animation of ``group`` whose frames ``fn(alpha)`` draws (alpha after the rate)."""

    def update(_: Mobject, alpha: float) -> None:
        fn(alpha)

    return UpdateFromAlphaFunc(group, update, **kwargs)
