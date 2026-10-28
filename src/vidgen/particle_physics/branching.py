"""Branching ratios of common decays (Phase Y, Step 241; DESIGN §99.11) — no manim.

Sources, stated per table (and shown on screen by the ``branching`` scenes):

- **Z, W, π, K, μ**: Particle Data Group, *Review of Particle Physics* (PDG 2024, S. Navas et al.,
  Phys. Rev. D 110, 030001), summary tables — **measured**. The W's three leptonic modes use the
  lepton-universality average ℓν = 10.86 % (the separately measured e, μ, τ values, 10.71, 10.63
  and 11.38 %, add up with the hadrons to slightly more than 100 % within their errors).
- **Higgs boson at 125 GeV**: Standard Model **predictions** of the LHC Higgs Cross Section
  Working Group (CERN Yellow Report 4, 2016, the table for m_H = 125 GeV — 125.00), not
  measurements; at 125.09 GeV or PDG 2024's m_H = 125.20 GeV the values differ in the third
  figure (e.g. bb̄ 58.09 %, WW* 21.52 %, ZZ* 2.641 % at 125.09 GeV).

Values written from memory of those tables are marked ``# check`` for the owner. Every mode with a
process is checked by the conservation checker (:func:`branching_problems`), and each table's
fractions add up to at most 1 (the rest: modes not listed) within :data:`SUM_TOLERANCE` — the Z's
measured fractions, averaged separately, add up to 1.0001."""

from __future__ import annotations

from dataclasses import dataclass

from vidgen.errors import VidgenError

from .names import antiparticle, particle
from .process import Leg, Process, parse_process

PDG = "PDG 2024 (measured)"
#: Measured fractions are averaged separately, so a table may add up to a little over 1 within
#: the quoted precision (the Z's: 1.0001); more than this is an error.
SUM_TOLERANCE = 1e-3
HXSWG = "LHC Higgs XS WG, Yellow Report 4 (2016), SM prediction at m(H) = 125 GeV"


@dataclass(frozen=True)
class Mode:
    """A decay mode: its ``process`` (text, or ``None`` for an inclusive mode such as hadrons),
    ``fraction`` (0–1), an explicit ``name`` for the label (else the products' symbols), a
    ``note`` and ``check`` (a value written from memory, for the owner to verify)."""

    process: str | None
    fraction: float
    name: str = ""
    note: str = ""
    check: bool = False

    @property
    def label(self) -> str:
        """The products as shown: ``bb̄``, ``μ⁺ν_μ``, ``hadrons``."""
        if self.name:
            return self.name
        if self.process is None:
            return "other"
        return "".join(leg.symbol for leg in parse_process(self.process).final)

    @property
    def percent(self) -> float:
        return self.fraction * 100


@dataclass(frozen=True)
class Branching:
    """The listed decay modes of ``parent`` (a particle key), the ``source`` and whether the
    values are ``measured`` or a ``theory`` prediction."""

    parent: str
    modes: tuple[Mode, ...]
    source: str
    kind: str = "measured"

    @property
    def total(self) -> float:
        return sum(m.fraction for m in self.modes)

    def mode(self, label: str) -> Mode:
        """The mode labelled ``label`` (or with that process)."""
        for m in self.modes:
            if label in (m.label, m.process, m.name):
                return m
        raise VidgenError(f"{self.parent} has no listed mode '{label}'; modes: {', '.join(m.label for m in self.modes)}")


