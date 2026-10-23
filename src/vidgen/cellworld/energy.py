"""Energy metabolism as data and rules (DESIGN.md §95.13; no manim): glycolysis (ten steps,
investment and payoff phases, in the cytosol), the link reaction (pyruvate into the matrix,
pyruvate dehydrogenase), the citric acid cycle (eight steps per acetyl-CoA), the mitochondrial
electron transport chain with ATP synthase, and the light reactions of photosynthesis in the
thylakoid membrane — the metabolites, enzymes, cofactors and their tallies, the components of
the chains with the protons each moves per two electrons, and the checks an author's choices
must pass (the membrane a chain sits in, the side protons are pumped to, the order of the
components, the compartment a pathway runs in). Textbook consensus (Berg/Stryer, Lehninger,
Alberts ch. 14)."""

from __future__ import annotations

from dataclasses import dataclass, field

from vidgen.errors import VidgenError

from .model import did_you_mean

PROCESSES = ("glycolysis", "link_reaction", "tca", "etc", "light_reactions")
PROCESS_ALIASES = {"krebs": "tca", "citric_acid_cycle": "tca", "krebs_cycle": "tca", "electron_transport_chain": "etc",
                   "respiratory_chain": "etc", "oxidative_phosphorylation": "etc", "photosynthesis": "light_reactions",
                   "light": "light_reactions", "pdh": "link_reaction", "link": "link_reaction", "pyruvate_oxidation": "link_reaction"}
PROCESS_TITLES = {"glycolysis": "Glycolysis", "link_reaction": "Pyruvate oxidation", "tca": "The citric acid cycle",
                  "etc": "The electron transport chain", "light_reactions": "The light reactions"}


def process_key(name: str) -> str:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    key = PROCESS_ALIASES.get(key, key)
    if key not in PROCESSES:
        raise VidgenError(f"process: unknown '{name}'{did_you_mean(key, list(PROCESSES) + list(PROCESS_ALIASES))} "
                          f"({', '.join(PROCESSES)})")
    return key


@dataclass(frozen=True)
class Metabolite:
    """A node of a pathway: ``key``, its name (markup), a short form, carbons per molecule."""

    key: str
    markup: str
    short: str
    carbons: int = 0
    note: str = ""


@dataclass(frozen=True)
class Step:
    """A reaction from ``source`` to ``target`` by ``enzyme`` (markup); ``inputs`` and
    ``outputs`` are the cofactors and side products it uses and makes (markup, count per
    occurrence); ``tally`` adds to the counters (ATP, NADH, FADH2, GTP, CO2, H2O); ``times``
    per glucose (2 from the cleavage of fructose 1,6-bisphosphate on); ``phase`` (investment,
    payoff) and ``compartment``."""

    key: str
    enzyme: str
    source: str
    target: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    tally: tuple[tuple[str, int], ...] = ()
    times: int = 1
    phase: str = ""
    note: str = ""
    aliases: tuple[str, ...] = ()


