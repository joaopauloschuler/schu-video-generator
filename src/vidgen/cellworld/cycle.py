"""The eukaryotic cell cycle as data and rules (DESIGN.md §95.13; no manim): the phases G1, S,
G2 and M (with the stages of mitosis inside M) and their typical lengths, the exit to G0 before
the restriction point, the three checkpoints with the regulators that pass or arrest them, the
stylised levels of the four cyclin–CDK complexes over the cycle, and the replay of ``advance``
and ``checkpoint`` actions in beat order (no passing an arrested checkpoint, no G0 after the
restriction point). Textbook consensus (Alberts ch. 17, Morgan *The Cell Cycle*)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vidgen.errors import VidgenError

from .model import did_you_mean

#: A typical proliferating human cell in culture (hours; about 24 h in all).
TYPICAL_HOURS = {"g1": 11.0, "s": 8.0, "g2": 4.0, "m": 1.0}
#: M is drawn at least this share of the circle (a true hour of 24 would hide its stages).
M_MIN_SHARE = 0.12
#: The stages of M in order, with their shares of M (prophase is the longest; anaphase short).
M_STAGES = (("prophase", 0.3), ("prometaphase", 0.15), ("metaphase", 0.2), ("anaphase", 0.1), ("telophase", 0.15),
            ("cytokinesis", 0.1))
#: The restriction point lies this far into G1 (mid-to-late G1: after it the cell is committed).
RESTRICTION = 0.6


@dataclass(frozen=True)
class Phase:
    """A phase of the cycle: ``key``, its markup label, its plain name, a note."""

    key: str
    markup: str
    plain: str
    note: str


PHASES = (
    Phase("g1", "G<sub>1</sub>", "G1", "growth; cyclin D–CDK4/6 rises with mitogens"),
    Phase("s", "S", "S", "DNA replication (each chromosome becomes two sister chromatids)"),
    Phase("g2", "G<sub>2</sub>", "G2", "growth; checks that replication is complete"),
    Phase("m", "M", "M", "mitosis and cytokinesis"),
)
PHASE_KEYS = tuple(p.key for p in PHASES)


@dataclass(frozen=True)
class Arc:
    """One arc of a regulation row: ``kind`` ``->`` (activates), ``-|`` (inhibits); ``mark``
    P (phosphorylation), Ub (ubiquitination: degradation) or empty."""

    kind: str
    mark: str = ""


@dataclass(frozen=True)
class Row:
    """A row of a checkpoint panel: nodes (markup) with the arcs between them."""

    nodes: tuple[str, ...]
    arcs: tuple[Arc, ...]


def _row(*items: str) -> Row:
    """``"A", "->", "B", "P-|", "C"``: nodes at even places, arcs (with an optional mark
    before the arrow) between."""
    nodes = items[0::2]
    arcs = []
    for a in items[1::2]:
        mark = a[:-2]
        arcs.append(Arc(a[-2:], mark))
    if len(arcs) != len(nodes) - 1:
        raise ValueError(f"a row alternates nodes and arcs: {items}")
    return Row(tuple(nodes), tuple(arcs))


@dataclass(frozen=True)
class Checkpoint:
    """A checkpoint: where it acts (``at``: a point of the cycle), what it checks, the rows
    that let the cell pass and those that arrest it, by cause (the first is the default)."""

    key: str
    markup: str
    plain: str
    at: str
    checks: str
    go: tuple[Row, ...]
    arrest: dict[str, tuple[Row, ...]] = field(default_factory=dict)
    stop_note: dict[str, str] = field(default_factory=dict)


CYC_D = "cyclin D–CDK4/6"
CYC_E = "cyclin E–CDK2"
CYC_A = "cyclin A–CDK2"
CYC_B = "cyclin B–CDK1"

CHECKPOINTS: dict[str, Checkpoint] = {
    "g1_s": Checkpoint(
        "g1_s", "G<sub>1</sub>/S checkpoint", "G1/S checkpoint", "g1_s",
        "mitogens, cell size and nutrients, undamaged DNA (the restriction point R in late G1 commits the cell)",
        (_row("mitogens", "->", CYC_D, "P-|", "Rb", "-|", "E2F", "->", CYC_E, "->", "S phase"),),
        {"dna_damage": (_row("DNA damage", "->", "ATM · Chk2", "P->", "p53", "->", "p21", "-|", CYC_E),),
         "no_mitogens": (_row("no mitogens", "-|", CYC_D), _row("Rb", "-|", "E2F", "->", "G<sub>0</sub> (quiescence)"))},
        {"dna_damage": "p53 is stabilised and makes p21, a CDK inhibitor: Rb stays unphosphorylated and holds E2F",
         "no_mitogens": "without cyclin D–CDK4/6 Rb keeps E2F bound: the cell stays in G1 or leaves for G0"},
    ),
    "g2_m": Checkpoint(
        "g2_m", "G<sub>2</sub>/M checkpoint", "G2/M checkpoint", "g2_m",
        "DNA fully replicated and undamaged",
        (_row("Cdc25", "->", CYC_B, "->", "mitosis"), _row("Wee1", "P-|", CYC_B)),
        {"dna_damage": (_row("damaged or unreplicated DNA", "->", "ATR · Chk1", "P-|", "Cdc25"),
                        _row("Wee1", "P-|", CYC_B, "-|", "mitosis")),},
        {"dna_damage": "Chk1 inactivates Cdc25: CDK1 keeps its inhibitory phosphate (Tyr15, from Wee1) and the cell waits in G2"},
    ),
    "spindle": Checkpoint(
        "spindle", "Spindle assembly checkpoint", "spindle assembly checkpoint", "anaphase",
        "every kinetochore attached and bi-oriented (metaphase → anaphase)",
        (_row("APC/C–Cdc20", "Ub-|", "securin", "-|", "separase", "-|", "cohesin"),
         _row("APC/C–Cdc20", "Ub-|", CYC_B)),
        {"unattached_kinetochore": (_row("unattached kinetochore", "->", "Mad2 · BubR1 (MCC)", "-|", "APC/C–Cdc20"),
                                    _row("securin", "-|", "separase", "-|", "cohesin cleavage"))},
        {"unattached_kinetochore": "one unattached kinetochore makes the mitotic checkpoint complex, which holds APC/C–Cdc20: "
                                   "securin stays, separase stays inactive, sisters stay cohesed"},
    ),
}
CHECKPOINT_ALIASES = {"g1": "g1_s", "restriction_point": "g1_s", "r": "g1_s", "g1s": "g1_s", "g2": "g2_m", "g2m": "g2_m",
                      "sac": "spindle", "spindle_assembly": "spindle", "metaphase_anaphase": "spindle", "m": "spindle"}


def checkpoint_key(name: str) -> str:
    """The checkpoint a name means (``g1_s``, ``g2_m``, ``spindle`` or an alias), or a
    :class:`VidgenError` with did-you-mean."""
    key = name.strip().lower().replace("/", "_").replace("-", "_").replace(" ", "_")
    key = CHECKPOINT_ALIASES.get(key, key)
    if key not in CHECKPOINTS:
        raise VidgenError(f"unknown checkpoint '{name}'{did_you_mean(name, list(CHECKPOINTS) + list(CHECKPOINT_ALIASES))} "
                          f"(checkpoints: g1_s, g2_m, spindle)")
    return key


# ----- the cycle's geometry --------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleGeometry:
    """The cycle on a circle of 1 (drawn shares): each phase's start and end, the stages of M,
    the restriction point; ``hours`` the phases' true lengths."""

    hours: dict[str, float]
    bounds: dict[str, tuple[float, float]]
    points: dict[str, float]

    def phase_at(self, t: float) -> str:
        t = t % 1.0
        for key in PHASE_KEYS:
            a, b = self.bounds[key]
            if a <= t < b:
                return key
        return "m"

    def stage_at(self, t: float) -> str:
        """The phase, or the stage of M, at cycle position ``t``."""
        t = t % 1.0
        phase = self.phase_at(t)
        if phase != "m":
            return phase
        for name, _ in reversed(M_STAGES):
            if t >= self.points[name] - 1e-9:
                return name
        return "prophase"


