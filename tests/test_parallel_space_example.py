"""examples/parallel-space (Step 355): the music film "Parallel Space" (v7) as an example, source
only, with its own audio data file (`ps_audio.json`, rebuilt by `scripts/make_ps_audio.py`).
Validate only: no render and no synthesis here (the README gives the render's cost)."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path

from vidgen import extensions
from vidgen.cli import validate_all
from vidgen.project import Project
from vidgen.studio import load_music_score
from vidgen.studio.render import range_warnings

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "parallel-space"
SCORE = EXAMPLE / "assets" / "music" / "parallel_space.yaml"
#: SHA-256 of the film's v7 score file (line ends as "\n"): the example plays the score unchanged.
SCORE_SHA256 = "b1c7286ddb67f587d4cb63af8b285de5cb0d03946a5b58ef844b33571b564893"
#: Where each scene starts, in bars of the song (one bar = 52 frames at 30 fps).
BAR_STARTS = [0, 8, 24, 32, 40, 56, 64, 72, 80, 88, 96]
BAR = Fraction(52, 30)


def test_the_example_is_source_only_and_validates() -> None:
    files = sorted(p.relative_to(EXAMPLE).as_posix() for p in EXAMPLE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    assert files == [".gitignore", "README.md", "assets/music/parallel_space.yaml", "extensions/ps.js",
                     "extensions/ps_audio.json", "extensions/webcut.py", "scripts/make_ps_audio.py", "video.yaml"]
    ignored = (EXAMPLE / ".gitignore").read_text(encoding="utf-8").split()
    assert {"build/", "output/", "*.wav", "*.mp4"} <= set(ignored)
    project = Project.load(EXAMPLE)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems
    with extensions.project_session(project):
        scenes = project.config.scenes
        assert [s.type for s in scenes] == ["web_cut"] * 11
        start = Fraction(0)
        for scene, bar in zip(scenes, BAR_STARTS):
            assert abs(start - bar * BAR) < Fraction(1, 1000), scene.id      # every scene starts on a bar line
            assert abs(scene.params["data"]["t0"] - float(bar * BAR)) < 1e-6, scene.id
            start += Fraction(scene.duration).limit_denominator(10**6)
        assert abs(float(start) - (104 * float(BAR) + 4.6)) < 1e-3        # 104 bars and 4.6 s for the last chord


def test_the_score_is_the_films_and_parses() -> None:
    text = SCORE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == SCORE_SHA256
    score = load_music_score(SCORE)
    assert range_warnings(score) == []
    assert len(score.tracks) == 30


def test_the_page_reads_the_shipped_audio_data() -> None:
    page = (EXAMPLE / "extensions" / "ps.js").read_text(encoding="utf-8")
    assert 'fetch(new URL("./ps_audio.json", import.meta.url))' in page
    data = json.loads((EXAMPLE / "extensions" / "ps_audio.json").read_text(encoding="utf-8"))
    assert data["fps"] == 30 and data["nbands"] == 16
    assert data["n"] >= 5546                                              # a value for every frame of the film
    assert len(data["bands"]) == data["n"] * data["nbands"]
    names = {t.name for t in load_music_score(SCORE).tracks}
    assert {"hook", "lead", "trumpet", "violins", "horn", "swell", "vla", "kick"} <= names   # what the script exports
