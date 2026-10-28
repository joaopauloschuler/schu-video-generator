"""Feynman diagrams as data, with the Standard Model's vertex rules (Phase Y, Step 238; DESIGN
§99.5). No manim; the ``feynman`` scene draws them and :mod:`.feynman_layout` places them.

A :class:`Diagram` is a list of lines (:class:`DiagramLine`), each a particle from
:mod:`.data` running **forward in time** from ``start`` to ``end``: a vertex id, ``in`` (an
incoming external leg) or ``out`` (an outgoing one); a line ``in`` → ``out`` is a spectator (a
quark that takes no part, drawn straight through). The particle is what travels forward in time:
an incoming positron is ``e+`` from ``in`` to its vertex, and its fermion arrow points back
against time (the arrow follows the fermion-number flow). Hadrons are drawn as their quark lines
grouped (:class:`HadronGroup`: the neutron's d u d on the way in).

:func:`check_diagram` checks every vertex: the allowed vertex types of the Standard Model at tree
level (:class:`VertexRule`: f f γ for charged fermions, q q g, g g g, g g g g, f f′ W within a
doublet — leptons only within their family —, f f Z, f f H for massive fermions, H W W, H Z Z,
H H H, W W γ, W W Z and the quartic ones; no H γ γ or H g g vertex: those go through loops),
charge, baryon and lepton family numbers with :func:`.conservation.check` (the vertex as a little
process with every line virtual), the fermion arrows running through each vertex, a basic colour
check, the lepton and baryon numbers along each fermion line, and the whole reaction with the
same checker (and the hadron-level reaction when groups are given).

Coupling values: α from the SI 2019 / CODATA 2022 constants; α_s(m_Z), G_F (hence the Higgs
vacuum value v and the SU(2) coupling g = 2m_W/v) from PDG 2024; sin²θ_W and the CKM magnitudes
rounded (see the constants below).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from vidgen.errors import VidgenError
from vidgen.quantities.constants import CONSTANTS

from .conservation import Check, Verdict, check
from .data import PARTICLES, Particle, fraction_text
from .names import particle
from .process import Leg, Process

# ----- couplings ------------------------------------------------------------------------------------

#: The fine-structure constant α = e² / (4π ε₀ ħ c) (SI 2019 exact e, h, c; CODATA 2022 ε₀).
ALPHA = float(CONSTANTS["e"].number()) ** 2 / (
    4 * math.pi * float(CONSTANTS["epsilon_0"].number()) * float(CONSTANTS["hbar"].number()) * float(CONSTANTS["c"].number()))
#: The strong coupling at the Z mass (PDG 2024 world average, 0.1180 ± 0.0009).
ALPHA_S_MZ = 0.1180
#: The Fermi constant G_F in GeV⁻² (PDG 2024, from the muon lifetime).
G_FERMI = 1.1663788e-5
#: The Higgs field's vacuum value v = (√2 G_F)^(−1/2), in GeV (≈ 246.22).
V_HIGGS = 1.0 / math.sqrt(math.sqrt(2.0) * G_FERMI)
#: sin²θ_W (MS-bar at m_Z, PDG 2024), shown rounded to three figures.   # check last digits
SIN2_THETA_W = 0.2313
#: |V_ij| of the CKM matrix, rounded to two figures (PDG 2024 CKM review, global fit).   # check (rounded)
CKM = {("u", "d"): 0.97, ("u", "s"): 0.22, ("u", "b"): 0.004, ("c", "d"): 0.22, ("c", "s"): 0.97, ("c", "b"): 0.04,
       ("t", "d"): 0.009, ("t", "s"): 0.04, ("t", "b"): 1.0}


def g_weak() -> float:
    """The SU(2) coupling g = 2 m_W / v (≈ 0.65)."""
    return 2 * PARTICLES["W+"].mass_mev / 1000.0 / V_HIGGS


def yukawa(p: Particle) -> float:
    """A fermion's Higgs coupling y = √2 m / v."""
    return math.sqrt(2.0) * p.mass_mev / 1000.0 / V_HIGGS


# ----- lines and diagrams ---------------------------------------------------------------------------

#: How each boson is drawn (the key of its line kind).
BOSON_KINDS = {"gamma": "photon", "g": "gluon", "W+": "W", "W-": "W", "Z": "Z", "H": "higgs"}
LINE_KINDS = ("fermion", "photon", "gluon", "W", "Z", "higgs")
SIDES = ("initial", "final")
#: The ends a line may have besides a vertex id.
IN, OUT = "in", "out"


def fermion_flow(p: Particle) -> int:
    """+1 for a fermion (quark, lepton), −1 for an antifermion, 0 for a boson."""
    if not p.is_fermion:
        return 0
    return 1 if (p.baryon > 0 or p.lepton_number > 0) else -1


def base(p: Particle) -> Particle:
    """The fermion of a fermion or antifermion (ū → u, e⁺ → e⁻); a boson itself."""
    return PARTICLES[p.antiparticle] if fermion_flow(p) < 0 else p


