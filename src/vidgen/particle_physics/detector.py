"""A schematic cylindrical detector and simulated events for event displays (Phase Y, Step 240;
DESIGN §99.9). No manim.

**The detector is schematic**: a generic general-purpose layout (sizes of our own choosing, not
any experiment's): a pixel and a strip tracker inside a solenoid, an electromagnetic (ECAL) and a
hadronic (HCAL) calorimeter outside it, then iron (the return yoke) interleaved with three muon
stations; barrels and endcaps. Lengths in metres, momenta and energies in GeV (c = 1), angles in
radians, the field in tesla along +z (the beam axis).

**Particles leave their signatures** (:data:`SIGNATURES`): an electron a track and an ECAL shower;
a photon an ECAL shower and no track; a muon a track through everything and hits in the muon
chambers; a charged hadron a track and an HCAL shower (with some energy in the ECAL); a neutral
hadron an HCAL shower only; a neutrino nothing — it shows as missing transverse momentum, computed
from the visible particles (:meth:`Event.missing_pt`).

**Tracks** are stepped through the field (:func:`trajectory`): inside the solenoid a charge q
turns with radius R [m] = p_T [GeV/c] / (0.3 |q| B [T]), clockwise seen from +z for q > 0 and
B > 0 (the force q v × B); straight outside it; in the iron of the barrel the return field
(opposite, ``return_field`` tesla, schematic) bends a muon back. A track whose 2R is smaller than
the calorimeter's radius curls up inside the tracker (drawn for one turn).

**Events** are simulated (:func:`generate`) from a seed with :class:`~vidgen.plotcore.SplitMix64`:
presets (``z_to_mumu``, ``h_to_gammagamma``, ``h_to_4l``, ``w_to_enu``, ``dijet``) decay a boson
(mass from PDG 2024, a seeded Breit–Wigner draw with its width truncated to M ± Γ so a showcase
event sits on the peak) isotropically in its rest frame and
boost the products to the lab (:mod:`.kinematics`); the boson's transverse momentum is balanced
by a recoil (a jet, or two soft pions), so the missing p_T is the neutrinos'. Jets are cones of
charged hadrons, photons (from π⁰) and neutral hadrons. Energy deposits are shared between the
calorimeters by fixed schematic fractions (:data:`CALO_SHARE`), binned in towers (:func:`towers`)
whose length is linear or logarithmic in the energy (:func:`tower_fraction`). No resolution
smearing: the missing p_T of a simulated event is exact."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.plotcore.models import SplitMix64

from .data import PARTICLES, Particle
from .kinematics import FourVector, two_body_momentum
from .names import particle as find_particle

# ----- geometry -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Layer:
    """One part of the detector: a barrel shell (``r0`` … ``r1`` for |z| ≤ ``z_half``) and, if it
    has one, two endcap discs (|z| from ``z0`` to ``z1``, radius ``rmin`` … ``r1``)."""

    key: str      # tracker, solenoid, ecal, hcal, iron, muon
    name: str
    r0: float
    r1: float
    z_half: float
    endcap: tuple[float, float, float] | None = None   # (z0, z1, rmin)

    def in_barrel(self, r: float, z: float) -> bool:
        return self.r0 <= r <= self.r1 and abs(z) <= self.z_half

    def in_endcap(self, r: float, z: float) -> bool:
        if self.endcap is None:
            return False
        z0, z1, rmin = self.endcap
        return z0 <= abs(z) <= z1 and rmin <= r <= self.r1

    def contains(self, r: float, z: float) -> bool:
        return self.in_barrel(r, z) or self.in_endcap(r, z)


#: Tracker layers: (radius, half-length) — three pixel layers, six strip layers.
TRACKER_LAYERS: tuple[tuple[float, float], ...] = (
    (0.05, 0.45), (0.09, 0.45), (0.13, 0.45),
    (0.30, 2.5), (0.45, 2.5), (0.60, 2.5), (0.75, 2.5), (0.90, 2.5), (1.05, 2.5))
TRACKER = Layer("tracker", "tracker (pixels, strips)", 0.0, 1.10, 2.6)
SOLENOID = Layer("solenoid", "solenoid", 1.18, 1.30, 2.8)
ECAL = Layer("ecal", "ECAL", 1.40, 1.80, 3.0, (3.05, 3.45, 0.30))
HCAL = Layer("hcal", "HCAL", 1.90, 2.90, 3.55, (3.55, 4.55, 0.40))
#: Iron (the return yoke) and the muon stations, barrel and endcap.
IRON = (Layer("iron", "iron yoke", 3.30, 3.65, 4.6, (4.90, 5.20, 0.60)), Layer("iron", "iron yoke", 4.00, 4.35, 4.6, (5.50, 5.80, 0.60)))
MUON = (Layer("muon", "muon chambers", 3.05, 3.20, 4.6, (4.70, 4.82, 0.60)), Layer("muon", "muon chambers", 3.75, 3.90, 4.6, (5.30, 5.42, 0.60)),
        Layer("muon", "muon chambers", 4.45, 4.60, 4.6, (5.90, 6.02, 0.60)))
#: The field volume (inside the coil) and the detector's outer envelope.
FIELD_R, FIELD_Z = SOLENOID.r0, SOLENOID.z_half
OUTER_R, OUTER_Z = 4.60, 6.02
#: Pseudorapidity reach: tracks (the tracker), the calorimeters and muon chambers.
ETA_TRACKER = 2.5
ETA_MAX = 3.0


@dataclass(frozen=True)
class Detector:
    """The schematic detector with its solenoid field ``field`` (T, along +z) and the return
    field in the barrel iron (``return_field`` T, opposite; schematic)."""

    field: float = 2.0
    return_field: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.field) or self.field <= 0:
            raise VidgenError(f"field: {self.field:g} T — the solenoid field must be positive (2 T is typical; tracks need it to bend)")
        if self.return_field is not None and (not math.isfinite(self.return_field) or self.return_field < 0):
            raise VidgenError(f"return_field: {self.return_field:g} T — give its size (≥ 0); it points opposite to the solenoid's")

    @property
    def yoke_field(self) -> float:
        """The return field's size in the barrel iron (default half the solenoid's, schematic)."""
        return self.field / 2 if self.return_field is None else self.return_field

    @property
    def layers(self) -> tuple[Layer, ...]:
        return (TRACKER, SOLENOID, ECAL, HCAL, *IRON, *MUON)

    def bz(self, r: float, z: float) -> float:
        """The field along z at (r, z): B inside the coil, minus the return field in the barrel
        iron, 0 elsewhere (schematic)."""
        if r < FIELD_R and abs(z) < FIELD_Z:
            return self.field
        if any(layer.in_barrel(r, z) for layer in IRON):
            return -self.yoke_field
        return 0.0


def bending_radius(pt: float, field: float, charge: float = 1.0) -> float:
    """R [m] = p_T [GeV/c] / (0.3 |q| B [T]) (exactly 0.299792458: c in units of 10⁹ m/s)."""
    if pt <= 0 or field <= 0 or charge == 0:
        return math.inf
    return pt / (0.299792458 * abs(charge) * field)


# ----- particles and their signatures -------------------------------------------------------------

#: What each kind of particle leaves: the parts it must show (and may show).
SIGNATURES: dict[str, tuple[frozenset[str], frozenset[str], str]] = {
    "electron": (frozenset({"track", "ecal"}), frozenset(), "track + ECAL shower"),
    "photon": (frozenset({"ecal"}), frozenset(), "ECAL shower, no track"),
    "muon": (frozenset({"track", "muon"}), frozenset(), "track through everything + muon chambers"),
    "charged_hadron": (frozenset({"track", "hcal"}), frozenset({"ecal"}), "track + HCAL shower (some ECAL)"),
    "neutral_hadron": (frozenset({"hcal"}), frozenset({"ecal"}), "HCAL shower, no track"),
    "neutrino": (frozenset({"missing"}), frozenset(), "nothing: missing transverse momentum"),
}
#: The parts a signature names: a track, ECAL and HCAL showers, muon-chamber hits, missing p_T.
SIGNATURE_PARTS = ("track", "ecal", "hcal", "muon", "missing")
#: Share of a particle's energy in (ECAL, HCAL) — schematic.
CALO_SHARE = {"electron": (1.0, 0.0), "photon": (1.0, 0.0), "charged_hadron": (0.3, 0.7), "neutral_hadron": (0.0, 1.0)}
#: A particle reaches the detector if stable or cτ at least this (m).
REACH_CTAU = 1.0


def signature(p: Particle | str) -> str:
    """The kind of signature ``p`` leaves (a key of :data:`SIGNATURES`), or a ``VidgenError``
    saying why it leaves none of its own (it decays first, or it is a quark or a gluon)."""
    p = find_particle(p) if isinstance(p, str) else p
    key = p.key
    if key in ("e-", "e+"):
        return "electron"
    if key == "gamma":
        return "photon"
    if key in ("mu-", "mu+"):
        return "muon"
    if p.family == "lepton" and p.charge == 0:
        return "neutrino"
    if p.family in ("quark", "gauge boson") and key in ("g", "u", "d", "s", "c", "b", "anti-u", "anti-d", "anti-s", "anti-c", "anti-b"):
        raise VidgenError(f"{p.name} ({key}): quarks and gluons are never seen alone; they make a jet — {{particle: jet, pt: 80, eta: 0.3, phi: 40}}")
    if key in ("Z", "W+", "W-", "H", "t", "anti-t"):
        raise VidgenError(f"{p.name} ({key}) decays at the collision point; give its decay products or use a preset "
                          f"(z_to_mumu, h_to_gammagamma, h_to_4l, w_to_enu, dijet)")
    reaches = p.stable or (p.c_tau_m is not None and p.c_tau_m >= REACH_CTAU)
    if not reaches:
        ctau = p.c_tau_m
        where = f"cτ = {_length(ctau)}" if ctau is not None else "it decays at once"
        hint = " (π⁰ → γγ: give two photons)" if key == "pi0" else (" (τ: give its products, e.g. pi- and nu_tau)" if key.startswith("tau") else "; give its decay products")
        raise VidgenError(f"{p.name} ({key}) decays before it reaches the detector ({where}){hint}")
    if p.family in ("meson", "baryon"):
        return "charged_hadron" if p.charge != 0 else "neutral_hadron"
    raise VidgenError(f"{p.name} ({key}) has no signature in this detector")


def _length(metres: float) -> str:
    for unit, scale in (("m", 1.0), ("cm", 1e-2), ("mm", 1e-3), ("µm", 1e-6)):
        if metres >= scale:
            return f"{metres / scale:.3g} {unit}"
    return f"{metres:.2g} m"


def signature_text(kind: str) -> str:
    """``track + ECAL shower`` for ``electron``…"""
    return SIGNATURES[kind][2]


def signature_problem(p: Particle | str, parts: Sequence[str]) -> str | None:
    """Whether ``parts`` (track, ecal, hcal, muon, missing) is what ``p`` leaves: ``None``, or
    the reason it is not ("a photon leaves no track: ECAL shower, no track")."""
    p = find_particle(p) if isinstance(p, str) else p
    kind = signature(p)
    unknown = [x for x in parts if x not in SIGNATURE_PARTS]
    if unknown:
        raise VidgenError(f"leaves: '{unknown[0]}' is not a signature part ({', '.join(SIGNATURE_PARTS)})")
    must, may, text = SIGNATURES[kind]
    claimed = set(parts)
    extra = sorted(claimed - must - may, key=SIGNATURE_PARTS.index)
    if extra:
        why = {"track": "it is neutral" if p.charge == 0 else "", "missing": "it is seen"}.get(extra[0], "")
        return f"{_a(p.name)} leaves no {_part(extra[0])}{f' ({why})' if why else ''}: {text}"
    lacking = sorted(must - claimed, key=SIGNATURE_PARTS.index)
    if lacking == ["missing"]:
        return f"{_a(p.name)} leaves nothing in the detector: it shows as missing p_T"
    if lacking:
        return f"{_a(p.name)} also leaves {_a(_part(lacking[0]))}: {text}"
    return None


def _part(key: str) -> str:
    return {"track": "track", "ecal": "ECAL shower", "hcal": "HCAL shower", "muon": "muon-chamber hits", "missing": "missing p_T"}[key]


def _a(text: str) -> str:
    return ("an " if text[:1].lower() in "aeiou" or text.startswith(("ECAL", "HCAL")) else "a ") + text


# ----- events -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EventParticle:
    """A particle of an event leaving the collision point: ``pt`` (GeV/c), pseudorapidity
    ``eta``, azimuth ``phi`` (radians, from +x), and the ``group`` it belongs to (``jet1``,
    ``soft``, ``recoil`` or "" for a decay product or a listed particle)."""

    particle: Particle
    pt: float
    eta: float
    phi: float
    group: str = ""

    @property
    def kind(self) -> str:
        return signature(self.particle)

    @property
    def charge(self) -> int:
        return int(self.particle.charge)

    @property
    def visible(self) -> bool:
        return self.kind != "neutrino"

    @property
    def px(self) -> float:
        return self.pt * math.cos(self.phi)

    @property
    def py(self) -> float:
        return self.pt * math.sin(self.phi)

    @property
    def pz(self) -> float:
        return self.pt * math.sinh(self.eta)

    @property
    def p(self) -> float:
        return self.pt * math.cosh(self.eta)

    @property
    def mass(self) -> float:
        """GeV/c²."""
        return self.particle.mass_mev / 1000.0

    @property
    def energy(self) -> float:
        return math.hypot(self.p, self.mass)

    @property
    def theta(self) -> float:
        """The polar angle from +z (radians): 2 atan(e^−η)."""
        return 2 * math.atan(math.exp(-self.eta))

    def four_vector(self) -> FourVector:
        """In MeV (the units of :mod:`.kinematics`)."""
        return FourVector(self.energy * 1e3, self.px * 1e3, self.py * 1e3, self.pz * 1e3)


@dataclass(frozen=True)
class Jet:
    """A jet: its constituents (indices into the event's particles) and their summed momentum."""

    name: str
    members: tuple[int, ...]
    pt: float
    eta: float
    phi: float


@dataclass(frozen=True)
class Event:
    """A simulated event: its particles, jets, the decay products whose invariant mass is worth
    showing (``products``, with the ``parent`` they came from), its ``seed`` and ``name``."""

    particles: tuple[EventParticle, ...]
    jets: tuple[Jet, ...] = ()
    products: tuple[int, ...] = ()
    parent: str = ""
    name: str = "event"
    seed: int = 1

    def missing_pt(self) -> tuple[float, float]:
        """The missing transverse momentum (px, py) in GeV/c: minus the sum of the visible
        particles' transverse momenta."""
        px = -sum(q.px for q in self.particles if q.visible)
        py = -sum(q.py for q in self.particles if q.visible)
        return px, py

    @property
    def met(self) -> float:
        return math.hypot(*self.missing_pt())

    def products_mass(self) -> float | None:
        """The invariant mass (GeV/c²) of the decay products, when the event has some."""
        if len(self.products) < 2:
            return None
        e = sum(self.particles[i].energy for i in self.products)
        px = sum(self.particles[i].px for i in self.products)
        py = sum(self.particles[i].py for i in self.products)
        pz = sum(self.particles[i].pz for i in self.products)
        return math.sqrt(max(e * e - px * px - py * py - pz * pz, 0.0))

    def transverse_mass(self) -> float | None:
        """m_T = √(2 p_T^ℓ p_T^miss (1 − cos Δφ)) (GeV/c²) of the one visible decay product and
        the missing p_T (a W → ℓν), else ``None``."""
        if len(self.products) != 1 or self.met <= 0:
            return None
        q = self.particles[self.products[0]]
        mx, my = self.missing_pt()
        dphi = q.phi - math.atan2(my, mx)
        return math.sqrt(max(0.0, 2 * q.pt * self.met * (1 - math.cos(dphi))))

    def objects(self) -> list[tuple[str, Any]]:
        """What a readout lists: the particles outside jets and soft tracks (leptons, photons,
        listed hadrons; not neutrinos) and the jets: (``particle`` | ``jet``, item) — by p_T, or
        for listed particles in their order."""
        firsts = {j.members[0]: j for j in self.jets}
        out: list[tuple[str, Any]] = []
        for i, q in enumerate(self.particles):
            if i in firsts:
                out.append(("jet", firsts[i]))
            elif q.visible and q.group == "":
                out.append(("particle", i))
        if self.name == "custom":
            return out
        return sorted(out, key=lambda o: -(self.particles[o[1]].pt if o[0] == "particle" else o[1].pt))


PRESETS = ("z_to_mumu", "h_to_gammagamma", "h_to_4l", "w_to_enu", "dijet")
#: Soft charged-pion pairs a preset adds by default (low p_T: some curl up in the tracker).
PRESET_SOFT = 4
#: Acceptance a generated lepton or photon must fall in.
LEPTON_ETA = 2.4
LEPTON_PT = 10.0
NEUTRINO_PT = 20.0


#: A display event's boson mass is a Breit–Wigner draw truncated to M ± this many widths, so a
#: showcase event lands on the peak (a histogram of many events uses ``mass_spectrum`` instead).
DISPLAY_WIDTHS = 1.0


def _mass(key: str, rng: SplitMix64) -> float:
    """A boson's mass (GeV) drawn from a Breit–Wigner of its PDG mass and width, truncated to
    M ± :data:`DISPLAY_WIDTHS` Γ (inverse CDF of the truncated distribution: one uniform)."""
    p = PARTICLES[key]
    m, gamma = p.mass_mev / 1e3, (p.width_mev or 0.0) / 1e3
    if gamma <= 0:
        return m
    u = 0.5 + (rng.uniform() - 0.5) * (2 / math.pi) * math.atan(2 * DISPLAY_WIDTHS)
    return m + gamma / 2 * math.tan(math.pi * (u - 0.5))


def _direction(rng: SplitMix64) -> np.ndarray:
    """An isotropic unit vector."""
    c = 2 * rng.uniform() - 1
    s = math.sqrt(max(0.0, 1 - c * c))
    f = 2 * math.pi * rng.uniform()
    return np.array([s * math.cos(f), s * math.sin(f), c])


def _from_vector(p: Particle, v: FourVector, group: str = "") -> EventParticle:
    px, py, pz = v.px / 1e3, v.py / 1e3, v.pz / 1e3
    pt = math.hypot(px, py)
    return EventParticle(p, pt, math.asinh(pz / pt) if pt > 0 else math.copysign(10.0, pz), math.atan2(py, px), group)


def _decay(parent: FourVector, m1: float, m2: float, rng: SplitMix64) -> tuple[FourVector, FourVector]:
    """Two-body decay of ``parent`` (MeV) into masses m1, m2 (MeV): isotropic in its rest frame,
    then boosted to the lab."""
    m = parent.mass
    p_star = two_body_momentum(m, m1, m2)
    d = _direction(rng) * p_star
    a = FourVector(math.hypot(p_star, m1), *d)
    b = FourVector(math.hypot(p_star, m2), *(-d))
    beta = parent.beta_vector
    return a.boost(beta), b.boost(beta)


def _boson(mass: float, rng: SplitMix64, mean_pt: float) -> FourVector:
    """A boson of ``mass`` (GeV) with p_T exponential (mean ``mean_pt``, at most 60 GeV),
    rapidity in [−1, 1], any azimuth — in MeV."""
    pt = min(-mean_pt * math.log(1 - rng.uniform()), 60.0)
    y = 2 * rng.uniform() - 1
    phi = 2 * math.pi * rng.uniform()
    mt = math.hypot(mass, pt)
    return FourVector(mt * math.cosh(y) * 1e3, pt * math.cos(phi) * 1e3, pt * math.sin(phi) * 1e3, mt * math.sinh(y) * 1e3)


def _accepted(items: Sequence[EventParticle]) -> bool:
    """Leptons and photons central and hard enough to see; a neutrino hard enough to miss."""
    return all(q.pt >= NEUTRINO_PT if q.kind == "neutrino" else abs(q.eta) <= LEPTON_ETA and q.pt >= LEPTON_PT for q in items)


def _decay_into(parent: FourVector, keys: tuple[str, str], rng: SplitMix64, masses: tuple[float, float] | None = None) -> list[EventParticle]:
    """Decay ``parent`` into the particles ``keys`` until the visible ones fall in the
    acceptance (at most 400 tries: a display event is chosen to be seen)."""
    p1, p2 = PARTICLES[keys[0]], PARTICLES[keys[1]]
    m1, m2 = masses if masses is not None else (p1.mass_mev, p2.mass_mev)
    out: list[EventParticle] = []
    for _ in range(400):
        a, b = _decay(parent, m1, m2, rng)
        out = [_from_vector(p1, a), _from_vector(p2, b)]
        if _accepted(out):
            return out
    return out


def make_jet(pt: float, eta: float, phi: float, rng: SplitMix64, group: str) -> list[EventParticle]:
    """A jet's constituents (5–10 charged pions, photons from π⁰, neutral hadrons) within ΔR ≲
    0.25 of (eta, phi), their transverse momenta summing exactly to (pt, phi)."""
    n = 5 + int(rng.uniform() * 6)
    weights = [rng.uniform() ** 2 + 0.02 for _ in range(n)]
    total = sum(weights)
    out = []
    for k, w in enumerate(sorted(weights, reverse=True)):
        u = rng.uniform()
        if u < 0.6:
            key = "pi+" if rng.uniform() < 0.5 else "pi-"
        elif u < 0.85:
            key = "gamma"
        else:
            key = "K0_L" if rng.uniform() < 0.5 else "n"
        r, a = 0.25 * math.sqrt(rng.uniform()), 2 * math.pi * rng.uniform()
        out.append(EventParticle(PARTICLES[key], pt * w / total, eta + r * math.cos(a), phi + r * math.sin(a), group))
    return _balance(out, pt * math.cos(phi), pt * math.sin(phi))


def _balance(items: list[EventParticle], tx: float, ty: float) -> list[EventParticle]:
    """Rotate and scale ``items``' transverse momenta so they sum exactly to (tx, ty)."""
    sx, sy = sum(q.px for q in items), sum(q.py for q in items)
    k = math.hypot(tx, ty) / max(math.hypot(sx, sy), 1e-12)
    turn = math.atan2(ty, tx) - math.atan2(sy, sx)
    return [replace(q, pt=q.pt * k, phi=_wrap(q.phi + turn)) for q in items]


def _wrap(phi: float) -> float:
    return (phi + math.pi) % (2 * math.pi) - math.pi


def _soft_pairs(n: int, rng: SplitMix64) -> list[EventParticle]:
    """``n`` soft charged pions (rounded up to even) in back-to-back pairs of equal p_T
    (0.3–1.8 GeV/c), so the event's p_T balance is kept."""
    out = []
    for _ in range((max(0, n) + 1) // 2):
        pt = 0.3 + 1.5 * rng.uniform()
        phi = 2 * math.pi * rng.uniform() - math.pi
        out.append(EventParticle(PARTICLES["pi+"], pt, 4 * rng.uniform() - 2, phi, "soft"))
        out.append(EventParticle(PARTICLES["pi-"], pt, 4 * rng.uniform() - 2, _wrap(phi + math.pi), "soft"))
    return out


def _recoil(boson: FourVector, rng: SplitMix64, jets: list[Jet], particles: list[EventParticle]) -> None:
    """Balance the boson's transverse momentum: a jet (p_T ≥ 15 GeV/c) or two soft pions."""
    tx, ty = -boson.px / 1e3, -boson.py / 1e3
    pt = math.hypot(tx, ty)
    if pt < 1e-9:
        return
    phi = math.atan2(ty, tx)
    if pt >= 15:
        _add_jet(particles, jets, make_jet(pt, 3 * rng.uniform() - 1.5, phi, rng, f"jet{len(jets) + 1}"))
        return
    a = EventParticle(PARTICLES["pi+"], pt * 0.6, 2 * rng.uniform() - 1, _wrap(phi + 0.4), "recoil")
    b = EventParticle(PARTICLES["pi-"], pt * 0.4, 2 * rng.uniform() - 1, _wrap(phi - 0.6), "recoil")
    particles.extend(_balance([a, b], tx, ty))


def _add_jet(particles: list[EventParticle], jets: list[Jet], members: list[EventParticle]) -> None:
    start = len(particles)
    particles.extend(members)
    px, py = sum(q.px for q in members), sum(q.py for q in members)
    pz = sum(q.pz for q in members)
    pt = math.hypot(px, py)
    jets.append(Jet(members[0].group, tuple(range(start, start + len(members))), pt, math.asinh(pz / pt), math.atan2(py, px)))


def generate(preset: str, seed: int = 1, soft: int | None = None) -> Event:
    """A simulated event of ``preset`` (:data:`PRESETS`) from ``seed`` (deterministic), with
    ``soft`` soft charged pions (default :data:`PRESET_SOFT`)."""
    if preset not in PRESETS:
        from vidgen.plotcore.data import did_you_mean

        raise VidgenError(f"event: unknown preset '{preset}' (presets: {', '.join(PRESETS)})" + did_you_mean(preset, list(PRESETS)))
    rng = SplitMix64(seed * 1_000_003 + PRESETS.index(preset))
    particles: list[EventParticle] = []
    jets: list[Jet] = []
    products: tuple[int, ...] = ()
    parent = ""
    if preset == "dijet":
        pt = 60 + 140 * rng.uniform()
        phi = 2 * math.pi * rng.uniform() - math.pi
        _add_jet(particles, jets, make_jet(pt, 3 * rng.uniform() - 1.5, phi, rng, "jet1"))
        first = jets[0]
        second = make_jet(pt, 3 * rng.uniform() - 1.5, phi + math.pi, rng, "jet2")
        _add_jet(particles, jets, _balance(second, -sum(particles[i].px for i in first.members), -sum(particles[i].py for i in first.members)))
    else:
        key, decay, mean = {"z_to_mumu": ("Z", ("mu+", "mu-"), 8.0), "h_to_gammagamma": ("H", ("gamma", "gamma"), 15.0),
                            "h_to_4l": ("H", ("Z", "Z"), 15.0), "w_to_enu": ("W+", ("e+", "nu_e"), 8.0)}[preset]
        parent = key
        boson = _boson(_mass(key, rng), rng, mean)
        if preset == "h_to_4l":   # H → Z Z*: one Z near its mass, the other off shell
            m_z = min(_mass("Z", rng), boson.mass / 1e3 - 13.0)
            m_star = 12.0 + (boson.mass / 1e3 - m_z - 12.5) * rng.uniform()
            for _ in range(400):
                z1, z2 = _decay(boson, m_z * 1e3, m_star * 1e3, rng)
                leptons = _decay_into(z1, ("e-", "e+"), rng) + _decay_into(z2, ("mu-", "mu+"), rng)
                if _accepted(leptons):
                    break
            decayed = leptons
        else:
            decayed = _decay_into(boson, decay, rng)
        particles.extend(decayed)
        products = tuple(i for i, q in enumerate(particles) if q.visible)
        _recoil(boson, rng, jets, particles)
    particles.extend(_soft_pairs(PRESET_SOFT if soft is None else soft, rng))
    return Event(tuple(particles), tuple(jets), products, parent, preset, seed)


def custom_event(items: Sequence[dict[str, Any]], seed: int = 1, soft: int = 0, products: Sequence[int] = ()) -> Event:
    """An event from listed particles: ``{particle, pt, eta, phi}`` (GeV/c, —, degrees); a
    ``particle: jet`` is made of constituents drawn from ``seed``. Checks every particle
    reaches the detector inside its reach (|η| ≤ 3). ``products``: the listed items (1, 2…)
    whose invariant mass the event states (a jet counts with all its constituents)."""
    rng = SplitMix64(seed * 1_000_003 + 17)
    particles: list[EventParticle] = []
    jets: list[Jet] = []
    chosen: list[int] = []
    for k, item in enumerate(items, start=1):
        start = len(particles)
        _add_item(k, item, rng, particles, jets)
        if k in products:
            chosen += list(range(start, len(particles)))
    if not particles:
        raise VidgenError("event: give at least one particle")
    particles.extend(_soft_pairs(soft, rng))
    return Event(tuple(particles), tuple(jets), tuple(chosen), "", "custom", seed)


def _add_item(k: int, item: dict[str, Any], rng: SplitMix64, particles: list[EventParticle], jets: list[Jet]) -> None:
    """Add listed item ``k`` (a particle, or a jet's constituents)."""
    where = f"particles[{k}]"
    pt, eta, phi = float(item.get("pt", 0.0)), float(item.get("eta", 0.0)), math.radians(float(item.get("phi", 0.0)))
    if not pt > 0:
        raise VidgenError(f"{where}: pt must be positive (GeV/c), got {pt:g}")
    if abs(eta) > ETA_MAX:
        raise VidgenError(f"{where}: η = {eta:g} is outside the detector (|η| ≤ {ETA_MAX:g}; it would escape along the beam)")
    name = str(item["particle"])
    if name.strip().lower() == "jet":
        _add_jet(particles, jets, make_jet(pt, eta, phi, rng, f"jet{len(jets) + 1}"))
        return
    try:
        p = find_particle(name)
        signature(p)
    except VidgenError as exc:
        raise VidgenError(f"{where}: {exc}") from None
    particles.append(EventParticle(p, pt, eta, _wrap(phi)))


# ----- trajectories, hits and deposits -------------------------------------------------------------


@dataclass(frozen=True)
class Trajectory:
    """A particle's path: ``points`` (N × 3, metres) from the collision point to where it stops,
    whether it ``curled`` (turned a full circle inside the field), the ``tracker_end`` index (the
    track seen in the tracker ends there), hits on the tracker layers and the muon stations, and
    where it enters each calorimeter (``entry``: ecal / hcal → point)."""

    points: np.ndarray
    curled: bool
    tracker_end: int
    tracker_hits: tuple[tuple[float, float, float], ...] = ()
    muon_hits: tuple[tuple[float, float, float], ...] = ()
    entry: dict[str, tuple[float, float, float]] = field(default_factory=dict)


def trajectory(q: EventParticle, det: Detector, step: float = 0.01) -> Trajectory:
    """Step ``q`` through ``det`` (transverse steps of ``step`` m, smaller for tight curls): a
    charge turns by −0.3 q B / p_T per metre of transverse path (clockwise for q B > 0); the
    path stops where the particle is absorbed (an electron or a photon in the ECAL, a hadron in
    the HCAL), after one full turn (a curler) or at the detector's edge (a muon)."""
    kind = q.kind
    charge = q.charge if kind in ("electron", "muon", "charged_hadron") else 0
    if kind == "neutrino":
        return Trajectory(np.zeros((1, 3)), False, 0)
    stop_in = {"electron": ECAL, "photon": ECAL, "charged_hadron": HCAL, "neutral_hadron": HCAL}.get(kind)
    slope = math.sinh(q.eta)   # dz per metre of transverse path
    ds = step / max(1.0, abs(slope))   # steps of at most ``step`` along z too (thin endcap stations)
    if charge:
        ds = min(ds, bending_radius(q.pt, det.field) / 40)
    x = y = z = 0.0
    psi = q.phi
    turned = 0.0
    pts = [(0.0, 0.0, 0.0)]
    tracker_end = 0
    hits: list[tuple[float, float, float]] = []
    mu_hits: list[tuple[float, float, float]] = []
    entry: dict[str, tuple[float, float, float]] = {}
    inside_station: dict[int, list[tuple[float, float, float]]] = {}
    radii = [r for r, _ in TRACKER_LAYERS]
    curled = False
    for _ in range(200_000):
        r_before = math.hypot(x, y)
        b = det.bz(r_before, z) if charge else 0.0
        dpsi = -0.299792458 * charge * b / q.pt * ds
        x += ds * math.cos(psi + dpsi / 2)
        y += ds * math.sin(psi + dpsi / 2)
        z += ds * slope
        psi += dpsi
        if r_before < FIELD_R and abs(z) < FIELD_Z:
            turned += abs(dpsi)
        r = math.hypot(x, y)
        pts.append((x, y, z))
        if r <= TRACKER.r1 and abs(z) <= TRACKER.z_half:
            tracker_end = len(pts) - 1
            for k, (rl, zl) in enumerate(TRACKER_LAYERS):
                if (r_before < rl <= r or r <= rl < r_before) and abs(z) <= zl:
                    hits.append((x, y, z))
        for name, layer in (("ecal", ECAL), ("hcal", HCAL)):
            if name not in entry and layer.contains(r, z):
                entry[name] = (x, y, z)
        if kind == "muon":
            for k, station in enumerate(MUON):
                if station.contains(r, z):
                    inside_station.setdefault(k, []).append((x, y, z))
        if stop_in is not None and stop_in.key in entry:
            break
        if turned >= 2 * math.pi:
            curled = True
            break
        if r > OUTER_R or abs(z) > OUTER_Z:
            break
    for k in sorted(inside_station):
        seg = inside_station[k]
        mu_hits.append(seg[len(seg) // 2])
    points = np.array(pts)
    return Trajectory(points, curled, tracker_end if charge else 0, tuple(hits) if charge else (), tuple(mu_hits), entry)


@dataclass(frozen=True)
class Deposit:
    """Energy (GeV) a particle leaves in a calorimeter (``ecal`` / ``hcal``) where it enters
    it (``point``), and the particle's index."""

    layer: str
    energy: float
    point: tuple[float, float, float]
    index: int

    @property
    def phi(self) -> float:
        return math.atan2(self.point[1], self.point[0])

    @property
    def theta(self) -> float:
        x, y, z = self.point
        return math.atan2(math.hypot(x, y), z)

    @property
    def endcap(self) -> bool:
        x, y, z = self.point
        layer = ECAL if self.layer == "ecal" else HCAL
        return layer.in_endcap(math.hypot(x, y), z) and not layer.in_barrel(math.hypot(x, y), z)


#: Hadron showers spread over neighbouring cells: (offset in cells, share).
HADRON_SPREAD = ((-1, 0.2), (0, 0.6), (1, 0.2))


def deposits(event: Event, paths: Sequence[Trajectory]) -> list[Deposit]:
    """Every calorimeter deposit of ``event`` (its trajectories ``paths``): the particle's energy
    shared by :data:`CALO_SHARE`, at the point it enters each calorimeter. A curler deposits
    nothing (it never reaches them)."""
    out = []
    for i, (q, path) in enumerate(zip(event.particles, paths)):
        share = CALO_SHARE.get(q.kind)
        if share is None or path.curled:
            continue
        for layer, frac in zip(("ecal", "hcal"), share):
            if frac > 0 and layer in path.entry:
                out.append(Deposit(layer, q.energy * frac, path.entry[layer], i))
    return out


@dataclass(frozen=True)
class Tower:
    """A calorimeter tower for drawing: its calorimeter, the cell's centre angle (azimuth φ in
    the x–y view; polar angle θ with the side ±1 in the r–z view), its angular size, summed
    energy (GeV), whether it sits in an endcap (r–z) and the particles in it."""

    layer: str
    angle: float
    width: float
    energy: float
    side: int = 1
    endcap: bool = False
    indices: tuple[int, ...] = ()


#: Cell sizes (schematic, coarser than a real calorimeter's so a tower reads at video size):
#: azimuth and polar angle (radians) per calorimeter.
CELL_PHI = {"ecal": math.radians(7.5), "hcal": math.radians(12.0)}
CELL_THETA = {"ecal": math.radians(6.0), "hcal": math.radians(9.0)}


def towers(event: Event, deps: Sequence[Deposit], view: str = "xy") -> list[Tower]:
    """The deposits binned in cells: by azimuth in the x–y view, by polar angle (and the side
    of the beam: upper +1 for 0 ≤ φ < π, lower −1) in the r–z view. Hadron showers spread over
    their neighbouring cells (:data:`HADRON_SPREAD`), electromagnetic ones stay in one."""
    cells: dict[tuple[str, int, int, bool], list[Any]] = {}
    for d in deps:
        kind = event.particles[d.index].kind
        if view == "xy":
            size, angle, side, endcap = CELL_PHI[d.layer], d.phi, 1, False
        else:
            size, angle = CELL_THETA[d.layer], d.theta
            side, endcap = (1 if d.phi >= 0 else -1), d.endcap
        k0 = math.floor(angle / size)
        spread = HADRON_SPREAD if kind in ("charged_hadron", "neutral_hadron") else ((0, 1.0),)
        for dk, share in spread:
            key = (d.layer, k0 + dk, side, endcap)
            entry = cells.setdefault(key, [0.0, set()])
            entry[0] += d.energy * share
            entry[1].add(d.index)
    out = []
    for (layer, k, side, endcap), (energy, idx) in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        size = CELL_PHI[layer] if view == "xy" else CELL_THETA[layer]
        out.append(Tower(layer, (k + 0.5) * size, size, energy, side, endcap, tuple(sorted(idx))))
    return out


def tower_fraction(energy: float, full: float, scale: str = "linear") -> float:
    """How much of the calorimeter's depth a tower of ``energy`` fills when ``full`` GeV fills
    it all: E / full (``linear``) or log(1 + E/GeV) / log(1 + full/GeV) (``log``); at least
    0.12 so a small one shows, at most 1."""
    if full <= 0:
        return 0.0
    if scale == "log":
        f = math.log1p(energy) / math.log1p(full)
    else:
        f = energy / full
    return max(0.12, min(1.0, f))


__all__ = [
    "CALO_SHARE",
    "CELL_PHI",
    "CELL_THETA",
    "ECAL",
    "ETA_MAX",
    "ETA_TRACKER",
    "HCAL",
    "IRON",
    "MUON",
    "OUTER_R",
    "OUTER_Z",
    "PRESETS",
    "PRESET_SOFT",
    "SIGNATURES",
    "SIGNATURE_PARTS",
    "SOLENOID",
    "TRACKER",
    "TRACKER_LAYERS",
    "Deposit",
    "Detector",
    "Event",
    "EventParticle",
    "Jet",
    "Layer",
    "Tower",
    "Trajectory",
    "bending_radius",
    "custom_event",
    "deposits",
    "generate",
    "make_jet",
    "signature",
    "signature_problem",
    "signature_text",
    "tower_fraction",
    "towers",
    "trajectory",
]
