"""The particle-physics accuracy lint's knowledge (Phase Y, Step 242; DESIGN §99.13) — no manim.

What narration and screen text say about particles, read narrowly and compared with the model:
masses, charges, spins, lifetimes and widths (:mod:`.data`, PDG 2024), branching ratios
(:mod:`.branching`), "allowed" / "forbidden" / "conserves" claims (the checker,
:func:`.conservation.check`), which boson does what (couplings, flavour change, the bosons of a
diagram), detector signatures (:data:`.detector.SIGNATURES`), significance claims (the p-value
said as the chance the result is wrong; σ against a spectrum's computed significance) and
decay lengths and dilated lifetimes said with a momentum. Numbers, units and "about" are read
by the ``calc_*`` reader (:mod:`vidgen.quantities.accuracy`). Particles are found by name
("the Z boson", "bottom quarks", "positrons", "neutral pions") or symbol (``μ⁺``, ``π⁰``,
``ν̄ₑ``, ``W⁻``); a claim is about the particle named just before it in the same clause. Like
the other accuracy modules every check is narrow: negations and questions are left alone (a
"not" turns a claim around, so "photons do not leave tracks" is never read as "photons leave
tracks"), ranges and bounds are not compared, a finding needs the particle and the quantity to
be clear. Each function returns :class:`Said` findings (rule, quote, message, severity)."""

from __future__ import annotations

import functools
import itertools
import math
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from vidgen.cellworld.accuracy import plain
from vidgen.quantities import accuracy as qa
from vidgen.quantities.units import dim

from . import branching as br
from .conservation import check
from .data import PARTICLES, Particle, energy_text, fraction_text, time_text
from .names import find_key
from .process import Leg, Process, _split_run

#: The rules, in :data:`vidgen.config.LINT_RULES` order.
PARTICLE_RULES: tuple[str, ...] = (
    "particle_mass", "particle_charge", "particle_spin", "particle_lifetime", "branching_ratio", "conservation_claim",
    "feynman_boson", "kinematics_number", "detector_signature", "significance_claim", "simulated_label", "particle_units",
)
#: Rules that read every project; the others only projects with a particle-physics scene.
EVERYWHERE = ("particle_charge", "particle_spin")

_MEV_J = 1.602176634e-13
_C = 299792458.0
ENERGY, MASS, MOMENTUM = dim(kg=1, m=2, s=-2), dim(kg=1), dim(kg=1, m=1, s=-1)
TIME, LENGTH = dim(s=1), dim(m=1)
#: Quark masses depend on the scheme (MS-bar, pole): a said value within this share is fine.
QUARK_SCHEME_TOLERANCE = 0.3


@dataclass(frozen=True)
class Said:
    """A finding: the ``rule``, the sentence (``quote``), what is wrong and what to say, and a
    severity when it differs from the rule's."""

    rule: str
    quote: str
    message: str
    severity: str | None = None


# ----- sentences ------------------------------------------------------------------------------------


def sentences(text: str) -> list[str]:
    """The sentences of ``text`` (split at . ! ? ; but not at decimal points), cleaned."""
    parts = re.split(r"(?<=[.!?;])\s+", qa.clean(str(text)).strip())
    return [p.strip() for p in parts if p.strip()]


def plain_sentences(text: str) -> list[str]:
    """The sentences that are plain statements: no negation, contrast or question."""
    return [s for s in sentences(text) if plain(s)]


def _plain_only(fn: Callable[..., list[Said]]) -> Callable[..., list[Said]]:
    """A claim reader that leaves negations, contrasts and questions alone ("photons do not
    leave tracks" is right; a "not" turns any claim around)."""
    @functools.wraps(fn)
    def wrapper(sentence: str, *args: Any, **kwargs: Any) -> list[Said]:
        return fn(sentence, *args, **kwargs) if plain(sentence) else []

    return wrapper


# ----- particles named in a sentence ---------------------------------------------------------------


@dataclass(frozen=True)
class Mention:
    """A particle named in a sentence: where, as written, the keys it may be (a generic "W"
    is W⁺ or W⁻, "neutrinos" any flavour) and whether it was plural."""

    start: int
    end: int
    text: str
    keys: tuple[str, ...]
    plural: bool = False

    @property
    def particles(self) -> list[Particle]:
        return [PARTICLES[k] for k in self.keys]

    @property
    def name(self) -> str:
        """How the message names it: the particle's name, or the text for a generic mention."""
        names = list(dict.fromkeys(_short_name(p) for p in self.particles))
        return names[0] if len(names) == 1 else self.text.strip().lower()


def _short_name(p: Particle) -> str:
    return {"W+": "W boson", "W-": "W boson", "gamma": "photon"}.get(p.key, p.name)


_NU = ("nu_e", "nu_mu", "nu_tau")
_ANU = ("anti-nu_e", "anti-nu_mu", "anti-nu_tau")
_QUARK_WORDS = {"u": "up", "d": "down", "s": "strange", "c": "charm(?:ed)?", "b": "bottom|beauty", "t": "top|truth"}


def _patterns() -> list[tuple[re.Pattern[str], tuple[str, ...]]]:
    """(pattern, keys), longest phrases first; names case-insensitive, W / Z / H as capitals."""
    i = re.IGNORECASE
    out: list[tuple[str, tuple[str, ...], int]] = []
    for key, words in _QUARK_WORDS.items():
        out += [(rf"\b(?:{words})[- ]anti-?quarks?\b", ("anti-" + key,), i), (rf"\banti-?(?:{words})[- ]quarks?\b", ("anti-" + key,), i),
                (rf"\b(?:{words})[- ]quarks?\b", (key,), i), (rf"\b{key}[- ]anti-?quarks?\b", ("anti-" + key,), 0),
                (rf"\b{key}[- ]quarks?\b", (key,), 0), (rf"\b{key}̄(?=\W|$)(?![-/])", ("anti-" + key,), 0)]
    for flavour, words in (("e", "electron|e"), ("mu", "muon|mu|μ"), ("tau", "tau|τ")):
        out += [(rf"\b(?:{words})[- ]anti-?neutrinos?\b", (f"anti-nu_{flavour}",), i), (rf"\b(?:{words})[- ]neutrinos?\b", (f"nu_{flavour}",), i)]
    out += [
        (r"\banti-?neutrinos?\b", _ANU, i), (r"\bneutrinos?\b", _NU, i),
        (r"\bpositrons?\b|\banti-?electrons?\b", ("e+",), i), (r"\belectrons?\b", ("e-",), i),
        (r"\banti-?muons?\b", ("mu+",), i), (r"\bmuons?\b", ("mu-",), i),
        (r"\banti-?taus?\b", ("tau+",), i), (r"\btau[- ](?:leptons?|particles?)\b|\btaus\b|\btau\b(?!\s*[=(₀])", ("tau-",), i),
        (r"\bphotons?\b", ("gamma",), i), (r"\bgluons?\b", ("g",), i),
        (r"\bHiggs(?:[- ](?:bosons?|particles?))?\b", ("H",), i), (r"\bH(?=\s*(?:→|->|boson))", ("H",), 0),
        (r"\bW(?:\s*[+⁺])(?:\s*bosons?)?", ("W+",), 0), (r"\bW(?:\s*[-⁻])(?!\w)(?:\s*bosons?)?", ("W-",), 0),
        (r"\bW(?:±)?(?:[- ]bosons?)?\b(?!\s*=)", ("W+", "W-"), 0), (r"\bZ(?:⁰|0)?(?:[- ]bosons?)?\b(?!\s*=)(?![-/])", ("Z",), 0),
        (r"\bantiprotons?\b", ("anti-p",), i), (r"\bprotons?\b", ("p",), i), (r"\bantineutrons?\b", ("anti-n",), i), (r"\bneutrons?\b", ("n",), i),
        (r"\b(?:positive|positively[- ]charged)\s+pions?\b|\bpi[- ]plus\b", ("pi+",), i),
        (r"\b(?:negative|negatively[- ]charged)\s+pions?\b|\bpi[- ]minus\b", ("pi-",), i),
        (r"\bneutral\s+pions?\b|\bpi[- ](?:zero|nought)\b", ("pi0",), i), (r"\bcharged\s+pions?\b", ("pi+", "pi-"), i),
        (r"\bpions?\b", ("pi+", "pi-", "pi0"), i), (r"\bcharged\s+kaons?\b", ("K+", "K-"), i),
        (r"\bneutral\s+kaons?\b", ("K0", "anti-K0", "K0_S", "K0_L"), i), (r"\bkaons?\b", ("K+", "K-", "K0", "anti-K0", "K0_S", "K0_L"), i),
        (r"\bLambda(?:\s+baryons?)?\b", ("Lambda",), 0), (r"\bJ/(?:ψ|psi)\b", ("J/psi",), i), (r"\bUpsilon\b", ("Upsilon(1S)",), 0),
    ]
    return [(re.compile(p, flags), keys) for p, keys, flags in out]


_PATTERNS = _patterns()
#: Words after a particle's name that make it a thing named after it ("muon chambers",
#: "electron number", "photon detector").
_NOT_A_PARTICLE = re.compile(r"[\s-]+(?:chambers?|system|detectors?|spectrometer|stations?|numbers?|family|families|flavou?r\s+number|"
                             r"multiplier|microscope|volts?|gun|cloud|shell|orbitals?|configuration)\b", re.IGNORECASE)
#: A symbol: a letter (Greek or Latin), an optional bar, then charge marks or a subscript.
_SYMBOL = re.compile(r"(?<![\w/])([A-Za-zα-ωΑ-Ω](?:[̄̅])?(?:[⁺⁻⁰±]+|[+-](?![\w\d])|[ₑ]|_(?:e|μ|mu|τ|tau|S|L)\b|⁰_[SL])*)")
#: Bare Greek letters that name a particle on their own (μ, τ, π, φ... are also quantities).
_BARE = {"γ": ("gamma",), "ν": _NU}


def _symbol_keys(token: str) -> tuple[str, ...] | None:
    if token in _BARE:
        return _BARE[token]
    marked = any(c in token for c in "⁺⁻⁰±+-ₑ_̄̅")
    if not marked:
        return None
    if token.endswith("±"):
        a, b = find_key(token[:-1] + "+"), find_key(token[:-1] + "-")
        return tuple(k for k in (a, b) if k) or None
    if token[:1].isascii() and token[:1].isalpha() and token[:1] not in "epnKDBWZΛ":
        return None
    key = find_key(token)
    return (key,) if key else None


