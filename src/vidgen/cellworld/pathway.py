"""Signalling pathways as data (DESIGN.md §95.12): a graph of nodes (ligands, receptors,
proteins, complexes, second messengers, genes, outcomes) in compartment bands (extracellular
space, plasma membrane, cytosol, ER, mitochondrion, nucleus) joined by SBGN-inspired arcs
(activation arrows, inhibition T-bars, catalysis, phosphorylation, binding, translocation,
transcription), the rules that refuse what cannot be (an unknown node, an arc against a
declared effect, a node in a compartment it never is in, a gene outside the nucleus, a name in
the wrong case for the species) and the logic the actions animate: a signal spreading step by
step, and the effects downstream of a knockout, a drug or an inhibitor. No manim."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, fields, replace
from html import escape

from vidgen.errors import VidgenError

from .catalog import COMPARTMENTS, MEMBRANES
from .model import did_you_mean
from .names import check_gene, check_modification, check_protein, species as species_of
from .notation import chem_markup, chem_plain


# ----- compartment bands ------------------------------------------------------------------------


@dataclass(frozen=True)
class Band:
    """A compartment band of a pathway drawing: its name, label (from the cell catalog), short
    label (for narrow columns), whether it is a membrane (its nodes stand in a row along it) and
    other names it is written as."""

    name: str
    label: str
    short: str
    membrane: bool
    aliases: tuple[str, ...]
    note: str


#: The bands in drawing order: the signal comes in from outside and ends in the nucleus.
BANDS: dict[str, Band] = {b.name: b for b in (
    Band("extracellular", COMPARTMENTS["extracellular"].label, "Outside", False, ("outside", "extracellular_space"),
         "outside the cell: ligands, hormones, growth factors"),
    Band("plasma_membrane", MEMBRANES["plasma_membrane"].label, "Membrane", True, ("membrane", "plasma", "cell_membrane"),
         "receptors, channels and membrane enzymes; lipid-anchored G proteins and membrane lipids (PIP₂, PIP₃, DAG)"),
    Band("cytosol", COMPARTMENTS["cytosol"].label, "Cytosol", False, ("cytoplasm", "cytoplasmic"),
         "kinase cascades, second messengers, latent transcription factors"),
    Band("er", "Endoplasmic reticulum", "ER", False, ("er_lumen", "er_membrane", "endoplasmic_reticulum"),
         "the ER membrane and lumen: the Ca²⁺ store, IP₃ receptors"),
    Band("mitochondrion", "Mitochondrion", "Mito.", False, ("mitochondria", "matrix", "intermembrane_space",
                                                               "outer_mitochondrial_membrane", "inner_mitochondrial_membrane"),
         "the mitochondrion: cytochrome c, Bcl-2 family proteins on the outer membrane"),
    Band("nucleus", "Nucleus", "Nucleus", False, ("nucleoplasm", "nuclear"),
         "inside the nuclear envelope: transcription factors on DNA, genes"),
)}
_BAND_ALIASES: dict[str, str] = {alias: b.name for b in BANDS.values() for alias in (b.name, *b.aliases)}


def band_name(text: str, where: str) -> str:
    """The band a compartment name means (``nucleoplasm`` → ``nucleus``, ``membrane`` →
    ``plasma_membrane``), or an error naming the bands."""
    key = text.strip().lower().replace("-", "_").replace(" ", "_")
    if key in _BAND_ALIASES:
        return _BAND_ALIASES[key]
    raise VidgenError(f"{where}: compartment '{text}'{did_you_mean(key, list(_BAND_ALIASES))} "
                      f"(compartments: {', '.join(BANDS)})")


# ----- node kinds -------------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeKind:
    """A kind of pathway node: its SBGN glyph (``macromolecule``, ``complex``,
    ``simple_chemical``, ``nucleic_acid``, ``phenotype``, ``drug``), the theme colour it is
    drawn in, its default band, the bands it may be in with the reason, its states (the first
    is the resting one; the signal turns it to the last) and what it is."""

    name: str
    glyph: str
    color: str
    band: str | None
    bands: tuple[str, ...]
    why: str
    states: tuple[str, ...]
    note: str


_INSIDE = ("plasma_membrane", "cytosol", "er", "mitochondrion", "nucleus")
_ALL = tuple(BANDS)
_ACTIVE = ("inactive", "active")
_GUANINE = ("gdp", "gtp")
#: Node kinds by name.
NODE_KINDS: dict[str, NodeKind] = {k.name: k for k in (
    NodeKind("ligand", "macromolecule", "primary", "extracellular", ("extracellular",),
             "a ligand reaches its receptor from outside the cell (a hormone that crosses the membrane, such as a steroid, "
             "is a small_molecule node)", ("unbound", "bound"), "a hormone, growth factor or other signal outside the cell"),
    NodeKind("receptor", "macromolecule", "primary", "plasma_membrane", ("plasma_membrane", "er"),
             "a receptor node is a membrane receptor (GPCR, RTK, ion channel; the IP₃ receptor of the ER); "
             "intracellular (nuclear) receptors are transcription_factor nodes", _ACTIVE,
             "a membrane receptor: GPCR, receptor tyrosine kinase, cytokine receptor, ligand-gated channel"),
    NodeKind("protein", "macromolecule", "primary", "cytosol", _ALL, "", _ACTIVE, "any protein"),
    NodeKind("kinase", "macromolecule", "secondary", "cytosol", _INSIDE,
             "signalling kinases act inside the cell", _ACTIVE, "a protein kinase (adds phosphates)"),
    NodeKind("phosphatase", "macromolecule", "accent", "cytosol", _INSIDE,
             "signalling phosphatases act inside the cell", _ACTIVE, "a protein or lipid phosphatase (removes phosphates)"),
    NodeKind("g_protein", "macromolecule", "tertiary", "plasma_membrane", ("plasma_membrane", "cytosol"),
             "heterotrimeric G proteins are anchored to the cytosolic face of the plasma membrane by lipids", _GUANINE,
             "a heterotrimeric G protein's α subunit (Gαs, Gαi, Gαq): GDP-bound off, GTP-bound on"),
    NodeKind("gtpase", "macromolecule", "tertiary", "cytosol", _INSIDE,
             "small GTPases act on the cytosolic faces of membranes (Ras at the plasma membrane, Rheb on lysosomes) or in the "
             "nucleus (Ran)", _GUANINE, "a small GTPase (Ras, Rheb, Rap, Rho, Ran): GDP-bound off, GTP-bound on"),
    NodeKind("gef", "macromolecule", "primary", "cytosol", _INSIDE, "GEFs act inside the cell", _ACTIVE,
             "a guanine-nucleotide exchange factor (SOS): swaps a GTPase's GDP for GTP, turning it on"),
    NodeKind("gap", "macromolecule", "accent", "cytosol", _INSIDE, "GAPs act inside the cell", _ACTIVE,
             "a GTPase-activating protein (p120RasGAP, NF1, TSC2, RGS): speeds GTP hydrolysis, turning a GTPase off"),
    NodeKind("adaptor", "macromolecule", "primary", "cytosol", _INSIDE, "adaptors act inside the cell", _ACTIVE,
             "an adaptor or scaffold without enzyme activity (Grb2, IRS1, 14-3-3)"),
    NodeKind("enzyme", "macromolecule", "secondary", "cytosol", _ALL, "", _ACTIVE,
             "an enzyme that makes or destroys a messenger (adenylyl cyclase, phospholipase C, phosphodiesterase)"),
    NodeKind("transcription_factor", "macromolecule", "purple", "nucleus", ("cytosol", "nucleus", "mitochondrion"),
             "a transcription factor waits in the cytosol (latent: STATs, NF-κB, SMADs) or works in the nucleus", _ACTIVE,
             "a transcription factor (CREB, Elk-1, FOXO, nuclear receptors)"),
    NodeKind("complex", "complex", "primary", "cytosol", _ALL, "", _ACTIVE,
             "a protein complex (mTORC1, the PKA holoenzyme, TSC1–TSC2)"),
    NodeKind("small_molecule", "simple_chemical", "highlight", "cytosol", _ALL, "", _ACTIVE,
             "a second messenger, lipid or ion (cAMP, IP₃, DAG, PIP₃, Ca²⁺)"),
    NodeKind("gene", "nucleic_acid", "tertiary", "nucleus", ("nucleus", "mitochondrion"),
             "genes are DNA: in a eukaryote in the nucleus (and the mitochondrial genome); a transcription factor regulates its "
             "target gene there", ("silent", "transcribed"), "a gene (italic symbol) whose transcription is regulated"),
    NodeKind("phenotype", "phenotype", "text", None, _ALL, "", ("off", "on"),
             "an outcome (proliferation, gluconeogenesis, cell growth, apoptosis)"),
    NodeKind("drug", "drug", "accent", None, _ALL, "", ("unbound", "bound"),
             "a drug or tool compound (an inhibitor unless role: activator)"),
)}

#: Small molecules whose compartments are known (label, case-insensitive → bands, reason).
SMALL_MOLECULES: dict[str, tuple[tuple[str, ...], str]] = {
    "camp": (("cytosol", "nucleus"), "cAMP is made by adenylyl cyclase on the cytosolic side and diffuses in the cytosol (and "
                                     "through the nuclear pores)"),
    "cgmp": (("cytosol", "nucleus"), "cGMP is made by guanylyl cyclases into the cytosol"),
    "ip3": (("cytosol",), "IP₃ is released from PIP₂ into the cytosol and binds IP₃ receptors on the ER"),
    "dag": (("plasma_membrane",), "DAG is a lipid: it stays in the plasma membrane, where it recruits PKC"),
    "pip2": (("plasma_membrane",), "PIP₂ (PI(4,5)P₂) is a lipid of the inner leaflet of the plasma membrane"),
    "pip3": (("plasma_membrane",), "PIP₃ (PI(3,4,5)P₃) is a lipid of the inner leaflet of the plasma membrane"),
    "pi(4,5)p2": (("plasma_membrane",), "PI(4,5)P₂ is a lipid of the inner leaflet of the plasma membrane"),
    "pi(3,4,5)p3": (("plasma_membrane",), "PI(3,4,5)P₃ is a lipid of the inner leaflet of the plasma membrane"),
    "atp": (("cytosol", "mitochondrion", "nucleus"), "ATP is inside cells"),
    "gtp": (("cytosol", "mitochondrion", "nucleus", "plasma_membrane"), "GTP is inside cells"),
}

#: Node roles a writer may declare (checked against the node's arcs).
ROLES = ("activator", "inhibitor")


# ----- arc types --------------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeType:
    """An arc type: its default sign (+1 activating, −1 inhibiting), whether ``effect`` may
    flip it, the mark drawn on it (``P``: phosphorylation, ``-P``: dephosphorylation, ``dot``:
    binding), whether it is drawn dashed, and what it means."""

    name: str
    sign: int
    flips: bool
    mark: str | None
    dashed: bool
    note: str


EDGE_TYPES: dict[str, EdgeType] = {t.name: t for t in (
    EdgeType("activates", +1, False, None, False, "stimulation (a filled arrowhead)"),
    EdgeType("inhibits", -1, False, None, False, "inhibition (a T-bar)"),
    EdgeType("catalyses", +1, False, None, False, "catalysis: the enzyme makes or converts the target (an open circle)"),
    EdgeType("phosphorylates", +1, True, "P", False, "phosphorylation (a P on the arc; effect: inhibits for an inhibitory site)"),
    EdgeType("dephosphorylates", -1, True, "-P", False, "dephosphorylation (−P on the arc; effect: activates when it activates)"),
    EdgeType("binds", +1, True, "dot", False, "binding / complex formation (a dot on the arc)"),
    EdgeType("translocates", +1, False, None, True, "the same molecule moves to another compartment (dashed; e.g. into the nucleus)"),
    EdgeType("transcribes", +1, True, None, False, "transcriptional regulation of a gene (effect: inhibits for repression)"),
    EdgeType("expresses", +1, False, None, True, "a gene's product is made (dashed)"),
    EdgeType("converts", +1, False, None, False, "one small molecule becomes another (PIP₂ → PIP₃)"),
)}
_EDGE_ALIASES = {
    "activation": "activates", "stimulates": "activates", "stimulation": "activates", "activate": "activates",
    "inhibition": "inhibits", "inhibit": "inhibits", "catalyzes": "catalyses", "catalysis": "catalyses",
    "phosphorylation": "phosphorylates", "dephosphorylation": "dephosphorylates", "binding": "binds", "complex": "binds",
    "translocation": "translocates", "transcription": "transcribes", "regulates_transcription": "transcribes",
    "expression": "expresses", "conversion": "converts", "produces": "converts",
}
EFFECTS = {"activates": +1, "inhibits": -1, "represses": -1, "activating": +1, "inhibitory": -1, "+": +1, "-": -1}
#: The shorthand arrows of ``"a -> b"`` strings.
ARROWS = {"->": "activates", "-|": "inhibits", "-o": "catalyses", "=>": "translocates"}
_ARROW_RE = re.compile(r"\s*(->|-\||-o|=>)\s*")


def edge_type_name(text: str, where: str) -> str:
    key = text.strip().lower().replace("-", "_").replace(" ", "_")
    key = _EDGE_ALIASES.get(key, key)
    if key not in EDGE_TYPES:
        raise VidgenError(f"{where}: arc type '{text}'{did_you_mean(key, list(EDGE_TYPES))} (types: {', '.join(EDGE_TYPES)})")
    return key


def parse_arrows(text: str) -> list[tuple[str, str, str]]:
    """``(from, to, type)`` for each arrow of a shorthand: ``"a -> b"`` (activates), ``"a -| b"``
    (inhibits), ``"a -o b"`` (catalyses), ``"a => b"`` (translocates), chains ``"a -> b -> c"``."""
    parts = _ARROW_RE.split(text.strip())
    if len(parts) < 3:
        raise ValueError(f"{text!r} is not an arc; write 'a -> b' (activates), 'a -| b' (inhibits), 'a -o b' (catalyses) "
                         f"or 'a => b' (translocates), or {{from, to, type}}")
    ids, arrows = parts[0::2], parts[1::2]
    out = []
    for a, b, arrow in zip(ids, ids[1:], arrows):
        if not a or not b:
            raise ValueError(f"{text!r}: an arrow needs a node id on both sides")
        out.append((a.strip(), b.strip(), ARROWS[arrow]))
    return out


# ----- specs (what the scene's params and the templates give) -----------------------------------


@dataclass(frozen=True)
class NodeSpec:
    """A node as written: ``id`` and any of its fields (``None``: not given; a template's node
    of the same id gives the rest)."""

    id: str
    kind: str | None = None
    label: str | None = None
    compartment: str | None = None
    gene: str | None = None
    state: str | None = None
    marks: tuple[tuple[str, str | None], ...] | None = None
    role: str | None = None
    where: str = ""


@dataclass(frozen=True)
class EdgeSpec:
    """An arc as written."""

    source: str
    target: str
    type: str = "activates"
    effect: str | None = None
    site: str | None = None
    feedback: bool = False
    label: str | None = None
    indirect: bool = False
    where: str = ""

    @property
    def ref(self) -> str:
        return f"{self.source}->{self.target}"


@dataclass(frozen=True)
class PathwaySpec:
    """A whole pathway as written: a ``template`` (its nodes and arcs first), ``nodes`` (one
    with a template node's id changes that node), ``edges`` (one between the same two nodes
    replaces the template's), ``remove`` (node ids or ``a->b`` arcs of the template to leave
    out) and the ``species`` whose nomenclature names follow."""

    nodes: tuple[NodeSpec, ...] = ()
    edges: tuple[EdgeSpec, ...] = ()
    species: str = "human"
    template: str | None = None
    remove: tuple[str, ...] = ()


# ----- the resolved pathway ---------------------------------------------------------------------


@dataclass(frozen=True)
class Mark:
    """A modification shown on a node: ``P`` / ``Ub`` / ``Ac`` / ``Me`` and the residue."""

    mark: str
    site: str | None

    @property
    def text(self) -> str:
        """``pS133`` for a site of phosphorylation (as research papers write it), ``P``
        without a site, ``Ub K48`` for another mark."""
        if self.mark == "P":
            return f"p{self.site}" if self.site else "P"
        return f"{self.mark} {self.site}" if self.site else self.mark


@dataclass(frozen=True)
class Node:
    """A checked node: its kind, label (Pango markup and plain), band, resting state, marks
    shown from the start, declared role and gene symbol."""

    id: str
    kind: NodeKind
    markup: str
    plain: str
    band: str
    state: str
    marks: tuple[Mark, ...]
    role: str | None
    gene: str | None

    @property
    def guanine(self) -> bool:
        """A G protein or small GTPase: GDP-bound, GTP-bound."""
        return self.kind.states == _GUANINE


@dataclass(frozen=True)
class Edge:
    """A checked arc (``index``: its place in the pathway's list)."""

    index: int
    source: str
    target: str
    type: EdgeType
    sign: int
    site: Mark | None
    feedback: bool
    label: str | None
    dashed: bool

    @property
    def ref(self) -> str:
        return f"{self.source}->{self.target}"

    @property
    def inhibits(self) -> bool:
        return self.sign < 0


@dataclass(frozen=True)
class Pathway:
    """A checked pathway: nodes in order, arcs, the bands used (in drawing order), the
    species and the loops no ``feedback`` arc closes (warned about)."""

    nodes: dict[str, Node]
    edges: tuple[Edge, ...]
    bands: tuple[str, ...]
    species: str
    loops: tuple[tuple[str, ...], ...] = field(default=())

    def out_edges(self, node: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node]

    def in_edges(self, node: str) -> list[Edge]:
        return [e for e in self.edges if e.target == node]

    def edge(self, ref: str) -> Edge:
        for e in self.edges:
            if e.ref == ref:
                return e
        raise KeyError(ref)

    def node_ids(self) -> list[str]:
        return list(self.nodes)


# ----- building and checking --------------------------------------------------------------------


def merged_specs(spec: PathwaySpec) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    """The nodes and arcs of ``spec`` with its template's first (changed, replaced and removed
    as written)."""
    nodes: dict[str, NodeSpec] = {}
    edges: dict[str, EdgeSpec] = {}
    if spec.template is not None:
        from .pathway_templates import TEMPLATES

        if spec.template not in TEMPLATES:
            raise VidgenError(f"template '{spec.template}'{did_you_mean(spec.template, list(TEMPLATES))} "
                              f"(templates: {', '.join(TEMPLATES)})")
        base = TEMPLATES[spec.template]
        nodes = {n.id: n for n in base.nodes}
        edges = {e.ref: e for e in base.edges}
        for k, ref in enumerate(spec.remove):
            ref = "->".join(p.strip() for p in ref.split("->"))
            if "->" in ref:
                if ref not in edges:
                    raise VidgenError(f"remove[{k}]: the template has no arc '{ref}'{did_you_mean(ref, list(edges))}")
                del edges[ref]
            else:
                if ref not in nodes:
                    raise VidgenError(f"remove[{k}]: the template has no node '{ref}'{did_you_mean(ref, list(nodes))}")
                del nodes[ref]
                edges = {r: e for r, e in edges.items() if ref not in (e.source, e.target)}
    elif spec.remove:
        raise VidgenError("remove: leaves out nodes or arcs of a template; this pathway has no template")
    seen: set[str] = set()
    for n in spec.nodes:
        if n.id in seen:
            raise VidgenError(f"{n.where}: id '{n.id}' is used twice")
        seen.add(n.id)
        if n.id in nodes:
            changes = {f.name: getattr(n, f.name) for f in fields(n) if f.name != "id" and getattr(n, f.name) is not None}
            nodes[n.id] = replace(nodes[n.id], **changes)
        else:
            nodes[n.id] = n
    written: set[str] = set()
    for e in spec.edges:
        if e.ref in written:
            raise VidgenError(f"{e.where}: {e.source} -> {e.target} is listed twice")
        written.add(e.ref)
        edges[e.ref] = e
    return list(nodes.values()), list(edges.values())


def build_pathway(spec: PathwaySpec) -> Pathway:
    """Check a pathway and resolve it (see the module's docs for the rules)."""
    species_of(spec.species, "species")
    node_specs, edge_specs = merged_specs(spec)
    if not node_specs:
        raise VidgenError("nodes: a pathway needs nodes (or a template)")
    reserved = set(BANDS) | {"title", "pathway", "legend"}
    for n in node_specs:
        if n.id in reserved:
            raise VidgenError(f"{n.where or 'node'}: id '{n.id}' is the name of a target of the scene; give the node another id")
        if not re.match(r"^[A-Za-z][\w.\-]*$", n.id) or n.id.endswith((".", "-")):
            raise VidgenError(f"{n.where or 'node'}: id '{n.id}': use letters, digits, '_', '.' and '-', starting with a letter")
    ids = [n.id for n in node_specs]
    for e in edge_specs:
        for end in (e.source, e.target):
            if end not in ids:
                raise VidgenError(f"{e.where or 'edges'} ({e.source} -> {e.target}): unknown node '{end}'{did_you_mean(end, ids)}"
                                  f" (nodes: {', '.join(ids[:16])}{', …' if len(ids) > 16 else ''})")
        if e.source == e.target:
            raise VidgenError(f"{e.where or 'edges'}: '{e.source}' points to itself; draw a node's own activity as its state")
    kinds = {n.id: _kind(n) for n in node_specs}
    # bands: written, else the kind's; outcomes and drugs follow the node they come from / act on
    bands: dict[str, str] = {}
    for n in node_specs:
        if n.compartment is not None:
            bands[n.id] = band_name(n.compartment, n.where or n.id)
        elif kinds[n.id].band is not None:
            bands[n.id] = kinds[n.id].band  # type: ignore[assignment]
    for n in node_specs:
        if n.id not in bands:
            kind = kinds[n.id]
            ends = [e.source for e in edge_specs if e.target == n.id] if kind.name == "phenotype" else [e.target for e in edge_specs if e.source == n.id]
            bands[n.id] = next((bands[x] for x in ends if x in bands), "cytosol")
    nodes: dict[str, Node] = {}
    for n in node_specs:
        nodes[n.id] = _node(n, kinds[n.id], bands[n.id], spec.species)
    edges = tuple(_edge(k, e, nodes) for k, e in enumerate(edge_specs))
    used = {n.band for n in nodes.values()}
    order = tuple(b for b in BANDS if b in used)
    pathway = Pathway(nodes, edges, order, spec.species)
    return replace(pathway, loops=tuple(undeclared_loops(pathway)))


def _kind(n: NodeSpec) -> NodeKind:
    name = (n.kind or "protein").strip().lower()
    if name not in NODE_KINDS:
        raise VidgenError(f"{n.where or n.id}: kind '{n.kind}'{did_you_mean(name, list(NODE_KINDS))} (kinds: {', '.join(NODE_KINDS)})")
    return NODE_KINDS[name]


def _node(n: NodeSpec, kind: NodeKind, band: str, species: str) -> Node:
    where = n.where or f"node '{n.id}'"
    if band not in kind.bands:
        allowed = ", ".join(kind.bands)
        raise VidgenError(f"{where} ({kind.name} '{n.id}'): not in the {BANDS[band].label.lower()}: {kind.why} (compartments: {allowed})")
    label = n.label if n.label is not None else n.id
    gene = None
    if kind.name == "gene":
        check_gene(label, species, where)
        markup, plain = f"<i>{escape(label, quote=False)}</i>", label
    elif kind.glyph == "simple_chemical" or kind.name == "drug":
        known = SMALL_MOLECULES.get(label.lower())
        if known is not None and kind.name == "small_molecule" and band not in known[0]:
            raise VidgenError(f"{where} ({label}): not in the {BANDS[band].label.lower()}: {known[1]} (compartments: {', '.join(known[0])})")
        markup, plain = _sub(chem_markup(label)), chem_plain(label).replace("_", "")
    else:
        if n.gene is not None:
            gene = check_gene(n.gene, species, f"{where} gene")
        check_protein(label.replace("_", ""), species, where, gene)
        markup, plain = _sub(escape(label, quote=False)), label.replace("_", "")
    state = (n.state or kind.states[0]).lower()
    if state not in kind.states:
        raise VidgenError(f"{where}: state '{n.state}': a {kind.name.replace('_', ' ')} is {' or '.join(kind.states)}")
    marks = []
    for mark, at in n.marks or ():
        mod, residue = check_modification(mark, at, where)
        marks.append(Mark(mod.mark, None if residue is None else f"{residue[0]}{residue[1]}"))
    if n.role is not None and n.role not in ROLES:
        raise VidgenError(f"{where}: role '{n.role}': use {' or '.join(ROLES)}")
    return Node(n.id, kind, markup, plain, band, state, tuple(marks), n.role, gene)


def _sub(markup: str) -> str:
    """``Gα_s`` → Gα<sub>s</sub>: an underscore makes the next letters or digits a subscript."""
    return re.sub(r"_([0-9A-Za-zα-ω]+)", r"<sub>\1</sub>", markup)


#: Kinds that cannot act on molecules (outcomes) or act only through their product (genes).
_NO_OUT = {"phenotype": "a phenotype is an outcome; it does not act on molecules (draw what causes it as a node)"}
_PHOSPHORYLATING = ("kinase", "receptor", "complex", "protein", "enzyme")
_DEPHOSPHORYLATING = ("phosphatase", "complex", "protein", "enzyme")
_CATALYSING = ("kinase", "phosphatase", "enzyme", "receptor", "complex", "protein", "gef", "gap", "g_protein", "gtpase")


def _edge(k: int, e: EdgeSpec, nodes: dict[str, Node]) -> Edge:
    where = f"{e.where or f'edges[{k}]'} ({e.source} -> {e.target})"
    etype = EDGE_TYPES[edge_type_name(e.type, where)]
    sign = etype.sign
    if e.effect is not None:
        key = e.effect.strip().lower()
        if key not in EFFECTS:
            raise VidgenError(f"{where}: effect '{e.effect}': use activates or inhibits")
        wanted = EFFECTS[key]
        if wanted != etype.sign and not etype.flips:
            raise VidgenError(f"{where}: type {etype.name} {'activates' if etype.sign > 0 else 'inhibits'}, but effect says "
                              f"{e.effect}: they contradict; write type: {'inhibits' if wanted < 0 else 'activates'}")
        sign = wanted
    a, b = nodes[e.source], nodes[e.target]
    ka, kb = a.kind.name, b.kind.name
    if ka in _NO_OUT:
        raise VidgenError(f"{where}: '{a.id}': {_NO_OUT[ka]}")
    if ka == "gene" and etype.name != "expresses":
        raise VidgenError(f"{where}: a gene acts through its product: add the protein as a node and write {a.id} -> <protein> "
                          f"with type: expresses")
    if kb == "gene" and etype.name != "transcribes":
        raise VidgenError(f"{where}: a gene is regulated by transcription factors binding at it: write type: transcribes "
                          f"(effect: inhibits for repression)")
    if etype.name == "expresses":
        if ka != "gene":
            raise VidgenError(f"{where}: expresses goes from a gene to its product; '{a.id}' is a {ka.replace('_', ' ')}")
        if kb in ("gene", "small_molecule", "drug"):
            raise VidgenError(f"{where}: a gene's product is an RNA or a protein, not a {kb.replace('_', ' ')}")
    if etype.name == "transcribes":
        if ka not in ("transcription_factor", "complex"):
            raise VidgenError(f"{where}: '{a.id}' is a {ka.replace('_', ' ')}; transcription is regulated by a transcription factor "
                              f"(kind: transcription_factor) binding at its target gene")
        if kb != "gene":
            raise VidgenError(f"{where}: transcribes goes to a gene node (kind: gene, an italic symbol); '{b.id}' is a {kb.replace('_', ' ')}")
        if a.band != b.band:
            raise VidgenError(f"{where}: {a.plain} is in the {BANDS[a.band].label.lower()} but its target gene {b.plain} is in the "
                              f"{BANDS[b.band].label.lower()}: a transcription factor binds its gene's DNA in the nucleus; add a "
                              f"translocates arc that brings it there ({a.id} => {a.id}_n) and regulate from that node")
    if etype.name == "translocates":
        if a.plain != b.plain:
            raise VidgenError(f"{where}: translocates moves one molecule between compartments: both nodes need the same label "
                              f"('{a.plain}' and '{b.plain}'); for one molecule acting on another use activates")
        if a.band == b.band:
            raise VidgenError(f"{where}: both nodes are in the {BANDS[a.band].label.lower()}; a translocation goes to another "
                              f"compartment (compartment: nucleus)")
        if "extracellular" in (a.band, b.band):
            raise VidgenError(f"{where}: crossing the plasma membrane is transport or secretion, not a translocation within the cell")
        if "cytosol" not in (a.band, b.band):
            raise VidgenError(f"{where}: from the {BANDS[a.band].label.lower()} to the {BANDS[b.band].label.lower()} the molecule "
                              f"passes through the cytosol: translocate it to the cytosol first")
    if etype.name == "converts" and (a.kind.glyph != "simple_chemical" or b.kind.glyph != "simple_chemical"):
        raise VidgenError(f"{where}: converts turns one small molecule into another (PIP2 -> PIP3); for an enzyme making it use "
                          f"catalyses")
    if etype.name == "phosphorylates":
        if ka == "phosphatase":
            raise VidgenError(f"{where}: '{a.id}' is a phosphatase: it removes phosphates; write type: dephosphorylates")
        if ka not in _PHOSPHORYLATING:
            raise VidgenError(f"{where}: '{a.id}' is a {ka.replace('_', ' ')}; only kinases (and receptor kinases, kinase complexes) "
                              f"phosphorylate")
    if etype.name == "dephosphorylates":
        if ka == "kinase":
            raise VidgenError(f"{where}: '{a.id}' is a kinase: it adds phosphates; write type: phosphorylates")
        if ka not in _DEPHOSPHORYLATING:
            raise VidgenError(f"{where}: '{a.id}' is a {ka.replace('_', ' ')}; phosphates are removed by phosphatases")
    if etype.name == "catalyses" and ka not in _CATALYSING:
        raise VidgenError(f"{where}: '{a.id}' is a {ka.replace('_', ' ')}, not an enzyme; catalysis is drawn from an enzyme")
    if kb in ("g_protein", "gtpase"):
        if ka == "gap" and sign > 0:
            raise VidgenError(f"{where}: a GAP turns its GTPase off: it speeds GTP hydrolysis to GDP; write type: inhibits")
        if ka == "gef" and sign < 0:
            raise VidgenError(f"{where}: a GEF turns its GTPase on: it swaps GDP for GTP; write type: activates")
    if ka == "drug" and sign > 0 and a.role != "activator":
        raise VidgenError(f"{where}: a drug node inhibits its target; for an agonist or activator give it role: activator")
    if a.role == "inhibitor" and sign > 0:
        raise VidgenError(f"{where}: '{a.id}' is declared role: inhibitor, but this arc ({etype.name}) activates; "
                          f"write type: inhibits (or effect: inhibits) or change the role")
    if a.role == "activator" and sign < 0:
        raise VidgenError(f"{where}: '{a.id}' is declared role: activator, but this arc inhibits; write type: activates or "
                          f"change the role")
    site = None
    if e.site is not None:
        if etype.name not in ("phosphorylates", "dephosphorylates"):
            raise VidgenError(f"{where}: site is the residue a (de)phosphorylation acts on; this arc {etype.name}")
        if kb not in ("protein", "kinase", "phosphatase", "g_protein", "gtpase", "gef", "gap", "adaptor", "enzyme",
                      "transcription_factor", "receptor", "complex", "ligand"):
            raise VidgenError(f"{where}: site: a {kb.replace('_', ' ')} has no amino-acid residues")
        _, residue = check_modification("P", e.site, f"{where} site")
        site = Mark("P", None if residue is None else f"{residue[0]}{residue[1]}")
    elif etype.name == "phosphorylates" and kb not in ("small_molecule",):
        site = Mark("P", None)
    dashed = etype.dashed or e.indirect
    return Edge(k, e.source, e.target, etype, sign, site, e.feedback, e.label, dashed)


def undeclared_loops(pathway: Pathway) -> list[tuple[str, ...]]:
    """The loops of the pathway (strongly connected groups of nodes) that no arc marked
    ``feedback`` breaks, each as its nodes in pathway order."""
    edges = [(e.source, e.target) for e in pathway.edges if not e.feedback]
    return [tuple(c) for c in _components(list(pathway.nodes), edges) if len(c) > 1]


def _components(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Strongly connected components (Tarjan, iterative), each in node order."""
    out: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        out[a].append(b)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    result: list[list[str]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work = [(root, 0)]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            v, i = work[-1]
            if i < len(out[v]):
                work[-1] = (v, i + 1)
                w = out[v][i]
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, 0))
                elif w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    rank = {n: k for k, n in enumerate(nodes)}
                    result.append(sorted(comp, key=rank.__getitem__))
    return result


def loop_warnings(pathway: Pathway, where: str = "edges") -> list[str]:
    """One warning per loop no ``feedback`` arc closes."""
    out = []
    for loop in pathway.loops:
        members = set(loop)
        arcs = [e.ref for e in pathway.edges if e.source in members and e.target in members]
        out.append(f"{where}: {', '.join(arcs)} form a loop ({' → '.join(loop)} → {loop[0]}) that no arc declares as feedback; "
                   f"mark the arc that closes it with feedback: true (it is drawn and laid out as feedback)")
    return out


# ----- order: what comes before what ------------------------------------------------------------


def acyclic_edges(pathway: Pathway) -> list[Edge]:
    """The arcs without the feedback arcs and the arcs a depth-first search (in pathway order)
    finds closing an undeclared loop: what runs "downstream"."""
    keep = [e for e in pathway.edges if not e.feedback]
    ids = list(pathway.nodes)
    out: dict[str, list[Edge]] = {n: [] for n in ids}
    for e in keep:
        out[e.source].append(e)
    state = dict.fromkeys(ids, 0)
    back: set[int] = set()
    for root in ids:
        if state[root]:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        state[root] = 1
        while stack:
            node, i = stack[-1]
            if i < len(out[node]):
                stack[-1] = (node, i + 1)
                e = out[node][i]
                if state[e.target] == 1:
                    back.add(e.index)
                elif state[e.target] == 0:
                    state[e.target] = 1
                    stack.append((e.target, 0))
            else:
                state[node] = 2
                stack.pop()
    return [e for e in keep if e.index not in back]


def topological(pathway: Pathway) -> list[str]:
    """Node ids upstream first (Kahn's order over :func:`acyclic_edges`, ties in pathway order)."""
    edges = acyclic_edges(pathway)
    indeg = dict.fromkeys(pathway.nodes, 0)
    for e in edges:
        indeg[e.target] += 1
    ready = [n for n in pathway.nodes if indeg[n] == 0]
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for e in edges:
            if e.source == n:
                indeg[e.target] -= 1
                if indeg[e.target] == 0:
                    ready.append(e.target)
    return order


# ----- activity and effects ---------------------------------------------------------------------

#: How strongly an active inhibitor lowers its target: activity = input / (1 + k × inhibition).
INHIBITION = 3.0
#: What a lost input leaves of a node with several activating inputs.
RESIDUE = 0.02


def activity(pathway: Pathway, off: Iterable[str] = ()) -> dict[str, float]:
    """A semi-quantitative steady state with the stimulus present: a node without activating
    inputs is at its basal level 1 (ligands, constitutive enzymes such as PTEN or a
    phosphodiesterase); otherwise at the geometric mean of its activating inputs (inputs that
    work together, such as PIP₃, PDK1 and mTORC2 on Akt: one lost leaves a small residue, 2 %,
    of its share; the only input lost leaves none); active inhibitors divide it by 1 + 3 × their
    activity. Nodes in ``off`` (knocked out, blocked by a drug) are 0. Feedback arcs are left
    out: they shape the dynamics, not which way a node changes."""
    off = set(off)
    edges = acyclic_edges(pathway)
    level: dict[str, float] = {}
    for n in topological(pathway):
        if n in off:
            level[n] = 0.0
            continue
        ins = [e for e in edges if e.target == n]
        pos = [level[e.source] for e in ins if e.sign > 0]
        neg = sum(level[e.source] for e in ins if e.sign < 0)
        if not pos:
            base = 1.0
        elif len(pos) == 1:
            base = pos[0]
        else:
            product = 1.0
            for x in pos:
                product *= max(x, RESIDUE)
            base = product ** (1.0 / len(pos))
        level[n] = base / (1.0 + INHIBITION * neg)
    return level


EFFECT_WORDS = ("up", "down", "off")


def effects(pathway: Pathway, before_off: Iterable[str], now_off: Iterable[str]) -> dict[str, str]:
    """How each node changes when the nodes in ``now_off`` are off as well as those in
    ``before_off``: ``up`` (more active, e.g. downstream of a lost inhibitor), ``down`` (less),
    ``off`` (no activity left). Nodes made off themselves are left out."""
    before_off, now_off = set(before_off), set(now_off)
    a, b = activity(pathway, before_off), activity(pathway, before_off | now_off)
    out: dict[str, str] = {}
    for n in pathway.nodes:
        if n in now_off or n in before_off:
            continue
        old, new = a[n], b[n]
        if new < 0.03 and old >= 0.03:
            out[n] = "off"
        elif old < 1e-9:
            if new > 0.03:
                out[n] = "up"
        elif new / old < 0.8:
            out[n] = "down"
        elif new / old > 1.25:
            out[n] = "up"
    return out


# ----- the signal -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One arc a signal runs along and what it does to the arc's target: ``effect`` +1 the
    target turns on, −1 it is turned off (an inhibitory arc from an active node, or an
    activating arc from a node the signal turned off: Akt ⊣ FOXO → *BCL2L11* falls), 0 it was
    reached before (the arc only flashes: a feedback arc onto a node already on). ``blocked``:
    the target is knocked out, blocked by a drug or held by an inhibitor — the signal stops."""

    edge: Edge
    effect: int = 1
    blocked: bool = False

    @property
    def inhibits(self) -> bool:
        return self.effect < 0


def signal_waves(pathway: Pathway, starts: Sequence[str], to: str | None = None, *, blocked: Iterable[str] = (),
                 feedback: bool = True, path: bool = False) -> list[list[Step]]:
    """The waves of a signal: each wave the arcs it runs along at once. From ``starts`` (on)
    breadth first along every arc, the sign carried (an inhibitor of an inhibitor turns its
    target on: Akt ⊣ TSC2 ⊣ Rheb → mTORC1); ``to``: only the shortest activating path to that
    node; ``path``: ``starts`` is the path itself, node by node. Feedback arcs come in a wave
    after the rest (``feedback: false`` leaves them out). A ``blocked`` node is reached but the
    signal stops there."""
    blocked = set(blocked)
    if path or to is not None:
        if path:
            route = [_arc(pathway, a, b) for a, b in zip(starts, starts[1:])]
        else:
            found = shortest_path(pathway, starts, to)  # type: ignore[arg-type]
            if found is None:
                return []
            route = found
        waves = []
        for e in route:
            waves.append([Step(e, e.sign, e.target in blocked)])
            if e.target in blocked:
                break
        return waves
    sign: dict[str, int] = {s: 1 for s in starts if s not in blocked}
    frontier = list(sign)
    shown: set[int] = set()
    waves: list[list[Step]] = []
    held: list[Edge] = []

    def step(e: Edge, nxt: list[str]) -> Step:
        effect = sign[e.source] * e.sign
        if e.target in blocked:
            return Step(e, effect, True)
        if e.target in sign:
            return Step(e, 0)
        sign[e.target] = effect
        nxt.append(e.target)
        return Step(e, effect)

    while frontier:
        wave: list[Step] = []
        nxt: list[str] = []
        for n in frontier:
            for e in pathway.out_edges(n):
                if e.index in shown or (e.feedback and not feedback):
                    continue
                shown.add(e.index)
                if e.feedback:
                    held.append(e)
                    continue
                wave.append(step(e, nxt))
        if wave:
            waves.append(wave)
        frontier = nxt
        if not frontier and held:
            wave = [step(e, frontier) for e in held]
            held = []
            waves.append(wave)
    return waves


def _arc(pathway: Pathway, a: str, b: str) -> Edge:
    for e in pathway.edges:
        if e.source == a and e.target == b:
            return e
    raise KeyError(f"{a}->{b}")


def shortest_path(pathway: Pathway, starts: Sequence[str], to: str) -> list[Edge] | None:
    """The shortest chain of activating, non-feedback arcs from one of ``starts`` to ``to``
    (breadth first, ties in pathway order), or ``None``."""
    previous: dict[str, Edge | None] = {s: None for s in starts}
    queue = list(starts)
    while queue:
        n = queue.pop(0)
        if n == to:
            route: list[Edge] = []
            while previous[n] is not None:
                e = previous[n]
                assert e is not None
                route.append(e)
                n = e.source
            return route[::-1]
        for e in pathway.out_edges(n):
            if e.sign > 0 and not e.feedback and e.target not in previous:
                previous[e.target] = e
                queue.append(e.target)
    return None


def signal_problem(pathway: Pathway, targets: Sequence[str], to: str | None) -> str | None:
    """Why a ``signal`` cannot run (``None``: it can): unknown nodes, a path whose
    neighbours are not joined by an arc in that direction, no activating path to ``to``."""
    ids = list(pathway.nodes)
    for t in [*targets, *([to] if to else [])]:
        if t not in pathway.nodes:
            return f"signal: unknown node '{t}'{did_you_mean(t, ids)}"
    if len(targets) > 1:
        if to is not None:
            return "signal: give either a path of nodes (signal: [a, b, c]) or a start and to:, not both"
        for a, b in zip(targets, targets[1:]):
            try:
                e = _arc(pathway, a, b)
            except KeyError:
                arcs = [x.ref for x in pathway.out_edges(a)]
                return f"signal: the path goes from '{a}' to '{b}', but no arc joins them that way (arcs from {a}: {', '.join(arcs) or 'none'})"
            if e.sign < 0:
                return f"signal: {a} -> {b} is an inhibitory arc: a signal does not pass it (inhibit: {a} shows it)"
        return None
    if to is not None and shortest_path(pathway, targets, to) is None:
        return f"signal: no activating path leads from '{targets[0]}' to '{to}'"
    if not any(e.sign > 0 for e in pathway.out_edges(targets[0])):
        return f"signal: nothing downstream of '{targets[0]}' is activated by it (no activating arc leaves it)"
    return None


def inhibitor_arcs(pathway: Pathway, node: str) -> list[Edge]:
    """The inhibitory arcs leaving ``node``."""
    return [e for e in pathway.out_edges(node) if e.sign < 0]


#: Drugs whose targets are known: name (lower case) → words one of which the node's label,
#: id or gene must contain (lower case), and what the drug is.
DRUGS: dict[str, tuple[tuple[str, ...], str]] = {
    "erlotinib": (("egfr", "erbb1"), "an EGFR tyrosine-kinase inhibitor"),
    "gefitinib": (("egfr", "erbb1"), "an EGFR tyrosine-kinase inhibitor"),
    "osimertinib": (("egfr",), "a third-generation EGFR inhibitor"),
    "lapatinib": (("egfr", "her2", "erbb2"), "an EGFR/HER2 inhibitor"),
    "cetuximab": (("egfr",), "an anti-EGFR antibody"),
    "trastuzumab": (("her2", "erbb2"), "an anti-HER2 antibody"),
    "imatinib": (("abl", "kit", "pdgfr"), "a BCR-ABL, KIT and PDGFR inhibitor"),
    "sotorasib": (("ras",), "a KRAS G12C inhibitor"),
    "adagrasib": (("ras",), "a KRAS G12C inhibitor"),
    "vemurafenib": (("raf",), "a BRAF V600E inhibitor"),
    "dabrafenib": (("raf",), "a BRAF inhibitor"),
    "encorafenib": (("raf",), "a BRAF inhibitor"),
    "trametinib": (("mek", "map2k"), "a MEK1/2 inhibitor"),
    "selumetinib": (("mek", "map2k"), "a MEK1/2 inhibitor"),
    "cobimetinib": (("mek", "map2k"), "a MEK1 inhibitor"),
    "ulixertinib": (("erk", "mapk"), "an ERK1/2 inhibitor"),
    "wortmannin": (("pi3k", "pik3"), "a PI3K inhibitor (tool compound)"),
    "ly294002": (("pi3k", "pik3"), "a PI3K inhibitor (tool compound)"),
    "alpelisib": (("pi3k", "pik3"), "a PI3Kα inhibitor"),
    "idelalisib": (("pi3k", "pik3"), "a PI3Kδ inhibitor"),
    "capivasertib": (("akt",), "an AKT inhibitor"),
    "mk-2206": (("akt",), "an allosteric AKT inhibitor"),
    "rapamycin": (("mtor",), "an mTORC1 inhibitor (with FKBP12)"),
    "sirolimus": (("mtor",), "an mTORC1 inhibitor (with FKBP12)"),
    "everolimus": (("mtor",), "an mTORC1 inhibitor"),
    "temsirolimus": (("mtor",), "an mTORC1 inhibitor"),
    "torin1": (("mtor",), "an ATP-competitive mTOR inhibitor (mTORC1 and mTORC2)"),
    "h-89": (("pka", "prka"), "a PKA inhibitor (tool compound)"),
    "ibmx": (("pde",), "a non-selective phosphodiesterase inhibitor"),
    "rolipram": (("pde",), "a PDE4 inhibitor"),
    "roflumilast": (("pde",), "a PDE4 inhibitor"),
    "sildenafil": (("pde",), "a PDE5 inhibitor"),
    "propranolol": (("adrenergic", "adrb", "β-ar", "β2-ar", "b2ar", "beta"), "a β-adrenergic receptor antagonist"),
    "pertussis toxin": (("gαi", "gai", "gα_i", "gnai"), "ADP-ribosylates Gαi, uncoupling it from its receptors"),
}


def drug_problem(pathway: Pathway, node: str, name: str) -> str | None:
    """Why the drug ``name`` cannot be shown blocking ``node`` (``None``: it can): a gene, a
    small molecule or an outcome is not a drug target here; a known drug on another target."""
    n = pathway.nodes[node]
    if n.kind.name == "gene":
        return f"drug: '{node}' is a gene; drugs here block proteins (to remove a gene, use knockout)"
    if n.kind.name in ("small_molecule", "phenotype", "drug"):
        return (f"drug: '{node}' is a {n.kind.name.replace('_', ' ')}; a drug blocks a protein (a receptor, an enzyme, a kinase) "
                f"or a complex — block the enzyme that makes it")
    known = DRUGS.get(name.strip().lower())
    if known is not None:
        words, what = known
        hay = " ".join(x for x in (n.id, n.plain, n.gene or "") if x).lower()
        if not any(w in hay for w in words):
            return f"drug: {name} is {what}; '{n.plain}' is not its target"
    return None


__all__ = [
    "ARROWS", "BANDS", "DRUGS", "EDGE_TYPES", "EFFECTS", "EFFECT_WORDS", "INHIBITION", "NODE_KINDS", "ROLES", "SMALL_MOLECULES",
    "Band", "Edge", "EdgeSpec", "EdgeType", "Mark", "Node", "NodeKind", "NodeSpec", "Pathway", "PathwaySpec", "Step",
    "activity", "acyclic_edges", "band_name", "build_pathway", "drug_problem", "edge_type_name", "effects", "inhibitor_arcs",
    "loop_warnings", "merged_specs", "parse_arrows", "shortest_path", "signal_problem", "signal_waves", "topological",
    "undeclared_loops",
]
