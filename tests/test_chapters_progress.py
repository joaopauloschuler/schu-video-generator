"""Chapters and the overlays reading them, Step 39 (DESIGN.md §42): the scene-level ``chapter:``
field and its checks, the chapter list of the planned timeline (``video_chapters``), the
``progress_bar`` and ``chapter_indicator`` overlays, overlays hidden on whole scenes
(``shown_in``) and drawing overlays with cropped cameras."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from manim import Camera, Square, Text, tempconfig

from conftest import minimal_config
from test_overlays import FPS, NARRATION, bullets, objects_of, render
from vidgen import extensions
from vidgen.api import video_chapters
from vidgen.chapters import chapter_marks, chapter_problems
from vidgen.config import ChapterConfig, SceneConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.overlay_layer import OverlayLayer
from vidgen.overlays import Overlay, scene_overlays
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.videoplan import VideoPlan


def card(sid: str, title: str, number: Any = None, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"title": title}
    if number is not None:
        params["number"] = number
    return {"id": sid, "type": "chapter", "params": params, "duration": 1.0, **extra}


def scenes_of(*specs: dict[str, Any]) -> list[SceneConfig]:
    return [SceneConfig.model_validate(s) for s in specs]


def load(make_project, scenes: list[dict[str, Any]], overlays: list[dict[str, Any]] | None = None) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, overlays=overlays or [], narration=NARRATION)))


def plan_of(project: Project) -> VideoPlan:
    """The plan with the project's scene types registered (their fade-out counts)."""
    extensions.activate(project)
    return VideoPlan(project, FPS)


#: 2 s intro (no chapter) | card "Setup" 1 s | bullets 2.2 s | bullets with chapter "Results" 2.2 s | bullets 2.2 s
VIDEO = [
    bullets("intro", beats=1),
    card("setup", "Setup", 1),
    bullets("a", beats=1),
    bullets("b", beats=1, chapter={"title": "Results", "number": 2}),
    bullets("c", beats=1),
]


# ----- config ----------------------------------------------------------------------------------------


def test_chapter_field_forms() -> None:
    assert SceneConfig.model_validate({"id": "a", "type": "t", "duration": 1, "chapter": "Results"}).chapter == "Results"
    long = SceneConfig.model_validate({"id": "a", "type": "t", "duration": 1, "chapter": {"title": "Results", "number": "II"}}).chapter
    assert long == ChapterConfig(title="Results", number="II")
    for bad in ("", {"number": 2}, {"title": "x", "subtitle": "y"}, {"title": "x", "number": ""}):
        with pytest.raises(ValueError):
            SceneConfig.model_validate({"id": "a", "type": "t", "duration": 1, "chapter": bad})


def test_chapter_marks_from_cards_and_fields() -> None:
    marks = chapter_marks(scenes_of(*VIDEO))
    assert [(m.title, m.number, m.scene, m.scene_index, m.card) for m in marks] == [
        ("Setup", "1", "setup", 1, True),
        ("Results", "2", "b", 3, False),
    ]
    # a card's own chapter field renames it (keeps the card's number unless given)
    renamed = chapter_marks(scenes_of(card("p", "A very long chapter title", 3, chapter="Short")))
    assert [(m.title, m.number, m.card) for m in renamed] == [("Short", "3", True)]
    assert chapter_marks(scenes_of(card("p", "T", "Part II", chapter={"title": "S", "number": 4})))[0].number == "4"


def test_chapter_problems() -> None:
    assert chapter_problems(scenes_of(*VIDEO)) == []
    twice = chapter_problems(scenes_of(card("p", "Setup", 1), bullets("a", beats=1), bullets("b", beats=1, chapter={"title": "setup", "number": 1})))
    assert len(twice) == 1 and "starts chapter 'setup' again" in twice[0] and "scene 'p'" in twice[0]
    down = chapter_problems(scenes_of(card("p", "A", 2), bullets("a", beats=1), card("q", "B", 1)))
    assert len(down) == 1 and "chapter number 1 after chapter number 2" in down[0]
    after_card = chapter_problems(scenes_of(card("p", "A"), bullets("a", beats=1, chapter="B")))
    assert len(after_card) == 1 and "right after the chapter card 'p'" in after_card[0]
    assert chapter_problems(scenes_of(card("p", "A"), card("q", "B"))) == []   # two cards in a row are two chapters
    assert chapter_problems(scenes_of(card("p", "Same"), bullets("a", beats=1), card("q", "Same", "x"))) == []   # numbers differ
    with pytest.raises(VidgenError, match="chapter number 1 after chapter number 2"):
        parse_config(minimal_config(scenes=[card("p", "A", 2), bullets("a", beats=1), card("q", "B", 1)]))