def cycle_geometry(hours: dict[str, float] | None = None) -> CycleGeometry:
    """The drawn cycle for these phase lengths (default :data:`TYPICAL_HOURS`; M is widened to
    :data:`M_MIN_SHARE` of the circle, the others keep their proportions)."""
    h = dict(TYPICAL_HOURS)
    for key, value in (hours or {}).items():
        if key not in PHASE_KEYS:
            raise VidgenError(f"hours: unknown phase '{key}'{did_you_mean(key, list(PHASE_KEYS))} (g1, s, g2, m)")
        if not value > 0:
            raise VidgenError(f"hours.{key}: a phase lasts more than 0 h")
        h[key] = float(value)
    total = sum(h.values())
    share = {k: h[k] / total for k in PHASE_KEYS}
    if share["m"] < M_MIN_SHARE:
        rest = 1.0 - share["m"]
        share = {k: (M_MIN_SHARE if k == "m" else share[k] * (1 - M_MIN_SHARE) / rest) for k in PHASE_KEYS}
    bounds: dict[str, tuple[float, float]] = {}
    t = 0.0
    for key in PHASE_KEYS:
        bounds[key] = (t, t + share[key])
        t += share[key]
    bounds["m"] = (bounds["m"][0], 1.0)
    points = {"g1": 0.0, "restriction_point": bounds["g1"][1] * RESTRICTION, "g1_s": bounds["s"][0], "s": bounds["s"][0],
              "g2": bounds["g2"][0], "g2_m": bounds["m"][0], "m": bounds["m"][0]}
    m0, m1 = bounds["m"]
    at = m0
    for name, part in M_STAGES:
        points[name] = at
        at += part * (m1 - m0)
    points["end"] = 1.0
    return CycleGeometry(h, bounds, points)


