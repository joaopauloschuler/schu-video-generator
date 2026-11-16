"""examples/signal-fire (Step 351): the orchestral instruments, expressive notes, ``music_data``
and ``vidgen/three-finish`` together in one small project. Validate only: no render here (the
README gives the render's cost)."""

from __future__ import annotations

from pathlib import Path

from vidgen import extensions
from vidgen.cli import validate_all
from vidgen.project import Project
from vidgen.studio import load_music_score
from vidgen.studio.events import score_events
from vidgen.studio.render import range_warnings

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "signal-fire"


def test_the_example_is_source_only_and_validates() -> None:
    files = sorted(p.relative_to(EXAMPLE).as_posix() for p in EXAMPLE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    assert files == ["README.md", "assets/music/signal_fire.yaml", "extensions/signal_fire.js", "extensions/web_cut.py", "video.yaml"]
    project = Project.load(EXAMPLE)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    with extensions.project_session(project):
        assert [s.type for s in project.config.scenes] == ["web_cut"] * 3


def test_the_score_uses_the_new_instruments_and_marks_within_their_ranges() -> None:
    score = load_music_score(EXAMPLE / "assets" / "music" / "signal_fire.yaml")
    assert range_warnings(score) == []
    instruments = {t.instrument.name for t in score.tracks}
    assert {"violins", "cellos", "double_basses", "horn", "trumpet", "low_brass", "choir", "timpani", "taiko", "snare_drum", "cymbal",
            "tam_tam"} <= instruments
    events = score_events(score)
    assert any(e.slur for e in events["trumpet"]) and any(e.slur for e in events["solo"])
    assert {e.stroke for e in events["cellos"]} == {"tremolo", "spiccato", "sustain"}
    roll = [e for e in events["timpani"] if e.stroke == "roll"]
    assert len(roll) == 1 and roll[0].dynamic < roll[0].dynamic_end   # the roll grows into the hit
    assert round(score.seconds, 3) == 24.0


def test_the_page_reads_only_tracks_the_score_has_and_uses_the_finishing_module() -> None:
    page = (EXAMPLE / "extensions" / "signal_fire.js").read_text(encoding="utf-8")
    assert 'from "vidgen/three-finish"' in page and "ctx.music" in page
    project = Project.load(EXAMPLE)
    names = {t.name for t in load_music_score(EXAMPLE / "assets" / "music" / "signal_fire.yaml").tracks}
    for scene in project.config.scenes:
        tracks = scene.params["music_data"]["tracks"]
        assert set(tracks) <= names
        for track in tracks:
            assert f'"{track}"' in page, track
