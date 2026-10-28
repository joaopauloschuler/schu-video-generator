"""Finding a particle by any common spelling (Phase Y, Step 237; DESIGN §99.2). No manim.

Accepted: the key (``pi+``, ``anti-nu_e``, ``K0_S``, ``J/psi``), names (``proton``, ``positron``,
``muon``), Unicode as printed (``π⁺``, ``ν̄ₑ``, ``ν̄_μ``, ``K̄⁰``, ``Σ̄⁻``, ``Δ⁺⁺``, ``Υ(1S)``, ``e⁺``)
and ASCII antiparticle markers (``anti-``, ``anti``, a trailing ``bar`` or ``~``: ``pbar``,
``nubar_e``, ``u~``). A bar keeps the antiparticle's own charge, as PDG writes it: ``Σ̄⁻`` (or
``anti-Sigma-``) is the antiparticle of the Σ⁺. Unknown names get a did-you-mean.
"""

from __future__ import annotations

import difflib
import unicodedata

from vidgen.errors import VidgenError

from .data import PARTICLES, Particle

_GREEK = {"π": "pi", "μ": "mu", "µ": "mu", "τ": "tau", "ν": "nu", "γ": "gamma", "Λ": "Lambda", "Σ": "Sigma", "Ξ": "Xi",
          "Ω": "Omega", "Δ": "Delta", "ψ": "psi", "Υ": "Upsilon", "η": "eta", "φ": "phi", "ϕ": "phi"}
_SIGNS = str.maketrans({"⁺": "+", "⁻": "-", "⁰": "0", "−": "-", "–": "-", "₀": "0", "ₑ": "_e", "ˢ": "S", "ₛ": "_S"})
#: Combining marks that make an antiparticle (macron, overline).
_BARS = ("̄", "̅")


def _aliases() -> dict[str, str]:
    table: dict[str, str] = {}
    for p in PARTICLES.values():
        for spelling in (p.key, *p.aliases):
            table.setdefault(spelling, p.key)
    return table


#: Every accepted ASCII spelling -> key (case-sensitive: ``b`` is the quark, ``B+`` the meson).
ALIASES: dict[str, str] = _aliases()


def _squash(text: str) -> str:
    return text.replace("_", "").replace(" ", "").replace("^", "").casefold()


def _folded() -> dict[str, set[str]]:
    folded: dict[str, set[str]] = {}
    for spelling, key in ALIASES.items():
        folded.setdefault(_squash(spelling), set()).add(key)
    return folded


_FOLDED = _folded()


def normalize(text: str) -> tuple[str, bool]:
    """The ASCII spelling of ``text`` and whether a bar (combining macron / overline) marks it
    as an antiparticle: ``ν̄ₑ`` -> ``('nu_e', True)``, ``π⁺`` -> ``('pi+', False)``."""
    decomposed = unicodedata.normalize("NFD", text.strip())
    anti = any(bar in decomposed for bar in _BARS)
    for bar in _BARS:
        decomposed = decomposed.replace(bar, "")
    out = "".join(_GREEK.get(ch, ch) for ch in unicodedata.normalize("NFC", decomposed))
    return out.translate(_SIGNS), anti


def _direct(spelling: str) -> str | None:
    if spelling in ALIASES:
        return ALIASES[spelling]
    keys = _FOLDED.get(_squash(spelling), set())
    return next(iter(keys)) if len(keys) == 1 else None


def _with_anti(spelling: str) -> str | None:
    """The key of ``spelling`` read as an antiparticle: ``anti-`` + it when that is a key (the
    antiparticle's own charge), else the antiparticle of what it names."""
    for candidate in ("anti-" + spelling,):
        if candidate in ALIASES:
            return ALIASES[candidate]
    key = _direct(spelling)
    return PARTICLES[key].antiparticle if key is not None else None


def find_key(text: str) -> str | None:
    """The key of the particle ``text`` names, or ``None``."""
    spelling, anti = normalize(text)
    if not spelling:
        return None
    if anti:
        return _with_anti(spelling)
    key = _direct(spelling)
    if key is not None:
        return key
    for prefix in ("anti-", "anti_", "anti"):
        if spelling.startswith(prefix) and len(spelling) > len(prefix):
            found = _with_anti(spelling[len(prefix):])
            if found is not None:
                return found
    for suffix in ("-bar", "_bar", "bar", "~"):
        if spelling.endswith(suffix) and len(spelling) > len(suffix):
            found = _with_anti(spelling[: -len(suffix)])
            if found is not None:
                return found
    if spelling.startswith("nubar"):
        return _with_anti("nu" + spelling[5:])
    return None


def suggestions(text: str, n: int = 3) -> list[str]:
    """Close spellings of ``text`` among the accepted ones (for did-you-mean)."""
    spelling, _ = normalize(text)
    found = difflib.get_close_matches(spelling, list(ALIASES), n=n, cutoff=0.6)
    folded = difflib.get_close_matches(_squash(spelling), list(_FOLDED), n=n, cutoff=0.6)
    out = list(dict.fromkeys([ALIASES[s] for s in found] + [k for f in folded for k in sorted(_FOLDED[f])]))
    return out[:n]


def particle(text: str) -> Particle:
    """The particle ``text`` names (any accepted spelling); raises :class:`VidgenError` with a
    did-you-mean otherwise."""
    key = find_key(text)
    if key is not None:
        return PARTICLES[key]
    close = suggestions(text)
    hint = f"; did you mean {' or '.join(repr(k) for k in close)}?" if close else ""
    raise VidgenError(f"unknown particle '{text}'{hint} (names like e-, mu+, nu_e, anti-nu_mu, pi0, K+, K0_S, p, anti-p, "
                      f"Lambda, Sigma+, J/psi, W+, Z, H, gamma, g, u, anti-u; Unicode such as π⁺, ν̄ₑ, Σ̄⁻ works too)")


def antiparticle(p: Particle | str) -> Particle:
    """The antiparticle of ``p`` (a particle or any spelling)."""
    p = particle(p) if isinstance(p, str) else p
    return PARTICLES[p.antiparticle]


__all__ = ["ALIASES", "antiparticle", "find_key", "normalize", "particle", "suggestions"]
