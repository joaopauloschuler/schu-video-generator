"""Step 175: the iso_diagram example `examples/iso-web-page` through `vidgen validate` (16:9 and its
9:16 variant) using the phase's features, and the fixes found while making it: the diagram is
fitted at the largest scale that fits even when a smaller one does not (labels pushed clear at one
scale lie by their block at a larger one), `focus` places its targets in the safe area (clear of
the captions), and `focus: diagram` goes back to the whole frame (the heading too)."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from test_actions import beats, project_with, render
from test_iso_diagram_actions import SCENE
from vidgen.cli import main, validate_all
from vidgen.project import Project
from vidgen.regions import Region

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "iso-web-page"


# ----- the example -------------------------------------------------------------------------------


@pytest.mark.parametrize("variant", [None, "short"])
def test_the_example_validates_and_uses_phase_r(variant: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = shutil.copytree(EXAMPLE, tmp_path / "web", ignore=shutil.ignore_patterns("build", "output", "exports", "audio"))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    project = Project.load(root, variant=variant)
    assert validate_all(project, keep_going=True)[0] == []
    types = [s.type for s in project.config.scenes]
    assert types.count("iso_diagram") == 3 and {"title", "bullets"} <= set(types)
    assert set(project.config.terms) == {"cache", "database"}
    text = (root / "video.yaml").read_text(encoding="utf-8")
    for used in ("build:", "style: drop", "flow:", "back: true", "chain: true", "style: packets", "explode:", "collapse:",
                 "focus:", "focus: diagram", "relabel:", "raise:", "dim:", "highlight:", "until:", 'at: "@', "layers:",
                 "groups:", "style: pipe", "-->", "shape: database", "shape: cylinder", "shape: tile", "shape: slab"):
        assert used in text, used


# ----- the fit: the largest scale that fits ------------------------------------------------------


def test_the_fit_finds_the_largest_scale_even_when_a_smaller_one_does_not_fit() -> None:
    from vidgen.scenes.iso_diagram import IsoDiagram, _Placement

    def place(scale: float, labels: list, sideways: bool = False) -> _Placement:
        width = 40.0 if 1.0 < scale < 1.5 else 4 * scale    # a label pushed far at middle scales only
        return _Placement(bounds=(0.0, 0.0, width, 1.0))

    stub = SimpleNamespace(max_tile=2.4, portrait_tile=1.35, is_portrait=False, _place=place, _bounds=(0.0, 0.0, 1.0, 0.1))
    plan = IsoDiagram._largest(stub, Region(0.0, 0.0, 8.0, 8.0), [])   # type: ignore[arg-type]
    assert plan.fits and plan.scale == pytest.approx(2.0, abs=0.01)     # bisection from the bottom stopped near 1.0
    tight = IsoDiagram._largest(stub, Region(0.0, 0.0, 0.5, 8.0), [])   # type: ignore[arg-type]
    assert not tight.fits and tight.scale == pytest.approx(0.15)          # nothing fits: the smallest


# ----- focus in the safe area, and back ----------------------------------------------------------


def on_screen(scene, point: np.ndarray) -> np.ndarray:
    frame = scene.camera.frame
    factor = scene.frame_width / frame.width
    return (np.asarray(point[:2]) - frame.get_center()[:2]) * factor


@pytest.mark.render
def test_focus_keeps_its_targets_clear_of_the_captions_and_diagram_goes_back(make_project, tmp_path: Path) -> None:
    captions = [{"type": "captions", "style": "karaoke"}]
    scenes = [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats([{"focus": "block:db", "padding": 0.2}])}]
    scene = render(project_with(make_project, scenes, overlays=captions), "s", tmp_path / "media", size=(160, 90))
    assert scene.camera.frame.width < scene.frame_width - 1e-3
    area = scene.safe_area
    db = scene._parts["blocks"]["db"]
    assert area.center[1] > 0.1                                           # the captions take room at the bottom
    assert on_screen(scene, db.get_center())[1] > 0.1                     # so the focused block sits above the middle
    for corner in (db.get_corner(np.array([-1, -1, 0])), db.get_corner(np.array([1, 1, 0]))):
        x, y = on_screen(scene, corner)
        assert area.x0 - 1e-3 <= x <= area.x1 + 1e-3 and area.y0 - 1e-3 <= y <= area.y1 + 1e-3
    back = [{"id": "s", "type": "iso_diagram", "params": SCENE, "beats": beats([{"focus": "block:db"}], [{"focus": "diagram"}])}]
    whole = render(project_with(make_project, back), "s", tmp_path / "media", size=(160, 90))
    assert whole.camera.frame.width == pytest.approx(whole.frame_width)
    assert np.allclose(whole.camera.frame.get_center()[:2], 0.0, atol=1e-6)
