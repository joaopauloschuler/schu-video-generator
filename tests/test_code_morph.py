"""Step 158: the ``code_morph`` scene type (a listing that morphs from one version of the code to
the next: kept tokens glide, new lines grow in, removed lines fade out), its diff
(``diff_code``, difflib), its params and targets, and tiny renders timed to a beat and to a word."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_actions import beat_total, plays, render
from test_builtin_scenes import cls_of
from test_comparison_table import safe_area_of
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.scenes.code_morph import code_tokens, diff_code
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
SLOW = "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
CACHED = "from functools import cache\n\n@cache\ndef fib(n: int) -> int:\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"


def params(versions: list[Any], **changes: Any) -> Any:
    return cls_of("code_morph").validate_params({"versions": versions, **changes}, Theme())


def load(make_project, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides)))


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- the diff -----------------------------------------------------------------------------------


def test_tokens_are_words_and_single_characters() -> None:
    assert code_tokens("    return fib(n - 1)  # hi") == ["return", "fib", "(", "n", "-", "1", ")", "#", "hi"]


def test_an_unchanged_listing_keeps_every_glyph() -> None:
    lines = SLOW.rstrip("\n").split("\n")
    diff = diff_code(lines, lines)
    assert diff.lines == {0: 0, 1: 1, 2: 2, 3: 3} and diff.changed == diff.removed == diff.added == []
    assert len(diff.glyphs) == sum(len(line.replace(" ", "")) for line in lines)


def test_an_edited_line_keeps_its_shared_tokens() -> None:
    diff = diff_code(["def fib(n):", "    return n"], ["def fib(n: int) -> int:", "    return n"])
    assert diff.lines == {0: 0, 1: 1} and diff.changed == [0] and diff.added == diff.removed == []
    kept = [(a, b) for i, a, j, b in diff.glyphs if i == 0]
    # "def", "fib", "(", "n" keep glyphs 0-7 in place; ")" (8) and ":" (9) find the ones after "int"
    assert kept[:8] == [(k, k) for k in range(8)]
    assert (8, 12) in kept and (9, 18) in kept


def test_added_removed_and_reindented_lines() -> None:
    old = ["a = 1", "b = 2", "print(a)", "x = 0"]
    new = ["a = 1", "for k in range(3):", "    print(a)", "c = 3"]
    diff = diff_code(old, new)
    assert diff.lines == {0: 0, 2: 2}          # print(a) re-indented: kept (it glides), but changed
    assert diff.removed == [1, 3] and diff.added == [1, 3] and diff.changed == [1, 2, 3]
    assert [(a, b) for i, a, j, b in diff.glyphs if i == 2] == [(k, k) for k in range(8)]


def test_a_line_moved_elsewhere_glides() -> None:
    diff = diff_code(["a = 1", "b = 2", "c = 3", "d = 4"], ["b = 2", "c = 3", "d = 4", "a = 1"])
    assert diff.lines == {0: 3, 1: 0, 2: 1, 3: 2} and diff.changed == [3]
    assert diff.removed == diff.added == []


def test_unlike_lines_in_a_changed_block_are_not_paired() -> None:
    diff = diff_code(["x = compute()"], ["print('hello world')"])
    assert diff.lines == {} and diff.removed == [0] and diff.added == [0] and diff.glyphs == []


# ----- params, targets, validation -----------------------------------------------------------------


def test_versions_as_strings_or_mappings() -> None:
    p = params([SLOW, {"code": CACHED, "highlight": "changed"}, {"code": "x = 1", "highlight": [1]}])
    assert [v.code for v in p.versions][:2] == [SLOW, CACHED] and p.versions[1].highlight == "changed"


@pytest.mark.parametrize(
    ("versions", "message"),
    [([SLOW], "at least 2 items"),
     ([SLOW, SLOW + "\n"], "versions[1] is the same code as versions[0]"),
     ([SLOW, {"code": "x = 1", "highlight": "2"}], "versions[1].highlight '2': version 2 has only 1 lines"),
     ([SLOW, {"code": "x = 1", "highlight": "changd"}], "invalid line spec 'changd'"),
     ([SLOW, {"code": "x", "path": "a.py"}], "exactly one of 'code'")],
)
def test_param_errors(versions: list[Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("[", r"\[").replace("]", r"\]")):
        params(versions)


def test_targets_and_reveal_steps() -> None:
    cls = cls_of("code_morph")
    p = params(["a = 1\nb = 2", {"code": "a = 1\nraise ValueError('bad')\nb = 2"}], title="T")
    names = cls.target_names(p)
    assert names[:4] == ["title", "listing", "version1", "version2"]
    assert names[4:] == ["version1.line1", "version1.line2", "version2.line1", "version2.line2", "version2.line3"]
    steps = cls.reveal_steps(p)
    assert [s.focus for s in steps] == ["version1", "version2"] and steps[1].result == "error"


def test_files_are_checked_in_the_project(make_project) -> None:
    spec = {"id": "m", "type": "code_morph", "params": {"versions": [{"path": "v1.py"}, {"path": "v2.py", "highlight": "4"}]},
            "beats": [{"text": "one"}, {"text": "two"}]}
    root = make_project(minimal_config(scenes=[spec]))
    project = Project.load(root)
    assert any("versions[0].path: file not found: v1.py" in p for p in check_project(project))
    (root / "v1.py").write_text("a = 1\n", encoding="utf-8")
    (root / "v2.py").write_text("a = 2\n", encoding="utf-8")
    assert any("versions[1].highlight '4': version 2 has only 1 lines" in p for p in check_project(project))
    (root / "v2.py").write_text("a = 1\n", encoding="utf-8")
    assert any("versions[1] is the same code as versions[0]" in p for p in check_project(project))


# ----- rendering ----------------------------------------------------------------------------------


def morph_scene(beats: list[dict[str, Any]], **params_: Any) -> dict[str, Any]:
    return {"id": "m", "type": "code_morph", "params": {"versions": [SLOW, {"code": CACHED, "highlight": "changed"}], **params_}, "beats": beats}


@pytest.mark.render
def test_morph_at_the_beat_ends_with_the_new_listing(make_project, media: Path) -> None:
    spec = morph_scene([{"text": "the slow one"}, {"text": "now with a cache"}], title="Fib")
    for size, fmt in (((160, 90), {}), ((90, 160), {"format": {"width": 1080, "height": 1920}})):
        scene = render(load(make_project, [spec], **fmt), "m", media, size=size)
        assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
        assert plays(scene, "m_b2")[0][0].startswith("_Morph(")
        assert scene.is_shown("version2") and not scene.is_shown("version1")
        shown = scene.get_mobject_family_members()
        assert scene._listings[1] in shown and scene._listings[0] not in shown   # one Code again, for the layout dump
        dim = [m.get_fill_opacity() for m in scene.find_targets("version2.line5")[0].mobject.family_members_with_points()]
        full = [m.get_fill_opacity() for m in scene.find_targets("version2.line4")[0].mobject.family_members_with_points()]
        assert max(dim) == pytest.approx(0.35) and min(full) == pytest.approx(1)   # highlight: changed
        for mob in scene.mobjects:
            assert safe_area_of(size).contains(mob, tolerance=0.02), type(mob).__name__


@pytest.mark.render
def test_a_reveal_action_morphs_on_its_word(make_project, media: Path) -> None:
    beats = [{"text": "the slow one"}, {"text": "now we add a cache to it", "actions": [{"reveal": "version2", "at": "@cache"}]}]
    scene = render(load(make_project, [morph_scene(beats)]), "m", media)
    morphs = [p for p in scene.play_log if p.beat == "m_b2" and any(a.startswith("_Morph(") for a in p.animations)]
    assert len(morphs) == 1   # the action's, not also the beat's own step
    beat2 = next(t for t in scene.beat_log if t.beat_id == "m_b2")
    assert morphs[0].start - beat2.start > 0.4 * (beat2.end - beat2.start)   # "cache" is the 5th of 6 words
    assert scene.is_shown("version2")