@dataclass(frozen=True)
class DiagramLine:
    """One line: ``particle`` travelling forward in time from ``start`` to ``end`` (vertex ids,
    ``in``, ``out``); ``off_shell`` writes it with ``*`` (Z*, γ*); ``label`` shows its name."""

    id: str
    particle: Particle
    start: str
    end: str
    off_shell: bool = False
    label: bool = True

    @property
    def kind(self) -> str:
        """``fermion``, ``photon``, ``gluon``, ``W``, ``Z`` or ``higgs``."""
        return BOSON_KINDS.get(self.particle.key, "fermion")

    @property
    def incoming(self) -> bool:
        return self.start == IN and self.end != OUT

    @property
    def outgoing(self) -> bool:
        return self.end == OUT and self.start != IN

    @property
    def spectator(self) -> bool:
        return self.start == IN and self.end == OUT

    @property
    def internal(self) -> bool:
        return self.start not in (IN, OUT) and self.end not in (IN, OUT)

    @property
    def flow(self) -> int:
        """Fermion-number flow along start → end: +1 (fermion), −1 (antifermion, its arrow
        against the line's direction), 0 (boson)."""
        return fermion_flow(self.particle)

    @property
    def symbol(self) -> str:
        return self.particle.symbol + ("*" if self.off_shell else "")

    def ends(self) -> tuple[str, str]:
        return (self.start, self.end)


@dataclass(frozen=True)
class HadronGroup:
    """A hadron drawn as its quark lines: ``lines`` (ids) on the ``initial`` or ``final`` side,
    bracketed and labelled with ``particle``."""

    particle: Particle
    side: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Diagram:
    """A Feynman diagram: its ``lines`` (vertices are the line ends other than ``in`` / ``out``),
    hadron ``groups``, a ``label`` (``s-channel``) and its ``name`` within a preset."""

    name: str
    lines: tuple[DiagramLine, ...]
    groups: tuple[HadronGroup, ...] = ()
    label: str = ""

    @property
    def vertices(self) -> tuple[str, ...]:
        """Vertex ids in order of first appearance."""
        found: dict[str, None] = {}
        for ln in self.lines:
            for end in ln.ends():
                if end not in (IN, OUT):
                    found.setdefault(end, None)
        return tuple(found)

    def line(self, line_id: str) -> DiagramLine:
        return next(ln for ln in self.lines if ln.id == line_id)

    def at(self, vertex: str) -> tuple[list[DiagramLine], list[DiagramLine]]:
        """The lines ending at ``vertex`` (into it) and starting there (out of it)."""
        into = [ln for ln in self.lines if ln.end == vertex]
        out = [ln for ln in self.lines if ln.start == vertex]
        return into, out

    @property
    def initial(self) -> tuple[DiagramLine, ...]:
        """Incoming external legs (spectators not included)."""
        return tuple(ln for ln in self.lines if ln.incoming)

    @property
    def final(self) -> tuple[DiagramLine, ...]:
        return tuple(ln for ln in self.lines if ln.outgoing)

    @property
    def spectators(self) -> tuple[DiagramLine, ...]:
        return tuple(ln for ln in self.lines if ln.spectator)

    @property
    def internal(self) -> tuple[DiagramLine, ...]:
        return tuple(ln for ln in self.lines if ln.internal)

    @property
    def loops(self) -> int:
        """Independent loops: internal lines − vertices + 1."""
        return len(self.internal) - len(self.vertices) + 1

    @property
    def is_decay(self) -> bool:
        return len(self.initial) == 1

    def process(self) -> Process:
        """The quark-level reaction of the external legs (spectators left out)."""
        return Process(tuple(Leg(ln.particle, ln.off_shell) for ln in self.initial), tuple(Leg(ln.particle, ln.off_shell) for ln in self.final))

    def hadron_process(self) -> Process | None:
        """The reaction with the hadron groups in place of their quarks, or ``None`` without
        groups."""
        if not self.groups:
            return None
        sides: dict[str, list[Leg]] = {}
        for side, legs in (("initial", [*self.initial, *self.spectators]), ("final", [*self.final, *self.spectators])):
            grouped = {i for g in self.groups if g.side == side for i in g.lines}
            out = [Leg(g.particle) for g in self.groups if g.side == side]
            out += [Leg(ln.particle, ln.off_shell) for ln in legs if ln.id not in grouped and not ln.spectator]
            sides[side] = out
        return Process(tuple(sides["initial"]), tuple(sides["final"]))


def _particle(text: str, where: str) -> tuple[Particle, bool]:
    text = str(text).strip()
    off = text.endswith("*") and len(text) > 1
    try:
        p = particle(text[:-1] if off else text)
    except VidgenError as exc:
        raise VidgenError(f"{where}: {exc}") from None
    if p.is_hadron:
        raise VidgenError(f"{where}: '{text}' is a hadron; a diagram line is a quark, lepton or boson — draw the hadron as its quark "
                          f"lines and name it with a group (groups: [{{particle: {p.key}, side: initial, lines: [...]}}])")
    return p, off


def build_diagram(name: str, lines: Sequence[Mapping[str, object]], groups: Sequence[Mapping[str, object]] = (), label: str = "") -> Diagram:
    """A :class:`Diagram` from plain data: each line ``{id, particle, from, to, label}``
    (``id`` defaults to ``l1``, ``l2``…; ``particle`` any spelling, ``*`` for off-shell; ``from``
    / ``to``: a vertex id, ``in`` or ``out``), each group ``{particle, side, lines}``. Raises
    :class:`VidgenError` for a structure that is not a diagram: unknown particles, a line from
    ``out`` or into ``in``, a line from a vertex to itself, a vertex with fewer than three
    lines, pieces not joined, more than one loop, groups that do not hold their hadron's
    quarks."""
    where = f"diagram '{name}'"
    if not lines:
        raise VidgenError(f"{where}: no lines")
    built: list[DiagramLine] = []
    seen: set[str] = set()
    for i, spec in enumerate(lines, start=1):
        line_id = str(spec.get("id") or f"l{i}")
        at = f"{where}: line '{line_id}'"
        if line_id in seen:
            raise VidgenError(f"{at}: the id is used twice")
        seen.add(line_id)
        if "particle" not in spec:
            raise VidgenError(f"{at}: give its particle (particle: e-)")
        p, off = _particle(str(spec["particle"]), at)
        start, end = str(spec.get("from", "")).strip(), str(spec.get("to", "")).strip()
        if not start or not end:
            raise VidgenError(f"{at}: give both ends (from: in, to: v1); ends are vertex ids, 'in' (incoming) or 'out' (outgoing)")
        if start == OUT or end == IN:
            raise VidgenError(f"{at}: lines run forward in time: 'in' can only be where a line starts (from: in), 'out' where it ends (to: out)")
        if start == end:
            raise VidgenError(f"{at}: a line from vertex '{start}' to itself is not drawn (no tadpoles)")
        ln = DiagramLine(line_id, p, start, end, off, bool(spec.get("label", True)))
        if ln.spectator and not p.is_quark:
            raise VidgenError(f"{at}: a line from 'in' to 'out' passes through without a vertex: only spectator quarks do that")
        built.append(ln)
    d = Diagram(name, tuple(built), (), label)
    _check_structure(d)
    return Diagram(name, tuple(built), tuple(_group(d, g, i) for i, g in enumerate(groups, start=1)), label)


