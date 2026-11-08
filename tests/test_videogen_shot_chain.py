"""One shot after another (DESIGN.md §113.14): ``first_frame: last_of:``, the opening match in QA
and the overlay of ``vidgen generate inputs``. Nothing is sent or paid."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import write_clip
from PIL import Image
from test_videogen_first_frame_in import picture_file, the_shot
from test_videogen_input_freshness import changed, config, cut, edit, plan_of, shot_of, stub_render
from test_videogen_shots import CATALOG

from vidgen.project import Project
from vidgen.render.ffmpeg import find_ffmpeg
from vidgen.videogen.inputs import last_frame, make_inputs, make_overlay
from vidgen.videogen.qa import OPENING_WARNING, check_clip, picture_similarity
from vidgen.videogen.shots import project_shots
from vidgen.videogen.takes import add_take, pick_take

MODEL = "bytedance/seedance-2.0-fast"


def keep_take(root: Path, shot: str, key: str, seconds: float = 1.0, **kwargs: Any) -> None:
    """Keep a small clip as a new take of ``shot`` (the last-frame shade depends on ``seconds``)."""
    clip = write_clip(root / "fake" / f"{key}.mp4", seconds=seconds, size="32x18", fps=5, audio=False)
    add_take(root, shot, clip, key=key, model=MODEL, provider="mock", job_id=None, cost=None, length=seconds, width=32, height=18, **kwargs)


def chain_project(make_project, **spec: Any) -> Path:
    return make_project(config(shot_of("a"), shot_of("b", first_frame="last_of:a", **spec)), folder="chain")


def shots_of(root: Path) -> dict[str, Any]:
    return {s.id: s for s in project_shots(Project.load(root), CATALOG)}


# ----- last_of: finding the source -----------------------------------------------------------------


def test_an_unknown_shot_is_a_problem_with_a_hint(make_project) -> None:
    root = make_project(config(shot_of("alpha"), shot_of("b", first_frame="last_of:alhpa")), folder="u")
    assert any("no shot 'alhpa'" in p and "alpha" in p for p in shots_of(root)["b"].problems)


def test_a_shot_cannot_start_from_itself(make_project) -> None:
    root = make_project(config(shot_of("a", first_frame="last_of:a")), folder="self")
    assert any("own last frame" in p for p in shots_of(root)["a"].problems)


def test_shots_waiting_for_each_other_are_problems(make_project) -> None:
    root = make_project(config(shot_of("a", first_frame="last_of:b"), shot_of("b", first_frame="last_of:a")), folder="cycle")
    found = shots_of(root)
    assert all(any("wait for each other" in p and "a -> b -> a" in p or "b -> a -> b" in p for p in found[s].problems) for s in "ab")


def test_a_source_with_no_take_blocks_and_is_not_a_problem(make_project) -> None:
    root = chain_project(make_project)
    shot = shots_of(root)["b"]
    assert not shot.problems and shot.last_of == "a" and shot.last_of_picture is None
    assert any("has no take yet" in b and "--shot a" in b for b in shot.blocked)


def test_the_picture_is_derived_from_the_shown_take(make_project) -> None:
    root = chain_project(make_project)
    keep_take(root, "a", "k1")
    keep_take(root, "a", "k2")
    shot = shots_of(root)["b"]
    assert shot.last_of_picture == root / "build" / "videogen" / "b" / "last_of.a.2.png"
    first = next(i for i in shot.inputs if i.frame)
    assert first.path == shot.last_of_picture and first.role == "first_frame" and "take 2" in first.what
    pick_take(root, "a", "1", ["a"])
    assert shots_of(root)["b"].last_of_picture.name == "last_of.a.1.png"


def test_guide_mode_opens_on_the_picture(make_project) -> None:
    root = chain_project(make_project, guide=True, first_frame_in="guide")
    keep_take(root, "a", "k1")
    shot = shots_of(root)["b"]
    assert shot.opening_picture == shot.last_of_picture and not any(i.frame for i in shot.inputs)


# ----- last_of: the cut, freshness ---------------------------------------------------------------


def test_last_frame_is_the_clips_last_decoded_frame(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "c.mp4", seconds=2.0, size="32x18", fps=5, audio=False)
    dest = tmp_path / "out" / "last.png"
    last_frame(find_ffmpeg(), clip, dest)
    assert np.asarray(Image.open(dest).convert("L")).mean() == pytest.approx(26 + 10 * 9, abs=6)   # frame n: 26 + 10 n, n = 9


def test_a_short_clip_still_gives_a_frame(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "s.mp4", seconds=0.4, size="32x18", fps=5, audio=False)
    dest = tmp_path / "last.png"
    last_frame(find_ffmpeg(), clip, dest)
    assert dest.is_file()


def test_generate_inputs_cuts_the_picture_without_a_render(make_project) -> None:
    root = chain_project(make_project)
    keep_take(root, "a", "k1", seconds=2.0)
    project = Project.load(root)
    written = make_inputs(project, project_shots(project, CATALOG), out=lambda line: None)
    assert [p.name for p in written] == ["last_of.a.1.png"] and written[0].is_file()
    assert not plan_of(root, "b").shot.blocked


def test_another_pick_makes_the_next_shot_stale(make_project) -> None:
    root = chain_project(make_project)
    keep_take(root, "a", "k1", seconds=1.0)
    keep_take(root, "a", "k2", seconds=2.0)
    pick_take(root, "a", "1", ["a"])
    cut(root)
    assert not changed(plan_of(root, "b"))
    pick_take(root, "a", "2", ["a"])
    item = plan_of(root, "b")
    assert item.changed_inputs and "last_of.a.1.png" in item.changed_inputs and "now take 2" in item.changed_inputs and "`vidgen generate inputs`" in item.changed_inputs
    cut(root)
    assert not changed(plan_of(root, "b"))
    pick_take(root, "a", "1", ["a"])   # back to a picture already cut: it still is that take's last frame
    assert not changed(plan_of(root, "b"))


def test_a_source_with_no_take_does_not_stop_the_other_cuts(make_project) -> None:
    root = chain_project(make_project)
    project = Project.load(root)
    lines: list[str] = []
    assert make_inputs(project, project_shots(project, CATALOG), out=lines.append) == []
    assert any("no starting picture yet" in line for line in lines)


# ----- the opening match -----------------------------------------------------------------------


def test_picture_similarity_runs_from_1_downwards() -> None:
    rng = np.random.default_rng(1)
    picture = rng.integers(0, 256, (90, 160)).astype(np.uint8)
    assert picture_similarity(picture, picture) == pytest.approx(1.0)
    assert picture_similarity(picture, rng.integers(0, 256, (90, 160)).astype(np.uint8)) < 0.3


def test_a_clip_opening_on_something_else_warns(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "c.mp4", seconds=1.0, size="64x36", fps=5, audio=False)
    picture = tmp_path / "p.png"
    # a picture that is not flat: a flat grey clip frame is very unlike it
    Image.fromarray(np.random.default_rng(2).integers(0, 256, (36, 64)).astype(np.uint8)).save(picture)
    report = check_clip(clip, length=1.0, width=64, height=36, opening_picture=picture)
    assert report.metrics["opening_similarity"] < OPENING_WARNING
    assert [c for c in report.warnings if c.name == "opening"]
    assert "opening match" in report.lines()[0]


def test_a_clip_opening_on_its_picture_does_not_warn(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "c.mp4", seconds=1.0, size="64x36", fps=5, audio=False)
    picture = tmp_path / "first.png"
    last_frame(find_ffmpeg(), write_clip(tmp_path / "x.mp4", seconds=0.2, size="64x36", fps=5, audio=False), picture)   # frame 0 of the same grey ramp
    report = check_clip(clip, length=1.0, width=64, height=36, opening_picture=picture)
    assert report.metrics["opening_similarity"] > OPENING_WARNING and not [c for c in report.warnings if c.name == "opening"]


def test_without_a_picture_nothing_is_measured(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "c.mp4", seconds=1.0, size="64x36", fps=5, audio=False)
    assert "opening_similarity" not in check_clip(clip, length=1.0, width=64, height=36).metrics


def test_a_picture_that_cannot_be_read_is_only_noted(tmp_path: Path) -> None:
    clip = write_clip(tmp_path / "c.mp4", seconds=1.0, size="64x36", fps=5, audio=False)
    report = check_clip(clip, length=1.0, width=64, height=36, opening_picture=tmp_path / "gone.png")
    assert [c.severity for c in report.checks if c.name == "opening"] == ["info"]


def test_add_take_records_the_score(make_project) -> None:
    root = make_project(config(shot_of("a")), folder="rec")
    picture = root / picture_file(root)
    keep_take(root, "a", "k1", opening_picture=picture)
    from vidgen.videogen.takes import takes_of

    (take,) = takes_of(root, "a")
    assert "opening_similarity" in take.qa["metrics"] and take.info["opening_picture"] == "assets/start.png"


# ----- the overlay ---------------------------------------------------------------------------------


def test_the_overlay_is_half_the_picture_half_the_guide(tmp_path: Path) -> None:
    guide = write_clip(tmp_path / "g.mp4", seconds=0.6, size="32x18", fps=5, audio=False)   # frame 0: grey 26
    picture = tmp_path / "white.png"
    Image.new("RGB", (32, 18), (255, 255, 255)).save(picture)
    dest = tmp_path / "out" / "overlay.png"
    make_overlay(find_ffmpeg(), picture, guide, dest, past_fade=False)
    mean = np.asarray(Image.open(dest).convert("L")).mean()
    assert 125 < mean < 150   # (26 + 255) / 2


def test_inputs_write_the_overlay_from_the_plain_guide(make_project) -> None:
    root = make_project(config(shot_of("act", guide=True, first_frame="assets/start.png", first_frame_in="guide")), folder="ov")
    picture_file(root)
    project = Project.load(root)
    lines: list[str] = []
    written = make_inputs(project, project_shots(project, CATALOG), guide=True, out=lines.append, render=stub_render(root))
    assert [p.name for p in written].count("overlay.png") == 1
    assert (root / "build" / "videogen" / "act" / "overlay.png").is_file() and any("overlay.png" in line for line in lines)


def test_a_shot_with_no_starting_picture_gets_no_overlay(make_project) -> None:
    root = make_project(config(shot_of("act", guide=True)), folder="noov")
    project = Project.load(root)
    written = make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=stub_render(root))
    assert "overlay.png" not in [p.name for p in written]