def mentions(sentence: str) -> list[Mention]:
    """The particles ``sentence`` names, in order (overlapping matches: the longest)."""
    found: list[Mention] = []
    for pattern, keys in _PATTERNS:
        for m in pattern.finditer(sentence):
            if m.end() > m.start() and not _NOT_A_PARTICLE.match(sentence, m.end()):
                word = m.group(0).rstrip().lower()
                found.append(Mention(m.start(), m.end(), m.group(0), keys, word.endswith("s") and len(word) > 2 and not word.endswith("higgs")))
    for m in _SYMBOL.finditer(sentence):
        token = m.group(1)
        keys = _symbol_keys(token)
        if keys:
            found.append(Mention(m.start(1), m.end(1), token, keys))
    found.sort(key=lambda x: (x.start, -(x.end - x.start)))
    out: list[Mention] = []
    for x in found:
        if out and x.start < out[-1].end:
            continue
        out.append(x)
    return out


def _placeholders(sentence: str, ms: Sequence[Mention]) -> str:
    """The sentence with each mention replaced by ``§k§`` (its index), for the claim patterns."""
    out, pos = [], 0
    for k, m in enumerate(ms):
        out += [sentence[pos:m.start], f"§{k}§"]
        pos = m.end
    return "".join(out) + sentence[pos:]


# ----- charge ------------------------------------------------------------------------------------------

_CHARGE_NUM = (r"(?P<sign>plus|minus|positive|negative|\+|-|±)?\s*(?P<num>two[- ]thirds?|one[- ]third|a[- ]third|2\s*/\s*3|1\s*/\s*3|⅔|⅓|one|zero|two|"
               r"[012](?![\d,/]|\.\d))(?:\s*(?:e\b|units?\s+of\s+(?:the\s+)?(?:elementary\s+)?charge))?")
_CHARGE_CLAIMS = [
    re.compile(rf"§(?P<k>\d+)§[^§.;]{{0,40}}?\bcharges?\b\s*(?:of|is|equals|=|:)?\s*(?:about\s+)?{_CHARGE_NUM}", re.IGNORECASE),
    re.compile(rf"§(?P<k>\d+)§\s+(?:has|have|carries|carry|with|bears?)\s+(?:a\s+|an\s+)?(?:electric\s+)?{_CHARGE_NUM}\s+(?:electric\s+)?charge",
               re.IGNORECASE),
    re.compile(rf"\bcharge\s+of\s+(?:the\s+|an?\s+)?§(?P<k>\d+)§\s*(?:is|equals|=|:)\s*{_CHARGE_NUM}", re.IGNORECASE),
]
_CHARGE_WORD = re.compile(r"§(?P<k>\d+)§\s+(?:is|are)\s+(?:electrically\s+)?(?P<word>neutral|uncharged|positively\s+charged|negatively\s+charged|"
                          r"positive|negative)\b", re.IGNORECASE)
_ARITHMETIC = re.compile(r"\b(?:sum|add(?:s|ed|ing)?\s+up|total|together|combined|plus\b.*\b(?:plus|minus)\b)", re.IGNORECASE)


def _charge_value(sign: str | None, num: str) -> tuple[Fraction, bool]:
    """The charge said (in units of e) and whether its sign was said."""
    n = num.lower().replace(" ", "").replace("-", "")
    magnitude = {"twothirds": Fraction(2, 3), "twothird": Fraction(2, 3), "2/3": Fraction(2, 3), "⅔": Fraction(2, 3), "onethird": Fraction(1, 3),
                 "athird": Fraction(1, 3), "1/3": Fraction(1, 3), "⅓": Fraction(1, 3), "one": Fraction(1), "1": Fraction(1), "zero": Fraction(0),
                 "0": Fraction(0), "two": Fraction(2), "2": Fraction(2)}[n]
    if not sign or sign == "±":
        return magnitude, False
    return (-magnitude if sign.lower() in ("minus", "negative", "-") else magnitude), True


def _same_charge(value: Fraction, family: str, exclude: Iterable[str]) -> list[str]:
    """Particles of ``family`` with charge ``value`` (did-you-mean)."""
    skip = set(exclude)
    names = [_short_name(p) for p in PARTICLES.values() if p.family == family and p.charge == value and p.key not in skip
             and p.family in ("quark", "lepton", "gauge boson", "scalar boson")]
    return list(dict.fromkeys(names))[:3]


@_plain_only
def charge_claims(sentence: str) -> list[Said]:
    """``particle_charge``: "the down quark has charge +2/3" (its charge is −1/3), "the
    neutron is positively charged"; a charge said without a sign is compared by size."""
    ms = mentions(sentence)
    if not ms or _ARITHMETIC.search(sentence):
        return []
    text = _placeholders(sentence, ms)
    out: list[Said] = []
    seen: set[int] = set()
    for pattern in _CHARGE_CLAIMS:
        for m in pattern.finditer(text):
            k = int(m.group("k"))
            if k in seen:
                continue
            seen.add(k)
            value, signed = _charge_value(m.group("sign"), m.group("num"))
            ps = ms[k].particles
            ok = any(p.charge == value if signed else abs(p.charge) == abs(value) for p in ps)
            if not ok:
                p = ps[0]
                said = fraction_text(value, sign=signed) if signed else fraction_text(value)
                actual = " or ".join(dict.fromkeys(fraction_text(q.charge, sign=True) for q in ps))
                hint = _same_charge(value, p.family, [q.key for q in ps]) if signed else []
                mean = f"; {said} is the charge of the {', the '.join(hint)}" if hint else ""
                out.append(Said("particle_charge", sentence, f"the {ms[k].name}'s charge is {actual} (in units of e), not {said}{mean}"))
    for m in _CHARGE_WORD.finditer(text):
        k = int(m.group("k"))
        if k in seen:
            continue
        word = m.group("word").lower()
        ps = ms[k].particles
        want = 0 if word in ("neutral", "uncharged") else (1 if word.startswith("positive") else -1)
        ok = any((p.charge == 0) if want == 0 else (p.charge * want > 0) for p in ps)
        if not ok:
            actual = " or ".join(dict.fromkeys(fraction_text(q.charge, sign=True) for q in ps))
            out.append(Said("particle_charge", sentence, f"the {ms[k].name} is not {word}: its charge is {actual} (in units of e)"))
    return out


# ----- spin --------------------------------------------------------------------------------------------

_SPIN_NUM = r"(?P<num>zero|0|one[- ]half|a[- ]half|half|1\s*/\s*2|½|one|1|three[- ]halves|3\s*/\s*2|two|2)(?![\d/]|\.\d|[- ]?(?:half|halves|thirds?))"
_SPIN_CLAIMS = [
    re.compile(rf"§(?P<k>\d+)§[^§.;]{{0,40}}?\bspin(?:[- ]|\s+of\s+|\s+is\s+|\s*=\s*|:\s*)(?:a\s+)?{_SPIN_NUM}", re.IGNORECASE),
    re.compile(rf"\bspin\s+of\s+(?:the\s+|an?\s+)?§(?P<k>\d+)§\s*(?:is|equals|=|:)\s*{_SPIN_NUM}", re.IGNORECASE),
    re.compile(rf"\bspin[- ]{_SPIN_NUM}\s+§(?P<k>\d+)§", re.IGNORECASE),
]
_KIND_WORD = re.compile(r"§(?P<k>\d+)§\s+(?:is|are)\s+(?:a\s+|an\s+)?(?:\w+\s+)?(?P<word>fermions?|bosons?|spinless)\b", re.IGNORECASE)


def _spin_value(num: str) -> Fraction:
    n = num.lower().replace(" ", "").replace("-", "")
    return {"zero": Fraction(0), "0": Fraction(0), "onehalf": Fraction(1, 2), "ahalf": Fraction(1, 2), "half": Fraction(1, 2), "1/2": Fraction(1, 2),
            "½": Fraction(1, 2), "one": Fraction(1), "1": Fraction(1), "threehalves": Fraction(3, 2), "3/2": Fraction(3, 2), "two": Fraction(2),
            "2": Fraction(2)}[n]


@_plain_only
def spin_claims(sentence: str) -> list[Said]:
    """``particle_spin``: "the photon has spin 1/2" (it has spin 1), "the Higgs boson is a
    fermion", "the electron is spinless"."""
    ms = mentions(sentence)
    if not ms:
        return []
    text = _placeholders(sentence, ms)
    out: list[Said] = []
    seen: set[int] = set()
    for pattern in _SPIN_CLAIMS:
        for m in pattern.finditer(text):
            k = int(m.group("k"))
            if k in seen:
                continue
            seen.add(k)
            value = _spin_value(m.group("num"))
            ps = ms[k].particles
            if not any(p.spin == value for p in ps):
                kind = "fermion" if ps[0].is_fermion else "boson"
                out.append(Said("particle_spin", sentence, f"the {ms[k].name} has spin {fraction_text(ps[0].spin)} (a {kind}), not spin "
                                                           f"{fraction_text(value)}"))
    for m in _KIND_WORD.finditer(text):
        k = int(m.group("k"))
        if k in seen:
            continue
        word = m.group("word").lower()
        ps = ms[k].particles
        p = ps[0]
        if word.startswith("fermion") and not any(q.is_fermion for q in ps) or word.startswith("boson") and all(q.is_fermion for q in ps):
            kind = "fermion" if p.is_fermion else "boson"
            out.append(Said("particle_spin", sentence, f"the {ms[k].name} is a {kind} (spin {fraction_text(p.spin)}), not a {word.rstrip('s')}"))
        elif word == "spinless" and all(q.spin != 0 for q in ps):
            out.append(Said("particle_spin", sentence, f"the {ms[k].name} has spin {fraction_text(p.spin)}; spinless (spin 0) is the Higgs boson "
                                                       f"(and the pions, kaons)"))
    return out


# ----- values said for a particle ------------------------------------------------------------------------


def mev_of(v: qa.SaidValue) -> float | None:
    """A value said in eV units (an energy, a mass in eV/c², a momentum in eV/c) in MeV (c = 1)."""
    if v.unit is None:
        return None
    if v.dim == ENERGY:
        return v.si / _MEV_J
    if v.dim == MASS:
        return v.si * _C**2 / _MEV_J
    if v.dim == MOMENTUM:
        return v.si * _C / _MEV_J
    return None