def _check_structure(d: Diagram) -> None:
    where = f"diagram '{d.name}'"
    vertices = d.vertices
    if not vertices:
        raise VidgenError(f"{where}: no vertex: lines join at vertex ids (from: in, to: v1)")
    for v in vertices:
        into, out = d.at(v)
        if len(into) + len(out) < 3:
            raise VidgenError(f"{where}: vertex '{v}' joins {len(into) + len(out)} line(s); a Standard Model vertex joins three or four")
        if len(into) + len(out) > 4:
            raise VidgenError(f"{where}: vertex '{v}' joins {len(into) + len(out)} lines; a Standard Model vertex joins three or four")
    if not d.initial:
        raise VidgenError(f"{where}: no incoming line (from: in)")
    if not d.final:
        raise VidgenError(f"{where}: no outgoing line (to: out)")
    # connected
    adjacency: dict[str, set[str]] = {v: set() for v in vertices}
    for ln in d.internal:
        adjacency[ln.start].add(ln.end)
        adjacency[ln.end].add(ln.start)
    reached = {vertices[0]}
    todo = [vertices[0]]
    while todo:
        for n in adjacency[todo.pop()]:
            if n not in reached:
                reached.add(n)
                todo.append(n)
    if len(reached) != len(vertices):
        rest = [v for v in vertices if v not in reached]
        raise VidgenError(f"{where}: the vertices {', '.join(rest)} are not joined to {vertices[0]} by internal lines: one diagram is one connected piece")
    if d.loops > 1:
        raise VidgenError(f"{where}: {d.loops} loops; tree diagrams and one-loop diagrams are drawn")


def _group(d: Diagram, spec: Mapping[str, object], i: int) -> HadronGroup:
    where = f"diagram '{d.name}': group {i}"
    p = particle(str(spec.get("particle", "")))
    if not p.is_hadron:
        raise VidgenError(f"{where}: '{p.symbol}' is not a hadron; a group names the hadron its quark lines make (n, p, pi+...)")
    side = str(spec.get("side", "initial"))
    if side not in SIDES:
        raise VidgenError(f"{where}: side is 'initial' or 'final', not '{side}'")
    ids = [str(x) for x in spec.get("lines", [])]  # type: ignore[attr-defined]
    known = {ln.id: ln for ln in d.lines}
    for line_id in ids:
        ln = known.get(line_id)
        if ln is None:
            raise VidgenError(f"{where}: no line '{line_id}' (lines: {', '.join(known)})")
        on_side = ln.start == IN if side == "initial" else ln.end == OUT
        if not on_side:
            raise VidgenError(f"{where}: line '{line_id}' is not an {'incoming' if side == 'initial' else 'outgoing'} line")
    quarks = sorted(known[x].particle.key for x in ids)
    if not any(sorted(c) == quarks for c in p.components):
        raise VidgenError(f"{where}: {p.symbol} is {p.content}; the lines {', '.join(ids)} carry "
                          f"{' '.join(known[x].particle.symbol for x in ids) or 'nothing'}")
    return HadronGroup(p, side, tuple(ids))


# ----- vertex rules ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class VertexRule:
    """An allowed Standard Model vertex: ``kind`` (``QED``, ``QCD``, ``ggg``, ``gggg``, ``CC``,
    ``NC``, ``Hff``, ``HVV``, ``VVV``, ``VVVV``, ``HHH``, ``HHHH``, ``HHVV``), its ``name``, the
    ``coupling`` in words and numbers and the ``interaction`` it belongs to."""

    kind: str
    name: str
    coupling: str
    interaction: str
    note: str = ""


def _alpha_text() -> str:
    return f"α = e²/4πε₀ħc ≈ 1/{1 / ALPHA:.0f}"


