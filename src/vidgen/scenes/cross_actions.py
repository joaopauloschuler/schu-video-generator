"""The beat actions of ``cross`` scenes (DESIGN.md §96.7): ``form_gametes`` (a parent's homologues
part and its gametes fly out: segregation and independent assortment; recombinants of linked
loci), ``fill`` (Punnett cells fill in, cell by cell, by row or by column — the gametes of the
row and column moving in — or the branch diagram grows), ``count`` (the offspring counted into
the phenotype or genotype classes), ``ratio`` (the whole-number ratio) and ``chi_square`` (the
goodness-of-fit table). Timed like any action (``at: "@word"``); ``highlight``, ``dim`` and
``callout`` work on the scene's targets (``cells:<class>``, ``class:<label>``…). Written against
``vidgen.api``; the scene draws (``scenes/cross.py``)."""

from fnmatch import fnmatchcase
from typing import Any, Literal

from vidgen.api import *

from .cross import CROSS_ACTIONS, genotype_table_fits

_PARENTS = {"parents": [0, 1], "both": [0, 1], "gametes": [0, 1], "parent1": [0], "mother": [0], "gametes1": [0],
            "parent2": [1], "father": [1], "gametes2": [1]}
_TABLES = ("phenotypes", "genotypes")


def _check(action: Action, scene_cls: type[NarratedScene], name: str, allowed: tuple[str, ...] | None) -> list[tuple[str, str]]:
    if not getattr(scene_cls, "cross_actions", False):
        return [("action", f"{name} is an action of cross scenes (type: cross)")]
    targets = action.config.targets()
    if allowed is not None:
        for t in targets:
            if t not in allowed:
                return [("target", f"{name} acts on {', '.join(allowed)}; '{t}' is not one{did_you_mean(t, list(allowed))}")]
    return []


def _matching(pattern: str, names: list[str]) -> list[str]:
    """The names a target pattern selects (``*`` / ``?`` as in every action)."""
    if "*" not in pattern and "?" not in pattern:
        return [pattern] if pattern in names else []
    return [n for n in names if fnmatchcase(n, pattern)]


def cells_of(plan: Any, targets: list[str], names: list[str]) -> list[tuple[int, int]] | None:
    """The Punnett cells the target patterns stand for (``None`` for a branch diagram)."""
    if plan.show != "punnett":
        return None
    every = [(c.row, c.col) for c in plan.cells]
    out: list[tuple[int, int]] = []
    for pattern in targets:
        for name in _matching(pattern, names):
            if name in ("square", "all"):
                cells = every
            elif name.startswith("cells:"):
                label = name[6:]
                found = next((k for k in plan.phenotypes if k.label == label), None)
                cells = list(found.cells) if found is not None else list(next(g for g in plan.genotypes if g.ascii == label).cells)
            elif name.startswith("cell"):
                r, c = name[4:].split(".")
                cells = [(int(r), int(c))]
            elif name.startswith("row"):
                cells = [c for c in every if c[0] == int(name[3:])]
            elif name.startswith("col"):
                cells = [c for c in every if c[1] == int(name[3:])]
            else:
                cells = []
            out += [c for c in cells if c not in out]
    return out


def _cells_of(scene: Any, targets: list[str]) -> list[tuple[int, int]] | None:
    return cells_of(scene.plan, targets, [n for t in scene.targets for n in t.names])


def _genotypes_shown(params: Any) -> bool:
    """Whether the genotype classes have a table: the panel's (at most 12 classes), or the
    leaves of a branch diagram of genotypes."""
    plan = params.plan()
    return genotype_table_fits(plan) or (plan.show == "branch" and params.branch == "genotypes")


def type_target_names(params: Any) -> list[str]:
    from .cross import CrossScene

    return CrossScene.target_names(params)


@action("form_gametes")
class FormGametes(Action):
    """A parent's gametes form (``form_gametes: both``, ``parent1``, ``parent2``, ``mother``,
    ``father``): its homologous chromosomes part (segregation; each pair independently of the
    others) and its gametes fly out of it to their places — the Punnett square's headers, or a
    row under the parent — each allele in the colour of the homologue it came from, with its
    exact frequency (recombinants of linked loci ringed)."""

    run_time = 2.2
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        return _check(self, scene_cls, "form_gametes", tuple(_PARENTS))

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        which = sorted({k for t in self.config.targets() for k in _PARENTS[t]})
        return scene.form_seconds(which)  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        which = sorted({k for t in self.config.targets() for k in _PARENTS[t]})
        return scene.run_form(which)  # type: ignore[attr-defined]


@action("fill")
class Fill(Action):
    """Fill the Punnett square (``fill: square``, ``all``), a row (``row2``), a column
    (``col3``), a cell (``cell2.3``) or a class's cells (``"cells:round, green"``): for each cell
    the gametes of its row and column move in and the zygote's genotype appears with its
    phenotype picture (a lethal genotype crossed out). ``by: row`` or ``column`` fills a line at
    a time; ``by: cell`` (default up to 16 cells) one after another. On a branch diagram
    (``fill: tree``) the branches grow level by level to the products. Gametes not formed yet
    are formed first."""

    class Options(ActionOptions):
        by: Literal["auto", "cell", "row", "column"] = "auto"
        """cell: one after another; row / column: a line at a time; auto: cells up to 16, rows beyond."""

    run_time = 3.0
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "fill", None)
        if problems:
            return problems
        plan = params.plan()
        for t in self.config.targets():
            if plan.show != "punnett" and t not in ("tree", "all"):
                return [("target", f"fill: this cross is drawn as a branch diagram: fill: tree")]
            if plan.show == "punnett" and t == "tree":
                return [("target", "fill: this cross is drawn as a Punnett square: fill: square (or a row, col, cell)")]
            if not (t in ("square", "all", "tree") or t.startswith(("row", "col", "cell"))):
                return [("target", f"fill acts on the square (square, row<N>, col<N>, cell<R>.<C>, cells:<class>), not '{t}'")]
        return []

    def _by(self, scene: Any) -> str:
        by = self.options.by
        if by == "auto":
            return "cell" if len(scene.plan.cells) <= 16 else "row"
        return by

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.fill_seconds(_cells_of(scene, self.config.targets()))  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_fill(_cells_of(scene, self.config.targets()), self._by(scene))  # type: ignore[attr-defined]


