"""Step 227: the science example `examples/radioactive-decay` through `vidgen validate` (16:9 and
its 9:16 variant) and the calc_* / plot_* lint, with the numbers it narrates computed by the
scenes and its data files written by its seeded script."""

from __future__ import annotations

import math
import runpy
import shutil
from pathlib import Path

import pytest

from vidgen.cli import main, validate_all
from vidgen.project import Project

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "radioactive-decay"


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_plots_and_calculations(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "decay", ignore=shutil.ignore_patterns("build", "output", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    types = [s.type for s in project.config.scenes]
    assert types.count("plot") == 2 and types.count("calculation") == 2
    assert set(project.config.terms) == {"decay constant", "half-life"}
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("fit:", "zoom:", "substitute:", "compute:", "live: true", "y_err: sqrt", "error: poisson", "residuals: normalized",
                 "scale: log", 'at: "@'):
        assert used in text, used


def test_the_lint_is_clean_and_the_numbers_are_the_scenes() -> None:
    from vidgen import extensions, registry
    from vidgen.lint.calc_rule import calc_issues
    from vidgen.lint.plot_rule import plot_issues

    project = Project.load(EXAMPLE)
    rules = project.config.lint.rules
    for scene in project.config.scenes:
        assert calc_issues(project, scene.id, rules) == [], scene.id
        assert plot_issues(project, scene.id, rules) == [], scene.id
    extensions.load_builtins()
    params = {s.id: s for s in project.config.scenes}
    calc = registry.get("calculation").cls
    half = {r.name: r for r in calc.validate_params(params["half"].params).worked().results}
    assert half["t_half"].value.value_text() == "2.51 min" and half["s_t"].value.value_text() == "0.040 min"
    assert half["z"].value.value_text() == "1"
    carbon = {r.name: r for r in calc.validate_params(params["carbon"].params).worked().results}
    assert carbon["lambda_C"].value.value_text() == "1.21 × 10⁻⁴ yr⁻¹" and carbon["t"].value.value_text() == "9.6 × 10³ yr"


def test_the_fit_gives_the_narrated_decay_constant() -> None:
    from vidgen import plotcore

    table = plotcore.read_table((EXAMPLE / "assets" / "counts.csv").read_text(encoding="utf-8"), "counts.csv")
    x, y = table.column("time").values, table.column("counts").values
    model = plotcore.make_model("custom", expr="A*exp(-lambda*x)", params=["A", "lambda"], guesses={"A": 700.0, "lambda": 0.3})
    fit = plotcore.fit_curve(x, y, model, y_err=[math.sqrt(v) for v in y])
    lam, err = fit.value("lambda")
    assert round(lam, 3) == 0.276 and round(err, 3) == 0.004 and 0.5 < fit.reduced_chi2 < 1.5
    assert abs(lam - math.log(2) / 2.552) < 1.5 * err          # the true value within the uncertainty


def test_the_data_script_is_seeded(tmp_path: Path) -> None:
    script = shutil.copy(EXAMPLE / "make_data.py", tmp_path / "make_data.py")
    runpy.run_path(str(script), run_name="__main__")
    for name in ("counts.csv", "nuclei.csv"):
        assert (tmp_path / "assets" / name).read_text(encoding="utf-8") == (EXAMPLE / "assets" / name).read_text(encoding="utf-8"), name


def test_the_readme_and_the_index_point_to_it() -> None:
    assert "examples/radioactive-decay/README.md" in (REPO / "README.md").read_text(encoding="utf-8")
    assert "make_data.py" in (EXAMPLE / "README.md").read_text(encoding="utf-8")
