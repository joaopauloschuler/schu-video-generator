"""A deterministic layout for a pedigree (DESIGN.md §96.8): generations are rows; a sibship sits in
birth order (YAML order, or the NSGC numbers) under its parents' mating line; a partner from
outside the family stands beside the relative (male left of female when nothing else decides);
each family is a block as wide as its widest generation, so lines never cross inside a tree. A
relative who marries a relative (consanguinity, or two families joined) is moved to the edge of
the sibship facing the partner, up to the common ancestors' sibship, where the two lines meet in
the middle — the mating line then crosses nothing. Positions are in units of the symbol pitch
(1 = one symbol and its gap); the scene scales them to its area. No manim."""

from __future__ import annotations

from dataclasses import dataclass

from vidgen.errors import VidgenError

from .pedigree import NSGC_ID, Couple, Pedigree, roman

#: Gap between the blocks of two siblings' families, and between unrelated families (pitch units).
FAMILY_GAP = 0.3
ROOT_GAP = 1.0


@dataclass(frozen=True)
class Layout:
    """Where each person stands: ``x`` (pitch units, the leftmost symbol's centre at 0.5) and
    ``row`` (its generation); ``order`` lists each row left to right; ``width`` is the extent."""

    x: dict[str, float]
    row: dict[str, int]
    order: tuple[tuple[str, ...], ...]
    width: float
    labels: dict[str, str]


@dataclass
class _Block:
    width: float
    x: dict[str, float]


