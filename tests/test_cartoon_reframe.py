"""Step 96: vertical cartoons follow the speaker (``reframe:``). The camera path is a pure function
of the beats, tested without rendering; the example's 9:16 variant is planned (no render)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from test_cartoon_directing import FEET, FH, FW, HEIGHT, MOVERS, line
from vidgen import extensions
from vidgen.cartoon.directing import (
    FIGURE_HALF_WIDTH,
    StageFrame,
    StagePlace,
    auto_label,
    plan_reframe,
    project_directions,
    stage_directions,
)
from vidgen.cartoon.reframe import (
    REFRAME_LOOK_ROOM,
    REFRAME_SECONDS,
    REPLY_HOLD_SECONDS,
    CameraMove,
    ReframeBeat,
    ReframeFigure,
    reframe_needed,
    reframe_path,
    stage_base_width,
)
from vidgen.project import Project

VW = 8.0                    # a 9:16 frame's width in Manim units
STAGE = 16 / 9 * VW         # the landscape stage it crops
HALF = FIGURE_HALF_WIDTH * HEIGHT
BOUNDS = (-STAGE / 2, STAGE / 2)
PIP = ReframeFigure("pip", -0.25 * STAGE, HALF, "right")
KIT = ReframeFigure("kit", 0.25 * STAGE, HALF, "left")


def beat(id: str, speaker: str | None = None, seconds: float = 3.0, figures: tuple[ReframeFigure, ...] = (PIP, KIT), **kw: Any) -> ReframeBeat:
    return ReframeBeat(id, (speaker,) if speaker else (), seconds, figures, **kw)


def path(*beats: ReframeBeat, start_x: float = 0.0) -> list[CameraMove]:
    return reframe_path(beats, frame_width=VW, bounds=BOUNDS, start_x=start_x)


def shows(figure: ReframeFigure, x: float) -> bool:
    left, right = figure.box()
    return left >= x - VW / 2 - 1e-6 and right <= x + VW / 2 + 1e-6


def cuts(figure: ReframeFigure, x: float) -> bool:
    left, right = figure.box()
    return any(left + 0.02 * (right - left) < edge < right - 0.02 * (right - left) for edge in (x - VW / 2, x + VW / 2))


# ----- the path (pure) -------------------------------------------------------------------------------------


def test_the_landscape_stage_a_narrow_frame_crops() -> None:
    assert stage_base_width(VW, FW, True) == pytest.approx(STAGE)          # 9:16: the 16:9 stage of the same short side
    assert stage_base_width(VW, FW, False) == VW                           # not reframing: the frame, as before
    assert stage_base_width(FW, FH, True) == pytest.approx(FW)             # 16:9 is already that wide
    assert stage_base_width(8.0, 8.0, True) == pytest.approx(STAGE)        # 1:1 too
    assert reframe_needed([PIP.box(), KIT.box()], VW) and not reframe_needed([PIP.box(), KIT.box()], FW)
    assert not reframe_needed([], VW)


def test_the_camera_eases_from_speaker_to_speaker() -> None:
    moves = path(beat("b1", "pip"), beat("b2", "kit"), beat("b3", "kit"), beat("b4", "pip"))
    assert [(m.beat, m.seconds) for m in moves] == [("b1", 0.0), ("b2", REFRAME_SECONDS), ("b4", REFRAME_SECONDS)]   # the first a cut
    first, second, third = (m.x for m in moves)
    assert shows(PIP, first) and not cuts(KIT, first) and shows(KIT, second) and not cuts(PIP, second) and third == first
    assert first == pytest.approx(PIP.x + REFRAME_LOOK_ROOM * VW)    # room in front of pip's face (it faces right)
    assert second == pytest.approx(KIT.x - REFRAME_LOOK_ROOM * VW)


def test_before_the_first_line_the_camera_cuts_to_the_first_speaker() -> None:
    moves = path(beat("b1"), beat("b2"), beat("b3", "kit"))
    assert [(m.beat, m.seconds) for m in moves] == [("b1", 0.0)] and shows(KIT, moves[0].x)
    assert path(beat("b1"), beat("b2", "kit"), start_x=KIT.x) == []    # already in view: nothing
    assert path(beat("b1"), beat("b2", camera="pan", camera_x=0.0), beat("b3", "kit")) != []   # a pan first: framed at b3
    assert [m.beat for m in path(beat("b1"), beat("b2", camera="pan", camera_x=0.0), beat("b3", "kit"))] == ["b3"]


def test_a_short_reply_holds_the_view() -> None:
    short = REPLY_HOLD_SECONDS - 0.1
    moves = path(beat("b1", "pip"), beat("b2", "kit", seconds=short), beat("b3", "pip"), beat("b4", "kit", seconds=REPLY_HOLD_SECONDS))
    assert [m.beat for m in moves] == ["b1", "b4"]


def test_written_camera_moves_win() -> None:
    zoomed = path(beat("b1", "pip"), beat("b2", "kit", camera="held"), beat("b3", "pip"))
    assert [m.beat for m in zoomed] == ["b1"]                                       # back from the zoom to pip's view
    followed = path(beat("b1", "pip"), beat("b2", "kit", camera="follow"), beat("b3", "pip"), beat("b4", camera="pan", camera_x=KIT.x), beat("b5", "pip"))
    assert [m.beat for m in followed] == ["b1", "b5"]                               # nothing while following; after the pan, again
    unknown = path(beat("b1", "pip"), beat("b2", camera="pan"), beat("b3", "kit"))
    assert [m.beat for m in unknown] == ["b1"]                                      # a pan whose view is not known


def test_a_bubble_cuts_instead_of_easing() -> None:
    moves = path(beat("b1", "pip"), beat("b2", "kit", bubble=True), beat("b3", "pip", seconds=REPLY_HOLD_SECONDS))
    assert [(m.beat, m.seconds) for m in moves] == [("b1", 0.0), ("b2", 0.0), ("b3", REFRAME_SECONDS)]
    assert REFRAME_SECONDS <= 0.8 * REPLY_HOLD_SECONDS   # every ease fits the line that moves the camera


def test_the_view_cuts_no_other_character() -> None:
    near = ReframeFigure("rex", PIP.x + 2.5, HALF, "left")   # just right of pip: the look room would cut it
    (move,) = path(beat("b1", "pip", figures=(PIP, near, KIT)))
    assert shows(PIP, move.x) and not cuts(near, move.x) and not cuts(KIT, move.x)
    walker = ReframeFigure("pip", PIP.x + 2.0, HALF, "right", start_x=PIP.x)   # walks while speaking: both ends in view
    (move,) = path(beat("b1", "pip", figures=(walker, KIT)))
    assert shows(PIP, move.x) and shows(walker, move.x)


def test_a_frame_as_wide_as_the_stage_never_moves() -> None:
    assert reframe_path([beat("b1", "pip"), beat("b2", "kit")], frame_width=STAGE, bounds=BOUNDS, start_x=0.0) == []


# ----- from the planner's beats ------------------------------------------------------------------------------


VERTICAL = StageFrame(VW, FW, STAGE, 0.0, {"pip": StagePlace(PIP.x, FEET, HEIGHT, "right"), "kit": StagePlace(KIT.x, FEET, HEIGHT, "left")})


def test_plan_reframe_writes_pans_to_the_speaker() -> None:
    beats = [
        line("b1", "Once upon a time."),
        line("b2", "Is that a kite, kit, over there?", ("pip",)),
        line("b3", "It is a box with a string on it.", ("kit",)),
        line("b4", "Sure.", ("pip",)),                                   # a short reply: held
        line("b5", "Look at me walking over here now.", ("kit",), [{"walk_to": "kit", "to": 0.6}]),
        line("b6", "Here we go, look over there!", ("pip",), [{"pan": "kit"}]),
    ]
    planned = {d.beat: [auto_label(a) for a in d.actions] for d in plan_reframe(MOVERS, beats, VERTICAL)}
    assert list(planned) == ["b1", "b3"]
    assert planned["b1"][0].endswith(" cut") and planned["b3"][0].startswith("pan ")
    to = float(planned["b3"][0].split()[1])
    assert shows(KIT, (to - 0.5) * STAGE)


# ----- the example's 9:16 variant ------------------------------------------------------------------------


def example_project(tmp_path: Path, **extra: Any) -> Path:
    root = tmp_path / "cartoon"
    root.mkdir()
    data = yaml.safe_load((Path(__file__).resolve().parents[1] / "examples" / "cartoon" / "video.yaml").read_text(encoding="utf-8"))
    data["variants"] = {"vertical": {"format": {"width": 1080, "height": 1920, "fps": 30}, "preview": {"width": 270, "height": 480, "fps": 15}}}
    (root / "video.yaml").write_text(yaml.safe_dump({**data, **extra}, sort_keys=False), encoding="utf-8")
    return root


def labels(project: Project) -> dict[str, list[tuple[str, list[str]]]]:
    with extensions.project_session(project):
        found = project_directions(project)
    return {sid: [(d.beat, [auto_label(a) for a in d.actions]) for d in beats] for sid, beats in found.items()}


def test_the_example_reframes_in_9_16_only(tmp_path: Path) -> None:
    root = example_project(tmp_path)
    assert labels(Project.load(root)) == {}                       # 16:9: everyone fits, nothing changes
    vertical = labels(Project.load(root, variant="vertical"))
    assert list(vertical) == ["yard"]                              # the hill's two start close together
    assert [b for b, _ in vertical["yard"]] == ["yard_plan", "yard_box", "yard_clever", "yard_expert"]
    assert vertical["yard"][0][1][0].endswith(" cut")             # the set fades in on dot
    assert vertical["yard"][3][1][0].endswith(" cut")             # moss's speech bubble: built for its view
    assert "yard_aside" not in dict(vertical["yard"])              # its written zoom wins
    off = tmp_path / "off"
    off.mkdir()
    assert labels(Project.load(example_project(off, reframe="none"), variant="vertical")) == {}


def test_reframe_needs_the_stage_geometry(tmp_path: Path) -> None:
    project = Project.load(example_project(tmp_path), variant="vertical")
    spec = project.scene("yard")
    with extensions.project_session(project):
        assert stage_directions(project, spec, ["dot", "moss"], None, None, reframe=True) == []
