"""Character sheets (`vidgen character-sheet`) and mid-action stills of `stage` scenes (Step 83)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES
from test_json_output import documented
from vidgen import extensions, registry
from vidgen.cartoon.poses import EXPRESSIONS, POSES
from vidgen.cartoon.still import (
    SHEET_CELL_WIDTH,
    SHEET_COLUMNS,
    SHEET_GUTTER,
    SHEET_HEAD_CELL_HEIGHT,
    SHEET_LABEL_LINE,
    SHEET_MARGIN,
    SHEET_POSE_CELL_HEIGHT,
    SHEET_SECTION_LINE,
    SHEET_SUBTITLE_LINE,
    SHEET_TITLE_LINE,
    SheetSection,
    character_sheet_sections,
    sheet_layout,
)
from vidgen.cli import main
from vidgen.config import CharacterEntry
from vidgen.project import Project
from vidgen.sheets import SheetStill, _label

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "svg_character"
GENERATED_MOUTHS = ["smile", "open", "A", "E", "O", "U", "M", "F", "L", "W"]


# ----- the grid (no drawing) ------------------------------------------------------------------------


def test_sections_of_a_generated_and_an_svg_character() -> None:
    kit = CharacterEntry(**CAST[1])   # its own expression 'smug'
    sections = character_sheet_sections(kit, Path("."))
    assert [(s.kind, s.title) for s in sections] == [("pose", "poses"), ("expression", "expressions"), ("mouth", "mouth shapes")]
    assert list(sections[0].names) == list(POSES) and sections[0].own == ()
    assert list(sections[1].names) == [*EXPRESSIONS, "smug"] and sections[1].own == ("smug",)
    assert list(sections[2].names) == GENERATED_MOUTHS
    sprout = Project.load(EXAMPLE).config.characters[0]
    poses, expressions, mouths = character_sheet_sections(sprout, EXAMPLE)
    assert poses.names[-1] == "bow" and poses.own == ("bow",) and expressions.own == ("cheer",)
    assert mouths.names == ("smile", "A", "E", "O", "M")   # the shapes its file names


def rows_height(cells: int, columns: int, cell_height: int) -> int:
    rows = -(-cells // columns)
    return SHEET_SECTION_LINE + rows * (cell_height + SHEET_LABEL_LINE + SHEET_GUTTER)


@pytest.mark.parametrize(
    ("counts", "columns", "rows"),
    [
        ((7, 7, 10), SHEET_COLUMNS, (1, 1, 2)),   # a generated character: 10 mouth shapes take two rows
        ((8, 8, 5), SHEET_COLUMNS, (1, 1, 1)),    # sprout (examples/svg_character)
        ((7, 9), SHEET_COLUMNS, (1, 2)),          # no mouth: two sections
        ((3, 2), 3, (1, 1)),                      # few names: the sheet is narrower
    ],
)
def test_sheet_grid_size_per_character(counts: tuple[int, ...], columns: int, rows: tuple[int, ...]) -> None:
    kinds = ["pose", "expression", "mouth"]
    sections = [SheetSection(kinds[k], kinds[k], tuple(f"n{i}" for i in range(n))) for k, n in enumerate(counts)]  # type: ignore[arg-type]
    layout = sheet_layout(sections)
    assert layout.columns == columns
    assert layout.width == 2 * SHEET_MARGIN + columns * SHEET_CELL_WIDTH + (columns - 1) * SHEET_GUTTER
    heights = [SHEET_POSE_CELL_HEIGHT] + [SHEET_HEAD_CELL_HEIGHT] * (len(counts) - 1)
    body = sum(rows_height(n, columns, h) for n, h in zip(counts, heights))
    assert layout.height == SHEET_MARGIN + SHEET_TITLE_LINE + SHEET_SUBTITLE_LINE + body + SHEET_MARGIN - SHEET_GUTTER
    assert len(layout.cells) == sum(counts)
    for index, (count, row_count) in enumerate(zip(counts, rows)):
        cells = [c for c in layout.cells if c.section == index]
        assert len({c.y for c in cells}) == row_count and max(c.x + c.width for c in cells) <= layout.width - SHEET_MARGIN
        assert all(c.y >= layout.section_tops[index] + SHEET_SECTION_LINE and c.height == heights[index] for c in cells)


# ----- mid-action stills: what a stage asks for, how the sheet labels them -----------------------------


def test_stage_asks_for_mid_action_stills_of_its_moving_actions() -> None:
    extensions.load_builtins()
    stage = registry.get("stage").cls
    assert stage.mid_still_actions == {"walk_to", "enter", "exit", "gesture", "jump", "keyframes", "move_along", "pick_up", "put_down", "give", "throw"}
    assert stage.mid_still_actions <= set(registry.action_names())
    assert registry.get("text_card").cls.mid_still_actions == frozenset()


def test_sheet_label_of_a_mid_action_still() -> None:
    still = SheetStill("park", "b1", 0, 1, 1.25, 3.25, Path("b1-m6.png"), "Hello.", mid="walk_to pip")
    assert _label(still, video_times=False) == "½ walk_to pip @ 1.2 s"
    assert _label(SheetStill("park", "b1", 1, 1, 2.0, None, Path("b1-1.png"), "Hello."), video_times=False) == "b1 @ 2.0 s"


# ----- drawing --------------------------------------------------------------------------------------


@pytest.mark.render
def test_character_sheet_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--all PROJECT --json`: a sheet per character, as large as its layout, small; then one by name."""
    from PIL import Image

    root = tmp_path / "svg_character"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("build", "exports", "output"))
    assert main(["character-sheet", "--all", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "character-sheet" and doc["ok"]
    assert [s["character"] for s in doc["sheets"]] == ["sprout", "pebble"]
    documented(*doc, *doc["sheets"][0], *doc["sheets"][0]["sections"][0])
    for sheet in doc["sheets"]:
        path = Path(sheet["path"])
        assert path == root / "exports" / f"character_sheet_{sheet['character']}.png"
        entry = next(c for c in Project.load(root).config.characters if c.name == sheet["character"])
        layout = sheet_layout(character_sheet_sections(entry, root))
        with Image.open(path) as image:
            assert image.size == (layout.width, layout.height) == (sheet["width"], sheet["height"])
            assert image.mode == "P"   # a palette: small
        assert sheet["bytes"] == path.stat().st_size < 60_000
        assert [s["kind"] for s in sheet["sections"]] == ["pose", "expression", "mouth"]
    out = tmp_path / "pebble.png"
    assert main(["character-sheet", "pebble", str(root), "--output", str(out)]) == 0
    assert out.is_file() and "7 poses, 7 expressions, 10 mouth shapes" in capsys.readouterr().out
    assert main(["character-sheet", "nobody", str(root)]) == 1


@pytest.mark.render
def test_stage_storyboard_stills_include_mid_action_frames(make_project, tmp_path: Path) -> None:
    """A walk and a gesture get a still half-way through them, besides the beat's end."""
    from manim import tempconfig

    from vidgen.capture import FrameCapture, StillWriter
    from vidgen.render.worker import frame_size

    params = {"idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}]}
    beats = [
        {"text": "Pip walks over to the middle of the park and waves at kit there.",
         "actions": [{"walk_to": "pip", "to": "centre", "speed": 4}, {"gesture": "pip", "to": "wave", "at": 0.7}]},
        {"text": "Nothing moves now."},
    ]
    scenes = [{"id": "park", "type": "stage", "params": params, "beats": beats}]
    project = Project.load(make_project(minimal_config(characters=CAST, voices=VOICES, scenes=scenes)))
    fw, fh = frame_size(160, 90)
    settings = {"pixel_width": 160, "pixel_height": 90, "frame_width": fw, "frame_height": fh, "frame_rate": 5,
                "media_dir": str(tmp_path / "media"), "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}
    writer = StillWriter(tmp_path / "frames")
    plays: list[Any] = []
    with tempconfig(settings):
        spec = project.scene("park")
        scene_cls = registry.get(spec.type).cls
        scene = scene_cls(spec, project, extensions.activate(project), capture=FrameCapture(1, [writer]))
        original = scene.play

        def play(*animations: Any, **kwargs: Any) -> None:
            start = round(float(scene.renderer.time) * 5)
            original(*animations, **kwargs)
            plays.append((start, round(float(scene.renderer.time) * 5) - start, [type(a).__name__ for a in animations]))

        scene.play = play   # type: ignore[method-assign]
        scene.render()
    frames = writer.index("park", 1, 160, 90, 5)["frames"]
    mids = [f for f in frames if "mid" in f]
    assert [(f["beat"], f["mid"], f["k"]) for f in mids] == [("park_b1", "walk_to pip", 0), ("park_b1", "gesture pip", 0)]
    for still, name in zip(mids, ("Walk", "Gesture")):
        start, count, _ = next(p for p in plays if name in p[2])
        assert still["frame"] == start + count // 2 and (tmp_path / "frames" / still["path"]).is_file()
    ends = [f for f in frames if "mid" not in f]
    assert [(f["beat"], f["k"]) for f in ends] == [("park_b1", 1), ("park_b2", 1)]