M = Metabolite
GLYCOLYSIS_NODES = (
    M("glucose", "glucose", "glucose", 6), M("g6p", "glucose 6-phosphate", "G6P", 6), M("f6p", "fructose 6-phosphate", "F6P", 6),
    M("f16bp", "fructose 1,6-bisphosphate", "F1,6BP", 6),
    M("dhap_gap", "DHAP + glyceraldehyde 3-P", "DHAP + GAP", 3, "two trioses"),
    M("gap", "2 glyceraldehyde 3-phosphate", "2 GAP", 3),
    M("bpg", "2 1,3-bisphosphoglycerate", "2 1,3BPG", 3), M("pg3", "2 3-phosphoglycerate", "2 3PG", 3),
    M("pg2", "2 2-phosphoglycerate", "2 2PG", 3), M("pep", "2 phosphoenolpyruvate", "2 PEP", 3), M("pyruvate", "2 pyruvate", "2 pyruvate", 3),
)
GLYCOLYSIS_STEPS = (
    Step("hexokinase", "hexokinase", "glucose", "g6p", ("ATP",), ("ADP",), (("ATP", -1),), 1, "investment",
         "traps glucose in the cell", ("hk",)),
    Step("pgi", "phosphoglucose isomerase", "g6p", "f6p", phase="investment", aliases=("phosphoglucose_isomerase",)),
    Step("pfk1", "phosphofructokinase-1", "f6p", "f16bp", ("ATP",), ("ADP",), (("ATP", -1),), 1, "investment",
         "the committed, rate-limiting step (phosphofructokinase-1)", ("pfk", "phosphofructokinase")),
    Step("aldolase", "aldolase", "f16bp", "dhap_gap", phase="investment"),
    Step("tpi", "triose phosphate isomerase", "dhap_gap", "gap", phase="investment", aliases=("triose_phosphate_isomerase",)),
    Step("gapdh", "GAP dehydrogenase", "gap", "bpg", ("NAD<sup>+</sup> + P<sub>i</sub>",), ("NADH + H<sup>+</sup>",), (("NADH", 1),), 2, "payoff",
         "an oxidation: NAD⁺ takes a hydride", ("glyceraldehyde_3_phosphate_dehydrogenase",)),
    Step("pgk", "phosphoglycerate kinase", "bpg", "pg3", ("ADP",), ("ATP",), (("ATP", 1),), 2, "payoff",
         "substrate-level phosphorylation", ("phosphoglycerate_kinase",)),
    Step("pgm", "phosphoglycerate mutase", "pg3", "pg2", times=2, phase="payoff", aliases=("phosphoglycerate_mutase",)),
    Step("enolase", "enolase", "pg2", "pep", (), ("H<sub>2</sub>O",), (("H2O", 1),), 2, "payoff"),
    Step("pyruvate_kinase", "pyruvate kinase", "pep", "pyruvate", ("ADP",), ("ATP",), (("ATP", 1),), 2, "payoff",
         "substrate-level phosphorylation", ("pk",)),
)
LINK_NODES = (M("pyruvate_m", "2 pyruvate (matrix)", "2 pyruvate", 3), M("acetyl_coa", "2 acetyl-CoA", "2 acetyl-CoA", 2))
LINK_STEPS = (
    Step("mpc", "pyruvate carrier (MPC)", "pyruvate", "pyruvate_m", phase="link", note="through the inner membrane, with an H⁺",
         aliases=("mitochondrial_pyruvate_carrier",)),
    Step("pdh", "pyruvate dehydrogenase", "pyruvate_m", "acetyl_coa", ("NAD<sup>+</sup> + CoA",), ("NADH", "CO<sub>2</sub>"),
         (("NADH", 1), ("CO2", 1)), 2, "link", "oxidative decarboxylation (TPP, lipoate, FAD)", ("pyruvate_dehydrogenase",)),
)
TCA_NODES = (
    M("oxaloacetate", "oxaloacetate", "OAA", 4), M("citrate", "citrate", "Cit", 6), M("isocitrate", "isocitrate", "Icit", 6),
    M("akg", "α-ketoglutarate", "αKG", 5), M("succinyl_coa", "succinyl-CoA", "Suc-CoA", 4), M("succinate", "succinate", "Suc", 4),
    M("fumarate", "fumarate", "Fum", 4), M("malate", "malate", "Mal", 4),
)
TCA_STEPS = (
    Step("citrate_synthase", "citrate synthase", "oxaloacetate", "citrate", ("acetyl-CoA", "H<sub>2</sub>O"), ("CoA",),
         note="acetyl-CoA (2 C) joins oxaloacetate (4 C)"),
    Step("aconitase", "aconitase", "citrate", "isocitrate"),
    Step("idh", "isocitrate dehydrogenase", "isocitrate", "akg", ("NAD<sup>+</sup>",), ("NADH", "CO<sub>2</sub>"),
         (("NADH", 1), ("CO2", 1)), aliases=("isocitrate_dehydrogenase",)),
    Step("akgdh", "α-KG dehydrogenase", "akg", "succinyl_coa", ("NAD<sup>+</sup> + CoA",), ("NADH", "CO<sub>2</sub>"),
         (("NADH", 1), ("CO2", 1)), aliases=("alpha_ketoglutarate_dehydrogenase", "ogdh")),
    Step("scs", "succinyl-CoA synthetase", "succinyl_coa", "succinate", ("GDP + P<sub>i</sub>",), ("GTP", "CoA"), (("GTP", 1),),
         note="substrate-level phosphorylation (GTP, or ATP in some tissues)", aliases=("succinyl_coa_synthetase",)),
    Step("sdh", "succinate dehydrogenase", "succinate", "fumarate", ("FAD",), ("FADH<sub>2</sub>",), (("FADH2", 1),),
         note="complex II of the electron transport chain, in the inner membrane", aliases=("succinate_dehydrogenase", "complex_ii")),
    Step("fumarase", "fumarase", "fumarate", "malate", ("H<sub>2</sub>O",), ()),
    Step("mdh", "malate dehydrogenase", "malate", "oxaloacetate", ("NAD<sup>+</sup>",), ("NADH",), (("NADH", 1),),
         aliases=("malate_dehydrogenase",)),
)
TCA_TOTALS = {"NADH": 3, "FADH2": 1, "GTP": 1, "CO2": 2}
#: The enzymes' usual abbreviations (drawn where the full names do not fit).
ENZYME_SHORT = {"hexokinase": "HK", "pgi": "PGI", "pfk1": "PFK-1", "aldolase": "aldolase", "tpi": "TPI", "gapdh": "GAPDH",
                "pgk": "PGK", "pgm": "PGM", "enolase": "enolase", "pyruvate_kinase": "PK", "mpc": "MPC", "pdh": "PDH",
                "citrate_synthase": "CS", "aconitase": "aconitase", "idh": "IDH", "akgdh": "α-KGDH", "scs": "SCS", "sdh": "SDH",
                "fumarase": "fumarase", "mdh": "MDH"}