@action("count")
class Count(Action):
    """Count the offspring into classes (``count: phenotypes`` or ``genotypes``): the table
    appears in the panel row by row, each class's cells flashing as it is counted (equally
    likely cells: its fraction counts up cell by cell), with exact fractions in lowest terms and
    percentages; a lethal class is shown dying. Unfilled cells are filled first."""

    run_time = 3.0
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "count", _TABLES)
        if problems:
            return problems
        if "genotypes" in self.config.targets() and not _genotypes_shown(params):
            n = len(params.plan().genotypes)
            return [("target", f"count: {n} genotype classes do not fit a table: count phenotypes (or use branch: genotypes)")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return sum(scene.count_seconds(t) for t in self.config.targets())  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        for t in self.config.targets():
            anims += scene.run_count(t)  # type: ignore[attr-defined]
        return [Succession(*anims)] if len(anims) > 1 else anims


@action("ratio")
class Ratio(Action):
    """Show the whole-number ratio of a table (``ratio: phenotypes`` → 9 : 3 : 3 : 1, or
    ``genotypes`` → 1 : 2 : 1): each class's number, then the ratio line. Counts the table
    first when it was not."""

    run_time = 1.2
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "ratio", _TABLES)
        if problems:
            return problems
        if "genotypes" in self.config.targets() and not _genotypes_shown(params):
            return [("target", "ratio: the genotype classes do not fit a table: ratio: phenotypes")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return sum(scene.ratio_seconds(t) + (0 if t in scene.counted else scene.count_seconds(t))  # type: ignore[attr-defined]
                   for t in self.config.targets())

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        anims: list[Animation] = []
        for t in self.config.targets():
            anims += scene.run_ratio(t)  # type: ignore[attr-defined]
        return [Succession(*anims)] if len(anims) > 1 else anims


@action("chi_square")
class ChiSquareAction(Action):
    """The chi-square goodness-of-fit test of the scene's ``observed`` counts
    (``chi_square: chi_square``): a table of observed and expected counts with (O − E)²/E per
    class, then χ², the degrees of freedom, the p-value, the critical value at ``alpha`` and the
    verdict."""

    run_time = 2.4
    needs_visible = False

    def scene_problems(self, scene_cls: type[NarratedScene], params: Any) -> list[tuple[str, str]]:
        problems = _check(self, scene_cls, "chi_square", ("test", "chi_square"))
        if problems:
            return problems
        if params.observed is None:
            return [("action", "chi_square needs the observed counts: observed: {round yellow: 315, ...} in the params")]
        return []

    def run_time_for(self, scene: NarratedScene, targets: list[Target]) -> float | None:
        return scene.chi_seconds()  # type: ignore[attr-defined]

    def apply(self, scene: NarratedScene, targets: list[Target]) -> list[Animation]:
        return scene.run_chi()  # type: ignore[attr-defined]


def cross_sequence_problems(spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
    """The cross actions in beat and ``at`` order: gametes formed twice, a cell filled twice, a
    table counted twice or its ratio shown twice, the chi-square test twice."""
    beats = [b.id for b in spec.beats]
    plan = params.plan()
    order = sorted(range(len(uses)), key=lambda i: (beats.index(uses[i].beat) if uses[i].beat in beats else 0, uses[i].config.fraction, i))
    formed: set[int] = set()
    filled: set[tuple[int, int]] = set()
    counted: set[str] = set()
    ratios: set[str] = set()
    chi = grown = False
    every = [(c.row, c.col) for c in plan.cells]
    problems: list[tuple[str, str]] = []
    names = type_target_names(params)
    for i in order:
        use = uses[i]
        name = use.kind.name
        if name not in CROSS_ACTIONS:
            continue
        where = f"{use.location}.target"
        targets = use.config.targets()
        if name == "form_gametes":
            which = {k for t in targets for k in _PARENTS.get(t, [])}
            if which and which <= formed:
                problems.append((where, "these gametes are formed already (an earlier form_gametes, fill or count formed them)"))
            formed |= which
        elif name == "fill":
            formed |= {0, 1}
            if plan.show != "punnett":
                if grown:
                    problems.append((where, "the branch diagram is grown already"))
                grown = True
                continue
            cells = cells_of(plan, targets, names) or []
            again = [c for c in cells if c in filled]
            if again and len(again) == len(cells):
                problems.append((where, f"cell{again[0][0]}.{again[0][1]} is filled already" if len(again) == 1 else
                                 "these cells are filled already"))
            filled |= set(cells)
        elif name in ("count", "ratio"):
            formed |= {0, 1}
            filled |= set(every)
            grown = True
            for t in targets:
                done = counted if name == "count" else ratios
                if t in done:
                    problems.append((where, f"the {t} are {'counted' if name == 'count' else 'given their ratio'} already"))
                done.add(t)
                counted.add(t)
        elif name == "chi_square":
            if chi:
                problems.append((where, "the chi-square test is shown already"))
            chi = True
    return problems

