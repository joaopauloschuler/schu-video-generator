"""The structure library, Step 203 (DESIGN.md §95.9): plant and bacterial cells, fine structure as
compartments (the ER one lumen with the perinuclear space, pores, cristae, cis/medial/trans
Golgi, thylakoids, intraluminal vesicles), the cytoskeleton and motors, the lipids of a bilayer,
the parts a zoomed view names — all without manim."""

from __future__ import annotations

import math
from functools import lru_cache

import pytest

from vidgen.cellworld import (
    KINDS, CellSpec, Ellipse, ObjectSpec, Polyline, Region, build_cell_world, level_view, part_anchors,
)
from vidgen.cellworld.bilayer import lipid_layout, membrane_between, mosaic, lipids_of, plasma_rafts
from vidgen.cellworld.curves import shape_curves
from vidgen.cellworld.morphology import cristae, pore_channel
from vidgen.errors import VidgenError

ASPECT = 16 / 9 * 0.8


@lru_cache(maxsize=8)
def built(kind: str = "animal", **extra: object) -> object:
    return build_cell_world(CellSpec(kind=kind, **extra))  # type: ignore[arg-type]


def world(*objects: ObjectSpec, **cell: object) -> object:
    return build_cell_world(CellSpec(objects=tuple(objects), **cell))  # type: ignore[arg-type]


# ----- cells ----------------------------------------------------------------------------------------


def test_a_typical_plant_cell() -> None:
    w = built("plant")
    kinds = {e.kind for e in w.entries}
    assert {"vacuole", "chloroplast", "nucleus", "golgi", "mitochondrion"} <= kinds
    assert not {"centrosome", "lysosome"} & kinds                     # no centrioles, digestion in the vacuole
    assert w.size == 32.0 and w.envelope[0][0] == "cell_wall"
    vacuole = w.thing("vacuole")
    assert w.compartment_at(vacuole.center) == ("vacuole_lumen", "vacuole.vacuole_lumen")
    x0, y0, x1, y1 = w.cell.bounds()
    assert w.compartment_at((x1 + 0.1, 0.0))[0] == "cell_wall"
    channel = w.channels[0]
    assert w.compartment_at(channel.center())[0] == "cytosol"         # a plasmodesma joins the cytosol of two cells
    for c in w.members("chloroplasts"):                                 # in the thin cytoplasm along the wall
        assert w.cell.distance(c.center) > -3.0


def test_bacteria_gram_negative_and_positive() -> None:
    w = built("bacterium")
    assert w.size == 2.0 and w.gram == "negative" and [n for n, _ in w.membranes] == ["bacterial_inner_membrane", "bacterial_outer_membrane"]
    top = w.cell.point(0.5)
    assert w.compartment_at((top[0], top[1] + 0.012))[0] == "periplasm"
    ribosomes = w.members("ribosomes")
    assert ribosomes[0].size == pytest.approx(0.021)                    # 70S, smaller than the 80S of eukaryotes
    nucleoid = w.thing("nucleoid")
    assert not any(nucleoid.contains(r.center) for r in ribosomes)      # ribosomes are kept out of the nucleoid
    for f in w.members("flagella"):
        line = f.footprint[0]
        assert isinstance(line, Polyline) and line.length > 4 and not w.cell.contains(line.points[-1])
    positive = built("bacterium", gram="positive", capsule=True)
    assert [n for n, _ in positive.envelope] == ["cell_wall", "capsule"] and positive.membranes[0][0] == "plasma_membrane"