def si_of_mev(mev: float, like: qa.SaidValue) -> float:
    """``mev`` in the SI dimension of the said value ``like`` (energy, mass or momentum)."""
    if like.dim == MASS:
        return mev * _MEV_J / _C**2
    if like.dim == MOMENTUM:
        return mev * _MEV_J / _C
    return mev * _MEV_J


def _subject(ms: Sequence[Mention], v: qa.SaidValue, sentence: str, reach: int = 70) -> Mention | None:
    """The particle a value is said about: the nearest mention before it, with no other mention
    or clause break (";", " while ", " whereas ") between, at most ``reach`` characters away."""
    before = [m for m in ms if m.end <= v.start]
    if not before:
        return None
    m = before[-1]
    gap = sentence[m.end:v.start]
    if len(gap) > reach or re.search(r";|\bwhile\b|\bwhereas\b|\bthen\b|\bwhich\b", gap):
        return None
    return m


_MASS_WORDS = re.compile(r"\b(?:mass(?:es)?|weigh(?:s|ing)?|weight|heav(?:y|ier|iest)|light(?:er|est)?|rest\s+energy)\b", re.IGNORECASE)
_ENERGY_WORDS = re.compile(r"\b(?:energ(?:y|ies)|momentum|momenta|beams?|collid\w*|collision|carr(?:y|ies|ying)|kinetic|threshold|width|wide|"
                           r"each|per|total|sum|transverse|p_?T|travels?|missing|invariant|resolution|bins?|window|fit\w*|accelerat\w*|"
                           r"produc\w*|needs?|takes?|at\s+least|between|range|from|to\s+\d)\b", re.IGNORECASE)
_COMPARISON_AFTER = re.compile(r"^\s*(?:heavier|lighter|more|less|times|than|above|below|apart|difference|over|under|higher|lower)\b", re.IGNORECASE)
_COPULA = re.compile(r"^\s*(?:is|are|'s|weighs|weigh|comes\s+in\s+at|sits\s+at|at)\s*(?:about|roughly|around|nearly|some|just\s+over|just\s+under|"
                     r"approximately|~|≈)?\s*$", re.IGNORECASE)
#: A mass of several particles together (the invariant mass of a pair): not one particle's.
_SYSTEM = re.compile(r"\binvariant\s+mass|\bmass(?:es)?\s+of\s+(?:the\s+|both\s+|all\s+)?(?:two|three|four|pair|system|both|products)\b|"
                     r"\bpair(?:'s)?\s+mass\b|\bcombined\b|\btogether\b|\bsystem\b|\bm\(", re.IGNORECASE)
#: Particles whose mass is said adjectivally ("a 125 GeV Higgs boson"): the bosons and the top
#: quark (for others an adjectival energy is more likely their energy: "a 45 GeV electron").
_ADJECTIVE_MASS = ("H", "Z", "W+", "W-", "t", "anti-t")


def _close(said: qa.SaidValue, actual_mev: float, tolerance: float) -> bool:
    return qa.agrees(said, si_of_mev(actual_mev, said), tolerance)


def _mass_tolerance(p: Particle, tolerance: float) -> float:
    return max(tolerance, QUARK_SCHEME_TOLERANCE) if p.is_quark and p.key.removeprefix("anti-") != "t" else tolerance


def _others_with_mass(said: qa.SaidValue, exclude: Iterable[str], tolerance: float) -> list[str]:
    skip = set(exclude)
    names: list[str] = []
    for p in PARTICLES.values():
        if p.key in skip or p.mass_mev <= 0 or p.key.startswith("anti-") or p.key in ("W-", "mu+", "e+", "tau+", "pi-", "K-", "D-", "B-"):
            continue
        if said.approx or said.sig is None or said.sig >= 2:
            if _close(said, p.mass_mev, _mass_tolerance(p, tolerance)) and abs(mev_of(said) or 0) > 0:
                names.append(_short_name(p))
    return list(dict.fromkeys(names))[:2]


@_plain_only
def mass_claims(sentence: str, tolerance: float = 0.05) -> list[Said]:
    """``particle_mass``: a mass said for a particle ("the Z weighs about 91 GeV" fits 91.19;
    "a top quark is 173 GeV" fits 172.57; "the W weighs 91 GeV" does not — the Z's), in eV,
    eV/c² or kg; quark masses within :data:`QUARK_SCHEME_TOLERANCE` (the scheme)."""
    ms = mentions(sentence)
    if not ms or _SYSTEM.search(sentence):
        return []
    out: list[Said] = []
    for v in qa.said_values(sentence):
        mev = mev_of(v)
        if mev is None or not v.checkable or v.dim == MOMENTUM:
            continue
        if _COMPARISON_AFTER.match(sentence[v.end:]) or re.search(r"\bby\s+$", sentence[:v.start]):
            continue
        m = _subject(ms, v, sentence)
        adjective = None
        if m is None or not (_MASS_WORDS.search(sentence[max(0, m.start - 25):v.end]) or v.dim == MASS or _COPULA.match(sentence[m.end:v.start])):
            after = next((x for x in ms if x.start >= v.end and re.fullmatch(r"[\s-]*", sentence[v.end:x.start])), None)
            if after is None or not set(after.keys) <= set(_ADJECTIVE_MASS):
                continue
            adjective = after
        subject = adjective or m
        assert subject is not None
        if v.dim == ENERGY and _ENERGY_WORDS.search(sentence) and not _MASS_WORDS.search(sentence):
            continue
        ps = [p for p in subject.particles]
        if any(p.mass_limit_mev is not None for p in ps):
            limit = ps[0].mass_limit_mev or 0.0
            if mev > limit * 1.0001:
                out.append(Said("particle_mass", sentence, f"{qa.said_name(v)} for the {subject.name}: neutrino masses are not known; the "
                                                           f"direct limit is {energy_text(limit, 1)} (KATRIN, PDG 2024)"))
            continue
        if all(p.mass_mev == 0 for p in ps):
            if mev > 0:
                out.append(Said("particle_mass", sentence, f"{qa.said_name(v)} for the {subject.name}: it is massless"))
            continue
        if any(_close(v, p.mass_mev, _mass_tolerance(p, tolerance)) for p in ps if p.mass_mev > 0):
            continue
        p = ps[0]
        actual = energy_text(p.mass_mev, 4 if p.mass_mev < 1000 else 5)
        power = qa.mixup_power(v, si_of_mev(p.mass_mev, v), _mass_tolerance(p, tolerance))
        hint = " — a prefix mixed up (MeV / GeV)?" if power else ""
        others = _others_with_mass(v, [q.key for q in ps], tolerance) if not power else []
        if others:
            hint = f" — that is the {' or the '.join(others)}'s mass: did you mean the {others[0]}?"
        out.append(Said("particle_mass", sentence, f"{qa.said_name(v)} for the {subject.name}'s mass: PDG 2024 gives {actual}"
                                                   f"{' (' + p.mass_scheme + ')' if p.mass_scheme else ''}{hint}"))
    return out


_LIFE_WORDS = re.compile(r"\b(?:lives?|living|lifetimes?|life\s*time|mean\s+life|lifespan|half[- ]li(?:fe|ves)|survives?|"
                         r"decays?\s+(?:after|within|in)|lasts?)\b", re.IGNORECASE)
_HALF_LIFE = re.compile(r"\bhalf[- ]li(?:fe|ves)\b", re.IGNORECASE)
#: Words of a moving particle's dilated life (checked by ``kinematics_number`` with its γ).
_DILATION = re.compile(r"\b(?:dilat\w*|lab(?:oratory)?\s+frame|our\s+frame|seen\s+from|appears?|moving|travel\w*|γ|gamma\s+factor|lorentz|"
                       r"fast|speed|cosmic|reach\w*|at\s+rest\s+it)\b", re.IGNORECASE)
_WIDTH_WORDS = re.compile(r"\b(?:width|wide|Γ)\b|Γ", re.IGNORECASE)
_MEASURED = re.compile(r"\b(?:fit\w*|measured|observed|apparent|resolution|bins?|smear\w*|detector|histogram|peak\s+in\s+the)\b", re.IGNORECASE)


@_plain_only
def lifetime_claims(sentence: str, tolerance: float = 0.05) -> list[Said]:
    """``particle_lifetime``: a mean life ("the muon lives 2.2 microseconds", 2.197 µs), a
    half-life (τ ln 2) or a width ("the Z is 2.5 GeV wide", 2.4955 GeV) said for a particle; a
    moving particle's dilated life is ``kinematics_number``'s."""
    ms = mentions(sentence)
    if not ms:
        return []
    out: list[Said] = []
    for v in qa.said_values(sentence):
        if not v.checkable or v.unit is None:
            continue
        m = _subject(ms, v, sentence)
        if m is None:
            continue
        ps = [p for p in m.particles if not p.stable and p.lifetime is not None]
        if not ps or len(ps) < len(m.particles):
            continue
        near = sentence[max(0, v.start - 40):v.start]
        width_said = _WIDTH_WORDS.search(sentence[max(0, v.start - 25):v.start]) or re.match(r"\s*(?:wide|width)\b", sentence[v.end:], re.IGNORECASE)
        if v.dim == TIME and _LIFE_WORDS.search(near) and not _DILATION.search(sentence):
            half = _HALF_LIFE.search(sentence) is not None
            factor = math.log(2) if half else 1.0
            if any(qa.agrees(v, (p.lifetime or 0.0) * factor, tolerance) for p in ps):
                continue
            p = ps[0]
            tau = (p.lifetime or 0.0) * factor
            word = "half-life (τ ln 2)" if half else "mean life τ"
            other = "" if half or not qa.agrees(v, tau * math.log(2), tolerance) else " (that is its half-life, τ ln 2)"
            power = qa.mixup_power(v, tau, tolerance)
            hint = " — a prefix mixed up?" if power else other
            out.append(Said("particle_lifetime", sentence, f"{qa.said_name(v)} for the {m.name}: its {word} is {time_text(tau, 4)} (PDG 2024){hint}"))
        elif v.dim == ENERGY and width_said and not _MEASURED.search(sentence):
            if any(_close(v, p.width or 0.0, tolerance) for p in ps):
                continue
            p = ps[0]
            power = qa.mixup_power(v, si_of_mev(p.width or 0.0, v), tolerance)
            out.append(Said("particle_lifetime", sentence, f"{qa.said_name(v)} for the {m.name}'s width: its width Γ is {energy_text(p.width or 0.0, 4)}"
                                                           f"{' (the Standard Model prediction)' if p.key == 'H' else ' (PDG 2024)'}"
                                                           f"{' — a prefix mixed up?' if power else ''}"))
    return out


