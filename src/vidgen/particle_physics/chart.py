"""The Standard Model chart as data (Phase Y, Step 237; DESIGN §99.4): which particle sits in
which cell in the wide (16:9) and tall (9:16) arrangements, the groups, the text of each cell
for particles and antiparticles, and which bosons couple to which particles. No manim; the
``standard_model`` scene draws it.

Wide: the classic grid — three columns of fermions (generations I–III; rows up-type quarks,
down-type quarks, charged leptons, neutrinos), a column of gauge bosons (g, γ, Z, W) and the
Higgs boson. Tall: the same fermion grid, the bosons in two rows under it (g γ Z / W H).
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import PARTICLES, Particle, fraction_text

GROUPS = ("quarks", "leptons", "gauge_bosons", "scalar_bosons")
#: Rows of the fermion block, top to bottom.
ROWS = ("up_type", "down_type", "charged_leptons", "neutrinos")


@dataclass(frozen=True)
class Cell:
    """One cell: ``key`` (the particle shown), ``target`` (its target label: ``u``, ``photon``),
    other target labels, group, fermion row (``None`` for bosons), generation, and the grid
    position (column, row) in the wide and the tall arrangement."""

    key: str
    target: str
    names: tuple[str, ...]
    group: str
    row: str | None
    generation: int | None
    wide: tuple[int, int]
    tall: tuple[int, int]
    #: Short name under the symbol (particle, antiparticle).
    label: tuple[str, str]
    #: Symbol in Pango markup (particle, antiparticle).
    symbol: tuple[str, str]
    #: The antiparticle's symbol carries a bar over its first letter (ū, ν̄ₑ), drawn by the scene
    #: (a combining macron sits badly on Greek letters).
    bar: bool = False

    @property
    def particle(self) -> Particle:
        return PARTICLES[self.key]

    @property
    def anti(self) -> Particle:
        return PARTICLES[self.particle.antiparticle]

    @property
    def is_fermion(self) -> bool:
        return self.group in ("quarks", "leptons")

    def mass_text(self) -> str:
        """The mass as the chart shows it: a few significant figures (``1.27 GeV``, ``< 0.8 eV``)."""
        p = self.particle
        digits = {"u": 3, "d": 3, "s": 3, "c": 3, "b": 3, "e-": 3}.get(self.key, 4)
        unit = "GeV" if p.mass_mev >= 1000 else None
        return p.mass_text(digits, unit)

    def charge_text(self, anti: bool = False) -> str:
        """``2/3``; the W cell shows ``±1``; ``anti``: the antiparticle's."""
        if self.key == "W+":
            return "±1"
        return fraction_text(self.anti.charge if anti else self.particle.charge)

    def spin_text(self) -> str:
        return fraction_text(self.particle.spin)


def _fermions() -> list[Cell]:
    cells = []
    table = [
        ("up_type", "quarks", [("u", "up", "anti-up"), ("c", "charm", "anti-charm"), ("t", "top", "anti-top")]),
        ("down_type", "quarks", [("d", "down", "anti-down"), ("s", "strange", "anti-strange"), ("b", "bottom", "anti-bottom")]),
        ("charged_leptons", "leptons", [("e-", "electron", "positron"), ("mu-", "muon", "antimuon"), ("tau-", "tau", "antitau")]),
        ("neutrinos", "leptons", [("nu_e", "electron neutrino", "electron antineutrino"), ("nu_mu", "muon neutrino", "muon antineutrino"),
                                  ("nu_tau", "tau neutrino", "tau antineutrino")]),
    ]
    marks = {"e-": ("e", "e<sup>+</sup>"), "mu-": ("μ", "μ<sup>+</sup>"), "tau-": ("τ", "τ<sup>+</sup>")}
    for r, (row, group, entries) in enumerate(table):
        for g, (key, name, anti_name) in enumerate(entries):
            p = PARTICLES[key]
            target = key.rstrip("-")
            symbol = marks.get(key, (p.markup, p.markup))
            words = name.split()
            names = tuple(dict.fromkeys([name.replace(" ", "_")] + ([words[0]] if len(words) == 1 else [])))
            cells.append(Cell(key, target, tuple(n for n in names if n != target), group, row, g + 1, (g, r), (g, r), (name, anti_name), symbol,
                              bar=key not in marks))
    return cells


def _bosons() -> list[Cell]:
    return [
        Cell("g", "g", ("gluon",), "gauge_bosons", None, None, (3, 0), (0, 4), ("gluon", "gluon"), ("g", "g")),
        Cell("gamma", "photon", ("gamma",), "gauge_bosons", None, None, (3, 1), (1, 4), ("photon", "photon"), ("γ", "γ")),
        Cell("Z", "Z", ("Z_boson",), "gauge_bosons", None, None, (3, 2), (2, 4), ("Z boson", "Z boson"), ("Z", "Z")),
        Cell("W+", "W", ("W_boson",), "gauge_bosons", None, None, (3, 3), (0, 5), ("W boson", "W boson"), ("W", "W")),
        Cell("H", "H", ("higgs", "Higgs"), "scalar_bosons", None, None, (4, 0), (1, 5), ("Higgs", "Higgs"), ("H", "H")),
    ]


#: Shorter names for narrow cells, shortest last (the symbol's subscript still tells them apart).
SHORT_LABELS = {
    "electron neutrino": ("e-neutrino", "neutrino"), "muon neutrino": ("μ-neutrino", "neutrino"), "tau neutrino": ("τ-neutrino", "neutrino"),
    "electron antineutrino": ("e-antineutrino", "antineutrino"), "muon antineutrino": ("μ-antineutrino", "antineutrino"),
    "tau antineutrino": ("τ-antineutrino", "antineutrino"),
}

#: The chart's cells: fermions by row and generation, then g, γ, Z, W, H.
CELLS: tuple[Cell, ...] = tuple(_fermions() + _bosons())
#: Grid size (columns, rows) of each arrangement.
GRID = {"wide": (5, 4), "tall": (3, 6)}


def cell(target: str) -> Cell:
    """The cell whose target label (or other name) is ``target``."""
    for c in CELLS:
        if target == c.target or target in c.names:
            return c
    raise KeyError(target)


@dataclass(frozen=True)
class Coupling:
    """Which particles a boson couples to (``fermions``, ``bosons`` as cell targets) and why."""

    boson: str
    fermions: tuple[str, ...]
    bosons: tuple[str, ...]
    reason: str


def _targets(*rows: str) -> tuple[str, ...]:
    return tuple(c.target for c in CELLS if c.row in rows)


#: The Standard Model's interaction vertices, by boson (tree level).
COUPLINGS: dict[str, Coupling] = {
    "g": Coupling("g", _targets("up_type", "down_type"), ("g",), "colour: the quarks and the gluons themselves"),
    "photon": Coupling("photon", _targets("up_type", "down_type", "charged_leptons"), ("W",), "electric charge: quarks, charged leptons, W"),
    "Z": Coupling("Z", _targets(*ROWS), ("W", "H"), "every quark and lepton (neutrinos too), W and H"),
    "W": Coupling("W", _targets(*ROWS), ("photon", "Z", "W", "H"), "every quark and lepton, changing its flavour (u ↔ d, e ↔ νₑ); γ, Z, W, H"),
    "H": Coupling("H", _targets("up_type", "down_type", "charged_leptons"), ("W", "Z", "H"),
                  "mass: quarks, charged leptons, W, Z and itself (stronger for heavier)"),
}


__all__ = ["CELLS", "COUPLINGS", "GRID", "GROUPS", "ROWS", "SHORT_LABELS", "Cell", "Coupling", "cell"]
