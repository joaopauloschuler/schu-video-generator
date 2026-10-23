"""The cell world, Step 202 (DESIGN.md §95): units, the model and its location rules, the camera
levels, level of detail, scale bar and zoom path — all without manim."""

from __future__ import annotations

import math
import subprocess
import sys

import pytest

from vidgen.cellworld import (
    BILAYER, KINDS, CellSpec, Ellipse, ObjectSpec, build_cell_world, focus_point, format_length, level_view, lod_weights, nice_length,
    parse_coordinate, parse_length, scale_bar, zoom_path,
)
from vidgen.cellworld.geometry import ArcBand, Capsule, inside, overlap
from vidgen.errors import VidgenError

ASPECT = 16 / 9 * 0.8


def world(*objects: ObjectSpec, **cell: object) -> object:
    return build_cell_world(CellSpec(objects=tuple(objects), **cell))  # type: ignore[arg-type]


def test_the_model_never_imports_manim() -> None:
    code = "import sys, vidgen.cellworld, vidgen.cellworld.view, vidgen.cellworld.model; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert out.strip() == "False"


# ----- units ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, um", [(2, 2.0), ("25 nm", 0.025), ("1.5 um", 1.5), ("20 µm", 20.0), ("20μm", 20.0), ("0.1 mm", 100.0), ("3", 3.0)])
def test_parse_length(text: object, um: float) -> None:
    assert parse_length(text) == pytest.approx(um)


