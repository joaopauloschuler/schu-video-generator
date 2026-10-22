"""Step 191, the review of Phase S (DESIGN.md §93.13): a beat ends on its planned frame (the
caption offset of Step 189), holds across a section's end, ducking that follows the hit's
level, the threaded filter sweep (equal to the bit), the check's per-chord fit, lifts and risers,
a cue starting at a section, the lint check on the part a video plays, and pieces and beds by
name in ``vidgen music render`` / ``check``."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from manim import tempconfig

from conftest import minimal_config
from vidgen import cli, extensions, music, music_pieces
from vidgen.config import MusicCheckRule, MusicCue
from vidgen.errors import VidgenError
from vidgen.lint.music_rule import music_issues, played_bars
from vidgen.mcp_server import MUSIC_NAME
from vidgen.project import Project
from vidgen.render.worker import frame_size
from vidgen.sfx import RATE, _lowpass, read_wav
from vidgen.studio import check as chk
from vidgen.studio import effects as fx
from vidgen.studio import parse_music_score, render_music_score
from vidgen.studio import render as rnd
from vidgen.studio.templates import TEMPLATE_DIR
from vidgen.videoplan import VideoPlan


def _score(**extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"key": "A minor", "tempo": 120, "progression": "i VI III VII", "tracks": {}}
    data.update(extra)
    return data


# ----- a beat ends on its planned frame --------------------------------------------------------------


@pytest.mark.render
def test_a_beat_ends_on_its_planned_frame_after_an_odd_number_of_frames(make_project, tmp_path: Path) -> None:
    """Step 189's captions were 2-3 frames late: a beat's window of a half frame (here 22.5 frames:
    2 s of words + a 0.25 s pad at 10 fps) was rounded as the time left after the beat's
    animations (an odd 3 frames: 19.5 -> 20, 23 in all) while the plan rounds the window (22)."""
    from vidgen.scenes.text_card import TextCard

    class OddBeat(TextCard):
        def construct(self) -> None:
            for _ in self.narrate_all():
                self.wait_seconds(0.3)  # three frames at 10 fps

    words = "one two three four five six seven eight"  # 2 s at 4 words per second
    scenes = [{"id": "a", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": words}, {"text": words}]}]
    root = make_project(minimal_config(scenes=scenes, narration={"pad": 0.25, "words_per_second": 4.0}))
    project = Project.load(root)
    with extensions.project_session(project):
        slot = VideoPlan(project, 10).scene("a")
    assert [round(b.start * 10, 6) for b in slot.beats] == [0, 22]
    fw, fh = frame_size(160, 90)
    settings = {"pixel_width": 160, "pixel_height": 90, "frame_width": fw, "frame_height": fh, "frame_rate": 10, "media_dir": str(tmp_path / "media"),
                "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR", "output_file": "odd"}
    with tempconfig(settings):
        theme = extensions.activate(project)
        scene = OddBeat(project.scene("a"), project, theme)
        scene.render()
    starts = [round(t.start * 10, 6) for t in scene.beat_log]
    assert starts == [0, 22]  # was [0, 23]
    assert float(scene.renderer.time) == pytest.approx(slot.duration, abs=1e-6)


# ----- holds across a section's end ------------------------------------------------------------------


def test_a_hold_goes_on_into_the_next_section() -> None:
    lead = {"instrument": "soft_lead"}
    split = parse_music_score(_score(sections=[{"name": "a", "bars": 1}, {"name": "b", "bars": 1}],
                                     tracks={"lead": {**lead, "steps": "C5 - - -", "sections": {"b": {"steps": "- - - -"}}}}))
    whole = parse_music_score(_score(bars=2, tracks={"lead": {**lead, "steps": "C5 - - - | - - - -"}}))
    assert np.array_equal(render_music_score(split), render_music_score(whole))
    # round the loop's end: "- - C5 -" is "C5 - - -" two steps later
    wrapped = render_music_score(parse_music_score(_score(bars=1, tracks={"lead": {**lead, "steps": "- - C5 -"}})))
    plain = render_music_score(parse_music_score(_score(bars=1, tracks={"lead": {**lead, "steps": "C5 - - -"}})))
    shifted = np.roll(plain, len(plain) // 2, axis=0)  # (the loudness blocks fall elsewhere: compare the shapes)
    assert np.allclose(wrapped / np.abs(wrapped).max(), shifted / np.abs(shifted).max(), atol=1e-5)


def test_a_leading_hold_needs_a_note_before_it() -> None:
    one_pass = _score(loop=False, bars=2, tracks={"lead": {"instrument": "soft_lead", "steps": "- C5 - -"}})
    with pytest.raises(VidgenError, match=r"tracks\.lead\.steps: starts with '-' in section 'main', which starts the piece \(loop: false\)"):
        parse_music_score(one_pass)
    rests = _score(sections=[{"name": "a", "bars": 1}, {"name": "b", "bars": 1}],
                   tracks={"lead": {"instrument": "soft_lead", "steps": "- - C5 .", "rest": ["a"]}})
    with pytest.raises(VidgenError, match=r"the track rests in 'a' just before"):
        parse_music_score(rests)
    with pytest.raises(VidgenError, match="a gate pattern has no pitch|starts with '-'"):
        parse_music_score(_score(bars=1, tracks={"pad": {"instrument": "pad", "play": "chords", "gate": "- x"}}))


# ----- ducking that follows the hit ------------------------------------------------------------------


def test_duck_follow_scales_each_dip_by_the_hit() -> None:
    def gain(follow: bool) -> np.ndarray:
        score = parse_music_score(_score(bars=1, tracks={
            "kick": {"instrument": "kick", "steps": "X... x... o... x..."},
            "pad": {"instrument": "pad", "play": "chords", "duck": {"to": "kick", "depth": 0.4, "follow": follow}},
        }))
        tracks = {t.name: t for t in score.tracks}
        out = rnd._duck_gain(score, tracks["pad"], tracks)
        assert out is not None
        return 1 - out

    beat = RATE // 2
    plain, follows = gain(False), gain(True)
    deepest = [float(d[k * beat : (k + 1) * beat].max()) for d in (plain, follows) for k in range(4)]
    assert deepest[:4] == pytest.approx([deepest[0]] * 4)  # every hit as deep
    # (a dip's tail adds a little to the next one's)
    assert deepest[4] / deepest[5] == pytest.approx(1.5, rel=0.06) and deepest[6] / deepest[5] == pytest.approx(0.5, rel=0.06)
    with pytest.raises(VidgenError, match=r"duck\.follow: expected true or false"):
        parse_music_score(_score(bars=1, tracks={"kick": {"instrument": "kick", "steps": "x"},
                                                 "pad": {"instrument": "pad", "play": "chords", "duck": {"to": "kick", "follow": "yes"}}}))


# ----- the filter sweep: threaded, the same to the bit -----------------------------------------------


def _sweep_before(x: np.ndarray, cutoff: np.ndarray) -> np.ndarray:
    """``swept_filter`` (lowpass) as Steps 185-190 computed it."""
    spectrum = np.fft.rfft(x, axis=0)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    lo, hi = float(cutoff.min()), float(cutoff.max())
    count = math.ceil(2 * math.log2(hi / lo)) + 1
    position = np.log(cutoff / lo) / math.log(hi / lo) * (count - 1)
    out = np.zeros_like(x)
    for j, fc in enumerate(np.geomspace(lo, hi, count)):
        weight = np.clip(1 - np.abs(position - j), 0.0, 1.0)
        if weight.any():
            out += np.fft.irfft(spectrum * _lowpass(freqs, fc, 2)[:, None], len(x), axis=0) * weight[:, None]
    return out


def test_swept_filter_is_bit_identical_to_the_one_before() -> None:
    x = np.random.default_rng(5).standard_normal((3 * RATE, 2))
    cutoff = np.concatenate([np.full(RATE, 600.0), np.geomspace(600, 4000, RATE), np.full(RATE, 4000.0)])
    assert np.array_equal(fx.swept_filter(x, cutoff, "lowpass"), _sweep_before(x, cutoff))


# ----- the check: chords, lifts, risers --------------------------------------------------------------


def test_check_finds_a_line_that_clashes_with_one_chord() -> None:
    bell = ["A5 - - - C6 - - - | E5 - - - A5 - - -", "F#5 - - - C#6 - - - | G#5 - - - F#5 - - -",
            "G5 - - - E5 - - - | C6 - - - B5 - - -", "G5 - - - D5 - - - | B5 - - - G5 - - -"]
    tracks = {"pad": {"instrument": "pad", "play": "chords"}, "bell": {"instrument": "bell", "volume": 4, "steps": bell}}
    report = chk.check_music_score(parse_music_score(_score(tempo=100, chord_bars=2, bars=8, tracks=tracks)))
    key = next(f for f in report.findings if f.topic == "key")
    assert key.level == "fix" and "under the F at bar 3 (main)" in key.text and "`bell`" in key.text
    assert "F#" in key.fixes[0] and "F (F, A, C)" in key.fixes[0]
    assert report.facts["in_key"] > chk.LIMITS["in_key"]  # the whole piece is in key: only the chord check sees it
    tracks["bell"]["steps"] = [s.replace("F#", "F").replace("C#", "C").replace("G#", "A") for s in bell]
    fine = chk.check_music_score(parse_music_score(_score(tempo=100, chord_bars=2, bars=8, tracks=tracks)))
    assert next(f for f in fine.findings if f.topic == "key").level == "ok"


def test_check_lift_after_a_break_and_lift_advice_skips_build_only_parts() -> None:
    data = _score(
        progression="i VI III VII",
        sections=[{"name": "intro", "bars": 2}, {"name": "build", "bars": 4}, {"name": "break", "bars": 2}, {"name": "lift", "bars": 4}],
        tracks={
            "pad": {"instrument": "pad", "play": "chords", "sections": {"build": {"volume": 4}, "break": {"volume": -8}, "lift": {"volume": -3}}},
            "kick": {"instrument": "kick", "steps": "x... x... x... x...", "only": ["build", "lift"], "sections": {"lift": {"volume": -6}}},
            "arp": {"instrument": "pluck", "steps": "1358 5358 1358 5358", "volume": -2, "only": ["intro", "build"]},
            "riser": {"instrument": "riser", "only": ["build"], "steps": ". | . | x | -"},
        },
    )
    report = chk.check_music_score(parse_music_score(data))
    texts = [f.text for f in report.findings if f.topic == "sections"]
    assert any("the lift lifts" in t and "than the break" in t for t in texts)
    note = next(f for f in report.findings if f.level == "note" and f.topic == "sections")
    assert "quieter than the build before it" in note.text
    advice = " ".join(note.fixes)
    assert "`arp` (pluck) plays in the intro" in advice and "`riser`" not in advice


def test_check_build_advice_measures_a_quiet_riser() -> None:
    data = _score(
        sections=[{"name": "intro", "bars": 2}, {"name": "build", "bars": 4}],
        tracks={"pad": {"instrument": "pad", "play": "chords", "sections": {"build": {"volume": -3}}},
                "kick": {"instrument": "kick", "steps": "x... x... x... x..."},
                "riser": {"instrument": "riser", "only": ["build"], "steps": ". | . | x | -"}},
    )
    score = parse_music_score(data)
    fixes = chk._build_fixes(score, _stems_of(score), "build", (2 * score.bar, 6 * score.bar))
    assert any("`riser` sits" in f and "dB under the rest of the build's second half" in f and "riser.volume" in f for f in fixes)


def _stems_of(score: Any) -> Any:
    stems = chk._Stems(chk.frame_hop(score.seconds), chk.master_response(score.lowpass, score.highpass))
    kinds = {t.name: t.instrument.kind for t in score.tracks}
    rnd.render_music_stems(score, lambda name, sound: stems.add(name, sound, score.loop, kinds[name] != "drum"))
    return stems


# ----- a cue that starts at a section ----------------------------------------------------------------

SECTIONS = """key: A minor
tempo: 120
progression: "i VI"
sections: [{name: intro, bars: 2}, {name: lift, bars: 2}]
tracks:
  pad: {instrument: pad, play: chords}