_TABLES: dict[str, Branching] = {
    "H": Branching("H", (
        Mode("H -> b anti-b", 0.5824, "bb̄", check=True),
        Mode("H -> W+ W-*", 0.2137, "WW*", check=True),
        Mode("H -> g g", 0.08187, "gg", note="through a top-quark loop", check=True),
        Mode("H -> tau+ tau-", 0.06272, "τ⁺τ⁻", check=True),
        Mode("H -> c anti-c", 0.02891, "cc̄", check=True),
        Mode("H -> Z Z*", 0.02619, "ZZ*", check=True),
        Mode("H -> gamma gamma", 0.002270, "γγ", note="through top and W loops", check=True),
        Mode("H -> Z gamma", 0.001533, "Zγ", check=True),
        Mode("H -> mu+ mu-", 0.0002176, "μ⁺μ⁻", check=True),
    ), HXSWG, "theory"),
    "Z": Branching("Z", (
        Mode(None, 0.69911, "hadrons", note="qq̄ pairs: u, d, s, c, b", check=True),
        Mode("Z -> nu_e anti-nu_e", 0.20000, "invisible", note="νν̄ of the three families", check=True),
        Mode("Z -> e- e+", 0.033632, "e⁺e⁻", check=True),
        Mode("Z -> mu- mu+", 0.033662, "μ⁺μ⁻", check=True),
        Mode("Z -> tau- tau+", 0.033696, "τ⁺τ⁻", check=True),
    ), PDG),
    "W+": Branching("W+", (
        Mode(None, 0.6741, "hadrons", note="ud̄′, cs̄′ pairs", check=True),
        Mode("W+ -> e+ nu_e", 0.1086, note="lepton-universality average ℓν", check=True),
        Mode("W+ -> mu+ nu_mu", 0.1086, note="lepton-universality average ℓν", check=True),
        Mode("W+ -> tau+ nu_tau", 0.1086, note="lepton-universality average ℓν", check=True),
    ), PDG),
    "pi+": Branching("pi+", (
        Mode("pi+ -> mu+ nu_mu", 0.9998770),
        Mode("pi+ -> e+ nu_e", 1.230e-4, note="helicity-suppressed"),
    ), PDG),
    "pi0": Branching("pi0", (
        Mode("pi0 -> gamma gamma", 0.98823),
        Mode("pi0 -> e+ e- gamma", 0.01174, note="Dalitz decay"),
    ), PDG),
    "K+": Branching("K+", (
        Mode("K+ -> mu+ nu_mu", 0.6356, check=True),
        Mode("K+ -> pi+ pi0", 0.2067, check=True),
        Mode("K+ -> pi+ pi+ pi-", 0.05583, check=True),
        Mode("K+ -> pi0 e+ nu_e", 0.0507, check=True),
        Mode("K+ -> pi0 mu+ nu_mu", 0.03352, check=True),
        Mode("K+ -> pi+ pi0 pi0", 0.01760, check=True),
    ), PDG),
    "mu-": Branching("mu-", (
        Mode("mu- -> e- anti-nu_e nu_mu", 1.0, note="≈ 100 % (radiative decays included)"),
    ), PDG),
}


def _conjugate(table: Branching) -> Branching:
    """The table of the antiparticle: every process charge-conjugated."""
    def conj(text: str | None) -> str | None:
        if text is None:
            return None
        p = parse_process(text)

        def legs(side: tuple[Leg, ...]) -> str:
            return " ".join(antiparticle(leg.particle).key + ("*" if leg.off_shell else "") for leg in side)

        return f"{legs(p.initial)} -> {legs(p.final)}"

    anti = antiparticle(table.parent).key
    modes = tuple(Mode(conj(m.process), m.fraction, m.name if m.name in ("hadrons", "invisible", "WW*", "ZZ*") else "", m.note, m.check) for m in table.modes)
    return Branching(anti, modes, table.source, table.kind)


def branching(name: str) -> Branching:
    """The branching ratios of the particle ``name`` (any spelling; antiparticles by charge
    conjugation). Raises ``VidgenError`` naming the particles listed."""
    key = particle(name).key
    if key in _TABLES:
        return _TABLES[key]
    anti = antiparticle(key).key
    if anti in _TABLES:
        return _conjugate(_TABLES[anti])
    listed = sorted(set(_TABLES) | {antiparticle(k).key for k in _TABLES})
    raise VidgenError(f"no branching ratios are listed for {particle(name).symbol} ({key}); listed: {', '.join(listed)}")


def listed() -> list[str]:
    """Particle keys with a table (antiparticles included)."""
    return sorted(set(_TABLES) | {antiparticle(k).key for k in _TABLES})


def branching_problems() -> list[str]:
    """Problems with the tables: a mode the conservation checker forbids, a process whose
    parent is not the table's, fractions out of 0–1 or adding up to more than 1."""
    from .conservation import check

    out = []
    for key in listed():
        table = branching(key)
        for m in table.modes:
            if not 0 < m.fraction <= 1:
                out.append(f"{key}: {m.label}: fraction {m.fraction} is not in (0, 1]")
            if m.process is None:
                continue
            proc: Process = parse_process(m.process)
            if proc.initial[0].particle.key != key:
                out.append(f"{key}: {m.process}: the parent is not {key}")
            verdict = check(proc)
            if not verdict.allowed:
                out.append(f"{key}: {m.process}: {verdict.summary()}")
        if table.total > 1 + SUM_TOLERANCE:
            out.append(f"{key}: the fractions add up to {table.total:.5f} > 1")
    return out