@dataclass(frozen=True)
class Component:
    """A component of a chain in a membrane: ``key``, its short label (markup) and name,
    where it sits (``span``: across the membrane; ``n`` / ``p``: on that side's face;
    ``pool``: a quinone pool in the bilayer), its drawn width (in membrane thicknesses), the
    protons it takes from the N side and gives to the P side per two electrons (``takes``,
    ``gives``), those it consumes on the N side (``consumes``: water, NADPH), light it absorbs
    (``photon``), what it does (``reaction`` markup at ``reaction_side``)."""

    key: str
    label: str
    name: str
    span: str
    width: float
    takes: int = 0
    gives: int = 0
    consumes: int = 0
    photon: bool = False
    reaction: str = ""
    reaction_side: str = "n"
    note: str = ""
    aliases: tuple[str, ...] = ()


ETC_COMPONENTS = (
    Component("complex_i", "I", "complex I (NADH dehydrogenase)", "span", 2.6, 4, 4, reaction="NADH → NAD<sup>+</sup> + H<sup>+</sup>",
              note="NADH gives 2 e⁻ to FMN and Fe–S clusters; 4 H⁺ pumped", aliases=("nadh_dehydrogenase", "i")),
    Component("complex_ii", "II", "complex II (succinate dehydrogenase)", "n", 1.5, reaction="succinate → fumarate",
              note="FADH₂ stays bound; no protons pumped", aliases=("succinate_dehydrogenase", "sdh", "ii")),
    Component("coq", "Q", "ubiquinone (coenzyme Q)", "pool", 0.9, note="mobile in the bilayer: Q + 2 e⁻ + 2 H⁺ → QH₂",
              aliases=("q", "ubiquinone", "coenzyme_q")),
    Component("complex_iii", "III", "complex III (cytochrome bc<sub>1</sub>)", "span", 2.1, 2, 4,
              note="the Q cycle: 4 H⁺ to the intermembrane space per 2 e⁻", aliases=("cytochrome_bc1", "bc1", "iii")),
    Component("cyt_c", "c", "cytochrome c", "p", 0.8, note="a mobile carrier on the intermembrane face, one e⁻ at a time",
              aliases=("cytochrome_c", "c")),
    Component("complex_iv", "IV", "complex IV (cytochrome c oxidase)", "span", 2.0, 2, 2, 2,
              reaction="½O<sub>2</sub> + 2H<sup>+</sup> → H<sub>2</sub>O", note="O₂ reduced to water; 2 H⁺ pumped per 2 e⁻",
              aliases=("cytochrome_c_oxidase", "iv")),
    Component("atp_synthase", "ATP synthase", "ATP synthase (F<sub>o</sub>F<sub>1</sub>)", "synthase", 2.4,
              reaction="ADP + P<sub>i</sub> → ATP", note="H⁺ flowing back through Fₒ turn the rotor; F₁ makes ATP",
              aliases=("complex_v", "f0f1", "fof1", "v")),
)
LIGHT_COMPONENTS = (
    Component("psii", "PSII", "photosystem II (P680)", "span", 2.8, 0, 2, photon=True,
              reaction="H<sub>2</sub>O → ½O<sub>2</sub> + 2H<sup>+</sup>", reaction_side="p",
              note="light excites P680; the oxygen-evolving complex (Mn₄CaO₅) splits water in the lumen",
              aliases=("photosystem_ii", "p680")),
    Component("pq", "PQ", "plastoquinone", "pool", 0.9, 2, 0, note="PQ + 2 e⁻ + 2 H⁺ (stroma) → PQH₂", aliases=("plastoquinone",)),
    Component("b6f", "b<sub>6</sub>f", "cytochrome b<sub>6</sub>f", "span", 2.1, 2, 4,
              note="the Q cycle: 4 H⁺ into the lumen per 2 e⁻", aliases=("cytochrome_b6f", "cyt_b6f")),
    Component("pc", "PC", "plastocyanin", "p", 0.8, note="a copper protein in the lumen, one e⁻ at a time", aliases=("plastocyanin",)),
    Component("psi", "PSI", "photosystem I (P700)", "span", 2.6, photon=True, note="light excites P700 again",
              aliases=("photosystem_i", "p700")),
    Component("fd", "Fd", "ferredoxin", "n", 0.8, note="an Fe–S protein in the stroma", aliases=("ferredoxin",)),
    Component("fnr", "FNR", "ferredoxin–NADP<sup>+</sup> reductase", "n", 1.4, consumes=1,
              reaction="NADP<sup>+</sup> + H<sup>+</sup> → NADPH", aliases=("ferredoxin_nadp_reductase",)),
    Component("atp_synthase", "ATP synthase", "ATP synthase (CF<sub>o</sub>CF<sub>1</sub>)", "synthase", 2.4,
              reaction="ADP + P<sub>i</sub> → ATP", note="CF₁ faces the stroma", aliases=("cf0cf1", "cfocf1")),
)
#: Each chain's components in the order electrons pass (ATP synthase last, beside the chain).
CHAIN_ORDER = {"etc": ("complex_i", "complex_ii", "coq", "complex_iii", "cyt_c", "complex_iv", "atp_synthase"),
               "light_reactions": ("psii", "pq", "b6f", "pc", "psi", "fd", "fnr", "atp_synthase")}