def unit_styles(sentence: str) -> tuple[list[str], list[str]]:
    """Masses written in eV (natural units) and in eV/c² in ``sentence`` (as written), for
    ``particle_units``."""
    ms = mentions(sentence)
    natural, explicit = [], []
    for v in qa.said_values(sentence):
        if mev_of(v) is None or v.dim == MOMENTUM:
            continue
        m = _subject(ms, v, sentence)
        if m is None or not (_MASS_WORDS.search(sentence) or v.dim == MASS):
            continue
        if v.dim == MASS and "c" in v.unit_text:
            explicit.append(v.text)
        elif v.dim == ENERGY and _MASS_WORDS.search(sentence):
            natural.append(v.text)
    return natural, explicit


# ----- decays in words ---------------------------------------------------------------------------------

_COUNT = {"a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "three": 3, "four": 4, "2": 2, "3": 3, "4": 4}
_LINK = re.compile(r"^(?:\s|,|and\b|plus\b|a\b|an\b|the\b|one\b|two\b|three\b|four\b|[234]\b|pairs?\s+of\b|single\b|another\b|its\b|their\b|"
                   r"or\b|either\b|\+|&)*$", re.IGNORECASE)
_DECAY_TO = re.compile(r"\bdecay(?:s|ed|ing)?\s+(?:\w+\s+){0,2}?(?:in)?to\b|→|->|\bgoes\s+to\b|\bturns?\s+into\b|\bproduces?\b", re.IGNORECASE)
#: Groups of products said in words, as the bases they stand for.
CATEGORIES: dict[str, tuple[re.Pattern[str], frozenset[str]]] = {
    "hadrons": (re.compile(r"\b(?:hadrons|jets|quark(?:[- ]antiquark)?\s+pairs|pairs\s+of\s+quarks|quarks)\b", re.IGNORECASE), frozenset({"hadrons"})),
    "leptons": (re.compile(r"\b(?:charged\s+)?lepton(?:[- ]antilepton)?\s*(?:pairs|s)\b|\bpairs\s+of\s+(?:charged\s+)?leptons\b", re.IGNORECASE),
                frozenset({"e", "mu", "tau"})),
    "invisible": (re.compile(r"\binvisible\b|\bneutrino(?:[- ]antineutrino)?\s+pairs\b|\bpairs\s+of\s+neutrinos\b", re.IGNORECASE), frozenset({"nu"})),
}


def base(p: Particle) -> str:
    """A particle's stem for comparing decays said loosely: the quark or lepton flavour (e, mu,
    tau, nu), the boson (W, Z, gamma, g, H), the hadron's key without charge."""
    key = p.key.removeprefix("anti-")
    if p.is_neutrino:
        return "nu"
    if p.is_lepton:
        return key.rstrip("+-")
    if key in ("W+", "W-"):
        return "W"
    if p.is_hadron:
        return re.sub(r"[+\-0]+$", "", key) or key
    return key


@dataclass(frozen=True)
class SaidDecay:
    """A decay said in words: the parent mention, the products (mentions with counts; a
    category such as hadrons or leptons), where the products end, and the bases said."""

    parent: Mention
    products: tuple[tuple[Mention, int], ...]
    categories: tuple[str, ...]
    end: int

    @property
    def bases(self) -> frozenset[str]:
        out = {b for m, _ in self.products for b in {base(p) for p in m.particles}}
        for c in self.categories:
            out |= CATEGORIES[c][1]
        return frozenset(out)


def said_decays(sentence: str) -> list[SaidDecay]:
    """"X decays (mostly) to Y and Z", "X → Y Z": the parent named before the verb, the products
    named after it (joined by commas, and, numbers, "a pair of")."""
    ms = mentions(sentence)
    out: list[SaidDecay] = []
    for d in _DECAY_TO.finditer(sentence):
        before = [m for m in ms if m.end <= d.start() and len(sentence[m.end:d.start()]) <= 45 and ";" not in sentence[m.end:d.start()]]
        if not before:
            continue
        parent = before[-1]
        pos = d.end()
        products: list[tuple[Mention, int]] = []
        categories: list[str] = []
        while True:
            nxt = next((m for m in ms if m.start >= pos), None)
            cat = None
            for name, (pattern, _) in CATEGORIES.items():
                cm = pattern.search(sentence, pos)
                if cm is not None and _LINK.match(sentence[pos:cm.start()]) and (nxt is None or cm.start() < nxt.start):
                    cat = (name, cm)
                    break
            if cat is not None:
                categories.append(cat[0])
                pos = cat[1].end()
                continue
            if nxt is None or not _LINK.match(sentence[pos:nxt.start]):
                break
            words = re.findall(r"[A-Za-z0-9]+", sentence[pos:nxt.start].lower())
            count = next((_COUNT[w] for w in reversed(words) if w in _COUNT), 1)
            if "pair" in words or "pairs" in words or re.match(r"[\s-]*pairs?\b", sentence[nxt.end:]):
                count = 2
            products.append((nxt, count))
            pos = nxt.end
            tail = re.match(r"[\s-]*(?:pairs?|(?:anti)?quark\s+pairs?)\b", sentence[pos:], re.IGNORECASE)
            if tail is not None:
                pos += tail.end()
        if products or categories:
            out.append(SaidDecay(parent, tuple(products), tuple(categories), pos))
    return out


def _readings(decay: SaidDecay, limit: int = 4096) -> Iterable[Process]:
    """Every specific process a decay said in words may mean: generic charges and neutrino
    flavours tried both ways (a narrator says "a muon" for μ⁺ too); "a pair" is a particle and
    its antiparticle."""
    parent_options = [(k,) for k in decay.parent.keys]
    slots: list[list[tuple[str, ...]]] = []
    for m, count in decay.products:
        keys = list(m.keys)
        extra = [PARTICLES[k].antiparticle for k in keys]
        options = list(dict.fromkeys(keys + extra))
        if count == 2 and len(decay.products) == 1:
            slots.append([(k, PARTICLES[k].antiparticle) for k in options] + [(k, k) for k in options])
        else:
            slots += [[(k,) for k in options] for _ in range(count)]
    for n, combo in enumerate(itertools.product(parent_options, *slots)):
        if n >= limit:
            return
        parent = PARTICLES[combo[0][0]]
        final = tuple(Leg(PARTICLES[k]) for group in combo[1:] for k in group)
        yield Process((Leg(parent),), final)


# ----- conservation claims ---------------------------------------------------------------------------

_FORBIDDEN = re.compile(r"\b(?:forbidden|impossible|not\s+allowed|not\s+possible|cannot\s+(?:happen|occur|proceed|go)|can't\s+(?:happen|occur)|"
                        r"never\s+(?:happens?|occurs?|seen)|is\s+not\s+seen|ruled\s+out|disallowed|prohibited)\b", re.IGNORECASE)
_ALLOWED = re.compile(r"\b(?:allowed|possible|can\s+(?:happen|occur|proceed)|permitted|conserves\s+(?:everything|all)|"
                      r"(?:is|are)\s+fine|nothing\s+forbids|not\s+forbidden)\b", re.IGNORECASE)
#: What a sentence says of a law named after it: broken ("violates", "forbidden by") or kept.
_BROKEN_BY = re.compile(r"\b(?:violat\w*|break(?:s|ing)?|broken|not\s+conserv\w*|fails?\s+to\s+conserve|forbidden\s+by|ruled\s+out\s+by|"
                        r"forbids?|changes)\b", re.IGNORECASE)
_KEPT_BY = re.compile(r"\b(?:conserv(?:es|ed|ing)|keeps?|respects?|obeys?|preserves?)\b", re.IGNORECASE)
_LAWS: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    ("charge", re.compile(r"\b(?:electric\s+)?charge\b", re.IGNORECASE), ("Q",)),
    ("baryon number", re.compile(r"\bbaryon\s+number\b", re.IGNORECASE), ("B",)),
    ("lepton number", re.compile(r"\blepton(?:\s+(?:family|flavou?r))?\s+numbers?\b|\b(?:electron|muon|tau)\s+number\b|\blepton\s+flavou?r\b",
                                 re.IGNORECASE), ("L_e", "L_μ", "L_τ")),
    ("strangeness", re.compile(r"\bstrangeness\b", re.IGNORECASE), ("S",)),
    ("energy", re.compile(r"\benergy(?:\s+conservation)?\b|\bmass[- ]energy\b|\btoo\s+light\b", re.IGNORECASE), ("energy",)),
    ("angular momentum", re.compile(r"\bangular\s+momentum\b|\bspin\b", re.IGNORECASE), ("spin",)),
)
_THIS = re.compile(r"\b(?:this|that|the|such\s+a)\s+(?:decay|reaction|process|collision|diagram|interaction|transition)\b|^(?:it|this)\b",
                   re.IGNORECASE)
_ARROW_RUN = re.compile(r"(?P<lhs>(?:[^\s,;:.()]+\s+){0,3}[^\s,;:.()]+)\s*(?:→|->|⟶)\s*(?P<rhs>[^\s,;:.()]+(?:\s+[^\s,;:.()]+){0,4})")


def written_processes(sentence: str) -> list[Process]:
    """Processes written with an arrow ("p → e⁺ π⁰"; the longest run of particle names on each
    side)."""
    from .process import parse_process

    out = []
    for m in _ARROW_RUN.finditer(sentence):
        lhs = m.group("lhs").split()
        rhs = m.group("rhs").split()
        def known(t: str) -> bool:
            t = t.rstrip("*")
            if t == "+" or find_key(t) is not None:
                return True
            # a run written together ("e⁺e⁻", "γγ", "μ+μ-"): never a plain word ("needs" is not n e e d s)
            marked = not t.isascii() or any(c in t for c in "+-")
            return marked and _split_run(t) is not None

        lhs = [t for t in itertools.takewhile(known, reversed(lhs))][::-1]
        rhs = list(itertools.takewhile(known, rhs))
        if not lhs or not rhs:
            continue
        try:
            out.append(parse_process(" ".join(lhs) + " -> " + " ".join(rhs)))
        except Exception:  # noqa: BLE001 - not a process after all
            continue
    return out


