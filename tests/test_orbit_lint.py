"""Step 234 (DESIGN.md §98.8): the orbital accuracy lint.

Numbers, dates and scale claims as narration writes them, the values an orbit scene computes,
each rule finding its planted mistake and leaving the right statements alone, the drift and crash
checks, the narration–picture rules' orbit targets; no render."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from conftest import minimal_config
from vidgen.config import LINT_RULES, LintRules
from vidgen.lint import RULES
from vidgen.lint.orbit_rule import ORBIT_RULES, facts, orbit_issues
from vidgen.orbits import accuracy as oa
from vidgen.project import Project
from vidgen.quantities import accuracy as qa

REPO = Path(__file__).resolve().parent.parent
SUN = {"central": "sun"}
INNER = {**SUN, "bodies": [{"preset": "mercury"}, {"preset": "venus"}, {"preset": "earth"}, {"preset": "mars"}], "span": "2 yr"}
GEO = {"central": "earth", "bodies": [{"name": "Satellite", "altitude": "300 km", "trail": False}], "transfer": {"ship": "Satellite", "to": "42164 km"}}
MARS = {**SUN, "bodies": [{"preset": "earth", "e": 0, "i": 0, "raan": 0, "argp": 0}, {"preset": "mars", "e": 0, "i": 0, "raan": 0, "argp": 0, "nu": 75},
                          {"name": "Ship", "alongside": "Earth"}], "transfer": {"ship": "Ship", "to": "Mars"}}


def _project(make_project, scenes: list[dict[str, Any]], **extra: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, **extra)))


def _scene(sid: str, params: dict[str, Any], *texts: str, kind: str = "orbit") -> dict[str, Any]:
    return {"id": sid, "type": kind, "params": params, "beats": [{"text": t} for t in texts]}


def _found(project: Project, scene_id: str) -> list[tuple[str, str | None, str]]:
    import vidgen.scenes  # noqa: F401 - registers the built-in scene types

    return [(f.rule, f.beat, f.message) for f in orbit_issues(project, scene_id, project.config.lint.rules)]


def _rules_at(project: Project, scene_id: str) -> list[tuple[str, str | None]]:
    return sorted((r, b) for r, b, _ in _found(project, scene_id))


# ----- registration and reading -----------------------------------------------------------------------


def test_rules_are_registered_last_in_config_order() -> None:
    k = LINT_RULES.index(ORBIT_RULES[0])   # Step 242's particle rules come after them
    assert list(LINT_RULES[k:k + len(ORBIT_RULES)]) == list(ORBIT_RULES) and LINT_RULES[k + len(ORBIT_RULES)] == "particle_mass"
    assert all(RULES[n].scope == "scene" and RULES[n].default == "warning" for n in ORBIT_RULES)
    rules = LintRules()
    assert rules.orbit_conserved.tolerance == 0.01 and rules.orbit_period.tolerance == 0.05 and rules.orbit_date.days == 3.0


def test_the_knowledge_does_not_import_manim() -> None:
    import subprocess
    import sys

    code = "import sys, vidgen.orbits.accuracy; print('manim' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_numbers_months_weeks_and_groups() -> None:
    [months] = oa.said_quantities("Launch windows come every 26 months.")
    assert months.unit.text == "d" and math.isclose(months.si, 26 * 365.25 / 12 * 86400)
    [weeks] = oa.said_quantities("It takes three weeks.")
    assert math.isclose(weeks.si, 21 * 86400)
    # Step 236: digit groups written with spaces (plain, thin, no-break) are one number
    for space in (" ", " ", " ", " "):
        [moon] = oa.said_quantities(f"The Moon is 384{space}400 km away.")
        assert moon.si == 384_400e3 and moon.text == f"384{space}400 km"
    [far] = oa.said_quantities("Mars is 227 900 000 km from the Sun.")
    assert far.si == 227.9e9
    assert [v.si for v in oa.said_quantities("a 3 400 km orbit")] == [3.4e6]
    assert oa.said_quantities("In 2026 300 km up is low.") == []   # a year then a number: not one number, and the second is left out
    [half] = qa.said_values("L1 lies about one and a half million kilometres away.")
    assert half.value == 1.5e6 and half.unit.text == "km" and half.approx
    assert [oa.quantity_of(v) for v in oa.said_quantities("44 degrees, 3.9 km/s, 259 days, 1.5 AU")] == ["angle", "speed", "time", "length"]


def test_topics_and_clauses() -> None:
    assert oa.topic_groups("Neptune barely moves in ten years.", "time") == ([], False)
    assert oa.topic_groups("Mars takes two years.", "time")[0] == [("period",)]
    assert oa.topic_groups("The trip takes 259 days.", "time")[0][0] == ("transfer_time",)
    assert oa.topic_groups("At aphelion it moves at 39 km/s.", "speed") == ([("apo_speed",)], True)
    assert oa.topic_groups("Fastest at perihelion, 59 km/s, slowest at aphelion, 39 km/s.", "speed")[1] is False
    s = "The Earth moves at about 30 km/s, and its escape velocity is 11.2 km/s."
    spans = [(v.start, v.end) for v in qa.said_values(s)]
    assert "escape" not in oa.clause(s, s.index("30"), s.index("30") + 8, spans)
    s2 = "Two hundred and fifty-nine days later, Mars is there."
    assert oa.clause(s2, 0, 30, [(v.start, v.end) for v in qa.said_values(s2)]).startswith("Two hundred and fifty-nine days later")


def test_dates_and_events() -> None:
    dates = oa.said_dates("On the first of June 2020; 13 October 2020; October 13, 2020; 2020-10-13; in October 2020; in 2021; in mid October.")
    assert [(d.precision, d.year, d.month, d.day) for d in dates] == [
        ("day", 2020, 6, 1), ("day", 2020, 10, 13), ("day", 2020, 10, 13), ("day", 2020, 10, 13), ("month", 2020, 10, 0), ("year", 2021, 0, 0),
        ("month_only", 0, 10, 0)]
    right = ["Mars was at opposition on 13 October 2020.", "Mars reached opposition on January 16, 2025.", "Venus was at inferior conjunction on 3 June 2020.",
             "Jupiter was at opposition on 3 November 2023.", "Saturn reached opposition in August 2023.", "Mars was at opposition in 2022."]
    assert [t for t in right if oa.event_claims(t)] == []
    wrong = ["Mars reaches opposition on 2 December 2020.", "Mars was at opposition in 2021.", "Venus was at inferior conjunction on 3 March 2020."]
    for text in wrong:
        [message] = oa.event_claims(text)
        assert "the nearest is on" in message, text
    assert oa.event_claims("Mars was at opposition on 13 October 1700.") == []       # outside Table 1: not read
    assert qa.statements("Mars was not at opposition in 2021.") == []              # a negation is never read


def test_scale_claims() -> None:
    assert oa.scale_claims("Here everything is drawn to scale.", "enlarged")
    assert oa.scale_claims("At true scale the inner planets crowd the Sun.", "enlarged") is None    # distances: true
    assert oa.scale_claims("On a logarithmic scale every planet fits.", "log") is None
    assert oa.scale_claims("This map is to scale.", "log")
    assert oa.scale_claims("The planets' sizes to scale.", "sizes") is None
    assert oa.scale_claims("Sizes and distances to scale.", "sizes")
    assert oa.scale_claims("The tides, to scale.", "schematic")
    assert oa.scale_claims("Everything is to scale.", "true") is None


def test_ratio_claims() -> None:
    radii = {"Earth": 6371e3, "Jupiter": 69911e3, "Sun": 695700e3}
    assert oa.ratio_claims("Jupiter is eleven times as wide as the Earth.", radii) == []
    assert oa.ratio_claims("The Sun is ten times as wide as Jupiter.", radii) == []
    [message] = oa.ratio_claims("The Sun is thirty times as wide as Jupiter.", radii)
    assert "9.95 times" in message


# ----- the rules on projects --------------------------------------------------------------------------------


def test_periods_speeds_and_cross_scene(make_project) -> None:
    p = _project(make_project, [
        _scene("p", INNER, "Mercury races around the Sun in eighty-eight days.", "Mars takes three years to go around the Sun.",
               "Mars takes about two years; the Earth takes 365 days.", "Neptune barely moves in ten years."),
        _scene("s", {**SUN, "bodies": [{"preset": "mercury"}, {"preset": "earth"}], "span": "1 yr"},
               "At perihelion Mercury moves at fifty-nine kilometres per second.", "At aphelion Mercury still moves at fifty-nine kilometres per second.",
               "The Earth moves at about thirty kilometres per second, and its escape velocity is 11.2 km/s.", "Earth's escape velocity is 15 km/s."),
        _scene("c", {"text": "Jupiter takes 20 years to orbit the Sun"}, "And Mars takes about two years.", kind="text_card")])
    assert _rules_at(p, "p") == [("orbit_period", "p_b2")]
    assert "687 d (1.88 yr)" in _found(p, "p")[0][2]
    assert _rules_at(p, "s") == [("orbit_speed", "s_b2"), ("orbit_speed", "s_b4")]
    assert "38.9 km/s" in _found(p, "s")[0][2] and "11.2 km/s" in _found(p, "s")[1][2]
    assert _rules_at(p, "c") == [] and "Jupiter" not in [f.subjects[0] for f in facts(p)["p"]]
    p2 = _project(make_project, [_scene("j", {**SUN, "bodies": [{"preset": "jupiter"}]}, "Jupiter."),
                                 _scene("c", {"text": "Jupiter takes 20 years to orbit the Sun"}, "And so on.", kind="text_card")])
    [(rule, _, message)] = _found(p2, "c")
    assert rule == "orbit_period" and "(scene 'j')" in message and "11.9 yr" in message


def test_transfers_and_dv(make_project) -> None:
    p = _project(make_project, [
        _scene("g", GEO, "The first burn takes 3.2 km/s.", "The second burn is about 1.5 kilometres per second.", "Almost four kilometres per second in all.",
               "Three point nine kilometres per second in total."),
        _scene("m", MARS, "Mars must lead the Earth by forty-four degrees when we leave.", "The trip to Mars takes about 180 days.",
               "Two hundred and fifty-nine days later, Mars is there.", "Launch windows to Mars come every 26 months.",
               "Launch windows to Mars come every 18 months.", "Mars must lead the Earth by 60 degrees when we leave.")])
    found = _found(p, "g")
    assert [(r, b) for r, b, _ in found] == [("orbit_dv", "g_b1")] and "Δv₁ of the Hohmann transfer is 2.43 km/s" in found[0][2]
    assert _rules_at(p, "m") == [("orbit_transfer", "m_b2"), ("orbit_transfer", "m_b5"), ("orbit_transfer", "m_b6")]
    messages = [m for _, _, m in _found(p, "m")]
    assert "259 d" in messages[0] and "780 d" in messages[1] and "44.3°" in messages[2]


def test_distances_lagrange_and_sizes(make_project) -> None:
    p = _project(make_project, [
        _scene("moon", {"central": "earth", "bodies": [{"preset": "moon"}], "orbits": 1}, "The Moon is 384,000 km away.", "The Moon is 38,000 km away."),
        _scene("l", {"system": "sun_earth", "view": "rotating", "lagrange": ["L1", "L2"], "center": "Earth", "extent": "2.2e6 km", "orbits": 0.25},
               "L1 and L2 lie about one and a half million kilometres from the Earth.", "L2 is 15 million km away."),
        _scene("z", {"sizes": True}, "Jupiter is eleven times as wide as the Earth.", "The Sun is thirty times as wide as Jupiter.",
               "Here the sizes and the distances are all to scale.", "The planets' sizes to scale.")])
    assert _rules_at(p, "moon") == [("orbit_distance", "moon_b2")]
    assert _rules_at(p, "l") == [("orbit_distance", "l_b2")] and "L2's distance from the Earth is 1.51 million km" in _found(p, "l")[0][2]
    assert _rules_at(p, "z") == [("orbit_distance", "z_b2"), ("orbit_scale", "z_b3")]


def test_dates_scale_on_scenes(make_project) -> None:
    sky = {"date": "2020-06-01", "bodies": [{"preset": "earth"}, {"preset": "mars"}], "event": {"kind": "opposition", "of": "Mars"}}
    planets = {"date": "2024-01-01", "bodies": [{"preset": p} for p in ("mercury", "venus", "earth", "mars", "jupiter")], "span": "2 yr"}
    p = _project(make_project, [
        _scene("o", sky, "In mid October Mars is at opposition, 62 million km from us.", "Mars reaches opposition on 2 December 2020.",
               "In mid December Mars is at opposition."),
        _scene("w", planets, "At true scale the inner planets crowd the Sun.", "Here everything is drawn to scale."),
        _scene("lg", {**planets, "radial": "log"}, "On a logarithmic scale every planet fits.", "This map of the Solar System is to scale.")])
    assert _rules_at(p, "o") == [("orbit_date", "o_b2"), ("orbit_date", "o_b3")]
    assert "2020-10-13" in _found(p, "o")[1][2]
    assert _rules_at(p, "w") == [("orbit_scale", "w_b2")]
    assert _rules_at(p, "lg") == [("orbit_scale", "lg_b2")]


def test_conserved_and_crash(make_project) -> None:
    coarse = {**SUN, "bodies": [{"name": "Inner", "a": "1 AU", "e": 0.6, "mass": "3e27 kg"}, {"name": "Outer", "a": "1.6 AU", "e": 0.05, "nu": 120,
                                                                                               "mass": "3e27 kg"}], "dynamics": "nbody", "orbits": 3}
    p = _project(make_project, [
        _scene("d", {**coarse, "step": "12 d"}, "Mutual gravity."),
        _scene("fine", coarse, "Mutual gravity."),
        _scene("g", {"central": "earth", "bodies": [{"name": "Sat", "altitude": "80 km"}], "orbits": 1}, "Low."),
        _scene("ok", {"central": "earth", "bodies": [{"preset": "iss"}], "orbits": 1}, "The ISS goes round in about ninety-three minutes."),
        _scene("f", {"central": "earth", "flyby": {"v_inf": "5 km/s", "altitude": "50 km"}}, "A flyby."),
        _scene("hit", {**SUN, "bodies": [{"name": "A", "a": "1 AU", "radius": "3e7 km", "mass": "1e24 kg"},
                                         {"name": "B", "a": "1.2 AU", "radius": "3e7 km", "mass": "1e24 kg"}], "dynamics": "nbody", "orbits": 0.2},
               "Two planets.")])
    [(rule, _, message)] = _found(p, "d")
    assert rule == "orbit_conserved" and "halve the step (now step 12 d)" in message
    assert _found(p, "fine") == [] and _found(p, "ok") == []
    assert [r for r, _, _ in _found(p, "g")] == ["orbit_crash"] and "Kármán line" in _found(p, "g")[0][2]
    assert [r for r, _, _ in _found(p, "f")] == ["orbit_crash"]
    assert [r for r, _, _ in _found(p, "hit")] == ["orbit_crash"] and "collide" in _found(p, "hit")[0][2]
    p = _project(make_project, [_scene("d", {**coarse, "step": "12 d"}, "x")], lint={"rules": {"orbit_conserved": {"tolerance": 0.5}}})
    assert _found(p, "d") == []
    p = _project(make_project, [_scene("g", {"central": "earth", "bodies": [{"name": "Sat", "altitude": "80 km"}], "orbits": 1}, "x")],
                 lint={"rules": {"orbit_crash": {"severity": "off"}}})
    assert _found(p, "g") == []


def test_examples_and_gallery_are_clean() -> None:
    import vidgen.scenes  # noqa: F401

    for path in sorted(REPO.glob("examples/**/video.yaml")):
        project = Project.load(path)
        for spec in project.config.scenes:
            if spec.type in ("orbit", "text_card", "calculation"):
                assert orbit_issues(project, spec.id, LintRules()) == [], (path, spec.id)


def test_narration_rules_know_orbit_targets(make_project) -> None:
    from vidgen import registry
    from vidgen.lint.narration_rule import SHOWING_ACTIONS, target_texts

    import vidgen.scenes  # noqa: F401

    actions = {"sweep", "launch", "burn", "flyby"}
    assert actions <= SHOWING_ACTIONS and actions <= {a.name for a in registry.all_actions()}
    burns = {"central": "earth", "bodies": [{"name": "Sat", "altitude": "400 km", "geometry": ["apsides"],
                                            "burns": [{"at": "20 min", "prograde": "0.6 km/s"}, {"at": "apoapsis", "prograde": "0.5 km/s", "label": "circularise"}]}],
             "span": "6 h"}
    p = _project(make_project, [_scene("b", burns, "x"), _scene("l", {"system": "earth_moon", "lagrange": True, "orbits": 1}, "x")])
    b = target_texts(p, "b")
    assert (b("body:Sat"), b("orbit:Sat"), b("periapsis:Sat"), b("apoapsis:Sat"), b("burn:2")) == ("Sat", "Sat", "perigee", "apogee", "circularise")
    assert b("burn:1").startswith("Δv₁ 0.6") and b("burn:9") is None
    assert target_texts(p, "l")("lagrange:L4") == "L4"