#: The electron paths: from NADH (complex I) or FADH₂ (complex II) to O₂; from water to NADP⁺.
ELECTRON_PATHS = {"nadh": ("complex_i", "coq", "complex_iii", "cyt_c", "complex_iv"),
                  "fadh2": ("complex_ii", "coq", "complex_iii", "cyt_c", "complex_iv"),
                  "water": ("psii", "pq", "b6f", "pc", "psi", "fd", "fnr")}
#: H⁺ through ATP synthase per ATP: c₈ ring in animal mitochondria (8 per 3 ATP), c₁₄ in
#: chloroplasts (14 per 3), c₁₀ in E. coli.
H_PER_ATP = {"inner_mitochondrial_membrane": 8 / 3, "thylakoid_membrane": 14 / 3, "bacterial_inner_membrane": 10 / 3}

MEMBRANE_ALIASES = {"inner_mitochondrial": "inner_mitochondrial_membrane", "thylakoid": "thylakoid_membrane",
                    "plasma": "plasma_membrane", "outer_mitochondrial": "outer_mitochondrial_membrane",
                    "bacterial": "bacterial_inner_membrane", "er": "er_membrane", "inner_envelope": "inner_envelope_membrane",
                    "outer_envelope": "outer_envelope_membrane", "nuclear": "inner_nuclear_membrane"}


def components(process: str) -> dict[str, Component]:
    rows = ETC_COMPONENTS if process == "etc" else LIGHT_COMPONENTS
    return {c.key: c for c in rows}


@dataclass(frozen=True)
class Setting:
    """Where a process runs, checked: the cell, the compartment (pathways) or the membrane and
    its P (``p_side``) and N sides (chains), and the chain's components in order."""

    process: str
    cell: str
    compartment: str = ""
    membrane: str = ""
    p_side: str = ""
    n_side: str = ""
    chain: tuple[str, ...] = ()
    link: bool = False


#: Where each pathway runs, by cell; and the membranes of each chain, by cell.
PATHWAY_PLACES = {"glycolysis": {"animal": "cytosol", "plant": "cytosol", "bacterium": "cytosol"},
                  "link_reaction": {"animal": "matrix", "plant": "matrix", "bacterium": "cytosol"},
                  "tca": {"animal": "matrix", "plant": "matrix", "bacterium": "cytosol"}}