def _law_status(verdict, symbols: tuple[str, ...]) -> bool | None:  # type: ignore[no-untyped-def]
    """Whether the verdict keeps the law (``True``), breaks it (``False``) or does not test it."""
    if symbols == ("energy",):
        return None if verdict.energy_ok is None else verdict.energy_ok
    if symbols == ("spin",):
        return not any(v.startswith("angular momentum") for v in verdict.violations)
    checks = [c for c in verdict.checks if c.symbol in symbols]
    if not checks:
        return True if symbols != ("S",) else None
    return all(c.conserved for c in checks)


def conservation_claims(sentence: str, own: Sequence[Process] = ()) -> list[Said]:
    """``conservation_claim``: "this decay is allowed" for a process the checker forbids (and
    the reverse), "forbidden by baryon number" for one that conserves it, "it conserves lepton
    number" for one that does not. The process: written with an arrow, said in words ("a muon
    decays to an electron and a photon") or the scene's own ("this decay")."""
    if sentence.rstrip().endswith("?"):
        return []
    out: list[Said] = []
    carried: list[list[Process]] = []
    decays = [d for d in said_decays(sentence) if not d.categories and d.products]   # whole-sentence lists ("a, b, and c")
    cuts = [0] + [x for m in _CLAUSE_BREAK.finditer(sentence) for x in (m.start(), m.end())] + [len(sentence)]
    for start, end in zip(cuts[::2], cuts[1::2]):
        clause = sentence[start:end]
        readings: list[list[Process]] = [[p] for p in written_processes(clause)]
        if not readings:
            readings = [list(_readings(d)) for d in decays if start <= d.parent.start < end]
        if not readings and carried:
            readings = carried   # "…, but it violates muon number": the clause before's process
        if not readings and own and _THIS.search(clause):
            readings = [[p] for p in own]
        out += _clause_claims(clause, sentence, readings)
        carried = readings
    return out


#: Where a sentence's clauses part, each with its own claim ("μ⁻ → e⁻ γ is allowed, and p → e⁺ π⁰ is forbidden").
_CLAUSE_BREAK = re.compile(r",\s*(?:and|but|while|whereas|yet)\s+|;\s*|\s+whereas\s+|\s+while\s+", re.IGNORECASE)


def _clause_claims(clause: str, sentence: str, readings: list[list[Process]]) -> list[Said]:
    """One clause's claims about its process (each reading of it: a decay said in words may mean
    several)."""
    forbidden = _FORBIDDEN.search(clause) is not None and re.search(r"\bnot\s+forbidden\b", clause, re.IGNORECASE) is None
    allowed = not forbidden and _ALLOWED.search(clause) is not None
    laws: list[tuple[str, tuple[str, ...], bool]] = []   # (name, symbols, said to be kept)
    for name, pattern, symbols in _LAWS:
        for lm in pattern.finditer(clause):
            if name == "energy" and re.match(r"\s*(?:of|is|=)\s", clause[lm.end():]):
                continue   # "an energy of 5 GeV": a quantity, not the law
            before = clause[max(0, lm.start() - 40):lm.start()]
            verbs = [(m.end(), False) for m in _BROKEN_BY.finditer(before)] + [(m.end(), True) for m in _KEPT_BY.finditer(before)]
            if verbs:
                laws.append((name, symbols, max(verbs)[1]))
                break
    if not (forbidden or allowed or laws):
        return []
    out: list[Said] = []
    for options in readings:
        if not options:
            continue
        verdicts = [check(p) for p in options]
        allowed_any = next((v for v in verdicts if v.allowed), None)
        shown = str(verdicts[0].process) if len(verdicts) == 1 else str(options[0]).split(" → ")[0] + " → …"
        broken_laws = [x for x in laws if not x[2]]
        if forbidden and allowed_any is not None and not broken_laws:
            out.append(Said("conservation_claim", sentence, f"called forbidden, but the checker allows {allowed_any.process} "
                                                            f"({allowed_any.summary().removeprefix('allowed: ')})"))
        if allowed and allowed_any is None:
            out.append(Said("conservation_claim", sentence, f"called allowed, but the checker forbids {shown}: "
                                                            f"{'; '.join(dict.fromkeys(x for v in verdicts for x in v.violations))}"))
        for name, symbols, kept in laws:
            status = [_law_status(v, symbols) for v in verdicts]
            if not kept and all(s is True for s in status):
                broken = "; ".join(dict.fromkeys(x for v in verdicts for x in v.violations)) or "nothing: it is allowed"
                out.append(Said("conservation_claim", sentence, f"{shown} conserves {name}; what the checker finds broken is: {broken}"))
            elif kept and all(s is False for s in status):
                detail = next((c.violation() for c in verdicts[0].checks if c.symbol in symbols and not c.conserved), f"{name} is not conserved")
                out.append(Said("conservation_claim", sentence, f"said to conserve {name}, but {shown}: {detail}"))
    return out


# ----- branching ratios --------------------------------------------------------------------------------

_MOST = re.compile(r"\b(?:most(?!\s+(?:common|frequent|likely))|mostly|mainly|usually|majority|predominantly|almost\s+always|chiefly|primarily|"
                   r"generally)\b", re.IGNORECASE)
_TOP = re.compile(r"\b(?:most\s+(?:common|frequent|likely)|commonest|dominant|leading|main|favou?rite|preferred)\b", re.IGNORECASE)
_RARE = re.compile(r"\b(?:rare(?:ly)?|seldom|occasionally|hardly\s+ever|a\s+tiny\s+fraction|very\s+few)\b", re.IGNORECASE)


def _table(parent: Mention) -> br.Branching | None:
    for key in parent.keys:
        if key in br.listed() or PARTICLES[key].antiparticle in br.listed():
            try:
                return br.branching(key)
            except Exception:  # noqa: BLE001 - not a listed parent
                continue
    return None


def _mode_bases(mode: br.Mode, table: br.Branching) -> frozenset[str]:
    if mode.process is None:
        return frozenset({"hadrons"}) if "hadron" in (mode.name or "") else frozenset({"nu"}) if "invisible" in (mode.name or "") else frozenset()
    from .process import parse_process

    proc = parse_process(mode.process)
    return frozenset(base(leg.particle) for leg in proc.final)


def _matching(decay: SaidDecay, table: br.Branching) -> list[br.Mode]:
    said = decay.bases
    out = []
    for mode in table.modes:
        bases = _mode_bases(mode, table)
        if not bases:
            continue
        if said == bases or (decay.categories and bases <= said and not (said - bases - {b for c in decay.categories for b in CATEGORIES[c][1]})):
            out.append(mode)
        elif said and said < bases and "nu" in bases and said | {"nu"} == bases:
            out.append(mode)   # "a muon" for μ⁺ν_μ: the neutrino left unsaid
    return out


_SHARE_AFTER = re.compile(r"\s*(?:,?\s*with\s+(?:a\s+|an\s+)?(?:branching\s+(?:ratio|fraction)|probability|share|rate)\s+(?:of\s+)?)?"
                          r"(?:in\s+|about\s+|roughly\s+|around\s+|nearly\s+|some\s+|only\s+|just\s+)*$", re.IGNORECASE)


def _share_of(sentence: str, v: qa.SaidValue, decay: SaidDecay) -> bool:
    """Whether a share said is this decay's: right before the parent ("70 % of Z bosons") or
    right after the products ("… to hadrons 70 % of the time", "with a branching ratio of 21 %")
    — not a later clause's ("…, twenty percent to neutrinos")."""
    if v.end <= decay.parent.start:
        return decay.parent.start - v.end <= 25 and "," not in sentence[v.end:decay.parent.start]
    return v.start >= decay.end and _SHARE_AFTER.match(sentence[decay.end:v.start]) is not None


@_plain_only
def branching_claims(sentence: str, tolerance: float = 0.1) -> list[Said]:
    """``branching_ratio``: "most Higgs bosons decay to two photons" (bb̄ 58 %, γγ 0.23 %), "the Z
    decays to hadrons 70 % of the time" (69.9 %), "the W rarely decays to a lepton and a
    neutrino" (10.9 % each) against the tables (:mod:`.branching`)."""
    out: list[Said] = []
    for decay in said_decays(sentence):
        table = _table(decay.parent)
        if table is None:
            continue
        modes = _matching(decay, table)
        if not modes:
            continue
        share = sum(m.fraction for m in modes)
        largest = max(table.modes, key=lambda m: m.fraction)
        what = " + ".join(m.label for m in modes)
        source = "Standard Model prediction" if table.kind == "theory" else "PDG 2024"
        said_share = [v for v in qa.said_values(sentence) if v.checkable and (v.per is not None or v.unit is not None and v.unit.text == "%")
                      and _share_of(sentence, v, decay)]
        for v in said_share:
            if not qa.agrees(v, share, tolerance):
                out.append(Said("branching_ratio", sentence, f"{qa.said_name(v)}: {table.parent} → {what} is {share * 100:.3g} % ({source})"))
        if not said_share:
            if _TOP.search(sentence) and largest not in modes:
                out.append(Said("branching_ratio", sentence, f"{table.parent} → {what} is {share * 100:.3g} %; the most common decay is "
                                                             f"{largest.label} ({largest.fraction * 100:.3g} %, {source})"))
            elif _MOST.search(sentence[:decay.end]) and share < 0.5 and largest not in modes:
                out.append(Said("branching_ratio", sentence, f"{table.parent} → {what} is only {share * 100:.3g} % ({source}); most decay to "
                                                             f"{largest.label} ({largest.fraction * 100:.3g} %)"))
            elif _RARE.search(sentence) and share > 0.1:
                out.append(Said("branching_ratio", sentence, f"{table.parent} → {what} is not rare: {share * 100:.3g} % ({source})"))
    return out


# ----- bosons and what they do --------------------------------------------------------------------------

_BOSONS = {"gamma": "photon", "g": "gluon", "Z": "Z boson", "W+": "W boson", "W-": "W boson", "H": "Higgs boson"}
_FORCES = (("strong", "g"), ("electromagnetic", "gamma"), ("electro-magnetic", "gamma"), ("weak", "W+"))