class _Planner:
    def __init__(self, ped: Pedigree, where: str) -> None:
        self.ped = ped
        self.where = where
        people = ped.people
        self.has_parents = {p: people[p].parents is not None for p in people}
        self.order_key = {pid: i for i, pid in enumerate(people)}
        if ped.nsgc_ids:
            for pid in people:
                m = NSGC_ID.match(pid)
                assert m is not None
                self.order_key[pid] = int(m.group("num"))
        self.couples = list(ped.couples)
        self._anchors()
        self.pull: dict[str, str] = {}          # spouse side: "right" (spouse left) or "left" (spouse right)
        self.edge: dict[str, str] = {}          # position in the sibship: "right" (last) or "left" (first)
        self.after: list[tuple[str, str]] = []  # (a, b): b right after a in their sibship (or among roots)
        self._assign_joins()
        self._pulls()

    # ----- who anchors whom -------------------------------------------------------------------------

    def _anchors(self) -> None:
        """Anchors are the people drawn with a block of their own: everyone with parents on the
        chart, and one founder per cluster of founder partners. Everyone else stands beside their
        anchor partner."""
        ped = self.ped
        self.attached: dict[str, str] = {}
        anchors = [p for p in ped.people if self.has_parents[p]]
        founders = [p for p in ped.people if not self.has_parents[p]]
        for f in founders:
            partners = [ped.partner(c, f) for c in ped.couples_of(f)]
            blood = [x for x in partners if self.has_parents[x]]
            if blood:
                if len(blood) > 1:
                    raise VidgenError(f"{self.where}: {f} married into the family twice ({', '.join(blood)}): "
                                      f"not supported in one chart")
                self.attached[f] = blood[0]
        clusters: list[list[str]] = []
        seen: set[str] = set()
        for f in founders:
            if f in self.attached or f in seen:
                continue
            group, todo = [], [f]
            while todo:
                x = todo.pop()
                if x in seen:
                    continue
                seen.add(x)
                group.append(x)
                todo += [ped.partner(c, x) for c in ped.couples_of(x) if not self.has_parents[ped.partner(c, x)]]
            clusters.append(sorted(group, key=lambda x: self.order_key[x]))
        self.roots: list[str] = []
        for group in clusters:
            people = ped.people
            anchor = sorted(group, key=lambda x: (-len(ped.couples_of(x)), people[x].sex != "male", self.order_key[x]))[0]
            self.roots.append(anchor)
            for x in group:
                if x == anchor:
                    continue
                if not any(anchor in c.partners for c in ped.couples_of(x)):
                    raise VidgenError(f"{self.where}: {x} is the partner of a partner of {anchor}: chains of partners among "
                                      f"founders are not supported in one chart")
                self.attached[x] = anchor
        self.roots.sort(key=lambda x: min(self.order_key[y] for y in [x] + [k for k, v in self.attached.items() if v == x]))
        self.anchors = set(anchors) | set(self.roots)

    def _is_join(self, c: Couple) -> bool:
        return c.a in self.anchors and c.b in self.anchors

    def _dfs(self, owner: dict[frozenset[str], str]) -> list[str]:
        """Anchors in preorder: roots, then each couple's children (join couples' children under
        the partner that owns them, once known)."""
        out: list[str] = []

        def walk(a: str) -> None:
            out.append(a)
            for c in self.ped.couples_of(a):
                if self._is_join(c) and owner.get(frozenset(c.partners)) != a:
                    continue
                for child in sorted(c.children, key=lambda x: self.order_key[x]):
                    if child not in out:
                        walk(child)

        for r in self.roots:
            walk(r)
        return out

    def _assign_joins(self) -> None:
        """Each join couple's children belong to the partner reached later in preorder."""
        self.owner: dict[frozenset[str], str] = {}
        joins = [c for c in self.couples if self._is_join(c)]
        for _ in range(len(joins) + 1):
            pre = self._dfs(self.owner)
            index = {a: i for i, a in enumerate(pre)}
            changed = False
            for c in joins:
                key = frozenset(c.partners)
                if key in self.owner or c.a not in index or c.b not in index:
                    continue
                self.owner[key] = c.a if index[c.a] > index[c.b] else c.b
                changed = True
            if not changed:
                break
        missing = [c for c in joins if frozenset(c.partners) not in self.owner]
        if missing:
            c = missing[0]
            raise VidgenError(f"{self.where}: {c.a} and {c.b} cannot be placed (their families are not connected to the top of the chart)")
        self.preorder = self._dfs(self.owner)
        for a in self.anchors:
            if a not in self.preorder:
                raise VidgenError(f"{self.where}: {a} is not connected to the chart's founders")

    def parent_anchor(self, x: str) -> str | None:
        c = self.ped.couple_of_parents(x)
        if c is None:
            return None
        if self._is_join(c):
            return self.owner[frozenset(c.partners)]
        return c.a if c.a in self.anchors else c.b

    def _chain(self, x: str) -> list[str]:
        out = [x]
        while (up := self.parent_anchor(out[-1])) is not None:
            out.append(up)
        return out

    def _pulls(self) -> None:
        index = {a: i for i, a in enumerate(self.preorder)}
        for c in self.couples:
            if not self._is_join(c):
                continue
            p, q = sorted(c.partners, key=lambda x: index[x])
            cp, cq = self._chain(p), self._chain(q)
            meet = None
            for i, a in enumerate(cp):
                for j, b in enumerate(cq):
                    same_couple = (self.ped.couple_of_parents(a) is not None
                                   and self.ped.couple_of_parents(a) == self.ped.couple_of_parents(b))
                    if a != b and (same_couple or (self.parent_anchor(a) is None and self.parent_anchor(b) is None)):
                        meet = (i, j)
                        break
                if meet:
                    break
            i, j = meet if meet else (len(cp) - 1, len(cq) - 1)
            for k, a in enumerate(cp[:i + 1]):
                self.pull.setdefault(a, "right")
                if k < i:
                    self.edge.setdefault(a, "right")
            for k, b in enumerate(cq[:j + 1]):
                self.pull.setdefault(b, "left")
                if k < j:
                    self.edge.setdefault(b, "left")
            if meet:
                self.after.append((cp[i], cq[j]))

    # ----- ordering ---------------------------------------------------------------------------------

    def ordered(self, items: list[str]) -> list[str]:
        """Children (or roots) in birth order, then twins together, people pulled to an edge at
        it, and the two lines of a consanguineous couple side by side."""
        out = sorted(items, key=lambda x: self.order_key[x])
        people = self.ped.people
        for x in list(out):
            t = people[x].twin
            if t in out and out.index(t) > out.index(x) + 1:
                out.remove(t)
                out.insert(out.index(x) + 1, t)
        lefts = [x for x in out if self.edge.get(x) == "left"]
        rights = [x for x in out if self.edge.get(x) == "right"]
        out = lefts + [x for x in out if x not in lefts and x not in rights] + rights
        for a, b in self.after:
            if a in out and b in out:
                out.remove(b)
                out.insert(out.index(a) + 1, b)
        return out

    def spouse_left(self, anchor: str, spouse: str) -> bool:
        if self.ped.nsgc_ids:
            return self.order_key[spouse] < self.order_key[anchor]
        side = self.pull.get(anchor)
        if side is not None:
            return side == "right"
        return self.ped.people[spouse].sex == "male"

    # ----- blocks -----------------------------------------------------------------------------------

    def group(self, children: list[str]) -> _Block:
        x: dict[str, float] = {}
        left = 0.0
        prev: str | None = None
        for child in self.ordered(children):
            if prev is not None:
                twins = self.ped.people[child].twin == prev or self.ped.people[prev].twin == child
                left += 0.0 if twins else FAMILY_GAP
            b = self.block(child)
            x.update({k: v + left for k, v in b.x.items()})
            left += b.width
            prev = child
        return _Block(left, x)

    def block(self, a: str) -> _Block:
        ped = self.ped
        spouse_groups: list[tuple[str, list[str]]] = []
        joins: list[list[str]] = []
        for c in ped.couples_of(a):
            s = ped.partner(c, a)
            if self._is_join(c):
                if self.owner[frozenset(c.partners)] == a and c.children:
                    joins.append(list(c.children))
            elif self.attached.get(s) == a:
                spouse_groups.append((s, list(c.children)))
        x: dict[str, float] = {}
        left = 0.0
        for kids in joins:
            g = self.group(kids)
            x.update(g.x)
            left += g.width + FAMILY_GAP
        if not spouse_groups:
            x[a] = left + 0.5
            return _Block(left + 1.0, x)
        if len(spouse_groups) == 1:
            s, kids = spouse_groups[0]
            g = self.group(kids) if kids else _Block(0.0, {})
            core = max(2.0, g.width)
            mid = left + core / 2
            s_left = self.spouse_left(a, s)
            x[s] = mid - 0.5 if s_left else mid + 0.5
            x[a] = mid + 0.5 if s_left else mid - 0.5
            x.update({k: v + mid - g.width / 2 for k, v in g.x.items()})
            return _Block(left + core, x)
        (s1, k1), (s2, k2) = spouse_groups
        if self.spouse_left(a, s2) and not self.spouse_left(a, s1):
            (s1, k1), (s2, k2) = (s2, k2), (s1, k1)
        g1 = self.group(k1) if k1 else _Block(1.0, {})
        g2 = self.group(k2) if k2 else _Block(1.0, {})
        c1 = g1.width / 2
        gap = FAMILY_GAP
        c2 = g1.width + gap + g2.width / 2
        if c2 - c1 < 1.0:
            gap += 1.0 - (c2 - c1)
            c2 = g1.width + gap + g2.width / 2
        p = (c1 + c2) / 2
        local = {s1: 2 * c1 - p, a: p, s2: 2 * c2 - p}
        local.update(g1.x)
        local.update({k: v + g1.width + gap for k, v in g2.x.items()})
        lo = min(0.0, local[s1] - 0.5)
        hi = max(g1.width + gap + g2.width, local[s2] + 0.5)
        x.update({k: v - lo + left for k, v in local.items()})
        return _Block(left + hi - lo, x)

    def roots_block(self) -> _Block:
        roots = self.ordered(self.roots) if self.after else list(self.roots)
        x: dict[str, float] = {}
        left = 0.0
        for k, r in enumerate(roots):
            if k:
                left += ROOT_GAP
            b = self.block(r)
            x.update({key: v + left for key, v in b.x.items()})
            left += b.width
        return _Block(left, x)