PATHWAY_WHY = {"glycolysis": "glycolysis runs in the cytosol (its enzymes are soluble cytosolic proteins) in every cell",
               "link_reaction": "pyruvate dehydrogenase is in the mitochondrial matrix (in bacteria, the cytosol)",
               "tca": "the citric acid cycle runs in the mitochondrial matrix (succinate dehydrogenase in the inner membrane); in bacteria in the cytosol"}
CHAIN_MEMBRANES = {"etc": {"animal": "inner_mitochondrial_membrane", "plant": "inner_mitochondrial_membrane",
                           "bacterium": "bacterial_inner_membrane"},
                   "light_reactions": {"plant": "thylakoid_membrane"}}
CHAIN_WHY = {"etc": "complexes I–IV and ATP synthase sit in the inner mitochondrial membrane (on the cristae); in bacteria in the "
                    "plasma (inner) membrane",
             "light_reactions": "photosystems, cytochrome b₆f and ATP synthase sit in the thylakoid membrane of chloroplasts"}
SIDES = {"inner_mitochondrial_membrane": ("intermembrane_space", "matrix"), "thylakoid_membrane": ("thylakoid_lumen", "stroma"),
         "bacterial_inner_membrane": ("periplasm", "cytosol")}
SIDE_ALIASES = {"ims": "intermembrane_space", "lumen": "thylakoid_lumen", "cytoplasm": "cytosol", "outside": "periplasm"}


def check_setting(process: str, cell: str | None = None, compartment: str | None = None, membrane: str | None = None,
                  protons_to: str | None = None, chain: tuple[str, ...] | None = None, link: bool = False) -> Setting:
    """The checked setting of a process, or a :class:`VidgenError` with the reason (a chain
    in the wrong membrane, protons pumped to the wrong side, components out of order, a
    pathway in the wrong compartment). ``cell`` defaults to a plant for the light reactions,
    else an animal."""
    process = process_key(process)
    cell = cell or ("plant" if process == "light_reactions" else "animal")
    if cell not in ("animal", "plant", "bacterium"):
        raise VidgenError(f"cell: '{cell}'{did_you_mean(cell, ['animal', 'plant', 'bacterium'])} (animal, plant, bacterium)")
    if process in PATHWAY_PLACES:
        if membrane is not None or protons_to is not None or chain:
            raise VidgenError(f"{process}: membrane, protons_to and components belong to the chains (etc, light_reactions)")
        if link and process == "link_reaction":
            raise VidgenError("link: true adds pyruvate oxidation to glycolysis or the citric acid cycle; process: link_reaction is it already")
        home = PATHWAY_PLACES[process][cell]
        if compartment is not None:
            got = compartment.strip().lower()
            got = {"mitochondrial_matrix": "matrix", "cytoplasm": "cytosol"}.get(got, got)
            if got != home:
                raise VidgenError(f"in: {compartment}: {PATHWAY_WHY[process]} — in a{'n' if cell[0] in 'aeiou' else ''} {cell} cell "
                                  f"it is in the {home}")
        return Setting(process, cell, home, link=link)
    if compartment is not None:
        raise VidgenError(f"{process}: a chain sits in a membrane; write membrane:, not in:")
    if link:
        raise VidgenError(f"link: true belongs to glycolysis and the citric acid cycle, not {process}")
    places = CHAIN_MEMBRANES[process]
    if cell not in places:
        raise VidgenError(f"process: {process} in a{'n' if cell[0] in 'aeiou' else ''} {cell} cell: "
                          + ("animal cells and bacteria have no chloroplasts (cell: plant)" if process == "light_reactions"
                             else "no such membrane"))
    home = places[cell]
    if membrane is not None:
        got = membrane.strip().lower()
        got = MEMBRANE_ALIASES.get(got, got)
        if got != home:
            raise VidgenError(f"membrane: {membrane}: {CHAIN_WHY[process]}; in a{'n' if cell[0] in 'aeiou' else ''} {cell} cell write "
                              f"membrane: {home} (or leave it out)")
    p_side, n_side = SIDES[home]
    if protons_to is not None:
        got = protons_to.strip().lower()
        got = SIDE_ALIASES.get(got, got)
        if got != p_side:
            pumps = "complexes I, III and IV" if process == "etc" else "water splitting at PSII and cytochrome b₆f"
            raise VidgenError(f"protons_to: {protons_to}: {pumps} move protons out of the {n_side.replace('_', ' ')} into the "
                              f"{p_side.replace('_', ' ')} (the P side); the gradient then drives them back into the "
                              f"{n_side.replace('_', ' ')} through ATP synthase, whose F₁ head faces the {n_side.replace('_', ' ')}")
    order = CHAIN_ORDER[process]
    known = components(process)
    if chain:
        resolved = []
        for name in chain:
            key = component_key(process, name)
            if key in resolved:
                raise VidgenError(f"components: {name} is listed twice")
            resolved.append(key)
        for a, b in zip(resolved, resolved[1:]):
            if order.index(b) < order.index(a):
                raise VidgenError(f"components: {known[b].name.split(' (')[0]} comes before {known[a].name.split(' (')[0]} "
                                  f"in the chain (electrons go {' → '.join(_plain(known[k].label) for k in order if k != 'atp_synthase')})")
        _check_continuity(process, tuple(resolved))
        chain = tuple(resolved)
    else:
        chain = order
    return Setting(process, cell, "", home, p_side, n_side, chain)