@pytest.mark.parametrize("spec, cell, message", [
    (ObjectSpec("centrosome"), "plant", "a centrosome cannot be in a plant cell: flowering-plant cells have no centrioles"),
    (ObjectSpec("chloroplast"), "animal", "a chloroplast cannot be in an animal cell: only plant"),
    (ObjectSpec("mitochondrion"), "bacterium", "prokaryotes have no nucleus and no membrane-bounded organelles"),
    (ObjectSpec("lysosome"), "plant", "lytic vacuole"),
    (ObjectSpec("intermediate_filament", count=3), "plant", "plants and bacteria have no cytoplasmic intermediate filaments"),
    (ObjectSpec("nucleoid"), "animal", "eukaryotes keep their chromosomes in a nucleus"),
    (ObjectSpec("vesicle", coat="copx"), "animal", "coat 'copx'.*did you mean 'copi'"),
    (ObjectSpec("lysosome", coat="copi"), "animal", "coat is for vesicle"),
    (ObjectSpec("kinesin", count=2), "animal", "a kinesin walks on a filament: give on:"),
    (ObjectSpec("microtubule", count=5), "bacterium", "bacteria have tubulin-like FtsZ but no microtubules"),
    (ObjectSpec("flagellum", at=(1.0, 0.0)), "bacterium", "give angle"),
])
def test_cell_kind_rules(spec: ObjectSpec, cell: str, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        world(spec, kind=cell)


def test_cell_options_and_sizes() -> None:
    with pytest.raises(VidgenError, match="a plant cell is drawn from 10 to 120 µm"):
        world(kind="plant", size=5.0)
    with pytest.raises(VidgenError, match="wall thickness is for plant cells"):
        world(wall=0.3)
    with pytest.raises(VidgenError, match="cell kind 'plnat'.*did you mean 'plant'"):
        world(kind="plnat")


# ----- fine structure as compartments ------------------------------------------------------------------


def test_the_er_is_one_lumen_with_the_nuclear_envelope() -> None:
    w = built()
    er, nucleus, smooth = w.thing("rough_er"), w.thing("nucleus"), w.thing("smooth_er")
    assert er.joined == ("nucleus",) and smooth.joined == ("rough_er",)
    for neck in er.option("necks")[:2]:                                   # joined to the outer nuclear membrane
        half = neck.half
        ends = [(neck.cx + sign * half * math.cos(neck.angle), neck.cy + sign * half * math.sin(neck.angle)) for sign in (-1, 1)]
        near = min(ends, key=lambda e: math.dist(e, nucleus.center))
        assert nucleus.footprint[0].contains(near, 0.002)                  # its end on the outer membrane's mid-line
        assert w.compartment_at(neck.center())[0] == "er_lumen"
    assert w.compartment_at(smooth.option("nodes")[0])[0] == "er_lumen"


def test_pores_open_the_envelope_and_cristae_open_into_the_intermembrane_space() -> None:
    w = built()
    pore = w.members("nucleus.pores")[0]
    assert w.compartment_at(pore.center)[0] in ("cytosol", "nucleoplasm")   # the channel, not the perinuclear space
    assert pore_channel(pore.center, pore.normal).contains(pore.center)
    mito = w.thing("mitochondria#1")
    inner = mito.footprint[0].inset(0.025)
    folds = cristae(inner, mito.key)
    assert len(folds) >= 4
    lamella = folds[1]
    assert w.compartment_at(lamella.center())[0] == "intermembrane_space"   # intracristal space = intermembrane space
    assert w.compartment_at(mito.center)[0] in ("matrix", "intermembrane_space")


def test_golgi_cis_to_trans_with_coats() -> None:
    w = built()
    golgi = w.thing("golgi")
    names = [part.interior[0] for part in golgi.parts]
    assert names[0] == "cis_golgi_lumen" and names[-1] == "trans_golgi_lumen" and set(names[1:-1]) == {"medial_golgi_lumen"}
    coats = {(k, coat) for _c, _r, coat, k in golgi.option("buds")}
    assert all(coat == "clathrin" for k, coat in coats if k == len(names) - 1)
    assert all(coat == "copi" for k, coat in coats if k < len(names) - 1)
    vesicles = w.members("golgi.vesicles")
    assert {v.option("coat") for v in vesicles} >= {"copi", "clathrin", None}
    assert all(w.compartment_at(v.center)[0] == "vesicle_lumen" for v in vesicles)
    copii = w.members("rough_er.vesicles")
    assert copii and all(v.option("coat") == "copii" for v in copii)       # COPII at the ER's exit sites


def test_chloroplast_and_late_endosome_inner_compartments() -> None:
    w = built("plant")
    chloroplast = w.thing("chloroplasts#1")
    disc = chloroplast.option("discs")[0]
    assert w.compartment_at(disc.center())[0] == "thylakoid_lumen"
    outer = chloroplast.footprint[0]
    p, n = outer.point(0.1), outer.normal(0.1)
    assert w.compartment_at((p[0] - n[0] * 0.01, p[1] - n[1] * 0.01))[0] == "chloroplast_intermembrane_space"
    animal = built()
    mvb = animal.thing("late_endosome")
    ilv = mvb.parts[1].membranes[0][1]
    assert animal.compartment_at(ilv.center())[0] == "intraluminal_vesicle"   # cytosol taken in
    assert len(mvb.parts) > 6


# ----- cytoskeleton and motors ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def skeleton() -> object:
    return world(ObjectSpec("nucleus"), ObjectSpec("centrosome"), ObjectSpec("microtubule", count=20), ObjectSpec("actin_cortex"),
                 ObjectSpec("stress_fiber", count=2), ObjectSpec("intermediate_filament", count=6),
                 ObjectSpec("kinesin", on="microtubule", count=3), ObjectSpec("dynein", on="microtubule", count=2),
                 ObjectSpec("myosin", on="actin_cortex", count=2), contents="none")


def test_microtubules_radiate_from_the_centrosome_round_the_nucleus() -> None:
    w = skeleton()
    centrosome, nucleus = w.thing("centrosome"), w.thing("nucleus")
    for mt in w.members("microtubule"):
        line = mt.footprint[0]
        minus, plus = line.points[0], line.points[-1]
        assert math.dist(minus, centrosome.center) < 0.4 < math.dist(plus, centrosome.center)   # minus end at the centrosome
        assert not any(nucleus.contains(q) for q in line.outline(60))
        assert all(w.cell.contains(q) for q in line.points)


def test_motors_face_the_end_they_walk_to() -> None:
    w = skeleton()
    for motor in w.members("kinesin") + w.members("dynein"):
        line = w.thing(motor.surface).footprint[0]
        base = motor.option("base")
        s = min(range(400), key=lambda k: math.dist(line.at(line.length * k / 400)[0], base)) * line.length / 400
        _, (dx, dy) = line.at(s)
        along = math.cos(motor.facing) * dx + math.sin(motor.facing) * dy
        assert along > 0.9 if motor.kind == "kinesin" else along < -0.9    # kinesin to +, dynein to −
    assert all(KINDS[w.thing(m.surface).kind].name == "actin_cortex" for m in w.members("myosin"))
    with pytest.raises(VidgenError, match="a kinesin cannot walk on a actin cortex"):
        world(ObjectSpec("actin_cortex"), ObjectSpec("kinesin", on="actin_cortex"), contents="none")
    with pytest.raises(VidgenError, match="microtubules radiate from the centrosome"):
        world(ObjectSpec("nucleus"), ObjectSpec("microtubule", count=4), contents="none")


# ----- the bilayer --------------------------------------------------------------------------------------


def test_membrane_names_and_sides() -> None:
    w = built()
    assert membrane_between(w, "extracellular", "cytosol") == ("plasma_membrane", 1)
    assert membrane_between(w, "cytosol", "er_lumen") == ("er_membrane", -1)
    assert membrane_between(w, "matrix", "intermembrane_space") == ("inner_mitochondrial_membrane", -1)
    assert membrane_between(w, "cytosol", "trans_golgi_lumen") == ("golgi_membrane", -1)
    assert membrane_between(w, "cytosol", "cytosol") is None


def test_lipids_of_the_plasma_membrane_and_others() -> None:
    w = built()
    focus = level_view(w, "complex", ASPECT).center
    lipids = lipid_layout(w, shape_curves(w.cell), focus, 0.03, "t", plasma_rafts(w))
    assert len(lipids) > 100 and {l.membrane for l in lipids} == {"plasma_membrane"}
    kinds = {(l.kind, l.leaflet) for l in lipids}
    assert ("glycolipid", "exo") in kinds and ("glycolipid", "cyto") not in kinds   # glycolipids only face outwards
    assert ("sterol", "exo") in kinds and ("sterol", "cyto") in kinds
    assert any(l.raft for l in lipids)
    for l in lipids:                                                    # the exoplasmic heads face the extracellular space
        out = (l.head[0] + l.out[0] * 0.003, l.head[1] + l.out[1] * 0.003)
        assert (w.compartment_at(out)[0] == "extracellular") == (l.leaflet == "exo")
    assert lipids_of(w, "inner_mitochondrial_membrane").sterol == 0 and lipids_of(w, "inner_mitochondrial_membrane").cardiolipin > 0
    bacterium = built("bacterium")
    outer = bacterium.membranes[1][1]
    top = outer.point(0.5)
    lps = lipid_layout(bacterium, shape_curves(outer), top, 0.02, "t")
    assert all(l.kind == "lps" for l in lps if l.leaflet == "exo") and not any(l.kind == "sterol" for l in lps)


def test_mosaic_face_on() -> None:
    w = built("plant")
    chloroplast = w.thing("chloroplasts#1")
    heads = mosaic(chloroplast.center, 0.01, chloroplast.footprint[0].contains, lipids_of(w, "outer_envelope_membrane"), "cyto", "t")
    assert len(heads) > 300 and {k for k, _ in heads} >= {"galactolipid", "phospholipid"}


# ----- zoomed views name their parts --------------------------------------------------------------------


@pytest.mark.parametrize("entry, level, expected", [
    ("mitochondria", "organelle", {"outer_membrane", "inner_membrane", "intermembrane_space", "crista", "matrix"}),
    ("mitochondria", "complex", {"crista_junction", "outer_membrane"}),
    ("nucleus", "complex", {"pore", "outer_nuclear_membrane", "inner_nuclear_membrane", "perinuclear_space"}),
    ("rough_er", "complex", {"ribosome", "large_subunit", "small_subunit", "lumen"}),
    ("golgi", "organelle", {"cis", "trans", "copi", "clathrin"}),
    (None, "complex", {"phospholipid", "sterol", "glycolipid", "raft"}),
])
def test_part_anchors(entry: str | None, level: str, expected: set[str]) -> None:
    w = built()
    view = level_view(w, level, ASPECT, entry)
    half = (view.span * ASPECT / 2, view.span / 2)
    anchors = part_anchors(w, entry, view, half)
    assert expected <= {a.name for a in anchors}
    assert all(abs(a.point[0] - view.center[0]) <= half[0] and abs(a.point[1] - view.center[1]) <= half[1] for a in anchors)


def test_regions() -> None:
    ring = Region.of(Ellipse(0, 0, 1, 1)).minus(Ellipse(0, 0, 0.5, 0.5))
    assert ring.contains((0.75, 0.0)) and not ring.contains((0.0, 0.0)) and not ring.contains((1.2, 0.0))
    assert ring.area() == pytest.approx(math.pi * 0.75, rel=1e-3)
    assert len(ring.contours()) == 2