_BOSON_RULES: dict[tuple[str, ...], tuple[str, str, str, str]] = {
    ("g", "g", "g"): ("ggg", "three-gluon vertex (QCD)", f"gluons carry colour, so they couple to each other; α_s(m_Z) ≈ {ALPHA_S_MZ:.3f}", "strong"),
    ("g", "g", "g", "g"): ("gggg", "four-gluon vertex (QCD)", f"strength α_s; α_s(m_Z) ≈ {ALPHA_S_MZ:.3f}", "strong"),
    ("W", "W", "photon"): ("VVV", "W W γ vertex", "the W is charged: coupling e (" + _alpha_text() + ")", "electroweak"),
    ("W", "W", "Z"): ("VVV", "W W Z vertex", "coupling g cos θ_W (weak isospin of the W)", "electroweak"),
    ("W", "W", "higgs"): ("HVV", "H W W vertex", "", "higgs"),
    ("Z", "Z", "higgs"): ("HVV", "H Z Z vertex", "", "higgs"),
    ("higgs", "higgs", "higgs"): ("HHH", "Higgs self-coupling (H H H)", "", "higgs"),
    ("higgs", "higgs", "higgs", "higgs"): ("HHHH", "quartic Higgs self-coupling", "", "higgs"),
    ("W", "W", "W", "W"): ("VVVV", "quartic gauge vertex (W W W W)", "coupling g²", "electroweak"),
    ("W", "W", "Z", "Z"): ("VVVV", "quartic gauge vertex (W W Z Z)", "coupling g² cos²θ_W", "electroweak"),
    ("W", "W", "photon", "photon"): ("VVVV", "quartic gauge vertex (W W γ γ)", "coupling e²", "electroweak"),
    ("W", "W", "Z", "photon"): ("VVVV", "quartic gauge vertex (W W Z γ)", "coupling e g cos θ_W", "electroweak"),
    ("W", "W", "higgs", "higgs"): ("HHVV", "H H W W vertex", "coupling 2m_W²/v²", "higgs"),
    ("Z", "Z", "higgs", "higgs"): ("HHVV", "H H Z Z vertex", "coupling 2m_Z²/v²", "higgs"),
}
#: Boson sets that only meet through a loop (no tree-level vertex), with the preset that draws it.
_LOOP_ONLY = {
    ("higgs", "photon", "photon"): ("H γ γ", "photon", "the top quark and the W boson", "h_to_gammagamma"),
    ("gluon", "gluon", "higgs"): ("H g g", "gluon", "quarks, mostly the top quark", "gg_to_h"),
    ("Z", "higgs", "photon"): ("H Z γ", "photon", "the top quark and the W boson", ""),
}
_KIND_ORDER = {k: i for i, k in enumerate(("W", "Z", "gluon", "higgs", "photon"))}


def _boson_key(kinds: list[str]) -> tuple[str, ...]:
    return tuple(sorted(kinds, key=lambda k: (_KIND_ORDER.get(k, 9), k)))


def _hvv_coupling(kind: str) -> str:
    gev = (PARTICLES["W+"] if kind == "W" else PARTICLES["Z"]).mass_mev / 1000.0
    return f"coupling 2m_{kind}²/v ≈ {2 * gev**2 / V_HIGGS:.0f} GeV (v ≈ {V_HIGGS:.0f} GeV): the Higgs boson couples to mass"


def _boson_rule(kinds: list[str]) -> tuple[VertexRule | None, str | None]:
    key = _boson_key(kinds)
    # ("g", "g", "g") style keys for the gluon rules
    gkey = tuple("g" if k == "gluon" else k for k in key)
    entry = _BOSON_RULES.get(gkey) or _BOSON_RULES.get(key)
    if entry is not None:
        kind, name, coupling, interaction = entry
        if kind == "HVV":
            coupling = _hvv_coupling("W" if "W" in key else "Z")
        elif kind == "HHH":
            mh = PARTICLES["H"].mass_mev / 1000.0
            coupling = f"coupling 3m_H²/v ≈ {3 * mh**2 / V_HIGGS:.0f} GeV"
        elif kind == "HHHH":
            mh = PARTICLES["H"].mass_mev / 1000.0
            coupling = f"coupling 3m_H²/v² ≈ {3 * mh**2 / V_HIGGS**2:.2f}"
        return VertexRule(kind, name, coupling, interaction), None
    loop = _LOOP_ONLY.get(key)
    if loop is not None:
        name, massless, heavy, preset = loop
        hint = f" (preset {preset})" if preset else ""
        return None, (f"no tree-level {name} vertex: the Higgs boson couples to mass and the {massless} is massless; this goes through "
                      f"a loop of heavy particles ({heavy}): draw the loop{hint}")
    names = " ".join({"photon": "γ", "gluon": "g", "higgs": "H"}.get(k, k) for k in key)
    return None, (f"no Standard Model vertex joins {names}: the boson vertices are g g g, g g g g, W W γ, W W Z, H W W, H Z Z, H H H "
                  f"and the quartic W W W W, W W Z Z, W W γ γ, W W Z γ, H H W W, H H Z Z, H H H H")


_LEPTON_PARTNER = {"e-": "nu_e", "mu-": "nu_mu", "tau-": "nu_tau"}


def _doublet(a: Particle, b: Particle) -> tuple[bool, str]:
    """Whether fermions ``a`` and ``b`` (their fermion states) form a weak doublet a W joins,
    and a note (CKM for quarks)."""
    if a.is_lepton and b.is_lepton:
        pair = {a.key, b.key}
        ok = any(pair == {c, n} for c, n in _LEPTON_PARTNER.items())
        return ok, ""
    if a.is_quark and b.is_quark:
        up, down = (a, b) if a.charge > 0 else (b, a)
        if up.charge <= 0 or down.charge >= 0:
            return False, ""
        v = CKM[(up.key, down.key)]
        same = up.generation == down.generation
        note = f"|V_{up.key}{down.key}| ≈ {v:g}" + ("" if same else " (CKM-suppressed: the W crosses generations)")
        return True, note
    return False, ""


