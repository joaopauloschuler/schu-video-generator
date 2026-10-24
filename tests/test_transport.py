"""Transport and membrane processes as actions, Step 205 (DESIGN.md §95.10): the rules and plans of
``vidgen.cellworld.transport`` and ``traffic`` (no manim), the validation of the actions with the
molecules' states replayed in beat order, the lipids that give way to membrane proteins, the
membrane rows of a tall frame, and tiny renders of every process."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_actions import project_with, render
from vidgen import extensions, registry
from vidgen.cellworld import CellSpec, ObjectSpec, build_cell_world
from vidgen.cellworld import traffic as tf
from vidgen.cellworld import transport as tr
from vidgen.cellworld.glyphs import MoleculeSpec, bilayer_span, check_molecule, molecule_glyph
from vidgen.cellworld.bilayer import lipid_layout
from vidgen.cellworld.curves import shape_curves
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def glyph(kind: str, state: str | None = None, **options: Any) -> Any:
    options.setdefault("membrane", "plasma_membrane")
    return molecule_glyph(check_molecule(MoleculeSpec(kind, state, **options)))


# ----- gradients and the rules ---------------------------------------------------------------------


def test_nernst_and_the_way_ions_flow() -> None:
    assert tr.nernst("K+", 5.0, 140.0) == pytest.approx(-89.0, abs=1.0)
    assert tr.nernst("Na+", 145.0, 12.0) == pytest.approx(66.5, abs=1.0)
    assert tr.nernst("Ca2+", 2.0, 0.0001) == pytest.approx(132.0, abs=2.0)
    g = tr.Gradients.typical("plasma_membrane")
    assert g.potential == -70.0
    assert g.passive_way("K+") == "out" and g.passive_way("Na+") == "in" and g.passive_way("Ca2+") == "in"
    assert g.passive_way("Cl-") == "out"           # E_Cl −64 mV: at −70 mV the inside repels Cl⁻ a little more than its gradient pushes it in
    assert tr.Gradients.typical("lysosomal_membrane").passive_way("K+") is None      # nothing known there


def test_channel_selectivity_and_gate() -> None:
    k = check_molecule(MoleculeSpec("ion_channel", ion="K+"))
    assert "Na⁺ cannot pass a K⁺ channel" in tr.channel_problem(k, "Na+", "open")
    assert "selectivity filter" in tr.channel_problem(k, "Na+", "open")
    assert "closed now" in tr.channel_problem(k, "K+", "closed")
    assert "inactivated" in tr.channel_problem(k, "K+", "inactivated")
    assert tr.channel_problem(k, "K+", "open") is None
    assert "aquaporin passes water" in tr.aquaporin_problem("Na+")


def test_carriers_need_their_energy() -> None:
    g = tr.Gradients.typical("plasma_membrane")
    assert tr.carrier_problem(check_molecule(MoleculeSpec("carrier", transporter="sglt1")), g) is None
    assert tr.carrier_problem(check_molecule(MoleculeSpec("carrier", transporter="ncx")), g) is None
    out = check_molecule(MoleculeSpec("carrier", substrates=("glucose",), moves=("out",)))
    assert "a uniporter only lets Glucose down its gradient" in tr.carrier_problem(out, g)
    # an antiporter whose coupled moves both go uphill
    uphill = check_molecule(MoleculeSpec("carrier", mode="antiport", substrates=("Na+", "K+"), moves=("out", "in")))
    assert "active transport needs an energy source: ATP or an ion gradient" in tr.carrier_problem(uphill, g)


@pytest.mark.parametrize("spec, message", [
    (MoleculeSpec("carrier", mode="antiport", substrates=("Na+", "Ca2+"), moves=("in", "in")), "an antiporter moves its solutes opposite ways"),
    (MoleculeSpec("carrier", mode="symport", substrates=("Na+", "glucose"), moves=("in", "out")), "a symporter moves its solutes the same way"),
    (MoleculeSpec("carrier", ratio=(2,)), "a uniporter moves one solute per cycle"),
    (MoleculeSpec("carrier", transporter="ncx", mode="symport"), "does not match transporter NCX"),
    (MoleculeSpec("carrier", transporter="sglt9"), "transporter 'sglt9'.*did you mean .*'sglt1'"),
    (MoleculeSpec("ion_channel", "inactivated", gating="ligand"), "only voltage-gated channels inactivate"),
    (MoleculeSpec("h_atpase", "e1p", membrane="lysosomal_membrane"), "rotary pump"),
    (MoleculeSpec("abc_transporter", moves=("in",), membrane="plasma_membrane"), "ABC importers .* are bacterial"),
])
def test_transporter_options_are_checked(spec: MoleculeSpec, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        check_molecule(spec)


def test_named_transporters() -> None:
    sglt1 = check_molecule(MoleculeSpec("carrier", transporter="sglt1"))
    assert (sglt1.mode, sglt1.substrates, sglt1.moves, sglt1.ratio) == ("symport", ("Na+", "glucose"), ("in", "in"), (2, 1))
    ncx = glyph("carrier", transporter="ncx")
    assert ncx.facts["ratio"] == (3, 1) and ncx.facts["moves"] == ("in", "out")


def test_simple_diffusion_rules_and_osmosis() -> None:
    assert tr.diffusion_problem("o2", "plasma_membrane") is None
    assert tr.diffusion_problem("Na+", None) is None
    assert "cannot cross the lipid bilayer by simple diffusion" in tr.diffusion_problem("K+", "plasma_membrane")
    assert "GLUT" in tr.diffusion_problem("glucose", "plasma_membrane")
    assert tr.osmosis_way({"Na+": 145, "Cl-": 145}, {"Na+": 200, "Cl-": 200}) == "out"
    assert "isotonic" in tr.osmosis_problem({"Na+": 150}, {"Na+": 150})


# ----- glyph states ----------------------------------------------------------------------------------


def test_state_glyphs() -> None:
    open_, inact = glyph("ion_channel", "open", ion="Na+"), glyph("ion_channel", "inactivated", ion="Na+")
    assert open_.facts["gate_gap"] == inact.facts["gate_gap"] > glyph("ion_channel", "closed", ion="Na+").facts["gate_gap"]
    assert "inactivation" in inact.anchors and inact.anchors["inactivation"][1][1] < -3.0          # it plugs the inner mouth
    pump = {s: glyph("na_k_atpase", s) for s in ("e1", "e1p", "e2p", "e2")}
    assert [pump[s].facts["phosphorylated"] for s in ("e1", "e1p", "e2p", "e2")] == [False, True, True, False]
    assert [pump[s].facts["access"] for s in ("e1", "e1p", "e2p", "e2")] == ["inward", "occluded", "outward", "occluded"]
    assert glyph("carrier", "occluded").facts["site"][1] == 0.0
    assert glyph("h_atpase", membrane="lysosomal_membrane").facts["type"] == "v"
    bare, full = glyph("na_k_atpase", "e1", bare=True), glyph("na_k_atpase", "e1")
    assert len(bare.prims) < len(full.prims)                     # no bound ions, arrows or ATP


# ----- plans -----------------------------------------------------------------------------------------


def _moves(plan: tr.Plan, pid: str) -> list[tr.Move]:
    return [m for phase in plan.phases for m in phase.moves if m.particle == pid]


def test_na_k_pump_cycle_plan() -> None:
    b = tr.builder("t", tr.Pool(boxes={"p": (-30, 3, 30, 20), "n": (-30, -20, 30, -3)}), "x.")
    plan = tr.plan_na_k_pump("pump", glyph("na_k_atpase", bare=True), (0.0, 0.0), "e1", 1, b)
    states = [s for phase in plan.phases for _, s in phase.states]
    assert states == ["e1p", "e2p", "e2", "e1"]
    na = [p.id for p in plan.particles if p.species == "Na+"]
    k = [p.id for p in plan.particles if p.species == "K+"]
    assert len(na) == 3 and len(k) == 2
    assert all(_moves(plan, pid)[-1].path[-1][1] > 2.5 for pid in na)       # sodium ends outside
    assert all(_moves(plan, pid)[-1].path[-1][1] < -2.5 for pid in k)       # potassium ends in the cytosol
    assert {p.species for p in plan.particles} >= {"atp", "adp", "pi"}
    assert plan.states == {"pump": "e1"}


def test_channel_and_carrier_plans() -> None:
    b = tr.builder("t", tr.Pool(boxes={"p": (-30, 3, 30, 20), "n": (-30, -20, 30, -3)}), "x.")
    plan = tr.plan_channel("k", glyph("ion_channel", "open", bare=True), (0.0, 0.0), "K+", "out", 3, b)
    assert all(m.path[0][1] < 0 < m.path[-1][1] for phase in plan.phases for m in phase.moves)
    ncx = check_molecule(MoleculeSpec("carrier", transporter="ncx", bare=True, membrane="plasma_membrane"))
    plan = tr.plan_carrier("ncx", ncx, molecule_glyph(ncx), (0.0, 0.0), "outward", 1, b)
    ends = {p.species: [] for p in plan.particles}
    for p in plan.particles:
        ends[p.species].append(_moves(plan, p.id)[-1].path[-1][1])
    assert len(ends["Na+"]) == 3 and all(y < 0 for y in ends["Na+"])       # 3 Na⁺ in
    assert len(ends["Ca2+"]) == 1 and ends["Ca2+"][0] > 0                  # 1 Ca²⁺ out
    states = [s for phase in plan.phases for _, s in phase.states]
    assert "occluded" in states and plan.states["ncx"] == "outward"


def test_diffusion_moves_net_down_the_gradient() -> None:
    rng = random.Random(1)
    boxes = {"p": (-20.0, 3.0, 20.0, 15.0), "n": (-20.0, -15.0, 20.0, -3.0)}
    field = {"p": [(f"a{k}", (rng.uniform(-20, 20), rng.uniform(3, 15))) for k in range(12)], "n": [("b0", (0.0, -8.0))]}
    plan = tr.plan_diffusion("o2", field, boxes, tr.Crossing(()), 0.6, random.Random(2), "")
    ends = list(plan.sides.values())
    assert ends.count("n") > 1 and ends.count("p") < 12                     # net flux into the cytosol
    for m in plan.phases[0].moves:
        assert len(m.path) > 5                                              # a random walk, not a line


def test_action_potential_trace() -> None:
    v = [tr.ap_voltage(t) for t in (0.0, 0.8, 1.6, 3.4, 6.0)]
    assert v[0] == -70.0 and v[1] == pytest.approx(-55.0) and v[2] == pytest.approx(35.0) and v[3] == pytest.approx(-80.0) and v[4] == -70.0
    trace = tr.ap_trace()
    assert max(mv for _, mv in trace) <= 35.5 and min(mv for _, mv in trace) >= -80.5


# ----- motors and membrane traffic ---------------------------------------------------------------------


def _motor_world() -> Any:
    return build_cell_world(CellSpec(objects=(ObjectSpec("microtubule", "mts", count=8), ObjectSpec("kinesin", "kin", on="mts"),
                                              ObjectSpec("dynein", "dyn", on="mts"))))


def test_motors_walk_to_their_end() -> None:
    world = _motor_world()
    assert "kinesin cannot walk to the minus end" in tf.walk_problem(world, "kin", 0.1, "minus")
    assert "dynein cannot walk to the plus end" in tf.walk_problem(world, "dyn", 0.1, "plus")
    assert "from the plus end of its filament; walk at most" in tf.walk_problem(world, "kin", 50.0, None)
    thing = world.members("kin")[0]
    track = tf.motor_track(world, thing)
    start, end = tf.walk_pose("kinesin", track, 0.08, 0.0), tf.walk_pose("kinesin", track, 0.08, 1.0)
    assert end.s - start.s == pytest.approx(0.08)                           # kinesin: towards the + end (s grows)
    mid = tf.walk_pose("kinesin", track, 0.08, 0.05)                        # half-way through its first step
    assert max(lift for _, lift in mid.heads) > 0                           # the trailing head swings over
    dyn = world.members("dyn")[0]
    d0, d1 = (tf.walk_pose("dynein", tf.motor_track(world, dyn), 0.08, t).s for t in (0.0, 1.0))
    assert d1 < d0                                                           # dynein: towards the − end


def test_endocytosis_and_exocytosis_rules_and_shapes() -> None:
    bacterium = build_cell_world(CellSpec(kind="bacterium"))
    assert "bacteria do not take up material by endocytosis" in tf.endocytosis_problem(bacterium, None)
    world = build_cell_world(CellSpec(objects=(ObjectSpec("vesicle", "cv", coat="clathrin", at=(9.6, 0.0)), ObjectSpec("vesicle", "sv", at=(0.0, 7.6)))))
    assert "cannot fuse: it sheds its coat first" in tf.exocytosis_problem(world, "cv")
    assert "cannot fuse with the nuclear envelope" in tf.exocytosis_problem(world, "sv", "nucleus")
    assert tf.exocytosis_problem(world, "sv") is None
    flat = tf.endocytosis_shape(0.0)
    pit = tf.endocytosis_shape(0.5)
    late = tf.endocytosis_shape(1.0)
    assert max(abs(v) for _, v in flat.membrane) == 0.0 and flat.vesicle is None
    assert min(v for _, v in pit.membrane) < -60 and pit.coat is not None
    assert tf.endocytosis_shape(0.68).neck is not None                      # dynamin's neck before scission
    assert late.vesicle is not None and late.vesicle[0] > 150 and late.coat_on_vesicle == 0.0
    assert max(abs(v) for _, v in late.membrane) < 1.0
    exo = [tf.exocytosis_shape(t, 45.0, 300.0) for t in (0.0, 0.4, 0.6, 1.0)]
    assert exo[0].vesicle[0] == pytest.approx(300.0) and exo[1].snares and exo[2].vesicle is None
    assert max(abs(v) for _, v in exo[3].membrane) == 0.0


def test_lipids_leave_room_for_membrane_proteins() -> None:
    world = build_cell_world(CellSpec(contents="none", objects=(ObjectSpec("na_k_atpase", "pump", on="cell"),)))
    pump = world.members("pump")[0]
    x0, x1 = bilayer_span(molecule_glyph(pump.option("molecule")))
    gap = (pump.center, pump.angle, x0 / 1000, x1 / 1000)
    curves = list(shape_curves(world.cell))
    near = lambda lipids: [l for l in lipids if math.dist(l.head, pump.center) < 0.003]  # noqa: E731
    assert near(lipid_layout(world, curves, pump.center, 0.03, "k"))
    assert not near(lipid_layout(world, curves, pump.center, 0.03, "k", gaps=[gap]))


# ----- the actions in projects --------------------------------------------------------------------------


def molecule_scene(actions: list[list[dict[str, Any]]], **params: Any) -> dict[str, Any]:
    texts = ["the channel is closed at rest", "it opens and potassium leaves the cell", "then the pump turns once more"]
    return {"id": "m", "type": "molecule", "params": {"membrane": "plasma", **params},
            "beats": [{"text": texts[k % 3], "actions": a} for k, a in enumerate(actions)]}


def problems_of(make_project: Any, scenes: list[dict[str, Any]]) -> list[str]:
    return [p.message for p in project_problems(project_with(make_project, scenes, narration=NARRATION))]


def test_process_actions_are_validated(make_project) -> None:
    channel = {"molecules": [{"kind": "ion_channel", "id": "k", "ion": "K+"}], "solutes": ["K+", "Na+"]}
    found = problems_of(make_project, [molecule_scene([[{"transport": "k"}]], **channel)])
    assert any("'k': the channel is closed now" in m for m in found)
    assert problems_of(make_project, [molecule_scene([[{"set_state": "k", "state": "open"}], [{"transport": "k", "at": "@potassium"}]], **channel)]) == []
    assert any("Na⁺ cannot pass a K⁺ channel" in m for m in problems_of(make_project, [molecule_scene([[{"transport": "k", "ion": "Na+"}]], **channel)]))
    assert any("down their electrochemical gradient" in m
               for m in problems_of(make_project, [molecule_scene([[{"set_state": "k", "state": "open"}], [{"transport": "k", "direction": "in"}]], **channel)]))
    assert any("state 'opened'" in m for m in problems_of(make_project, [molecule_scene([[{"set_state": "k", "state": "opened"}]], **channel)]))
    assert any("diffuse: oxygen" not in m and "cannot cross the lipid bilayer" in m
               for m in problems_of(make_project, [molecule_scene([[{"diffuse": "potassium"}]], **channel)]))
    ap = {"molecules": [{"kind": "ion_channel", "id": "nav", "ion": "Na+", "state": "open"}, {"kind": "ion_channel", "id": "kv", "ion": "K+"}]}
    assert any("an action potential starts at rest: channel 'nav' is open" in m
               for m in problems_of(make_project, [molecule_scene([[{"action_potential": "membrane"}]], **ap)]))
    assert any("needs voltage-gated K⁺ channels" in m
               for m in problems_of(make_project, [molecule_scene([[{"action_potential": "membrane"}]], molecules=[{"kind": "ion_channel", "ion": "Na+"}])]))
    assert any("isotonic" in m for m in problems_of(make_project, [molecule_scene([[{"osmosis": "membrane"}]], solutes=[
        {"solute": "Na+", "mM": {"extracellular": 150, "cytosol": 150}}])]))
    assert any("motor_walk is a cell action" in m for m in problems_of(make_project, [molecule_scene([[{"motor_walk": "k"}]], **channel)]))


def test_traffic_actions_are_validated(make_project) -> None:
    def cell(actions: list[list[dict[str, Any]]], **params: Any) -> dict[str, Any]:
        return {"id": "c", "type": "cell", "params": params, "beats": [{"text": "a motor walks along a microtubule", "actions": a} for a in actions]}

    motors = {"objects": [{"kind": "microtubule", "id": "mts", "count": 8}, {"kind": "kinesin", "id": "kin", "on": "mts", "cargo": True}]}
    assert problems_of(make_project, [cell([[{"motor_walk": "kin", "distance": "100 nm"}], [{"motor_walk": "kin", "distance": "100 nm"}]], **motors)]) == []
    assert any("kinesin cannot walk to the minus end" in m for m in problems_of(make_project, [cell([[{"motor_walk": "kin", "toward": "minus"}]], **motors)]))
    assert any("after its earlier walks" in m
               for m in problems_of(make_project, [cell([[{"motor_walk": "kin"}]] * 12, **motors)]))
    assert any("bacteria do not take up material" in m for m in problems_of(make_project, [cell([[{"endocytosis": "cell"}]], cell="bacterium")]))
    coated = {"objects": [{"kind": "vesicle", "id": "cv", "coat": "clathrin", "at": [9.6, 0]}]}
    assert any("sheds its coat first" in m for m in problems_of(make_project, [cell([[{"exocytosis": "cv"}]], **coated)]))
    assert any("set_state is an action of molecule scenes" in m for m in problems_of(make_project, [cell([[{"set_state": "cell", "state": "open"}]])]))


def test_tall_frames_put_membrane_proteins_on_rows() -> None:
    extensions.load_builtins()
    from vidgen.scenes.molecule import _arrange, layout

    placed = layout([*(registry.get("molecule").cls.Params.model_fields["molecules"].annotation.__args__[0].model_validate(k)
                       for k in ("ion_channel", "carrier", "na_k_atpase"))], "plasma_membrane", "cytosol", "animal", "human")
    rows = _arrange(placed, "plasma_membrane", None, 9 / 16, 1.0)
    assert len(rows) > 1 and rows[1] < rows[0]
    assert len({p.row for p in placed}) == len(rows)
    assert len(_arrange(placed, "plasma_membrane", None, 16 / 9, 1.0)) == 1


# ----- renders ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_molecule_processes_render(size: tuple[int, int], make_project, media: Path) -> None:
    scenes = [
        {"id": "m", "type": "molecule", "params": {"membrane": "plasma", "potential": -70, "solutes": ["K+", {"solute": "o2", "mM": {"extracellular": 0.2, "cytosol": 0.02}}],
                                                   "molecules": [{"kind": "ion_channel", "id": "nav", "ion": "Na+"}, {"kind": "ion_channel", "id": "kv", "ion": "K+"},
                                                                 {"kind": "na_k_atpase", "id": "pump"}]},
         "beats": [{"text": "sodium channels open and close in an action potential", "actions": [{"action_potential": "membrane"}]},
                   {"text": "the pump turns once", "actions": [{"transport": "pump"}]},
                   {"text": "oxygen diffuses in", "actions": [{"diffuse": "o2"}, {"set_state": "kv", "state": "open", "at": 0.5}]}]},
    ]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 2.0})))
    scene = render(project, "m", media, size)
    assert scene.specs["pump"].state == "e1" and scene.specs["kv"].state == "open"
    assert scene.digits is not None and len(scene.particle_mobs) > 10
    assert scene.levels["o2"]["cytosol"] > 0.02                                     # oxygen moved in


@pytest.mark.render
def test_cell_traffic_renders(make_project, media: Path) -> None:
    scenes = [{"id": "c", "type": "cell", "params": {"labels": False, "view": {"level": "complex", "on": "cell", "width": "400 nm"},
                                                    "objects": [{"kind": "microtubule", "id": "mts", "count": 6}, {"kind": "kinesin", "id": "kin", "on": "mts", "cargo": True},
                                                                {"kind": "vesicle", "id": "sv", "at": [9.6, 0.0], "size": "90 nm"}]},
               "beats": [{"text": "a coated pit buds inwards", "actions": [{"endocytosis": "cell"}]},
                         {"text": "the vesicle fuses with the membrane", "actions": [{"exocytosis": "sv"}]},
                         {"text": "kinesin walks outwards", "actions": [{"motor_walk": "kin", "distance": "50 nm"}]}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": 0.2, "words_per_second": 2.0})))
    scene = render(project, "c", media, (160, 90))
    assert len(scene.traffic_events) == 2 and scene._walked()["kin"] == pytest.approx(0.05)
    assert all(p.emphasis == (0.0, 0.0) for p in scene.drawing.lod.pieces if p.owner == "sv")      # the fused vesicle is gone
