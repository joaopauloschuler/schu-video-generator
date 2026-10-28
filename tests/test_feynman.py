"""Feynman diagrams (Phase Y, Step 238; DESIGN §99.5–§99.6): the vertex rules of the Standard
Model (allowed and forbidden), charge / lepton / baryon numbers at vertices and along fermion
lines, colour, the presets, deterministic uncrossed layouts, the ``feynman`` scene's params,
targets, actions and tiny renders in 16:9 and 9:16."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import render
from vidgen import extensions, registry
from vidgen.cli import project_problems
from vidgen.errors import VidgenError
from vidgen.particle_physics import PARTICLES, feynman as fy, feynman_layout as fl
from vidgen.project import Project

NARRATION = {"pad": 0.2, "words_per_second": 4.0}
P = PARTICLES


def rule(into: str, out: str) -> tuple[Any, str | None]:
    return fy.vertex_rule([P[k] for k in into.split()], [P[k] for k in out.split()])


@pytest.mark.parametrize(
    ("into", "out", "kind"),
    [("e-", "e- gamma", "QED"), ("e- e+", "gamma", "QED"), ("gamma", "u anti-u", "QED"), ("u", "u g", "QCD"), ("g", "g g", "ggg"),
     ("g g", "g g", "gggg"), ("mu-", "nu_mu W-", "CC"), ("W-", "e- anti-nu_e", "CC"), ("d", "u W-", "CC"), ("s", "u W-", "CC"),
     ("t", "b W+", "CC"), ("nu_e", "nu_e Z", "NC"), ("Z", "mu- mu+", "NC"), ("t anti-t", "H", "Hff"), ("H", "b anti-b", "Hff"),
     ("H", "W+ W-", "HVV"), ("H", "Z Z", "HVV"), ("H", "H H", "HHH"), ("W+", "W+ gamma", "VVV"), ("W+ W-", "Z", "VVV"),
     ("W+ W-", "W+ W-", "VVVV"), ("H H", "Z Z", "HHVV")],
)
def test_allowed_vertices(into: str, out: str, kind: str) -> None:
    found, why = rule(into, out)
    assert why is None and found is not None and found.kind == kind


@pytest.mark.parametrize(
    ("into", "out", "message"),
    [("nu_e", "nu_e gamma", "couples to electric charge"), ("e-", "e- g", "a lepton and has none"), ("e-", "mu- gamma", "does not change flavour"),
     ("u", "c Z", "no flavour-changing neutral currents"), ("e-", "nu_mu W-", "neutrino of its own family"), ("u", "u W+", "changes the charge"),
     ("e-", "d W-", "never turns a quark into a lepton"), ("nu_e", "nu_e H", "massless in the Standard Model"),
     ("H", "gamma gamma", "no tree-level H γ γ vertex"), ("g g", "H", "no tree-level H g g vertex"), ("Z", "Z Z", "no Standard Model vertex joins"),
     ("gamma", "gamma gamma", "no Standard Model vertex joins"), ("e- e+", "mu- mu+", "draw the W"), ("e-", "e- gamma gamma", "two fermion lines and one boson"),
     ("e- e-", "gamma", "arrows must run through the vertex")],
)
def test_forbidden_vertices(into: str, out: str, message: str) -> None:
    found, why = rule(into, out)
    assert found is None and why is not None and message in why, why


def test_loop_only_vertices_point_to_the_loop_presets() -> None:
    assert "preset h_to_gammagamma" in rule("H", "gamma gamma")[1]
    assert "preset gg_to_h" in rule("g g", "H")[1]


def test_couplings_are_computed() -> None:
    assert 1 / fy.ALPHA == pytest.approx(137.036, abs=0.001)
    assert fy.V_HIGGS == pytest.approx(246.22, abs=0.01)
    assert fy.g_weak() == pytest.approx(0.6528, abs=0.001)
    assert fy.yukawa(P["t"]) == pytest.approx(0.991, abs=0.002)
    assert "1/137" in rule("e-", "e- gamma")[0].coupling and "0.118" in rule("u", "u g")[0].coupling
    assert "|V_us| ≈ 0.22" in rule("s", "u W-")[0].coupling and "CKM-suppressed" in rule("s", "u W-")[0].note
    assert "CKM-suppressed" not in rule("d", "u W-")[0].note
    assert "52 GeV" in rule("H", "W+ W-")[0].coupling     # 2 m_W² / v
    assert "191 GeV" in rule("H", "H H")[0].coupling      # 3 m_H² / v


def diagram(lines: list[str], groups: list[dict[str, Any]] | None = None) -> Any:
    specs = []
    for text in lines:
        line_id, rest = text.split(":")
        particle, start, _, end = rest.split()
        specs.append({"id": line_id, "particle": particle, "from": start, "to": end})
    return fy.build_diagram("d", specs, groups or [])


def test_charge_and_lepton_numbers_are_checked_at_each_vertex() -> None:
    wrong_sign = fy.check_diagram(diagram(["mu: mu- in -> v1", "nu: nu_mu v1 -> out", "w: W+ v1 -> v2", "e: e+ v2 -> out", "n: nu_e v2 -> out"]))
    assert not wrong_sign.ok
    assert any("charge not conserved" in p and "vertex v1" in p for p in wrong_sign.problems)
    family = fy.check_diagram(diagram(["mu: mu- in -> v1", "nu: nu_e v1 -> out", "w: W- v1 -> v2", "e: e- v2 -> out", "n: anti-nu_e v2 -> out"]))
    assert any("neutrino of its own family" in p for p in family.problems)
    assert any("muon number not conserved" in p for p in family.problems)
    good = fy.check_diagram(fy.preset_diagrams("muon_decay")[0])
    assert good.ok and good.verdict.allowed and good.verdict.interaction == "weak"
    assert [c.text() for c in good.chains] == ["μ⁻ → ν_μ: L_μ = +1 along the line", "νₑ → e⁻: L_e = +1 along the line"]
    v1 = good.vertex("v1")
    assert v1.text() == "μ⁻ → ν_μ W⁻" and v1.rule.kind == "CC"
    assert v1.conservation_text() == "Q: −1 → 0 + −1 ✓ · B: 0 → 0 + 0 ✓ · L_μ: +1 → +1 + 0 ✓"


def test_baryon_number_and_colour() -> None:
    assert fy.colour_problem([P["u"]], [P["u"], P["g"]]) is None
    assert fy.colour_problem([P["g"]], [P["g"], P["g"]]) is None
    assert fy.colour_problem([P["u"], P["u"]], [P["g"]]) is not None          # two quarks into a gluon
    assert fy.colour_problem([P["e-"]], [P["e-"], P["g"]]) is not None        # a gluon alone among colourless lines
    beta = fy.check_diagram(fy.preset_diagrams("beta_decay")[0])
    assert [c.text() for c in beta.chains][0] == "d → u: B = 1/3 along the line"
    bad = fy.check_diagram(diagram(["a: u in -> v1", "b: u in -> v1", "g: g v1 -> v2", "c: u v2 -> out", "d: anti-u v2 -> out"]))
    assert any("baryon number not conserved" in p for p in bad.problems)


def test_whole_reaction_and_hadrons_are_checked() -> None:
    beta = fy.preset_diagrams("beta_decay", spectators=True)[0]
    checked = fy.check_diagram(beta)
    assert checked.ok and str(checked.hadron_verdict.process) == "n → p e⁻ ν̄ₑ" and checked.hadron_verdict.interaction == "weak"
    pion = fy.check_diagram(fy.preset_diagrams("pion_decay")[0])
    assert str(pion.hadron_verdict.process) == "π⁺ → μ⁺ ν_μ" and pion.hadron_verdict.allowed
    assert "fermion line" in checked.explain() and "as hadrons: n → p e⁻ ν̄ₑ" in checked.explain()


@pytest.mark.parametrize("key", list(fy.PRESETS))
def test_presets_validate_and_lay_out_without_crossings(key: str) -> None:
    for spectators in (False, True):
        for d in fy.preset_diagrams(key, spectators):
            checked = fy.check_diagram(d)
            assert checked.ok, checked.explain()
            lay = fl.layout(d)
            assert lay.crossings == 0, (key, d.name)
            again = fl.layout(fy.preset_diagrams(key, spectators)[[x.name for x in fy.preset_diagrams(key, spectators)].index(d.name)])
            assert again == lay      # deterministic
            assert d.loops == (1 if key in ("gg_to_h", "h_to_gammagamma") else 0)


def test_layout_channels() -> None:
    s, t = fy.preset_diagrams("bhabha")
    ls, lt = fl.layout(s), fl.layout(t)
    assert ls.columns == {"v1": 0, "v2": 1} and ls.timelike["photon"]           # s-channel: a timelike propagator
    assert lt.columns == {"v1": 0, "v2": 0} and not lt.timelike["photon"]       # t-channel: the vertices share a time
    assert lt.vertices["v1"][1] > lt.vertices["v2"][1]
    _, u = fy.preset_diagrams("moller")
    lu = fl.layout(u)       # u-channel: drawn uncrossed with the outgoing legs swapped
    assert lu.crossings == 0 and lu.lines["e2_out"].end[1] > lu.lines["e1_out"].end[1]
    _, w = fy.preset_diagrams("h_to_gammagamma")
    lw = fl.layout(w)
    assert lw.columns == {"v1": 0, "v2": 1, "v3": 1} and lw.times("loop2") == (lw.vertices["v2"][0],) * 2
    muon = fl.layout(fy.preset_diagrams("muon_decay")[0])
    assert muon.vertices["v1"][0] < muon.vertices["v2"][0] and muon.timelike["W"]


def test_custom_tree_layouts_are_uncrossed() -> None:
    # e+ e- -> W+ W- through a neutrino exchange (t-channel) written in a crossing order
    d = diagram(["em: e- in -> v1", "ep: e+ in -> v2", "wm: W- v1 -> out", "wp: W+ v2 -> out", "nu: nu_e v1 -> v2"])
    assert fy.check_diagram(d).ok
    assert fl.layout(d).crossings == 0
    bubble = diagram(["a: gamma in -> v1", "l1: e- v1 -> v2", "l2: e+ v1 -> v2", "b: gamma v2 -> out"])
    lay = fl.layout(bubble)
    assert lay.lines["l1"].bend == -lay.lines["l2"].bend != 0 and lay.crossings == 0


@pytest.mark.parametrize(
    ("lines", "message"),
    [(["a: e- out -> v1", "b: e- v1 -> out", "c: gamma v1 -> out"], "lines run forward in time"),
     (["a: e- in -> v1", "b: e- v1 -> out"], r"joins 2 line\(s\)"),
     (["a: e- in -> v1", "b: e- v1 -> out", "c: gamma v1 -> out", "d: e- in -> v2", "e: e- v2 -> out", "f: gamma v2 -> out"], "not joined"),
     (["a: p in -> v1", "b: p v1 -> out", "c: gamma v1 -> out"], "is a hadron"),
     (["a: e- in -> v1", "b: e- v1 -> v1", "c: gamma v1 -> out"], "no tadpoles"),
     (["a: e- in -> out"], "only spectator quarks"),
     (["a: e- in -> v1", "b: e- v1 -> out", "c: gamma v1 -> out", "d: gamma v1 -> out", "e: gamma v1 -> out"], "joins 5 lines"),
     (["a: muon_x in -> v1", "b: e- v1 -> out", "c: gamma v1 -> out"], "unknown particle")],
)
def test_structure_errors(lines: list[str], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        diagram(lines)


def test_group_errors() -> None:
    lines = ["u: u in -> v1", "d: anti-d in -> v1", "w: W+ v1 -> v2", "m: mu+ v2 -> out", "n: nu_mu v2 -> out"]
    with pytest.raises(VidgenError, match="π⁻ is .*; the lines u, d carry"):
        diagram(lines, [{"particle": "pi-", "side": "initial", "lines": ["u", "d"]}])
    with pytest.raises(VidgenError, match="is not an outgoing line"):
        diagram(lines, [{"particle": "pi+", "side": "final", "lines": ["u", "d"]}])
    with pytest.raises(VidgenError, match="not a hadron"):
        diagram(lines, [{"particle": "mu+", "lines": ["u"]}])


# ----- the scene ------------------------------------------------------------------------------------


def cls() -> Any:
    extensions.load_builtins()
    return registry.get("feynman").cls


def test_params_and_targets() -> None:
    p = cls().validate_params({"preset": "bhabha", "title": "Bhabha"})
    assert p.time == "right" and p.reveal == "time" and p.process and p.time_axis
    names = cls().target_names(p)
    assert names == ["title", "process", "diagram", "time_axis", "line:e_minus", "line:e_plus", "line:photon", "line:e_minus_out", "line:e_plus_out",
                     "vertex:v1", "vertex:v2"]
    assert cls().target_text(p, "line:photon") == "photon" and cls().target_text(p, "line:e_plus") == "positron"
    beta = cls().validate_params({"preset": "beta_decay", "spectators": True})
    assert "hadron:n" in cls().target_names(beta) and cls().target_text(beta, "hadron:p") == "proton"
    custom = cls().validate_params({"diagrams": [{"name": "s", "lines": ["e- in -> v1", "e+ in -> v1", "ph: gamma v1 -> v2",
                                                                         {"particle": "mu-", "from": "v2", "to": "out"}, "mu+ v2 -> out"]}]})
    assert cls().target_names(custom)[3:] == ["line:l1", "line:l2", "line:ph", "line:l4", "line:l5", "vertex:v1", "vertex:v2"]


@pytest.mark.parametrize(
    ("params", "message"),
    [({}, "give a preset or diagrams"), ({"preset": "bhabha", "diagrams": [{"lines": ["e- in -> v1", "e- v1 -> out", "gamma v1 -> out"]}]}, "one of the two"),
     ({"preset": "bhabba"}, "Input should be"), ({"preset": "bhabha", "diagram": "x"}, "diagram 'x' is not one of s, t"),
     ({"diagrams": [{"lines": ["H in -> v1", "gamma v1 -> out", "gamma v1 -> out"]}]}, "no tree-level H γ γ vertex"),
     ({"diagrams": [{"lines": ["e- in -> v1", "e- v1 -> out", "gamma v1 -> out"]}, {"lines": ["e- in -> v1", "e- v1 -> out", "gamma v1 -> out"]}],
       "diagram": "d3"}, "not one of d1, d2"),
     ({"diagrams": [{"lines": ["e- in v1", "e- v1 -> out", "gamma v1 -> out"]}]}, "write a line as"),
     ({"diagrams": [{"lines": ["x-y: e- in -> v1", "e- v1 -> out", "gamma v1 -> out"]}]}, "write a line as"),
     ({"preset": "bhabha", "time": "down"}, "Input should be")],
)
def test_param_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        cls().validate_params(params)


def test_actions_are_checked(make_project) -> None:
    def problems(scene: dict[str, Any]) -> list[str]:
        return [m.message for m in project_problems(Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION))))]

    bhabha = {"id": "f", "type": "feynman", "params": {"preset": "bhabha"}}
    ok = [{"text": "a vertex", "actions": [{"vertex_rule": "vertex:v1", "show": ["rule", "checks"]}, {"travel": "line:e_minus"}]},
          {"text": "swap", "actions": [{"action": "swap_channel", "to": "t"}, {"travel": "diagram"}, {"highlight": "line:photon"}]}]
    assert problems({**bhabha, "beats": ok}) == []
    assert any("vertex_rule names one vertex" in m for m in problems({**bhabha, "beats": [{"text": "x", "actions": [{"vertex_rule": "line:photon"}]}]}))
    assert any("vertex_rule names one vertex" in m for m in problems({**bhabha, "beats": [{"text": "x", "actions": [{"vertex_rule": "vertex:*"}]}]}))
    assert any("travel runs along lines" in m for m in problems({**bhabha, "beats": [{"text": "x", "actions": [{"travel": "vertex:v1"}]}]}))
    assert any("no diagram 'u'" in m for m in problems({**bhabha, "beats": [{"text": "x", "actions": [{"action": "swap_channel", "to": "u"}]}]}))
    muon = {"id": "m", "type": "feynman", "params": {"preset": "muon_decay"}, "beats": [{"text": "x", "actions": [{"action": "swap_channel"}]}]}
    assert any("two or more diagrams" in m for m in problems(muon))
    other = {"id": "b", "type": "bullets", "params": {"items": ["a"]}, "beats": [{"text": "go", "actions": [{"action": "swap_channel"}]}]}
    assert any("swap_channel is an action of feynman scenes" in m for m in problems(other))


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
def test_diagram_renders_with_its_actions(size: tuple[int, int], make_project, media: Path) -> None:
    beats = [{"text": "an electron and a positron annihilate", "actions": [{"vertex_rule": "vertex:v1", "show": ["rule", "coupling", "checks"], "at": 0.6}]},
             {"text": "or they exchange a photon", "actions": [{"action": "swap_channel", "to": "t", "at": 0.1}]},
             {"text": "follow them through", "actions": [{"travel": "diagram", "at": 0.1}]}]
    scene = {"id": "bh", "type": "feynman", "params": {"title": "Bhabha scattering", "preset": "bhabha"}, "beats": beats}
    project = Project.load(make_project(minimal_config(scenes=[scene], narration=NARRATION)))
    s = render(project, "bh", media, size)
    registered = sorted({n for t in s.targets for n in t.names})
    assert registered == sorted(type(s).target_names(s.params))
    assert s.current.name == "t"
    assert all(s.is_shown(f"line:{ln.id}") for ln in s.current.lines) and s.is_shown("vertex:v2")
    # the travel dots are gone and the vertex rule was undone at the next beat
    from manim import Dot

    assert not [m for m in s.mobjects if isinstance(m, Dot) and m.radius > 0.1]
    # labels inside the frame, none overlapping another
    labels = [parts[k] for parts in s._parts.values() for k in ("label", "label_out", "name") if k in parts]
    boxes = [_box(m) for m in labels]
    assert all(abs(x) <= s.frame_width / 2 for b in boxes for x in (b[0], b[2])) and all(abs(y) <= s.frame_height / 2 for b in boxes for y in (b[1], b[3]))
    assert all(_overlap(a, b) == 0 for i, a in enumerate(boxes) for b in boxes[i + 1:])


@pytest.mark.render
def test_loops_spectators_and_time_up(make_project, media: Path) -> None:
    scenes = [{"id": "gg", "type": "feynman", "params": {"preset": "gg_to_h", "time": "up"}, "beats": [{"text": "two gluons make a higgs boson"}]},
              {"id": "beta", "type": "feynman", "params": {"preset": "beta_decay", "spectators": True, "reveal": "all"}, "beats": [{"text": "a down quark decays"}]}]
    project = Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))
    gg = render(project, "gg", media, (320, 180))
    h_line = gg._parts["line:H"]["path"]
    g_line = gg._parts["line:g1"]["path"]
    assert h_line.get_center()[1] > g_line.get_center()[1]       # time runs up: the Higgs boson leaves at the top
    beta = render(project, "beta", media, (320, 180))
    assert {"hadron:n", "hadron:p"} <= set(beta._parts) and beta.is_shown("hadron:p")
    n = beta._parts["hadron:n"]
    assert n["name"].get_right()[0] < n["bracket"].get_left()[0] < beta._parts["line:d_in"]["label"].get_left()[0]
