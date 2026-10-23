"""``pathway``: a signalling pathway drawn with SBGN-inspired notation (DESIGN.md §95.12) —
nodes (ligands, receptors, proteins, complexes, second messengers, genes, outcomes) with their
states (GDP / GTP, P marks), arcs (activation arrows, inhibition T-bars, catalysis circles,
phosphorylation, binding, translocation, transcription) laid out automatically in compartment
bands (extracellular space / plasma membrane / cytosol / ER / mitochondrion / nucleus), and
the actions ``signal``, ``inhibit``, ``knockout``, ``drug`` and ``amplify``
(``scenes/pathway_actions.py``) on the graph's logic (``vidgen.cellworld.pathway``)."""

import html
import logging
from functools import lru_cache
from typing import Any, Literal

import numpy as np

from vidgen.api import *

from .molecule import Modification
from .pathway_play import PathwayPlay

log = logging.getLogger("vidgen.scenes")

#: Text grows up to this factor over the requested size when the pathway has room, and shrinks
#: in these steps down to the readable size.
GROWTH = (1.3, 1.15, 1.0, 0.9, 0.8, 0.72, 0.65, 0.58, 0.52)
#: Covering a label costs this many times covering a node (text over text is a lint error).
TEXT_WEIGHT = 3.0
#: At the readable size, a layout this much too large is still drawn without a warning (scaled).
FLOOR_SHRINK = 0.97
#: Small text (state marks, arc labels, band names) relative to the node labels.
SMALL = 0.72
#: Opacity of node tints at rest (lit, off and held looks: ``pathway_play``).
TINT = 0.12
#: Stroke widths (Manim units of stroke).
NODE_STROKE, EDGE_STROKE = 2.6, 2.6
#: Labels wrap onto two lines beyond this many characters.
WRAP_CHARS = 9
#: What the state badges say.
BADGE_TEXT = {"gdp": "GDP", "gtp": "GTP"}


