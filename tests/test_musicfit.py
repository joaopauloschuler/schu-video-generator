"""Composed music that follows the video (Step 148): the section plan from the timings (bar lines
at scene changes, tempo limits, holds, short scenes), per-scene moods, swells, pauses, the
closing cadence, the config, the mix and the stings played by the music's instruments. No
rendering, except one real render skipped without symusic 0.5.9 and a SoundFont."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

from vidgen import composer, loudness, mix, music, musicfit, sfx, synth
from vidgen.config import VideoConfig
from vidgen.musicfit import TEMPO_LIMIT, Pause, Settings, Slot, fit_music, plan_sections
from vidgen.project import Project
from vidgen.score import Score
from vidgen.sfx import RATE, SfxEvent
from vidgen.soundfont import default_path

HAS_SYMUSIC = synth.symusic_version() == synth.SYMUSIC_VERSION
CURIOUS, TENSE, SLEEPY = Settings("curious"), Settings("tense"), Settings("sleepy")


def _sections(changes: list[float], seconds: float, settings: list[Settings] | None = None) -> tuple[musicfit.FitSection, ...]:
    chosen = settings or [CURIOUS] * len(changes)
    return plan_sections([Slot(f"s{k}", at, s) for k, (at, s) in enumerate(zip(changes, chosen))], seconds)


def _section_beats(sections: tuple[musicfit.FitSection, ...]) -> list[float]:
    beats, at = [], 0.0
    for section in sections:
        beats.append(at)
        at += section.beats
    return beats


# ----- the section plan ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "seconds"),
    [([0.0, 7.3, 15.0, 27.9], 41.2), ([0.0, 4.1, 9.9, 12.4, 20.0], 25.0), ([0.0, 30.0], 33.0), ([0.0], 9.0), ([0.0, 2.6, 5.1, 7.7], 10.4)],
)
def test_every_scene_change_falls_on_a_bar_line(changes: list[float], seconds: float) -> None:
    sections = _sections(changes, seconds)
    score = fit_music(sections).score
    assert score.length_seconds == pytest.approx(seconds, abs=1e-6)
    planned = {s.scenes[0]: s.start for s in sections}
    for section, beat in zip(sections, _section_beats(sections)):
        assert beat % section.meter == 0
        assert score.seconds_at(beat) == pytest.approx(section.start, abs=1e-6)  # a bar line
    assert set(planned) == {f"s{k}" for k in range(len(changes))}  # no scene too short here
    assert all(planned[f"s{k}"] == at for k, at in enumerate(changes))


def test_tempo_stays_within_the_limit_and_holds_beyond_it() -> None:
    sections = _sections([0.0, 7.3, 15.0, 27.9], 41.2)
    for s in sections:
        assert -TEMPO_LIMIT - 1e-9 <= s.tempo_change <= TEMPO_LIMIT + 1e-9
    first = sections[0]  # 7.3 s at 108 BPM: 3 bars need -8.7 %, 4 bars +22 %: 3 bars at -8 % and a hold
    assert first.bars == 3 and first.tempo == pytest.approx(108 * (1 - TEMPO_LIMIT))
    held = first.stretch[-first.meter :]
    assert all(s > 1 for s in held) and list(held) == sorted(held) and all(s == 1 for s in first.stretch[: -first.meter])
    assert sum(first.stretch) * 60 / first.tempo == pytest.approx(7.3)
    middle = sections[2]  # 12.9 s: 6 bars at +7.3 % (5 bars would be -10.6 %)
    assert middle.bars == 6 and middle.tempo_change == pytest.approx(6 * 2.2222222 / 12.9 - 1, abs=1e-4) and set(middle.stretch) == {1.0}


def test_a_scene_shorter_than_a_bar_shares_bars_with_the_next() -> None:
    sections = _sections([0.0, 5.0, 6.1, 12.0], 20.0)  # s1 lasts 1.1 s, a bar is 2.2 s
    assert [s.scenes for s in sections] == [("s0",), ("s1", "s2"), ("s3",)]
    last_short = _sections([0.0, 9.0, 18.0], 19.5)  # the last scene cannot hold the closing bar
    assert [s.scenes for s in last_short] == [("s0",), ("s1", "s2")]
    assert _sections([0.0], 1.0)[0].bars == 1  # a cue shorter than a bar: one fast bar


def test_the_piece_closes_with_a_cadence_slowing_into_a_held_tonic() -> None:
    sections = _sections([0.0, 8.0], 20.0)
    last = sections[-1]
    meter = last.meter
    assert last.stretch[-meter:] == (musicfit.CLOSE_STRETCH,) * meter
    rit = last.stretch[-2 * meter : -meter]
    assert list(rit) == sorted(rit) and rit[0] > 1  # a ritardando in the bar before
    piece = fit_music(sections)
    score, total = piece.score, piece.score.length_beats
    parts = {p.name: p for p in score.parts}
    key = composer.parse_key("F major", False)
    final = total - meter
    melody = [n for n in parts["melody"].notes if n.start >= final]
    assert len(melody) == 1 and melody[0].pitch % 12 == key.tonic and melody[0].length == meter
    chords = [n for n in parts["chords"].notes if n.start >= final]
    assert {n.start for n in chords} == {final} and {n.pitch % 12 for n in chords} <= {5, 9, 0}  # F major held
    assert [n.pitch for n in parts["drums"].notes if n.start >= final] == [36, 49]
    assert "hold" in [s.name for s in score.sections]  # the slower beats are tempo changes of the score


def test_composer_endings() -> None:
    loop = composer.compose_piece("curious", bars=8)
    assert loop.chords[-1] == ("F", "C7")  # Step 147's loop bar unchanged
    closed = composer.compose_piece("curious", bars=7, ending="cadence")
    assert closed.bars == 7 and closed.chords[-1] == ("F",) and closed.chords[-2][-1] in ("C", "C7")
    opened = composer.compose_piece("tense", bars=3, ending="open")
    assert opened.chords[-1] == ("Dm",) and opened.score.length_beats == 12
    with pytest.raises(composer.VidgenError, match="ending 'fade'"):
        composer.compose_piece("calm", bars=4, ending="fade")


# ----- moods per scene, swells, pauses -------------------------------------------------------------


def test_a_scenes_mood_starts_at_its_first_bar() -> None:
    sections = _sections([0.0, 10.0, 22.0], 32.0, [CURIOUS, TENSE, CURIOUS])
    score = fit_music(sections).score
    starts = _section_beats(sections)
    names = [p.name for p in score.parts]
    assert "melody" in names and "melody 2" in names
    tense = [p for p in score.parts if p.name.endswith(" 2")]
    assert tense and all(starts[1] <= n.start < starts[2] for p in tense for n in p.notes)
    clarinet = next(p for p in score.parts if p.name == "melody 2")
    assert clarinet.program == composer.INSTRUMENTS["clarinet"].program and min(n.start for n in clarinet.notes) == starts[1]
    flute = next(p for p in score.parts if p.name == "melody")
    assert not [n for n in flute.notes if starts[1] <= n.start < starts[2]]  # the curious parts rest, then return
    assert [n for n in flute.notes if n.start >= starts[2]]
    waltz = _sections([0.0, 10.0], 25.0, [CURIOUS, SLEEPY])
    assert [s.meter for s in waltz] == [4, 3]
    assert fit_music(waltz).score.seconds_at(waltz[0].beats) == pytest.approx(10.0)


def test_each_moods_key_and_time_signature_reach_the_midi_export() -> None:
    sections = _sections([0.0, 10.0, 22.0], 32.0, [CURIOUS, SLEEPY, TENSE])
    score = fit_music(sections).score
    starts = _section_beats(sections)
    marked = [(s.start, s.key, s.time_signature) for s in score.sections if s.key is not None]
    assert marked == [(starts[0], "F major", (4, 4)), (starts[1], "F major", (3, 4)), (starts[2], "D minor", (4, 4))]
    if not HAS_SYMUSIC:
        return
    from vidgen.score import TICKS_PER_BEAT, to_symusic

    midi = to_symusic(score)
    assert [(t.time, t.numerator) for t in midi.time_signatures] == [(0, 4), (starts[1] * TICKS_PER_BEAT, 3), (starts[2] * TICKS_PER_BEAT, 4)]
    assert [(k.time, k.key, k.tonality) for k in midi.key_signatures] == [(0, -1, 0), (starts[2] * TICKS_PER_BEAT, -1, 1)]


def test_swells_on_reveals() -> None:
    sections = _sections([0.0], 20.0)
    plain, swelled = fit_music(sections), fit_music(sections, reveals=[0.1, 6.0, 6.5, 19.0])
    tempo_map = swelled.tempo_map
    beat = float(round(tempo_map.beat_at(6.0)))
    assert swelled.swells == (beat,)  # 0.1 s: too early; 6.5 s: too close; 19 s: in the closing bar
    before = {(p.name, n.start, n.pitch): n.velocity for p in plain.score.parts for n in p.notes}
    after = {(p.name, n.start, n.pitch): n.velocity for p in swelled.score.parts for n in p.notes}
    louder = [k for k in before if k in after and after[k] > before[k]]
    assert louder and all(beat - musicfit.SWELL_BEATS <= k[1] < beat + 1 for k in louder)
    added = set(after) - set(before)  # the held note on the reveal, in the pad / chords part
    assert len(added) == 1 and next(iter(added))[1] == beat and next(iter(added))[0] == "chords"


def test_a_pause_before_the_punchline_until_the_next_bar_line() -> None:
    sections = _sections([0.0, 8.0], 22.0)
    music_ = fit_music(sections, pauses=[Pause(9.5, 12.0)])
    (a, b), = music_.pauses
    tempo_map = music_.tempo_map
    assert tempo_map.seconds_at(a) <= 9.5 - musicfit.PAUSE_LEAD + 1e-9 and a == int(a)
    assert b in musicfit._bar_lines(sections) and tempo_map.seconds_at(b) >= 12.0 - 1e-9
    for part in music_.score.parts:
        assert not [n for n in part.notes if a <= n.start < b] and all(n.end <= a + 1e-9 for n in part.notes if n.start < a <= n.end + 1e-9)
        assert [n for n in part.notes if n.start >= b] or part.name == "pad"  # it comes back
    late = fit_music(sections, pauses=[Pause(20.5, 22.0)]).pauses  # into the closing chord: it still plays
    assert late == () or late[0][1] == music_.score.length_beats - sections[-1].meter


def test_fitted_scores_differ_when_the_timings_do() -> None:
    first = fit_music(_sections([0.0, 8.0], 20.0)).score
    assert first.fingerprint() == fit_music(_sections([0.0, 8.0], 20.0)).score.fingerprint()
    assert first.fingerprint() != fit_music(_sections([0.0, 8.4], 20.0)).score.fingerprint()  # the render cache key


# ----- the config and the project ------------------------------------------------------------------


def _video(**extra: Any) -> dict[str, Any]:
    scenes = [
        {"id": "intro", "type": "title", "params": {"title": "x"}, "beats": [{"text": "One two three."}]},
        {"id": "list", "type": "bullets", "params": {"items": ["a", "b"]}, "beats": [{"text": "First."}, {"text": "Second.", "actions": [{"reveal": "item2", "at": 0.5}]}]},
        {"id": "storm", "type": "title", "params": {"title": "y"}, "music": {"mood": "tense"}, "beats": [{"text": "Rain.", "sting": "reveal"}]},
        {"id": "gag", "type": "card", "params": {"text": "Later"}, "beats": [{"text": "Much later."}]},
        {"id": "end", "type": "title", "params": {"title": "z"}, "beats": [{"text": "A long closing line here."}, {"text": "The end, short."}]},
    ]
    return {"title": "t", "music": {"compose": "curious"}, "scenes": scenes, **extra}


#: Each beat's speech (seconds); every scene ends 0.7 s after its last line.
_LINES = {"intro": [3.0], "list": [3.0, 4.0], "storm": [5.0], "gag": [3.0], "end": [4.0, 3.0]}
TOTAL = 28.5


def _timings() -> dict[str, Any]:
    scenes, at = [], 0.0
    for sid, beats in _LINES.items():
        entries, t = [], at
        for k, d in enumerate(beats):
            entries.append({"id": f"{sid}_b{k + 1}", "start": t, "end": t + d})
            t += d
        scenes.append({"id": sid, "start": at, "duration": t + 0.7 - at, "beats": entries})
        at = t + 0.7
    scenes[2]["sfx"] = [{"time": scenes[2]["start"], "sound": "sting_reveal", "duck": True}]
    scenes[1]["transition"] = {"type": "crossfade", "duration": 0.5, "overlap": 0.5}
    return {"scenes": scenes}


def _load(tmp_path: Path, video: dict[str, Any]) -> Project:
    root = tmp_path / "p"
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(video), encoding="utf-8")
    return Project.load(root)


def test_cue_inputs_from_the_config_and_timings(tmp_path: Path) -> None:
    project = _load(tmp_path, _video())
    cue = project.config.music_cues[0]
    slots, reveals, pauses = musicfit.cue_inputs(project, _timings(), cue, 0, 4, 0.0, TOTAL)
    assert [s.scene for s in slots] == ["intro", "list", "storm", "gag", "end", "end (end)"]
    assert [s.start for s in slots] == pytest.approx([0.0, 3.95, 11.4, 17.1, 20.8, 27.8])  # list: mid-crossfade
    assert [s.settings.mood for s in slots] == ["curious", "curious", "tense", "curious", "curious", "curious"]
    assert [s.button for s in slots] == [False] * 5 + [True]  # the closing chord after the last line
    # bullets reveal an item in each beat; the written reveal half-way through beat 2; the sting
    assert sorted(reveals) == pytest.approx([3.7, 6.7, 8.7, 11.4])
    # automatic: before the card (until its first line ends) and before the short last line
    assert [t for p in pauses for t in (p.start, p.end)] == pytest.approx([17.1, 20.1, 24.8, 27.8])
    video = _video()
    video["scenes"][3]["beats"][0]["music_pause"] = False
    video["scenes"][4]["beats"][1]["music_pause"] = False
    video["scenes"][0]["beats"][0]["music_pause"] = True
    slots, _, pauses = musicfit.cue_inputs(_load(tmp_path / "b", video), _timings(), cue, 0, 4, 0.0, TOTAL)
    assert pauses == [Pause(0.0, 3.0)] and not slots[-1].button


def test_the_last_line_ends_on_the_closing_chord() -> None:
    slots = [Slot("a", 0.0, CURIOUS), Slot("b", 9.0, CURIOUS), Slot("b (end)", 15.2, CURIOUS, button=True)]
    sections = plan_sections(slots, 16.0)
    assert [s.scenes for s in sections] == [("a",), ("b",), ("b (end)",)] and sections[-1].bars == 1
    fitted = fit_music(sections, pauses=[Pause(12.5, 15.2)])
    assert fitted.closing_seconds == pytest.approx(15.2)  # struck as the line ends
    (a, b), = fitted.pauses
    assert fitted.tempo_map.seconds_at(a) <= 12.1 and b == fitted.score.length_beats - 4
    assert all(n.start < a or n.start >= b for p in fitted.score.parts for n in p.notes)


def test_scene_compose_keys_need_a_fitted_cue() -> None:
    VideoConfig.model_validate(_video())
    with pytest.raises(ValidationError, match=r"scenes\[2\]\.music: mood change composed music that follows the video"):
        VideoConfig.model_validate(_video(music={"compose": {"mood": "curious", "bars": 8}}))
    with pytest.raises(ValidationError, match=r"scenes\[2\]\.music: mood"):
        VideoConfig.model_validate(_video(music="calm"))
    bad = _video()
    bad["scenes"][2]["music"] = {"mood": "tense", "key": "E major"}
    with pytest.raises(ValidationError, match="written for a minor key"):
        VideoConfig.model_validate(bad)
    settings = musicfit.scene_settings(Settings("curious", key="G", seed=3, instruments={"melody": "oboe"}), VideoConfig.model_validate(_video()).scenes[2].music)
    assert settings == Settings("tense", seed=3)  # another mood: its defaults, the cue's seed


def test_music_settings_do_not_make_scene_renders_stale(tmp_path: Path) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    plain = _video()
    plain["scenes"][2].pop("music")
    changed = _video()
    changed["scenes"][2]["beats"][0]["music_pause"] = True
    one, two = _load(tmp_path / "a", plain), _load(tmp_path / "b", changed)
    assert scene_fingerprint(one, "storm") == scene_fingerprint(two, "storm")  # applied when the video is joined


def _fake_render(calls: list[Score]) -> Any:
    def render(score: Score, soundfont: Path, cache_dir: Path | None = None) -> np.ndarray:
        calls.append(score)
        n = round((score.length_seconds + synth.TAIL_SECONDS) * RATE)
        t = np.arange(n) / RATE
        audio = np.repeat((0.1 * np.sin(2 * np.pi * 262 * t))[:, None], 2, axis=1)
        return (audio * 10 ** ((music.MUSIC_LEVEL - loudness.integrated_loudness(audio)) / 20)).astype(np.float32)

    return render


def test_the_mix_plays_the_fitted_piece_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Score] = []
    monkeypatch.setattr(synth, "symusic_version", lambda: synth.SYMUSIC_VERSION)
    monkeypatch.setattr(synth, "render_score", _fake_render(calls))
    monkeypatch.setattr("vidgen.soundfont.resolve", lambda setting, root, download=True: Path("bank.sf2"))
    project = _load(tmp_path, _video(music={"compose": "curious", "duck": False}))
    placement = mix.plan_music(project, _timings(), round(TOTAL * RATE))[0]
    assert not placement.source.loop
    fit = placement.summary()["fit"]
    assert [s["scenes"] for s in fit["sections"]] == [["intro"], ["list"], ["storm"], ["gag"], ["end"], ["end (end)"]]
    assert [s["start"] for s in fit["sections"]] == [0.0, 3.95, 11.4, 17.1, 20.8, 27.8]
    assert [s["mood"] for s in fit["sections"]] == ["curious"] * 2 + ["tense"] + ["curious"] * 3
    assert len(fit["pauses"]) == 2 and fit["swells"] and fit["closing"] == 27.8
    # the last bar (the chord after the last line, 4 beats at 300 BPM at most) runs 0.1 s past the cue's end
    assert calls[0].length_seconds == pytest.approx(27.8 + 0.8)
    gain = placement.gain[round(27.8 * 100) - 5 : round(27.8 * 100)]
    assert gain.min() > 0.9  # the fade-out starts at the closing chord, not 3 s before the end


def test_stings_are_played_by_the_composed_musics_instruments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Score] = []
    monkeypatch.setattr(synth, "symusic_version", lambda: synth.SYMUSIC_VERSION)
    monkeypatch.setattr(synth, "render_score", _fake_render(calls))
    monkeypatch.setattr("vidgen.soundfont.resolve", lambda setting, root, download=True: Path("bank.sf2"))
    project = _load(tmp_path, _video())
    events = [SfxEvent(11.4, "sting_reveal", duck=True), SfxEvent(18.0, "sting_comic", duck=True), SfxEvent(1.0, "pop")]
    library = sfx.SoundLibrary(project.root)
    replaced = musicfit.composed_stings(project, _timings(), events, library)
    assert set(replaced) == {0, 1}
    assert [s.key for s in calls] == ["D minor", "F major"]  # the storm scene's tense mood, then the cue's
    target = loudness.integrated_loudness(sfx.stereo(sfx.synthesize("sting_reveal")))
    assert loudness.integrated_loudness(replaced[0]) == pytest.approx(target, abs=0.3)
    assert len(replaced[0]) <= round((calls[0].length_seconds + musicfit.STING_TAIL) * RATE)
    monkeypatch.setattr(synth, "symusic_version", lambda: None)  # no extra: the generated stings
    assert musicfit.composed_stings(project, _timings(), events, library) == {}
    beds = _load(tmp_path / "b", {**_video(), "music": "calm", "scenes": _video()["scenes"][:2]})
    assert musicfit.composed_stings(beds, _timings(), events, library) == {}


@pytest.mark.parametrize("mood", list(composer.MOODS))
def test_sting_scores_are_in_the_musics_key(mood: str) -> None:
    settings = Settings(mood)
    key = composer.mood_key(composer.MOODS[mood], None)
    reveal = musicfit.sting_score("reveal", settings)
    assert reveal.key == key.name and reveal.tempo == settings.nominal_tempo and reveal.length_beats <= 2 * reveal.bar_beats
    melody = next(p for p in reveal.parts if p.name == "melody")
    assert melody.notes[-1].pitch % 12 == key.tonic and (melody.notes[-1].pitch - melody.notes[0].pitch) == 5  # dominant, then tonic
    sad = next(p for p in musicfit.sting_score("sad", settings).parts if p.name == "melody")
    assert [b.pitch - a.pitch for a, b in zip(sad.notes, sad.notes[1:])] == [-1, -1, -1] and sad.notes[-1].pitch % 12 == key.tonic
    comic = musicfit.sting_score("comic", settings)
    drums = next(p for p in comic.parts if p.drums)
    assert [n.pitch for n in drums.notes] == [48, 45, 36, 49]
    voices = {v.role: v for v in composer.resolve_voices(composer.MOODS[mood])}
    assert drums.program == (voices["drums"].instrument.program if "drums" in voices else 0)


# ----- one real render -----------------------------------------------------------------------------


def _test_soundfont() -> Path | None:
    candidate = Path(os.environ.get("VIDGEN_TEST_SOUNDFONT") or default_path())
    return candidate if candidate.is_file() else None


@pytest.mark.skipif(not HAS_SYMUSIC or _test_soundfont() is None, reason="needs symusic 0.5.9 and a SoundFont (VIDGEN_TEST_SOUNDFONT or the downloaded default)")
def test_real_render_of_a_fitted_piece(tmp_path: Path) -> None:
    soundfont = _test_soundfont()
    assert soundfont is not None
    sections = _sections([0.0, 4.7], 9.0, [CURIOUS, TENSE])
    audio = synth.render_score(fit_music(sections, reveals=[2.0]).score, soundfont, tmp_path)
    assert len(audio) == round((9.0 + synth.TAIL_SECONDS) * RATE)
    assert loudness.integrated_loudness(audio) == pytest.approx(music.MUSIC_LEVEL, abs=0.3)
    sting = synth.render_score(musicfit.sting_score("reveal", TENSE), soundfont, tmp_path)
    assert math.isfinite(loudness.integrated_loudness(sting))