def couples(boson: str, p: Particle) -> bool | None:
    """Whether the Standard Model has a tree-level vertex of ``boson`` (gamma, g, Z, W+, H)
    with ``p``; ``None`` when it is not a clear case (a composite particle's parts)."""
    if p.is_hadron:
        if boson in ("g", "W+", "W-", "Z"):
            return True
        if boson == "gamma":
            return True if p.charge != 0 else None
        return None
    key = p.key
    if boson == "g":
        return p.is_quark or key == "g"
    if boson == "gamma":
        return p.charge != 0
    if boson == "Z":
        return p.is_quark or p.is_lepton or key in ("W+", "W-", "H")
    if boson in ("W+", "W-"):
        return p.is_quark or p.is_lepton or key in ("gamma", "Z", "W+", "W-", "H")
    if boson == "H":
        return (p.is_quark or (p.is_lepton and p.charge != 0)) or key in ("W+", "W-", "Z", "H")
    return None


_COUPLE = re.compile(r"§(?P<b>\d+)§\s+(?:only\s+)?(?:bosons?\s+)?(?:couples?|coupling|interacts?|acts?|talks?)\s+(?:only\s+|directly\s+)?(?:to|with|on)\s+"
                     r"(?P<rest>[^.;]*)", re.IGNORECASE)
_FEEL = re.compile(r"§(?P<p>\d+)§\s+(?:also\s+|all\s+)?(?:feels?|experiences?|(?:are|is)\s+affected\s+by|interacts?\s+(?:via|through)|"
                   r"responds?\s+to)\s+(?:only\s+)?the\s+(?P<force>strong|weak|electromagnetic|electro-magnetic)\s+(?:force|interaction)", re.IGNORECASE)
_FLAVOUR = re.compile(r"§(?P<b>\d+)§[^§.;]{0,25}?\b(?:changes?|changing|switch(?:es)?|alters?)\s+(?:the\s+)?(?:\w+(?:'s)?\s+)?(?:flavou?r|type|"
                      r"identity|kind)", re.IGNORECASE)
_TURNS = re.compile(r"§(?P<b>\d+)§[^§.;]{0,25}?\b(?:turns?|converts?|changes?|transforms?)\s+(?:an?\s+|the\s+)?§(?P<x>\d+)§\s+(?:in)?to\s+"
                    r"(?:an?\s+|the\s+)?§(?P<y>\d+)§", re.IGNORECASE)
_EXCHANGE = re.compile(r"\b(?:exchang\w*|mediat\w*|virtual|carr(?:y|ies)\s+the\s+force|force\s+carrier|annihilat\w*\s+(?:in)?to|emit\w*|absorb\w*|"
                       r"through\s+an?|via\s+an?|by\s+exchanging|is\s+passed)\b", re.IGNORECASE)


def _boson_key(m: Mention) -> str | None:
    keys = [k for k in m.keys if k in _BOSONS]
    return keys[0] if keys and len(keys) == len(m.keys) else None


@_plain_only
def boson_claims(sentence: str, diagram_bosons: Sequence[str] | None = None) -> list[Said]:
    """``feynman_boson``: a boson said to couple to what it does not ("gluons couple to
    electrons", "the Higgs boson couples to photons": only through a loop), a particle said to
    feel a force it does not ("neutrinos feel the strong force"), flavour changed by a boson
    other than the W ("a photon changes the quark's flavour"), and in a ``feynman`` scene a
    boson named as exchanged that the diagram does not have (``diagram_bosons``)."""
    ms = mentions(sentence)
    if not ms:
        return []
    text = _placeholders(sentence, ms)
    out: list[Said] = []
    for m in _COUPLE.finditer(text):
        b = _boson_key(ms[int(m.group("b"))])
        if b is None:
            continue
        for k in re.findall(r"§(\d+)§", m.group("rest")):
            target = ms[int(k)]
            verdicts = [couples(b, p) for p in target.particles]
            if verdicts and all(v is False for v in verdicts):
                why = " (only through a loop of heavy particles: the top quark and the W)" if b == "H" and any(p.mass_mev == 0 for p in target.particles) else ""
                out.append(Said("feynman_boson", sentence, f"the {_BOSONS[b]} has no vertex with the {target.name}{why}: "
                                                           f"{_coupling_text(b)}"))
    for m in _FEEL.finditer(text):
        target = ms[int(m.group("p"))]
        force = m.group("force").lower().replace("-", "")
        b = dict(_FORCES)[force]
        verdicts = [couples(b, p) for p in target.particles]
        if force == "weak":
            verdicts = [couples("Z", p) or couples("W+", p) for p in target.particles]
        if verdicts and all(v is False for v in verdicts):
            out.append(Said("feynman_boson", sentence, f"the {force} force does not act on the {target.name}: {_coupling_text(b)}"))
    for m in _FLAVOUR.finditer(text):
        b = _boson_key(ms[int(m.group("b"))])
        if b is not None and b not in ("W+", "W-"):
            out.append(Said("feynman_boson", sentence, f"only the W boson changes a quark's or lepton's flavour (u ↔ d, e ↔ νₑ); the {_BOSONS[b]} "
                                                       f"keeps it — did you mean the W?"))
    for m in _TURNS.finditer(text):
        b = _boson_key(ms[int(m.group("b"))])
        x, y = ms[int(m.group("x"))], ms[int(m.group("y"))]
        if b is None or b in ("W+", "W-"):
            continue
        if {base(p) for p in x.particles}.isdisjoint({base(p) for p in y.particles}) and all(p.is_quark or p.is_lepton for p in x.particles + y.particles):
            out.append(Said("feynman_boson", sentence, f"the {_BOSONS[b]} cannot turn the {x.name} into the {y.name}: only the W boson changes "
                                                       f"flavour — did you mean the W?"))
    if diagram_bosons and _EXCHANGE.search(sentence):
        shown = set(diagram_bosons)
        for m in ms:
            b = _boson_key(m)
            if b is None:
                continue
            same = {"W+", "W-"} if b in ("W+", "W-") else {b}
            if not same & shown:
                names = sorted({_BOSONS[k] for k in shown})
                out.append(Said("feynman_boson", sentence, f"the {_BOSONS[b]} is named, but the diagram's bosons are: {', '.join(names)}"
                                                           f" — did you mean the {names[0]}?"))
    return out


def _coupling_text(boson: str) -> str:
    return {"g": "gluons couple to quarks and to gluons (colour)", "gamma": "photons couple to electric charge: quarks, charged leptons and W",
            "Z": "the Z couples to every quark and lepton, neutrinos too, and to W and H", "W+": "the W couples to every quark and lepton, changing flavour",
            "W-": "the W couples to every quark and lepton, changing flavour",
            "H": "the Higgs boson couples to mass: quarks, charged leptons, W, Z and itself"}[boson]


# ----- detector signatures ------------------------------------------------------------------------------

_PARTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("muon", re.compile(r"\bmuon\s+(?:chambers?|system|detectors?|spectrometer|stations?)\b|\bout(?:er|ermost)\s+(?:layers?|detectors?)\b",
                        re.IGNORECASE)),
    ("ecal", re.compile(r"\bECAL\b|\belectromagnetic\s+calorimeters?\b|\bEM\s+calorimeters?\b", re.IGNORECASE)),
    ("hcal", re.compile(r"\bHCAL\b|\bhadron(?:ic)?\s+calorimeters?\b", re.IGNORECASE)),
    ("calo", re.compile(r"\bcalorimeters?\b", re.IGNORECASE)),
    ("track", re.compile(r"\btracks?\b|\btracker\b|\btracking\s+(?:detector|system)\b|\bpixel\b|\bsilicon\b", re.IGNORECASE)),
    ("missing", re.compile(r"\bmissing\s+(?:transverse\s+)?(?:momentum|energy|p_?T)\b|\bescape\w*(?:\s+undetected)?\b|\binvisible\b|"
                           r"\bundetected\b|\bunseen\b", re.IGNORECASE)),
)
_ORDER = ("track", "ecal", "hcal", "muon")
_LEAVE = re.compile(r"\b(?:leaves?|leaving|makes?|produces?|gives?|creates?|deposits?|depositing|showers?|showering|"
                    r"(?:are|is)\s+(?:seen|detected|measured|recorded|visible|identified|caught)|shows?\s+up|lights?\s+up)\b", re.IGNORECASE)
_STOP = re.compile(r"\b(?:stops?|stopped|absorbed|ends?|dies?|stuck)\b", re.IGNORECASE)
_REACH = re.compile(r"\b(?:reach(?:es)?|gets?\s+to|makes?\s+it\s+to|arrives?\s+at)\b", re.IGNORECASE)
_PASS = re.compile(r"\b(?:pass(?:es)?\s+(?:right\s+)?through|crosses|traverses|penetrates|goes\s+through|punch(?:es)?\s+through)\b", re.IGNORECASE)
_CURVE = re.compile(r"\b(?:curves?|curving|bends?|bending|spirals?|curls?)\b", re.IGNORECASE)


def _signature_kind(p: Particle) -> str | None:
    from .detector import signature

    try:
        return signature(p)
    except Exception:  # noqa: BLE001 - quarks, bosons, short-lived particles: no signature of their own
        return None


def _stop_layer(kind: str) -> str | None:
    return {"electron": "ecal", "photon": "ecal", "charged_hadron": "hcal", "neutral_hadron": "hcal"}.get(kind)


_KIND_NAMES = {"electron": "an electron", "photon": "a photon", "muon": "a muon", "charged_hadron": "a charged hadron",
               "neutral_hadron": "a neutral hadron", "neutrino": "a neutrino"}
_PART_NAMES = {"track": "a track", "ecal": "the ECAL", "hcal": "the HCAL", "muon": "the muon chambers", "calo": "the calorimeters",
               "missing": "missing transverse momentum"}