class PathwayNode(SceneParams):
    """A node: ``{id, kind, label, in, gene, state, marks, role}``; a string is an id (a
    protein labelled by its id)."""

    also_accepts = (str,)

    id: str
    """Its name for arcs and actions (letters, digits, _ . -)."""
    kind: str | None = None
    """ligand, receptor, protein (default), kinase, phosphatase, g_protein, gtpase, gef, gap, adaptor, enzyme, transcription_factor, complex, small_molecule, gene, phenotype, drug."""
    label: str | None = None
    """What it is called (default: the id): a gene's symbol (italic, checked for the species), a protein name (roman; Gα_s writes s as a subscript), a molecule (Ca2+, PIP3, cAMP)."""
    compartment: str | None = Field(None, alias="in")
    """Its compartment (band): extracellular, plasma_membrane (membrane), cytosol, er, mitochondrion, nucleus (nucleoplasm); default by kind (ligand: extracellular, receptor and g_protein: plasma_membrane, gene and transcription_factor: nucleus, else cytosol)."""
    gene: str | None = None
    """A protein's gene symbol (checked for the species; a protein written like its gene is refused: mouse TRP53 is the protein of Trp53)."""
    state: str | None = None
    """Its state at the start: inactive / active, gdp / gtp (G proteins and GTPases), silent / transcribed (genes)."""
    marks: list[Modification] = Field(default_factory=list, max_length=4)
    """Modifications shown from the start: {mark: P, at: Ser133} (P, Ub, Ac, Me; the residue checked)."""
    role: Literal["activator", "inhibitor"] | None = None
    """Its declared role: its arcs must agree (an inhibitor's arc that activates is refused)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        return {"id": data} if isinstance(data, str) else data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        return {"anyOf": [{"type": "string"}, handler(core_schema)]}

    def spec(self, where: str) -> Any:
        marks = tuple((m.mark, m.at) for m in self.marks) if "marks" in self.model_fields_set else None
        return cell_pathway.NodeSpec(self.id, self.kind, self.label, self.compartment, self.gene, self.state, marks, self.role, where)


class PathwayEdge(SceneParams):
    """An arc: ``{from, to, type, effect, site, feedback, label, indirect}``, or ``"a -> b"``
    (activates), ``"a -| b"`` (inhibits), ``"a -o b"`` (catalyses), ``"a => b"``
    (translocates)."""

    also_accepts = (str,)

    source: str = Field(alias="from")
    """The node it starts at."""
    to: str
    """The node it acts on."""
    type: str = "activates"
    """activates, inhibits, catalyses, phosphorylates, dephosphorylates, binds, translocates, transcribes, expresses, converts."""
    effect: Literal["activates", "inhibits"] | None = None
    """Whether it activates or inhibits its target, where the type allows both (an inhibitory phosphorylation: Akt → GSK3β; repression: transcribes); a contradiction with the type is refused."""
    site: str | None = None
    """(De)phosphorylation: the residue (Ser133, T308, Y1068), checked; shown as pS133 on the target."""
    feedback: bool = False
    """It closes a feedback loop (drawn and laid out against the flow; loops not declared are warned about)."""
    label: TranslatableStr | None = None
    """A short note on the arc (GEF: GDP → GTP, cAMP → AMP)."""
    indirect: bool = False
    """Through steps not drawn (dashed)."""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            arcs = cell_pathway.parse_arrows(data)
            if len(arcs) > 1:
                raise ValueError(f"{data!r} is a chain of {len(arcs)} arcs; list it under the scene's edges")
            a, b, kind = arcs[0]
            return {"from": a, "to": b, "type": kind}
        return data

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        return {"anyOf": [{"type": "string", "pattern": "(->|-\\||-o|=>)"}, handler(core_schema)]}

    def spec(self, where: str) -> Any:
        return cell_pathway.EdgeSpec(self.source.strip(), self.to.strip(), self.type, self.effect, self.site, self.feedback,
                                     self.label, self.indirect, where)


@lru_cache(maxsize=32)
def _build(spec: Any) -> Pathway:
    return build_pathway(spec)


@scene("pathway")
class PathwayScene(PathwayPlay, NarratedScene):
    """A signalling pathway in SBGN-inspired notation, laid out automatically in compartment
    bands (extracellular space, plasma membrane, cytosol, ER, mitochondrion, nucleus: columns
    left to right in landscape frames, rows top to bottom in portrait ones). Nodes are drawn by
    kind (proteins as rounded boxes, complexes with cut corners, small molecules as ellipses,
    genes with an italic symbol, outcomes as hexagons) with their state (GDP / GTP, pS133);
    arcs activate (arrow), inhibit (T-bar), catalyse (circle), (de)phosphorylate (P on the arc),
    bind (dot), translocate (dashed, e.g. into the nucleus), regulate transcription. Built-in
    templates (gpcr_camp_pka, rtk_ras_mapk, pi3k_akt) can be used as they are or changed.
    Everything is checked: unknown nodes, arcs against declared effects, nodes in impossible
    compartments, names in the wrong case for the species. The actions signal, inhibit,
    knockout, drug and amplify animate the graph's logic; focus moves the camera.

    Action targets: ``title``, each node's id, ``edge:<from>-><to>``, each band
    (``band:cytosol``…) and ``pathway`` (everything)."""

    outro = 0.5
    target_patterns = ("title", "<id>", "edge:<from>-><to>", "band:<name>", "pathway")
    #: The actions signal, inhibit, knockout, drug and amplify act on this scene type (and focus).
    pathway_actions = True
    mid_still_actions = frozenset({"signal", "inhibit", "knockout", "drug", "amplify"})

    class Params(SceneParams):
        title: TranslatableStr = ""
        """Title (in the header band at the top)."""
        template: Literal["gpcr_camp_pka", "rtk_ras_mapk", "pi3k_akt"] | None = None
        """A built-in pathway to start from: gpcr_camp_pka (glucagon → GCGR → Gαs → adenylyl cyclase → cAMP → PKA → CREB → PCK1, PDE4), rtk_ras_mapk (EGF → EGFR → Grb2/SOS → Ras → Raf → MEK → ERK → Elk-1 → FOS, RasGAP, ERK ⊣ SOS), pi3k_akt (RTK → PI3K → PIP3 ⊣ PTEN → PDK1/mTORC2 → Akt ⊣ TSC2 ⊣ Rheb → mTORC1; ⊣ GSK3β, ⊣ FOXO)."""
        nodes: list[PathwayNode] = Field(default_factory=list, max_length=30)
        """The nodes: an id, or {id, kind, label, in, gene, state, marks, role}; with a template, a node of a template id changes it."""
        edges: list[PathwayEdge] = Field(default_factory=list, max_length=60)
        """The arcs: 'a -> b', 'a -| b', 'a -o b', 'a => b', or {from, to, type, effect, site, feedback, label, indirect}; with a template, an arc between the same nodes replaces it."""
        remove: list[str] = Field(default_factory=list, max_length=30)
        """Template nodes (ids) or arcs ('a->b') to leave out."""
        species: str = "human"
        """Nomenclature of gene and protein names: human, mouse, rat, yeast, fission_yeast, fly, zebrafish, e_coli, arabidopsis."""
        direction: Literal["auto", "LR", "TB"] = "auto"
        """LR: bands as columns, the signal left to right; TB: bands as rows, top to bottom; auto: LR in landscape frames, TB in portrait ones (the other if it keeps text much larger)."""
        reveal: Literal["all", "bands", "nodes"] = "all"
        """all: the whole pathway in the first beat; bands: one compartment per step; nodes: one rank (layer) per step, arcs with their nodes."""
        bands: bool = True
        """Draw and name the compartment bands (the plasma membrane as a bilayer, the nuclear envelope as a double membrane with pores)."""
        edge_labels: bool | Literal["auto"] = "auto"
        """Show the arcs' labels: true, false, or auto (when they leave the text nearly as large; in a long left-to-right pathway they are left out)."""
        title_size: ThemeSize = "heading"
        """Title size."""
        size: ThemeSize = "body"
        """Node label size (up to 1.3x larger when there is room; smaller, not below the readable minimum, when the pathway is large)."""

        def spec(self) -> Any:
            return cell_pathway.PathwaySpec(
                tuple(n.spec(f"nodes[{k}] ({n.id})") for k, n in enumerate(self.nodes)),
                tuple(e.spec(f"edges[{k}]") for k, e in enumerate(self.edges)),
                self.species, self.template, tuple(self.remove))

        def pathway(self) -> Pathway:
            return _build(self.spec())

        @model_validator(mode="after")
        def _check(self) -> "PathwayScene.Params":
            if not self.nodes and self.template is None:
                raise ValueError("nodes: a pathway needs nodes (or a template: gpcr_camp_pka, rtk_ras_mapk, pi3k_akt)")
            try:
                self.pathway()
            except VidgenError as error:
                raise ValueError(str(error)) from None
            return self

    @classmethod
    def target_names(cls, params: Any) -> list[str]:
        p = params.pathway()
        names = (["title"] if params.title else []) + list(p.nodes)
        names += [f"edge:{e.ref}" for e in p.edges]
        names += [f"band:{b}" for b in p.bands] if params.bands else []
        return names + ["pathway"]

    @classmethod
    def target_text(cls, params: Any, name: str) -> str | None:
        """What target ``name`` is called on screen (a node's label), for the narration lint rules."""
        node = params.pathway().nodes.get(name)
        return node.plain if node is not None else None

    @classmethod
    def target_kind(cls, name: str) -> str:
        """``node``, ``edge``, ``band``, ``title`` or ``pathway``."""
        if name.startswith("edge:"):
            return "edge"
        if name.startswith("band:"):
            return "band"
        return name if name in ("title", "pathway") else "node"

    @classmethod
    def validate_project(cls, params: Any, project: Any) -> list[str]:
        """Loops no arc declares as feedback are warned about (they still draw)."""
        where = f"pathway '{params.title}'" if params.title else "a pathway scene"
        for message in cell_pathway.loop_warnings(params.pathway()):
            log.warning("%s: %s", where, message)
        return []

    @classmethod
    def action_sequence_problems(cls, spec: Any, params: Any, uses: list[Any]) -> list[tuple[str, str]]:
        """Knockouts, drugs and inhibitors replayed in beat and ``at`` order (an effect lasts
        until its ``until`` beat): a node knocked out twice, a drug on a knocked-out node, a
        signal from a node that is off."""
        from .pathway_actions import sequence_problems

        return sequence_problems(spec, params, uses)

    # ----- building -----------------------------------------------------------------------------

    def construct(self) -> None:
        p = self.params
        self.pathway = p.pathway()
        body = self.safe_area
        title = None
        if p.title:
            title = chart_title(p.title, size=p.title_size, area=self.safe_area)
            body = body.below(title, gap=0.3)
        self.body = body
        self._colors()
        self._texts()
        plan = self._choose(body)
        self._draw(plan, body)
        self._state_init()
        self._register(title)

    def _colors(self) -> None:
        th = self.theme
        self.bg = th.background
        self.ink = th.color("text")
        self.dim_ink = th.color("dim")
        self.hi = th.color("highlight")
        self.bad = th.color("accent")
        self.good = th.color("tertiary")
        # badges and P marks: a strong tint on a dark background, a pale one on a light one (dark
        # text either way, never a mid-tone that reads with neither)
        rgb = [int(self.bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        self.pill_mix = 0.8 if 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] < 128 else 0.3

        def kind_color(token: str) -> str:
            return th.palette_color(2) if token == "purple" else th.color(token)

        self.node_color = {n.id: kind_color(n.kind.color) for n in self.pathway.nodes.values()}
        self.edge_color = {e.index: (self.bad if e.sign < 0 else mix_colors(self.ink, self.bg, 0.72)) for e in self.pathway.edges}

    # ----- text -------------------------------------------------------------------------------

    def _lines(self, markup: str, plain: str) -> list[str]:
        """The label on one line, or two at the space nearest its middle when it is long."""
        if len(plain) <= WRAP_CHARS or " " not in markup:
            return [markup]
        spaces = [i for i, ch in enumerate(markup) if ch == " "]
        mid = len(markup) / 2
        cut = min(spaces, key=lambda i: abs(i - mid))
        return [markup[:cut], markup[cut + 1:]]

    def _markup(self, lines: list[str], size: float, color: str, weight: str = NORMAL) -> VGroup:
        rows = [self.markup(line, size=size, color=color, weight=weight) for line in lines]
        group = VGroup(*rows)
        if len(rows) > 1:
            group.arrange(DOWN, buff=0.06 * size / 32)
        return group

    def _texts(self) -> None:
        """Node labels, state marks, arc labels and band names, made once at reference sizes
        (measured for the layout; scaled to the size chosen)."""
        self.size0 = float(self.theme.size(self.params.size))
        self.small0 = self.size0 * SMALL
        self.labels0: dict[str, VGroup] = {}
        for n in self.pathway.nodes.values():
            self.labels0[n.id] = self._markup(self._lines(n.markup, n.plain), self.size0, self.ink)
        self.edge_labels0: dict[int, VGroup] = {}
        if self.params.edge_labels is not False:
            for e in self.pathway.edges:
                if e.label:
                    self.edge_labels0[e.index] = self._markup([chem_markup_arrows(e.label)], self.small0, self.dim_ink)
        self.badge_keys = {n.id: self._badge_keys(n) for n in self.pathway.nodes.values()}
        self.badge_w0: dict[str, float] = {}
        self.badge_h0 = 0.0
        for keys in self.badge_keys.values():
            for key in keys:
                if key not in self.badge_w0:
                    t = self.markup(BADGE_TEXT.get(key, key), size=self.small0)
                    self.badge_w0[key] = t.width
                    self.badge_h0 = max(self.badge_h0, t.height)

    def _badge_keys(self, n: Any) -> list[str]:
        """The state marks a node may show: GDP / GTP, the marks written on it, the sites
        phosphorylated by the arcs into it."""
        keys: list[str] = ["gdp", "gtp"] if n.guanine else []
        keys += [m.text for m in n.marks if m.text not in keys]
        for e in self.pathway.in_edges(n.id):
            if e.site is not None and e.type.name == "phosphorylates" and e.site.text not in keys:
                keys.append(e.site.text)
        return keys

    def _badge_room(self, nid: str, sf: float, u: float) -> tuple[float, float]:
        """Width the node's badges take along its top edge, and their height (0, 0 without)."""
        keys = self.badge_keys[nid]
        if not keys:
            return 0.0, 0.0
        h = self.badge_h0 * sf + 0.12 * u
        widths = {k: max(self.badge_w0[k] * sf + 0.22 * u, h + 0.04 * u) for k in keys}
        if "gdp" in widths:
            widths["gtp"] = max(widths.pop("gdp"), widths["gtp"])
        return sum(widths.values()) + 0.05 * u * (len(widths) - 1) + 0.2 * u, h

    # ----- layout -----------------------------------------------------------------------------

    def _directions(self) -> list[str]:
        d = self.params.direction
        if d != "auto":
            return [d]
        return ["TB", "LR"] if self.is_portrait else ["LR", "TB"]

    def _fit(self, direction: str, body: Any, labels: bool) -> dict[str, Any]:
        """The largest size factor (from :data:`GROWTH`, not below the readable size) at which
        the layout fits the body, or the readable size's plan when none does."""
        floor = readable_size() * 1.02 / self.size0   # lint measures some words a little smaller
        plan = None
        for f in GROWTH:
            plan = self._plan(direction, max(f, floor), body, labels)
            if plan["fits"] or f <= floor:
                break
        assert plan is not None
        if not plan["fits"] and plan["shrink"] >= FLOOR_SHRINK:
            plan["fits"] = True   # readable_size keeps a 5 % margin over lint's minimum: a little less is still readable
        return plan

    @staticmethod
    def _score(plan: dict[str, Any]) -> float:
        """How large the text ends up: the size factor, times the shrink when it does not fit."""
        return plan["factor"] * min(1.0, plan["shrink"])

    def _choose(self, body: Any) -> dict[str, Any]:
        """The direction (and whether arc labels are shown, for ``edge_labels: auto``) with
        the largest text that fits the body."""
        setting = self.params.edge_labels
        chosen: dict[str, Any] | None = None
        best = -1.0
        for rank, direction in enumerate(self._directions()):
            bias = 1.0 if rank == 0 else 1 / 1.12
            plan = self._fit(direction, body, bool(setting) and bool(self.edge_labels0))
            if setting == "auto" and self.edge_labels0:
                bare = self._fit(direction, body, False)
                if self._score(plan) < 0.9 * self._score(bare):
                    plan = bare
            if self._score(plan) * bias > best:
                best, chosen = self._score(plan) * bias, plan
        assert chosen is not None
        if not chosen["fits"]:
            log.warning("scene '%s': the pathway's %d nodes do not fit this frame at the readable size; it is drawn smaller "
                        "(split it, or use remove: to leave out nodes)", self.spec.id, len(self.pathway.nodes))
        return chosen

    def _small_factor(self, factor: float) -> float:
        """The factor of the small texts: their reference size times it, never below readable."""
        return max(factor, readable_size() * 1.02 / self.small0)

    def _plan(self, direction: str, factor: float, body: Any, labels: bool) -> dict[str, Any]:
        u = self.size0 * factor / 32
        sf = self._small_factor(factor)
        bands = list(self.pathway.bands)
        nodes = []
        for n in self.pathway.nodes.values():
            lab = self.labels0[n.id]
            w, h = self._outer(n, lab.width * factor, lab.height * factor, u)
            bw, bh = self._badge_room(n.id, sf, u)
            # badges widen a node in a top-to-bottom layout; left to right, where the width is
            # the scarce length of the flow, they may reach past its ends
            w, h = (max(w, bw) if direction == "TB" else max(w, 0.6 * bw)), h + 0.5 * bh
            nodes.append(cell_pathway_layout.LayoutNode(n.id, bands.index(n.band), w, h, PATHWAY_BANDS[n.band].membrane,
                                                        n.kind.name == "phenotype"))
        edges = []
        for e in self.pathway.edges:
            lab = self.edge_labels0.get(e.index) if labels else None
            size = (lab.width * sf + 0.16 * u, lab.height * sf + 0.1 * u) if lab is not None else None
            edges.append(cell_pathway_layout.LayoutEdge(e.source, e.target, e.feedback, size))
        band_text = self.small0 * sf / 32
        label_room = (0.5 * band_text + 0.12 * u) if self.params.bands else 0.0
        layout = cell_pathway_layout.pathway_layout(
            nodes, edges, direction=direction, rank_gap=0.38 * u, band_gap=0.4 * u, node_gap=0.34 * u, row_gap=0.7 * u,
            band_pad=0.1 * u, label_room=label_room, port_spacing=0.16 * u, label_margin=0.08 * u,
            outcomes_beside=direction == "LR")
        shrink = min(body.width / max(layout.width, 1e-6), body.height / max(layout.height, 1e-6))
        return {"layout": layout, "direction": direction, "factor": factor, "small": sf, "u": u, "labels": labels,
                "fits": shrink >= 1.0 - 1e-6, "shrink": shrink}

    @staticmethod
    def _outer(n: Any, w: float, h: float, u: float) -> tuple[float, float]:
        """A node's outer size round a label ``w`` × ``h``."""
        glyph = n.kind.glyph
        px, py = 0.18 * u, 0.16 * u
        if glyph == "simple_chemical":
            return max(w * 1.15 + 2 * px, 0.95 * u), h + 2.4 * py
        if glyph == "phenotype":
            return w + 2 * px + 0.28 * (h + 2 * py), h + 2 * py
        if glyph == "complex":
            return max(w + 2.4 * px, 1.0 * u), h + 2.4 * py
        if glyph == "nucleic_acid":
            return max(w + 2 * px, 0.95 * u), h + 2 * py + 0.12 * u
        return max(w + 2 * px, 0.95 * u), h + 2 * py

    # ----- drawing ----------------------------------------------------------------------------

    def _draw(self, plan: dict[str, Any], body: Any) -> None:
        self.plan = plan
        layout = plan["layout"]
        self.direction = plan["direction"]
        self.u = plan["u"]
        f, sf = plan["factor"], plan["small"]
        scale = min(1.0, plan["shrink"])
        center = np.array([float(body.center[0]), float(body.center[1]), 0.0])
        self.center = center
        self.scale_ = scale

        def at(x: float, y: float) -> np.ndarray:
            return center + scale * np.array([x, y, 0.0])

        self.at = at
        self.layout = layout
        u = self.u * scale
        self.us = u
        self.band_mobs: dict[str, VGroup] = {}
        if self.params.bands:
            self._draw_bands(layout, at, u, sf * scale)
        self.nodes: dict[str, dict[str, Any]] = {}
        for n in self.pathway.nodes.values():
            self.nodes[n.id] = self._draw_node(n, layout.nodes[n.id], at, u, f * scale, sf * scale)
        self.edges: dict[int, dict[str, Any]] = {}
        for e in self.pathway.edges:
            self.edges[e.index] = self._draw_edge(e, layout.routes[e.index], at, u, sf * scale)
        if self.params.bands:
            self._pores(u)
        self._place_labels()

    def _band_fill(self, name: str) -> tuple[str, float]:
        th = self.theme
        return {
            "extracellular": (self.bg, 0.0),
            "plasma_membrane": (th.color("secondary"), 0.0),
            "cytosol": (th.color("primary"), 0.05),
            "er": (th.color("tertiary"), 0.08),
            "mitochondrion": (th.color("secondary"), 0.08),
            "nucleus": (th.palette_color(2), 0.09),
        }[name]

    def _draw_bands(self, layout: Any, at: Any, u: float, sf: float) -> None:
        names = list(self.pathway.bands)
        boxes = {names[b.index]: b for b in layout.bands}
        lr = self.direction == "LR"
        membrane_ink = mix_colors(self.theme.color("secondary"), self.bg, 0.7)
        self.envelopes: list[tuple[str, float]] = []   # (band boundary kind, main coordinate in scene units)
        self.band_labels: dict[str, tuple[VGroup, tuple[float, float, float, float]]] = {}
        self.envelope_mobs: dict[str, VGroup] = {}
        for k, name in enumerate(names):
            box = boxes[name]
            band = PATHWAY_BANDS[name]
            lo, hi = at(box.x0, box.y0), at(box.x1, box.y1)
            parts: list[Mobject] = []
            if band.membrane:
                main_mid = self._row_main(name, at)
                thick = 0.34 * u
                if lr:
                    rect = Rectangle(width=thick, height=hi[1] - lo[1]).move_to(np.array([main_mid, (lo[1] + hi[1]) / 2, 0]))
                    lines = [Line(np.array([main_mid + s * thick / 2, lo[1], 0]), np.array([main_mid + s * thick / 2, hi[1], 0])) for s in (-1, 1)]
                else:
                    rect = Rectangle(width=hi[0] - lo[0], height=thick).move_to(np.array([(lo[0] + hi[0]) / 2, main_mid, 0]))
                    lines = [Line(np.array([lo[0], main_mid + s * thick / 2, 0]), np.array([hi[0], main_mid + s * thick / 2, 0])) for s in (-1, 1)]
                rect.set_fill(mix_colors(self.theme.color("secondary"), self.bg, 0.16), opacity=1).set_stroke(width=0)
                for line in lines:
                    line.set_stroke(membrane_ink, width=2.4)
                parts += [rect, *lines]
            else:
                color, opacity = self._band_fill(name)
                x0, y0, x1, y1 = lo[0], lo[1], hi[0], hi[1]
                # a band next to a membrane reaches the membrane's middle
                for j, other in ((k - 1, "before"), (k + 1, "after")):
                    if 0 <= j < len(names) and PATHWAY_BANDS[names[j]].membrane:
                        mid = self._row_main(names[j], at)
                        if lr:
                            x0, x1 = (mid, x1) if other == "before" else (x0, mid)
                        else:
                            y0, y1 = (y0, mid) if other == "before" else (mid, y1)
                rect = Rectangle(width=abs(x1 - x0), height=abs(y1 - y0)).move_to(np.array([(x0 + x1) / 2, (y0 + y1) / 2, 0]))
                rect.set_fill(mix_colors(color, self.bg, opacity) if opacity else self.bg, opacity=1 if opacity else 0).set_stroke(width=0)
                parts.append(rect)
                if k > 0 and not PATHWAY_BANDS[names[k - 1]].membrane:
                    edge = x0 if lr else y1
                    double = name in ("nucleus", "mitochondrion")
                    self.envelopes.append((name, edge))
                    boundary = self._boundary(edge, lr, (y0, y1) if lr else (x0, x1), double, u, name)
                    self.envelope_mobs[name] = boundary
                    parts.append(boundary)
            text = PATHWAY_BANDS[name].short if lr else PATHWAY_BANDS[name].label
            words = self.markup(text, size=self.small0 * sf, color=self.dim_ink)
            plate = RoundedRectangle(width=words.width + 0.1 * u, height=words.height + 0.06 * u, corner_radius=0.05 * u)
            plate.set_fill(self.bg, opacity=0.75).set_stroke(width=0)
            label = VGroup(plate, words)
            group = VGroup(*parts)
            group.set_z_index(-2)
            label.set_z_index(1)
            self.band_mobs[name] = VGroup(group, label)
            self.band_labels[name] = (label, (lo[0], lo[1], hi[0], hi[1]))   # placed by _place_labels

    def _row_main(self, band: str, at: Any) -> float:
        """The scene coordinate (x in LR, y in TB) of a membrane row's middle."""
        ids = [n.id for n in self.pathway.nodes.values() if n.band == band]
        pts = [at(self.layout.nodes[i].x, self.layout.nodes[i].y) for i in ids]
        axis = 0 if self.direction == "LR" else 1
        return float(np.mean([pt[axis] for pt in pts]))

    def _boundary(self, edge: float, lr: bool, span: tuple[float, float], double: bool, u: float, name: str) -> VGroup:
        """The membrane between two bands at main coordinate ``edge``: one line (ER), two
        (the nuclear envelope, the mitochondrion's)."""
        ink = mix_colors(self.theme.palette_color(2) if name == "nucleus" else self.theme.color("secondary"), self.bg, 0.75)
        offsets = (-0.05 * u, 0.05 * u) if double else (0.0,)
        lines = VGroup()
        for off in offsets:
            if lr:
                a, b = np.array([edge + off, span[0], 0]), np.array([edge + off, span[1], 0])
            else:
                a, b = np.array([span[0], edge + off, 0]), np.array([span[1], edge + off, 0])
            lines.add(Line(a, b).set_stroke(ink, width=2.2))
        return lines

    def _pores(self, u: float) -> None:
        """Gaps in the nuclear envelope where arcs cross it (the nuclear pores)."""
        if "nucleus" not in self.band_mobs:
            return
        cuts = []
        lr = self.direction == "LR"
        for name, edge in getattr(self, "envelopes", []):
            if name != "nucleus":
                continue
            for parts in self.edges.values():
                pts = parts["path"].points
                axis = 0 if lr else 1
                for a, b in zip(pts[:-1], pts[1:]):
                    if (a[axis] - edge) * (b[axis] - edge) <= 0 and abs(a[axis] - b[axis]) > 1e-9:
                        t = (edge - a[axis]) / (b[axis] - a[axis])
                        cuts.append((a + (b - a) * t)[1 - axis])
                        break
            envelope = self.envelope_mobs.get("nucleus")
            if envelope is None or not cuts:
                continue
            gap = 0.22 * u
            for line in list(envelope):
                start, end = line.get_start(), line.get_end()
                axis = 1 if lr else 0
                lo, hi = sorted((start[axis], end[axis]))
                pieces, at_ = [], lo
                for c in sorted(cuts):
                    if c - gap / 2 > at_:
                        pieces.append((at_, c - gap / 2))
                    at_ = max(at_, c + gap / 2)
                if at_ < hi:
                    pieces.append((at_, hi))
                envelope.remove(line)
                for p0, p1 in pieces:
                    a, b = start.copy(), start.copy()
                    a[axis], b[axis] = p0, p1
                    envelope.add(Line(a, b).set_stroke(line.get_stroke_color(), width=line.get_stroke_width()))
                for c in sorted(cuts):   # the pore complex's rim
                    for s in (-1, 1):
                        a = start.copy()
                        a[axis] = c + s * gap / 2
                        envelope.add(Dot(a, radius=0.03 * u, color=line.get_stroke_color()))

    def _shape(self, n: Any, w: float, h: float, u: float) -> VMobject:
        glyph = n.kind.glyph
        if glyph == "simple_chemical":
            return Ellipse(width=w, height=h)
        if glyph == "phenotype":
            d = h / 2
            pts = [(-w / 2, 0), (-w / 2 + d, h / 2), (w / 2 - d, h / 2), (w / 2, 0), (w / 2 - d, -h / 2), (-w / 2 + d, -h / 2)]
            return Polygon(*[np.array([x, y, 0]) for x, y in pts])
        if glyph == "complex":
            c = min(0.18 * u, h / 3)
            pts = [(-w / 2 + c, h / 2), (w / 2 - c, h / 2), (w / 2, h / 2 - c), (w / 2, -h / 2 + c), (w / 2 - c, -h / 2),
                   (-w / 2 + c, -h / 2), (-w / 2, -h / 2 + c), (-w / 2, h / 2 - c)]
            return Polygon(*[np.array([x, y, 0]) for x, y in pts])
        if glyph == "nucleic_acid":
            r = min(0.2 * u, h / 2.5)
            shape = VMobject()
            shape.start_new_path(np.array([-w / 2, h / 2, 0]))
            shape.add_line_to(np.array([w / 2, h / 2, 0]))
            shape.add_line_to(np.array([w / 2, -h / 2 + r, 0]))
            shape.append_points(Arc(radius=r, start_angle=0, angle=-PI / 2).shift(np.array([w / 2 - r, -h / 2 + r, 0])).points)
            shape.add_line_to(np.array([-w / 2 + r, -h / 2, 0]))
            shape.append_points(Arc(radius=r, start_angle=-PI / 2, angle=-PI / 2).shift(np.array([-w / 2 + r, -h / 2 + r, 0])).points)
            shape.add_line_to(np.array([-w / 2, h / 2, 0]))
            return shape
        if glyph == "drug":
            return RoundedRectangle(width=w, height=h, corner_radius=h / 2 - 1e-4)
        return RoundedRectangle(width=w, height=h, corner_radius=min(0.16 * u, h / 3))

    def _rest_look(self, n: Any, shape: VMobject) -> None:
        color = self.node_color[n.id]
        shape.set_fill(color, opacity=TINT).set_stroke(color, width=NODE_STROKE)

    def _draw_node(self, n: Any, place: Any, at: Any, u: float, f: float, sf: float) -> dict[str, Any]:
        c = at(place.x, place.y)
        w, h = place.width * self.scale_, place.height * self.scale_
        shape = self._shape(n, w, h, u).move_to(c)
        self._rest_look(n, shape)
        label = self.labels0[n.id].copy().scale(f).move_to(c)
        label.set_z_index(1)       # over a knockout's cross
        if n.kind.glyph == "nucleic_acid":
            label.shift(UP * 0.05 * u)
        parts: dict[str, Any] = {"shape": shape, "label": label, "center": c, "w": w, "h": h, "badges": {}, "shown": set()}
        # state marks along the top edge, from the right: GDP / GTP, then modifications; the
        # label sits below them (the node was made taller for them)
        for key in self.badge_keys[n.id]:
            parts["badges"][key] = self._badge(key, sf)
        if parts["badges"]:
            label.shift(DOWN * 0.25 * max(b.height for b in parts["badges"].values()))
        self._place_badges(parts, n)
        group = VGroup(shape, label, *parts["badges"].values())
        parts["group"] = group
        visible = [shape, label] + [parts["badges"][k] for k in parts["shown"]]
        parts["visible"] = visible
        return parts

    def _badge(self, key: str, sf: float) -> VGroup:
        t = self.markup(BADGE_TEXT.get(key, key), size=self.small0 * sf, color=self.ink)
        if key in ("gdp", "gtp"):
            color = self.good if key == "gtp" else self.dim_ink
        else:
            color = self.theme.color("highlight")
        pill = RoundedRectangle(width=max(t.width + 0.22 * self.us, t.height + 0.16 * self.us), height=t.height + 0.12 * self.us,
                                corner_radius=(t.height + 0.12 * self.us) / 2 - 1e-4)
        pill.set_fill(mix_colors(color, self.bg, self.pill_mix), opacity=1).set_stroke(color, width=1.8)
        t.set_color(text_color_on(mix_colors(color, self.bg, self.pill_mix)))
        t.move_to(pill)
        group = VGroup(pill, t)
        group.set_z_index(3)
        return group

    def _place_badges(self, parts: dict[str, Any], n: Any) -> None:
        """Badges sit on the node's top edge from its right end (GDP and GTP share a place);
        the state and the marks written on the node show from the start, the sites the signal
        phosphorylates appear with it."""
        c, w, h = parts["center"], parts["w"], parts["h"]
        x = c[0] + w / 2 - 0.08 * self.us
        badges = parts["badges"]
        if "gdp" in badges:
            for key in ("gdp", "gtp"):
                badges[key].move_to(np.array([x - badges[key].width / 2, c[1] + h / 2, 0]))
            x -= max(badges["gdp"].width, badges["gtp"].width) + 0.05 * self.us
            parts["shown"].add("gtp" if n.state == "gtp" else "gdp")
        for key, b in badges.items():
            if key in ("gdp", "gtp"):
                continue
            b.move_to(np.array([x - b.width / 2, c[1] + h / 2, 0]))
            x -= b.width + 0.05 * self.us
        parts["shown"] |= {m.text for m in n.marks}

    def _draw_edge(self, e: Any, route: Any, at: Any, u: float, sf: float) -> dict[str, Any]:
        color = self.edge_color[e.index]
        pts = [at(x, y) for x, y in route.points]
        main = RIGHT if self.direction == "LR" else DOWN
        head_len = float(np.clip(0.2 * u, 0.1, 0.24))
        end, prev = pts[-1], pts[-2]
        tangent = _unit(end - prev)
        bar = e.sign < 0
        circle = e.type.name == "catalyses"
        back = head_len * (0.25 if bar else (0.9 if not circle else 1.6))
        stops = pts[:-1] + [end - tangent * back]
        path = VMobject()
        path.start_new_path(stops[0])
        for (a, b), curve in zip(zip(stops, stops[1:]), route.curves):
            if curve:
                d = float(np.dot(b - a, main))
                path.add_cubic_bezier_curve_to(a + main * d / 2, b - main * d / 2, b)
            else:
                path.add_line_to(b)
        path.set_stroke(color, width=EDGE_STROKE).set_fill(opacity=0)
        line: VMobject = path
        if e.dashed:
            length = sum(float(np.linalg.norm(b - a)) for a, b in zip(stops, stops[1:]))
            line = DashedVMobject(path, num_dashes=max(4, int(length / (0.16 * u))), dashed_ratio=0.55)
            line.set_stroke(color, width=EDGE_STROKE)
        side = np.array([-tangent[1], tangent[0], 0.0])
        if bar:
            tip_at = end - tangent * 0.04 * u
            head: VMobject = Line(tip_at + side * head_len * 0.75, tip_at - side * head_len * 0.75).set_stroke(color, width=EDGE_STROKE * 1.5)
        elif circle:
            r = head_len * 0.55
            head = Circle(radius=r).move_to(end - tangent * r).set_stroke(color, width=EDGE_STROKE).set_fill(self.bg, opacity=1)
        else:
            head = Polygon(end, end - tangent * head_len + side * head_len * 0.5, end - tangent * head_len - side * head_len * 0.5)
            head.set_fill(color, opacity=1).set_stroke(color, width=1)
        parts: dict[str, Any] = {"line": line, "path": path, "head": head, "color": color}
        items: list[Mobject] = [line, head]
        mid = path.point_from_proportion(0.5)
        mark = None
        if e.type.mark in ("P", "-P"):
            text = self.markup("P" if e.type.mark == "P" else "−P", size=self.small0 * sf, color=self.ink)
            disc = Circle(radius=max(text.width, text.height) / 2 + 0.07 * u)
            ring = self.theme.color("highlight")
            disc.set_fill(mix_colors(ring, self.bg, self.pill_mix), opacity=1).set_stroke(ring, width=1.8)
            text.set_color(text_color_on(mix_colors(ring, self.bg, self.pill_mix)))
            mark = VGroup(disc, text.move_to(disc)).move_to(mid)
        elif e.type.mark == "dot":
            mark = Dot(mid, radius=0.07 * u, color=color)
        if mark is not None and path.get_arc_length() < 2.6 * max(mark.width, mark.height):
            mark = None    # too short an arc (a node beside its target): the badge on the target tells
        if mark is not None:
            mark.set_z_index(2)
            items.append(mark)
        parts["mark"] = mark
        label = None
        if self.plan["labels"] and e.index in self.edge_labels0:
            text = self.edge_labels0[e.index].copy().scale(sf)
            plate = RoundedRectangle(width=text.width + 0.12 * u, height=text.height + 0.08 * u, corner_radius=0.06 * u)
            plate.set_fill(self.bg, opacity=0.9).set_stroke(width=0).move_to(text)
            plate.set_z_index(1)
            text.set_z_index(2)
            label = VGroup(plate, text)     # placed once every node and arc is drawn (_place_labels)
            items.append(label)
        parts["label"] = label
        parts["group"] = VGroup(*items)
        return parts

    # ----- labels that keep clear of nodes and arcs ----------------------------------------------

    def _obstacles(self) -> tuple[list[tuple[float, float, float, float]], np.ndarray]:
        """Boxes (x0, y0, x1, y1) of the nodes with their badges and of the arcs' marks, and
        points along the arcs."""
        boxes = []
        for parts in self.nodes.values():
            mob = VGroup(parts["shape"], *parts["badges"].values())
            boxes.append(_box(mob))
        points = []
        for parts in self.edges.values():
            if parts["mark"] is not None:
                boxes.append(_box(parts["mark"]))
            boxes.append(_box(parts["head"]))
            path = parts["path"]
            points += [path.point_from_proportion(t / 24) for t in range(25)]
        return boxes, np.array(points) if points else np.zeros((0, 3))

    def _spot(self, candidates: list[np.ndarray], w: float, h: float, boxes: list[Any], points: np.ndarray,
              anchor: np.ndarray | None = None) -> np.ndarray:
        """The candidate centre (in order of preference) where a ``w`` × ``h`` box covers the
        least: other boxes (area), arc points, the frame's edge; and, with an ``anchor``, the
        nearer to it the better."""
        safe = self.safe_area
        best, best_cost = candidates[0], None
        for k, p in enumerate(candidates):
            x0, y0, x1, y1 = p[0] - w / 2, p[1] - h / 2, p[0] + w / 2, p[1] + h / 2
            cost = 0.0
            for bx0, by0, bx1, by1, weight in boxes:
                ox = min(x1, bx1) - max(x0, bx0)
                oy = min(y1, by1) - max(y0, by0)
                if ox > 0 and oy > 0:
                    cost += weight * (10 * ox * oy + 2.0)
            if len(points):
                inside = (points[:, 0] > x0) & (points[:, 0] < x1) & (points[:, 1] > y0) & (points[:, 1] < y1)
                cost += 0.05 * float(np.count_nonzero(inside))
            if x0 < safe.x0 or x1 > safe.x1 or y0 < safe.y0 or y1 > safe.y1:
                cost += 50
            if anchor is not None:
                cost += 0.15 * float(np.linalg.norm(p[:2] - anchor[:2])) / self.us
            cost += 0.002 * k
            if best_cost is None or cost < best_cost - 1e-9:
                best, best_cost = p, cost
        return best

    def _place_labels(self) -> None:
        """Band names in a free corner of their band; arc labels beside their arc where they
        cover no node, mark or other label (each placed one becomes an obstacle)."""
        boxes, points = self._obstacles()
        first = len(boxes)
        u = self.us
        lr = self.direction == "LR"
        for name, (label, band_box) in getattr(self, "band_labels", {}).items():
            w, h = label.width, label.height
            x0, y0, x1, y1 = band_box
            pad = 0.1 * u
            if PATHWAY_BANDS[name].membrane:
                m = self._row_main(name, self.at)
                off = 0.17 * u + pad + (w / 2 if lr else h / 2)
                if lr:
                    cands = [np.array([m, y1 - h / 2 - pad, 0]), np.array([m, y0 + h / 2 + pad, 0]),
                             np.array([m - off, y1 - h / 2 - pad, 0]), np.array([m + off, y1 - h / 2 - pad, 0]),
                             np.array([m - off, y0 + h / 2 + pad, 0]), np.array([m + off, y0 + h / 2 + pad, 0])]
                else:   # along the membrane, clear of the nodes in it (above or below them), wherever it is free
                    row = [VGroup(p["shape"], *p["badges"].values()) for nid, p in self.nodes.items() if self.pathway.nodes[nid].band == name]
                    up = max(float(r.get_top()[1]) for r in row) - m + pad + h / 2
                    down = m - min(float(r.get_bottom()[1]) for r in row) + pad + h / 2
                    xs = [x0 + w / 2 + pad + (x1 - x0 - w - 2 * pad) * t / 8 for t in range(9)]
                    cands = [np.array([x, m + dy, 0]) for dy in (up, -down, off, -off) for x in xs]
            else:
                corners = [(x0 + w / 2 + pad, y1 - h / 2 - pad), (x1 - w / 2 - pad, y1 - h / 2 - pad),
                           (x0 + w / 2 + pad, y0 + h / 2 + pad), (x1 - w / 2 - pad, y0 + h / 2 + pad)]
                if lr:
                    corners = [((x0 + x1) / 2, y1 - h / 2 - pad), ((x0 + x1) / 2, y0 + h / 2 + pad)] + corners
                cands = [np.array([x, y, 0]) for x, y in corners]
            spot = self._spot(cands, w + 0.1 * u, h + 0.06 * u, boxes, points)
            label.move_to(spot)
            boxes.append(_box(label, TEXT_WEIGHT))
        for k, parts in self.edges.items():
            label = parts["label"]
            if label is None:
                continue
            path = parts["path"]
            w, h = label.width, label.height
            dxs = [0.0, *(s * (w / 2 + 0.12 * u) for s in (1, -1)), *(s * (w + 0.25 * u) for s in (1, -1))]
            dys = [0.0, *(s * (h / 2 + 0.1 * u) for s in (1, -1)), *(s * (h + 0.35 * u) for s in (1, -1)),
                   *(s * (1.5 * h + 0.6 * u) for s in (1, -1))]
            shifts = sorted((np.array([dx, dy, 0.0]) for dx in dxs for dy in dys), key=lambda v: float(np.hypot(v[0], v[1])))
            cands = [path.point_from_proportion(t) + shift for shift in shifts for t in (0.5, 0.35, 0.65)]
            spot = self._spot(cands, w + 0.06 * u, h + 0.04 * u, boxes, points, anchor=path.point_from_proportion(0.5))
            label.move_to(spot)
            boxes.append(_box(label, TEXT_WEIGHT))
        self.label_boxes = boxes[first:]

    # ----- targets and reveal -------------------------------------------------------------------

    def _register(self, title: Mobject | None) -> None:
        p = self.params
        steps: list[Any] = []
        self.title_target = self.target("title", title, entrance=lambda: [FadeIn(title)]) if title is not None else None
        self.band_targets: dict[str, Target] = {}
        for name, mob in self.band_mobs.items():
            self.band_targets[name] = self.target(f"band:{name}", mob, entrance=lambda m=mob: [FadeIn(m)])
        self.node_targets: dict[str, Target] = {}
        for nid, parts in self.nodes.items():
            self.node_targets[nid] = self.target(nid, parts["group"], outline=parts["shape"],
                                                 on_fill=[(parts["label"], parts["shape"])],
                                                 entrance=lambda nid=nid: self._node_entrance(nid))
        self.edge_targets: dict[int, Target] = {}
        for e in self.pathway.edges:
            parts = self.edges[e.index]
            self.edge_targets[e.index] = self.target(f"edge:{e.ref}", parts["group"], entrance=lambda k=e.index: [self._grow(k)])
        everything = VGroup(*self.band_mobs.values(), *[n["group"] for n in self.nodes.values()], *[x["group"] for x in self.edges.values()])
        self.whole_target = self.target("pathway", everything, entrance=lambda: self._reveal_all())
        groups = self._step_groups()
        for k, (bands, nodes) in enumerate(groups):
            def build(bands: list[str] = bands, nodes: list[str] = nodes, first: bool = k == 0) -> list[Animation]:
                anims: list[Animation] = []
                if first and self.title_target is not None:
                    anims += self.entrance(self.title_target)
                return anims + self._reveal(bands, nodes)
            steps.append(build)
        self.reveal(steps, fraction=0.8, cap=1.8)
        self.finish()

    def _step_groups(self) -> list[tuple[list[str], list[str]]]:
        p = self.params
        bands = list(self.band_mobs)
        order = sorted(self.pathway.nodes, key=lambda i: (self.layout.nodes[i].rank, self.layout.nodes[i].order))
        if p.reveal == "all":
            return [(bands, order)]
        if p.reveal == "bands":
            return [([b], [n for n in order if self.pathway.nodes[n].band == b]) for b in self.pathway.bands]
        ranks: dict[int, list[str]] = {}
        for n in order:
            ranks.setdefault(self.layout.nodes[n].rank, []).append(n)
        out = []
        seen: set[str] = set()
        for r in sorted(ranks):
            new_bands = [b for b in bands if b not in seen and any(self.pathway.nodes[n].band == b for n in ranks[r])]
            seen |= set(new_bands)
            out.append((new_bands, ranks[r]))
        return out

    def _reveal(self, bands: list[str], nodes: list[str]) -> list[Animation]:
        """Bands, then their nodes, then the arcs whose ends are both on screen."""
        chain: list[Animation] = []
        band_anims = [a for b in bands for a in self.entrance(self.band_targets[b])]
        if band_anims:
            chain.append(AnimationGroup(*band_anims))
        node_anims = [a for n in nodes for a in self.entrance(self.node_targets[n])]
        if node_anims:
            chain.append(LaggedStart(*node_anims, lag_ratio=0.08))
        shown = {n for n in self.pathway.nodes if self.is_shown(self.node_targets[n])} | set(nodes)
        edge_anims = [self._grow(e.index) for e in self.pathway.edges
                      if e.source in shown and e.target in shown and not self.is_shown(self.edge_targets[e.index])]
        if edge_anims:
            chain.append(LaggedStart(*edge_anims, lag_ratio=0.1))
        return [Succession(*chain)] if len(chain) > 1 else chain

    def _reveal_all(self) -> list[Animation]:
        return self._reveal(list(self.band_mobs), list(self.pathway.nodes))

    def _node_entrance(self, nid: str) -> list[Animation]:
        parts = self.nodes[nid]
        return [FadeIn(VGroup(*parts["visible"]), scale=0.9)]

    def _grow(self, k: int) -> Animation:
        parts = self.edges[k]
        line = Create(parts["line"], lag_ratio=1.0 if isinstance(parts["line"], DashedVMobject) else 0.0, rate_func=linear)
        rest: list[Animation] = [FadeIn(parts["head"], scale=0.6)]
        if parts["mark"] is not None:
            rest.append(FadeIn(parts["mark"], scale=0.6))
        if parts["label"] is not None:
            rest.append(FadeIn(VGroup(*[m for m in parts["group"] if m is not parts["line"] and m is not parts["head"] and m is not parts["mark"]])))
        return Succession(line, AnimationGroup(*rest))

    # ----- runtime state (the actions) ---------------------------------------------------------

    def _state_init(self) -> None:
        self.knocked: set[str] = set()
        self.drugged: dict[str, str] = {}
        self.held: set[str] = set()

    def blocked_nodes(self) -> set[str]:
        """Nodes a signal cannot pass: knocked out, blocked by a drug, held by an inhibitor."""
        return set(self.knocked) | set(self.drugged) | set(self.held)

    def off_nodes(self) -> set[str]:
        return set(self.knocked) | set(self.drugged)


def chem_markup_arrows(text: str) -> str:
    """An arc label as markup: plain text with the molecule names in it typeset (cAMP → AMP,
    Ca2+, PIP3)."""
    words = text.split(" ")
    out = []
    for w in words:
        core = w.rstrip(",.;:)")
        tail = w[len(core):]
        lead = ""
        if core.startswith("("):
            lead, core = "(", core[1:]
        if core and (any(ch.isdigit() for ch in core) and core[:1].isupper() and len(core) <= 8):
            out.append(lead + chem_markup(core) + tail)
        else:
            out.append(html.escape(w, quote=False))
    return " ".join(out)


def _box(mob: Mobject, weight: float = 1.0) -> tuple[float, float, float, float, float]:
    """``mob``'s bounding box as an obstacle: (x0, y0, x1, y1, how much covering it costs)."""
    lo, hi = mob.get_corner(DL), mob.get_corner(UR)
    return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]), weight


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else RIGHT