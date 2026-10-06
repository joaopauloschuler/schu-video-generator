"""Step 29 scene types ``process`` (a pipeline with a travelling token) and ``network`` (a layered
neural network with forward-pass pulses): params, targets, layouts per frame, the token's path,
connections, ellipses, highlight and timing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_comparison_table import safe_area_of
from test_schema import errors
from vidgen import extensions, registry, schema
from vidgen.cli import project_problems
from vidgen.project import Project
from vidgen.scenes.network import Connection
from vidgen.scenes.process import rounded_path
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
PIPE = [{"label": "Collect", "icon": "database", "text": "from every service"}, {"label": "Clean", "icon": "funnel"}, {"label": "Train", "icon": "brain-circuit"}]
NET = [{"size": 3, "label": "In"}, {"size": 512, "label": "Hidden", "show": 4}, {"size": 2, "label": "Out"}]


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))


def process(**changes: Any) -> Any:
    return cls_of("process").validate_params({"stages": PIPE, **changes}, Theme())


def network(**changes: Any) -> Any:
    return cls_of("network").validate_params({"layers": NET, **changes}, Theme())


def n_beats(n: int) -> list[dict[str, str]]:
    return [{"text": "one two three four five six seven eight"} for _ in range(n)]


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- process: params -------------------------------------------------------------------------------


def test_process_params_and_defaults() -> None:
    p = cls_of("process").validate_params({"stages": ["Plan", {"label": "Do", "icon": "check"}]}, Theme())
    assert [s.label for s in p.stages] == ["Plan", "Do"] and p.stages[1].icon == "check"
    assert (p.layout, p.reveal, p.loop, p.token, p.token_icon) == ("auto", "per_beat", False, True, None)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"stages": ["a"]}, "at least 2"),
        ({"stages": [str(i) for i in range(9)]}, "at most 8"),
        ({"stages": ["a", "b", "a"]}, "stages[2]: label 'a' is used by stages[0] too"),
        ({"loop_label": "again"}, "loop_label needs loop: true"),
        ({"token": False, "token_label": "x"}, "token_icon and token_label need token: true"),
        ({"token_icon": "no-such-icon"}, "unknown icon"),
        ({"layout": "grid"}, "layout"),
    ],
)
def test_process_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=None) as caught:
        process(**changes)
    assert message in str(caught.value)


def test_process_target_names() -> None:
    cls = cls_of("process")
    assert cls.target_names(process()) == ["stage1", "stage:Collect", "stage2", "stage:Clean", "stage3", "stage:Train", "connector1", "connector2", "token"]
    full = process(heading="H", input="in", output="out", loop=True, token=False)
    assert cls.target_names(full) == ["heading", "input", "stage1", "stage:Collect", "stage2", "stage:Clean", "stage3", "stage:Train",
                                      "connector1", "connector2", "loop", "output"]


def test_rounded_path_keeps_straight_runs_and_rounds_corners() -> None:
    pts = [np.array(p, dtype=float) for p in ([0, 0, 0], [1, 0, 0], [2, 0, 0], [2, -1, 0], [0, -1, 0])]
    path = rounded_path(pts, 0.2)
    assert np.allclose(path.get_start(), pts[0]) and np.allclose(path.get_end(), pts[-1])
    assert path.get_right()[0] == pytest.approx(2.0) and path.get_bottom()[1] == pytest.approx(-1.0)
    assert not np.allclose(path.point_from_proportion(0.5), pts[3])   # the corner is cut


# ----- network: params -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("dense", ("dense", 0.35, 2)), ("sparse:0.2", ("sparse", 0.2, 2)), ("grouped 3", ("grouped", 0.35, 3)),
     ({"type": "sparse", "ratio": 0.5}, ("sparse", 0.5, 2)), ("one_to_one", ("one_to_one", 0.35, 2))],
)
def test_connection_forms(text: Any, expected: tuple[str, float, int]) -> None:
    c = Connection.model_validate(text)
    assert (c.type, c.ratio, c.groups) == expected


def test_connection_pairs() -> None:
    assert Connection(type="dense").pairs(2, 3, seed=1) == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    assert Connection(type="grouped", groups=2).pairs(4, 4, seed=1) == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 2), (2, 3), (3, 2), (3, 3)]
    assert Connection(type="one_to_one").pairs(3, 3, seed=1) == [(0, 0), (1, 1), (2, 2)]
    assert Connection(type="none").pairs(3, 3, seed=1) == []
    sparse = Connection(type="sparse", ratio=0.3).pairs(6, 6, seed=2)
    assert {i for i, _ in sparse} == set(range(6)) and {j for _, j in sparse} == set(range(6)) and len(sparse) < 36


def test_network_params_drawn_units_and_counts() -> None:
    p = cls_of("network").validate_params({"layers": [4, {"size": 512, "label": "H"}, {"size": 9, "show": 3, "connect": "sparse:0.5"}]}, Theme())
    assert [layer.size for layer in p.layers] == [4, 512, 9]
    assert [p.drawn(k) for k in range(3)] == [4, 6, 3] and [p.truncated(k) for k in range(3)] == [False, True, True]
    assert p.connection(1).type == "dense" and p.connection(2).type == "sparse" and p.connect.type == "dense"
    assert p.neuron("2.6") == (1, 5)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"layers": [3]}, "at least 2"),
        ({"highlight": ["2.5"]}, "layer 2 draws units 1..4"),
        ({"highlight": ["4.1"]}, "there is no layer 4"),
        ({"highlight": ["2-1"]}, "is not 'layer.unit'"),
        ({"count_format": "{m}"}, "is not a format with n"),
        ({"layers": [{"size": 2, "label": "a"}, {"size": 2, "label": "a"}]}, "layer labels must differ"),
        ({"layers": [{"size": 2, "connect": "dense"}, 3]}, "the first layer has no previous layer"),
        ({"connect": "fancy"}, "type"),
    ],
)
def test_network_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception) as caught:
        network(**changes)
    assert message in str(caught.value)


def test_network_target_names() -> None:
    cls = cls_of("network")
    names = cls.target_names(network(heading="H", layers=[*NET[:2], {"size": 2, "label": "Out", "connect": "none"}]))
    assert names == ["heading", "layer1", "layer:In", "neuron1.1", "neuron1.2", "neuron1.3", "layer2", "layer:Hidden", "neuron2.1",
                     "neuron2.2", "neuron2.3", "neuron2.4", "layer3", "layer:Out", "neuron3.1", "neuron3.2", "edges1"]


def test_schema_accepts_shorthands_and_validate_checks_targets(make_project) -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    scenes = [{"id": "p", "type": "process", "params": {"stages": ["a", {"label": "b"}]}, "duration": 2},
              {"id": "n", "type": "network", "params": {"layers": [2, {"size": 3, "connect": "grouped:3"}], "connect": "sparse:0.3"}, "duration": 2}]
    assert errors(doc, minimal_config(scenes=scenes)) == []
    scenes = [{"id": "p", "type": "process", "params": {"stages": PIPE}, "beats": beats([{"highlight": "stage:Clean"}], [{"dim": "stage:Clan"}])},
              {"id": "n", "type": "network", "params": {"layers": NET}, "beats": beats([{"highlight": "neuron2.4"}], [{"zoom": "neuron2.5"}])}]
    problems = project_problems(load(make_project, scenes))
    assert [p.location for p in problems] == ["scenes[0].beats[1].actions[0].target", "scenes[1].beats[1].actions[0].target"]
    assert "did you mean" in problems[0].message and "'stage:Clean'" in problems[0].message


# ----- process: rendering ------------------------------------------------------------------------------


def drawing(scene: Any) -> Any:
    return scene._drawing


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("p", "timing"),
    [
        ({"heading": "Pipeline", "stages": PIPE, "input": "Raw logs", "output": "Model", "token_label": "batch"}, 3),
        ({"stages": ["Plan", "Build", "Measure", "Learn"], "loop": True, "loop_label": "repeat", "token_icon": "rocket"}, 4),
        ({"heading": "Eight", "stages": [f"Stage {i}" for i in range(1, 9)], "reveal": "all", "loop": True, "input": "Order"}, 2),
        ({"stages": ["a", "b"], "token": False}, 0),
    ],
)
def test_process_renders_within_its_beats_and_the_safe_area(p: dict[str, Any], timing: int, size: tuple[int, int], make_project, media: Path) -> None:
    extra = {"beats": n_beats(timing)} if timing else {"duration": 2.0}
    project = load(make_project, [{"id": "s", "type": "process", "params": p, **extra}])
    scene, duration, portrait = render_scene(project, "s", media, *size)
    assert scene.plan.layout == ("column" if portrait else ("snake" if len(p["stages"]) == 8 else "row"))
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    safe = safe_area_of(size)
    for t in scene.targets:
        assert safe.contains(t.mobject, tolerance=0.05), t.name


@pytest.mark.render
def test_token_travels_to_each_stage_and_the_active_stage_is_emphasised(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "process", "params": {"stages": PIPE, "input": "in"}, "beats": n_beats(3)}])
    scene = render(project, "s", media)
    d = drawing(scene)
    xs = [c[0].get_x() for c in d.cards]
    assert xs == sorted(xs) and len({round(c[0].get_y(), 6) for c in d.cards}) == 1   # one row, left to right
    assert np.allclose(d.token.get_center(), d.rests[2], atol=1e-6)                    # waiting in front of the last stage
    assert d.rests[2][0] < d.cards[2][0].get_left()[0]
    active, normal = (scene.theme.color(c).lower() for c in ("highlight", "primary"))
    assert [c[0].get_stroke_color().to_hex().lower() for c in d.cards] == [normal, normal, active]
    assert d.cards[2][1].get_color().to_hex().lower() == active                          # its icon too
    assert all(plays(scene, b.id) for b in scene.beats)
    names = [a for b in scene.beats for anims in plays(scene, b.id) for a in anims]
    assert any("MoveAlongPath" in a for a in names)


@pytest.mark.render
def test_loop_returns_the_token_to_the_first_stage(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "process", "params": {"stages": ["a", "b", "c"], "loop": True}, "beats": n_beats(4)}])
    scene = render(project, "s", media)
    d = drawing(scene)
    assert np.allclose(d.token.get_center(), d.rests[-1], atol=1e-6)
    assert d.rests[-1][1] < d.cards[0][0].get_bottom()[1] and abs(d.rests[-1][0] - d.cards[0][0].get_x()) < 1e-6   # below stage 1
    assert d.loop.get_bottom()[1] < d.cards[0][0].get_bottom()[1]
    assert d.cards[0][0].get_stroke_color().to_hex().lower() == scene.theme.color("highlight").lower()


@pytest.mark.render
def test_column_in_portrait_and_layout_override(make_project, media: Path) -> None:
    project = load(make_project, [
        {"id": "v", "type": "process", "params": {"stages": PIPE, "token_label": "x"}, "beats": n_beats(3)},
        {"id": "r", "type": "process", "params": {"stages": PIPE, "layout": "row"}, "beats": n_beats(3)},
    ])
    scene = render(project, "v", media, size=(90, 160))
    d = drawing(scene)
    ys = [c[0].get_y() for c in d.cards]
    assert ys == sorted(ys, reverse=True) and len({round(c[0].get_x(), 6) for c in d.cards}) == 1
    assert d.tag.get_right()[0] <= d.cards[0][0].get_left()[0] + 1e-6   # the tag travels left of the column
    assert render(project, "r", media, size=(90, 160)).plan.layout == "row"


@pytest.mark.render
def test_early_stage_reveal_is_not_repeated(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "process", "params": {"stages": PIPE}, "beats": beats([{"reveal": "stage3"}], None, None)}])
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    d = drawing(scene)
    assert np.allclose(d.token.get_center(), d.rests[2], atol=1e-6)   # the token still went the whole way
    assert scene.is_shown("connector2")


@pytest.mark.render
@pytest.mark.slow
def test_overfull_process_is_scaled_into_the_frame_with_a_warning(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    stages = [{"label": f"A rather long stage name {i}", "text": "a detail line that keeps going for a while"} for i in range(1, 9)]
    project = load(make_project, [{"id": "s", "type": "process", "params": {"stages": stages, "input": "Customer order", "loop": True, "layout": "row"}, "duration": 1.0}])
    with caplog.at_level(logging.WARNING):
        scene = render(project, "s", media)
    assert any("do not fit this frame at the readable size" in r.getMessage() for r in caplog.records)
    safe = safe_area_of((160, 90))
    assert all(safe.contains(t.mobject, tolerance=0.05) for t in scene.targets)


# ----- network: rendering ------------------------------------------------------------------------------


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("p", "timing"),
    [
        ({"heading": "Net", "layers": NET, "highlight": ["1.1", "2.2", "3.2"]}, 4),
        ({"layers": [{"size": 9, "show": 9}, {"size": 9, "show": 9, "connect": "grouped:3"}, {"size": 9, "show": 9, "connect": "one_to_one"}],
          "max_neurons": 9, "reveal": "all", "passes": 2}, 3),
        ({"layers": [784, *[{"size": 64, "label": f"L{i}"} for i in range(1, 7)], 10], "counts": "all"}, 2),
        ({"layers": [2, 3]}, 0),
    ],
)
def test_network_renders_within_its_beats_and_the_safe_area(p: dict[str, Any], timing: int, size: tuple[int, int], make_project, media: Path) -> None:
    extra = {"beats": n_beats(timing)} if timing else {"duration": 2.0}
    project = load(make_project, [{"id": "s", "type": "network", "params": p, **extra}])
    scene, duration, portrait = render_scene(project, "s", media, *size)
    d = drawing(scene)
    axis = 1 if portrait else 0   # layers spread along x in 16:9, along y in 9:16
    spots = [round(float(layer.get_center()[axis]), 6) for layer in d.layers]
    assert len(set(spots)) == len(spots) and spots == sorted(spots, reverse=portrait)
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    safe = safe_area_of(size)
    for t in scene.targets:
        assert safe.contains(t.mobject, tolerance=0.05), t.name


@pytest.mark.render
def test_network_ellipsis_counts_edges_and_pass(make_project, media: Path) -> None:
    layers = [{"size": 3, "label": "In"}, {"size": 512, "label": "Hidden", "show": 4}, {"size": 4, "label": "Out", "connect": "grouped:2"}]
    project = load(make_project, [{"id": "s", "type": "network", "params": {"layers": layers}, "beats": n_beats(4)}])
    scene = render(project, "s", media)
    d = drawing(scene)
    assert [len(layer) for layer in d.layers] == [3, 4, 4]
    assert d.ellipses[0] is None and d.ellipses[2] is None and len(d.ellipses[1]) == 3
    gaps = np.diff([dot.get_y() for dot in d.layers[1]])
    assert abs(gaps[1]) == pytest.approx(2 * abs(gaps[0]), rel=1e-6)   # the ellipsis takes one slot in the middle
    def texts(caption: Any) -> list[str]:
        return [m.lines_text.original_text for m in caption.get_family() if hasattr(m, "lines_text")]

    assert texts(d.captions[1]) == ["Hidden", "512"] and texts(d.captions[0]) == ["In"] and texts(d.captions[2]) == ["Out"]
    assert len(d.bundles[0]) == 12 and len(d.bundles[1]) == 8 and d.pairs[1] == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 2), (2, 3), (3, 2), (3, 3)]
    colors = {line.get_stroke_color().to_hex().lower() for line in d.bundles[1]}
    assert len(colors) == 2   # grouped edges coloured by block
    last = [a for anims in plays(scene, scene.beats[3].id) for a in anims]
    assert any("LaggedStart" in a for a in last)   # the forward pass


@pytest.mark.render
def test_network_caps_edges_and_highlights_a_path(make_project, media: Path) -> None:
    layers = [{"size": 12, "show": 12}, {"size": 12, "show": 12, "connect": "sparse:0.2"}, {"size": 3}]
    p = {"layers": layers, "max_neurons": 12, "max_edges": 40, "passes": 0, "highlight": ["1.1", "2.12", "3.3"]}
    project = load(make_project, [{"id": "s", "type": "network", "params": p, "beats": n_beats(4)}])
    scene = render(project, "s", media)
    d = drawing(scene)
    assert len(d.bundles[0]) <= 40 + 12 and {i for i, _ in d.pairs[0]} == set(range(12))   # thinned, everyone connected
    color = scene.theme.color("highlight").lower()
    assert d.layers[0][0].get_fill_color().to_hex().lower() == color and d.layers[2][2].get_fill_color().to_hex().lower() == color
    assert d.layers[0][1].get_fill_opacity() == pytest.approx(scene.dimmed_opacity, abs=0.02)
    linked = [line for line, pair in zip(d.bundles[0], d.pairs[0]) if pair == (0, 11)]
    if linked:
        assert linked[0].get_stroke_color().to_hex().lower() == color
    else:   # not drawn by the connection: added in the highlight step
        assert any(isinstance(m, type(d.bundles[0][0])) and m.get_stroke_color().to_hex().lower() == color for m in scene.mobjects)


@pytest.mark.render
def test_network_early_layer_reveal_is_not_repeated(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "network", "params": {"layers": NET, "passes": 0}, "beats": beats([{"reveal": "layer3"}], None, None)}])
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert scene.is_shown("layer3")
    names = [a for anims in plays(scene, "s_b3") for a in anims]
    assert not any("GrowFromCenter" in a for a in names)   # only the edges into it were left