@_plain_only
def signature_claims(sentence: str) -> list[Said]:
    """``detector_signature``: "photons leave tracks", "neutrinos are seen in the calorimeter",
    "muons stop in the ECAL", "neutrons curve in the field" against the signatures (electron:
    track + ECAL; photon: ECAL, no track; muon: track through everything + muon chambers;
    charged hadron: track + HCAL; neutral hadron: HCAL; neutrino: missing p_T)."""
    from .detector import SIGNATURES

    ms = mentions(sentence)
    out: list[Said] = []
    for k, m in enumerate(ms):
        kinds = {_signature_kind(p) for p in m.particles}
        if None in kinds or len(kinds) != 1:
            continue
        kind = kinds.pop()
        nxt = ms[k + 1].start if k + 1 < len(ms) else len(sentence)
        clause_end = re.search(r"[;:]|\bwhile\b|\bwhereas\b|\bunlike\b", sentence[m.end:])
        end = min(nxt, m.end + clause_end.start() if clause_end else len(sentence))
        rest = sentence[m.end:end]
        verb = next(((name, v) for name, pattern in (("pass", _PASS), ("stop", _STOP), ("reach", _REACH), ("curve", _CURVE), ("leave", _LEAVE))
                     if (v := pattern.search(rest)) is not None), None)
        if verb is None:
            continue
        name, v = verb
        after = rest[v.start():]
        parts = [(pn, pm.start()) for pn, pattern in _PARTS if (pm := pattern.search(after)) is not None]
        parts = [pn for pn, _ in sorted(parts, key=lambda x: x[1])]
        must, may, text = SIGNATURES[kind]
        who = _KIND_NAMES[kind]
        if name == "curve":
            if kind in ("photon", "neutral_hadron", "neutrino"):
                out.append(Said("detector_signature", sentence, f"{who} is neutral: it does not curve in the magnetic field ({text})"))
            continue
        if not parts:
            continue
        said_part = parts[0]
        part = ("ecal" if kind in ("electron", "photon") else "hcal") if said_part == "calo" else said_part
        if name == "leave":
            if part == "missing":
                if kind != "neutrino":
                    out.append(Said("detector_signature", sentence, f"{who} is seen ({text}); missing transverse momentum is the neutrinos' signature"))
            elif part not in must | may:
                where = "no track" if part == "track" else f"nothing in {_PART_NAMES[said_part]}"
                out.append(Said("detector_signature", sentence, f"{who} leaves {where}: {text}"))
        elif name == "stop":
            stop = _stop_layer(kind)
            if part in _ORDER and stop != part:
                where = f"stops in {_PART_NAMES[stop]}" if stop else ("passes through everything to the muon chambers" if kind == "muon" else
                                                                     "passes through everything unseen")
                out.append(Said("detector_signature", sentence, f"{who} does not stop in {_PART_NAMES[part]}: it {where} ({text})"))
        elif name in ("reach", "pass"):
            stop = _stop_layer(kind)
            if kind in ("neutrino", "muon") or part not in _ORDER:
                continue
            limit = _ORDER.index(stop) if stop else len(_ORDER)
            index = _ORDER.index(part)
            if index > limit or (name == "pass" and index >= limit):
                out.append(Said("detector_signature", sentence, f"{who} {'does not reach' if index > limit else 'stops in'} "
                                                                f"{_PART_NAMES[part if index > limit else stop]}: {text}"))
    return out


# ----- significance -----------------------------------------------------------------------------------

_SIGMA_AFTER = re.compile(r"^\s*-?\s*(?:σ|sigma|standard\s+deviations?)\b|^σ", re.IGNORECASE)
_SURE = re.compile(r"\b(?:sure|certain(?:ty)?|confiden(?:t|ce)\s+that|proof|proves?|probability\s+(?:that|of)\s+(?:the\s+|a\s+|it\s+)?(?:\w+\s+)?"
                   r"(?:is\s+real|exists|being\s+real|existing|is\s+right|is\s+true)|chance\s+(?:that\s+)?(?:the\s+|a\s+|it\s+|this\s+)?(?:\w+\s+){0,2}?"
                   r"(?:exists|is\s+real))\b", re.IGNORECASE)
_FLUKE = re.compile(r"\b(?:chance|probability|odds|likelihood)\b[^.;]{0,40}?\b(?:fluke|wrong|false(?:\s+alarm)?|mistake|mistaken|not\s+real|"
                    r"a\s+coincidence|an?\s+accident|noise|error)\b", re.IGNORECASE)
_SIG_CONTEXT = re.compile(r"σ|\bsigma\b|\bp[- ]?values?\b|\bstandard\s+deviations?\b|\bsignificance\b", re.IGNORECASE)
_RIGHT_WAY = re.compile(r"\bbackground\s+alone\b|\bif\s+there\s+(?:were|was|is)\s+no\b|\bwithout\s+(?:a|any|the)\b|\bno\s+(?:higgs|signal|particle)\b|"
                        r"\bassum\w+|\bbackground[- ]only\b|\bnothing\s+but\s+background\b|\bonly\s+background\b", re.IGNORECASE)
_CONVENTION = re.compile(r"\b(?:means?|convention|threshold|discovery|standard|rule|required|requires?|needs?|needed|called|criterion|bar|"
                         r"evidence|claim)\b", re.IGNORECASE)


def sigma_values(sentence: str) -> list[qa.SaidValue]:
    """The numbers said in σ ("five sigma", "5σ", "6.7 standard deviations")."""
    return [v for v in qa.said_values(sentence) if v.unit is None and v.per is None and _SIGMA_AFTER.match(sentence[v.end:])]


@_plain_only
def p_meaning_claims(sentence: str) -> list[Said]:
    """``significance_claim``: the p-value said as the chance the result is wrong or the
    particle exists ("five sigma means 99.99994 % sure the Higgs exists"); numbers said with
    σ that do not match it ("five sigma is one in a million")."""
    if not _SIG_CONTEXT.search(sentence):
        return []
    out: list[Said] = []
    if not _RIGHT_WAY.search(sentence) and (_SURE.search(sentence) or _FLUKE.search(sentence)):
        out.append(Said("significance_claim", sentence, "the p-value is the chance that background alone fluctuates this high, not the "
                                                        "probability that the result is wrong or that the particle exists: say \"if there "
                                                        "were no Higgs boson, background would fluctuate this high once in 3.5 million "
                                                        "tries\""))
    sigmas = [v for v in sigma_values(sentence) if v.checkable]
    if len(sigmas) == 1:
        from .spectrum import p_value

        z = sigmas[0].value
        one, two = p_value(z), 2 * p_value(z)
        for v in qa.said_values(sentence):
            if v is sigmas[0] or not v.checkable:
                continue
            if v.per is not None:
                if not (qa.agrees(v, one, 0.1) or qa.agrees(v, two, 0.1)):
                    out.append(Said("significance_claim", sentence, f"{qa.said_name(v)} for {z:g}σ: one-sided p = {one:.2g} (1 in "
                                                                    f"{1 / one:,.3g}), two-sided {two:.2g} (1 in {1 / two:,.3g})"))
            elif v.unit is not None and v.unit.text == "%" and v.value > 90:
                if not (qa.agrees(v, 1 - one, 0.0) or qa.agrees(v, 1 - two, 0.0)):
                    out.append(Said("significance_claim", sentence, f"{qa.said_name(v)} for {z:g}σ: 1 − p is {(1 - one) * 100:.7g} % one-sided, "
                                                                    f"{(1 - two) * 100:.7g} % two-sided"))
    return out


_SO_FAR = re.compile(r"\b(?:so\s+far|already|now|after\s+\w+|at\s+this\s+point|climbs?|grows?|rises?|creeps?|builds?|halfway|early|first)\b",
                     re.IGNORECASE)


@_plain_only
def sigma_claims(sentence: str, computed: Sequence[tuple[str, float]], tolerance: float = 0.5, upto: float | None = None) -> list[Said]:
    """``significance_claim`` in a ``mass_spectrum`` scene: a significance said for the bump
    ("the bump reaches five sigma") against what the scene computes (``computed``: (what,
    z) — the Asimov expectation with all the events, the likelihood-ratio fit); said while the
    data are still coming ("so far", "already", "climbs"), anything up to ``upto`` (the
    largest along the filling) is fine. The 5σ convention itself ("five sigma means…", "the
    discovery threshold") is not compared."""
    if not computed or _CONVENTION.search(sentence):
        return []
    growing = upto is not None and _SO_FAR.search(sentence) is not None
    out: list[Said] = []
    for v in sigma_values(sentence):
        if growing and v.value <= (upto or 0.0) + tolerance:
            continue
        if v.bound:
            if re.search(r"(?:more|greater|higher)\s+than|over|above|beyond|exceed|at\s+least", sentence[:v.start], re.IGNORECASE) and \
                    not any(z >= v.value for _, z in computed):
                out.append(Said("significance_claim", sentence, f"{qa.said_name(v)} σ: the scene computes " + ", ".join(f"{z:.1f}σ ({w})" for w, z in computed)))
            continue
        if not v.checkable:
            continue
        slack = tolerance + (0.5 if v.approx else 0.0) + v.resolution
        if not any(abs(v.value - z) <= slack for _, z in computed):
            out.append(Said("significance_claim", sentence, f"{qa.said_name(v)} σ: the scene computes " + ", ".join(f"{z:.1f}σ ({w})" for w, z in computed)))
    return out


# ----- kinematics -------------------------------------------------------------------------------------

_KIND_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("momentum", re.compile(r"\bmoment(?:um|a)\b|\bp\*|\bp_?T\b|\bp\s*=", re.IGNORECASE)),
    ("mass", re.compile(r"\binvariant\s+mass\b|\bmass\b|\bm_?inv\b", re.IGNORECASE)),
    ("energy", re.compile(r"\benerg(?:y|ies)\b|\bcarr(?:y|ies)\b|\bE\s*=", re.IGNORECASE)),
    ("q", re.compile(r"\bQ[- ]value\b|\breleased\b|\bkinetic\s+energy\b", re.IGNORECASE)),
    ("length", re.compile(r"\b(?:travels?|flies|fly|goes|decay\s+length|distance|before\s+(?:it\s+)?decay\w*|cτ|flight)\b", re.IGNORECASE)),
    ("angle", re.compile(r"\bangle\b|\bapart\b|\bopening\b", re.IGNORECASE)),
    ("gamma", re.compile(r"\bLorentz\s+factor\b|\bgamma\s+(?:factor|of|is)\b|γ\s*=", re.IGNORECASE)),
    ("threshold", re.compile(r"\bthreshold\b|\bat\s+least\b|\bneeds?\b|\bminimum\b", re.IGNORECASE)),
)
#: The kind of each value a ``kinematics`` scene computes (its ``calc_values`` names).
VALUE_KINDS = {"M": "mass", "m_inv": "mass", "p_star": "momentum", "p_lab": "momentum", "p_total": "momentum", "E1": "energy", "E2": "energy",
               "E_lab": "energy", "E_total": "energy", "Q": "q", "decay_length": "length", "opening_angle": "angle", "gamma": "gamma",
               "beta_gamma": "gamma"}
