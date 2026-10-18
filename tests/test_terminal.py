"""Step 159: the ``terminal`` scene type (commands typed at a prompt and their output shown, beat
by beat or on a spoken word; the author writes the output, vidgen runs nothing), its session rows,
params and targets, and tiny renders in 16:9 and 9:16, with a ``clear`` and the code beside it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from manim import Code, Paragraph
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, render
from test_builtin_scenes import cls_of
from test_comparison_table import safe_area_of
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.scenes.terminal import CURSOR_OPACITY, session_pages
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
STEPS = [{"command": "pip install -e .", "output": "ok"}, {"command": "pytest -q", "output": "..F\n1 failed, 2 passed"}]


def params(steps: list[Any], **changes: Any) -> Any:
    return cls_of("terminal").validate_params({"steps": steps, **changes}, Theme())


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- the session as rows ------------------------------------------------------------------------


def rows_of(p: Any, prompt: str = "$") -> list[list[tuple[str, int, int, str]]]:
    return [[(r.kind, r.step, r.line, r.text) for r in page] for page in session_pages(p.steps, prompt, p.language)]


def test_session_rows_pages_and_the_prompt_after_the_last_step() -> None:
    p = params(["ls", {"command": "cat a.txt", "output": "hello\n\n\tworld\n"}, {"command": "echo hi", "clear": True}])
    assert rows_of(p) == [
        [("command", 0, 0, "$ ls"), ("command", 1, 0, "$ cat a.txt"), ("output", 1, 0, "hello"), ("output", 1, 1, ""), ("output", 1, 2, "    world")],
        [("command", 2, 0, "$ echo hi"), ("end", 2, 0, "$")],
    ]
    first = session_pages(p.steps, "$", "bash")[0][0]
    assert first.typed_from == 2 and [t for t, _ in first.runs][:2] == ["$", " "]


def test_a_running_program_has_no_prompt_after_it_and_a_command_may_take_lines() -> None:
    p = params([{"command": "for f in *; do\n  echo $f\ndone"}, {"output": "Serving on :8000"}])
    assert rows_of(p, prompt="") == [[("command", 0, 0, "for f in *; do"), ("command", 0, 1, "  echo $f"), ("command", 0, 2, "done"), ("output", 1, 0, "Serving on :8000")]]
    assert rows_of(params(["ls"]), prompt="")[0][-1] == ("end", 0, 0, " ")   # the cursor's line keeps a space


# ----- params, targets, validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("steps", "changes", "message"),
    [([], {}, "at least 1 item"),
     ([{}], {}, "give a command, an output"),
     ([{"command": "  "}], {}, "command is empty"),
     ([{"command": "a", "clear": True}], {}, "steps[0].clear: the first step starts on an empty screen"),
     (["a"], {"language": "nosuch"}, "unknown language 'nosuch'"),
     (["a"], {"prompt": "a\nb"}, "prompt: one line only"),
     (["a"], {"typing_speed": 0}, "greater than 0"),
     (["a"], {"code": {"code": "x", "path": "a.py"}}, "exactly one of 'code'"),
     (["a"], {"code": {"code": "x", "highlight": 3}}, "highlight 3: the code has only 1 lines")],
)
def test_param_errors(steps: list[Any], changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("[", r"\[").replace("]", r"\]")):
        params(steps, **changes)


def test_targets_and_reveal_steps() -> None:
    cls = cls_of("terminal")
    p = params(["ls", {"command": "pytest", "output": "x\n\nValueError: bad"}, {"output": "more"}], title="T", code={"code": "a = 1\nb = 2"})
    assert cls.target_names(p) == ["title", "terminal", "code", "code.line1", "code.line2", "command1", "command2", "output2",
                                   "output2.line1", "output2.line3", "output3", "output3.line1"]   # a blank line is no target
    assert [(s.focus, s.result) for s in cls.reveal_steps(p)] == [("command1", None), ("command2", "error"), ("output3", None)]


def test_the_code_file_is_checked_in_the_project(make_project) -> None:
    spec = {"id": "t", "type": "terminal", "params": {"steps": ["python a.py"], "code": {"path": "a.py", "highlight": 3}}, "beats": [{"text": "run it"}]}
    root = make_project(minimal_config(scenes=[spec]))
    project = Project.load(root)
    assert any("code.path: file not found: a.py" in p for p in check_project(project))
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")
    assert any("code.path: highlight 3: the code has only 1 lines" in p for p in check_project(project))


# ----- rendering ----------------------------------------------------------------------------------


def terminal_scene(beats: list[dict[str, Any]], steps: list[Any] = STEPS, **params_: Any) -> dict[str, Any]:
    return {"id": "t", "type": "terminal", "params": {"steps": steps, **params_}, "beats": beats}


def window_texts(scene: Any) -> list[str]:
    return [m.lines_text.original_text for m in scene._frame.submobjects if isinstance(m, Paragraph)]


def show_plays(scene: Any, beat: str) -> list[Any]:
    return [p for p in scene.play_log if p.beat == beat and "_Show" in p.animations]


@pytest.mark.render
def test_commands_are_typed_and_outputs_shown_beat_by_beat(make_project, media: Path) -> None:
    beats = [{"text": "first we install the package"}, {"text": "then we run the tests"}]
    spec = terminal_scene(beats, title="Tests", code={"code": "a = 1\nprint(a)", "highlight": 2})
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [spec], **fmt), "t", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        assert [len(show_plays(scene, b)) for b in ("t_b1", "t_b2")] == [1, 1]
        assert all(scene.is_shown(n) for n in type(scene).target_names(scene.params))
        assert isinstance(scene._frame, Code) and scene._frame in scene.mobjects   # one listing, for the layout dump and lint
        assert window_texts(scene) == ["$", "pip install -e .", "ok", "$", "pytest -q", "..F", "1 failed, 2 passed", "$"]
        assert min(g.get_fill_opacity() for s in scene._all_segments() for g in s.glyphs) == pytest.approx(1)
        cursor = scene._cursor
        end = scene._segments[("end", 1, 0)][0].text
        assert cursor in scene.mobjects and cursor.get_fill_opacity() == pytest.approx(CURSOR_OPACITY)
        assert cursor.get_center()[1] == pytest.approx(end.get_center()[1], abs=0.1) and cursor.get_left()[0] > end.get_right()[0]
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.02), type(mob).__name__


@pytest.mark.render
def test_actions_type_a_command_and_show_an_output_on_their_words(make_project, media: Path) -> None:
    beats = [{"text": "we start with an install and wait until now", "actions": [{"reveal": "command1", "at": "@now"}]},
             {"text": "then we run the tests and watch how one of them fails, as we will see", "actions": [{"reveal": "output2", "at": "@fails"}]}]
    steps = [STEPS[0], {"command": "pytest -q", "output": "\n".join(f"test {k} ok" for k in range(10))}]   # 0.6 s of output
    scene = render(load(make_project, [terminal_scene(beats, steps, typing_speed=5)]), "t", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    start = {t.beat_id: t for t in scene.beat_log}
    first, typed = show_plays(scene, "t_b1")   # the window with its prompt, then the action's command
    assert first.start == pytest.approx(start["t_b1"].start, abs=0.01)
    assert typed.start - start["t_b1"].start > 0.7 * (start["t_b1"].end - start["t_b1"].start)
    # a reveal plays a command for its typing time (16 characters at 5 per second), not 0.8 s
    assert typed.end - typed.start >= 3.0 or typed.requested is not None
    own, shown = show_plays(scene, "t_b2")   # the scene types command 2; the action shows its output
    assert own.end < shown.start and shown.start - start["t_b2"].start > 0.6 * (start["t_b2"].end - start["t_b2"].start)
    assert window_texts(scene)[-2:] == ["test 9 ok", "$"]


@pytest.mark.render
def test_clear_starts_a_new_page_in_the_same_window(make_project, media: Path) -> None:
    steps = [*STEPS, {"command": "ls", "output": "a.py", "clear": True}]
    beats = [{"text": "one two three"}, {"text": "four five six"}, {"text": "seven eight nine"}]
    scene = render(load(make_project, [terminal_scene(beats, steps)]), "t", media)
    assert window_texts(scene) == ["$", "ls", "a.py", "$"]   # page 1 left with the clear
    assert scene._frame.height == pytest.approx(max(page.height for page in scene._pages), rel=0.03)
    assert not scene.is_shown("output1") and scene.is_shown("output3")
