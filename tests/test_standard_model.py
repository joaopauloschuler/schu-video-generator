"""The ``standard_model`` scene type (Phase Y, Step 237; DESIGN §99.4): params, targets, the
actions' checks, and tiny renders in 16:9 and 9:16 (cells laid out without overlaps, the
antiparticles action, couplings)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import render
from vidgen import extensions, registry
from vidgen.cli import project_problems
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("standard_model").cls


def test_params_and_targets() -> None:
    p = cls().validate_params({"title": "The Standard Model"})
    assert p.show == ["mass", "charge", "spin", "name"] and p.reveal == "groups" and p.source and p.key and not p.antiparticles
    names = cls().target_names(p)
    assert names[:6] == ["title", "chart", "header", "labels", "key", "source"]
    for name in ("particle:u", "particle:up", "particle:e", "particle:electron", "particle:nu_mu", "particle:muon_neutrino",
                 "particle:photon", "particle:gamma", "particle:W", "particle:H", "particle:higgs", "generation:3", "group:quarks",
                 "group:gauge_bosons", "group:fermions", "row:neutrinos"):
        assert name in names, name
    assert len(names) == len(set(names))
    assert cls().target_names(cls().validate_params({"key": False, "source": False}))[:3] == ["chart", "header", "labels"]
    assert cls().target_text(p, "particle:e") == "electron" and cls().target_text(p, "group:gauge_bosons") == "gauge bosons"
    anti = cls().validate_params({"antiparticles": True})
    assert cls().target_text(anti, "particle:e") == "positron" and cls().target_text(anti, "particle:photon") == "photon"
    assert cls().target_text(p, "generation:2") == "generation II"
    assert cls().validate_params({"show": ["mass", "mass", "name"]}).show == ["mass", "name"]


@pytest.mark.parametrize(
    ("params", "message"),
    [({"show": []}, "at least 1 item"), ({"show": ["width"]}, "Input should be"), ({"layout": "square"}, "Input should be"),
     ({"reveal": "rows"}, "Input should be"), ({"colour": "x"}, "Extra inputs")],
)
def test_param_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(params)


def test_actions_are_checked(make_project) -> None:
    def problems(scene: dict[str, Any]) -> list[str]:
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION))))]

    chart = {"id": "c", "type": "standard_model", "params": {}}
    assert problems({**chart, "beats": [{"text": "flip them", "actions": [{"action": "antiparticles"}]},
                                        {"text": "the photon", "actions": [{"couplings": "particle:photon"}, {"highlight": "generation:2"}]}]}) == []
    assert any("couplings acts on a boson" in m for m in problems({**chart, "beats": [{"text": "x", "actions": [{"couplings": "particle:e"}]}]}))
    assert any("couplings acts on a boson" in m for m in problems({**chart, "beats": [{"text": "x", "actions": [{"couplings": "group:bosons"}]}]}))
    assert any("unknown target" in m for m in problems({**chart, "beats": [{"text": "x", "actions": [{"highlight": "particle:muon_x"}]}]}))
    other = {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "go", "actions": [{"action": "antiparticles"}]}]}
    assert any("antiparticles is an action of standard_model scenes" in m for m in problems(other))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def _box(m: Any) -> tuple[float, float, float, float]:
    return (m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


@pytest.mark.render
@pytest.mark.parametrize("size", [(320, 180), (180, 320)], ids=["landscape", "portrait"])
def test_chart_renders_with_its_actions(size: tuple[int, int], make_project, media: Path) -> None:
    beats = [{"text": "six quarks in three generations"},
             {"text": "now flip them into antiparticles", "actions": [{"action": "antiparticles", "at": "@flip"}]},
             {"text": "the photon couples to charge", "actions": [{"couplings": "particle:photon", "at": 0.2}]},
             {"text": "and the higgs boson to mass"}]
    scene = {"id": "sm", "type": "standard_model", "params": {"title": "The Standard Model"}, "beats": beats}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "sm", media, size)
    assert s._arr == ("wide" if size[0] > size[1] else "tall")
    assert s._row_mode == (size[0] > size[1])        # wide cells: mass and charge on one line; tall: the classic column
    registered = sorted({n for t in s.targets for n in t.names})
    assert registered == sorted(type(s).target_names(s.params))
    assert all(s.is_shown(t) for t in s.targets)
    # the antiparticles action turned every quark and lepton; the bosons stay
    assert len(s._anti) == 12 and "photon" not in s._anti
    up = s._cells["u"]["shown"]
    looks = s._cells["u"]["looks"][True]
    assert all(up[k].width == pytest.approx(looks[k].width) for k in ("charge", "name", "symbol"))   # −2/3, anti-up, ū
    assert up["symbol"][1].get_stroke_opacity() == pytest.approx(1.0)   # ū: its bar
    assert getattr(s._labels["quarks"], "_word") == "antiquarks"
    # inside every cell no two texts overlap and all stay within the outline
    for t, v in s._cells.items():
        parts = list(v["shown"].values())
        box = _box(v["box"])
        for i, a in enumerate(parts):
            ba = _box(a)
            assert box[0] - 1e-6 <= ba[0] and ba[2] <= box[2] + 1e-6 and box[1] - 1e-6 <= ba[1] and ba[3] <= box[3] + 1e-6, t
            assert all(_overlap(ba, _box(b)) < 1e-9 for b in parts[i + 1:]), t
    # couplings drew outlines and is undone when the next beat starts (until_next_beat)
    assert s._coupling_parts and not any(o in s.mobjects for o in s._coupling_parts)
    # no two cells overlap; the chart stays in the frame
    boxes = [_box(v["box"]) for v in s._cells.values()]
    assert all(_overlap(a, b) == 0 for i, a in enumerate(boxes) for b in boxes[i + 1:])
    assert all(abs(x) <= s.frame_width / 2 for b in boxes for x in (b[0], b[2]))
