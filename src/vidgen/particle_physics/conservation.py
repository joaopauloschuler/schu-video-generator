"""Which reactions and decays can happen, and why (Phase Y, Step 237; DESIGN §99.3). No manim.

:func:`check` takes a process (``"n -> p e- anti-nu_e"``) and checks, with teaching-style
explanations ("lepton number L_e not conserved: 0 → +1"):

- **Conserved by every interaction**: electric charge Q, baryon number B, the lepton family
  numbers L_e, L_μ, L_τ (the Standard Model without neutrino masses; only neutrino oscillations,
  over long flights, are seen to change them), angular momentum (as far as counting can tell: a
  half-integer total spin cannot become integer, so the number of fermions changes by an even
  number), and energy: a decay needs the parent heavier than the products (off-shell ``Z*``,
  ``W*`` do not count); a reaction gets its threshold (√s and the beam energy on a fixed target);
  two real particles merge into one only if it is at least as heavy as both (e⁺e⁻ → Z can happen
  at √s = m_Z; e⁺e⁻ → γ with a real photon never can).
- **Which interaction**: a W, Z or neutrino means the weak interaction, and so does a change of
  quark flavour (S, C, B′, T), by at most one unit each per W (``|ΔS| = 2`` is refused as
  first-order forbidden); a Higgs boson means a Higgs coupling (flavour kept); else photons or
  charged leptons mean electromagnetic, and only hadrons, quarks and gluons strong.
- **Conserved by the strong and electromagnetic interactions only**: flavour, C-parity (checked
  when every particle has one: π⁰ → γγγ is refused) and, strong only, G-parity (η → πππ is not
  strong: it is slow, isospin-violating). The Landau–Yang theorem: a spin-1 particle never decays
  into two photons.

Parity and orbital angular momentum are not checked (they need the partial waves), nor colour
(quarks and gluons are counted, not their colours).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from fractions import Fraction

from .data import ENERGY_UNITS, FLAVOUR_NAMES, FLAVOURS, LEPTON_FAMILIES, Particle, energy_text, fraction_text
from .process import Leg, Process, as_process

#: What each interaction conserves (quantity, strong, electromagnetic, weak) — for docs and lint.
CONSERVATION_TABLE: tuple[tuple[str, str, str, str], ...] = (
    ("electric charge Q", "yes", "yes", "yes"),
    ("baryon number B", "yes", "yes", "yes"),
    ("lepton family numbers L_e, L_μ, L_τ", "yes", "yes", "yes"),
    ("energy, momentum, angular momentum", "yes", "yes", "yes"),
    ("strangeness S, charm C, beauty B′, topness T", "yes", "yes", "no: one unit per W (|ΔS| ≤ 1)"),
    ("parity P", "yes", "yes", "no"),
    ("C-parity", "yes", "yes", "no"),
    ("isospin, G-parity", "yes", "no", "no"),
)
#: One line on each interaction, for explanations.
INTERACTIONS: dict[str, str] = {
    "strong": "the strong interaction (gluons between quarks): conserves every quantum number in the table; "
              "the fastest decays (widths of MeV to hundreds of MeV, lifetimes near 10⁻²³ s)",
    "electromagnetic": "the electromagnetic interaction (photons): conserves flavour, parity and C-parity, not isospin; "
                       "lifetimes near 10⁻²⁰ to 10⁻¹⁶ s",
    "weak": "the weak interaction (W and Z bosons): conserves charge, baryon number and each lepton family number, "
            "changes quark flavour by one unit per W and violates parity and C; the slowest decays (10⁻¹³ s and longer), "
            "the only interaction neutrinos feel",
    "higgs": "a Higgs-boson coupling: its strength is proportional to the mass of the particle it couples to; it keeps every flavour",
}
WEAK_BOSONS = ("W+", "W-", "Z")
TICK, CROSS, CHANGED = "✓", "✗", "Δ"


@dataclass(frozen=True)
class Check:
    """One quantity before and after (``before``/``after`` with each particle's share)."""

    quantity: str
    symbol: str
    before: Fraction
    after: Fraction
    terms_before: tuple[tuple[str, Fraction], ...]
    terms_after: tuple[tuple[str, Fraction], ...]
    #: Conserved by every interaction (charge, baryon and lepton numbers); a flavour is not.
    absolute: bool = True

    @property
    def conserved(self) -> bool:
        return self.before == self.after

    def text(self) -> str:
        """``charge Q: 0 → 0``."""
        return f"{self.quantity} {self.symbol}: {_value(self.before)} → {_value(self.after)}"

    def detail(self) -> str:
        """``Q: n 0 → p +1, e⁻ −1, ν̄ₑ 0 (total 0)``."""
        def side(terms: tuple[tuple[str, Fraction], ...], total: Fraction) -> str:
            parts = ", ".join(f"{s} {_value(v)}" for s, v in terms)
            return parts if len(terms) == 1 else f"{parts} (total {_value(total)})"

        return f"{self.symbol}: {side(self.terms_before, self.before)} → {side(self.terms_after, self.after)}"

    def violation(self) -> str:
        """``baryon number not conserved: B = 1 → 0``."""
        return f"{self.quantity} not conserved: {self.symbol} = {_value(self.before)} → {_value(self.after)}"


@dataclass(frozen=True)
class Threshold:
    """Masses before and after (MeV, off-shell legs left out), Q = before − after, the least √s
    for the products, and for two particles before, the beam energy needed on a fixed target
    (the second particle at rest)."""

    initial_mev: float
    final_mev: float
    sqrt_s_mev: float
    beam_mev: float | None = None
    beam_kinetic_mev: float | None = None

    @property
    def q_mev(self) -> float:
        """Q value: the mass that turns into kinetic energy (negative: energy must be supplied)."""
        return self.initial_mev - self.final_mev


@dataclass(frozen=True)
class Verdict:
    """The result of :func:`check`: ``allowed``, the ``interaction`` (``strong``,
    ``electromagnetic``, ``weak``, ``higgs`` or ``None`` when forbidden), every check, the
    reasons it is forbidden (``violations``) and notes."""

    process: Process
    allowed: bool
    interaction: str | None
    checks: tuple[Check, ...]
    violations: tuple[str, ...]
    notes: tuple[str, ...]
    threshold: Threshold
    energy: str
    energy_ok: bool | None

    def check_of(self, symbol: str) -> Check:
        """The check of quantity ``symbol`` (``Q``, ``B``, ``L_e``, ``S``...)."""
        return next(c for c in self.checks if c.symbol == symbol)

    def summary(self) -> str:
        """``allowed: weak interaction`` or ``forbidden: baryon number not conserved: B = 1 → 0``."""
        if self.allowed:
            return f"allowed: {_interaction_name(self.interaction)}"
        return "forbidden: " + "; ".join(self.violations)

    def explain(self) -> str:
        """Every check with a tick, a cross (broken) or Δ (a flavour the weak interaction may
        change), the energy, then the notes."""
        lines = [f"{self.process}: {self.summary()}"]
        for c in self.checks:
            mark = TICK if c.conserved else (CHANGED if self.allowed and not c.absolute else CROSS)
            lines.append(f"  {mark} {c.detail()}")
        if self.energy:
            lines.append(f"  {TICK if self.energy_ok in (True, None) else CROSS} {self.energy}")
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def _value(v: Fraction) -> str:
    return fraction_text(v, sign=True)


def _interaction_name(interaction: str | None) -> str:
    return {"higgs": "a Higgs-boson coupling", None: "no interaction"}.get(interaction, f"{interaction} interaction")


def _sum_check(quantity: str, symbol: str, legs_i: tuple[Leg, ...], legs_f: tuple[Leg, ...], value) -> Check:  # type: ignore[no-untyped-def]
    ti = tuple((leg.symbol, Fraction(value(leg.particle))) for leg in legs_i)
    tf = tuple((leg.symbol, Fraction(value(leg.particle))) for leg in legs_f)
    return Check(quantity, symbol, sum((v for _, v in ti), Fraction(0)), sum((v for _, v in tf), Fraction(0)), ti, tf)


def _absolute_checks(proc: Process) -> list[Check]:
    checks = [
        _sum_check("charge", "Q", proc.initial, proc.final, lambda p: p.charge),
        _sum_check("baryon number", "B", proc.initial, proc.final, lambda p: p.baryon),
    ]
    names = ("electron number", "muon number", "tau number")
    for i, (name, symbol) in enumerate(zip(names, LEPTON_FAMILIES)):
        involved = any(leg.particle.lepton[i] for leg in proc.legs)
        if involved:
            checks.append(_sum_check(name, symbol, proc.initial, proc.final, lambda p, i=i: p.lepton[i]))
    return checks


def _flavour_checks(proc: Process) -> tuple[list[Check], list[str]]:
    """S, C, B′, T checks for the reading of mixtures (K⁰_S as K⁰ or K̄⁰) that changes flavour
    least, and notes naming the reading."""
    legs = proc.legs
    options = [leg.particle.flavour_options() for leg in legs]
    n_initial = len(proc.initial)
    best: tuple[int, tuple[tuple[int, int, int, int], ...]] | None = None
    for combo in itertools.product(*options):
        delta = [sum(f[i] for f in combo[n_initial:]) - sum(f[i] for f in combo[:n_initial]) for i in range(4)]
        cost = sum(abs(d) for d in delta)
        if best is None or cost < best[0]:
            best = (cost, combo)
    assert best is not None
    combo = best[1]
    checks: list[Check] = []
    for i, symbol in enumerate(FLAVOURS):
        if not any(f[i] for f in combo):
            continue
        ti = tuple((leg.symbol, Fraction(f[i])) for leg, f in zip(proc.initial, combo[:n_initial]))
        tf = tuple((leg.symbol, Fraction(f[i])) for leg, f in zip(proc.final, combo[n_initial:]))
        checks.append(Check(FLAVOUR_NAMES[symbol], symbol, sum((v for _, v in ti), Fraction(0)), sum((v for _, v in tf), Fraction(0)), ti, tf,
                            absolute=False))
    notes = []
    for leg, opts, f in zip(legs, options, combo):
        if len(opts) > 1:
            as_what = "K⁰ (S = +1)" if f[0] > 0 else "K̄⁰ (S = −1)"
            notes.append(f"{leg.particle.symbol} has no definite strangeness (a mixture of K⁰ and K̄⁰); read here as {as_what}")
    return checks, notes


def _threshold(proc: Process) -> Threshold:
    initial = sum(leg.particle.mass_mev for leg in proc.initial if not leg.off_shell)
    final = sum(leg.particle.mass_mev for leg in proc.final if not leg.off_shell)
    beam = kinetic = None
    if len(proc.initial) == 2 and final > initial:
        m_a, m_b = (leg.particle.mass_mev for leg in proc.initial)
        if m_b > 0:
            beam = (final**2 - m_a**2 - m_b**2) / (2 * m_b)
            kinetic = beam - m_a
    return Threshold(initial, final, max(final, initial), beam, kinetic)


def _unit(mev: float) -> str:
    """The unit an energy line is written in: that of its largest mass."""
    return next((u for u, s in ENERGY_UNITS if mev >= s), "MeV") if mev >= 1.0 else "MeV"


def _mass(p: Particle, unit: str) -> str:
    return "0" if p.mass_mev == 0 else energy_text(p.mass_mev, 4, unit)


def _masses(legs: tuple[Leg, ...], unit: str, total: float) -> str:
    """``938.3 MeV + 0.5110 MeV + 0 = 938.8 MeV`` (one unit; the total only for two or more)."""
    on = [leg.particle for leg in legs if not leg.off_shell]
    if len(on) < 2:
        return _mass(on[0], unit) if on else "0"
    return " + ".join(_mass(p, unit) for p in on) + f" = {energy_text(total, 4, unit)}"


def _article(word: str) -> str:
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def _energy(proc: Process, t: Threshold) -> tuple[str, bool | None, list[str]]:
    """The energy line, whether a decay is allowed by it (``None`` for a reaction), and notes."""
    notes = []
    off = [leg for leg in proc.legs if leg.off_shell]
    if off:
        names = ", ".join(leg.symbol for leg in off)
        notes.append(f"{names} {'is' if len(off) == 1 else 'are'} off-shell (virtual): the mass is not fixed, so it does not count in the energy check")
    if proc.is_decay:
        parent = proc.initial[0]
        if parent.off_shell:
            return "", None, notes
        m = parent.particle.mass_mev
        unit = parent.particle.unit if m > 0 else _unit(t.final_mev)
        if m > t.final_mev:
            text = (f"energy: m({parent.symbol}) = {_mass(parent.particle, unit)} > {_masses(proc.final, unit, t.final_mev)}; "
                    f"Q = {energy_text(t.q_mev, 4)} becomes kinetic energy")
            return text, True, notes
        text = f"energy not conserved: m({parent.symbol}) = {_mass(parent.particle, unit)} is not more than the products' {energy_text(t.final_mev, 4, unit)}"
        if parent.particle.key == "p" and any(leg.particle.key == "n" for leg in proc.final):
            notes.append("a free proton cannot do this; in a proton-rich nucleus the binding energy can make up the difference (β⁺ decay)")
        if m == 0:
            notes.append(f"a free massless {parent.particle.name} cannot decay; a photon turns into an e⁺e⁻ pair only near a nucleus, which takes up the recoil (pair production)")
        heavy = [leg for leg in proc.final if leg.particle.key in WEAK_BOSONS and not leg.off_shell]
        if heavy and m > t.final_mev - heavy[-1].particle.mass_mev:
            notes.append(f"with one {heavy[-1].symbol} off-shell (write {heavy[-1].particle.key}*) the decay can happen, as H → ZZ* does")
        return text, False, notes
    if t.final_mev > t.initial_mev:
        text = f"energy: the products need √s ≥ {energy_text(t.sqrt_s_mev, 4)} (Q = {energy_text(t.q_mev, 4)})"
        if t.beam_mev is not None:
            a, b = proc.initial[0].particle, proc.initial[1].particle
            text += (f"; on {_article(b.name)} at rest, {_article(a.name)} needs E ≥ {energy_text(t.beam_mev, 4)} "
                     f"(kinetic energy {energy_text(t.beam_kinetic_mev or 0.0, 4)})")
        return text, None, notes
    return f"energy: no threshold (Q = {energy_text(t.q_mev, 4)} ≥ 0)", None, notes


def _merge_problem(proc: Process) -> str | None:
    """Two real particles merging into one: possible only at √s = M of the product (resonance
    formation, e⁺e⁻ → Z), and √s ≥ m_a + m_b, so the product must be at least as heavy as the
    two together. A single real photon (M = 0) can never be made this way."""
    if len(proc.initial) != 2 or len(proc.final) != 1 or any(leg.off_shell for leg in proc.legs):
        return None
    a, b = (leg.particle for leg in proc.initial)
    product = proc.final[0]
    m = product.particle.mass_mev
    if m >= a.mass_mev + b.mass_mev and m > 0:
        return None
    unit = _unit(max(a.mass_mev + b.mass_mev, m))
    if m == 0:
        return (f"energy and momentum: two particles cannot merge into one real massless {product.symbol} — its √s would be 0, but "
                f"two particles have √s ≥ {_masses(proc.initial, unit, a.mass_mev + b.mass_mev)}; they make two photons, or a virtual "
                f"one (write {product.particle.key}*) that goes on to something else")
    return (f"energy and momentum: two particles merge into one only at √s = m({product.symbol}) = {_mass(product.particle, unit)}, "
            f"below their √s ≥ {_masses(proc.initial, unit, a.mass_mev + b.mass_mev)}")


def _product(values: list[int]) -> int:
    return math.prod(values)


def _sign(value: int) -> str:
    return fraction_text(Fraction(value), sign=True)


def check(process: Process | str) -> Verdict:
    """Check a reaction or decay; see the module docstring for the rules."""
    proc = as_process(process)
    checks = _absolute_checks(proc)
    violations = [c.violation() for c in checks if not c.conserved]
    notes: list[str] = []
    if any(c.symbol in LEPTON_FAMILIES and not c.conserved for c in checks):
        notes.append("lepton family numbers are conserved in every reaction and decay seen; only neutrino oscillations "
                     "(over long flights) change them")
    fermions = sum(1 for leg in proc.legs if leg.particle.is_fermion)
    if fermions % 2:
        violations.append("angular momentum not conserved: a half-integer total spin cannot become integer "
                          f"({sum(1 for leg in proc.initial if leg.particle.is_fermion)} fermion(s) before, "
                          f"{sum(1 for leg in proc.final if leg.particle.is_fermion)} after)")
    threshold = _threshold(proc)
    energy, energy_ok, energy_notes = _energy(proc, threshold)
    notes += energy_notes
    if energy_ok is False:
        violations.append(energy.replace("energy not conserved: ", "energy: "))
    merge = _merge_problem(proc)
    if merge:
        violations.append(merge)
    ps = proc.particles()
    if (proc.is_decay and proc.initial[0].particle.spin == 1 and len(proc.final) == 2
            and all(leg.particle.key == "gamma" for leg in proc.final)):
        violations.append(f"a spin-1 particle cannot decay into two photons (Landau–Yang theorem): {proc.initial[0].symbol} → γγ never happens")
    flavour, flavour_notes = _flavour_checks(proc)
    checks += flavour
    notes += flavour_notes
    if any(p.is_quark for p in ps):
        notes.append("quark-level process: quarks are bound in hadrons and their masses depend on the scheme, so the energy check is "
                     "only indicative; colour is not checked here")
    interaction: str | None = None
    if not violations:
        interaction, more_violations, more_notes = _interaction(proc, flavour)
        violations += more_violations
        notes += more_notes
    allowed = not violations
    return Verdict(proc, allowed, interaction if allowed else None, tuple(checks), tuple(violations), tuple(notes), threshold, energy, energy_ok)


def _interaction(proc: Process, flavour: list[Check]) -> tuple[str, list[str], list[str]]:
    ps = proc.particles()
    keys = {p.key for p in ps}
    changed = [c for c in flavour if not c.conserved]
    violations: list[str] = []
    notes: list[str] = []
    if "H" in keys:
        if changed:
            violations.append("the Higgs boson's couplings keep every quark flavour: " + "; ".join(c.violation() for c in changed))
        others = [p for p in ps if p.key != "H"]
        if others and all(p.mass_mev == 0 for p in others):
            notes.append("the Higgs boson has no direct coupling to massless photons or gluons: this goes through a loop of heavy "
                         "particles (the top quark, and the W boson for photons)")
        return "higgs", violations, notes
    if keys & set(WEAK_BOSONS) or any(p.is_neutrino for p in ps) or changed:
        for c in changed:
            step = abs(c.after - c.before)
            if step > 1:
                violations.append(f"{c.quantity} changes by {step}: a weak interaction changes it by at most one unit "
                                  f"({c.symbol} = {_value(c.before)} → {_value(c.after)}); it would take two weak steps and is not seen")
        if changed and not violations:
            notes.append("flavour changes (" + ", ".join(f"Δ{c.symbol} = {_value(c.after - c.before)}" for c in changed)
                         + "): only the weak interaction does that")
        elif any(p.is_neutrino for p in ps):
            notes.append("a neutrino takes part: only the weak interaction acts on neutrinos")
        return "weak", violations, notes
    em = "gamma" in keys or any(p.is_lepton and p.charge != 0 for p in ps)
    c_values = [p.c_parity for p in ps]
    if all(c is not None for c in c_values):
        before = _product([p.c_parity for p in proc.particles("initial")])  # type: ignore[misc]
        after = _product([p.c_parity for p in proc.particles("final")])  # type: ignore[misc]
        if before != after:
            violations.append(f"C-parity not conserved: C = {_sign(before)} → {_sign(after)} (strong and electromagnetic interactions conserve C)")
            return "electromagnetic" if em else "strong", violations, notes
    if em:
        return "electromagnetic", violations, notes
    g_values = [p.g_parity for p in ps]
    if all(g is not None for g in g_values):
        before = _product([p.g_parity for p in proc.particles("initial")])  # type: ignore[misc]
        after = _product([p.g_parity for p in proc.particles("final")])  # type: ignore[misc]
        if before != after:
            notes.append(f"not strong: G-parity {_sign(before)} → {_sign(after)} (the strong interaction conserves isospin and G); it goes "
                         "through isospin-violating effects (the u–d mass difference, electromagnetism), so it is slow")
            return "electromagnetic", violations, notes
    return "strong", violations, notes


def allowed(process: Process | str) -> bool:
    """Whether :func:`check` allows the process."""
    return check(process).allowed


__all__ = ["CONSERVATION_TABLE", "INTERACTIONS", "Check", "Threshold", "Verdict", "allowed", "check"]
