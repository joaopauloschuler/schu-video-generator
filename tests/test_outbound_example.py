"""examples/outbound (Step 377): the short space film "Outbound", five `space` scenes written in YAML
alone with an original score, source only. Validate only: no render and no synthesis here (the README
gives the render's estimated cost)."""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction
from pathlib import Path

from vidgen import extensions, orbits
from vidgen.cli import validate_all
from vidgen.project import Project
from vidgen.studio import load_music_score
from vidgen.studio.render import range_warnings

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "outbound"
SCORE = EXAMPLE / "assets" / "music" / "outbound.yaml"
#: SHA-256 of the film's score file (line ends as "\n"): the example plays the score unchanged.
SCORE_SHA256 = "b6ec3697ac11f2e617a1e0d0aff83590e0ac6d1b66b35dad6031b2520f1d9c60"
#: Where each scene starts, in bars of the song from 0 (one bar = 96 frames at 30 fps).
BAR_STARTS = [0, 5, 8, 11, 12]
BAR = Fraction(96, 30)


def scenes() -> list:
    project = Project.load(EXAMPLE)
    with extensions.project_session(project):
        return list(project.config.scenes)


def test_the_example_is_source_only_and_validates() -> None:
    files = sorted(p.relative_to(EXAMPLE).as_posix() for p in EXAMPLE.rglob("*")
                   if p.is_file() and not {"__pycache__", "build", "output"} & set(p.relative_to(EXAMPLE).parts))
    assert files == [".gitignore", "README.md", "assets/music/outbound.yaml", "video.yaml"]
    ignored = (EXAMPLE / ".gitignore").read_text(encoding="utf-8").split()
    assert {"build/", "output/", "*.wav", "*.mp4"} <= set(ignored)
    project = Project.load(EXAMPLE)
    problems, _ = validate_all(project, keep_going=True)
    assert not problems, problems


def test_every_scene_is_a_space_scene_on_a_bar_line_with_no_code() -> None:
    start = Fraction(0)
    found = scenes()
    assert [s.type for s in found] == ["space"] * 5
    for scene, bar in zip(found, BAR_STARTS):
        assert start == bar * BAR, scene.id                              # every scene starts on a bar line
        assert "script" not in scene.params and scene.params["fade"] is False, scene.id
        assert scene.params["sky"] == {"seed": 7, "look": "rich"}, scene.id   # one sky for the film
        start += Fraction(scene.duration).limit_denominator(10**6)
    assert start == 18 * BAR                                             # 18 bars = 57.6 s
    first, last = found[0].params, found[-1].params
    assert first["camera"]["move"] == "reveal" and first["camera"]["at"] == "bar 4"      # the sunrise on the arrival
    assert "link" not in first["title"] and first["title"]["title"] == "Outbound"
    assert last["end_card"]["lines"] == ["made with schu-video-generator"]
    assert last["end_card"]["link"] == "https://github.com/joaopauloschuler/schu-video-generator"
    assert last["end_card"]["start"] == float(4 * BAR)                   # the end card on bar 17, four bars into its scene


def test_the_burn_and_the_fly_by_are_the_hohmann_transfers() -> None:
    depart, rings = scenes()[1].params, scenes()[2].params
    transfer = orbits.hohmann(orbits.GM_SUN, orbits.TABLE1["earth"][0][0] * orbits.AU, orbits.TABLE1["saturn"][0][0] * orbits.AU)
    ship = depart["orbits"]["bodies"][0]
    r = orbits.R_EARTH + 2_000_000.0
    assert ship["altitude"] == "2000 km"
    dv = math.sqrt(transfer.dv1 ** 2 + 2 * orbits.GM_EARTH / r) - math.sqrt(orbits.GM_EARTH / r)
    assert ship["burns"] == [{"at": "8 min", "prograde": "7.280 km/s"}] and abs(dv - 7280.0) < 1.0
    assert depart["orbits"]["speedup"] * float(BAR) == 8 * 60            # the burn falls on the scene's second bar line
    assert rings["orbits"]["flyby"]["v_inf"] == "5.44 km/s" and abs(transfer.dv2 - 5440.0) < 5.0


def test_the_score_is_the_films_and_parses() -> None:
    text = SCORE.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == SCORE_SHA256
    score = load_music_score(SCORE)
    assert range_warnings(score) == []
    assert len(score.tracks) == 17 and score.tempo == 75
    assert sum(s.bars for s in score.sections) == 18
    names = {t.name for t in score.tracks}
    for scene in scenes():
        assert set(scene.params["music_data"]["tracks"]) <= names
        assert {r["track"] for r in scene.params.get("music", [])} <= names