# ----- planned chapters ------------------------------------------------------------------------------


def test_plan_chapters_start_end_and_lookups(make_project) -> None:
    project = load(make_project, VIDEO)
    plan = plan_of(project)
    starts = {s.id: s.start for s in plan.scenes}
    chapters = plan.chapters
    assert [(c.title, c.label, c.scene, c.index, c.count, c.card) for c in chapters] == [
        ("Setup", "1", "setup", 1, 2, True),
        ("Results", "2", "b", 2, 2, False),
    ]
    assert chapters[0].start == pytest.approx(starts["setup"]) and chapters[0].end == pytest.approx(starts["b"])
    assert chapters[1].end == pytest.approx(plan.duration) and chapters[1].duration == pytest.approx(plan.duration - starts["b"])
    assert plan.chapter_of("intro") is None and plan.chapter_of("a") == chapters[0] and plan.chapter_of("c") == chapters[1]
    assert plan.chapter_at(0.5) is None and plan.chapter_at(starts["b"]) == chapters[1] and plan.chapter_at(starts["b"] - 0.01) == chapters[0]
    assert [s.chapter for s in plan.scenes] == [None, "Setup", "Setup", "Results", "Results"]
    # the public API: the final format's frame rate by default
    assert [c.title for c in video_chapters(project)] == ["Setup", "Results"]
    assert video_chapters(project, FPS) == chapters
    assert video_chapters(load(make_project, [bullets("x", beats=1)])) == ()


def test_unnumbered_chapters_count_by_position(make_project) -> None:
    project = load(make_project, [bullets("a", beats=1, chapter="Intro"), bullets("b", beats=1, chapter="Body")])
    # 2 s of speech + 0.2 s pad + the 0.5 s fade-out of bullets
    assert [(c.number, c.label, c.start) for c in video_chapters(project, FPS)] == [(None, "1", 0.0), (None, "2", pytest.approx(2.7))]


def test_fingerprint_sees_chapters_only_with_overlays(make_project) -> None:
    base = [bullets("a", beats=1), bullets("b", beats=1)]
    renamed = [bullets("a", beats=1), bullets("b", beats=1, chapter="Results")]
    plain = (load(make_project, base), load(make_project, renamed))
    assert scene_fingerprint(plain[0], "a") == scene_fingerprint(plain[1], "a")
    assert scene_fingerprint(plain[0], "b") == scene_fingerprint(plain[1], "b")   # no overlay reads it
    bar = [{"type": "chapter_indicator"}]
    with_overlay = (load(make_project, base, bar), load(make_project, renamed, bar))
    assert scene_fingerprint(with_overlay[0], "a") != scene_fingerprint(with_overlay[1], "a")


# ----- overlays: progress bar ------------------------------------------------------------------------


def built(project: Project, scene_id: str, size: tuple[int, int] = (320, 180)) -> list[Overlay]:
    """The overlays of a scene, built (as a render would) in a tiny frame."""
    from vidgen.render.worker import frame_size

    w, h = size
    fw, fh = frame_size(w, h)
    with tempconfig({"pixel_width": w, "pixel_height": h, "frame_width": fw, "frame_height": fh, "frame_rate": FPS}):
        theme = extensions.activate(project)
        overlays = scene_overlays(project, project.scene(scene_id), theme, VideoPlan(project, FPS))
        for o in overlays:
            o.built = o.build()  # type: ignore[attr-defined]
    return overlays


def test_progress_bar_fills_with_the_video_and_splits_at_chapters(make_project) -> None:
    project = load(make_project, VIDEO, [{"type": "progress_bar"}])
    plan = plan_of(project)
    (bar,) = built(project, "a")
    track, played = bar.built.submobjects  # type: ignore[attr-defined]
    assert len(track) == 3 and len(played) == 3   # split where the two chapters start
    columns = 320
    assert bar.state(0.0) == 0 and bar.state(plan.duration) == columns and bar.state(plan.duration / 2) == columns // 2
    assert all(bar.state(t) <= bar.state(t + 0.1) for t in np.arange(0, plan.duration, 0.1))
    # the same state on both sides of a cut: a pure function of video time
    (other,) = built(project, "b")
    cut = plan.scene_start("b")
    assert bar.state(cut) == other.state(cut)
    half = bar.pose(bar.built, bar.state(plan.duration / 2))  # type: ignore[attr-defined]
    assert half.submobjects[1].width < played.width * 0.6 and half.submobjects[0] is track
    assert bar.built.get_top()[1] == pytest.approx(4.0) and bar.built.width == pytest.approx(14.222, abs=0.01)  # type: ignore[attr-defined]