"""


def _project(root: Path, music_setting: Any, n: int = 2) -> Project:
    (root / "assets" / "music").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "music" / "theme.yaml").write_text(SECTIONS, encoding="utf-8")
    scenes = [{"id": f"s{i}", "type": "title", "params": {"title": "x"}, "duration": 2.0} for i in range(n)]
    (root / "video.yaml").write_text(yaml.safe_dump({"title": "t", "scenes": scenes, "music": music_setting}), encoding="utf-8")
    return Project.load(root)


def test_a_cue_can_start_at_a_section(tmp_path: Path) -> None:
    project = _project(tmp_path, [{"source": "theme", "to": "s0"}, {"source": "theme", "from": "s1", "section": "lift", "start": 0.5}])
    assert music.config_problems(project.config, tmp_path) == []
    second = music.Source(project.config.music_cues[1], tmp_path)
    assert second.offset == round(4.5 * RATE)  # the lift starts at bar 3 = 4 s, plus start
    bed = music.Source(MusicCue(source="tidewater", section="lift"), tmp_path)
    lift = next(s for s in parse_music_score(yaml.safe_load((TEMPLATE_DIR / "tidewater.yaml").read_text(encoding="utf-8"))).sections if s.name == "lift")
    assert bed.offset == lift.first_bar * 26664 * 4
    bad = _project(tmp_path / "bad", [{"source": "theme", "section": "lfit", "to": "s0"}, {"source": "calm", "section": "lift", "from": "s1"}])
    problems = music.config_problems(bad.config, tmp_path / "bad")
    assert ("music[0].section", "theme has no section 'lfit'; did you mean 'lift'? (sections: intro, lift)") in problems
    assert any(where == "music[1].section" and "only a score file has sections" in text and "tidewater, skyline" in text for where, text in problems)
    assert music.Source(MusicCue(source="theme"), tmp_path).offset == 0  # no section: as before


# ----- lint: only the part the video plays -----------------------------------------------------------


def test_lint_reports_what_the_cue_plays(tmp_path: Path) -> None:
    project = _project(tmp_path, {"source": "theme", "loop": False})  # 4 s of an 8 s piece, played once
    report = music_pieces.piece_check(tmp_path / "assets" / "music" / "theme.yaml")
    assert played_bars(project, project.config.music_cues[0], report) == ({0, 1}, False)
    lift = {"topic": "sections", "level": "fix", "text": "the lift does not lift: ...", "fixes": []}
    seam = {"topic": "loop seam", "level": "fix", "text": "a click", "fixes": []}
    from vidgen.lint.music_rule import _heard

    assert not _heard(lift, report, {0, 1}, False) and not _heard(seam, report, {0, 1}, False)
    assert _heard(lift, report, {0, 1, 2, 3}, True)
    looped = _project(tmp_path / "l", {"source": "theme", "section": "lift"}, n=3)  # 6 s from the lift: round the seam
    bars, wraps = played_bars(looped, looped.config.music_cues[0], report)
    assert bars == {2, 3, 0} and wraps
    assert all("(the video plays bars 1-2 of its 4)" in m for m, _ in music_issues(project, "s0", MusicCheckRule(topics=["bass", "voice range", "sections"])))


# ----- names in vidgen music render / check ----------------------------------------------------------


def test_music_render_and_check_take_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _project(tmp_path, "theme")
    monkeypatch.chdir(tmp_path)
    assert music_pieces.music_source("theme", tmp_path) == ("piece", tmp_path / "assets" / "music" / "theme.yaml")
    assert music_pieces.music_source("skyline", tmp_path) == ("score bed", TEMPLATE_DIR / "skyline.yaml")
    assert music_pieces.music_source("pulse", tmp_path) == ("bed", None)
    with pytest.raises(VidgenError, match="did you mean 'theme'"):
        music_pieces.music_source("theem", tmp_path)
    assert cli.main(["music", "render", "theme", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["sections"][1]["name"] == "lift" and read_wav(tmp_path / "theme.wav").shape == (8 * RATE, 2)
    assert cli.main(["music", "render", "pulse", "--out", "p.wav"]) == 0
    assert "pulse: a built-in bed (its own code, not a score file)" in capsys.readouterr().out
    assert read_wav(tmp_path / "p.wav").shape == music.bed_loop("pulse").shape
    assert cli.main(["music", "check", "theme", "--out", "chk", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["kind"] == "score" and (tmp_path / "chk" / "theme-check.png").is_file()
    (tmp_path / "assets" / "music" / "pulse.yaml").write_text(SECTIONS, encoding="utf-8")
    assert cli.main(["music", "check", "pulse"]) == 1
    assert "is a built-in bed and also the project piece assets/music/pulse.yaml" in capsys.readouterr().err
    assert all(MUSIC_NAME.match(n) for n in ("theme", "themes/night", "tidewater")) and not any(
        MUSIC_NAME.match(n) for n in ("../x", "a.yaml", "/etc/x", "a/../b"))
