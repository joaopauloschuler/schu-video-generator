"""Relativistic kinematics (Phase Y, Step 239; DESIGN §99.7). No manim.

Four-vectors (E, p) in natural units — energies, momenta and masses all in MeV with c = 1 —
with the conversions to SI shown through ``vidgen.quantities`` (MeV → J, MeV/c → kg·m/s, MeV/c²
→ kg); the invariant mass of a system, m² = (ΣE)² − |Σp|²; two-body decays in the parent's rest
frame, p* = √λ(M², m₁², m₂²) / 2M with the Källén function λ; Lorentz boosts (β, γ; a decay seen
in the lab, the opening angle of its products); thresholds on a fixed target and at a collider
(from the conservation checker's :class:`~.conservation.Threshold`); time dilation and the mean
decay length L = βγcτ from the PDG lifetimes of :mod:`.data`.

Every value is computed from the masses (PDG 2024, :mod:`.data`); nothing is hard-coded. Errors
the author can cause — a decay below threshold, a negative mass², β ≥ 1, an energy below the
mass — raise :class:`~vidgen.errors.VidgenError` with the numbers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Context, Decimal
from fractions import Fraction
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore import register_model
from vidgen.quantities.quantity import decimal_text
from vidgen.quantities.units import parse_unit

from .conservation import Threshold, check
from .data import EDITION, Particle, energy_text
from .names import particle
from .process import Process, as_process

#: The kinds of a value in natural units and their unit suffix: an energy (MeV), a momentum
#: (MeV/c), a mass (MeV/c²).
KINDS = {"energy": "", "momentum": "/c", "mass": "/c²"}
#: The SI unit each kind converts to.
SI_UNITS = {"energy": "J", "momentum": "kg·m/s", "mass": "kg"}
_SI_PARSE = {"energy": "MeV", "momentum": "MeV/c", "mass": "MeV/c^2"}
#: m² as small as this fraction of E² (rounding) counts as zero, not negative.
MASS2_TOLERANCE = 1e-9


# ----- values and units -------------------------------------------------------------------------


def value_text(mev: float, kind: str = "energy", digits: int = 4, unit: str | None = None) -> str:
    """``29.79 MeV/c``, ``62.60 GeV``, ``139.6 MeV/c²``: a value in natural units with the unit
    of its kind (``unit``: MeV, GeV... for all; default the largest giving a number ≥ 1)."""
    mev = float(f"{mev:.12g}")   # 999.9999999998 (a boost's rounding) is 1 GeV
    return energy_text(mev, digits, unit) + ("" if mev == 0 else KINDS[_kind(kind)])


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise VidgenError(f"kind '{kind}' is not one of {', '.join(KINDS)}")
    return kind


def to_si(mev: float, kind: str = "energy") -> float:
    """A value in MeV (energy), MeV/c (momentum) or MeV/c² (mass) in SI: J, kg·m/s, kg — the
    unit factors of ``vidgen.quantities`` (exact e and c of the SI 2019)."""
    return float(parse_unit(_SI_PARSE[_kind(kind)]).to_si(mev))


def from_si(value: float, kind: str = "energy") -> float:
    """An SI value (J, kg·m/s, kg) in MeV, MeV/c or MeV/c²."""
    return float(parse_unit(_SI_PARSE[_kind(kind)]).from_si(value))


def si_text(mev: float, kind: str = "energy", digits: int = 4, unit: str | None = None) -> str:
    """``29.79 MeV/c = 1.592 × 10⁻²⁰ kg·m/s``: the value in natural units and in SI."""
    si = to_si(mev, kind)
    return f"{value_text(mev, kind, digits, unit)} = {decimal_text(si, digits, 'sci').plain} {SI_UNITS[kind]}"


_NUMBER = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")
_EXAMPLES = {"energy": "4 GeV, 500 MeV", "momentum": "10 GeV/c, 200 MeV/c", "mass": "125.2 GeV/c^2"}


def natural_value(text: str | float, kind: str = "momentum") -> float:
    """``"10 GeV/c"`` → 10000 (MeV/c), ``"4 GeV"`` → 4000 (MeV), ``"1.6e-19 kg m/s"`` too: a value
    with its unit (any of ``vidgen.quantities``' units of that kind) in MeV, MeV/c or MeV/c²."""
    kind = _kind(kind)
    m = _NUMBER.match(str(text))
    if m is None or not m.group(2):
        raise VidgenError(f"'{text}': write the {kind} with its unit ({_EXAMPLES[kind]})")
    unit, base = parse_unit(m.group(2)), parse_unit(_SI_PARSE[kind])
    if unit.dim != base.dim:
        raise VidgenError(f"'{text}': {m.group(2)} is not a unit of {kind} ({_EXAMPLES[kind]})")
    return float(base.from_si(unit.to_si(float(m.group(1)))))


def mass_of(name: str | Particle) -> float:
    """The PDG mass of a particle (MeV/c²) by any of its names (``pi+``, ``π⁺``, ``muon``)."""
    return (name if isinstance(name, Particle) else particle(name)).mass_mev


#: What :func:`pdg_value` reads.
PDG_QUANTITIES = ("mass", "lifetime", "width")


@dataclass(frozen=True)
class PdgValue:
    """A particle's PDG value written for a calculation: ``number`` (a decimal string with the
    table's significant figures) in ``unit``, what it is (``meaning``) and the ``source``."""

    particle: Particle
    quantity: str
    number: str
    unit: str
    meaning: str
    source: str


def pdg_value(name: str | Particle, quantity: str = "mass", unit: str = "") -> PdgValue:
    """A particle's mass (MeV/c² below 1 GeV, else GeV/c²), mean life (s) or width (MeV below 1
    GeV, else GeV) from PDG 2024 for a ``calculation`` symbol (``mass: pi+``), in ``unit`` if
    given (``GeV/c^2``, ``ns``, ``keV``). Significant figures as the table gives them (a width
    computed from the mean life: 4)."""
    p = name if isinstance(name, Particle) else particle(name)
    if quantity not in PDG_QUANTITIES:
        raise VidgenError(f"'{quantity}' is not one of {', '.join(PDG_QUANTITIES)}")
    if quantity == "mass":
        if p.mass_limit_mev is not None:
            raise VidgenError(f"the {p.name}'s mass is only bounded (< {energy_text(p.mass_limit_mev, 1)}): no value to calculate with")
        raw, natural, sig = Fraction(Decimal(repr(p.mass_mev))), "MeV/c^2", _sig(p.mass_mev, p.digits)
        default = "MeV/c^2" if p.mass_mev < 1000 else "GeV/c^2"
        meaning = f"{p.symbol} mass"
    elif quantity == "lifetime":
        if p.stable or p.lifetime is None:
            raise VidgenError(f"the {p.name} ({p.symbol}) {'is stable' if p.stable else 'has no mean life in the table'}")
        given = p.lifetime_s is not None
        raw, natural, sig = Fraction(Decimal(repr(p.lifetime))), "s", _sig(p.lifetime, 0) if given else 4
        default, meaning = "s", f"{p.symbol} mean life"
    else:
        if p.stable or p.width is None:
            raise VidgenError(f"the {p.name} ({p.symbol}) {'is stable' if p.stable else 'has no width in the table'}")
        given = p.width_mev is not None
        raw, natural, sig = Fraction(Decimal(repr(p.width))), "MeV", _sig(p.width, 0) if given else 4
        default, meaning = ("MeV" if p.width < 1000 else "GeV"), f"{p.symbol} width"
    target = unit or default
    shown, base = parse_unit(target), parse_unit(natural)
    if shown.dim != base.dim:
        raise VidgenError(f"unit '{target}' does not fit a {quantity} (it is in {natural})")
    value = Fraction(raw) * Fraction(base.factor) / Fraction(shown.factor)
    return PdgValue(p, quantity, _decimal_string(value, sig), target, meaning, EDITION)


def _sig(value: float, least: int) -> int:
    """Significant figures of a table value (its digits, trailing zeros of the float lost), at
    least ``least``."""
    digits = Decimal(repr(value)).normalize().as_tuple().digits
    return max(len(digits), least)


def _decimal_string(value: Fraction, sig: int) -> str:
    """``0.13957039``, ``2.6033e-08``: ``value`` with ``sig`` significant figures, plainly from
    10⁻³ to 10⁶, else in e-notation (both readable by the calculation's value parser)."""
    ctx = Context(prec=sig)
    d = ctx.divide(Decimal(value.numerator), Decimal(value.denominator))
    if d == 0:
        return "0"
    if Decimal("1e-3") <= abs(d) < Decimal("1e6"):
        exp = d.adjusted() - sig + 1
        return format(d.quantize(Decimal(1).scaleb(exp)), "f")
    return f"{d:.{sig - 1}e}"


# ----- four-vectors -------------------------------------------------------------------------------


@dataclass(frozen=True)
class FourVector:
    """(E, px, py, pz) in MeV with c = 1. Pictures use the x–y plane (pz = 0)."""

    energy: float
    px: float = 0.0
    py: float = 0.0
    pz: float = 0.0

    @classmethod
    def from_mass(cls, mass: float, momentum: float = 0.0, angle: float = 0.0) -> "FourVector":
        """A particle of ``mass`` with momentum ``momentum`` (MeV/c) at ``angle`` degrees from
        the x axis in the x–y plane: E = √(m² + p²)."""
        if mass < 0:
            raise VidgenError(f"a mass cannot be negative (got {mass:g} MeV/c²)")
        if momentum < 0:
            raise VidgenError(f"a momentum's size cannot be negative (got {momentum:g} MeV/c); turn the angle by 180° instead")
        a = math.radians(angle)
        return cls(math.hypot(mass, momentum), momentum * math.cos(a), momentum * math.sin(a), 0.0)

    @property
    def p3(self) -> np.ndarray:
        return np.array([self.px, self.py, self.pz])

    @property
    def p(self) -> float:
        """|p| (MeV/c)."""
        return math.sqrt(self.px**2 + self.py**2 + self.pz**2)

    @property
    def mass2(self) -> float:
        """m² = E² − |p|² (MeV²), the invariant (rounding below :data:`MASS2_TOLERANCE` × E² is 0)."""
        m2 = self.energy**2 - (self.px**2 + self.py**2 + self.pz**2)
        return 0.0 if abs(m2) <= MASS2_TOLERANCE * max(self.energy**2, 1e-300) else m2

    @property
    def mass(self) -> float:
        """√(E² − |p|²); a negative m² (a momentum larger than the energy) is an error."""
        m2 = self.mass2
        if m2 < 0:
            raise VidgenError(f"negative mass²: E² − |p|² = {_g(self.energy)}² − {_g(self.p)}² = {_g(m2)} MeV² < 0 — "
                              "nothing real has |p| > E (c = 1): check the energy and momentum")
        return math.sqrt(m2)

    @property
    def angle(self) -> float:
        """The direction in the x–y plane, degrees from the x axis."""
        return math.degrees(math.atan2(self.py, self.px))

    @property
    def beta_vector(self) -> np.ndarray:
        """β = p / E (the velocity over c)."""
        if self.energy <= 0:
            raise VidgenError(f"the energy must be positive to have a velocity (got {_g(self.energy)} MeV)")
        return self.p3 / self.energy

    @property
    def beta(self) -> float:
        return self.p / self.energy if self.energy > 0 else 0.0

    @property
    def gamma(self) -> float:
        """γ = E / m (an error for a massless particle: it has no rest frame)."""
        m = self.mass
        if m == 0:
            raise VidgenError("a massless particle has no rest frame: γ is infinite")
        return self.energy / m

    def __add__(self, other: "FourVector") -> "FourVector":
        return FourVector(self.energy + other.energy, self.px + other.px, self.py + other.py, self.pz + other.pz)

    def __sub__(self, other: "FourVector") -> "FourVector":
        return FourVector(self.energy - other.energy, self.px - other.px, self.py - other.py, self.pz - other.pz)

    def dot(self, other: "FourVector") -> float:
        """The Minkowski product E₁E₂ − p₁·p₂ (MeV²)."""
        return self.energy * other.energy - float(self.p3 @ other.p3)

    def boost(self, beta: Any) -> "FourVector":
        """This vector seen from a frame in which the current frame moves with velocity ``beta``
        (a vector, or a number along x): E' = γ(E + β·p), p' = p + [(γ − 1)(β·p)/β² + γE] β.
        Boosting a rest-frame decay by the parent's velocity gives the lab frame."""
        b = np.array([float(beta), 0.0, 0.0]) if np.isscalar(beta) else np.asarray(beta, dtype=float).reshape(-1)
        if b.size == 2:
            b = np.array([b[0], b[1], 0.0])
        b2 = float(b @ b)
        if b2 == 0:
            return self
        g = gamma_of(math.sqrt(b2))
        bp = float(b @ self.p3)
        e = g * (self.energy + bp)
        p = self.p3 + ((g - 1) * bp / b2 + g * self.energy) * b
        return FourVector(e, float(p[0]), float(p[1]), float(p[2]))

    def text(self, digits: int = 4) -> str:
        """``(E, p) = (109.8 MeV, 29.79 MeV/c at 60°)``."""
        return f"(E, p) = ({value_text(self.energy, 'energy', digits)}, {value_text(self.p, 'momentum', digits)} at {self.angle:.0f}°)"


def _g(x: float) -> str:
    return decimal_text(x, 4).plain if x else "0"


def total(vectors: Any) -> FourVector:
    """The sum of four-vectors."""
    out = FourVector(0.0)
    for v in vectors:
        out = out + v
    return out


def invariant_mass(vectors: Any) -> float:
    """m = √((ΣE)² − |Σp|²) of a system (MeV/c²): the same in every frame."""
    vs = list(vectors)
    if not vs:
        raise VidgenError("the invariant mass needs at least one particle")
    return total(vs).mass


def rest_frame_beta(vectors: Any) -> np.ndarray:
    """The velocity of a system's rest frame (centre of momentum), β = Σp / ΣE; an error when
    the system is massless (photons all moving one way have no rest frame)."""
    t = total(vectors)
    if t.mass == 0:
        raise VidgenError("the system is massless (its particles all move one way at the speed of light): it has no rest frame")
    return t.beta_vector


def to_rest_frame(vectors: Any) -> list[FourVector]:
    """The vectors in the system's rest frame (Σp = 0 there)."""
    vs = list(vectors)
    b = rest_frame_beta(vs)
    return [v.boost(-b) for v in vs]


# ----- boosts -------------------------------------------------------------------------------------


def gamma_of(beta: float) -> float:
    """γ = 1/√(1 − β²); β must be in [0, 1)."""
    if not math.isfinite(beta) or beta < 0:
        raise VidgenError(f"β = v/c must be between 0 and 1 (got {beta:g})")
    if beta >= 1:
        raise VidgenError(f"β = {beta:g} is not below 1: nothing massive moves at or faster than light (superluminal)")
    return 1.0 / math.sqrt(1.0 - beta * beta)


@dataclass(frozen=True)
class Boost:
    """A particle's motion: β, γ and βγ = p/m."""

    beta: float
    gamma: float

    @property
    def beta_gamma(self) -> float:
        return self.beta * self.gamma

    @classmethod
    def from_beta(cls, beta: float) -> "Boost":
        return cls(beta, gamma_of(beta))

    @classmethod
    def from_gamma(cls, gamma: float) -> "Boost":
        if not math.isfinite(gamma) or gamma < 1:
            raise VidgenError(f"γ must be at least 1 (got {gamma:g}): γ = 1 at rest, larger when moving")
        return cls(math.sqrt(1.0 - 1.0 / gamma**2), gamma)

    @classmethod
    def from_momentum(cls, momentum: float, mass: float) -> "Boost":
        """βγ = p/m, γ = E/m."""
        _massive(mass, "a momentum")
        if momentum < 0:
            raise VidgenError(f"a momentum's size cannot be negative (got {momentum:g} MeV/c)")
        e = math.hypot(mass, momentum)
        return cls(momentum / e, e / mass)

    @classmethod
    def from_energy(cls, energy: float, mass: float) -> "Boost":
        """γ = E/m; E must be at least m."""
        _massive(mass, "an energy")
        if energy < mass * (1 - 1e-12):
            raise VidgenError(f"the energy {value_text(energy)} is below the mass {value_text(mass, 'mass')}: E ≥ mc² always "
                              "(did you mean the kinetic energy?)")
        energy = max(energy, mass)
        return cls(math.sqrt(1.0 - (mass / energy) ** 2), energy / mass)

    @classmethod
    def from_kinetic(cls, kinetic: float, mass: float) -> "Boost":
        """E = T + m."""
        if kinetic < 0:
            raise VidgenError(f"a kinetic energy cannot be negative (got {kinetic:g} MeV)")
        return cls.from_energy(kinetic + mass, mass)


def _massive(mass: float, what: str) -> None:
    if mass <= 0:
        raise VidgenError(f"a massless particle always moves at c: {what} gives it no β or γ (γ is infinite)")


def motion(mass: float, *, momentum: float | None = None, energy: float | None = None, kinetic: float | None = None,
           beta: float | None = None, gamma: float | None = None) -> Boost:
    """The :class:`Boost` from exactly one of momentum (MeV/c), energy, kinetic energy (MeV), β
    or γ."""
    given = {k: v for k, v in (("momentum", momentum), ("energy", energy), ("kinetic", kinetic), ("beta", beta), ("gamma", gamma)) if v is not None}
    if len(given) != 1:
        raise VidgenError("give exactly one of momentum, energy, kinetic, beta or gamma" + (f" (got {', '.join(given)})" if given else ""))
    (key, value), = given.items()
    if key == "beta":
        return Boost.from_beta(value)
    if key == "gamma":
        return Boost.from_gamma(value)
    return {"momentum": Boost.from_momentum, "energy": Boost.from_energy, "kinetic": Boost.from_kinetic}[key](value, mass)


# ----- two-body decays ---------------------------------------------------------------------------


def kallen(x: float, y: float, z: float) -> float:
    """The Källén (triangle) function λ(x, y, z) = x² + y² + z² − 2xy − 2yz − 2zx."""
    return x * x + y * y + z * z - 2 * x * y - 2 * y * z - 2 * z * x


def two_body_momentum(parent: float, m1: float, m2: float) -> float:
    """p* = √λ(M², m₁², m₂²) / 2M: each product's momentum in the parent's rest frame (MeV/c).
    Below threshold (M < m₁ + m₂) an error."""
    if parent <= 0:
        raise VidgenError(f"a decaying particle must have mass (got M = {parent:g} MeV/c²)")
    if parent < m1 + m2 - 1e-9:
        raise VidgenError(f"below threshold: M = {value_text(parent, 'mass')} is less than m₁ + m₂ = {value_text(m1 + m2, 'mass')}; "
                          "the decay cannot happen")
    lam = kallen(parent**2, m1**2, m2**2)
    return math.sqrt(max(lam, 0.0)) / (2 * parent)


@dataclass(frozen=True)
class TwoBodyDecay:
    """A two-body decay M → 1 + 2 in the parent's rest frame: p*, the energies
    E₁ = (M² + m₁² − m₂²) / 2M and E₂, and the four-vectors for an emission angle."""

    process: Process
    parent: Particle
    first: Particle
    second: Particle
    p_star: float

    @property
    def masses(self) -> tuple[float, float, float]:
        return self.parent.mass_mev, self.first.mass_mev, self.second.mass_mev

    @property
    def energies(self) -> tuple[float, float]:
        m, m1, m2 = self.masses
        return (m * m + m1 * m1 - m2 * m2) / (2 * m), (m * m + m2 * m2 - m1 * m1) / (2 * m)

    @property
    def q_value(self) -> float:
        """Q = M − m₁ − m₂: the kinetic energy shared by the products (MeV)."""
        m, m1, m2 = self.masses
        return m - m1 - m2

    def rest_vectors(self, angle: float = 0.0) -> tuple[FourVector, FourVector]:
        """The products in the rest frame, the first at ``angle`` degrees from the x axis, the
        second opposite (back to back)."""
        _, m1, m2 = self.masses
        return FourVector.from_mass(m1, self.p_star, angle), FourVector.from_mass(m2, self.p_star, angle + 180.0)

    def lab_vectors(self, boost: Boost, angle: float = 0.0) -> tuple[FourVector, FourVector]:
        """The products in the lab, the parent moving along +x with ``boost``; ``angle`` is the
        emission angle in the rest frame."""
        a, b = self.rest_vectors(angle)
        return a.boost(boost.beta), b.boost(boost.beta)

    def parent_vector(self, boost: Boost | None = None) -> FourVector:
        m = self.parent.mass_mev
        if boost is None:
            return FourVector(m)
        return FourVector(boost.gamma * m, boost.beta_gamma * m)

    def opening_angle(self, boost: Boost, angle: float = 90.0) -> float:
        """The lab angle between the products (degrees) for the rest-frame emission ``angle``."""
        _, m1, m2 = self.masses
        return _lab_opening(m1, m2, self.p_star, boost.beta, angle)

    def min_opening_angle(self, boost: Boost, samples: int = 721) -> float:
        """The smallest lab opening angle over all emission angles (degrees); for massless
        products sin(θ_min / 2) = 1/γ."""
        _, m1, m2 = self.masses
        return _min_opening(m1, m2, self.p_star, boost.beta, samples)


def _lab_opening(m1: float, m2: float, p_star: float, beta: float, angle: float) -> float:
    a, b = FourVector.from_mass(m1, p_star, angle), FourVector.from_mass(m2, p_star, angle + 180.0)
    return opening_angle(a.boost(beta), b.boost(beta))


def _min_opening(m1: float, m2: float, p_star: float, beta: float, samples: int = 721) -> float:
    return min(_lab_opening(m1, m2, p_star, beta, float(a)) for a in np.linspace(0.0, 180.0, samples))


def opening_angle(a: FourVector, b: FourVector) -> float:
    """The angle between two momenta (degrees)."""
    pa, pb = a.p, b.p
    if pa == 0 or pb == 0:
        raise VidgenError("a particle at rest has no direction: no opening angle")
    c = float(a.p3 @ b.p3) / (pa * pb)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def two_body(decay: str | Process) -> TwoBodyDecay:
    """``"pi+ -> mu+ nu_mu"`` as a :class:`TwoBodyDecay` (masses from PDG 2024). The decay must
    be one particle into two on-shell particles, allowed by the conservation checker, and above
    threshold."""
    proc = as_process(decay)
    where = f"decay '{proc}'"
    if len(proc.initial) != 1 or len(proc.final) != 2:
        raise VidgenError(f"{where}: a two-body decay is one particle into two (got {len(proc.initial)} → {len(proc.final)})")
    if any(leg.off_shell for leg in proc.legs):
        raise VidgenError(f"{where}: an off-shell (*) particle has no fixed mass; write the decay with real particles")
    parent = proc.initial[0].particle
    first, second = (leg.particle for leg in proc.final)
    if parent.mass_mev < first.mass_mev + second.mass_mev:
        raise VidgenError(f"{where}: below threshold: M = {value_text(parent.mass_mev, 'mass')} is less than "
                          f"{first.symbol} + {second.symbol} = {value_text(first.mass_mev + second.mass_mev, 'mass')}")
    verdict = check(proc)
    if not verdict.allowed:
        raise VidgenError(f"{where}: {verdict.summary()}")
    return TwoBodyDecay(proc, parent, first, second, two_body_momentum(*(p.mass_mev for p in (parent, first, second))))


# ----- momentum pictures --------------------------------------------------------------------------


@dataclass(frozen=True)
class MomentumPicture:
    """The particles of a momentum-vector picture: their four-vectors in the system's rest frame
    (``rest``; Σp = 0), the direction of the boost to the lab and its rapidity ``eta_lab`` (β =
    tanh η). ``vectors(eta)`` gives the picture in any frame along that boost: η = 0 the rest
    frame, ``eta_lab`` the lab. ``decay`` is set for a two-body decay (the parent moving along +x
    in the lab), else the particles were given in the lab."""

    particles: tuple[Particle, ...]
    rest: tuple[FourVector, ...]
    direction: tuple[float, float]
    eta_lab: float
    decay: TwoBodyDecay | None = None
    angle: float = 0.0

    def beta_vector(self, eta: float) -> np.ndarray:
        return math.tanh(eta) * np.array([self.direction[0], self.direction[1], 0.0])

    def vectors(self, eta: float) -> list[FourVector]:
        """The particles seen from the frame at rapidity ``eta`` along the boost."""
        b = self.beta_vector(eta)
        return [v.boost(b) for v in self.rest]

    @property
    def lab(self) -> list[FourVector]:
        return self.vectors(self.eta_lab)

    @property
    def mass(self) -> float:
        """The invariant mass of the system (the parent's mass for a decay)."""
        return invariant_mass(self.rest)

    def motion(self, eta: float) -> Boost:
        """β and γ of the frame at ``eta`` relative to the rest frame."""
        return Boost(math.tanh(abs(eta)), math.cosh(eta))

    @staticmethod
    def eta_of(beta: float) -> float:
        gamma_of(abs(beta))   # checks 0 ≤ β < 1
        return math.atanh(beta)


def decay_picture(decay: str | TwoBodyDecay, angle: float = 60.0, lab: Boost | None = None) -> MomentumPicture:
    """A two-body decay: the products back to back in the rest frame, the first at ``angle``
    degrees from the flight direction (+x), and the lab where the parent moves with ``lab``."""
    d = decay if isinstance(decay, TwoBodyDecay) else two_body(decay)
    eta = math.atanh(lab.beta) if lab is not None else 0.0
    return MomentumPicture((d.first, d.second), d.rest_vectors(angle), (1.0, 0.0), eta, d, angle)


def system_picture(items: Any) -> MomentumPicture:
    """Particles given in the lab, ``[(particle, momentum MeV/c, angle degrees), ...]``: their
    rest frame (centre of momentum) is found from Σp / ΣE; a massless system has none."""
    parts, lab = [], []
    for name, momentum, angle in items:
        p = name if isinstance(name, Particle) else particle(name)
        if p.mass_limit_mev is None and p.mass_mev == 0 and momentum == 0:
            raise VidgenError(f"a {p.name} always moves at c: give it a momentum")
        parts.append(p)
        lab.append(FourVector.from_mass(p.mass_mev, momentum, angle))
    if not parts:
        raise VidgenError("a momentum picture needs at least one particle")
    t = total(lab)
    if t.mass == 0:
        raise VidgenError("the particles are massless and all move one way: the system has no rest frame (its invariant mass is 0)")
    b = t.beta_vector
    speed = float(np.linalg.norm(b))
    direction = (float(b[0] / speed), float(b[1] / speed)) if speed > 1e-12 else (1.0, 0.0)
    rest = tuple(v.boost(-b) for v in lab) if speed > 1e-12 else tuple(lab)
    return MomentumPicture(tuple(parts), rest, direction, math.atanh(min(speed, 1 - 1e-15)))


# ----- thresholds ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """The least energy for a reaction a + b → products: √s_min = Σ m(products); on a fixed
    target (b at rest) the beam energy E = (s − m_a² − m_b²) / 2m_b and its kinetic part; at a
    collider (head on, Σp = 0) the energies of the two beams √s-shared."""

    process: Process
    threshold: Threshold

    @property
    def sqrt_s(self) -> float:
        return self.threshold.sqrt_s_mev

    @property
    def fixed_target(self) -> float | None:
        return self.threshold.beam_mev

    @property
    def fixed_target_kinetic(self) -> float | None:
        return self.threshold.beam_kinetic_mev

    @property
    def collider(self) -> tuple[float, float]:
        """The two beams' energies at threshold in the centre-of-momentum frame:
        E_a = (s + m_a² − m_b²) / 2√s (equal masses: √s / 2 each)."""
        m_a, m_b = (leg.particle.mass_mev for leg in self.process.initial)
        s = self.sqrt_s**2
        return (s + m_a**2 - m_b**2) / (2 * self.sqrt_s), (s + m_b**2 - m_a**2) / (2 * self.sqrt_s)

    @property
    def collider_kinetic(self) -> tuple[float, float]:
        m_a, m_b = (leg.particle.mass_mev for leg in self.process.initial)
        e_a, e_b = self.collider
        return e_a - m_a, e_b - m_b

    @property
    def ratio(self) -> float | None:
        """Fixed-target over collider total beam energy (how much a fixed target wastes)."""
        if self.fixed_target is None:
            return None
        return self.fixed_target / sum(self.collider)


def threshold(reaction: str | Process) -> Thresholds:
    """The thresholds of a two-particle reaction (``"p p -> p p p anti-p"``): it must conserve
    what the checker checks; endothermic or not, √s_min = max(Σ m before, Σ m after)."""
    proc = as_process(reaction)
    if len(proc.initial) != 2:
        raise VidgenError(f"reaction '{proc}': a threshold is for two particles colliding (got {len(proc.initial)} before the arrow)")
    verdict = check(proc)
    if not verdict.allowed:
        raise VidgenError(f"reaction '{proc}': {verdict.summary()}")
    return Thresholds(proc, verdict.threshold)


def fixed_target_energy(products_mass: float, beam_mass: float, target_mass: float) -> float:
    """E_beam = (M² − m_a² − m_b²) / 2m_b for products of total mass M (MeV)."""
    if target_mass <= 0:
        raise VidgenError("a fixed target must have mass")
    return (products_mass**2 - beam_mass**2 - target_mass**2) / (2 * target_mass)


# ----- time dilation and decay length -------------------------------------------------------------


@dataclass(frozen=True)
class DecayLength:
    """A moving particle's mean decay length L = βγcτ and its lifetime in the lab γτ."""

    particle: Particle
    motion: Boost

    @property
    def tau(self) -> float:
        return float(self.particle.lifetime or 0.0)

    @property
    def c_tau(self) -> float:
        """cτ in metres."""
        return float(self.particle.c_tau_m or 0.0)

    @property
    def lab_lifetime(self) -> float:
        """γτ in seconds (time dilation)."""
        return self.motion.gamma * self.tau

    @property
    def length(self) -> float:
        """L = βγcτ in metres."""
        return self.motion.beta_gamma * self.c_tau

    def survival(self, distance: float) -> float:
        """The fraction still undecayed after ``distance`` metres, e^(−d/L)."""
        return math.exp(-distance / self.length) if self.length > 0 else 0.0

    def text(self) -> str:
        """``βγ = 37.85, cτ = 658.6 m → L = βγcτ = 24.93 km``."""
        return f"βγ = {_g(self.motion.beta_gamma)}, cτ = {length_text(self.c_tau)} → L = βγcτ = {length_text(self.length)}"


def decay_length(name: str | Particle, **given: float | None) -> DecayLength:
    """L = βγcτ for a particle by name with exactly one of ``momentum`` (MeV/c), ``energy``,
    ``kinetic`` (MeV), ``beta`` or ``gamma``; an error for a stable or massless particle."""
    p = name if isinstance(name, Particle) else particle(name)
    if p.stable or p.lifetime is None:
        raise VidgenError(f"{p.name} ({p.symbol}) {'is stable' if p.stable else 'has no lifetime in the table'}: no decay length")
    return DecayLength(p, motion(p.mass_mev, **given))


#: Length units for display, largest first (metres).
LENGTH_UNITS = (("km", 1e3), ("m", 1.0), ("cm", 1e-2), ("mm", 1e-3), ("µm", 1e-6), ("nm", 1e-9), ("fm", 1e-15))


def length_text(metres: float, digits: int = 4) -> str:
    """``24.93 km``, ``491.1 µm``, ``25.35 nm``."""
    if metres == 0:
        return "0"
    unit, scale = next(((u, s) for u, s in LENGTH_UNITS if abs(metres) >= s), LENGTH_UNITS[-1])
    if abs(metres) < 1e-15:
        return f"{decimal_text(metres, min(digits, 3), 'sci').plain} m"
    return f"{decimal_text(metres / scale, digits, 'plain').plain} {unit}"


# ----- plot model ---------------------------------------------------------------------------------


@register_model("two_body_opening",
                labels={"p": "parent momentum", "gamma": "γ", "theta_min": "smallest opening angle θ", "theta_90": "opening angle (90° in the rest frame)"},
                units={"p": "GeV/c", "theta_min": "deg", "theta_90": "deg"})
def _opening_model(params: dict[str, float], seed: int) -> dict[str, Any]:
    """The plot model ``two_body_opening`` (``kind: function``): a two-body decay of a parent of
    mass ``M`` (GeV/c²) into ``m1`` and ``m2`` (default 0) seen in the lab for parent momenta
    ``p_min`` … ``p_max`` (GeV/c; default 0.1 M … 20 M): columns ``p`` (GeV/c), ``gamma``,
    ``theta_min`` (the smallest opening angle, degrees) and ``theta_90`` (products emitted at
    90° in the rest frame, degrees)."""
    allowed = {"M", "m1", "m2", "p_min", "p_max", "samples"}
    extra = sorted(set(params) - allowed)
    if extra:
        raise VidgenError(f"two_body_opening does not take {', '.join(extra)} (it takes {', '.join(sorted(allowed))})")
    if "M" not in params:
        raise VidgenError("two_body_opening needs M, the parent's mass in GeV/c² (e.g. M: 0.1349768 for π⁰ → γγ)")
    m, m1, m2 = (float(params.get(k, 0.0)) * 1e3 for k in ("M", "m1", "m2"))
    p_star = two_body_momentum(m, m1, m2)
    lo = float(params.get("p_min", 0.1 * m / 1e3)) * 1e3
    hi = float(params.get("p_max", 20 * m / 1e3)) * 1e3
    if not 0 < lo < hi:
        raise VidgenError(f"two_body_opening: need 0 < p_min < p_max (got {lo / 1e3:g}, {hi / 1e3:g} GeV/c)")
    n = int(params.get("samples", 120))
    ps = np.geomspace(lo, hi, max(10, min(n, 1000)))
    theta_min, theta_90, gammas = [], [], []
    for p in ps:
        b = Boost.from_momentum(float(p), m)
        gammas.append(b.gamma)
        theta_min.append(_min_opening(m1, m2, p_star, b.beta, 361))
        theta_90.append(_lab_opening(m1, m2, p_star, b.beta, 90.0))
    return {"p": ps / 1e3, "gamma": gammas, "theta_min": theta_min, "theta_90": theta_90}


__all__ = [
    "KINDS",
    "LENGTH_UNITS",
    "PDG_QUANTITIES",
    "SI_UNITS",
    "PdgValue",
    "pdg_value",
    "Boost",
    "DecayLength",
    "FourVector",
    "MomentumPicture",
    "decay_picture",
    "system_picture",
    "Thresholds",
    "TwoBodyDecay",
    "decay_length",
    "fixed_target_energy",
    "from_si",
    "gamma_of",
    "invariant_mass",
    "kallen",
    "length_text",
    "mass_of",
    "motion",
    "natural_value",
    "opening_angle",
    "rest_frame_beta",
    "si_text",
    "threshold",
    "to_rest_frame",
    "to_si",
    "total",
    "two_body",
    "two_body_momentum",
    "value_text",
]
