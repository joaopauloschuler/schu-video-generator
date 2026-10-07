"""Step 25 scene types: ``stat`` (a big number counting up, label, context, comparison) and
``chapter`` (a section divider), at 16:9 and 9:16."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_schema import errors
from vidgen import extensions, registry, schema
from vidgen.cli import check_project
from vidgen.project import Project
from vidgen.scenes.stat import MINUS, format_number, needed_decimals
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
TWO = [{"text": "one two three four five six"}, {"text": "seven eight nine ten"}]


# ----- formatting ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((1234567, 0), "1,234,567"),
        ((1234567, 0, ""), "1234567"),
        ((1234567.25, 2, " "), "1 234 567.25"),
        ((-12345.6, 1, ".", ","), f"{MINUS}12.345,6"),
        ((-0.004, 2), "0.00"),            # no "minus zero"
        ((0.5, 0), "0"),
        ((3, 2, "'"), "3.00"),
    ],
)
def test_format_number(args: tuple, expected: str) -> None:
    assert format_number(*args) == expected


def test_needed_decimals() -> None:
    assert needed_decimals([3, 4.0]) == 0
    assert needed_decimals([1, 2.5, 0.25]) == 2
    assert needed_decimals([0.123456]) == 2
    assert needed_decimals([0.123456], most=4) == 4


# ----- params ------------------------------------------------------------------------------------


def test_stat_params_and_comparison_shorthand() -> None:
    p = cls_of("stat").validate_params({"value": 3, "comparison": 12}, Theme())
    assert (p.comparison.value, p.comparison.kind, p.comparison.delta, p.comparison.better) == (12, "versus", "difference", "higher")
    p = cls_of("stat").validate_params({"value": 3, "comparison": {"value": 1.5, "kind": "before", "better": "lower"}}, Theme())
    assert p.comparison.kind == "before" and p.comparison.better == "lower"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"value": 1, "comparison": {"value": 0, "delta": "percent"}}, "delta: percent needs a non-zero value"),
        ({"value": 1, "thousands": ".", "decimal_mark": "."}, "thousands and decimal_mark are both '.'"),
        ({"value": 1, "thousands": "1"}, "cannot be digits"),
        ({"value": 1, "decimals": 7}, "less than or equal to 6"),
        ({"value": 1, "comparison": {"value": 2, "colour": "red"}}, "Extra inputs are not permitted"),
        ({"value": 1, "good_color": "grean"}, "unknown theme color 'grean'"),
        ({"value": 1, "icon": "no-such-icon"}, "unknown icon"),
        ({"label": "x"}, "value"),
    ],
)
def test_stat_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        cls_of("stat").validate_params(params, Theme())


def test_chapter_number_text() -> None:
    def text(**params: Any) -> str | None:
        return cls_of("chapter").validate_params({"title": "T", **params}, Theme()).number_text()

    assert text(number=2) == "02"
    assert text(number=2, number_format="{}") == "2"
    assert text(number=3, number_format="Part {}") == "Part 3"
    assert text(number="II") == "II"
    assert text() is None and text(number="") is None


@pytest.mark.parametrize(
    ("params", "message"),
    [({"title": ""}, "at least 1 character"), ({"title": "T", "number_format": "{:d"}, "invalid number format"), ({"number": 1}, "title")],
)
def test_chapter_params_errors(params: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        cls_of("chapter").validate_params(params, Theme())


def test_schema_accepts_a_number_or_a_mapping_as_comparison() -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    scene = {"id": "s", "type": "stat", "duration": 2}
    for comparison in (12, {"value": 12, "kind": "before", "delta": "percent"}):
        config = minimal_config(scenes=[{**scene, "params": {"value": 3, "comparison": comparison}}])
        assert errors(doc, config) == []
    bad = minimal_config(scenes=[{**scene, "params": {"value": 3, "comparison": {"value": 1, "kind": "after"}}}])
    assert errors(doc, bad)


def test_validate_reports_bad_stat_and_chapter_params(make_project) -> None:
    root = make_project(minimal_config(scenes=[
        {"id": "a", "type": "stat", "params": {"value": 1, "comparison": {"value": 0, "delta": "percent"}}, "duration": 2},
        {"id": "b", "type": "chapter", "params": {"title": "T", "number_color": "nope"}, "duration": 2},
    ]))
    problems = check_project(Project.load(root))
    assert problems[0].startswith("scenes[0].params.comparison: delta: percent needs a non-zero value")
    assert problems[1].startswith("scenes[1].params.number_color: unknown theme color 'nope'")


# ----- rendering ---------------------------------------------------------------------------------

STATS: dict[str, dict[str, Any]] = {
    "plain": {"value": 73, "suffix": "%"},
    "full": {"value": 1234567, "prefix": "$", "label": "saved per year", "context": "Finance report 2025", "icon": "banknote",
             "comparison": {"value": 2100000, "kind": "before", "delta": "percent", "better": "lower", "label": "last year"}},
    "unit": {"value": 12.5, "unit": "ms", "label": "median latency", "thousands": " ", "decimal_mark": ",", "comparison": 18},
    "long": {"value": 98765432.1, "decimals": 1, "unit": "requests", "label": "served in the first month of a deliberately long label that wraps",
             "comparison": {"value": 98765432.1, "delta": "difference", "label": "the same as before, a long comparison line"}},
    "fade": {"value": 42, "count": False, "label": "no count"},
}
CHAPTERS: dict[str, dict[str, Any]] = {
    "numbered": {"number": 2, "title": "Results", "subtitle": "What the benchmark shows", "icon": "chart-line"},
    "bare": {"title": "Why parameters matter"},
    "text_number": {"number": "Part II", "title": "Training at scale on a single small GPU and what it costs", "rule": False},
    "icon_only": {"icon": "rocket", "title": "Launch", "subtitle": "Going live"},
}


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    root = tmp_path_factory.mktemp("stat_chapter")
    scenes = [{"id": f"stat_{k}", "type": "stat", "params": v, "beats": TWO} for k, v in STATS.items()]
    scenes += [{"id": f"chapter_{k}", "type": "chapter", "params": v, "beats": TWO} for k, v in CHAPTERS.items()]
    scenes += [
        {"id": "stat_one", "type": "stat", "params": STATS["full"], "beats": TWO[:1]},
        {"id": "stat_silent", "type": "stat", "params": STATS["unit"], "duration": 2.5},
        {"id": "stat_many", "type": "stat", "params": STATS["plain"], "beats": TWO + TWO},
        # chapters must not repeat (DESIGN.md §42): the same card, numbered on
        {"id": "chapter_silent", "type": "chapter", "params": {**CHAPTERS["numbered"], "number": 3, "title": "Results, silent"}, "duration": 2.5},
        {"id": "chapter_one", "type": "chapter", "params": {**CHAPTERS["numbered"], "number": 4, "title": "Results, one beat"}, "beats": TWO[:1]},
    ]
    data = minimal_config(scenes=scenes, narration=NARRATION)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return Project.load(root)


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


SIZES = [(160, 90), (90, 160)]


@pytest.mark.render
@pytest.mark.parametrize("size", SIZES, ids=["landscape", "portrait"])
@pytest.mark.parametrize("scene_id", [f"stat_{k}" for k in STATS] + [f"chapter_{k}" for k in CHAPTERS]
                         + ["stat_one", "stat_silent", "stat_many", "chapter_silent", "chapter_one"])
@pytest.mark.slow
def test_renders_within_the_frame_and_the_beats(project: Project, media: Path, scene_id: str, size: tuple[int, int]) -> None:
    scene, duration, portrait = render_scene(project, scene_id, media, *size)
    assert portrait == (size[1] > size[0])
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert sorted(n for t in scene.targets for n in t.names) == sorted(type(scene).target_names(scene.params))
    area = scene.safe_area
    for t in scene.targets:
        assert area.contains(t.mobject, tolerance=0.02), f"{t.name} leaves the safe area"
    busy = scene.beat_busy
    for b in scene.beats:  # nothing runs past the narration (+ pad)
        assert busy[b.id] <= scene.beat_duration(b) + scene.pad + 1e-6
    assert scene.mobjects == []  # faded out


def value_text(scene: Any) -> str:
    """The number line as written (number text + unit)."""
    line = scene.find_targets("value")[0].mobject
    return " ".join(part.original_text for part in line)


@pytest.mark.render
def test_stat_counts_to_the_formatted_value(project: Project, media: Path) -> None:
    scene, *_ = render_scene(project, "stat_unit", media, 160, 90)
    assert value_text(scene) == "12,5 ms"
    assert scene.change() == (f"{MINUS}5,5 ms", "accent", -1)   # lower, but higher is better
    # the count, replayed: half-way it shows a number between start and end, with the same format
    (count,) = scene.entrance("value")
    count.begin()
    count.interpolate(0.5)
    middle = float(value_text(scene).split()[0].replace(",", "."))
    assert 0 < middle < 12.5 and value_text(scene).endswith(" ms")
    count.interpolate(1.0)
    assert value_text(scene) == "12,5 ms"


@pytest.mark.render
@pytest.mark.slow
def test_stat_before_comparison_counts_from_the_old_value(project: Project, media: Path) -> None:
    scene, *_ = render_scene(project, "stat_full", media, 160, 90)
    assert scene.start_value() == 2100000
    assert scene.change() == (f"{MINUS}41%", "tertiary", -1)    # better: lower -> good
    (count,) = scene.entrance("value")
    count.begin()
    count.interpolate(0.02)
    assert value_text(scene).startswith("$2,") and value_text(scene) != "$2,100,000"
    assert scene.written(2100000) == "$2,100,000"


@pytest.mark.render
@pytest.mark.slow
def test_stat_reveal_steps_follow_the_beats(project: Project, media: Path) -> None:
    """Beat 1: icon, value, label; beat 2: comparison and context; one beat: all in beat 1."""
    for scene_id, second in (("stat_full", "stat_full_b2"), ("stat_one", "stat_one_b1")):
        scene, *_ = render_scene(project, scene_id, media, 160, 90)
        plays = [p for p in scene.play_log if not p.wait and p.beat is not None]
        first = scene.beats[0].id
        assert plays[0].beat == first and "UpdateFromAlphaFunc" in plays[0].animations[0]
        assert plays[1].beat == second


@pytest.mark.render
@pytest.mark.slow
def test_stat_without_count_or_change_fades_in(project: Project, media: Path) -> None:
    scene, *_ = render_scene(project, "stat_fade", media, 160, 90)
    assert "UpdateFromAlphaFunc" not in " ".join(a for p in scene.play_log for a in p.animations)
    scene, *_ = render_scene(project, "stat_long", media, 160, 90)
    assert scene.change() == ("0.0 requests", "dim", 0)        # no change: neutral, no arrow
    chip = scene.find_targets("comparison")[0].mobject[0]
    assert len(chip) == 2   # pill + delta text, no arrow


@pytest.mark.render
@pytest.mark.parametrize("size", SIZES, ids=["landscape", "portrait"])
@pytest.mark.slow
def test_chapter_layouts(project: Project, media: Path, size: tuple[int, int]) -> None:
    scene, *_ = render_scene(project, "chapter_numbered", media, *size)
    number = scene.find_targets("number")[0].mobject
    title = scene.find_targets("title")[0].mobject
    icon = scene.find_targets("icon")[0].mobject
    if size[0] > size[1]:  # side by side: icon over number, title right of them
        assert title.get_left()[0] > number.get_right()[0] + 0.5
        assert icon.get_bottom()[1] > number.get_top()[1] - 0.05
    else:                 # stacked: icon, number, title top to bottom, centred
        assert icon.get_bottom()[1] > number.get_top()[1] - 0.05 > title.get_top()[1]
        assert abs(title.get_x() - number.get_x()) < 0.05
    plays = [p for p in scene.play_log if not p.wait]
    assert plays[0].beat == "chapter_numbered_b1" and plays[1].beat == "chapter_numbered_b2"   # subtitle in beat 2
    scene, *_ = render_scene(project, "chapter_one", media, *size)
    assert [p.beat for p in scene.play_log if not p.wait][:1] == ["chapter_one_b1"]
    assert len([p for p in scene.play_log if not p.wait and p.beat is not None]) == 1   # all in beat 1


@pytest.mark.render
def test_chapter_without_rule_never_draws_it(project: Project, media: Path) -> None:
    scene, *_ = render_scene(project, "chapter_text_number", media, 160, 90)
    assert "Create" not in scene.play_log[0].animations[0] and "GrowFromCenter" not in scene.play_log[0].animations[0]
    scene, *_ = render_scene(project, "chapter_bare", media, 160, 90)
    assert "GrowFromCenter" in scene.play_log[0].animations[0]   # stacked: the short rule grows