def _plain(markup: str) -> str:
    return markup.replace("<sub>", "").replace("</sub>", "").replace("<sup>", "").replace("</sup>", "")


def _check_continuity(process: str, chain: tuple[str, ...]) -> None:
    """Electrons must have a way through: each carrier between two drawn complexes is needed."""
    known = components(process)
    needs = {"etc": (("complex_iii", "complex_iv", "cyt_c", "complex III passes electrons to complex IV only through cytochrome c"),
                     ("complex_i", "complex_iii", "coq", "complex I reduces ubiquinone, which carries the electrons to complex III"),
                     ("complex_ii", "complex_iii", "coq", "complex II reduces ubiquinone, which carries the electrons to complex III")),
             "light_reactions": (("psii", "b6f", "pq", "PSII reduces plastoquinone, which carries the electrons to cytochrome b₆f"),
                                 ("b6f", "psi", "pc", "cytochrome b₆f reduces plastocyanin, which carries the electrons to PSI"),
                                 ("psi", "fnr", "fd", "PSI reduces ferredoxin, which carries the electrons to FNR"))}[process]
    for a, b, carrier, why in needs:
        if a in chain and b in chain and carrier not in chain:
            raise VidgenError(f"components: add {_plain(known[carrier].label)} ({_plain(known[carrier].name)}): {why}")
    starts = [k for k in chain if k != "atp_synthase"]
    if not starts:
        raise VidgenError("components: list the chain's complexes (ATP synthase alone has no gradient to use)")


def component_key(process: str, name: str) -> str:
    known = components(process)
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    for comp in known.values():
        if key == comp.key or key in comp.aliases:
            return comp.key
    other = components("light_reactions" if process == "etc" else "etc")
    for comp in other.values():
        if key == comp.key or key in comp.aliases:
            where = "the thylakoid membrane (process: light_reactions)" if process == "etc" else "the inner mitochondrial membrane (process: etc)"
            raise VidgenError(f"components: {name} is not part of {PROCESS_TITLES[process].lower()}: it sits in {where}")
    raise VidgenError(f"components: unknown '{name}'{did_you_mean(key, list(known))} ({', '.join(known)})")


# ----- pathways (glycolysis, link, TCA) ----------------------------------------------------------------


@dataclass(frozen=True)
class Pathway:
    """A drawn pathway: its nodes and steps in order, whether it is a cycle (TCA), and the
    entry (acetyl-CoA joining the cycle)."""

    process: str
    nodes: tuple[Metabolite, ...]
    steps: tuple[Step, ...]
    cyclic: bool = False
    link: bool = False

    def node(self, key: str) -> Metabolite:
        return next(n for n in self.nodes if n.key == key)


def pathway(process: str, link: bool = False) -> Pathway:
    if process == "glycolysis":
        if link:
            return Pathway(process, GLYCOLYSIS_NODES + LINK_NODES, GLYCOLYSIS_STEPS + LINK_STEPS, False, True)
        return Pathway(process, GLYCOLYSIS_NODES, GLYCOLYSIS_STEPS)
    if process == "link_reaction":
        return Pathway(process, (GLYCOLYSIS_NODES[-1],) + LINK_NODES, LINK_STEPS, False, True)
    return Pathway(process, TCA_NODES, TCA_STEPS, True, link)


