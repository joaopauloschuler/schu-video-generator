"""Chapters in the outputs, Step 49 (DESIGN.md §52): the published list (an intro chapter at
0:00), MP4 chapter entries and tags (FFMETADATA, read back with ffprobe), the YouTube list
``<output>_chapters.txt`` and its rules, ``chapters:`` / ``metadata:`` config, validate warnings."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from vidgen import chapter_export as ce
from vidgen.api import video_chapters
from vidgen.cli import validate_warnings
from vidgen.config import parse_config
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.videoplan import Chapter


def chapter(title: str, start: float, end: float, intro: bool = False, scene: str = "s") -> Chapter:
    return Chapter(title, None, scene, start, end, 0, 0, False, intro)


def card(sid: str, title: str, number: int, seconds: float, **extra: Any) -> dict[str, Any]:
    return {"id": sid, "type": "chapter", "params": {"title": title, "number": number}, "duration": seconds, **extra}


def text(sid: str, seconds: float, **extra: Any) -> dict[str, Any]:
    return {"id": sid, "type": "text_card", "params": {"text": sid}, "duration": seconds, **extra}


# ----- config ------------------------------------------------------------------------------------


def test_config_defaults_and_errors() -> None:
    config = parse_config(minimal_config())
    assert (config.chapters.metadata, config.chapters.youtube, config.chapters.intro) == (True, True, "Intro")
    assert parse_config(minimal_config(chapters={"intro": False})).chapters.intro is False
    assert parse_config(minimal_config(chapters={"intro": "Opening"})).chapters.intro == "Opening"
    for bad in ({"intro": True}, {"intro": ""}, {"youtub": False}):
        with pytest.raises(Exception, match="chapters"):
            parse_config(minimal_config(chapters=bad))
    with pytest.raises(Exception, match="autor"):
        parse_config(minimal_config(metadata={"autor": "x"}))


def test_video_tags() -> None:
    assert ce.video_tags(parse_config(minimal_config())) == {"title": "Test video"}
    tags = ce.video_tags(parse_config(minimal_config(metadata={"artist": "Jane", "title": "Other", "date": "2026"})))
    assert tags == {"title": "Other", "artist": "Jane", "date": "2026"}


def test_chapters_and_metadata_do_not_change_scene_fingerprints(make_project) -> None:
    base = Project.load(make_project(minimal_config(), folder="a"))
    changed = Project.load(
        make_project(minimal_config(chapters={"metadata": False, "intro": "Hi"}, metadata={"artist": "Jane"}), folder="b")
    )
    assert scene_fingerprint(base, "intro") == scene_fingerprint(changed, "intro")


# ----- the published list ------------------------------------------------------------------------


def test_published_chapters_start_at_zero() -> None:
    config = parse_config(minimal_config())
    later = [chapter("Setup", 4.5, 20.0), chapter("Results", 20.0, 40.0)]
    intro, setup, results = ce.published_chapters(config, later)
    assert (intro.title, intro.intro, intro.start, intro.end, intro.scene) == ("Intro", True, 0.0, 4.5, "intro")
    assert [(c.index, c.count) for c in (intro, setup, results)] == [(1, 3), (2, 3), (3, 3)]
    assert (setup.start, setup.intro) == (4.5, False)
    moved = ce.published_chapters(parse_config(minimal_config(chapters={"intro": False})), later)
    assert [(c.title, c.start) for c in moved] == [("Setup", 0.0), ("Results", 20.0)]
    at_zero = ce.published_chapters(config, [chapter("Setup", 0.0, 20.0), chapter("Results", 20.0, 40.0)])
    assert [c.title for c in at_zero] == ["Setup", "Results"]
    assert ce.published_chapters(config, []) == ()


def test_video_chapters_with_intro_follows_the_plan(make_project) -> None:
    scenes = [text("intro", 3.0), card("setup", "Setup", 1, 2.0), text("more", 1.0), text("data", 2.0, chapter="Data")]
    project = Project.load(make_project(minimal_config(scenes=scenes)))
    plain = video_chapters(project)
    assert [c.title for c in plain] == ["Setup", "Data"] and plain[0].start == pytest.approx(3.0)
    published = video_chapters(project, intro=True)
    assert [(c.title, c.intro) for c in published] == [("Intro", True), ("Setup", False), ("Data", False)]
    assert published[0].end == plain[0].start and published[1:] == tuple(
        Chapter(c.title, c.number, c.scene, c.start, c.end, c.index + 1, 3, c.card) for c in plain
    )


def test_chapter_json_round_trip() -> None:
    c = Chapter("A", "2", "s", 1.23456789, 5.0, 2, 3, True)
    data = ce.chapter_json(c)
    assert data == {"title": "A", "number": "2", "scene": "s", "start": 1.234568, "end": 5.0, "index": 2, "count": 3, "card": True, "intro": False}
    assert ce.chapter_from_json(json.loads(json.dumps(data))) == Chapter("A", "2", "s", 1.234568, 5.0, 2, 3, True)


# ----- FFMETADATA --------------------------------------------------------------------------------


def test_ffmetadata_escapes_and_times() -> None:
    text_ = ce.ffmetadata({"title": "A = b; #1", "comment": "one\ntwo\\"}, [chapter("Intro", 0.0, 1.2344), chapter("Two\nlines", 1.2344, 9.9996)])
    assert text_ == (
        ";FFMETADATA1\ntitle=A \\= b\\; \\#1\ncomment=one\\\ntwo\\\\\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1234\ntitle=Intro\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1234\nEND=10000\ntitle=Two lines\n"
    )


# ----- YouTube -----------------------------------------------------------------------------------


def test_youtube_times_round_down() -> None:
    assert [ce.youtube_time(t) for t in (0.0, 9.999, 10.0, 59.9, 61.5, 600.0, 3599.99, 3600.0, 3725.2)] == [
        "0:00", "0:09", "0:10", "0:59", "1:01", "10:00", "59:59", "1:00:00", "1:02:05",
    ]


def test_youtube_list_and_rules() -> None:
    good = [chapter("Intro", 0, 12.4, intro=True), chapter("Setup\nand data", 12.4, 30), chapter("Results", 30, 41)]
    assert ce.youtube_list(good) == "0:00 Intro\n0:12 Setup and data\n0:30 Results\n"
    assert ce.youtube_problems(good) == []
    assert ce.youtube_problems([]) == []
    (few,) = ce.youtube_problems(good[1:])
    assert "2 chapter(s)" in few and "at least 3" in few
    # timestamps count whole seconds: 0:12 -> 0:22 is 10 s on YouTube (9.9 s in the video), 0:12 -> 0:21 is 9 s
    fine = [chapter("Intro", 0, 12.4, intro=True), chapter("Setup", 12.4, 22.3), chapter("Results", 22.3, 41)]
    assert ce.youtube_problems(fine) == []
    short = [chapter("Intro", 0, 12.4, intro=True), chapter("Setup", 12.4, 21.9), chapter("Results", 21.9, 41)]
    (problem,) = ce.youtube_problems(short)
    assert problem.startswith("chapters: 'Setup' (0:12-0:21) lasts 9.0 s") and "merge it" in problem
    # a short intro says how to avoid it
    brief = [chapter("Intro", 0, 3.0, intro=True), chapter("Setup", 3.0, 20), chapter("Results", 20, 41)]
    (problem,) = ce.youtube_problems(brief)
    assert "'Intro' (0:00-0:03) lasts 3.0 s" in problem and "chapters: {intro: false}" in problem
    last = [chapter("A", 0, 20), chapter("B", 20, 40), chapter("C", 40, 45.5)]
    (problem,) = ce.youtube_problems(last)
    assert "'C' (0:40-0:45) lasts 5.5 s" in problem


def test_validate_warns_about_the_youtube_list(make_project) -> None:
    scenes = [text("intro", 3.0), card("setup", "Setup", 1, 12.0), card("more", "More", 2, 12.0)]
    project = Project.load(make_project(minimal_config(scenes=scenes), folder="a"))
    warnings = [w for w in validate_warnings(project) if w.startswith("chapters:")]
    assert len(warnings) == 1 and "'Intro' (0:00-0:03)" in warnings[0]
    quiet = Project.load(make_project(minimal_config(scenes=scenes, chapters={"youtube": False}), folder="b"))
    assert not [w for w in validate_warnings(quiet) if w.startswith("chapters:")]
    moved = Project.load(make_project(minimal_config(scenes=scenes, chapters={"intro": False}), folder="c"))
    (warning,) = [w for w in validate_warnings(moved) if w.startswith("chapters:")]
    assert "2 chapter(s)" in warning
    none = Project.load(make_project(minimal_config(), folder="d"))
    assert not [w for w in validate_warnings(none) if w.startswith("chapters:")]


# ----- rendered ----------------------------------------------------------------------------------

#: 10 fps: the scenes' durations and fade-outs are whole frames, so the plan equals the render.
FPS = 10


def ffprobe(path: Path) -> dict[str, Any]:
    exe = shutil.which("ffprobe")
    assert exe is not None
    out = subprocess.run(
        [exe, "-v", "error", "-show_chapters", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(out.stdout)


@pytest.mark.render
@pytest.mark.slow
def test_rendered_chapters_metadata_and_youtube_list(make_project, caplog: pytest.LogCaptureFixture) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg / ffprobe not found on PATH")
    from vidgen.render.pipeline import render_project

    scenes = [
        text("intro", 1.6),
        card("setup", "Setup", 1, 1.2, transition={"type": "crossfade", "duration": 0.4}),
        text("data", 1.0),
        text("results", 1.4, chapter="Results = done; #1"),
    ]
    config = minimal_config(
        output="out",
        preview={"width": 160, "height": 90, "fps": FPS},
        scenes=scenes,
        metadata={"artist": "Jane Doe", "comment": "line one\nline two"},
        variants={"plain": {"chapters": {"metadata": False, "youtube": False}}, "nointro": {"chapters": {"intro": False}}},
    )
    root = make_project(config)
    project = Project.load(root)
    with caplog.at_level(logging.WARNING, logger="vidgen"):
        result = render_project(project, preview=True, no_audio=True)
    planned = video_chapters(project, fps=FPS, intro=True)
    assert [c.title for c in planned] == ["Intro", "Setup", "Results = done; #1"]
    assert planned[1].start == pytest.approx(1.2)  # the crossfade starts the card 0.4 s early

    # MP4: one chapter per planned chapter, starting within a frame (to the millisecond here)
    info = ffprobe(result.output)
    got = [(float(c["start_time"]), float(c["end_time"]), c["tags"]["title"]) for c in info["chapters"]]
    assert [title for _, _, title in got] == [c.title for c in planned]
    for (start, end, _), c in zip(got, planned):
        assert abs(start - c.start) <= 0.0015 and abs(start - c.start) < 1 / FPS
        assert abs(end - c.end) <= 0.0015
    assert got[-1][1] == pytest.approx(result.duration, abs=0.0015)
    tags = info["format"]["tags"]
    assert (tags["title"], tags["artist"], tags["comment"]) == ("Test video", "Jane Doe", "line one\nline two")

    # timings.json and the YouTube list
    timings = json.loads(result.timings_file.read_text(encoding="utf-8"))
    assert [ce.chapter_from_json(c).title for c in timings["chapters"]] == [c.title for c in planned]
    assert result.chapters == root / "out_preview_chapters.txt"
    assert result.chapters.read_text(encoding="utf-8") == "0:00 Intro\n0:01 Setup\n0:03 Results = done; #1\n"
    youtube = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chapters:")]
    assert len(youtube) == 3 and all("shorter than 10 s" in m for m in youtube)

    # a variant writes its own files; with both outputs off: no chapters, tags still, an old list removed
    plain = Project.load(root, variant="plain")
    stale = root / "out_plain_preview_chapters.txt"
    stale.write_text("old\n", encoding="utf-8")
    result = render_project(plain, preview=True, no_audio=True)
    info = ffprobe(result.output)
    assert info["chapters"] == [] and info["format"]["tags"]["title"] == "Test video"
    assert result.chapters is None and not stale.exists()
    timings = json.loads(result.timings_file.read_text(encoding="utf-8"))
    assert len(timings["chapters"]) == 3  # still listed in the timings

    nointro = Project.load(root, variant="nointro")
    result = render_project(nointro, preview=True, no_audio=True)
    assert result.chapters == root / "out_nointro_preview_chapters.txt"
    assert result.chapters.read_text(encoding="utf-8") == "0:00 Setup\n0:03 Results = done; #1\n"
    assert [float(c["start_time"]) for c in ffprobe(result.output)["chapters"]][0] == 0.0
