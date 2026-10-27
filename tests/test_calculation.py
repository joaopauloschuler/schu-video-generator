"""The ``calculation`` scene type (Phase W Step 225): params and their checks, targets, the
actions ``substitute`` / ``compute`` / ``convert``, results taken from another scene, and tiny
renders in 16:9 and 9:16."""

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

NARRATION = {"pad": 0.2, "words_per_second": 3.0}
ORBIT = {"title": "Orbital speed",
         "symbols": [{"name": "G", "constant": "G"}, {"name": "M_sun", "constant": "M_sun"}, {"name": "r", "constant": "AU", "meaning": "Earth–Sun distance"}],
         "calculations": [{"name": "v", "expr": "sqrt(G*M_sun/r)", "sig": 3, "convert": "km/s", "meaning": "orbital speed"}]}
RISK = {"symbols": [{"name": "a", "value": "2/3"}, {"name": "b", "value": "1/25"}, {"name": "c", "value": "1/4", "show": False}],
        "calculations": [{"name": "P", "expr": "a*b*c"}, {"name": "Q", "expr": "1 - P", "format": "percent"}]}


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("calculation").cls


def params(**p: Any) -> Any:
    return cls().validate_params(p)


def test_params_work_the_calculation() -> None:
    p = params(**ORBIT)
    worked = p.worked()
    (v,) = worked.results
    assert v.conversions[0].value_text() == "29.8 km/s"
    assert worked.symbols["r"].tex == "r" and worked.symbols["M_sun"].tex == r"M_{\odot}"


@pytest.mark.parametrize(
    ("p", "message"),
    [
        ({"calculations": []}, "at least 1 item"),
        ({"symbols": [{"name": "x", "value": "3 m"}], "calculations": [{"name": "y", "expr": "x + z"}]}, "unknown symbol 'z'"),
        ({"symbols": [{"name": "x", "value": "3 m"}, {"name": "t", "value": "2 s"}], "calculations": [{"name": "y", "expr": "x + t"}]},
         r"cannot add 'x' and 't': length \(m\) vs time \(s\)"),
        ({"symbols": [{"name": "x", "value": "3 meter"}], "calculations": [{"name": "y", "expr": "x"}]}, "unknown unit 'meter'"),
        ({"symbols": [{"name": "x", "constant": "Gee"}], "calculations": [{"name": "y", "expr": "x"}]}, "unknown constant 'Gee'"),
        ({"symbols": [{"name": "x", "from_scene": ".v"}], "calculations": [{"name": "y", "expr": "x"}]}, "from_scene names a scene"),
        ({"calculations": [{"name": "y", "expr": "1/0"}]}, "division by zero"),
        ({"calculations": [{"name": "y", "expr": "2", "sig": 0}]}, "sig: 0 is impossible"),
        ({"calculations": [{"name": "y", "expr": "2", "format": "fancy"}]}, "Input should be"),
    ],
)
def test_params_errors(p: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(p)


def test_targets() -> None:
    names = cls().target_names(params(**RISK))
    assert names == ["table", "symbol:a", "row:a", "symbol:b", "row:b", "symbol:c",
                     "calc1", "calc:P", "formula1", "substitution1", "result1", "result:P", "symbol:P", "row:P",
                     "calc2", "calc:Q", "formula2", "substitution2", "result2", "result:Q", "symbol:Q"]
    assert "conversion1" in cls().target_names(params(**ORBIT))
    assert "table" not in cls().target_names(params(**{**RISK, "table": "none"}))


def scene(sid: str, p: dict[str, Any], beats: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": sid, "type": "calculation", "params": p, "beats": beats or [{"text": "one two three"}]}


def test_actions_are_checked(make_project) -> None:
    def problems(p: dict[str, Any], actions: list[dict[str, Any]], kind: str = "calculation") -> list[str]:
        sc = {"id": "c", "type": kind, "params": p, "beats": [{"text": "one two three", "actions": actions}]}
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[sc], narration=NARRATION))))]

    assert problems(ORBIT, [{"substitute": "calc1", "at": "@two"}, {"compute": "calc:v", "at": "@three"}, {"convert": "calc1"},
                            {"highlight": "symbol:G"}, {"reveal": "formula1"}]) == []
    assert any("convert needs a calculation with convert" in m for m in problems(RISK, [{"convert": "calc1"}]))
    assert any("compute acts on calculations" in m and "did you mean 'calc1'" in m for m in problems(ORBIT, [{"compute": "calc11"}]))
    assert any("substitute is an action of calculation scenes" in m for m in problems({"latex": "x"}, [{"substitute": "step1"}], kind="equation"))


def test_results_from_another_scene(make_project) -> None:
    period = {"symbols": [{"name": "v", "from_scene": "orbit"}, {"name": "r", "constant": "AU"}],
              "calculations": [{"name": "T", "expr": "2*pi*r/v", "unit": "d", "sig": 3}]}
    root = make_project(minimal_config(scenes=[scene("orbit", ORBIT), scene("period", period)], narration=NARRATION))
    project = Project.load(root)
    assert [m.message for m in project_problems(project)] == []
    p = cls().validate_params(period)
    assert p.worked(lenient=True).results == []                                   # without the project: skipped, not an error
    assert p.worked(project).results[0].value.value_text() == "365 d"

    def problem(sym: dict[str, Any]) -> str:
        bad = {**period, "symbols": [sym, {"name": "r", "constant": "AU"}]}
        found = [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[scene("orbit", ORBIT), scene("period", bad)], narration=NARRATION))))]
        assert found
        return found[0]

    assert "no calculation scene 'orbt'" in problem({"name": "v", "from_scene": "orbt"}) and "did you mean 'orbit'" in problem({"name": "v", "from_scene": "orbt"})
    assert "scene 'orbit' computes v, not 'w'" in problem({"name": "v", "from_scene": "orbit.w"})


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
def test_calculation_scenes_render(size: tuple[int, int], make_project, media: Path) -> None:
    beats = [{"text": "the formula and the numbers", "actions": [{"substitute": "calc1", "at": "@numbers"}]},
             {"text": "about thirty kilometres per second", "actions": [{"compute": "calc1", "at": "@thirty"}, {"highlight": "symbol:G"}]}]
    scenes = [scene("orbit", ORBIT, beats), scene("risk", RISK, [{"text": "multiply"}, {"text": "and the rest"}])]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    s = render(project, "orbit", media, size)
    assert all(s.is_shown(t) for t in s.find_targets("*1")) and s.is_shown("table")
    kinds = [row.kind for row in s._calcs[0].rows]
    assert kinds == ["formula", "substitute", "intermediate", "result", "convert"]
    lefts = {round(float(row.tex.id_to_vgroup_dict["vgrel"].get_left()[0]), 4) for row in s._calcs[0].rows}
    assert len(lefts) == 1                                             # aligned at the equals sign
    r = render(project, "risk", media, size)
    assert r.is_shown("result2") and not r.is_shown("formula1")        # the first calculation left, its result joined the table
    assert r.is_shown("row:P") and not r.find_targets("row:c")
