"""Project pieces: score files in ``assets/music`` played like beds (Step 188, DESIGN.md §93.10):
names and conflicts, validation, ``vidgen list-music``, the mix (rendered at the join and
cached), the ``music_check`` lint rule."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import mix, music, music_pieces
from vidgen.cli import main, project_problems, validate_warnings
from vidgen.config import LINT_RULES, MusicCheckRule, MusicCue
from vidgen.errors import VidgenError
from vidgen.lint import RULES, SceneContext
from vidgen.lint.music_rule import music_issues
from vidgen.project import Project
from vidgen.sfx import RATE, read_wav, write_wav
from vidgen.studio import load_music_score

#: A tiny loop: 4 bars at 120 BPM = 8 s.
SMALL = """title: Small theme
description: a tiny test piece
key: A minor
tempo: 120
bars: 4
progression: "i VI"
chord_bars: 2
tracks:
  pad: {instrument: pad, play: chords}
  kick: {instrument: kick, steps: "x... x... x... x..."}
  bass: {instrument: synth_bass, steps: "1... ..1. 1... ..1."}
"""
#: The same as one pass with an ending.
ENDING = SMALL.replace("bars: 4\n", "bars: 2\nloop: false\n")
#: Loud piano and lead in the voice's range (the check flags it).
LOUD = """key: A minor
tempo: 100
bars: 4
progression: "i VI"
chord_bars: 2
tracks:
  pad: {instrument: pad, play: chords, volume: -6}
  piano: {instrument: piano, steps: "* . * . * . * .", octave: 4, volume: 4}
  lead: {instrument: soft_lead, volume: 8, steps: "A4 - - - C5 - - - | E5 - - - D5 - - -"}