def test_progress_bar_options(make_project) -> None:
    project = load(make_project, VIDEO, [{"type": "progress_bar", "position": "bottom", "chapters": False, "track_opacity": 0}])
    (bar,) = built(project, "a")
    track, played = bar.built.submobjects  # type: ignore[attr-defined]
    assert len(track) == 0 and len(played) == 1
    assert played.get_bottom()[1] < 0


# ----- overlays: chapter indicator -------------------------------------------------------------------


def test_chapter_indicator_runs_fades_and_cards(make_project) -> None:
    project = load(make_project, VIDEO, [{"type": "chapter_indicator", "fade": 0.4}])
    plan = plan_of(project)
    start = {s.id: s.start for s in plan.scenes}
    end = {s.id: s.end for s in plan.scenes}
    # not drawn before the first chapter nor on the chapter card: left out of those renders
    assert built(project, "intro") == [] and built(project, "setup") == []
    (ind,) = built(project, "a")
    runs = [(r.start, r.end, r.chapter, r.joined_before, r.joined_after) for r in ind.runs]  # type: ignore[attr-defined]
    assert runs == [
        (pytest.approx(start["a"]), pytest.approx(end["a"]), 0, False, True),
        (pytest.approx(start["b"]), pytest.approx(end["c"]), 1, True, False),   # b and c merged
    ]
    assert ind.state(start["a"]) is None   # fades in after the card
    assert ind.state(start["a"] + 1.0) == ((0, 1.0),) and ind.settled(((0, 1.0),))
    mid = ind.state(start["b"])            # the chapter change: a cross-fade around the cut
    assert [c for c, _ in mid] == [0, 1] and all(0 < p < 1 for _, p in mid) and not ind.settled(mid)
    (on_b,) = built(project, "b")
    assert on_b.state(start["b"]) == mid and on_b.state(start["b"] - 0.1) == ind.state(start["b"] - 0.1)
    assert 0 < ind.state(end["c"] - 0.1)[0][1] < 1   # fades out at the end
    labels = ind.built.submobjects  # type: ignore[attr-defined]
    assert len(labels) == 2 and len(ind.pose(ind.built, mid).submobjects) == 2  # type: ignore[attr-defined]
    # on the cards too when asked
    shown = load(make_project, VIDEO, [{"type": "chapter_indicator", "on_chapter_cards": True}])
    assert len(built(shown, "setup")) == 1


def label_texts(overlay: Overlay) -> list[str]:
    """The labels' texts without their markup."""
    return [re.sub(r"<[^>]+>", "", label.original_text) for label in overlay.built.submobjects]  # type: ignore[attr-defined]


def test_chapter_indicator_text_and_shortening(make_project) -> None:
    long_title = "A chapter whose title goes on and on far beyond the corner of the frame"
    scenes = [bullets("a", beats=1, chapter="Setup"), bullets("b", beats=1, chapter={"title": long_title, "number": "II"})]
    (ind,) = built(load(make_project, scenes, [{"type": "chapter_indicator", "max_width": 0.3}]), "a")
    first, second = ind.built.submobjects  # type: ignore[attr-defined]
    texts = label_texts(ind)
    assert "1" in texts[0] and "Setup" in texts[0]
    assert "II" in texts[1] and "…" in texts[1] and long_title not in texts[1]
    assert second.width <= 0.3 * 14.23
    (total,) = built(load(make_project, scenes, [{"type": "chapter_indicator", "total": True, "corner": "bottom_right"}]), "a")
    assert "1/2" in label_texts(total)[0] and total.built.get_right()[0] > 0 and total.built.get_bottom()[1] < 0  # type: ignore[attr-defined]
    (bare,) = built(load(make_project, scenes, [{"type": "chapter_indicator", "number": False}]), "a")
    assert label_texts(bare)[0].strip() == "Setup"


def test_overlay_hidden_on_a_scene_reserves_nothing_there(make_project) -> None:
    """``shown_in``: an indicator hidden on the card is left out of its render (no reserve)."""
    project = load(make_project, VIDEO, [{"type": "chapter_indicator", "reserve": True}])
    assert built(project, "setup") == []
    assert len(built(project, "a")) == 1


# ----- drawing ---------------------------------------------------------------------------------------