def _fermion_rule(f1: Particle, f2: Particle, boson: str) -> tuple[VertexRule | None, str | None]:
    """The rule of a vertex of two fermions (all-outgoing ``f1``, ``f2``) and a boson."""
    if fermion_flow(f1) + fermion_flow(f2) != 0:
        return None, "the fermion arrows must run through the vertex (one into it, one out of it): two fermions, or two antifermions, cannot meet a boson"
    a, b = base(f1), base(f2)
    same = a.key == b.key
    if boson == "W":
        ok, note = _doublet(a, b)
        if ok:
            pair = f"{a.symbol} ↔ {b.symbol}" if (a.is_lepton and a.charge != 0) or (a.is_quark and a.charge > 0) else f"{b.symbol} ↔ {a.symbol}"
            coupling = f"coupling g/√2, g = 2m_W/v ≈ {g_weak():.2f}; flavour changes within a doublet: {pair}"
            return VertexRule("CC", "weak charged-current vertex (W)", coupling + (f"; {note}" if note else ""), "weak", note), None
        if a.is_lepton and b.is_lepton and not same:
            return None, (f"the W joins a charged lepton to the neutrino of its own family (e⁻ ↔ νₑ, μ⁻ ↔ ν_μ, τ⁻ ↔ ν_τ): "
                          f"{a.symbol} and {b.symbol} are not partners")
        if a.is_lepton != b.is_lepton:
            return None, f"the W never turns a quark into a lepton ({a.symbol}, {b.symbol}): it changes flavour within a doublet"
        return None, f"the W changes the charge by one unit, joining an up-type and a down-type quark (u ↔ d) or a lepton and its neutrino: {a.symbol} and {b.symbol} cannot meet it"
    if not same:
        name = {"photon": "the photon", "gluon": "the gluon", "Z": "the Z", "higgs": "the Higgs boson"}[boson]
        return None, (f"{name} does not change flavour ({a.symbol} and {b.symbol} differ): only the W does; there are no flavour-changing "
                      f"neutral currents at tree level")
    if boson == "photon":
        if a.charge == 0:
            return None, f"the photon couples to electric charge: {a.symbol} has none (the Z couples to neutrinos)"
        return VertexRule("QED", "electromagnetic vertex (QED)", f"coupling Q·e with Q = {_charge(a.charge)}; " + _alpha_text(), "electromagnetic"), None
    if boson == "gluon":
        if not a.is_quark:
            return None, f"the gluon couples to colour: {a.symbol} is a lepton and has none"
        return VertexRule("QCD", "strong vertex (QCD)",
                          f"coupling g_s, α_s(m_Z) ≈ {ALPHA_S_MZ:.3f}; colour runs along the quark line and the gluon carries colour and "
                          f"anticolour (r → b + g with rb̄)", "strong"), None
    if boson == "Z":
        return VertexRule("NC", "weak neutral-current vertex (Z)",
                          f"coupling g/cos θ_W · (T₃ − Q sin²θ_W), sin²θ_W ≈ {SIN2_THETA_W:.3f}; it keeps flavour", "weak"), None
    # higgs
    if a.mass_mev == 0:
        return None, f"the Higgs boson couples to mass: {a.symbol} is massless in the Standard Model, so there is no H {a.symbol} vertex"
    return VertexRule("Hff", "Higgs–fermion (Yukawa) vertex",
                      f"coupling y = √2 m/v ≈ {yukawa(a):.3g} for {a.symbol} (v ≈ {V_HIGGS:.0f} GeV): proportional to the mass", "higgs"), None


def _charge(q: Fraction) -> str:
    return fraction_text(q, sign=True)


def vertex_rule(into: Sequence[Particle], out: Sequence[Particle]) -> tuple[VertexRule | None, str | None]:
    """The Standard Model rule of a vertex with particles ``into`` it and ``out`` of it, or
    ``None`` and why there is no such vertex."""
    outgoing = [PARTICLES[p.antiparticle] for p in into] + list(out)   # every line as outgoing (crossing)
    hadrons = [p for p in outgoing if p.is_hadron]
    if hadrons:
        return None, "hadrons do not meet at a vertex: draw their quark lines"
    fermions = [p for p in outgoing if p.is_fermion]
    bosons = [p for p in outgoing if not p.is_fermion]
    kinds = [BOSON_KINDS[p.key] for p in bosons]
    if len(fermions) == 2 and len(bosons) == 1:
        return _fermion_rule(fermions[0], fermions[1], kinds[0])
    if not fermions:
        return _boson_rule(kinds)
    if len(fermions) == 4:
        return None, ("four fermions do not meet at one point in the Standard Model: Fermi's contact interaction is the low-energy "
                      "picture of a W exchanged between two vertices — draw the W")
    return None, (f"a Standard Model vertex joins two fermion lines and one boson, or three or four bosons; this one has "
                  f"{len(fermions)} fermion(s) and {len(bosons)} boson(s)")


def colour_problem(into: Sequence[Particle], out: Sequence[Particle]) -> str | None:
    """A basic colour check: the colours at the vertex (as outgoing: 3, 3̄, 8) must be able to
    make a colourless whole — triplets minus antitriplets a multiple of three, and a gluon never
    alone among colourless lines. ``None`` when they can."""
    reps = [PARTICLES[p.antiparticle].colour for p in into] + [p.colour for p in out]
    n3, n3b, n8 = reps.count("3"), reps.count("3̄"), reps.count("8")
    if (n3 - n3b) % 3 == 0 and not (n8 == 1 and n3 == n3b == 0):
        return None
    shown = " ".join(r for r in reps if r != "1") or "none"
    return (f"colour cannot balance at this vertex (colours {shown}): a quark's colour must run on through the vertex, and a gluon "
            f"meets quarks or gluons")