"""


def _scenes(n: int = 2, seconds: float = 4.0) -> list[dict[str, Any]]:
    return [{"id": f"s{i}", "type": "title", "params": {"title": "x"}, "duration": seconds} for i in range(n)]


def _project(root: Path, music_setting: Any, pieces: dict[str, str] | None = None, n: int = 2) -> Project:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in (pieces if pieces is not None else {"small.yaml": SMALL}).items():
        path = root / "assets" / "music" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (root / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": _scenes(n), "music": music_setting}), encoding="utf-8")
    return Project.load(root)


def _timings(n: int = 2, seconds: float = 4.0) -> dict[str, Any]:
    return {"scenes": [{"id": f"s{i}", "start": seconds * i, "duration": seconds, "beats": []} for i in range(n)]}


def _wavs(root: Path, n: int = 2, seconds: float = 4.0) -> list[Path]:
    out = []
    for i in range(n):
        out.append(root / "padded" / f"s{i}.wav")
        write_wav(out[-1], np.zeros((round(seconds * RATE), 2)))
    return out


# ----- names ---------------------------------------------------------------------------------------


def test_sources_that_name_a_piece(tmp_path: Path) -> None:
    score = music_pieces.is_score_source
    assert score("my_theme") and score("themes/night") and score("assets/music/x.yaml") and score("x.YML")
    assert not score("momentum") and not score("assets/music/x.mp3") and not score("song.wav")
    (tmp_path / "raw").write_bytes(b"")  # an existing file without a suffix stays a file (as before)
    assert score("raw") and not score("raw", tmp_path)
    kinds = [music.source_kind(MusicCue(source=s), tmp_path) for s in ("calm", "small", "assets/music/a.yaml", "a.mp3", "raw")]
    assert kinds == ["bed", "score", "score", "file", "file"]
    (tmp_path / "assets" / "music" / "themes").mkdir(parents=True)
    for rel in ("b.yaml", "a.yml", "themes/night.yaml", "skip.mp3"):
        (tmp_path / "assets" / "music" / rel).write_text(SMALL, encoding="utf-8")
    assert list(music_pieces.project_pieces(tmp_path)) == ["a", "b", "themes/night"]
    assert music_pieces.piece_path("themes/night", tmp_path) == tmp_path / "assets" / "music" / "themes" / "night.yaml"
    assert music_pieces.piece_path("a", tmp_path).suffix == ".yml"
    with pytest.raises(VidgenError, match="did you mean 'themes/night'"):
        music_pieces.piece_path("themes/nigth", tmp_path)
    with pytest.raises(VidgenError, match="may not contain"):
        music_pieces.piece_path("../b", tmp_path)


def test_validate_reports_piece_problems(tmp_path: Path) -> None:
    bad = "key: H minor\ntempo: 500\nbars: 4\ntracks: {a: {instrument: pda}}\n"
    project = _project(tmp_path / "p1", [{"source": "smal", "to": "s0"}, {"source": "assets/music/bad.yaml", "from": "s1"}],
                       {"small.yaml": SMALL, "bad.yaml": bad})
    problems = [(p.location, p.message) for p in project_problems(project)]
    assert problems[0][0] == "music[0].source" and "did you mean 'small'?" in problems[0][1] and "project pieces: bad, small" in problems[0][1]
    assert "momentum, lab, ascent" in problems[0][1]
    rest = [m for loc, m in problems[1:] if loc == "music[1].source"]
    assert len(rest) == 3 and all(m.startswith("assets/music/bad.yaml: ") for m in rest)
    assert any("tracks.a.instrument: unknown instrument 'pda'; did you mean 'pad'?" in m for m in rest)
    assert any(m.startswith("assets/music/bad.yaml: tempo: 500") for m in rest)
    # a bed's name that is also a piece: which plays would be a guess
    clash = _project(tmp_path / "p2", "calm", {"calm.yaml": SMALL})
    [problem] = project_problems(clash)
    assert problem.location == "music.source" and "rename the piece" in problem.message and "source: assets/music/calm.yaml" in problem.message
    assert project_problems(_project(tmp_path / "p3", {"source": "assets/music/calm.yaml"}, {"calm.yaml": SMALL})) == []
    # Step 190: the beds written as score files are beds too (a copy of a template clashes)
    for bed in ("tidewater", "skyline", "time_of_flight"):  # time_of_flight since Step 192
        [problem] = project_problems(_project(tmp_path / f"p-{bed}", bed, {f"{bed}.yaml": SMALL}))
        assert "rename the piece" in problem.message and f"source: assets/music/{bed}.yaml" in problem.message
        assert music.source_kind(MusicCue(source=bed)) == "bed"
    # the pieces a video does not play are checked too, as warnings
    unused = _project(tmp_path / "p4", "small", {"small.yaml": SMALL, "bad.yaml": bad})
    assert project_problems(unused) == []
    [warning] = [w for w in validate_warnings(unused) if "bad.yaml" in w]
    assert "does not play" in warning and "key 'H minor'" in warning and "+2 more" in warning


def test_validate_summary_names_the_piece(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = _project(tmp_path, {"source": "small", "volume": -2})
    assert music.music_summary(project.config, project.root)[0]["kind"] == "score"
    assert main(["validate", str(tmp_path)]) == 0
    assert "music:     small, a project piece (score file, rendered at the join)" in capsys.readouterr().out


def test_list_music_lists_pieces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(music, "bed_loop", lambda name: np.zeros((RATE, 2), dtype=np.float32))  # the beds are tested elsewhere
    _project(tmp_path, "small", {"small.yaml": SMALL, "end.yaml": ENDING, "broken.yaml": "key: A minor\n"})
    assert main(["list-music", str(tmp_path), "--json"]) == 0
    items = {m["name"]: m for m in json.loads(capsys.readouterr().out)["music"]}
    small = items["small"]
    assert (small["origin"], small["path"], small["key"], small["tempo"], small["time"], small["bars"]) == ("score", "assets/music/small.yaml", "A minor", 120, "4/4", 4)
    assert small["loop"] and small["loop_seconds"] == 8.0 and small["duration"] is None and small["chords"] == ["Am", "F"]
    assert small["title"] == "Small theme" and small["description"] == "a tiny test piece" and small["problems"] == []
    assert items["end"]["loop"] is False and items["end"]["duration"] == 4.0 and items["end"]["loop_seconds"] is None
    assert items["broken"]["problems"] and items["broken"]["key"] is None
    assert main(["list-music", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "small  project piece  A minor, 120 BPM, 4/4, 4 bars, 8 s loop  (assets/music/small.yaml)" in out
    assert "description: Small theme - a tiny test piece" in out and "broken  project piece  assets/music/broken.yaml:" in out


# ----- playing -------------------------------------------------------------------------------------


def test_a_piece_plays_in_the_mix_and_is_cached(tmp_path: Path) -> None:
    project = _project(tmp_path, {"source": "small", "volume": -2})
    report = mix.mix_audio(project, _timings(), _wavs(tmp_path), None, tmp_path / "mix.wav")
    assert report.mixed and report.normalized and report.integrated_lufs == pytest.approx(-16, abs=0.5)
    assert report.music == [{"source": "small", "kind": "score", "from": "s0", "to": "s1", "start": 0.0, "end": 8.0, "volume": -2.0, "duck": 12.0}]
    [cached] = (tmp_path / "build" / "music").glob("piece-*.npy")
    music_pieces._rendered.cache_clear()
    again = mix.mix_audio(project, _timings(), _wavs(tmp_path), None, tmp_path / "mix2.wav")
    assert again.to_json() == report.to_json() and (tmp_path / "mix.wav").read_bytes() == (tmp_path / "mix2.wav").read_bytes()
    # an edit makes a new render; the samples are the studio's render, at the music level
    from vidgen.studio import load_music_score, render_music_score

    loop = render_music_score(load_music_score(tmp_path / "assets" / "music" / "small.yaml"))
    assert np.array_equal(np.load(cached), loop)
    (tmp_path / "assets" / "music" / "small.yaml").write_text(SMALL.replace("tempo: 120", "tempo: 121"), encoding="utf-8")
    mix.mix_audio(project, _timings(), _wavs(tmp_path), None, tmp_path / "mix3.wav")
    assert len(list((tmp_path / "build" / "music").glob("piece-*.npy"))) == 2
    assert read_wav(tmp_path / "mix3.wav").shape == read_wav(tmp_path / "mix.wav").shape


def test_loop_and_one_pass_sources(tmp_path: Path) -> None:
    _project(tmp_path, "small", {"small.yaml": SMALL, "end.yaml": ENDING})
    looped = music.Source(MusicCue(source="small", start=6), tmp_path)
    assert looped.seamless and looped.ends_at is None and looped.length == 8 * RATE
    assert np.array_equal(looped.read(0, RATE), looped.data[6 * RATE : 7 * RATE])
    assert np.array_equal(looped.read(2 * RATE, 3 * RATE), looped.data[:RATE])  # wraps round the loop
    once = music.Source(MusicCue(source="small", loop=False, start=9), tmp_path)  # start wraps, then one pass
    assert once.ends_at == 7 * RATE and not once.read(7 * RATE, 8 * RATE).any()
    ending = music.Source(MusicCue(source="assets/music/end.yaml"), tmp_path)  # a one-shot plays once, loop or not
    assert not ending.loop and ending.ends_at is not None and ending.ends_at > 4 * RATE  # its ending's tail
    with pytest.raises(VidgenError, match="past the end"):
        music.Source(MusicCue(source="end", start=30), tmp_path)


# ----- lint ----------------------------------------------------------------------------------------


def test_music_check_lint_rule(tmp_path: Path) -> None:
    assert LINT_RULES[-1] == "music_check" and RULES["music_check"].scope == "scene"
    project = _project(tmp_path, [{"source": "calm", "to": "s0"}, {"source": "loud", "from": "s1"}], {"loud.yaml": LOUD})
    assert music_issues(project, "s0", MusicCheckRule()) == []  # a bed is not checked
    issues = music_issues(project, "s1", MusicCheckRule())
    # the cue plays 4 s of the 9.6 s piece (Step 191: the part it plays is named)
    assert any("music piece assets/music/loud.yaml (voice range) (the video plays bars 1-2 of its 4):" in m and sev is None for m, sev in issues)
    assert all("vidgen music check assets/music/loud.yaml" in m for m, _ in issues)
    [cached] = (tmp_path / "build" / "music").glob("piece-*-check2.json")
    assert json.loads(cached.read_text(encoding="utf-8"))["verdict"].startswith("needs work")
    assert music_issues(project, "s1", MusicCheckRule(topics=["tempo"])) == []
    ctx = SceneContext("s1", {"fps": 5, "beats": []}, tmp_path, music_issues=issues)
    found = list(RULES["music_check"].check(ctx, MusicCheckRule()))
    assert len(found) == len(issues) and found[0].time == 0.0


# ----- the example (Step 189) ---------------------------------------------------------------------

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "gps-time-of-flight"


def test_the_gps_example_validates_with_its_bed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Step 192: the example's piece became the built-in bed ``time_of_flight``; the example plays
    the bed and keeps no project copy (which would clash with the bed's name)."""
    import shutil

    from vidgen.studio.templates import TEMPLATE_DIR

    assert not (EXAMPLE / "assets" / "music").exists()
    root = shutil.copytree(EXAMPLE, tmp_path / "gps", ignore=shutil.ignore_patterns("build", "output", "audio"))
    assert main(["validate", str(root)]) == 0
    assert "music:     time_of_flight" in capsys.readouterr().out
    project = Project.load(root)
    assert project_problems(project) == []
    assert music.source_kind(project.config.music, root) == "bed" and music.BUILTIN_BEDS["time_of_flight"].score
    score = load_music_score(TEMPLATE_DIR / "time_of_flight.yaml")
    assert [s.name for s in score.sections] == ["intro", "build", "lift", "settle"] and score.loop
    assert score.key.name == "B minor" and score.tempo == 108   # not the template's G minor at 120
    assert "music: time_of_flight" in (EXAMPLE / "video.yaml").read_text(encoding="utf-8")


@pytest.mark.slow
def test_the_gps_example_piece_is_fine_under_narration() -> None:
    from vidgen.studio import check_music_score
    from vidgen.studio.templates import TEMPLATE_DIR

    check = check_music_score(load_music_score(TEMPLATE_DIR / "time_of_flight.yaml"))
    assert [f.topic for f in check.findings if f.level != "ok"] == []
    assert [f.text.split(":")[0] for f in check.findings if f.topic == "sections"] == ["the build builds", "the lift lifts"]
