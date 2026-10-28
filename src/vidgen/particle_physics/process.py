"""Reactions and decays written as text (Phase Y, Step 237; DESIGN §99.2). No manim.

``"n -> p e- anti-nu_e"``, ``"mu- → e- ν̄ₑ ν_μ"``, ``"pi0 -> gamma gamma"``, ``"p p -> p p p pbar"``,
``"H -> Z Z*"``: one arrow (``->``, ``→``, ``=>``, ``⟶``), particles separated by spaces (a ``+``
between them, commas and a run such as ``e+e-`` are fine). A trailing ``*`` marks an off-shell
(virtual) boson or fermion (``Z*``, ``W*``): its mass is not fixed, so it does not count in the
energy check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vidgen.errors import VidgenError

from .data import Particle
from .names import find_key, particle

_ARROW = re.compile(r"\s*(?:-->|->|=>|→|⟶|⇒)\s*")
#: Families a ``*`` (off-shell) may mark.
OFF_SHELL_FAMILIES = ("quark", "lepton", "gauge boson", "scalar boson")


@dataclass(frozen=True)
class Leg:
    """One particle of a process; ``off_shell``: written with ``*`` (virtual)."""

    particle: Particle
    off_shell: bool = False

    @property
    def symbol(self) -> str:
        return self.particle.symbol + ("*" if self.off_shell else "")

    @property
    def key(self) -> str:
        return self.particle.key + ("*" if self.off_shell else "")


@dataclass(frozen=True)
class Process:
    """A decay (one particle before the arrow) or a reaction (two or more)."""

    initial: tuple[Leg, ...]
    final: tuple[Leg, ...]

    @property
    def is_decay(self) -> bool:
        return len(self.initial) == 1

    @property
    def legs(self) -> tuple[Leg, ...]:
        return self.initial + self.final

    def particles(self, side: str = "both") -> list[Particle]:
        """The particles of ``initial``, ``final`` or ``both`` sides."""
        legs = {"initial": self.initial, "final": self.final}.get(side, self.legs)
        return [leg.particle for leg in legs]

    def text(self, style: str = "unicode") -> str:
        """``n → p e⁻ ν̄ₑ`` (``unicode``), ``n -> p e- anti-nu_e`` (``ascii``) or TeX."""
        if style == "ascii":
            return " ".join(leg.key for leg in self.initial) + " -> " + " ".join(leg.key for leg in self.final)
        if style == "tex":
            def tex(leg: Leg) -> str:
                return leg.particle.tex + ("^*" if leg.off_shell and "^" not in leg.particle.tex else "")

            return " ".join(tex(leg) for leg in self.initial) + r" \to " + " ".join(tex(leg) for leg in self.final)
        return " ".join(leg.symbol for leg in self.initial) + " → " + " ".join(leg.symbol for leg in self.final)

    def __str__(self) -> str:
        return self.text()


def _split_run(token: str) -> list[str] | None:
    """A run of particles written together (``e+e-``, ``μ+μ-``) split greedily into known
    names, or ``None``."""
    if find_key(token) is not None:
        return [token]
    for cut in range(len(token) - 1, 0, -1):
        head = token[:cut]
        if find_key(head) is not None:
            rest = _split_run(token[cut:])
            if rest is not None:
                return [head, *rest]
    return None


def _legs(side: str, text: str, where: str) -> tuple[Leg, ...]:
    tokens = [t for t in re.split(r"[\s,]+", side.strip()) if t and t != "+"]
    if not tokens:
        raise VidgenError(f"process '{text}': nothing {where} the arrow")
    legs: list[Leg] = []
    for token in tokens:
        off = token.endswith("*") and len(token) > 1
        name = token[:-1] if off else token
        parts = _split_run(name) if find_key(name) is None else [name]
        if parts is None:
            if off:
                raise VidgenError(f"process '{text}': unknown particle '{token}': excited hadrons (K*, Σ*...) are not in the particle "
                                  f"table; '*' marks an off-shell (virtual) boson or fermion such as Z* or W*")
            particle(name)   # raises with a did-you-mean
            parts = [name]
        for i, part in enumerate(parts):
            p = particle(part)
            star = off and i == len(parts) - 1
            if star and p.family not in OFF_SHELL_FAMILIES:
                raise VidgenError(f"process '{text}': '{token}': '*' marks an off-shell (virtual) boson or fermion such as Z* or W*; "
                                  f"excited hadrons (K*, Σ*...) are not in the particle table")
            legs.append(Leg(p, star))
    return tuple(legs)


def parse_process(text: str) -> Process:
    """Parse ``"n -> p e- anti-nu_e"`` into a :class:`Process`; raises :class:`VidgenError`
    naming what is wrong (no arrow, two arrows, an unknown particle with a did-you-mean)."""
    if not isinstance(text, str) or not text.strip():
        raise VidgenError("a process needs text such as 'n -> p e- anti-nu_e'")
    parts = _ARROW.split(text.strip())
    if len(parts) != 2:
        found = "no arrow" if len(parts) == 1 else f"{len(parts) - 1} arrows"
        raise VidgenError(f"process '{text}': write one arrow between the particles before and after ('n -> p e- anti-nu_e'); found {found}")
    initial = _legs(parts[0], text, "before")
    final = _legs(parts[1], text, "after")
    return Process(initial, final)


def as_process(process: Process | str) -> Process:
    """A :class:`Process` from itself or its text."""
    return process if isinstance(process, Process) else parse_process(process)


__all__ = ["OFF_SHELL_FAMILIES", "Leg", "Process", "as_process", "parse_process"]
