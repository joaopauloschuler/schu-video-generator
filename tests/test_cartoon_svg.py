"""Step 69: characters drawn from SVG files (``look: {svg: FILE}``), split into parts by element ids."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from vidgen import cli, runtime
from vidgen.cartoon.cast import ACTION_NEEDS, character_lines, unavailable_actions
from vidgen.cartoon.character import Character, build_character, character
from vidgen.cartoon.svg_look import (
    SVG_REQUIRED_PARTS,
    default_pivot,
    part_key,
    pivot_warnings,
    read_character_svg,
    split_character_svg,
    svg_character_parts,
)
from vidgen.cli import project_problems, validate_warnings
from vidgen.config import CharacterEntry, CharacterLook
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.theme import Theme

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "svg_character" / "assets" / "sprout.svg"
EXAMPLE_PARTS = {
    "arm_right": ["rest"], "legs": ["rest"], "body": ["rest"], "arm_left": ["rest"], "head": ["rest"],
    "eyes": ["open", "closed"], "brows": ["rest"], "mouth": ["smile", "A", "E", "O", "M"],
}


def svg(body: str, view_box: str = "0 0 100 200") -> bytes:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">{body}</svg>'.encode()


# ----- splitting (no manim) ------------------------------------------------------------------


def test_example_svg_splits_into_every_part() -> None:
    split = read_character_svg(EXAMPLE, where="sprout.svg")
    assert split.part_shapes() == EXAMPLE_PARTS
    assert split.pivots == {"arm_right": (70, 150), "legs": (100, 226), "body": (101, 230), "arm_left": (132, 150), "head": (102, 132)}
    assert split.warnings == () and split.report.warnings == () and pivot_warnings(split, "x") == []
    assert unavailable_actions(split.part_shapes()) == []


def test_part_keys() -> None:
    assert part_key("mouth") == ("mouth", "smile") and part_key("eyes") == ("eyes", "open") and part_key("head") == ("head", "rest")
    assert part_key("mouth_A") == ("mouth", "A") and part_key("eyes_closed") == ("eyes", "closed")
    assert part_key("arm_left") == ("arm_left", "rest") and part_key("arm_left_up") == ("arm_left", "up")
    assert part_key("path12") is None and part_key("mouth_") is None and part_key("arm") is None


def test_nesting_loose_shapes_and_pieces() -> None:
    data = svg(
        '<rect x="10" y="100" width="80" height="90"/>'                       # loose: body
        '<g id="head"><circle cx="50" cy="50" r="40"/><path id="head_outline" d="M 10 50 L 90 50"/>'
        '<g id="eyes"><circle cx="40" cy="45" r="3"/></g></g>'                # eyes inside head
        '<circle cx="5" cy="5" r="2" display="none"/>'                        # hidden, outside parts: not drawn
        '<g id="mouth_O" style="display:none"><circle cx="50" cy="70" r="4"/></g>'
    )
    split = split_character_svg(data, where="t.svg")
    assert split.part_shapes() == {"body": ["rest"], "head": ["rest"], "eyes": ["open"], "mouth": ["O"]}
    by_key = {(s.part, s.shape): s for s in split.shapes}
    head = by_key[("head", "rest")].data.decode()
    assert "head_outline" in head and 'r="3"' not in head            # head_outline is a piece of head; eyes are not
    assert 'r="2"' not in by_key[("body", "rest")].data.decode()     # the hidden loose circle is dropped
    mouth = by_key[("mouth", "O")].data.decode()
    assert "display" not in mouth and 'r="4"' in mouth               # the hidden shape is shown in its own document
    assert all(s.data.decode().count("<rect") >= 1 for s in split.shapes)   # every document keeps the viewBox box


def test_no_ids_is_a_body_only_character() -> None:
    split = split_character_svg(svg('<rect x="10" y="10" width="80" height="180"/>'), where="t.svg")
    assert split.part_shapes() == {"body": ["rest"]}
    assert {action for action, _ in unavailable_actions(split.part_shapes())} == set(ACTION_NEEDS)


def test_split_errors() -> None:
    with pytest.raises(VidgenError, match="two elements are the smile shape of mouth"):
        split_character_svg(svg('<rect width="9" height="9"/><path id="mouth" d="M0 0 L1 1"/><g id="mouth"><path d="M0 0 L1 1"/></g>'), where="t.svg")
    with pytest.raises(VidgenError, match="data-pivot of 'head' must be two numbers"):
        split_character_svg(svg('<rect width="9" height="9"/><circle id="head" cx="5" cy="5" r="4" data-pivot="5"/>'), where="t.svg")
    with pytest.raises(VidgenError, match="no body"):
        split_character_svg(svg('<circle id="head" cx="5" cy="5" r="4"/>'), where="t.svg")
    with pytest.raises(VidgenError, match="file not found"):
        read_character_svg(Path("nowhere.svg"), where="nowhere.svg")
    with pytest.raises(VidgenError, match="declares XML entities"):
        split_character_svg(b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>', where="t.svg")


def test_split_warnings() -> None:
    data = svg(
        '<rect width="100" height="200"/><script>alert(1)</script>'
        '<circle id="Mouth" cx="5" cy="5" r="4"/>'                 # near miss
        '<circle id="eyes_closed" cx="5" cy="5" r="2"/>'           # another shape, but visible
        '<g id="arm_left"></g>'                                    # draws nothing
        '<circle id="head" cx="50" cy="40" r="30"/>'
    )
    split = split_character_svg(data, where="t.svg")
    text = "\n".join(split.warnings)
    assert "id 'Mouth' is not a part name (did you mean 'mouth'?)" in text
    assert "'eyes_closed' is another shape of eyes" in text and "'arm_left' draws nothing" in text
    assert any("scripts removed" in w for w in split.report.warnings)
    assert pivot_warnings(split, "t.svg") == ['t.svg: no data-pivot on head: the pivot is guessed from the part\'s box (add data-pivot="x y" in viewBox coordinates)']


def test_unavailable_actions() -> None:
    one_arm = {"body": ["rest"], "head": ["rest"], "arm_right": ["rest"], "eyes": ["open"], "mouth": ["smile"]}
    missing = dict(unavailable_actions(one_arm))
    assert missing == {"blink": "eyes_closed", "gesture: shrug": "arm_left and arm_right"}
    assert dict(unavailable_actions({"body": ["rest"]}))["gesture: wave"] == "arm_left or arm_right"


def test_default_pivots() -> None:
    assert default_pivot("head", (0, 1, 2, 3), 0) == (1, 1)
    assert default_pivot("legs", (0, 0, 2, 1), 0) == (1, 1)
    assert default_pivot("arm_left", (2, 0, 3, 2), 0) == (2, 2) and default_pivot("arm_right", (-3, 0, -2, 2), 0) == (-2, 2)
    assert default_pivot("mouth", (0, 0, 2, 2), 0) == (1, 1)


def test_look_svg_config() -> None:
    assert CharacterLook(svg="assets/a.svg").svg == "assets/a.svg"
    with pytest.raises(ValidationError, match="body, eyes only apply to the generator"):
        CharacterLook(svg="a.svg", body="tall", eyes="oval")
    with pytest.raises(ValidationError, match="svg must name an .svg file"):
        CharacterLook(svg="a.png")


# ----- parts and the character (manim) -------------------------------------------------------


def test_parts_in_character_units() -> None:
    parts = {p.name: p for p in svg_character_parts(EXAMPLE, where="sprout.svg")}
    assert list(parts) == list(EXAMPLE_PARTS)
    assert [p.order for p in parts.values()] == [0, 10, 20, 30, 40, 50, 60, 70]   # the file's order
    assert parts["eyes"].parent == "head" and parts["arm_left"].parent == "body" and parts["body"].parent is None
    # the figure spans y 12..290 in the file (stroke not counted), the legs x 76..134 (feet at 105)
    unit = 1 / 278
    assert parts["head"].pivot == pytest.approx(((102 - 105) * unit, (290 - 132) * unit), abs=0.002)
    c = Character(parts.values(), name="sprout", height=2.0, required=SVG_REQUIRED_PARTS)
    assert c.get_bottom()[1] == pytest.approx(0, abs=0.02) and c.get_top()[1] == pytest.approx(2.0, abs=0.02)
    assert c.shape_names("mouth") == ["smile", "A", "E", "O", "M"] and c.shape_names("eyes") == ["open", "closed"]
    hand = c.parts["arm_left"].get_bottom()[1]
    c.set_part("arm_left", angle=150).swap("mouth", "A").face("left")
    assert c.parts["arm_left"].get_bottom()[1] > hand   # the arm turned up about its shoulder
    assert c.pivot("arm_left")[0] < 0                     # facing left mirrors it to the other side


def test_svg_strokes_follow_the_character_height() -> None:
    from manim import tempconfig

    with tempconfig({"pixel_width": 1920, "pixel_height": 1080, "frame_width": 14.22, "frame_height": 8.0}):
        parts = svg_character_parts(EXAMPLE, where="sprout.svg")
        small = Character(parts, height=3.0, required=SVG_REQUIRED_PARTS)
        big = Character(parts, height=6.0, required=SVG_REQUIRED_PARTS)
    width = lambda c: max(m.get_stroke_width() for m in c.parts["body"].family_members_with_points())  # noqa: E731
    # body stroke 4 SVG units of a 278-unit figure, 3 Manim units tall: 4 / 278 * 3 / 0.01
    assert width(small) == pytest.approx(4 / 278 * 3 / 0.01, rel=0.02) and width(big) == pytest.approx(2 * width(small))


def test_body_only_svg_builds(tmp_path: Path) -> None:
    path = tmp_path / "c.svg"
    path.write_bytes(svg('<rect x="10" y="10" width="80" height="180"/>'))
    parts = svg_character_parts(path, where="c.svg")
    c = Character(parts, required=SVG_REQUIRED_PARTS)
    assert list(c.parts) == ["body"] and not c.has_part("arm_left")
    with pytest.raises(VidgenError, match="missing part"):
        Character(parts)   # the generator's required parts still apply by default


# ----- the project: build, validate, vidgen character ----------------------------------------


def svg_project(make_project, look: dict | None = None, **entry) -> Project:
    root = make_project(minimal_config(characters=[{"name": "sprout", "look": look or {"svg": "assets/sprout.svg"}, **entry}]))
    (root / "assets").mkdir(exist_ok=True)
    shutil.copy(EXAMPLE, root / "assets" / "sprout.svg")
    return Project.load(root)


def test_build_and_character_helper(make_project) -> None:
    project = svg_project(make_project)
    entry = project.config.characters[0]
    c = build_character(entry, root=project.root, height=2.0)
    assert c.name == "sprout" and set(c.parts) == set(EXAMPLE_PARTS)
    with runtime.use_context(project):
        assert set(character("sprout").parts) == set(EXAMPLE_PARTS)


def test_validate_reports_svg_problems_and_warnings(make_project) -> None:
    project = svg_project(make_project)
    assert project_problems(project) == [] and validate_warnings(project) == []
    missing = svg_project(make_project, {"svg": "assets/gone.svg"})
    problems = {p.location: p.message for p in project_problems(missing)}
    assert "file not found" in problems["characters[0].look.svg"]
    (missing.root / "assets" / "armless.svg").write_bytes(svg('<rect x="10" y="10" width="80" height="180"/><path id="mouth" d="M 40 40 L 60 40"/>'))
    armless = svg_project(make_project, {"svg": "assets/armless.svg"}, colors={"skin": "accent"})
    warnings = "\n".join(validate_warnings(armless))
    assert "character 'sprout' (assets/armless.svg): actions unavailable: blink (needs eyes_closed)" in warnings
    assert "gesture: wave (needs arm_left or arm_right)" in warnings
    assert "colors are not used by an svg look" in warnings and "the mouth has one shape" in warnings


def test_character_lines_for_an_svg_look(make_project, capsys) -> None:
    entry = CharacterEntry(name="sprout", look={"svg": "assets/sprout.svg"})
    assert character_lines(entry, Theme()) == ["character sprout  (voice: none)", "  look:   svg assets/sprout.svg", "  colors: the SVG's own"]
    project = svg_project(make_project)
    assert cli.main(["character", "sprout", str(project.root)]) == 0
    out = capsys.readouterr().out
    assert "parts:  arm_right, legs, body, arm_left, head, eyes (open, closed), brows, mouth (smile, A, E, O, M)" in out


@pytest.mark.render
def test_svg_character_still(make_project) -> None:
    from manim import Camera, tempconfig

    project = svg_project(make_project)
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 14.22, "frame_height": 8.0, "background_color": "#FFFFFF"}):
        figure = build_character(project.config.characters[0], root=project.root, height=6.0).move_to([0, 0, 0])
        camera = Camera()
        camera.capture_mobjects([figure])
        image = np.asarray(camera.get_image().convert("RGB"), dtype=int)
    drawn = np.any(np.abs(image - 255) > 30, axis=2)
    assert 0.05 < drawn.mean() < 0.5