def test_cropped_drawing_matches_the_whole_frame() -> None:
    """A patch drawn by a camera cropped to the overlay's box equals the whole-frame drawing."""
    with tempconfig({"pixel_width": 320, "pixel_height": 180, "frame_rate": FPS}):
        mob = Square(1.3).set_fill("#FF8800", opacity=0.6).set_stroke("#00FF00", width=5, opacity=0.8).move_to([-3.1, 1.7, 0])
        text = Text("Chapter 2", font_size=30, color="#FFFFFF").move_to([4.2, -3.6, 0])   # partly off the frame
        layer = OverlayLayer.__new__(OverlayLayer)
        layer.overlays, layer.mobjects, layer._cache, layer._camera = [Overlay.__new__(Overlay)] * 2, [mob, text], {}, None
        layer.following, layer.following_mobjects = [], []
        frame = np.zeros((180, 320, 4), dtype=np.uint8)
        frame[..., :3], frame[..., 3] = (20, 40, 90), 255
        out = layer.composite(frame, ("on", "on"))
        reference = Camera()
        reference.set_pixel_array(frame.copy())
        reference.capture_mobjects([mob, text])
        assert np.abs(out.astype(int) - reference.pixel_array.astype(int)).max() <= 2
        box = layer._patch(0, "on").box
        assert box is not None and (box[1] - box[0]) < 60 and (box[3] - box[2]) < 60   # only the square's pixels


@pytest.mark.render
def test_progress_and_indicator_render_across_a_cut(make_project, tmp_path: Path) -> None:
    """Rendered: the bar's played part grows between frames and continues across the cut; the
    layout dump has the indicator's label (settled at beat ends) and the bar."""
    scenes = [bullets("a", beats=1, chapter="Setup"), bullets("b", beats=1, chapter={"title": "Results", "number": 2})]
    project = load(make_project, scenes, [{"type": "progress_bar", "thickness": 0.02}, {"type": "chapter_indicator", "fade": 0.2}])
    media = tmp_path / "media"
    one = render(project, "a", media, per_beat=2)
    two = render(project, "b", media, per_beat=2)
    primary = np.array([0x58, 0xC4, 0xDD])

    def played(frame: np.ndarray) -> int:
        row = frame[1, :, :3].astype(int)
        return int(np.sum(np.abs(row - primary).max(axis=1) <= 12))

    first, last, next_first = played(one.frames_seen[0]), played(one.frames_seen[-1]), played(two.frames_seen[0])
    assert first < last <= next_first <= last + 3 and played(two.frames_seen[-1]) > 300
    labels = [o for o in objects_of(one.layout[-2], "chapter_indicator") if o["kind"] == "text"]
    assert labels and "Setup" in labels[0]["text"]
    assert objects_of(one.layout[-2], "progress_bar")
    assert {o["text"] for o in objects_of(two.layout[-2], "chapter_indicator") if o["kind"] == "text"} >= {"2 · Results"}


def test_both_in_portrait(make_project) -> None:
    project = load(make_project, VIDEO, [{"type": "progress_bar"}, {"type": "chapter_indicator", "reserve": True}])
    bar, ind = built(project, "a", size=(180, 320))
    assert bar.built.width == pytest.approx(8.0, abs=0.01)  # type: ignore[attr-defined]
    assert ind.built.get_left()[0] < -3.5 and ind.built.get_top()[1] > 6.5  # type: ignore[attr-defined]


def test_validate_reports_bad_options(make_project) -> None:
    from vidgen.cli import project_problems

    project = load(make_project, VIDEO, [{"type": "progress_bar", "position": "left"}, {"type": "chapter_indicator", "corner": "middle"}])
    found = {p.location for p in project_problems(project)}
    assert {"overlays[0].position", "overlays[1].corner"} <= found


@pytest.mark.render
@pytest.mark.slow
@pytest.mark.parametrize("reserve", [False, True])
def test_lint_overlay_overlap_and_reserve_with_a_chart_title(reserve: bool, make_project) -> None:
    """A big indicator over a chart's title is an ``overlay_overlap``; with ``reserve`` the
    title (laid out by ``chart_title`` in the scene's safe area) moves clear of it."""
    from vidgen.lint import RULES, lint_project

    chart = {
        "id": "s", "type": "bar_chart", "chapter": "Results and what they mean", "beats": [{"text": "one two three four"}],
        "params": {"title": "A title that spans the whole width of the frame", "labels": ["a", "b"], "values": [1, 2]},
    }
    overlays = [{"type": "chapter_indicator", "size": "title", "inset": 0.06, "reserve": reserve}, {"type": "progress_bar"}]
    root = make_project(minimal_config(scenes=[chart], overlays=overlays, narration=NARRATION, preview={"width": 320, "height": 180, "fps": FPS}))
    result = lint_project(Project.load(root), rules=[name for name, entry in RULES.items() if entry.scope == "still"])
    found = sorted({f.rule for f in result.findings})
    assert found == ([] if reserve else ["overlay_overlap"]), [f.message for f in result.findings]
