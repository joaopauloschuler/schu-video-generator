"""Step 207: the ``pathway`` scene — the model and its rules (nodes, arcs, compartments, names),
the three templates checked against the textbook account, the layout (deterministic, no route
through a node, bands in order), the signal's waves and the effects of knockouts and drugs, the
actions' validation, and tiny renders in 16:9 and 9:16."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen.cellworld import pathway as pw
from vidgen.cellworld.pathway_layout import LayoutEdge, LayoutNode, pathway_layout, route_hits, samples
from vidgen.cellworld.pathway_templates import TEMPLATES
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def build(nodes: list[dict[str, Any]], edges: list[dict[str, Any]] | None = None, **kw: Any) -> pw.Pathway:
    specs = tuple(pw.NodeSpec(**n) for n in nodes)
    arcs = tuple(pw.EdgeSpec(**e) for e in edges or [])
    return pw.build_pathway(pw.PathwaySpec(specs, arcs, **kw))


def template(name: str) -> pw.Pathway:
    return pw.build_pathway(pw.PathwaySpec(template=name))


def layout_of(p: pw.Pathway, direction: str, *, sizes: dict[str, tuple[float, float]] | None = None, labels: bool = False) -> Any:
    bands = list(p.bands)
    nodes = [LayoutNode(n.id, bands.index(n.band), *(sizes or {}).get(n.id, (1.2 + 0.05 * len(n.plain), 0.5)),
                        pw.BANDS[n.band].membrane, n.kind.name == "phenotype") for n in p.nodes.values()]
    edges = [LayoutEdge(e.source, e.target, e.feedback, (0.9, 0.25) if labels and e.label else None) for e in p.edges]
    return pathway_layout(nodes, edges, direction=direction, label_room=0.3, outcomes_beside=direction == "LR")  # type: ignore[arg-type]


# ----- the model and its rules ----------------------------------------------------------------------


def test_templates_follow_the_textbook() -> None:
    gpcr = template("gpcr_camp_pka")
    assert gpcr.bands == ("extracellular", "plasma_membrane", "cytosol", "nucleus")
    assert gpcr.nodes["gas"].guanine and gpcr.nodes["gas"].band == "plasma_membrane" and gpcr.nodes["gas"].plain == "Gαs"
    assert gpcr.edge("ac->camp").type.name == "catalyses" and gpcr.edge("pde->camp").inhibits
    assert gpcr.edge("pka_n->creb").site == pw.Mark("P", "S133") and gpcr.edge("pka_n->creb").site.text == "pS133"
    assert gpcr.edge("pka->pka_n").type.name == "translocates" and gpcr.nodes["pka_n"].band == "nucleus"
    assert gpcr.edge("creb->pck1").type.name == "transcribes" and gpcr.nodes["pck1"].markup == "<i>PCK1</i>"
    assert gpcr.edge("pka->pde").feedback and gpcr.loops == ()       # PKA → PDE4 ⊣ cAMP → PKA, declared
    mapk = template("rtk_ras_mapk")
    assert mapk.nodes["ras"].guanine and mapk.nodes["ras"].band == "plasma_membrane"
    assert mapk.edge("sos->ras").sign > 0 and mapk.nodes["sos"].kind.name == "gef"
    assert mapk.edge("rasgap->ras").inhibits and mapk.nodes["rasgap"].kind.name == "gap"
    assert [mapk.edge(r).type.name for r in ("raf->mek", "mek->erk")] == ["phosphorylates"] * 2
    assert mapk.edge("erk->sos").feedback and mapk.edge("erk->sos").inhibits and mapk.loops == ()
    akt = template("pi3k_akt")
    assert akt.nodes["pip3"].markup == "PIP<sub>3</sub>" and akt.nodes["pip3"].band == "plasma_membrane"
    assert akt.edge("pip2->pip3").type.name == "converts" and akt.edge("pi3k->pip3").type.name == "catalyses"
    assert akt.edge("pten->pip3").inhibits and akt.nodes["pten"].kind.name == "phosphatase"
    assert {akt.edge(r).site.text for r in ("pdk1->akt", "mtorc2->akt")} == {"pT308", "pS473"}
    assert akt.edge("akt->gsk3b").inhibits and akt.edge("akt->gsk3b").site.text == "pS9"
    assert akt.edge("akt->tsc2").inhibits and akt.edge("tsc2->rheb").inhibits and akt.nodes["tsc2"].kind.name == "gap"
    assert akt.edge("akt->foxo").inhibits and akt.nodes["foxo"].band == "nucleus"
    for name in TEMPLATES:
        assert pw.loop_warnings(template(name)) == []


def test_unknown_nodes_and_arcs_are_refused_with_a_suggestion() -> None:
    with pytest.raises(VidgenError, match=r"unknown node 'ercc'; did you mean 'erk'"):
        build([{"id": "mek", "kind": "kinase"}, {"id": "erk", "kind": "kinase"}], [{"source": "mek", "target": "ercc"}])
    with pytest.raises(VidgenError, match="arc type 'activate'|did you mean 'activates'"):
        build([{"id": "a"}, {"id": "b"}], [{"source": "a", "target": "b", "type": "activat"}])
    with pytest.raises(VidgenError, match="kind 'kinas'; did you mean 'kinase'"):
        build([{"id": "a", "kind": "kinas"}])
    with pytest.raises(VidgenError, match="points to itself"):
        build([{"id": "a"}], [{"source": "a", "target": "a"}])
    with pytest.raises(VidgenError, match="template 'gpcr'"):
        pw.build_pathway(pw.PathwaySpec(template="gpcr"))
    with pytest.raises(VidgenError, match="the name of a target"):
        build([{"id": "cytosol"}])


@pytest.mark.parametrize(("nodes", "edge", "message"), [
    ([{"id": "a", "kind": "kinase"}, {"id": "b"}], {"type": "inhibits", "effect": "activates"}, "they contradict"),
    ([{"id": "a", "kind": "gap"}, {"id": "b", "kind": "gtpase"}], {"type": "activates"}, "a GAP turns its GTPase off"),
    ([{"id": "a", "kind": "gef"}, {"id": "b", "kind": "gtpase"}], {"type": "inhibits"}, "a GEF turns its GTPase on"),
    ([{"id": "a", "kind": "phosphatase"}, {"id": "b"}], {"type": "phosphorylates"}, "write type: dephosphorylates"),
    ([{"id": "a", "kind": "kinase"}, {"id": "b"}], {"type": "dephosphorylates"}, "it adds phosphates"),
    ([{"id": "a", "kind": "adaptor"}, {"id": "b"}], {"type": "phosphorylates"}, "only kinases"),
    ([{"id": "a", "kind": "kinase", "role": "inhibitor"}, {"id": "b"}], {"type": "activates"}, "declared role: inhibitor"),
    ([{"id": "a", "kind": "drug"}, {"id": "b"}], {"type": "activates"}, "a drug node inhibits"),
    ([{"id": "a", "kind": "phenotype"}, {"id": "b"}], {"type": "activates"}, "a phenotype is an outcome"),
    ([{"id": "a", "kind": "kinase"}, {"id": "b", "kind": "gene", "label": "FOS"}], {"type": "activates"}, "write type: transcribes"),
    ([{"id": "a", "kind": "kinase", "compartment": "nucleus"}, {"id": "b", "kind": "gene", "label": "FOS"}], {"type": "transcribes"},
     "transcription factor"),
    ([{"id": "a", "kind": "transcription_factor", "compartment": "cytosol"}, {"id": "b", "kind": "gene", "label": "FOS"}],
     {"type": "transcribes"}, "binds its gene's DNA in the nucleus"),
    ([{"id": "a", "kind": "kinase", "label": "ERK"}, {"id": "b", "kind": "kinase", "label": "ERK"}], {"type": "translocates"},
     "both nodes are in the cytosol"),
    ([{"id": "a", "kind": "kinase", "label": "ERK"}, {"id": "b", "kind": "kinase", "label": "MEK", "compartment": "nucleus"}],
     {"type": "translocates"}, "the same label"),
    ([{"id": "a", "kind": "protein", "label": "X", "compartment": "nucleus"}, {"id": "b", "label": "X", "compartment": "membrane"}],
     {"type": "translocates"}, "translocate it to the cytosol first"),
    ([{"id": "a", "kind": "kinase"}, {"id": "b"}], {"type": "binds", "site": "Ser9"}, "site is the residue"),
    ([{"id": "a", "kind": "kinase"}, {"id": "b"}], {"type": "phosphorylates", "site": "Lys9"}, "not on Lys9"),
    ([{"id": "a", "kind": "enzyme"}, {"id": "b", "kind": "kinase"}], {"type": "converts"}, "one small molecule into another"),
])
def test_arcs_against_their_declared_effects_are_refused(nodes: list[dict[str, Any]], edge: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        build(nodes, [{"source": "a", "target": "b", **edge}])


@pytest.mark.parametrize(("node", "message"), [
    ({"id": "fos", "kind": "gene", "label": "FOS", "compartment": "cytosol"}, "genes are DNA"),
    ({"id": "egfr", "kind": "receptor", "compartment": "cytosol"}, "a receptor node is a membrane receptor"),
    ({"id": "egf", "kind": "ligand", "compartment": "nucleus"}, "a ligand reaches its receptor from outside"),
    ({"id": "camp", "kind": "small_molecule", "label": "cAMP", "compartment": "membrane"}, "cAMP is made by adenylyl cyclase"),
    ({"id": "pip3", "kind": "small_molecule", "label": "PIP3", "compartment": "cytosol"}, "lipid of the inner leaflet"),
    ({"id": "gs", "kind": "g_protein", "compartment": "nucleus"}, "anchored to the cytosolic face"),
    ({"id": "k", "kind": "kinase", "compartment": "outside"}, "act inside the cell"),
    ({"id": "k", "compartment": "golgi"}, "compartment 'golgi'"),
    ({"id": "k", "kind": "g_protein", "state": "active"}, "is gdp or gtp"),
])
def test_impossible_compartments_and_states_are_refused(node: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        build([node])


def test_names_follow_each_species_nomenclature() -> None:
    assert build([{"id": "p53", "kind": "transcription_factor", "label": "p53", "gene": "TP53"}]).nodes["p53"].gene == "TP53"
    assert build([{"id": "g", "kind": "gene", "label": "Trp53"}], species="mouse").nodes["g"].markup == "<i>Trp53</i>"
    with pytest.raises(VidgenError, match="mouse gene symbols .* write Trp53"):
        build([{"id": "g", "kind": "gene", "label": "TRP53"}], species="mouse")
    with pytest.raises(VidgenError, match="written like the mouse gene .* write TRP53"):
        build([{"id": "p", "kind": "protein", "label": "Trp53", "gene": "Trp53"}], species="mouse")
    with pytest.raises(VidgenError, match=r"budding yeast \(S. cerevisiae\) gene .* write Cdc28"):
        build([{"id": "p", "kind": "kinase", "label": "CDC28"}], species="yeast")
    with pytest.raises(VidgenError, match="human gene symbols are italic capitals"):
        build([{"id": "g", "kind": "gene", "label": "fos"}])
    with pytest.raises(VidgenError, match="species 'human2'"):
        build([{"id": "g"}], species="human2")
    assert build([{"id": "g", "label": "Gα_s", "kind": "g_protein"}]).nodes["g"].markup == "Gα<sub>s</sub>"
    assert build([{"id": "c", "label": "Ca2+", "kind": "small_molecule"}]).nodes["c"].markup == "Ca<sup>2+</sup>"
    marked = build([{"id": "h", "kind": "protein", "marks": (("P", "Ser15"), ("Ac", "K382"))}]).nodes["h"]
    assert [m.text for m in marked.marks] == ["pS15", "Ac K382"]


def test_loops_not_declared_as_feedback_are_warned_about() -> None:
    nodes = [{"id": "a", "kind": "kinase"}, {"id": "b", "kind": "kinase"}, {"id": "c", "kind": "phosphatase"}]
    loop = build(nodes, [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}, {"source": "c", "target": "a", "type": "inhibits"}])
    assert loop.loops == (("a", "b", "c"),)
    assert "a->b, b->c, c->a form a loop (a → b → c → a)" in pw.loop_warnings(loop)[0]
    declared = build(nodes, [{"source": "a", "target": "b"}, {"source": "b", "target": "c"},
                             {"source": "c", "target": "a", "type": "inhibits", "feedback": True}])
    assert declared.loops == () and pw.loop_warnings(declared) == []


def test_templates_are_changed_by_nodes_edges_and_remove() -> None:
    spec = pw.PathwaySpec((pw.NodeSpec("glucagon", label="Adrenaline"), pw.NodeSpec("gcgr", label="β2-AR", gene=None)),
                          (pw.EdgeSpec("pde", "camp", "inhibits", label="hydrolysis"),), template="gpcr_camp_pka", remove=("gluconeogenesis",))
    p = pw.build_pathway(spec)
    assert p.nodes["glucagon"].plain == "Adrenaline" and p.nodes["gcgr"].kind.name == "receptor"
    assert "gluconeogenesis" not in p.nodes and all("gluconeogenesis" not in e.ref for e in p.edges)
    assert p.edge("pde->camp").label == "hydrolysis" and len([e for e in p.edges if e.ref == "pde->camp"]) == 1
    with pytest.raises(VidgenError, match="the template has no node 'glucose'"):
        pw.build_pathway(pw.PathwaySpec(template="gpcr_camp_pka", remove=("glucose",)))
    with pytest.raises(VidgenError, match="this pathway has no template"):
        pw.build_pathway(pw.PathwaySpec((pw.NodeSpec("a"),), remove=("a",)))


def test_arrow_shorthand() -> None:
    assert pw.parse_arrows("pde -| camp") == [("pde", "camp", "inhibits")]
    assert pw.parse_arrows("a -> b -> c") == [("a", "b", "activates"), ("b", "c", "activates")]
    assert pw.parse_arrows("ac -o camp") == [("ac", "camp", "catalyses")]
    assert pw.parse_arrows("erk => erk_n") == [("erk", "erk_n", "translocates")]
    with pytest.raises(ValueError, match="is not an arc"):
        pw.parse_arrows("a b")


# ----- the signal and the effects ------------------------------------------------------------------


def refs(waves: list[list[pw.Step]]) -> list[list[str]]:
    return [[s.edge.ref for s in wave] for wave in waves]


def test_signal_runs_wave_by_wave_and_feedback_last() -> None:
    gpcr = template("gpcr_camp_pka")
    waves = pw.signal_waves(gpcr, ["glucagon"])
    assert refs(waves)[:6] == [["glucagon->gcgr"], ["gcgr->gas"], ["gas->ac"], ["ac->camp"], ["camp->pka"], ["pka->pka_n"]]
    assert refs(waves)[-2:] == [["pka->pde"], ["pde->camp"]]                # the feedback fires after the rest
    assert waves[-1][0].effect == 0                                        # cAMP was reached already: the arc only flashes
    assert refs(pw.signal_waves(gpcr, ["glucagon"], feedback=False))[-1] == ["pck1->gluconeogenesis"]
    assert refs(pw.signal_waves(gpcr, ["glucagon"], to="creb")) == [["glucagon->gcgr"], ["gcgr->gas"], ["gas->ac"], ["ac->camp"],
                                                                    ["camp->pka"], ["pka->pka_n"], ["pka_n->creb"]]
    assert refs(pw.signal_waves(gpcr, ["gcgr", "gas", "ac"], path=True)) == [["gcgr->gas"], ["gas->ac"]]


def test_signal_signs_and_blocks() -> None:
    akt = template("pi3k_akt")
    steps = {s.edge.ref: s for wave in pw.signal_waves(akt, ["gf"]) for s in wave}
    assert steps["akt->tsc2"].effect == -1 and steps["tsc2->rheb"].effect == 1 and steps["rheb->mtorc1"].effect == 1   # Akt ⊣ TSC2 ⊣ Rheb → mTORC1
    assert steps["akt->foxo"].effect == -1 and steps["foxo->bcl2l11"].effect == -1                                  # FOXO off: BIM falls
    assert steps["pdk1->akt"].effect == 0                     # Akt reached through PIP3 first; its pT308 still appears
    mapk = template("rtk_ras_mapk")
    blocked = pw.signal_waves(mapk, ["egf"], blocked={"mek"})
    assert refs(blocked)[-1] == ["raf->mek"] and blocked[-1][0].blocked
    assert all("erk" not in r for wave in refs(blocked) for r in wave)


def test_effects_of_knockouts_and_drugs() -> None:
    akt = template("pi3k_akt")
    pten = pw.effects(akt, [], ["pten"])
    assert {pten[n] for n in ("pip3", "pdk1", "akt", "rheb", "mtorc1", "growth")} == {"up"}
    assert {pten[n] for n in ("tsc2", "gsk3b", "foxo", "bcl2l11", "apoptosis")} == {"down"}
    pi3k = pw.effects(akt, [], ["pi3k"])
    assert pi3k["akt"] == "down" and pi3k["foxo"] == "up" and pi3k["mtorc1"] == "down"
    gpcr = template("gpcr_camp_pka")
    assert set(pw.effects(gpcr, [], ["pde"]).values()) == {"up"} and pw.effects(gpcr, [], ["pde"])["camp"] == "up"
    assert set(pw.effects(gpcr, [], ["ac"]).values()) == {"off"}
    mapk = template("rtk_ras_mapk")
    assert pw.effects(mapk, [], ["rasgap"])["ras"] == "up"
    assert pw.effects(mapk, [], ["mek"]) == {n: "off" for n in ("erk", "erk_n", "elk1", "fos", "proliferation")}
    assert pw.effects(mapk, ["mek"], ["rasgap"]).get("erk") is None        # nothing more to lose downstream of a blocked MEK


def test_signal_and_drug_problems() -> None:
    gpcr = template("gpcr_camp_pka")
    assert pw.signal_problem(gpcr, ["glucagon"], None) is None
    assert "did you mean 'glucagon'" in pw.signal_problem(gpcr, ["glucgon"], None)
    assert "no activating path leads from 'creb' to 'gcgr'" in pw.signal_problem(gpcr, ["creb"], "gcgr")
    assert "no arc joins them that way" in pw.signal_problem(gpcr, ["gas", "gcgr"], None)
    assert "inhibitory arc" in pw.signal_problem(gpcr, ["pde", "camp"], None)
    assert "nothing downstream" in pw.signal_problem(gpcr, ["gluconeogenesis"], None)
    mapk = template("rtk_ras_mapk")
    assert pw.drug_problem(mapk, "mek", "trametinib") is None and pw.drug_problem(mapk, "mek", "Xyz-123") is None
    assert "trametinib is a MEK1/2 inhibitor; 'ERK' is not its target" in pw.drug_problem(mapk, "erk", "trametinib")
    assert "is a gene" in pw.drug_problem(mapk, "fos", "x")
    assert "block the enzyme that makes it" in pw.drug_problem(template("gpcr_camp_pka"), "camp", "x")


# ----- the layout ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(TEMPLATES))
@pytest.mark.parametrize("direction", ["LR", "TB"])
def test_layout_is_deterministic_banded_and_routes_avoid_nodes(name: str, direction: str) -> None:
    p = template(name)
    first, again = layout_of(p, direction, labels=True), layout_of(p, direction, labels=True)
    assert first == again
    assert route_hits(first, pad=0.02) == []
    assert first.crossings <= 1
    # bands follow each other along the main axis, each node inside its band
    boxes = {list(p.bands)[b.index]: b for b in first.bands}
    for nid, place in first.nodes.items():
        box = boxes[p.nodes[nid].band]
        assert box.x0 - 1e-6 <= place.x <= box.x1 + 1e-6 and box.y0 - 1e-6 <= place.y <= box.y1 + 1e-6
    mains = [((b.x0 + b.x1) / 2 if direction == "LR" else -(b.y0 + b.y1) / 2) for b in first.bands]
    assert mains == sorted(mains)
    # every route starts on its source's outline and ends on its target's
    for route in first.routes:
        for end, nid in ((route.points[0], route.source), (route.points[-1], route.target)):
            x0, y0, x1, y1 = first.nodes[nid].box()
            assert min(abs(end[0] - x0), abs(end[0] - x1), abs(end[1] - y0), abs(end[1] - y1)) < 1e-6
            assert x0 - 1e-6 <= end[0] <= x1 + 1e-6 and y0 - 1e-6 <= end[1] <= y1 + 1e-6


def test_layout_rows_satellites_and_feedback() -> None:
    gpcr = template("gpcr_camp_pka")
    lay = layout_of(gpcr, "TB")
    row = lay.ranks[1]
    assert row == ["gcgr", "gas", "ac"]                                  # along the membrane in the order of its arcs
    assert lay.nodes["pde"].rank == lay.nodes["camp"].rank               # PDE4 beside cAMP, not a rank of its own
    assert lay.nodes["pde"].x < lay.nodes["camp"].x                       # top to bottom: on its left
    across = layout_of(gpcr, "LR")
    assert across.nodes["pde"].y < across.nodes["camp"].y                 # left to right: below it, clear of cAMP's badges
    lateral = [r for r in lay.routes if r.lateral]
    assert {(r.source, r.target) for r in lateral} == {("gcgr", "gas"), ("gas", "ac"), ("pde", "camp")}
    assert lay.nodes["gluconeogenesis"].rank > lay.nodes["pck1"].rank   # top to bottom: the outcome below its gene
    assert layout_of(gpcr, "LR").nodes["gluconeogenesis"].rank == layout_of(gpcr, "LR").nodes["pck1"].rank
    # a feedback arc runs back against the flow without moving ranks
    fb = next(r for r in layout_of(template("rtk_ras_mapk"), "TB").routes if (r.source, r.target) == ("erk", "sos"))
    assert fb.points[0][1] < fb.points[-1][1]                          # from ERK up to SOS


def test_routes_avoid_nodes_in_a_crowded_custom_pathway() -> None:
    nodes = [{"id": "l", "kind": "ligand"}, {"id": "r", "kind": "receptor"}, {"id": "r2", "kind": "receptor"},
             {"id": "a", "kind": "kinase"}, {"id": "b", "kind": "kinase"}, {"id": "c", "kind": "kinase"}, {"id": "d", "kind": "kinase"},
             {"id": "e", "kind": "kinase"}, {"id": "t", "kind": "transcription_factor"}, {"id": "g", "kind": "gene", "label": "MYC"},
             {"id": "x", "kind": "phosphatase"}]
    edges = [("l", "r"), ("l", "r2"), ("r", "a"), ("r2", "b"), ("a", "c"), ("b", "c"), ("c", "d"), ("d", "e"), ("a", "e"), ("e", "t"),
             ("r", "d"), ("x", "c")]
    arcs = [{"source": a, "target": b, "type": "inhibits" if a == "x" else ("transcribes" if b == "g" else "activates")} for a, b in edges]
    arcs += [{"source": "t", "target": "g", "type": "transcribes"}, {"source": "e", "target": "r", "type": "inhibits", "feedback": True}]
    p = build(nodes, arcs)
    for direction in ("LR", "TB"):
        lay = layout_of(p, direction)
        assert route_hits(lay, pad=0.02) == []
        assert all(len(samples(r, direction)) > 2 for r in lay.routes)


# ----- the scene and its actions in projects --------------------------------------------------------


def scene(actions: list[list[dict[str, Any]]], **params: Any) -> dict[str, Any]:
    texts = ["glucagon reaches the liver", "the signal runs to the nucleus", "a drug blocks it", "the receptor is lost"]
    return {"id": "p", "type": "pathway", "params": {"template": "gpcr_camp_pka", **params},
            "beats": [{"id": f"b{k}", "text": texts[k % 4], "actions": a} for k, a in enumerate(actions)]}


def problems_of(make_project: Any, scenes: list[dict[str, Any]]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, scenes, narration=NARRATION))]


def test_params_are_validated(make_project) -> None:
    assert problems_of(make_project, [scene([[{"signal": "glucagon"}]])]) == []
    assert any("unknown node 'pck2'; did you mean 'pck1'" in m for m in problems_of(make_project, [scene([[]], edges=["creb -> pck2"])]))
    assert any("binds its gene's DNA in the nucleus" in m
               for m in problems_of(make_project, [scene([[]], nodes=[{"id": "creb", "in": "cytosol"}])]))
    assert any("a pathway needs nodes" in m for m in problems_of(make_project, [scene([[]], template=None)]))
    assert any("is a chain of 2 arcs" in m for m in problems_of(make_project, [scene([[]], edges=[{"from": "a"}, "a -> b -> c"])]))


def test_pathway_actions_are_validated(make_project) -> None:
    def found(actions: list[list[dict[str, Any]]], **params: Any) -> list[str]:
        return problems_of(make_project, [scene(actions, **params)])

    assert found([[{"signal": "glucagon", "to": "creb"}], [{"drug": "pde", "name": "IBMX"}], [{"knockout": "ac", "until": "b3"}],
                  [{"knockout": "ac"}, {"amplify": "camp", "factor": "×100"}, {"focus": "camp"}, {"highlight": "pka"}]]) == []
    assert any("did you mean 'glucagon'" in m for m in found([[{"signal": "glucgon"}]]))
    assert any("no activating path leads" in m for m in found([[{"signal": "creb", "to": "gcgr"}]]))
    assert any("has no inhibitory arc" in m for m in found([[{"inhibit": "pka"}]]))
    assert any("'pde' does not inhibit 'pka'" in m for m in found([[{"inhibit": "pde", "on": ["pka"]}]]))
    assert any("trametinib is a MEK1/2 inhibitor" in m for m in found([[{"drug": "pka", "name": "trametinib"}]]))
    assert any("is already knocked out" in m for m in found([[{"knockout": "ac"}], [{"knockout": "ac"}]]))
    assert any("blocked by a drug at this point" in m for m in found([[{"drug": "gcgr", "name": "x"}], [{"signal": "gcgr"}]]))
    assert any("nothing activates or makes 'glucagon'" in m for m in found([[{"amplify": "glucagon"}]]))
    assert any("'pka' does not activate or make 'camp'" in m for m in found([[{"amplify": "camp", "from": "pka"}]]))
    assert any("signal is an action of pathway scenes" in m
               for m in problems_of(make_project, [{"id": "t", "type": "title", "params": {"title": "x"},
                                                    "beats": [{"text": "a", "actions": [{"signal": "title"}]}]}]))
    assert any("focus is an action of iso_diagram and pathway scenes" in m
               for m in problems_of(make_project, [{"id": "t", "type": "title", "params": {"title": "x"},
                                                    "beats": [{"text": "a", "actions": [{"focus": "title"}]}]}]))


def test_targets(make_project) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()
    cls = registry.get("pathway").cls
    params = cls.Params.model_validate({"template": "rtk_ras_mapk", "title": "MAPK"})
    names = cls.target_names(params)
    assert names[:3] == ["title", "egf", "egfr"] and "edge:raf->mek" in names and "band:nucleus" in names and names[-1] == "pathway"


# ----- renders ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_pathway_renders(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [{"id": "p", "type": "pathway", "params": {"template": "rtk_ras_mapk", "title": "MAPK"},
               "beats": [{"text": "EGF switches on the cascade", "actions": [{"signal": "egf"}]},
                         {"text": "trametinib blocks MEK", "actions": [{"drug": "mek", "name": "trametinib"}]},
                         {"text": "the GAP turns Ras off and each step amplifies", "actions": [{"inhibit": "rasgap"}, {"amplify": "erk", "factor": "×10"},
                                                                                             {"focus": "ras", "at": 0.5}]},
                         {"text": "without the receptor nothing happens", "actions": [{"knockout": "egfr"}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 2.0})))
    rendered = render(project, "p", media, size)
    assert rendered.direction == ("LR" if size[0] > size[1] else "TB")
    assert rendered.drugged == {"mek": "trametinib"} and rendered.knocked == {"egfr"} and rendered.held == {"ras"}
    assert "gtp" not in rendered.nodes["ras"]["shown"] and "gdp" in rendered.nodes["ras"]["shown"]   # the GAP put Ras back to GDP
    assert set(rendered.effect_badges) >= {"erk", "elk1", "fos", "proliferation"}