# ----- decay chains -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainNode:
    """A particle of a decay chain: ``leg`` (particle, off-shell), the ``parent`` node index
    (``None`` for the first parent), ``made_by`` (the decay that made it) and ``decay`` (the
    decay it undergoes, or ``None``)."""

    leg: Leg
    parent: int | None
    made_by: int | None
    decay: int | None

    @property
    def particle(self):   # noqa: ANN201 - Particle
        return self.leg.particle

    def lifetime_lines(self) -> list[str]:
        """``τ = 26.03 ns``, ``cτ = 7.804 m`` (a resonance: ``Γ = 2.495 GeV``, ``τ = 2.6 × 10⁻²⁵ s``);
        an off-shell particle: ``off shell (virtual)``."""
        from .kinematics import length_text

        p = self.particle
        if self.leg.off_shell:
            return ["off shell (virtual)"]
        if p.stable:
            return ["stable"]
        if p.lifetime_s is None and p.width_mev:   # the Higgs width is a prediction known to two figures
            return [f"Γ = {p.width_text(2 if p.key == 'H' else 4)}", f"τ = {p.lifetime_text(2)}"]
        out = [f"τ = {p.lifetime_text(4)}"]
        if p.c_tau_m is not None:
            out.append(f"cτ = {length_text(p.c_tau_m, 4)}")
        return out


@dataclass(frozen=True)
class Chain:
    """A decay chain: its ``nodes`` (the first parent first, products in order) and its
    ``decays`` (processes, in the order given), with each decay's ``fraction`` when listed."""

    nodes: tuple[ChainNode, ...]
    decays: tuple[Process, ...]
    fractions: tuple[float | None, ...]

    def children(self, i: int) -> list[int]:
        return [k for k, n in enumerate(self.nodes) if n.parent == i]


def _same_products(a: Process, b: Process) -> bool:
    return sorted(leg.particle.key for leg in a.final) == sorted(leg.particle.key for leg in b.final)


def mode_fraction(process: Process) -> float | None:
    """The branching fraction of ``process`` when its parent's table lists it, else ``None``."""
    try:
        table = branching(process.initial[0].particle.key)
    except VidgenError:
        return None
    for m in table.modes:
        if m.process is not None and _same_products(parse_process(m.process), process):
            return m.fraction
    return None


def chain(decays: list[str]) -> Chain:
    """Build a decay chain from decay texts (``["pi+ -> mu+ nu_mu", "mu+ -> e+ nu_e
    anti-nu_mu"]``): the first decay's parent starts it; each later decay's parent must be a
    product not yet decayed (the first such one). Every decay must be allowed by the
    conservation checker. Raises ``VidgenError`` saying which decay is wrong and why."""
    from .conservation import check

    if not decays:
        raise VidgenError("a decay chain needs at least one decay, e.g. 'pi+ -> mu+ nu_mu'")
    nodes: list[ChainNode] = []
    procs: list[Process] = []
    for k, text in enumerate(decays):
        where = f"decays[{k + 1}] ('{text}')"
        try:
            proc = parse_process(text)
        except VidgenError as error:
            raise VidgenError(f"{where}: {error}") from None
        if len(proc.initial) != 1:
            raise VidgenError(f"{where}: a decay has one particle before the arrow")
        verdict = check(proc)
        if not verdict.allowed:
            raise VidgenError(f"{where}: {verdict.summary()}")
        head = proc.initial[0]
        if k == 0:
            nodes.append(ChainNode(head, None, None, 0))
            parent = 0
        else:
            free = [i for i, n in enumerate(nodes) if n.decay is None and n.parent is not None]
            exact = [i for i in free if nodes[i].leg.particle.key == head.particle.key and nodes[i].leg.off_shell == head.off_shell]
            loose = [i for i in free if nodes[i].leg.particle.key == head.particle.key]
            match = (exact or loose or [None])[0]
            if match is None:
                left = ", ".join(nodes[i].leg.symbol for i in free) or "none"
                raise VidgenError(f"{where}: no {head.symbol} to decay among the products not yet decayed ({left})")
            nodes[match] = ChainNode(nodes[match].leg, nodes[match].parent, nodes[match].made_by, k)
            parent = match
        for leg in proc.final:
            nodes.append(ChainNode(leg, parent, k, None))
        procs.append(proc)
    return Chain(tuple(nodes), tuple(procs), tuple(mode_fraction(p) for p in procs))


__all__ = ["HXSWG", "PDG", "SUM_TOLERANCE", "Branching", "Chain", "ChainNode", "Mode", "branching", "branching_problems", "chain", "listed", "mode_fraction"]