def step_index(p: Pathway, name: str) -> int:
    """The step a name means: the step's enzyme (or alias) or the metabolite it makes; the
    index of the step that ends there."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    for k, s in enumerate(p.steps):
        if key == s.key or key in s.aliases or key == s.target:
            return k
    if p.cyclic and key == p.nodes[0].key:
        return len(p.steps) - 1
    names = [s.key for s in p.steps] + [n.key for n in p.nodes]
    raise VidgenError(f"{PROCESS_TITLES[p.process].lower()} has no step or metabolite '{name}'{did_you_mean(key, names)} "
                      f"(metabolites: {', '.join(n.key for n in p.nodes)})")


def tallies(p: Pathway, upto: int, turns: int = 0) -> dict[str, int]:
    """The counters after steps 0..``upto`` (inclusive; -1: none) and ``turns`` full turns
    before, per glucose for glycolysis (steps after the cleavage count twice) and per acetyl-CoA
    for the cycle."""
    out: dict[str, int] = {}
    for k, s in enumerate(p.steps):
        n = turns + (1 if k <= upto else 0)
        for key, value in s.tally:
            out[key] = out.get(key, 0) + value * s.times * n
    return {k: v for k, v in out.items() if v}


@dataclass
class FlowState:
    """Where a pathway's token or a chain's electrons are: ``step`` (last step done; -1 at the
    start), ``turns`` (cycles completed), the protons on the P side (``gradient``), and the
    products so far."""

    step: int = -1
    turns: int = 0
    gradient: int = 0
    made: dict[str, int] = field(default_factory=dict)


def pathway_advance_problem(p: Pathway, state: FlowState, to: str | None) -> str | None:
    if to is None:
        return None if (p.cyclic or state.step < len(p.steps) - 1) else f"{PROCESS_TITLES[p.process].lower()} has already run to its end"
    try:
        k = step_index(p, to)
    except VidgenError as error:
        return str(error)
    if k <= state.step and not p.cyclic:
        return (f"{PROCESS_TITLES[p.process].lower()} is past '{to}' already ({p.nodes[state.step + 1].markup} made); "
                f"it runs one way: advance to a later step")
    return None


def chain_advance_problem(setting: Setting, state: FlowState, to: str | None, source: str | None) -> str | None:
    """Why ``advance`` along a chain cannot happen (``None`` when it can)."""
    if source is not None:
        src = source.strip().lower()
        if setting.process == "light_reactions" and src not in ("water", "h2o"):
            return f"from: {source}: the light reactions take electrons from water (from: water)"
        if setting.process == "etc" and src not in ("nadh", "fadh2", "succinate"):
            return f"from: {source}: electrons enter the chain from NADH (complex I) or FADH₂ (complex II, succinate)"
        if src in ("fadh2", "succinate") and "complex_ii" not in setting.chain:
            return "from: fadh2 enters at complex II, which the components leave out"
        if src == "nadh" and "complex_i" not in setting.chain:
            return "from: nadh enters at complex I, which the components leave out"
    if to is None:
        return None
    try:
        key = component_key(setting.process, to)
    except VidgenError as error:
        return str(error).replace("components: ", "")
    if key not in setting.chain:
        return f"to: {to} is not drawn (components: {', '.join(setting.chain)})"
    if key == "atp_synthase" and state.gradient <= 0:
        return "no proton gradient yet: advance the electrons through the chain first (the gradient drives ATP synthase)"
    path = electron_path(setting, source)
    if key != "atp_synthase" and key not in path:
        return f"to: {to}: electrons from {source or ('water' if setting.process == 'light_reactions' else 'NADH')} do not pass it"
    return None


def electron_path(setting: Setting, source: str | None) -> tuple[str, ...]:
    """The drawn components electrons pass from ``source`` (NADH by default; water for the
    light reactions)."""
    src = (source or ("water" if setting.process == "light_reactions" else "nadh")).strip().lower()
    src = {"h2o": "water", "succinate": "fadh2"}.get(src, src)
    return tuple(k for k in ELECTRON_PATHS[src] if k in setting.chain)


def chain_effects(setting: Setting, path: tuple[str, ...]) -> dict[str, int]:
    """Protons moved per two electrons along ``path``: ``taken`` from the N side, ``given`` to
    the P side, ``consumed`` on the N side."""
    known = components(setting.process)
    out = {"taken": 0, "given": 0, "consumed": 0}
    for key in path:
        c = known[key]
        out["taken"] += c.takes
        out["given"] += c.gives
        out["consumed"] += c.consumes
    return out
