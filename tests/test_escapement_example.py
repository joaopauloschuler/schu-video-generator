"""examples/escapement (Step 352): the published clockwork film "Escapement" as an example, source
only. Validate only: no render and no synthesis here (the README gives the render's cost; the
pictures were proved pixel-identical to the film's with `vidgen still`, HANDOFF Step 352)."""

from __future__ import annotations

import hashlib
import itertools
from pathlib import Path

from vidgen import extensions
from vidgen.cli import validate_all
from vidgen.project import Project
from vidgen.studio import load_music_score
from vidgen.studio.events import score_events
from vidgen.studio.render import range_warnings

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "escapement"
SCORE = EXAMPLE / "assets" / "music" / "escapement.yaml"
#: SHA-256 of the film's score file (line ends as "\n"): the example plays the published score unchanged.
SCORE_SHA256 = "55a4ff226666ac05dcea13c30a6189d86f8a9c54992e532595e77c9183802c38"
#: Where each scene starts in the song (seconds): every scene starts on a bar line (2 s at 120 BPM).
SONG_STARTS = [0, 16, 32, 48, 64, 80, 96, 112, 120, 136, 152, 168]


def test_the_example_is_source_only_and_validates() -> None:
    files = sorted(p.relative_to(EXAMPLE).as_posix() for p in EXAMPLE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    assert files == [".gitignore", "README.md", "assets/music/escapement.yaml", "extensions/escapement.js", "extensions/webcut.py", "video.yaml"]
    ignored = (EXAMPLE / ".gitignore").read_text(encoding="utf-8").split()
    assert {"build/", "output/", "*.wav", "*.mp4"} <= set(ignored)
    project = Project.load(EXAMPLE)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    with extensions.project_session(project):
        scenes = project.config.scenes
        assert [s.type for s in scenes] == ["web_cut"] * 12
        starts = [0, *itertools.accumulate(s.duration for s in scenes)][:-1]
        assert starts == SONG_STARTS
        assert sum(s.duration for s in scenes) == 191   # 94 bars and 3 s for the last chord


def test_the_score_is_the_films_and_parses_without_range_warnings() -> None:
    text = SCORE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == SCORE_SHA256
    score = load_music_score(SCORE)
    assert range_warnings(score) == []
    assert len(score.tracks) == 26 and round(score.seconds, 3) == 188.0
    events = score_events(score)
    assert len(events["tick"]) == 231 and len(events["three"]) == 48   # what the film's own exporter counted


def test_the_page_reads_the_music_through_ctx_music_only() -> None:
    page = (EXAMPLE / "extensions" / "escapement.js").read_text(encoding="utf-8")
    assert "ctx.music" in page and "fetch(" not in page and "escapement_audio" not in page
    names = {t.name for t in load_music_score(SCORE).tracks}
    for scene in Project.load(EXAMPLE).config.scenes:
        tracks = scene.params["music_data"]["tracks"]
        assert set(tracks) <= names
        for track in tracks:
            assert f'"{track}"' in page, track
        assert "t0" not in scene.params["data"]   # ctx.music.t0 is worked out by vidgen