@pytest.mark.parametrize("text, message", [("2 inches", "unknown unit"), ("big", "write a length"), (0, "greater than 0"), ("-2 um", "write a length"), (True, "write a length")])
def test_parse_length_errors(text: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_length(text)  # type: ignore[arg-type]


def test_coordinates_formatting_and_nice_lengths() -> None:
    assert parse_coordinate("-250 nm") == pytest.approx(-0.25) and parse_coordinate(0) == 0.0 and parse_coordinate("0 um") == 0.0
    assert parse_coordinate("−3") == -3.0
    assert [format_length(v) for v in (0.025, 0.5, 1.5, 20, 2000)] == ["25 nm", "500 nm", "1.5 µm", "20 µm", "2 mm"]
    assert [nice_length(v) for v in (0.7, 3.9, 4.0, 9.99, 0.031)] == [0.5, 2.0, 2.0, 5.0, 0.02]
    assert scale_bar(17.2) == (2.0, "2 µm") and scale_bar(0.125) == (0.02, "20 nm")


# ----- the typical cell ----------------------------------------------------------------------------


def test_the_typical_animal_cell_is_at_textbook_scale() -> None:
    w = world()
    sizes = {e.id: w.thing(e.keys[0]) for e in w.entries}
    assert w.size == 20.0 and w.cell.b == pytest.approx(8.0)
    assert sizes["nucleus"].size == 7.0 and sizes["mitochondria"].width == 0.7 and sizes["ribosomes"].size == 0.025
    # relative scale: the nucleus is a third of the cell, a ribosome about 1/80 of a mitochondrion's length
    assert sizes["nucleus"].size / w.size == pytest.approx(0.35) and sizes["mitochondria"].size / sizes["ribosomes"].size == 80
    nucleus = sizes["nucleus"]
    outer, inner = (m[1] for m in nucleus.parts[0].membranes)
    assert outer.a - inner.a == pytest.approx(0.035)   # 30 nm perinuclear space + a bilayer, mid-line to mid-line
    kinds = {e.kind for e in w.entries}
    assert {"nucleus", "nucleolus", "rough_er", "smooth_er", "golgi", "centrosome", "mitochondrion", "lysosome", "peroxisome", "vesicle",
            "ribosome", "nuclear_pore"} == kinds
    assert len(w.members("mitochondria")) == 8 and len(w.members("nucleus.pores")) == pytest.approx(20, abs=3)
    assert len(w.members("rough_er.ribosomes")) > 400


def test_every_thing_is_where_it_may_be() -> None:
    w = world()
    for thing in w.placed:
        kind = KINDS[thing.kind]
        compartment = thing.host.rsplit(".", 1)[-1]
        if thing.surface is None:
            assert compartment in kind.places, thing.key
            assert w.compartment_at(thing.center)[1] == thing.host or kind.category == "structure", thing.key
        else:
            assert KINDS[w.thing(thing.surface).kind].name in kind.surfaces, thing.key
    for thing in w.members("rough_er.ribosomes") + w.members("nucleus.ribosomes") + w.members("ribosomes"):
        assert w.compartment_at(thing.center)[0] == "cytosol"   # never in a lumen or the nucleoplasm
    structures = [t for t in w.structures() if t.kind not in ("nucleolus",)]
    for a in structures:
        assert all(inside(s, w.cell, 0.2) for s in a.footprint), a.key
        for b in structures:
            if a.key < b.key:
                assert not any(overlap(s, o) for s in a.footprint for o in b.footprint), (a.key, b.key)


def test_compartments_by_point_and_topology() -> None:
    w = world()
    nucleus = w.thing("nucleus")
    assert w.compartment_at(nucleus.center) == ("nucleoplasm", "nucleus.nucleoplasm")
    outer = nucleus.parts[0].membranes[0][1]
    assert isinstance(outer, Ellipse)
    x, y = outer.point(0.0)
    nx, ny = outer.normal(0.0)
    assert w.compartment_at((x - nx * 0.018, y - ny * 0.018))[0] == "perinuclear_space"
    mito = w.thing("mitochondria#1")
    assert w.compartment_at(mito.center)[0] == "matrix"
    assert w.compartment_at((30.0, 0.0)) == ("extracellular", "extracellular")
    assert w.region_at(w.thing("nucleolus").center).kind == "nucleolus"
    golgi = w.thing("golgi")
    nucleus_dir = math.atan2(nucleus.center[1] - golgi.center[1], nucleus.center[0] - golgi.center[0])
    assert golgi.facing == pytest.approx(nucleus_dir)   # cis face towards the nucleus (and the ER)
    cis, trans = golgi.footprint[0], golgi.footprint[-1]
    assert isinstance(cis, ArcBand) and math.dist(cis.center(), nucleus.center) < math.dist(trans.center(), nucleus.center)


def test_building_is_deterministic_and_the_seed_moves_things() -> None:
    a, b, c = world(), world(), world(seed=2)
    assert [p.center for p in a.placed] == [p.center for p in b.placed]
    assert [p.center for p in a.members("mitochondria")] != [p.center for p in c.members("mitochondria")]


# ----- the location rules --------------------------------------------------------------------------


@pytest.mark.parametrize("spec, message", [
    (ObjectSpec("ribosome", at=(-1.2, 0.6), where="objects[0]"), r"objects\[0\] \(ribosome 'ribosome'\): at \[-1.2, 0.6\] µm: that point is in the nucleoplasm of 'nucleus'; ribosomes .*never in the nucleoplasm"),
    (ObjectSpec("ribosome", inside="nucleus", count=3), "a ribosome cannot be in the nucleoplasm: ribosomes translate in the cytosol"),
    (ObjectSpec("ribosome", inside="lysosomes", count=3), "cannot be in the lysosome lumen"),
    (ObjectSpec("ribosome", on="golgi", count=3), r"cannot sit on a Golgi apparatus \(only on a nucleus or rough ER\)"),
    (ObjectSpec("ribosome", on="smooth_er", count=3), "cannot sit on a smooth ER"),
    (ObjectSpec("proteasome", inside="golgi", count=3), "cannot be in the Golgi lumen"),
    (ObjectSpec("mitochondrion", at=(-1.2, 0.6)), "that point is in the nucleoplasm of 'nucleus'; mitochondria lie in the cytosol; move it"),
    (ObjectSpec("mitochondrion", at=(9.6, 0.0)), "reaches the plasma membrane or out of the cell"),
    (ObjectSpec("lysosome", at=(-1.2, 4.2), size=0.6), "overlaps 'rough_er'"),
    (ObjectSpec("nucleolus", id="extra", at=(5.0, 5.0)), "that point is in the cytosol; the nucleolus is a region of the nucleoplasm"),
    (ObjectSpec("nuclear_pore", inside="cytosol"), "nuclear pore cannot be in the cytosol"),
    (ObjectSpec("mitocondrion"), "unknown kind 'mitocondrion'; did you mean 'mitochondrion'"),
    (ObjectSpec("ribosome", inside="cytosl", count=2), "did you mean 'cytosol'"),
    (ObjectSpec("ribosome", inside="mitochondria.matrx", count=2), "did you mean 'matrix'"),
    (ObjectSpec("ribosome", at=(5, 5), count=2), "at places one thing"),
    (ObjectSpec("ribosome", inside="cytosol", on="rough_er"), "not both"),
    (ObjectSpec("mitochondrion", on="rough_er"), "does not sit on a membrane"),
    (ObjectSpec("mitochondrion", inside="cytosol"), "in is for complexes"),
    (ObjectSpec("golgi", sheets=3), "sheets is for rough_er"),
    (ObjectSpec("mitochondrion", id="cell"), "id 'cell' is reserved"),
    (ObjectSpec("mitochondrion", count=400), "could not fit 400 of them"),
])
def test_location_rules_refuse_with_the_reason(spec: ObjectSpec, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        world(spec)


def test_rules_allow_what_cells_do() -> None:
    w = world(ObjectSpec("ribosome", id="mitoribosomes", inside="mitochondria", count=10),
              ObjectSpec("proteasome", id="nuclear_proteasomes", inside="nucleus", count=5),
              ObjectSpec("ribosome", id="er_bound", on="rough_er", count=5),
              ObjectSpec("mitochondrion", id="mito", at=(6.0, 3.0), angle=30))
    assert all(w.compartment_at(p.center)[0] == "matrix" for p in w.members("mitoribosomes"))
    assert all(w.compartment_at(p.center)[0] == "nucleoplasm" for p in w.members("nuclear_proteasomes"))
    assert all(p.surface == "rough_er" for p in w.members("er_bound"))
    assert w.thing("mito").center == (6.0, 3.0) and w.thing("mito").angle == pytest.approx(math.radians(30))


def test_an_object_with_a_typical_id_replaces_it_and_contents_none() -> None:
    w = world(ObjectSpec("nucleus", id="nucleus", size=9.0, width=8.0))
    assert w.thing("nucleus").size == 9.0 and len([e for e in w.entries if e.kind == "nucleus"]) == 1
    bare = world(ObjectSpec("mitochondrion", count=3), contents="none")
    assert [e.id for e in bare.entries] == ["mitochondrion"]
    with pytest.raises(VidgenError, match="the rough ER grows from the nuclear envelope; add a nucleus"):
        world(ObjectSpec("rough_er"), contents="none")
    with pytest.raises(VidgenError, match="two objects have the id 'm'"):
        world(ObjectSpec("mitochondrion", id="m"), ObjectSpec("lysosome", id="m"))
    with pytest.raises(VidgenError, match="cell size 2 µm"):
        world(size=2.0)


# ----- camera, level of detail, zoom ---------------------------------------------------------------


def test_levels_frame_their_subject() -> None:
    w = world()
    cell = level_view(w, "cell", ASPECT)
    assert cell.center == (0.0, 0.0) and cell.span == pytest.approx(16 / 0.93)   # the short axis fills 93 % of a landscape body
    assert level_view(w, "cell", 0.6).span == pytest.approx(20 / 0.93)          # the long axis across a portrait body
    assert level_view(w, "tissue", ASPECT).span == pytest.approx(64.0)
    mito = level_view(w, "organelle", ASPECT, "mitochondria")
    assert mito.center == pytest.approx(focus_point(w, "mitochondria", "organelle")[0]) and 2.0 < mito.span < 4.0
    ribosome = level_view(w, "complex", ASPECT, "rough_er")
    near = min(w.members("rough_er.ribosomes"), key=lambda p: math.dist(p.center, ribosome.center))
    assert math.dist(near.center, ribosome.center) < 1e-9 and ribosome.span == pytest.approx(0.125)
    pore = level_view(w, "complex", ASPECT, "nucleus")
    assert any(math.dist(p.center, pore.center) < 1e-9 for p in w.members("nucleus.pores"))
    assert level_view(w, "organelle", ASPECT, "golgi", span=3.0).span == 3.0


def test_level_of_detail_follows_the_size_on_screen() -> None:
    cell = lod_weights(47.0, 20.0, 17.2)        # the cell view: 47 pixels per µm (1080-pixel frame)
    assert cell["particles"] > 0.9 and cell["particle_detail"] == 0.0 and cell["double_membrane"] < 0.01 and cell["bilayer"] == 0.0
    assert cell["cristae"] == 1.0 and cell["neighbours"] == 0.0
    organelle = lod_weights(400.0, 20.0, 2.6)
    assert organelle["double_membrane"] == 1.0 and organelle["bilayer"] == 0.0 and organelle["particle_detail"] < 0.2
    assert lod_weights(700.0, 20.0, 1.5)["particle_detail"] == 1.0     # a ribosome 17 px across shows its two subunits
    complex_ = lod_weights(7000.0, 20.0, 0.125)
    assert complex_["bilayer"] == 1.0 and BILAYER * 7000.0 == pytest.approx(35.0)
    assert lod_weights(13.0, 20.0, 64.0)["neighbours"] == 1.0 and lod_weights(13.0, 20.0, 64.0)["particles"] == 0.0


def test_zoom_path() -> None:
    (x, y), w = zoom_path((0.0, 0.0), 10.0, (0.0, 0.0), 0.1, 0.5)
    assert (x, y) == (0.0, 0.0) and w == pytest.approx(1.0)        # an even pace on a log scale
    assert zoom_path((0.0, 0.0), 1.0, (5.0, 0.0), 2.0, 0.0)[1] == pytest.approx(1.0)
    end = zoom_path((0.0, 0.0), 1.0, (5.0, 0.0), 2.0, 1.0)
    assert end[0] == pytest.approx((5.0, 0.0)) and end[1] == pytest.approx(2.0)
    far = zoom_path((0.0, 0.0), 0.1, (5.0, 0.0), 0.1, 0.5)
    assert far[1] > 1.0 and far[0][0] == pytest.approx(2.5)        # far apart: out on the way, in the middle
    widths = [zoom_path((0.0, 0.0), 0.1, (5.0, 0.0), 0.1, t / 10)[1] for t in range(11)]
    assert widths == sorted(widths[:6]) + sorted(widths[5:], reverse=True)[1:]


def test_shapes() -> None:
    capsule = Capsule(0.0, 0.0, 2.0, 0.7)
    assert capsule.contains((0.99, 0.0)) and not capsule.contains((1.01, 0.0)) and capsule.inset(0.1).length == pytest.approx(1.8)
    band = ArcBand(0.0, 0.0, 4.0, 0.05, 0.0, math.pi / 2)
    assert band.contains((4.0, 0.0)) and band.contains((0.0, 4.02)) and not band.contains((4.1, 0.0)) and not band.contains((-4.0, 0.0))
    assert band.length == pytest.approx(2 * math.pi)
    faces = band.faces(0.5)
    assert len(faces) == 2 * int(band.length / 0.5) and all(abs(math.hypot(*p) - 4.0) == pytest.approx(0.025) for p, _ in faces)
