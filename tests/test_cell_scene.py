"""The ``cell`` scene type and the ``zoom_to`` action, Step 202 (DESIGN.md §95): params and their
errors, targets, validation of zoom_to, and tiny renders in 16:9 and 9:16 (the camera in µm,
level of detail, screen-sized labels and scale bar)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import project_with, render
from vidgen import extensions, registry
from vidgen.cli import project_problems
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def cell_cls() -> Any:
    extensions.load_builtins()
    return registry.get("cell").cls


def test_params_shorthands_and_lengths() -> None:
    p = cell_cls().validate_params({"cell": "animal", "objects": ["lysosome", {"kind": "mitochondrion", "at": ["5 um", "-5500 nm"], "size": "1.5 um"}],
                                    "view": "tissue"})
    spec = p.spec()
    assert spec.kind == "animal" and spec.size is None and p.world().size == 20.0 and p.view.level == "tissue"
    mito = spec.objects[1]
    assert mito.at == (5.0, -5.5) and mito.size == 1.5 and mito.where == "objects[1]"
    assert cell_cls().validate_params({"cell": {"size": "15 um", "aspect": 1.1}}).spec().size == 15.0


@pytest.mark.parametrize("params, message", [
    ({"objects": [{"kind": "ribosome", "in": "nucleus", "count": 4}]}, "a ribosome cannot be in the nucleoplasm"),
    ({"objects": [{"kind": "mitochondrion", "at": [-1.2, 0.6]}]}, r"objects\[0\] \(mitochondrion 'mitochondrion'\): at \[-1.2, 0.6\] µm, 2 µm long: that point is in the nucleoplasm"),
    ({"objects": [{"kind": "golgi", "size": "2 inches"}]}, "unknown unit"),
    ({"objects": [{"kind": "golgi", "at": [1]}]}, r"at is \[x, y\]"),
    ({"cell": "fungus"}, "Input should be 'animal', 'plant' or 'bacterium'"),
    ({"cell": {"kind": "animal", "gram": "positive"}}, "cell gram is for a bacterium, not an animal cell"),
    ({"cell": {"kind": "bacterium", "wall": "300 nm"}}, "cell wall is for a plant, not a bacterium"),
    ({"cell": "plant", "objects": ["centrosome"]}, "a centrosome cannot be in a plant cell"),
    ({"objects": [{"kind": "vesicle", "coat": "cop1"}]}, "Input should be 'none', 'clathrin', 'copi' or 'copii'"),
    ({"view": {"level": "organelle", "on": "mitocondria"}}, "view.on: 'mitocondria' is not an object of this cell; did you mean 'mitochondria'"),
    ({"view": "molecular"}, "Input should be 'tissue', 'cell', 'organelle' or 'complex'"),
])
def test_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cell_cls().validate_params(params)


def test_target_names() -> None:
    cls = cell_cls()
    names = cls.target_names(cls.validate_params({"title": "T", "objects": [{"kind": "ribosome", "id": "mitoribosomes", "in": "mitochondria", "count": 3}]}))
    assert names[:3] == ["title", "cell", "tissue"] and names[-1] == "scale_bar"
    assert {"nucleus", "rough_er", "golgi", "mitochondria", "ribosomes", "mitoribosomes"} <= set(names)
    assert "nucleus.pores" not in names and "rough_er.ribosomes" not in names   # bound complexes belong to their structure
    assert cls.target_names(cls.validate_params({"contents": "none", "scale_bar": False})) == ["cell", "tissue"]


def scene_config(actions_per_beat: list[list[dict[str, Any]] | None], **params: Any) -> dict[str, Any]:
    words = ["The cell is about twenty micrometres across", "zoom into the mitochondrion now please", "then a ribosome on the rough membrane"]
    beats = [{"text": words[k % 3], **({"actions": a} if a else {})} for k, a in enumerate(actions_per_beat)]
    return {"id": "c", "type": "cell", "params": {"title": "Cell", **params}, "beats": beats}


def test_zoom_to_is_validated(make_project) -> None:
    project = project_with(make_project, [
        scene_config([[{"zoom_to": "mitocondria"}], [{"zoom_to": "title"}], [{"zoom_to": ["nucleus", "golgi"]}]]),
        {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "a", "actions": [{"zoom_to": "item1"}]}]},
    ], narration=NARRATION)
    problems = [(p.location, p.message) for p in project_problems(project)]
    assert any(loc.endswith("beats[0].actions[0].target") and "mitocondria" in msg for loc, msg in problems)
    assert any(loc.endswith("beats[1].actions[0].target") and "not 'title'" in msg for loc, msg in problems)
    assert any(loc.endswith("beats[2].actions[0].target") and "one target" in msg for loc, msg in problems)
    assert any(loc.startswith("scenes[1]") and "zoom_to is a cell action" in msg for loc, msg in problems)
    good = project_with(make_project, [scene_config([[{"zoom_to": "rough_er", "level": "complex", "at": "@twenty"}], None])], narration=NARRATION)
    assert project_problems(good) == []


def test_zoom_to_labels_are_validated(make_project) -> None:
    project = project_with(make_project, [scene_config([[{"zoom_to": "mitochondria", "labels": ["crista", "matrx"]}], None])], narration=NARRATION)
    problems = [p.message for p in project_problems(project)]
    assert any("labels: 'matrx' is not a part this view names; did you mean 'matrix'" in m for m in problems)
    fine = project_with(make_project, [scene_config([[{"zoom_to": "mitochondria", "labels": ["crista", "matrix"]}], [{"zoom_to": "cell", "labels": False}]])],
                        narration=NARRATION)
    assert project_problems(fine) == []


def test_yaml_reads_on_as_true() -> None:
    # YAML 1.1 reads the key `on` as true: {kind: ribosome, on: rough_er} must still mean on
    p = cell_cls().validate_params({"objects": [{"kind": "ribosome", True: "rough_er", "count": 3}], "view": {"level": "complex", True: "rough_er"}})
    assert p.objects[0].on == "rough_er" and p.view.on == "rough_er"
    assert all(t.surface == "rough_er" for t in p.world().members("ribosome"))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def pixels_of(scene: Any) -> float:
    """Screen units per scene unit now (the camera's zoom)."""
    return scene._frame[0] / float(scene.camera.frame.width)


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_zoom_levels_detail_labels_and_scale_bar(size: tuple[int, int], make_project, media: Path) -> None:
    config = scene_config([None, [{"zoom_to": "mitochondria", "at": "@mitochondrion"}], [{"zoom_to": "rough_er", "level": "complex", "at": "@ribosome"}]])
    project = Project.load(make_project(minimal_config(scenes=[config], narration=NARRATION)))
    scene = render(project, "c", media, size)
    assert (scene.body.width < scene.body.height) == (size[1] > size[0])
    zooms = [p for p in scene.play_log if "CellZoom" in p.animations]
    assert [p.beat for p in zooms] == ["c_b2", "c_b3"]
    starts = {t.beat_id: t.start for t in scene.beat_log}
    assert zooms[0].start > starts["c_b2"] + 0.5                  # on the word, not at the beat's start
    # the camera ended on the complex view: 0.125 µm across the body, a ribosome in its middle
    _s, px_per_um, span = scene.screen_scale()
    assert span == pytest.approx(0.125, rel=1e-3)
    keys = scene.layout_keys(None)["cell"]
    assert keys["scale_bar"] == "20 nm" and keys["lod"]["bilayer"] == 1.0 and keys["lod"]["particle_detail"] == 1.0
    # labels, title and scale bar keep their size on screen at a 150x zoom
    title = next(t for t in scene.targets if t.name == "title").mobject
    assert title.height * pixels_of(scene) == pytest.approx(scene._pinned[0][0].height * pixels_of(scene))
    for label in scene._labels:
        assert label.words.get_fill_opacity() == 0.0              # the start view's labels have faded
    # the zoomed view names its parts (a ribosome, its subunits, the ER membrane and lumen), screen-sized
    width, _cam, view_labels = scene._view_labels[-1]
    shown = [lab for lab in view_labels if lab.words.get_fill_opacity() > 0.9]
    assert len(shown) >= 4
    for label in shown:
        assert label.box.height * pixels_of(scene) == pytest.approx(label.height, rel=1e-6)
    assert all(lab.words.get_fill_opacity() == 0.0 for lab in scene._view_labels[0][2])   # the mitochondrion's are gone
    bar = scene._bar_texts["20 nm"]
    assert bar.get_fill_opacity() == 1.0 and all(t.get_fill_opacity() == 0.0 for k, t in scene._bar_texts.items() if k != "20 nm")
    # strokes stay thin on screen: a membrane line is drawn its true 5 nm wide
    piece = next(p for p in scene.drawing.pieces if p.true_um == pytest.approx(0.005) and p.stroke > 0 and p.lod > 0.99)
    assert piece.mobject.get_stroke_width() * 0.01 * scene.ref_pixels * pixels_of(scene) == pytest.approx(0.005 * px_per_um, rel=1e-3)


@pytest.mark.render
def test_start_view_labels_and_reveal_per_beat(make_project, media: Path) -> None:
    config = scene_config([None, None, None], reveal="per_beat", view={"level": "organelle", "on": "golgi"}, labels=True)
    project = Project.load(make_project(minimal_config(scenes=[config], narration=NARRATION)))
    scene = render(project, "c", media)
    assert scene.start.level == "organelle" and scene.start.span == pytest.approx(scene.layout_keys(None)["cell"]["span_um"])
    # a zoomed start view names the parts it shows (not the objects round it)
    assert scene._labels == []
    shown = {lab.words.get_fill_opacity() > 0.5 for lab in scene._view_labels[0][2]}
    assert shown == {True} and len(scene._view_labels[0][2]) >= 3
    assert all(scene.is_shown(name) for name in ("cell", "nucleus", "golgi"))


def _pieces_of(scene: Any, entry: str) -> list[Any]:
    family = {id(m) for m in scene.drawing.groups[entry].get_family()}
    return [p for p in scene.drawing.pieces if id(p.mobject) in family]


@pytest.mark.render
def test_a_dim_during_a_zoom_keeps_its_opacity(make_project, media: Path) -> None:
    # the 202 gap: a dim played while a zoom changes the level of detail left pieces at the wrong opacity
    config = scene_config([None, [{"dim": "rough_er", "opacity": 0.4, "at": "@zoom"},
                                  {"zoom_to": "rough_er", "level": "complex", "at": "@zoom"}], [{"highlight": "nucleus", "at": "@then"}]])
    project = Project.load(make_project(minimal_config(scenes=[config], narration=NARRATION)))
    scene = render(project, "c", media)
    shown = [p for p in _pieces_of(scene, "rough_er") if p.lod > 0.99 and p.fill > 0]
    assert shown
    for piece in shown:       # the pieces drawn at the complex level (hidden when the dim began) are dimmed too
        assert piece.mobject.get_fill_opacity() == pytest.approx(piece.fill * 0.4, abs=0.02), piece.feature
    nucleus = [p for p in _pieces_of(scene, "nucleus") if p.lod > 0.99 and p.fill > 0]
    assert nucleus and all(p.mobject.get_fill_opacity() > 0.5 for p in nucleus)   # a highlight keeps what the zoom shows
    from vidgen.scenes.cell import cell_scale_bar
    start_text = cell_scale_bar(scene.start.span)[1]
    assert {"2 nm", "5 nm", "100 nm", start_text} <= set(scene._bar_texts)          # texts for any zoom, a built-in zoom too


@pytest.mark.render
@pytest.mark.parametrize("kind, size", [("plant", (160, 90)), ("bacterium", (90, 160))])
def test_plant_and_bacterium_render(kind: str, size: tuple[int, int], make_project, media: Path) -> None:
    config = scene_config([None, [{"zoom_to": "cell", "level": "complex", "at": "@mitochondrion"}]], cell=kind)
    project = Project.load(make_project(minimal_config(scenes=[config], narration=NARRATION)))
    scene = render(project, "c", media, size)
    assert any(lab.entry_id == "cell" for lab in scene._labels)           # the cell's own wall or outer membrane is named
    keys = scene.layout_keys(None)["cell"]
    assert keys["lod"]["bilayer"] == 1.0
    shown = [lab for lab in scene._view_labels[-1][2] if lab.words.get_fill_opacity() > 0.9]
    assert len(shown) >= 4                                               # plasmodesma / envelope parts named


@pytest.mark.render
def test_surface_style_and_cytoskeleton(make_project, media: Path) -> None:
    config = scene_config([None, [{"zoom_to": "kinesin", "at": "@mitochondrion"}], [{"zoom_to": "mito", "level": "complex", "at": "@ribosome"}]],
                          style="surface", contents="none",
                          objects=["nucleus", "centrosome", {"kind": "microtubule", "count": 12}, {"kind": "kinesin", "on": "microtubule", "cargo": True},
                                   {"kind": "mitochondrion", "id": "mito", "at": [6, 2]}])
    project = Project.load(make_project(minimal_config(scenes=[config], narration=NARRATION)))
    scene = render(project, "c", media)
    assert scene.world.thing("mito").option("style") == "surface"
    _s, _px, span = scene.screen_scale()
    assert span == pytest.approx(0.06, rel=1e-3)                          # a membrane face on, lipid by lipid
    heads = [p for p in _pieces_of(scene, "mito") if p.feature == "lipids" and p.lod > 0.99]
    assert heads and len(heads[0].mobject.points) > 4 * 1000