# ----- checks ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VertexCheck:
    """The checks of one vertex: its ``rule`` (``None`` when it is not a Standard Model vertex),
    the conserved quantities (Q, B, L_e, L_μ, L_τ as :class:`.conservation.Check`), problems and
    the process text (``e⁻ e⁺ → γ``)."""

    vertex: str
    into: tuple[DiagramLine, ...]
    out: tuple[DiagramLine, ...]
    rule: VertexRule | None
    checks: tuple[Check, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def text(self) -> str:
        """``e⁻ e⁺ → γ`` (the lines into the vertex, then out of it)."""
        return " ".join(ln.symbol for ln in self.into) + " → " + " ".join(ln.symbol for ln in self.out)

    def conservation_text(self) -> str:
        """``Q: −1 → −1 + 0 ✓ · L_e: +1 → +1 ✓``."""
        parts = []
        for c in self.checks:
            mark = "✓" if c.conserved else "✗"
            before = " + ".join(_charge(v) for _, v in c.terms_before) or "0"
            after = " + ".join(_charge(v) for _, v in c.terms_after) or "0"
            parts.append(f"{c.symbol}: {before} → {after} {mark}")
        return " · ".join(parts)


@dataclass(frozen=True)
class FermionChain:
    """A fermion line through the diagram: its line ids in the order the fermion number flows,
    the particles along it (as fermions: d → u) and whether it closes (a loop)."""

    lines: tuple[str, ...]
    particles: tuple[Particle, ...]
    closed: bool

    def text(self) -> str:
        names = " → ".join(dict.fromkeys(p.symbol for p in self.particles)) if not self.closed else f"{self.particles[0].symbol} loop"
        p = self.particles[0]
        if p.is_quark:
            return f"{names}: B = 1/3 along the line"
        family = next((s for s, x in zip(("L_e", "L_μ", "L_τ"), p.lepton) if x), "L")
        return f"{names}: {family} = +1 along the line"


@dataclass(frozen=True)
class DiagramCheck:
    """Every check of a diagram (:func:`check_diagram`)."""

    diagram: Diagram
    vertices: tuple[VertexCheck, ...]
    chains: tuple[FermionChain, ...]
    verdict: Verdict
    hadron_verdict: Verdict | None = None
    extra: tuple[str, ...] = field(default=())

    @property
    def problems(self) -> tuple[str, ...]:
        out = [f"vertex {v.vertex} ({v.text()}): {p}" for v in self.vertices for p in v.problems]
        if not self.verdict.allowed:
            out += [f"the reaction {self.verdict.process}: {x}" for x in self.verdict.violations]
        if self.hadron_verdict is not None and not self.hadron_verdict.allowed:
            out += [f"the reaction {self.hadron_verdict.process}: {x}" for x in self.hadron_verdict.violations]
        return tuple(out + list(self.extra))

    @property
    def ok(self) -> bool:
        return not self.problems

    def vertex(self, vertex_id: str) -> VertexCheck:
        return next(v for v in self.vertices if v.vertex == vertex_id)

    def explain(self) -> str:
        """Every vertex with its rule and conservation, the fermion lines, the reaction."""
        lines = [f"{self.diagram.name}: {self.verdict.process}" + (f" ({self.diagram.label})" if self.diagram.label else "")]
        for v in self.vertices:
            mark = "✓" if v.ok else "✗"
            rule = v.rule.name if v.rule is not None else "not a Standard Model vertex"
            lines.append(f"  {mark} {v.vertex}: {v.text()} — {rule}; {v.conservation_text()}")
            lines += [f"      ✗ {p}" for p in v.problems]
        lines += [f"  fermion line: {c.text()}" for c in self.chains]
        lines.append(f"  reaction: {self.verdict.summary()}")
        if self.hadron_verdict is not None:
            lines.append(f"  as hadrons: {self.hadron_verdict.process}: {self.hadron_verdict.summary()}")
        lines += [f"  ✗ {p}" for p in self.extra]
        return "\n".join(lines)


def _vertex_process(into: list[DiagramLine], out: list[DiagramLine]) -> Process:
    """The vertex as a process with every line virtual (off-shell: no energy check). A vertex
    with every line on one side is crossed (one line moved over as its antiparticle)."""
    a = [Leg(ln.particle, True) for ln in into]
    b = [Leg(ln.particle, True) for ln in out]
    if not a:
        a.append(Leg(PARTICLES[b[0].particle.antiparticle], True))
        b = b[1:]
    elif not b:
        b.append(Leg(PARTICLES[a[-1].particle.antiparticle], True))
        a = a[:-1]
    return Process(tuple(a), tuple(b))


def check_vertex(d: Diagram, vertex: str) -> VertexCheck:
    """The checks of one vertex of ``d``."""
    into, out = d.at(vertex)
    pin, pout = [ln.particle for ln in into], [ln.particle for ln in out]
    rule, why = vertex_rule(pin, pout)
    problems = [why] if why else []
    verdict = check(_vertex_process(into, out))
    checks = tuple(c for c in verdict.checks if c.absolute)
    problems += [c.violation() for c in checks if not c.conserved]
    if rule is not None and rule.interaction == "strong" or any(p.colour != "1" for p in pin + pout):
        colour = colour_problem(pin, pout)
        if colour and not why:
            problems.append(colour)
    return VertexCheck(vertex, tuple(into), tuple(out), rule, checks, tuple(dict.fromkeys(problems)))


def fermion_chains(d: Diagram) -> tuple[FermionChain, ...]:
    """The fermion lines through the diagram, each in the direction its fermion number flows."""
    fermions = [ln for ln in d.lines if ln.flow]

    def flow_ends(ln: DiagramLine) -> tuple[str, str]:
        """(where the fermion number comes from, where it goes)."""
        return (ln.start, ln.end) if ln.flow > 0 else (ln.end, ln.start)

    # at each vertex: the fermion line flowing in → the one flowing out
    nxt: dict[str, str] = {}
    has_prev: set[str] = set()
    for v in d.vertices:
        ins = [ln for ln in fermions if flow_ends(ln)[1] == v]
        outs = [ln for ln in fermions if flow_ends(ln)[0] == v]
        if len(ins) == 1 and len(outs) == 1:
            nxt[ins[0].id] = outs[0].id
            has_prev.add(outs[0].id)
    chains: list[FermionChain] = []
    used: set[str] = set()
    for ln in fermions:
        if ln.id in used or ln.id in has_prev:
            continue
        ids = [ln.id]
        while ids[-1] in nxt and nxt[ids[-1]] not in ids:
            ids.append(nxt[ids[-1]])
        used.update(ids)
        chains.append(FermionChain(tuple(ids), tuple(base(d.line(i).particle) for i in ids), False))
    for ln in fermions:   # loops: every line has a predecessor
        if ln.id in used:
            continue
        ids = [ln.id]
        while ids[-1] in nxt and nxt[ids[-1]] not in ids:
            ids.append(nxt[ids[-1]])
        used.update(ids)
        chains.append(FermionChain(tuple(ids), tuple(base(d.line(i).particle) for i in ids), True))
    return tuple(chains)


def check_diagram(d: Diagram) -> DiagramCheck:
    """Check every vertex, the fermion lines and the whole reaction of ``d``."""
    vertices = tuple(check_vertex(d, v) for v in d.vertices)
    verdict = check(d.process())
    hadron = d.hadron_process()
    return DiagramCheck(d, vertices, fermion_chains(d), verdict, check(hadron) if hadron is not None else None)


# ----- presets --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Preset:
    """A standard diagram (or several: the channels of one reaction) with a title."""

    key: str
    title: str
    description: str
    diagrams: tuple[tuple[str, str, tuple[tuple[str, str, str, str, bool], ...]], ...]
    groups: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    spectators: tuple[tuple[str, str], ...] = ()


def _l(line_id: str, p: str, start: str, end: str, label: bool = True) -> tuple[str, str, str, str, bool]:
    return (line_id, p, start, end, label)


_EE_IN = (_l("e_minus", "e-", "in", "v1"), _l("e_plus", "e+", "in", "v1"))
_MUMU_OUT = (_l("mu_minus", "mu-", "v2", "out"), _l("mu_plus", "mu+", "v2", "out"))

PRESETS: dict[str, Preset] = {p.key: p for p in [
    Preset("ee_to_mumu", "e⁺e⁻ → μ⁺μ⁻", "electron–positron annihilation into a muon pair (s-channel γ or Z)",
           (("photon", "s-channel, photon", (*_EE_IN, _l("boson", "gamma", "v1", "v2"), *_MUMU_OUT)),
            ("Z", "s-channel, Z boson", (*_EE_IN, _l("boson", "Z", "v1", "v2"), *_MUMU_OUT)))),
    Preset("compton", "Compton scattering", "e⁻ γ → e⁻ γ (s- and u-channel)",
           (("s", "s-channel", (_l("e_in", "e-", "in", "v1"), _l("gamma_in", "gamma", "in", "v1"), _l("e_mid", "e-", "v1", "v2"),
                                _l("e_out", "e-", "v2", "out"), _l("gamma_out", "gamma", "v2", "out"))),
            ("u", "u-channel", (_l("e_in", "e-", "in", "v1"), _l("gamma_out", "gamma", "v1", "out"), _l("e_mid", "e-", "v1", "v2"),
                                _l("gamma_in", "gamma", "in", "v2"), _l("e_out", "e-", "v2", "out"))))),
    Preset("bhabha", "Bhabha scattering", "e⁺e⁻ → e⁺e⁻ (s- and t-channel)",
           (("s", "s-channel", (*_EE_IN, _l("photon", "gamma", "v1", "v2"), _l("e_minus_out", "e-", "v2", "out"), _l("e_plus_out", "e+", "v2", "out"))),
            ("t", "t-channel", (_l("e_minus", "e-", "in", "v1"), _l("e_minus_out", "e-", "v1", "out"), _l("photon", "gamma", "v1", "v2"),
                                _l("e_plus", "e+", "in", "v2"), _l("e_plus_out", "e+", "v2", "out"))))),
    Preset("moller", "Møller scattering", "e⁻e⁻ → e⁻e⁻ (t- and u-channel)",
           (("t", "t-channel", (_l("e1", "e-", "in", "v1"), _l("e1_out", "e-", "v1", "out"), _l("photon", "gamma", "v1", "v2"),
                                _l("e2", "e-", "in", "v2"), _l("e2_out", "e-", "v2", "out"))),
            ("u", "u-channel", (_l("e1", "e-", "in", "v1"), _l("e2_out", "e-", "v1", "out"), _l("photon", "gamma", "v1", "v2"),
                                _l("e2", "e-", "in", "v2"), _l("e1_out", "e-", "v2", "out"))))),
    Preset("beta_decay", "β⁻ decay", "n → p e⁻ ν̄ₑ at quark level: d → u e⁻ ν̄ₑ through a W⁻",
           (("quark", "quark level", (_l("d_in", "d", "in", "v1"), _l("u_out", "u", "v1", "out"), _l("W", "W-", "v1", "v2"),
                                      _l("e", "e-", "v2", "out"), _l("nu", "anti-nu_e", "v2", "out"))),),
           groups=(("n", "initial", ("d_in", "u_spec", "d_spec")), ("p", "final", ("u_out", "u_spec", "d_spec"))),
           spectators=(("u_spec", "u"), ("d_spec", "d"))),
    Preset("muon_decay", "Muon decay", "μ⁻ → e⁻ ν̄ₑ ν_μ through a W⁻",
           (("W", "", (_l("mu", "mu-", "in", "v1"), _l("nu_mu", "nu_mu", "v1", "out"), _l("W", "W-", "v1", "v2"),
                       _l("e", "e-", "v2", "out"), _l("nu_e", "anti-nu_e", "v2", "out"))),)),
    Preset("pion_decay", "Pion decay", "π⁺ → μ⁺ ν_μ: the u and d̄ annihilate into a W⁺",
           (("W", "", (_l("u", "u", "in", "v1"), _l("dbar", "anti-d", "in", "v1"), _l("W", "W+", "v1", "v2"),
                       _l("mu", "mu+", "v2", "out"), _l("nu", "nu_mu", "v2", "out"))),),
           groups=(("pi+", "initial", ("u", "dbar")),)),
    Preset("drell_yan", "Drell–Yan", "q q̄ → γ*/Z → ℓ⁺ℓ⁻ (here u ū → μ⁻ μ⁺)",
           (("photon", "virtual photon", (_l("q", "u", "in", "v1"), _l("qbar", "anti-u", "in", "v1"), _l("boson", "gamma*", "v1", "v2"), *_MUMU_OUT)),
            ("Z", "Z boson", (_l("q", "u", "in", "v1"), _l("qbar", "anti-u", "in", "v1"), _l("boson", "Z", "v1", "v2"), *_MUMU_OUT)))),
    Preset("gg_to_h", "Gluon fusion: gg → H", "two gluons make a Higgs boson through a top-quark loop",
           (("top", "top-quark loop", (_l("g1", "g", "in", "v1"), _l("g2", "g", "in", "v2"), _l("loop1", "t", "v1", "v3"),
                                       _l("loop2", "t", "v3", "v2", False), _l("loop3", "t", "v2", "v1", False), _l("H", "H", "v3", "out"))),)),
    Preset("h_to_gammagamma", "H → γγ", "the Higgs boson decays to two photons through a loop (top quark or W boson)",
           (("top", "top-quark loop", (_l("H", "H", "in", "v1"), _l("loop1", "t", "v1", "v2"), _l("loop2", "t", "v2", "v3", False),
                                       _l("loop3", "t", "v3", "v1", False), _l("gamma1", "gamma", "v2", "out"), _l("gamma2", "gamma", "v3", "out"))),
            ("W", "W-boson loop", (_l("H", "H", "in", "v1"), _l("loop1", "W+", "v1", "v2"), _l("loop2", "W+", "v2", "v3", False),
                                   _l("loop3", "W-", "v1", "v3"), _l("gamma1", "gamma", "v2", "out"), _l("gamma2", "gamma", "v3", "out"))))),
    Preset("h_to_zz_4l", "H → ZZ* → 4ℓ", "the Higgs boson decays to a Z and an off-shell Z*, each to a lepton pair",
           (("4l", "", (_l("H", "H", "in", "v1"), _l("Z", "Z", "v1", "v2"), _l("Zstar", "Z*", "v1", "v3"),
                        _l("e_minus", "e-", "v2", "out"), _l("e_plus", "e+", "v2", "out"), _l("mu_minus", "mu-", "v3", "out"),
                        _l("mu_plus", "mu+", "v3", "out"))),)),
    Preset("top_decay", "Top-quark decay", "t → W⁺ b (and the W⁺ → e⁺ νₑ)",
           (("W", "", (_l("t", "t", "in", "v1"), _l("W", "W+", "v1", "out"), _l("b", "b", "v1", "out"))),
            ("leptonic", "W⁺ → e⁺ νₑ", (_l("t", "t", "in", "v1"), _l("W", "W+", "v1", "v2"), _l("b", "b", "v1", "out"),
                                         _l("e", "e+", "v2", "out"), _l("nu", "nu_e", "v2", "out"))))),
]}


def preset_diagrams(key: str, spectators: bool = False) -> tuple[Diagram, ...]:
    """The diagrams of preset ``key`` (``spectators``: the spectator quarks and the hadron
    groups too, where the preset has them)."""
    if key not in PRESETS:
        from vidgen.plotcore.data import did_you_mean

        raise VidgenError(f"unknown Feynman-diagram preset '{key}'{did_you_mean(key, list(PRESETS))} (presets: {', '.join(PRESETS)})")
    p = PRESETS[key]
    out = []
    for name, label, lines in p.diagrams:
        specs: list[dict[str, object]] = [{"id": i, "particle": q, "from": a, "to": b, "label": lab} for i, q, a, b, lab in lines]
        groups: list[dict[str, object]] = []
        if p.groups and (spectators or not p.spectators):
            specs += [{"id": i, "particle": q, "from": "in", "to": "out"} for i, q in p.spectators]
            groups = [{"particle": h, "side": side, "lines": list(ids)} for h, side, ids in p.groups]
        out.append(build_diagram(name, specs, groups, label))
    return tuple(out)


__all__ = [
    "ALPHA",
    "ALPHA_S_MZ",
    "BOSON_KINDS",
    "CKM",
    "G_FERMI",
    "LINE_KINDS",
    "PRESETS",
    "SIN2_THETA_W",
    "V_HIGGS",
    "Diagram",
    "DiagramCheck",
    "DiagramLine",
    "FermionChain",
    "HadronGroup",
    "Preset",
    "VertexCheck",
    "VertexRule",
    "base",
    "build_diagram",
    "check_diagram",
    "check_vertex",
    "colour_problem",
    "fermion_chains",
    "fermion_flow",
    "g_weak",
    "preset_diagrams",
    "vertex_rule",
    "yukawa",
]
