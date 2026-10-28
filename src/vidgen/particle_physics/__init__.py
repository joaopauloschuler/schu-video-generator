"""Particle physics without manim (Phase Y, DESIGN §99): the Standard Model's particles and the
common hadrons with PDG 2024 values (:mod:`.data`), names in ASCII and Unicode with did-you-mean
(:mod:`.names`), reactions and decays as text (:mod:`.process`), the conservation checker
(:mod:`.conservation`) and the Standard Model chart's cells and couplings (:mod:`.chart`).
Exported by ``vidgen.api`` as the module ``particle_physics``."""

from .chart import CELLS, COUPLINGS, GRID, GROUPS, ROWS, SHORT_LABELS, Cell, Coupling, cell
from .conservation import CONSERVATION_TABLE, INTERACTIONS, Check, Threshold, Verdict, allowed, check
from .data import (
    EDITION,
    ELEMENTARY,
    FLAVOUR_NAMES,
    FLAVOURS,
    HADRONS,
    HBAR_MEV_S,
    LEPTON_FAMILIES,
    PARTICLES,
    QUARK_NUMBERS,
    SOURCE,
    Particle,
    content_baryon,
    content_charge,
    content_flavour,
    energy_text,
    fraction_text,
    particle_problems,
    time_text,
)
from .names import ALIASES, antiparticle, find_key, normalize, particle, suggestions
from .process import Leg, Process, as_process, parse_process

__all__ = [
    "ALIASES",
    "CELLS",
    "CONSERVATION_TABLE",
    "COUPLINGS",
    "EDITION",
    "ELEMENTARY",
    "FLAVOURS",
    "FLAVOUR_NAMES",
    "GRID",
    "GROUPS",
    "HADRONS",
    "HBAR_MEV_S",
    "INTERACTIONS",
    "LEPTON_FAMILIES",
    "PARTICLES",
    "QUARK_NUMBERS",
    "ROWS",
    "SHORT_LABELS",
    "SOURCE",
    "Cell",
    "Check",
    "Coupling",
    "Leg",
    "Particle",
    "Process",
    "Threshold",
    "Verdict",
    "allowed",
    "antiparticle",
    "as_process",
    "cell",
    "check",
    "content_baryon",
    "content_charge",
    "content_flavour",
    "energy_text",
    "find_key",
    "fraction_text",
    "normalize",
    "parse_process",
    "particle",
    "particle_problems",
    "suggestions",
    "time_text",
]
