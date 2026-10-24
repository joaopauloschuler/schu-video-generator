"""Step 210: the cell-biology example `examples/gene-to-secreted-protein` through `vidgen validate`
(16:9 and its 9:16 variant) with the phase's features: a gene followed from the nucleus to the
blood in `cell` and `molecule` scenes, a `pathway`, references and concept colours."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vidgen.cli import main, validate_all
from vidgen.project import Project

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "gene-to-secreted-protein"


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_phase_u(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "gene", ignore=shutil.ignore_patterns("build", "output", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    config = project.config
    types = [s.type for s in config.scenes]
    assert {"cell", "molecule", "pathway"} <= set(types) and types.count("cell") == 3
    assert set(config.terms) == {"messenger RNA", "signal peptide", "glycan"}
    text = (root / "video.yaml").read_text(encoding="utf-8")
    steps = ("transcribe:", "cap:", "splice:", "polyadenylate:", "export:", "translate:", "target_er:", "glycosylate:", "fold:",
             "to_golgi:", "secrete:", "exocytosis:", "zoom_to:", "signal:", 'at: "@', "cite:", "indirect: true")
    for used in steps:
        assert used in text, used
    references = [r for s in config.scenes for r in s.references]
    assert {r.doi or r.isbn for r in references} == {"10.1083/jcb.67.3.835", "978-0-8153-4432-2"}


def test_scenery_groups_are_not_reported_off_frame() -> None:
    """Found while making it: a zoomed `cell` view crops its world on purpose; the pieces are
    marked `scenery` and a group of them only (empty groups beside them aside) counts as scenery
    in the layout dump, so lint's off_frame leaves it alone."""
    from manim import Square, VGroup

    from vidgen.introspect import _scenery

    piece = Square()
    piece.scenery = True
    assert _scenery(piece) and _scenery(VGroup(piece, VGroup())) and _scenery(VGroup(VGroup(piece)))
    assert not _scenery(VGroup(piece, Square())) and not _scenery(VGroup()) and not _scenery(Square())


def test_route_captions_speak_to_viewers() -> None:
    """A cell route's caption is for the viewer: it no longer points at vidgen's molecule scene."""
    import inspect

    from vidgen.cellworld import expression_route

    assert "in a molecule scene" not in inspect.getsource(expression_route)


def test_the_readme_and_the_index_point_to_it() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "examples/gene-to-secreted-protein/README.md" in readme
    assert "α1-antitrypsin" in (EXAMPLE / "README.md").read_text(encoding="utf-8")