def layout_pedigree(ped: Pedigree, where: str = "params.individuals") -> Layout:
    """Positions for every person (deterministic: the same chart always gives the same picture),
    and the NSGC labels (``II-3``: generation, then the number left to right; the author's own
    when the ids are NSGC labels, which must then read left to right as drawn)."""
    planner = _Planner(ped, where)
    block = planner.roots_block()
    x = dict(block.x)
    if set(x) != set(ped.people):
        missing = sorted(set(ped.people) - set(x), key=lambda p: planner.order_key[p])
        raise VidgenError(f"{where}: {', '.join(missing)} could not be placed (not connected to the chart's families)")
    lo = min(x.values()) - 0.5
    x = {k: round(v - lo, 6) for k, v in x.items()}
    width = max(x.values()) + 0.5
    rows: list[list[str]] = [[] for _ in range(ped.rows)]
    for pid in ped.people:
        rows[ped.generation[pid]].append(pid)
    order = tuple(tuple(sorted(r, key=lambda p: (x[p], planner.order_key[p]))) for r in rows)
    for r in order:
        for a, b in zip(r, r[1:]):
            if x[b] - x[a] < 0.999:
                raise VidgenError(f"{where}: {a} and {b} overlap in this layout (a family shape the layout does not handle)")
    labels: dict[str, str] = {}
    if ped.nsgc_ids:
        for g, r in enumerate(order):
            nums = [int(p.split("-")[1]) for p in r if not ped.people[p].proposed]
            if nums != sorted(nums):
                drawn = ", ".join(p for p in r if not ped.people[p].proposed)
                raise VidgenError(f"{where}: generation {roman(g + 1)} is drawn {drawn} (left to right: sibships in birth order, "
                                  f"a partner from outside beside the relative): number them left to right as drawn, or use "
                                  f"other ids and let schu-video-generator number the chart")
        labels = {p: p for p in ped.people}
    else:
        for g, r in enumerate(order):
            k = 0
            for p in r:
                if ped.people[p].proposed:
                    labels[p] = "?"
                    continue
                k += 1
                labels[p] = f"{roman(g + 1)}-{k}"
    return Layout(x, dict(ped.generation), order, width, labels)


__all__ = ["FAMILY_GAP", "Layout", "ROOT_GAP", "layout_pedigree"]
