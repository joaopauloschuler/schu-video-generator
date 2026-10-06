"""Step 27 scene type ``timeline``: events along a horizontal (16:9) or vertical (9:16) axis,
revealed per beat with a growing progress line; spacing by date, ``now`` and ``highlight``."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from test_actions import beat_total, beats, plays, render
from test_builtin_scenes import cls_of, expected_duration, render_scene
from test_comparison_table import safe_area_of
from test_schema import errors
from vidgen import extensions, registry, schema
from vidgen.cli import check_project, project_problems
from vidgen.project import Project
from vidgen.scenes.timeline import date_position
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
SPACE = [
    {"date": 1957, "title": "Sputnik", "text": "First satellite in orbit", "icon": "satellite"},
    {"date": 1961, "title": "Gagarin", "text": "First human in space", "icon": "user"},
    {"date": 1969, "title": "Apollo 11", "icon": "moon"},
]
PLAN = [{"date": "Day 1", "title": "Draft"}, {"date": "Day 2", "title": "Review"}, {"date": "Day 3", "title": "Ship"}]


def load(make_project, scenes: list[dict[str, Any]]) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration=NARRATION)))


def params(**changes: Any) -> Any:
    return cls_of("timeline").validate_params({"events": SPACE, **changes}, Theme())


def three_beats() -> list[dict[str, str]]:
    return [{"text": "one two three four five six"}, {"text": "seven eight nine ten"}, {"text": "eleven twelve thirteen"}]


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


# ----- params ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("date", "expected"),
    [(1969, 1969.0), (2.5, 2.5), ("1969", 1969.0), (" -12.5 ", -12.5), ("2024-07", 2024 + 182 / 366),
     ("2023-01-01", 2023.0), ("2023-12-31", 2023 + 364 / 365), ("2024-13", None), ("Q3 2024", None), ("500 BC", None)],
)
def test_date_position(date: Any, expected: float | None) -> None:
    got = date_position(date)
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_params_defaults_dates_and_positions() -> None:
    p = params()
    assert (p.orientation, p.sides, p.spacing, p.reveal, p.now_label) == ("auto", "auto", "even", "per_beat", "Now")
    assert [e.shown() for e in p.events] == ["1957", "1961", "1969"]
    assert p.positions() == [0.0, 0.5, 1.0]
    assert params(spacing="proportional").positions() == pytest.approx([0.0, 4 / 12, 1.0])
    events = [{"date": datetime.date(2024, 3, 1), "title": "a"}, {"date": 3.0, "title": "b"}, {"date": "Later", "title": "c", "at": 9}]
    p = cls_of("timeline").validate_params({"events": events}, Theme())
    assert [e.shown() for e in p.events] == ["2024-03-01", "3", "Later"]   # YAML reads 2024-03-01 as a date
    assert [e.position() for e in p.events][1:] == [3.0, 9.0]


def test_events_are_referenced_by_index_date_or_title() -> None:
    p = params(highlight="Apollo 11", now="1961")
    assert p.event_index(p.highlight) == 2 and p.event_index(p.now) == 1
    assert p.event_index(0) == 0 and p.event_index(1969) == 2   # an int out of range is a date


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"events": SPACE[:1]}, "at least 2 items"),
        ({"events": SPACE * 4}, "at most 10 items"),
        ({"events": [{"date": "x", "title": ""}, SPACE[0]]}, "at least 1 character"),
        ({"events": [{"date": True, "title": "a"}, SPACE[0]]}, "True is not a date"),
        ({"events": [{"date": " ", "title": "a"}, SPACE[0]]}, "date must not be empty"),
        ({"events": [{"date": "1957", "title": "a", "colour": "red"}, SPACE[0]]}, "Extra inputs are not permitted"),
        ({"events": PLAN, "spacing": "proportional"}, r"needs a position for every event: events\[0\] \('Day 1'\)"),
        ({"events": SPACE[::-1], "spacing": "proportional"}, r"in time order; events\[1\] \('1961'\) comes before events\[0\]"),
        ({"highlight": "Vostok"}, "highlight: 'Vostok' is not an index"),
        ({"now": 7}, "now: 7 is not an index"),
        ({"events": [{"date": "x", "title": "a"}, {"date": "x", "title": "b"}], "highlight": "x"}, "names several events"),
        ({"orientation": "diagonal"}, "'auto', 'horizontal' or 'vertical'"),
        ({"sides": "both"}, "'auto', 'alternate' or 'one'"),
        ({"now_color": "nope"}, "unknown theme color 'nope'"),
    ],
)
def test_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(Exception, match=message):
        params(**changes)


def test_target_names() -> None:
    cls = cls_of("timeline")
    assert cls.target_names(params(heading="H")) == ["heading", "axis", "event1", "event:1957", "event2", "event:1961", "event3", "event:1969"]
    assert cls.target_names(params())[:2] == ["axis", "event1"]


def test_schema_accepts_numbers_and_text_as_dates() -> None:
    with registry.isolated():
        extensions.load_builtins()
        doc = schema.config_schema(registry.all(), [Theme()])
    scene = {"id": "t", "type": "timeline", "duration": 2}
    assert errors(doc, minimal_config(scenes=[{**scene, "params": {"events": SPACE, "highlight": 2, "now": "1961"}}])) == []
    assert errors(doc, minimal_config(scenes=[{**scene, "params": {"events": [{"date": [1], "title": "a"}, SPACE[0]]}}]))


def test_validate_checks_targets_and_params(make_project) -> None:
    scenes = [
        {"id": "t", "type": "timeline", "params": {"events": SPACE}, "beats": beats([{"highlight": "event:1961"}, {"dim": "axis"}], [{"zoom": "event:1970"}])},
    ]
    problems = project_problems(load(make_project, scenes))
    assert [p.location for p in problems] == ["scenes[0].beats[1].actions[0].target"]
    assert "unknown target 'event:1970' for scene type 'timeline'; did you mean" in problems[0].message and "'event:1969'" in problems[0].message
    root = make_project(minimal_config(scenes=[{"id": "a", "type": "timeline", "params": {"events": PLAN, "spacing": "proportional"}, "duration": 2}]))
    assert check_project(Project.load(root))[0].startswith("scenes[0].params: spacing: proportional needs a position")


def test_yaml_dates_load(make_project) -> None:
    """An unquoted YAML date (2024-03-15) is a date object: shown as written."""
    text = yaml.safe_dump(minimal_config(scenes=[{"id": "t", "type": "timeline", "duration": 2, "params": {"events": [
        {"date": "2024-03-15", "title": "a"}, {"date": "2024-06-01", "title": "b"}]}}]), sort_keys=False).replace("'2024-03-15'", "2024-03-15")
    root = make_project(minimal_config(scenes=[]))
    (root / "video.yaml").write_text(text, encoding="utf-8")
    p = Project.load(root).scene("t").params
    assert p["events"][0]["date"] == datetime.date(2024, 3, 15)
    assert [e.shown() for e in cls_of("timeline").validate_params(p, Theme()).events] == ["2024-03-15", "2024-06-01"]


# ----- rendering ------------------------------------------------------------------------------------


def parts(scene: Any) -> Any:
    return scene._drawing


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)])
@pytest.mark.parametrize(
    ("p", "timing"),
    [
        ({"heading": "The space race", "events": SPACE, "highlight": "Apollo 11"}, "three"),
        ({"events": SPACE, "spacing": "proportional", "now": 1}, "one"),
        ({"events": PLAN, "reveal": "all", "sides": "one"}, "three"),
        ({"events": PLAN[:2]}, "silent"),
        pytest.param({"heading": "Ten", "events": [{"date": f"Step {i}", "title": f"Event {i}", "text": "a short detail"} for i in range(1, 11)]}, "one", marks=pytest.mark.slow),
    ],
)
@pytest.mark.slow
def test_timeline_renders_within_its_beats_and_the_safe_area(p: dict[str, Any], timing: str, size: tuple[int, int], make_project, media: Path) -> None:
    extra = {"silent": {"duration": 2.0}, "one": {"beats": three_beats()[:1]}, "three": {"beats": three_beats()}}[timing]
    project = load(make_project, [{"id": "s", "type": "timeline", "params": p, **extra}])
    scene, duration, portrait = render_scene(project, "s", media, *size)
    assert portrait == (size[1] > size[0])
    axis = {round(float(m.get_center()[0 if portrait else 1]), 6) for m in parts(scene).markers}
    assert len(axis) == 1   # one horizontal axis in 16:9, one vertical in 9:16
    assert duration == pytest.approx(expected_duration(scene), abs=1.5 / FPS)
    assert all(scene.beat_busy[b] <= scene.beat_duration(b) + scene.pad + 1e-6 for b in scene.beat_busy)
    safe = safe_area_of(size)
    for t in scene.targets:
        assert safe.contains(t.mobject, tolerance=0.05), t.name


@pytest.mark.render
def test_events_alternate_sides_without_overlap_and_the_progress_line_grows(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "timeline", "params": {"events": SPACE}, "beats": three_beats()}])
    scene = render(project, "s", media)
    d = parts(scene)
    assert d.sides == [1, -1, 1]
    axis_y = d.track.get_y()
    assert d.cards[0].get_bottom()[1] > axis_y > d.cards[1].get_top()[1]   # above, below
    assert d.cards[0].get_right()[0] < d.cards[2].get_left()[0]            # same side: apart
    xs = [m.get_x() for m in d.markers]
    assert xs == sorted(xs) and all(abs(m.get_y() - axis_y) < 1e-6 for m in d.markers)
    for i, seg in enumerate(d.segments):   # each segment ends at its event's marker
        assert seg.get_end()[0] == pytest.approx(xs[i] - scene.radius, abs=1e-6)
    assert all(plays(scene, b.id) for b in scene.beats)   # one event per beat


@pytest.mark.render
@pytest.mark.slow
def test_vertical_axis_in_portrait_and_orientation_override(make_project, media: Path) -> None:
    project = load(make_project, [
        {"id": "v", "type": "timeline", "params": {"events": SPACE}, "beats": three_beats()},
        {"id": "h", "type": "timeline", "params": {"events": SPACE, "orientation": "horizontal"}, "beats": three_beats()},
    ])
    scene = render(project, "v", media, size=(90, 160))
    d = parts(scene)
    ys = [m.get_y() for m in d.markers]
    assert ys == sorted(ys, reverse=True) and len({round(m.get_x(), 6) for m in d.markers}) == 1   # top to bottom
    axis_x = d.markers[0].get_x()
    assert all((c.get_x() - axis_x) * side > 0 for c, side in zip(d.cards, d.sides))   # each on its side
    forced = render(project, "h", media, size=(90, 160))
    assert forced.horizontal and len({round(m.get_y(), 6) for m in parts(forced).markers}) == 1


@pytest.mark.render
def test_proportional_spacing_and_now(make_project, media: Path) -> None:
    events = [{"date": 2000, "title": "a"}, {"date": 2001, "title": "b"}, {"date": 2010, "title": "c"}, {"date": 2020, "title": "d"}]
    project = load(make_project, [{"id": "s", "type": "timeline", "params": {"events": events, "spacing": "proportional", "now": "c"}, "beats": three_beats()}])
    scene = render(project, "s", media)
    d = parts(scene)
    xs = [m.get_x() for m in d.markers]
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    assert gaps[0] < gaps[1] and gaps[2] == pytest.approx(gaps[1] * 10 / 9, rel=0.25)
    assert gaps[0] >= 2 * scene.radius + 0.2   # pulled apart to keep the markers apart
    assert [type(s).__name__ for s in d.segments] == ["Line", "Line", "Line", "DashedLine"]   # after now: planned
    tag = d.cards[2][0]
    assert any(getattr(m, "original_text", "") == "Now" for m in tag.get_family())
    assert len(d.markers[2]) == 2   # ring around the now marker (disc + ring, no icons)


@pytest.mark.render
def test_early_reveal_grows_the_line_but_not_the_skipped_event(make_project, media: Path) -> None:
    acts = beats([{"reveal": "event3"}], None, None)
    project = load(make_project, [{"id": "s", "type": "timeline", "params": {"events": SPACE}, "beats": acts}])
    scene = render(project, "s", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert scene.is_shown("event3") and scene.is_shown("event2")
    assert plays(scene, "s_b3") == []   # event 3 was on screen already
    seg_ids = [id(s) for s in parts(scene).segments]
    assert all(i in {id(m) for m in scene.mobjects} for i in seg_ids)


@pytest.mark.render
def test_highlight_step_dims_the_others(make_project, media: Path) -> None:
    project = load(make_project, [{"id": "s", "type": "timeline", "params": {"events": PLAN, "highlight": 1}, "beats": three_beats() + [{"text": "the end"}]}])
    scene = render(project, "s", media)
    d = parts(scene)
    highlight = scene.theme.color("highlight").lower()
    assert d.cards[1][1].get_color().to_hex().lower() == highlight
    assert max(m.get_fill_opacity() for m in d.cards[0].family_members_with_points()) == pytest.approx(scene.dimmed_opacity, abs=0.02)


@pytest.mark.render
@pytest.mark.slow
def test_too_many_events_for_the_frame_warn(make_project, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    text = "a long detail line that keeps going and going to fill the card with many words"
    events = [{"date": f"Phase {i}", "title": f"A rather long event title number {i}", "text": text} for i in range(1, 11)]
    project = load(make_project, [{"id": "s", "type": "timeline", "params": {"events": events}, "duration": 1.0}])
    with caplog.at_level(logging.WARNING):
        scene = render(project, "s", media, size=(90, 160))
    assert any("do not fit this frame at the readable size" in r.getMessage() and "split it into two timelines" in r.getMessage() for r in caplog.records)
    safe = safe_area_of((90, 160))
    assert all(safe.contains(t.mobject, tolerance=0.05) for t in scene.targets)
