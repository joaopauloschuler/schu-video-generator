"""Step 220: the genetics example `examples/cystic-fibrosis` through `vidgen validate` (16:9 and
its 9:16 variant) and the genetics lint, with the numbers it narrates computed by the scenes."""

from __future__ import annotations

import shutil
from fractions import Fraction
from pathlib import Path

import pytest

from vidgen.cli import main, validate_all
from vidgen.project import Project

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "cystic-fibrosis"


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_phase_v(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "cf", ignore=shutil.ignore_patterns("build", "output", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    config = project.config
    types = [s.type for s in config.scenes]
    assert {"pedigree", "cross", "karyotype", "mutation", "dna_lab", "population"} <= set(types) and types.count("pedigree") == 2
    assert set(config.terms) == {"carrier", "autosomal recessive", "F508del"}
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("analyse:", "deduce:", "risk:", "form_gametes:", "fill:", "count:", "mutate:", "run:", "reveal:", 'at: "@', "cite:"):
        assert used in text, used
    references = [r for s in config.scenes for r in s.references]
    assert {r.pmid for r in references} == {"2475911", "2570460"}


def test_the_genetics_lint_is_clean_and_the_numbers_are_the_scenes() -> None:
    from vidgen.genetics.dna_lab import plan_lab
    from vidgen.genetics.mutation import plan_mutation
    from vidgen.genetics.pedigree_plan import plan_pedigree
    from vidgen.genetics.population import plan_population
    from vidgen.lint.genetics_rule import genetics_issues

    project = Project.load(EXAMPLE)
    for scene in project.config.scenes:
        assert genetics_issues(project, scene.id, project.config.lint.rules) == [], scene.id
    params = {s.id: dict(s.params) for s in project.config.scenes}
    risk = plan_pedigree(params["risk"])
    assert risk.mode == "AR" and risk.inference.risk.affected == Fraction(1, 150)
    assert [f[2] for f in risk.inference.risk.factors] == [Fraction(2, 3), Fraction(1, 25), Fraction(1, 4)]
    variant = plan_mutation(params["variant"]).variants[0]
    assert variant.p_text == "p.(Phe508del)" and variant.consequence.kind == "inframe_del"
    ngs = plan_lab(params["test"]).ngs
    assert ngs.kind == "deletion" and ngs.ref == "CTT" and ngs.call == "heterozygous"
    hw = plan_population({k: v for k, v in params["population"].items() if k != "title"}).hw
    assert hw.q == Fraction(1, 50) and 2 * hw.p * hw.q == Fraction(49, 1250)


def test_the_readme_and_the_index_point_to_it() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "examples/cystic-fibrosis/README.md" in readme
    assert "c.1521_1523del" in (EXAMPLE / "README.md").read_text(encoding="utf-8")