#: Names ``advance`` takes (besides g0) and what they mean.
POINT_NOTES = {
    "g1": "the start of G1 (a new cycle after mitosis)", "restriction_point": "the restriction point (mid-to-late G1)",
    "g1_s": "the G1/S transition", "s": "the start of S", "g2": "the start of G2", "g2_m": "the G2/M transition",
    "m": "the start of M (prophase)", **{name: f"the start of {name}" for name, _ in M_STAGES}, "end": "the end of the cycle",
}
POINTS = tuple(POINT_NOTES) + ("g0",)
POINT_ALIASES = {"r": "restriction_point", "g1/s": "g1_s", "g2/m": "g2_m", "mitosis": "m", "division": "m", "g0_exit": "g1"}


def point_key(name: str) -> str:
    key = name.strip().lower()
    key = POINT_ALIASES.get(key, key)
    if key not in POINTS:
        raise VidgenError(f"unknown point of the cycle '{name}'{did_you_mean(name, list(POINTS))} "
                          f"(phases g1, s, g2, m, g0; the stages prophase … cytokinesis; restriction_point, g1_s, g2_m, end)")
    return key


# ----- cyclin levels ---------------------------------------------------------------------------------


def monotone_cubic(points: tuple[tuple[float, float], ...] | list[tuple[float, float]], x: float) -> float:
    """The value at ``x`` of the monotone cubic (Fritsch–Carlson) through ``points`` (x
    increasing): no overshoot between the points, flat outside them."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n = len(points)
    d = [(ys[k + 1] - ys[k]) / (xs[k + 1] - xs[k]) for k in range(n - 1)]
    m = [d[0]] + [0.0 if d[k - 1] * d[k] <= 0 else (d[k - 1] + d[k]) / 2 for k in range(1, n - 1)] + [d[-1]]
    for k in range(n - 1):
        if d[k] == 0:
            m[k] = m[k + 1] = 0.0
            continue
        a, b = m[k] / d[k], m[k + 1] / d[k]
        s = a * a + b * b
        if s > 9:
            tau = 3 / math.sqrt(s)
            m[k], m[k + 1] = tau * a * d[k], tau * b * d[k]
    k = max(i for i in range(n - 1) if xs[i] <= x)
    h = xs[k + 1] - xs[k]
    t = (x - xs[k]) / h
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    return h00 * ys[k] + h10 * h * m[k] + h01 * ys[k + 1] + h11 * h * m[k + 1]


@dataclass(frozen=True)
class Cyclin:
    """A cyclin–CDK complex: its key (d, e, a, b), markup label, plain label, what it does,
    and its stylised level over the cycle as control points (cycle position, level 0–1)."""

    key: str
    markup: str
    plain: str
    role: str
    points: tuple[tuple[float, float], ...]

    def level(self, t: float) -> float:
        return max(0.0, monotone_cubic(self.points, t % 1.0))


CYCLIN_KEYS = ("d", "e", "a", "b")
CYCLIN_LABELS = {"d": "cyclin D–CDK4/6", "e": "cyclin E–CDK2", "a": "cyclin A–CDK2/1", "b": "cyclin B–CDK1"}


def cyclins(geo: CycleGeometry) -> dict[str, Cyclin]:
    """The four cyclin–CDK complexes with levels placed on ``geo``: D rises in G1 with mitogens
    and stays; E peaks at G1/S and is degraded early in S (SCF–Fbw7); A rises from S, peaks at
    G2/M and is degraded in prometaphase (APC/C, before the checkpoint is satisfied); B rises
    through S and G2, peaks at metaphase and is destroyed abruptly at the metaphase → anaphase
    transition (APC/C–Cdc20)."""
    g1 = geo.bounds["g1"][1]
    s0, s1 = geo.bounds["s"]
    m0 = geo.bounds["m"][0]
    p = geo.points
    s_at = lambda f: s0 + f * (s1 - s0)   # noqa: E731
    ana, telo = p["anaphase"], p["telophase"]
    return {
        "d": Cyclin("d", "cyclin D–CDK4/6", CYC_D, "mitogen sensor: phosphorylates Rb in G1",
                    ((0.0, 0.12), (0.3 * g1, 0.32), (RESTRICTION * g1, 0.5), (g1, 0.55), (m0, 0.55), (p["anaphase"], 0.5), (1.0, 0.12))),
        "e": Cyclin("e", "cyclin E–CDK2", CYC_E, "G1/S: completes Rb phosphorylation, starts replication",
                    ((0.0, 0.03), (0.5 * g1, 0.03), (0.82 * g1, 0.35), (g1, 0.9), (s_at(0.25), 0.3), (s_at(0.5), 0.03), (1.0, 0.03))),
        "a": Cyclin("a", "cyclin A–CDK2/1", "cyclin A–CDK2 (CDK1 in G2)", "S phase: replication once per cycle; G2",
                    ((0.0, 0.03), (0.92 * g1, 0.03), (s_at(0.2), 0.18), (s1, 0.6), (m0, 0.85), (p["prometaphase"], 0.75),
                     (p["metaphase"], 0.04), (1.0, 0.03))),
        "b": Cyclin("b", "cyclin B–CDK1", CYC_B, "M phase: drives mitosis (MPF)",
                    ((0.0, 0.03), (s_at(0.4), 0.04), (s1, 0.28), (m0, 0.72), (p["metaphase"], 0.98), (ana - 0.002, 1.0),
                     (ana + 0.45 * (telo - ana), 0.06), (1.0, 0.03))),
    }


# ----- the rules, replayed ---------------------------------------------------------------------------


@dataclass
class CycleState:
    """Where the cell is: ``t`` (cycle position, growing past 1 in later cycles), ``g0`` (in
    quiescence), the checkpoints held (arrest) and since which beat."""

    t: float = 0.0
    g0: bool = False
    arrests: dict[str, str] = field(default_factory=dict)


def start_state(geo: CycleGeometry, start: str) -> CycleState:
    key = point_key(start)
    if key == "g0":
        return CycleState(0.0, True)
    return CycleState(geo.points[key] if key != "end" else 0.0)


def target_t(geo: CycleGeometry, state: CycleState, to: str, into: float) -> tuple[float, str]:
    """The cycle position ``advance`` goes to (the next time the cell reaches ``to``, ``into``
    of the way through that phase or stage) and the key."""
    key = point_key(to)
    if key == "g0":
        return state.t, key
    if key in PHASE_KEYS:
        a, b = geo.bounds[key]
        base = a + into * (b - a)
    elif key in dict(M_STAGES):
        names = [n for n, _ in M_STAGES]
        k = names.index(key)
        a = geo.points[key]
        b = geo.points[names[k + 1]] if k + 1 < len(names) else 1.0
        base = a + into * (b - a)
    else:
        base = geo.points[key]
    cycle = math.floor(state.t + 1e-9)
    t = cycle + base
    if t <= state.t + 1e-9:
        t += 1.0
    return t, key


def advance_problem(geo: CycleGeometry, state: CycleState, to: str, into: float) -> str | None:
    """Why ``advance`` to ``to`` cannot happen now (``None`` when it can)."""
    try:
        t, key = target_t(geo, state, to, into)
    except VidgenError as error:
        return str(error)
    if key == "g0":
        if state.g0:
            return "the cell is already in G0"
        pos = state.t % 1.0
        if geo.phase_at(state.t) != "g1" or pos > geo.points["restriction_point"] + 1e-9:
            where = geo.stage_at(state.t)
            where = next((p.plain for p in PHASES if p.key == where), where)
            if geo.phase_at(state.t) == "g1":
                where = "late G1, past the restriction point"
            return (f"a cell leaves for G0 only from G1 before the restriction point; it is in {where} now "
                    f"(past R it is committed to S phase and mitosis)")
        return None
    for ck, why in state.arrests.items():
        at = geo.points[CHECKPOINTS[ck].at]
        nxt = math.floor(state.t + 1e-9) + at
        if nxt < state.t - 1e-9:
            nxt += 1.0
        if state.t - 1e-9 <= nxt < t - 1e-9:
            return (f"the cell is held at the {CHECKPOINTS[ck].plain} ({why}); it can advance only up to "
                    f"{'anaphase' if ck == 'spindle' else ck} until that arrest ends (give the checkpoint action an until:)")
    return None


def advance(geo: CycleGeometry, state: CycleState, to: str, into: float) -> CycleState:
    """The state after ``advance``."""
    t, key = target_t(geo, state, to, into)
    if key == "g0":
        return CycleState(state.t, True, dict(state.arrests))
    return CycleState(t, False, dict(state.arrests))


def checkpoint_problem(geo: CycleGeometry, state: CycleState, name: str, outcome: str, cause: str | None) -> str | None:
    try:
        key = checkpoint_key(name)
    except VidgenError as error:
        return str(error)
    ck = CHECKPOINTS[key]
    if cause is not None and cause not in ck.arrest:
        return f"the {ck.plain} arrests on {', '.join(ck.arrest)}, not '{cause}'{did_you_mean(cause, list(ck.arrest))}"
    if outcome == "pass" and key in state.arrests:
        return f"the {ck.plain} is arrested at this point ({state.arrests[key]}): end that arrest (until:) before it passes"
    if outcome == "arrest" and key in state.arrests:
        return f"the {ck.plain} is already arrested at this point"
    return None