_VALUE_NAMES = {"M": "the parent's mass", "m_inv": "the invariant mass", "p_star": "the momentum p* in the rest frame", "p_lab": "the parent's momentum",
                "p_total": "the total momentum", "E1": "the first product's energy", "E2": "the second product's energy", "E_lab": "the parent's energy",
                "E_total": "the total energy", "Q": "the Q value", "decay_length": "the mean decay length βγcτ", "opening_angle": "the opening angle",
                "gamma": "γ", "beta_gamma": "βγ"}


def _value_dim_kind(v: qa.SaidValue) -> str | None:
    if v.unit is None:
        return "gamma"
    if v.dim in (ENERGY, MASS, MOMENTUM):
        return "energy-like"
    if v.dim == LENGTH:
        return "length"
    if v.dim == qa.DIMENSIONLESS and v.unit.text in ("deg", "°", "rad"):
        return "angle"
    return None


@_plain_only
def kinematics_claims(sentence: str, values: dict[str, tuple[float, str]], tolerance: float = 0.05) -> list[Said]:
    """``kinematics_number`` in a ``kinematics`` scene: a momentum, energy, invariant mass, Q
    value, decay length, opening angle or γ said in a sentence that names the quantity, against
    the scene's computed values (``calc_values``, the ``from_scene`` names); any value of the
    kinds named agreeing is fine."""
    named = [kind for kind, pattern in _KIND_WORDS if pattern.search(sentence)]
    if not named or not values:
        return []
    out: list[Said] = []
    for v in qa.said_values(sentence):
        if not v.checkable:
            continue
        dk = _value_dim_kind(v)
        if dk is None or dk == "gamma" and "gamma" not in named:
            continue
        if dk == "energy-like":
            kinds = [k for k in named if k in ("momentum", "mass", "energy", "q")]
            if v.dim == MOMENTUM:
                kinds = ["momentum"]
        else:
            kinds = [dk] if dk in named or dk in ("length", "angle") else []
        facts = [(name, si, unit) for name, (si, unit) in values.items() if VALUE_KINDS.get(name) in kinds]
        if not facts:
            continue
        ok = False
        for name, si, unit in facts:
            if dk == "energy-like":
                mev = si / _MEV_J * (_C**2 if VALUE_KINDS[name] == "mass" else _C if VALUE_KINDS[name] == "momentum" else 1.0)
                ok = ok or _close(v, mev, tolerance)
            elif dk == "angle":
                ok = ok or qa.agrees(v, si, tolerance)
            else:
                ok = ok or qa.agrees(v, si, tolerance)
        if ok:
            continue
        shown = []
        for name, si, unit in facts[:3]:
            if dk == "energy-like":
                mev = si / _MEV_J * (_C**2 if VALUE_KINDS[name] == "mass" else _C if VALUE_KINDS[name] == "momentum" else 1.0)
                suffix = {"momentum": "/c", "mass": "/c²"}.get(VALUE_KINDS[name], "")
                shown.append(f"{_VALUE_NAMES[name]} {energy_text(mev, 4)}{suffix}")
            elif dk == "angle":
                shown.append(f"{_VALUE_NAMES[name]} {math.degrees(si):.3g}°")
            elif dk == "length":
                shown.append(f"{_VALUE_NAMES[name]} {qa.in_unit_text(si, v.unit, 3)}")
            else:
                shown.append(f"{_VALUE_NAMES[name]} {si:.4g}")
        out.append(Said("kinematics_number", sentence, f"{qa.said_name(v)}: the scene computes {'; '.join(shown)}"))
    return out


@_plain_only
def flight_claims(sentence: str, tolerance: float = 0.1) -> list[Said]:
    """``kinematics_number`` anywhere: a decay length said with the particle's momentum or
    energy ("a 5 GeV muon travels about 30 km": βγcτ = p/m · cτ = 31 km), a dilated life said
    with γ ("at γ = 10 a muon lives 22 µs")."""
    ms = mentions(sentence)
    movers = [m for m in ms if all(not p.stable and p.lifetime is not None and p.mass_mev > 0 for p in m.particles)]
    if len(movers) != 1 or len({p.key.removeprefix("anti-").rstrip("+-") for p in movers[0].particles}) != 1:
        return []
    p = movers[0].particles[0]
    values = [v for v in qa.said_values(sentence) if v.checkable]
    energies = [v for v in values if mev_of(v) is not None]
    gammas = [v for v in values if v.unit is None and v.per is None and re.search(r"(?:γ|gamma|Lorentz\s+factor)\s*(?:=|of|is)?\s*$",
                                                                                 sentence[:v.start], re.IGNORECASE)]
    lengths = [v for v in values if v.dim == LENGTH]
    times = [v for v in values if v.dim == TIME]
    out: list[Said] = []
    tau = p.lifetime or 0.0
    ctau = tau * _C
    gamma = None
    if len(gammas) == 1:
        gamma = gammas[0].value
    elif len(energies) == 1:
        e = energies[0]
        mev = mev_of(e) or 0.0
        if e.dim == MOMENTUM or re.search(r"\bmomentum\b", sentence, re.IGNORECASE):
            gamma = math.hypot(mev, p.mass_mev) / p.mass_mev
        elif re.search(r"\bkinetic\b", sentence, re.IGNORECASE):
            gamma = (mev + p.mass_mev) / p.mass_mev
        elif mev > p.mass_mev:
            gamma = mev / p.mass_mev
    if gamma is None or gamma < 1:
        return []
    bg = math.sqrt(max(gamma * gamma - 1.0, 0.0))
    if len(lengths) == 1 and re.search(r"\b(?:travels?|flies|fly|goes|covers?|decay\s+length|before\s+(?:it\s+)?decay\w*|on\s+average|reach\w*)\b",
                                       sentence, re.IGNORECASE):
        v = lengths[0]
        if not qa.agrees(v, bg * ctau, tolerance):
            out.append(Said("kinematics_number", sentence, f"{qa.said_name(v)}: the {_short_name(p)}'s mean decay length is βγcτ = {bg:.3g} × "
                                                           f"{qa.in_unit_text(ctau, None, 3)} m = {qa.in_unit_text(bg * ctau, v.unit, 3)}"))
    if len(times) == 1 and _LIFE_WORDS.search(sentence):
        v = times[0]
        if not (qa.agrees(v, gamma * tau, tolerance) or qa.agrees(v, tau, tolerance)):
            out.append(Said("kinematics_number", sentence, f"{qa.said_name(v)}: the {_short_name(p)}'s dilated mean life is γτ = {gamma:.3g} × "
                                                           f"{time_text(tau, 4)} = {time_text(gamma * tau, 3)}"))
    return out


@_plain_only
def threshold_claims(sentence: str, tolerance: float = 0.05) -> list[Said]:
    """``kinematics_number``: a threshold said with a reaction written out ("p p → p p p p̄
    needs 6.5 GeV"): the least √s, the beam energy on a fixed target or its kinetic energy."""
    if not re.search(r"\bthreshold\b|\bat\s+least\b|\bneeds?\b|\bminimum\b|\brequires?\b", sentence, re.IGNORECASE):
        return []
    procs = [p for p in written_processes(sentence) if not p.is_decay]
    if len(procs) != 1:
        return []
    t = check(procs[0]).threshold
    if t.final_mev <= t.initial_mev:
        return []
    candidates = [("√s", t.sqrt_s_mev)] + ([("the beam energy on a target at rest", t.beam_mev)] if t.beam_mev else []) + \
                 ([("the beam's kinetic energy", t.beam_kinetic_mev)] if t.beam_kinetic_mev else [])
    out: list[Said] = []
    for v in qa.said_values(sentence):
        if mev_of(v) is None or v.in_range or v.dim == MOMENTUM:   # "at least 6.6 GeV" states the threshold
            continue
        if any(_close(v, mev, tolerance) for _, mev in candidates):
            continue
        listed = "; ".join(f"{name} {energy_text(mev, 4)}" for name, mev in candidates)
        out.append(Said("kinematics_number", sentence, f"{qa.said_name(v)} for the threshold of {procs[0]}: {listed}"))
    return out


# ----- simulated data -------------------------------------------------------------------------------------

_REAL_DATA = re.compile(r"\b(?:real|actual|measured|recorded|genuine)\s+(?:collision\s+|LHC\s+|experimental\s+)?(?:data|events?|collisions?)\b|"
                        r"\b(?:data|events?|collisions?)\s+(?:from|recorded\s+(?:by|at)|taken\s+(?:by|at)|collected\s+(?:by|at)|of|measured\s+(?:by|at))"
                        r"\s+(?:the\s+)?(?:LHC|ATLAS|CMS|LHCb|ALICE|Tevatron|CDF|D0|DØ|LEP|HERA|Belle|BaBar|experiments?)\b|"
                        r"\b(?:ATLAS|CMS|LHCb|ALICE|CDF|D0|DØ)(?:'s)?\s+(?:data|events?|measurement)\b", re.IGNORECASE)


@_plain_only
def real_data_claims(sentence: str) -> list[Said]:
    """``simulated_label``: narration calling a scene's simulated data real ("real collision
    data", "data from the LHC", "ATLAS data")."""
    if _REAL_DATA.search(sentence) is None:
        return []
    return [Said("simulated_label", sentence, "the scene's data are simulated (seeded), not a real experiment's: say \"simulated data\" — real "
                                              "spectra are the experiments' own (cite them, do not draw them)")]


__all__ = [
    "CATEGORIES", "EVERYWHERE", "PARTICLE_RULES", "QUARK_SCHEME_TOLERANCE", "VALUE_KINDS", "Mention", "Said", "SaidDecay", "base", "boson_claims",
    "branching_claims", "charge_claims", "conservation_claims", "couples", "flight_claims", "kinematics_claims", "lifetime_claims", "mass_claims",
    "mentions", "mev_of", "p_meaning_claims", "plain_sentences", "real_data_claims", "said_decays", "sentences", "si_of_mev", "sigma_claims",
    "sigma_values", "signature_claims", "spin_claims", "threshold_claims", "unit_styles", "written_processes",
]
