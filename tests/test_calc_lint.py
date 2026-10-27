"""Step 226 (DESIGN.md §97.11): the calculation and plot lint rules.

Numbers and units as narration writes them (words and digits), how they compare with computed
values, the text checks on wrong statements (each must be found) and right ones (none may be),
and the scene rules on small projects (no render)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from vidgen.config import LINT_RULES, LintRules
from vidgen.lint import RULES
from vidgen.lint.calc_rule import CALC_RULES, calc_issues
from vidgen.lint.plot_rule import PLOT_RULES, plot_issues
from vidgen.project import Project
from vidgen.quantities import accuracy as qa
from vidgen.quantities.units import parse_unit

REPO = Path(__file__).resolve().parent.parent


def _said(text: str) -> list[qa.SaidValue]:
    return [v for s in qa.statements(text) for v in qa.said_values(s)]


# ----- numbers and units --------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "value", "unit", "resolution"), [
    ("about thirty kilometres per second", 30, "km/s", 3),         # trailing zeros: at most a tenth
    ("one in two hundred", 0.005, None, 0.0),
    ("eleven point two kilometres per second", 11.2, "km/s", 0.05),
    ("eight point oh four days", 8.04, "d", 0.005),
    ("three point seven times ten to the minus nineteen joules", 3.7e-19, "J", 5e-21),
    ("three hundred sixty-five days", 365, "d", 0.5),
    ("a hundred and thirty-three", 133, None, 0.5),
    ("29.8 km/s", 29.8, "km/s", 0.05),
    ("9.81 m/s²", 9.81, "m/s²", 0.005),
    ("3.73 × 10⁻¹⁹ J", 3.73e-19, "J", 5e-22),
    ("6.674e-11", 6.674e-11, None, 5e-15),
    ("1.5 million years", 1.5e6, "yr", 5e4),
    ("0.173 per hour", 0.173, "h⁻¹", 5e-4),
    ("metres per second squared", None, None, None),
    ("25 %", 25, "%", 0.5),
    ("37 °C", 37, "°C", 0.5),
    ("twenty-five degrees Celsius", 25, "°C", 0.5),
    ("minus seventy millivolts", -70, "mV", 5),
    ("five micrograms per litre", 5, "µg/L", 0.5),
    ("ninety kilometres an hour", 90, "km/h", 5),
])
def test_said_values(text: str, value: float | None, unit: str | None, resolution: float | None) -> None:
    found = _said(text)
    if value is None:
        assert found == []
        return
    [v] = found
    assert math.isclose(v.value, value, rel_tol=1e-12) and math.isclose(v.resolution, resolution, rel_tol=1e-9), v
    assert (v.unit.text if v.unit is not None else None) == unit


def test_fractions_shares_and_how_numbers_are_said() -> None:
    values = {v.text: v for v in _said("Two thirds times one twenty-fifth times one quarter is one in one hundred fifty; "
                                       "forty-nine fiftieths; three halves; one and a half hours; 1/25 of them.")}
    assert math.isclose(values["Two thirds"].value, 2 / 3) and math.isclose(values["one twenty-fifth"].value, 1 / 25)
    assert values["one in one hundred fifty"].per == 150 and math.isclose(values["forty-nine fiftieths"].value, 0.98)
    assert values["three halves"].value == 1.5 and values["one and a half hours"].unit.text == "h" and values["1/25"].value == 0.04
    [share] = _said("about one person in twenty-six")
    assert share.per == 26 and share.approx
    assert [v.in_range for v in _said("Light spans 400 to 700 nanometres.")] == [True, True]
    assert [v.in_range for v in _said("It takes between 3 and 5 days.")] == [True, True]
    assert [v.bound for v in qa.said_values("more than 30 km/s")] == [True]
    assert qa.statements("It is faster than 30 km/s.") == []          # a comparison is left alone
    assert _said("It is 5 am.")[0].unit is None and _said("8 seedlings")[0].unit is None
    assert qa.words_value("two and three") is None and qa.words_value("one hundred fifty") == 150
    [v] = _said("In kilograms, the mass is two point two times ten to the minus twenty-five.")
    assert v.unit.text == "kg" and math.isclose(v.value, 2.2e-25)
    sig = {v.text: (v.sig, v.sig_sure) for v in _said("29.80 km/s, 1500 m, thirty kilometres, eleven point two kilometres")}
    assert sig == {"29.80 km/s": (4, True), "1500 m": (2, False), "thirty kilometres": (None, False), "eleven point two kilometres": (3, True)}


def test_agreement_rounding_and_mixups() -> None:
    v = 29784.7                                       # m/s
    [thirty] = _said("thirty kilometres per second")
    assert qa.agrees(thirty, v) and not qa.agrees(_said("three kilometres per second")[0], v)
    assert qa.agrees(_said("29.8 km/s")[0], v) and not qa.agrees(_said("29.6 km/s")[0], v)
    assert qa.agrees(_said("about 30 km/s")[0], v) and qa.agrees(_said("about 29 km/s")[0], v)      # 5 %
    assert not qa.agrees(_said("about 25 km/s")[0], v)
    assert qa.mixup_power(_said("30 metres per second")[0], v) == -3
    assert qa.mixup_power(_said("5 milligrams")[0], 5e-9) == 3      # mg for µg
    assert qa.mixup_power(_said("35 km/s")[0], v) == 0
    share = _said("one in a hundred and fifty")[0]
    assert qa.agrees(share, 1 / 150) and not qa.agrees(_said("one in two hundred")[0], 1 / 150)
    assert qa.agrees(_said("about one in twenty-six")[0], 2 * 49 / 2500)
    assert qa.in_unit_text(v, parse_unit("km/s"), 3) == "29.8 km/s"


def test_dimension_words() -> None:
    wrong = ["The probe reaches a speed of 30 kilometres.", "Its half-life is 8 metres.", "An energy of 5 kilograms.",
             "The wavelength is 532 nanoseconds."]
    for text in wrong:
        assert len(qa.dimension_claims(text)) == 1, text
    right = ["A speed of 30 kilometres per second.", "The mass of the Higgs boson is 125 GeV.", "A half-life of eight days.",
             "A temperature of 25 degrees.", "The allele frequency is 2 percent.", "It travels at light speed: about seventy milliseconds.",
             "The speed is not 30 kilometres.", "A distance of 1 AU."]
    assert [t for t in right if qa.dimension_claims(t)] == []


def test_fit_quantities_and_claims() -> None:
    decay = qa.fit_quantities("exponential fit", "exponential", ("A", "k"), (1000, -0.0862), (10, 0.001), ("Bq", "d⁻¹"), "d")
    half = next(q for q in decay if q.key == "half_life")
    assert math.isclose(half.value, math.log(2) / 0.0862) and half.unit == "d" and math.isclose(half.error, math.log(2) * 0.001 / 0.0862**2)
    wrong = ["The fit gives a half-life of twelve days.", "The half-life is 150 hours.", "A time constant of 20 days.",
             "The decay constant is 0.2 per day."]
    for text in wrong:
        assert len(qa.fit_claims(text, decay)) == 1, text
    right = ["The fit gives a half-life of eight days.", "A half-life of about 8 days.", "The half-life is 193 hours.",
             "The half-life is 8.0 days.", "Half the activity is gone after eight days.", "The half-life is not twelve days.",
             "Iodine-131 has a half-life of 8.02 days."]
    assert [t for t in right if qa.fit_claims(t, decay)] == []
    power = qa.fit_quantities("power law", "power", ("A", "k"), (1.0, 1.4996), (0.001, 0.0005), ("yr", ""))
    assert qa.fit_claims("A power law with exponent five halves.", power) and not qa.fit_claims("A power law with exponent three halves.", power)
    peak = qa.fit_quantities("peak", "gaussian", ("A", "mu", "sigma"), (100, 125.1, 1.6), (5, 0.2, 0.2), ("", "GeV", "GeV"))
    assert qa.fit_claims("The peak at 135 GeV.", peak) and not qa.fit_claims("A peak at 125 GeV, with a width of about 4 GeV.", peak)
    poisson = qa.fit_quantities("Poisson", "poisson", ("mu",), (3.02,), (0.1,), ("",))
    assert not qa.fit_claims("A Poisson distribution with mean about three.", poisson)
    assert qa.fit_claims("A Poisson distribution with mean about five.", poisson)


def test_error_meanings() -> None:
    assert qa.error_meaning_claims("The error bars show one standard deviation.", {"sem"})
    assert qa.error_meaning_claims("Bars: the 95 % confidence interval.", {"sd"})
    assert not qa.error_meaning_claims("The error bars are standard errors of the mean.", {"sem"})
    assert not qa.error_meaning_claims("The standard deviation of the peak is 2 GeV.", {"sem"})      # not about the bars
    assert not qa.error_meaning_claims("Over the range of doses the error bars shrink.", {"sem"})
    assert not qa.error_meaning_claims("The error bars show one standard deviation.", {"other"})


# ----- the rules on projects ---------------------------------------------------------------------------

ORBIT = {"title": "How fast does the Earth orbit the Sun?",
         "symbols": [{"name": "G", "constant": "G"}, {"name": "M_sun", "constant": "M_sun"}, {"name": "r", "constant": "AU", "meaning": "Earth–Sun distance"}],
         "calculations": [{"name": "v", "expr": "sqrt(G*M_sun/r)", "sig": 3, "convert": "km/s", "meaning": "orbital speed"}]}
RISK = {"symbols": [{"name": "P_m", "value": "2/3"}, {"name": "P_f", "value": "1/25"}, {"name": "P_c", "value": "1/4"}],
        "calculations": [{"name": "P", "expr": "P_m*P_f*P_c", "meaning": "risk for the child"}]}


def _project(make_project, scenes: list[dict[str, Any]], **extra: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, **extra)))


def _beats(*texts: str) -> list[dict[str, str]]:
    return [{"text": t} for t in texts]


def _calc(project: Project, scene_id: str) -> list[tuple[str, str | None, str]]:
    import vidgen.scenes  # noqa: F401 - registers the built-in scene types

    return [(f.rule, f.beat, f.message) for f in calc_issues(project, scene_id, project.config.lint.rules)]


def _plot(project: Project, scene_id: str) -> list[tuple[str, str]]:
    import vidgen.scenes  # noqa: F401 - registers the built-in scene types

    return [(f.rule, f.message) for f in plot_issues(project, scene_id, project.config.lint.rules)]


def test_rules_are_registered_in_config_order() -> None:
    names = CALC_RULES + PLOT_RULES
    assert list(LINT_RULES[-len(names):]) == list(names)
    defaults = {name: RULES[name].default for name in names}
    assert defaults.pop("calc_sigfigs") == "info" and defaults.pop("plot_truncated") == "info"
    assert set(defaults.values()) == {"warning"} and all(RULES[n].scope == "scene" for n in names)
    assert LintRules().plot_conserved.tolerance == 0.01 and LintRules().plot_fit_claims.sigmas == 2.0


def test_calculation_numbers(make_project) -> None:
    right = ["The Earth moves at about thirty kilometres per second.", "That is 29.8 km/s.", "Roughly 30,000 metres per second.",
             "One astronomical unit is the distance.", "Light spans 400 to 700 nanometres."]
    wrong = {"The Earth moves at about thirty-five kilometres per second.": "calc_numbers",
             "That is 30 metres per second.": "calc_units",
             "It moves at a speed of 30 kilometres.": "calc_units",
             "Precisely, 29.7847 kilometres per second.": "calc_sigfigs"}
    p = _project(make_project, [{"id": "o", "type": "calculation", "params": ORBIT, "beats": _beats(*right, *wrong)}])
    found = _calc(p, "o")
    assert sorted((f[0], f[1]) for f in found) == sorted((rule, f"o_b{k}") for k, rule in enumerate(wrong.values(), start=len(right) + 1)), found
    message = next(f[2] for f in found if f[0] == "calc_numbers")
    assert "orbital speed (v) is 29.8 km/s" in message
    assert "1,000 times smaller" in next(f[2] for f in found if f[2].startswith('"That is 30'))


def test_pure_numbers_need_their_name(make_project) -> None:
    p = _project(make_project, [{"id": "r", "type": "calculation", "params": RISK, "beats": _beats(
        "Multiply the three probabilities: two thirds times one twenty-fifth times one quarter.",
        "The risk for the child is one in a hundred and fifty.",
        "The risk for the child is one in two hundred.",
        "Two thirds times one twenty-fifth times one quarter is one in two hundred.")}])
    found = _calc(p, "r")
    assert [(f[0], f[1]) for f in found] == [("calc_numbers", "r_b3")], found
    assert "risk for the child (P) is 1/150 (1 in 150)" in found[0][2]


def test_other_scenes_and_screen_text(make_project) -> None:
    scenes = [{"id": "o", "type": "calculation", "params": ORBIT, "beats": _beats("Gravity sets the speed.")},
              {"id": "card", "type": "text_card", "params": {"text": "Orbital speed: 35 km/s"}, "beats": _beats(
                  "So the orbital speed is about thirty kilometres per second.", "The orbital speed is 45 kilometres per second.",
                  "A train runs at 50 kilometres per hour.")}]
    p = _project(make_project, scenes)
    found = _calc(p, "card")
    assert sorted((f[0], f[1]) for f in found) == [("calc_numbers", "card_b1"), ("calc_numbers", "card_b2")], found
    assert any(f[2].startswith("text 'Orbital speed: 35 km/s'") and "in scene 'o'" in f[2] for f in found)


def test_sig_warnings_and_rules_off(make_project) -> None:
    params = {"symbols": [{"name": "k", "value": "0.173 h^-1", "meaning": "rate constant"}],
              "calculations": [{"name": "t_half", "expr": "ln(2)/k", "unit": "h", "sig": 5, "meaning": "half-life"}]}
    scenes = [{"id": "h", "type": "calculation", "params": params, "beats": _beats("The half-life is four hours.", "The half-life is six hours.")}]
    p = _project(make_project, scenes)
    assert sorted(f[0] for f in _calc(p, "h")) == ["calc_numbers", "calc_sigfigs"]
    assert "sig 5 claims more than the inputs give (3" in next(f[2] for f in _calc(p, "h") if f[0] == "calc_sigfigs")
    p = _project(make_project, scenes, lint={"rules": {"calc_sigfigs": {"severity": "off"}, "calc_numbers": {"severity": "off"}}})
    assert _calc(p, "h") == []


def test_plot_rules(make_project) -> None:
    scenes = [
        {"id": "a", "type": "plot", "params": {
            "x": {"label": "time"}, "y": {"scale": "log", "label": "activity", "unit": "Bq"},
            "series": [{"name": "measured", "style": "points", "x": [0, 4, 8, 12, 16, 20], "y": [1000, 700, 500, 360, 250, 180],
                        "y_err": [60, 50, 40, 400, 30, 25]}],
            "fits": [{"series": "measured", "model": "exponential", "name": "exponential fit"}],
            "annotations": [{"type": "hline", "y": 500, "text": "half"}]},
         "beats": _beats("The fit gives a half-life of twelve days.", "Half the start.")},
        {"id": "g", "type": "plot", "params": {
            "legend": False, "x": {"label": "dose", "unit": "mg"}, "y": {"label": "response", "unit": "mmHg"},
            "series": [{"name": "treated", "x": [0, 5, 10], "y": [0, 4, 7], "y_err": 1, "error": "sem"},
                       {"name": "series 2", "x": [0, 5, 10], "y": [0, 1, 2], "y_err": 1, "error": "sem"}]},
         "beats": _beats("The error bars show one standard deviation.")},
        {"id": "s", "type": "plot", "params": {
            "models": {"osc": {"kind": "ode", "equations": {"x": "v", "v": "-x"}, "initial": {"x": 1, "v": 0}, "t": [0, 200], "step": 0.5,
                               "quantities": {"E": "0.5*v^2 + 0.5*x^2"}, "conserved": ["E"], "units": {"t": "s", "E": "J/kg"}}},
            "series": [{"name": "energy", "x": "t", "y": "E"}]}, "beats": _beats("The energy should stay constant.")},
        {"id": "b", "type": "bar_chart", "params": {"labels": ["A", "B"], "values": [62, 70], "baseline": 60}, "beats": _beats("C wins.")},
    ]
    p = _project(make_project, scenes)
    assert sorted(f[0] for f in _plot(p, "a")) == ["plot_errors", "plot_fit_claims", "plot_log", "plot_units"], _plot(p, "a")
    assert sorted(f[0] for f in _plot(p, "g")) == ["plot_errors", "plot_series", "plot_series"]
    [(rule, message)] = _plot(p, "s")
    assert rule == "plot_conserved" and "use method: leapfrog" in message and "step 0.5" in message
    assert [f[0] for f in _plot(p, "b")] == ["plot_truncated"]
    assert [f.severity for f in plot_issues(p, "b", LintRules())] == [None]     # the rule's default: info


def test_plot_log_fits_bands_and_csv(make_project) -> None:
    scenes = [
        {"id": "f", "type": "plot", "params": {
            "y": {"scale": "log", "label": "signal", "unit": "V"}, "x": {"label": "depth", "unit": "m"},
            "series": [{"name": "data", "style": "points", "x": [1, 2, 3, 4, 5, 6], "y": [5, 4.1, 2.9, 2.2, 1.1, 0.3]}],
            "fits": [{"series": "data", "model": "linear", "name": "line", "band": "prediction"}]},
         "beats": _beats("A straight line.")},
        {"id": "c", "type": "plot", "params": {"data": "assets/d.csv", "y": {"scale": "log"},
                                              "series": [{"name": "data", "x": "time", "y": "level"}]}, "beats": _beats("Data.")},
    ]
    root = make_project(minimal_config(scenes=scenes))
    (root / "assets").mkdir()
    (root / "assets" / "d.csv").write_text("time (s), level (V)\n0, 1\n1, 0\n2, 3\n", encoding="utf-8")
    p = Project.load(root)
    found = _plot(p, "f")
    assert [f[0] for f in found] == ["plot_log"] and "fit 'line'" in found[0][1]
    [(rule, message)] = _plot(p, "c")
    assert rule == "plot_log" and "positive values" in message


def test_plot_rules_quiet_on_good_plots(make_project) -> None:
    scenes = [
        {"id": "k", "type": "plot", "params": {
            "x": {"label": "semi-major axis", "unit": "AU", "scale": "log"}, "y": {"label": "period", "unit": "yr", "scale": "log"},
            "series": [{"name": "planets", "style": "points", "x": [0.387, 0.723, 1.0, 1.524, 5.203, 9.537, 19.19, 30.07],
                        "y": [0.241, 0.615, 1.0, 1.881, 11.86, 29.46, 84.01, 164.8]}],
            "fits": [{"series": "planets", "model": "power", "name": "power law"}]},
         "beats": _beats("A power law with exponent three halves.")},
        {"id": "t", "type": "plot", "params": {
            "legend": False, "x": {"label": "time", "unit": "s"}, "y": {"label": "position", "unit": "m"},
            "series": [{"name": "fast", "x": [0, 1, 2], "y": [0, 2, 4]}, {"name": "slow", "x": [0, 1, 2], "y": [0, 1, 2]}],
            "annotations": [{"type": "label", "series": "fast", "index": 3, "text": "fast"}, {"type": "label", "series": "slow", "index": 3, "text": "slow"}]},
         "beats": _beats("Two runners.")},
        {"id": "n", "type": "plot", "params": {"x": {"label": "relative time"}, "y": {"label": "count"},
                                              "series": [{"name": "m", "x": [0, 1], "y": [1, 2], "y_err": 0.1, "error": "sd"}]},
         "beats": _beats("The error bars are one standard deviation.")},
    ]
    p = _project(make_project, scenes)
    for sid in ("k", "t", "n"):
        assert _plot(p, sid) == [], sid


def test_gallery_is_clean() -> None:
    import vidgen.scenes  # noqa: F401

    project = Project.load(REPO / "examples" / "gallery")
    for spec in project.config.scenes:
        assert calc_issues(project, spec.id, LintRules()) == [], spec.id
        assert plot_issues(project, spec.id, LintRules()) == [], spec.id


def test_narration_rules_know_plots_and_calculations(make_project) -> None:
    from vidgen import registry
    from vidgen.lint.narration_rule import SHOWING_ACTIONS, target_texts

    import vidgen.scenes  # noqa: F401

    actions = {"fit", "annotate", "grow", "substitute", "compute", "convert"}
    assert actions <= SHOWING_ACTIONS and actions <= {a.name for a in registry.all_actions()}
    p = _project(make_project, [
        {"id": "p", "type": "plot", "params": {
            "series": [{"name": "measured", "x": [1, 2, 3], "y": [2, 4, 6]}],
            "fits": [{"series": "measured", "model": "linear", "name": "straight line"}],
            "annotations": [{"type": "note", "text": "a note", "id": "n1"}]}, "beats": _beats("x")},
        {"id": "c", "type": "calculation", "params": {**ORBIT, "title": "Speed"}, "beats": _beats("x")}])
    plot = target_texts(p, "p")
    assert (plot("series1"), plot("series:measured"), plot("fit1"), plot("annotation:n1"), plot("axes")) == (
        "measured", "measured", "straight line", "a note", None)
    calc = target_texts(p, "c")
    assert calc("row:r") == "Earth–Sun distance · IAU 2012 (exact)" or calc("row:r").startswith("Earth–Sun distance")
    assert calc("row:v") == "orbital speed" and calc("title") == "Speed" and calc("result1") is None
