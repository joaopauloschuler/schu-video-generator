"""Expressive notes in score files (Step 346, DESIGN.md §120.7): the marks are read, a score
without them plays as before, and what each mark does is measured on one short track."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import INSTRUMENTS, parse_music_score, patch_catalog
from vidgen.studio.check import check_music_score
from vidgen.studio.patterns import DYNAMICS, parse_steps
from vidgen.studio.render import range_warnings, render_music_score, render_track_stem


def _score(track: dict[str, object], bars: int = 1, tempo: float = 120, **more: object) -> dict[str, object]:
    return {"key": "C major", "tempo": tempo, "progression": "I", "loop": False, "bars": bars, "tracks": {"t": track}, **more}


def _stem(steps: str, instrument: str, tempo: float = 120, **settings: object) -> np.ndarray:
    """The track alone (mono), before the master filter and the level."""
    track: dict[str, object] = {"instrument": instrument, "steps": steps, "settings": settings}
    score = parse_music_score(_score(track, steps.count("|") + 1, tempo))
    return np.asarray(render_track_stem(score, "t").piece, dtype=float).mean(axis=1)


def _db(y: np.ndarray, start: float, end: float) -> float:
    return 10 * math.log10(float(np.mean(y[int(start * RATE) : int(end * RATE)] ** 2)) + 1e-30)


def _centroid(y: np.ndarray, start: float, end: float) -> float:
    part = y[int(start * RATE) : int(end * RATE)]
    power = np.abs(np.fft.rfft(part * np.hanning(len(part)))) ** 2
    return float(np.sum(np.fft.rfftfreq(len(part), 1 / RATE) * power) / np.sum(power))


def _pitch(y: np.ndarray, low: float, high: float) -> np.ndarray:
    """The frequency of the band ``low`` to ``high`` Hz (the fundamental) every 5 ms."""
    spectrum = np.fft.fft(y)
    freqs = np.fft.fftfreq(len(y), 1 / RATE)
    phase = np.unwrap(np.angle(np.fft.ifft(np.where((freqs > low) & (freqs < high), 2 * spectrum, 0))))
    hz = np.diff(phase) * RATE / (2 * np.pi)
    hop = int(0.005 * RATE)
    return hz[: len(hz) // hop * hop].reshape(-1, hop).mean(axis=1)


def _problems(track: dict[str, object], **more: object) -> str:
    with pytest.raises(VidgenError) as caught:
        parse_music_score(_score(track, **more))
    return str(caught.value)


# ----- the notation --------------------------------------------------------------------------------


def test_dynamic_marks_stay_until_changed_and_a_hairpin_runs_to_the_next_level() -> None:
    (bar,) = parse_steps("[p] x x [f] x - [mf <] x x x x [ff]", "w", expressive=True)
    assert [s.level for s in bar[:4]] == [DYNAMICS["p"], DYNAMICS["p"], DYNAMICS["f"], DYNAMICS["f"]]
    assert [(s.level, s.level_end) for s in bar[4:]] == [(0.0, 1.75), (1.75, 3.5), (3.5, 5.25), (5.25, 7.0)]
    first, second = parse_steps("[-6 <] A4 - - - | [+3] . . . .", "w", expressive=True)
    assert (first[0].level, first[3].level_end, second[0].level) == (-6.0, 3.0, 3.0)
    assert all(s.level == 0.0 and not s.marks for s in parse_steps("x . x .", "w")[0])


def test_fp_sfz_slurs_and_setting_items_are_read() -> None:
    (bar,) = parse_steps("[fp] A4 - [sfz] C5 (D5 - E5 F5) [stroke=pizzicato roll] G5", "w", expressive=True)
    assert (bar[0].level, bar[0].burst, bar[1].level) == (DYNAMICS["p"], DYNAMICS["f"] - DYNAMICS["p"], DYNAMICS["p"])
    assert (bar[2].level, bar[2].burst) == (DYNAMICS["p"], 7.0)
    assert [s.slur for s in bar[3:8]] == [False, False, True, True, False]
    assert bar[7].marks == ("stroke=pizzicato", "roll")


@pytest.mark.parametrize(
    ("steps", "words"),
    [
        ("[p <] A4 - - -", "has no end"),
        ("[f <] A4 - [p] -", "grows, but it runs from +4 dB to [p]"),
        ("[p <] A4 [>] A4 [f] A4", "has no end yet"),
        ("A4 [fp] - A4", "shapes the start of a note"),
        ("A4 [] A4", "an empty mark"),
        ("A4 [F] A4", "[F] is not a mark"),
        ("A4 [+30] A4", "from -40 to +12"),
        ("(A4 . C5)", "a rest inside the slur"),
        ("(A4 C5+E5)", "a chord inside the slur"),
        ("(A4 -)", "holds one note"),
        ("(A4 C5", "is not closed"),
        ("A4 C5)", "closes no slur"),
        ("A4 [stroke=roll] ", "belongs to no step"),
        ("A4 [f", "a mark is closed by ']'"),
    ],
)
def test_a_wrong_mark_is_named(steps: str, words: str) -> None:
    with pytest.raises(VidgenError, match="w: ") as caught:
        parse_steps(steps, "w", lead_hold=True, expressive=True)
    assert words in str(caught.value)


def test_marks_belong_to_a_tracks_steps_only() -> None:
    with pytest.raises(VidgenError, match="marks and slurs belong to a track's steps"):
        parse_steps("[p] x . x .", "gate.steps")
    assert "marks and slurs" in _problems({"instrument": "pad", "play": "chords", "gate": {"steps": "[f] x . x ."}})


def test_setting_marks_are_resolved_for_the_instrument() -> None:
    score = parse_music_score(_score({"instrument": "cellos", "steps": "C3 [pizzicato vibrato=0] D3 [stroke=2] E3 [default] F3"}))
    (bar,) = score.tracks[0].parts["main"].steps
    assert [dict(s.changes) for s in bar] == [{}, {"stroke": 3.0, "vibrato": 0.0}, {"stroke": 2.0, "vibrato": 0.0}, {}]
    drum = parse_music_score(_score({"instrument": "snare_drum", "steps": "x [pitch=200] x . [roll] x -"}))
    assert [dict(s.changes) for s in drum.tracks[0].parts["main"].steps[0]] == [{}, {"pitch": 200.0}, {}, {"pitch": 200.0, "stroke": 1.0}, {}]


@pytest.mark.parametrize(
    ("track", "words"),
    [
        ({"instrument": "cellos", "steps": "[pizzicatto] C3"}, "[pizzicatto]: unknown mark; did you mean 'pizzicato'?"),
        ({"instrument": "cellos", "steps": "[strok=pizzicato] C3"}, "cellos has no setting 'strok'; did you mean 'stroke'?"),
        ({"instrument": "cellos", "steps": "[stroke=plucked] C3"}, "unknown name 'plucked'"),
        ({"instrument": "cellos", "steps": "[vibrato=900] C3"}, "900.0 is out of range (0 to 50)"),
        ({"instrument": "cellos", "steps": "[vibrato] C3"}, "a setting is written with its value: [vibrato=...]"),
        ({"instrument": "piano", "steps": "[fortissimo] C3"}, "[fortissimo]: unknown mark"),
        ({"instrument": "choir", "steps": "[aah] C3"}, "write which, e.g. [vowel=aah]"),
        ({"instrument": "piano", "steps": "(C3 D3)"}, "piano cannot slur"),
        ({"instrument": "cellos", "settings": {"stroke": "spiccato"}, "steps": "(C3 D3)"}, "a slur needs stroke sustain or tremolo, not spiccato"),
        ({"instrument": "cellos", "steps": "(C3 [vibrato=0] D3)"}, "only glide may change there"),
        ({"instrument": "trumpet", "steps": "C4", "sections": {"main": {"instrument": "taiko"}}}, "taiko has no pitch and the track's trumpet plays notes"),
        ({"instrument": "trumpet", "steps": "C4", "sections": {"main": {"instrument": "hron"}}}, "unknown instrument 'hron'; did you mean 'horn'?"),
        ({"instrument": "pad", "play": "chords", "sections": {"main": {"instrument": "horn"}}}, "horn cannot hold chords"),
    ],
)
def test_a_mark_the_instrument_cannot_play_is_an_error_with_the_nearest_word(track: dict[str, object], words: str) -> None:
    assert words in _problems(track)


def test_a_slur_may_change_its_glide_and_brass_strings_choir_and_the_lead_slur() -> None:
    for name in ("trumpet", "horn", "low_brass", "violins", "violas", "cellos", "double_basses", "choir", "soft_lead"):
        parse_music_score(_score({"instrument": name, "steps": "(C3 - [glide=0.3] E3 -)"}))
    assert [n for n, i in INSTRUMENTS.items() if i.slurs is not None][0] == "soft_lead"


# ----- nothing changes without marks ---------------------------------------------------------------


def test_a_score_without_marks_has_plain_events_and_mf_is_the_unmarked_level() -> None:
    plain = _stem("A3 - C4 - E4 . A3!  .", "trumpet", tempo=200)
    assert np.array_equal(plain, _stem("[mf] A3 - C4 - [+0] E4 . A3! .", "trumpet", tempo=200))
    assert np.array_equal(plain, _stem("A3 - C4 - E4 . A3! .", "trumpet", tempo=200, vibrato_speed=5.3, vibrato_delay=0.28, touch=0, glide=0.4))
    assert not np.array_equal(plain, _stem("[mp] A3 - C4 - E4 . A3! .", "trumpet", tempo=200))


def test_the_same_marked_score_gives_the_same_samples() -> None:
    track = {"instrument": "violins", "steps": "[p <] (A4 - C5 -) [f] [spiccato] E5 E5 [fp sustain] A4 - - -", "settings": {"players": 2}}
    first, second = (render_music_score(parse_music_score(_score(track, tempo=160))) for _ in range(2))
    assert np.array_equal(first, second) and np.abs(first).max() > 0


# ----- dynamics ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "note", "settings", "window"), [
    ("trumpet", "A4", {}, (0.25, 0.45)),
    ("cellos", "D3", {"stroke": "spiccato", "players": 2}, (0.0, 0.1)),
    ("choir", "A3", {"singers": 2}, (0.3, 0.5)),
    ("taiko", "x", {}, (0.0, 0.08)),
    ("timpani", "D3", {}, (0.0, 0.1)),
])
def test_a_louder_mark_is_louder_and_brighter(name: str, note: str, settings: dict[str, object], window: tuple[float, float]) -> None:
    notes = {mark: _stem(f"[{mark}] {note} .", name, tempo=100, **settings) for mark in ("pp", "mf", "ff")}
    levels = [_db(y, 0.0, 0.5) for y in notes.values()]
    assert levels[1] - levels[0] == pytest.approx(15.0, abs=1.6) and levels[2] - levels[1] == pytest.approx(7.0, abs=1.6)
    bright = [_centroid(y, *window) for y in notes.values()]
    assert bright[0] < 0.92 * bright[1] and bright[1] < 0.95 * bright[2]


@pytest.mark.parametrize("name", ["organ", "soft_lead", "piano"])
def test_an_instrument_without_a_response_changes_its_level_only(name: str) -> None:
    soft, loud = (_stem(f"[{mark}] A3 .", name, tempo=100) for mark in ("p", "ff"))
    assert INSTRUMENTS[name].respond is None
    assert np.allclose(loud, soft * 10 ** (17 / 20), atol=1e-9)


def test_a_crescendo_inside_a_note_grows_evenly_and_opens_the_tone() -> None:
    y = _stem("[pp <] A4 - - - [ff] .", "trumpet", tempo=150, vibrato=0, breath=0)
    times = np.arange(0.2, 1.15, 0.1)  # the note lasts 1.28 s
    levels = np.array([_db(y, t, t + 0.1) for t in times])
    assert np.all(np.diff(levels) > 0.8) and levels[-1] - levels[0] == pytest.approx(22 * 0.9 / 1.28, abs=2.0)
    bright = [_centroid(y, t, t + 0.2) for t in (0.2, 0.6, 1.0)]
    assert bright[0] < 0.95 * bright[1] < 0.9 * bright[2]
    # the cross-fade between the soft and the loud note cancels nothing: the level never falls
    frames = np.array([_db(y, t, t + 0.05) for t in np.arange(0.2, 1.2, 0.025)])
    assert np.diff(frames).min() > 0.0


def test_a_short_note_under_a_hairpin_takes_the_level_at_its_start() -> None:
    y = _stem("[spiccato pp <] D3 D3 D3 D3 D3 D3 D3 D3 [ff] | D3 .", "cellos", tempo=240, players=1)
    peaks = [float(np.abs(y[int(k * 0.125 * RATE) : int((k + 1) * 0.125 * RATE)]).max()) for k in range(9)]
    steps = np.diff(20 * np.log10(peaks))
    # 22 dB of level in eight steps, and the bite of a louder stroke on top
    assert np.all(steps > 1.5) and np.all(steps < 6.0) and 22.0 < 20 * math.log10(peaks[8] / peaks[0]) < 34.0


def test_fp_starts_loud_and_bright_and_falls_to_piano_and_sfz_comes_back() -> None:
    y = _stem("[fp] A4 - - - | [sfz] A4 - - -", "trumpet", tempo=160)
    assert _db(y, 0.03, 0.08) - _db(y, 0.4, 0.6) == pytest.approx(14.0, abs=2.0)
    assert _centroid(y, 0.02, 0.09) > 1.3 * _centroid(y, 0.4, 0.6)
    assert _db(y, 1.53, 1.58) - _db(y, 1.9, 2.1) == pytest.approx(7.0, abs=2.5)  # sfz: 7 dB over the level in force (piano), and back


def test_touch_makes_an_accent_bite() -> None:
    plain, accented = (_stem(f"{note} .", "cellos", tempo=100, stroke="spiccato", players=1, touch=1) for note in ("D3", "D3!"))
    untouched = _stem("D3! .", "cellos", tempo=100, stroke="spiccato", players=1)
    assert _centroid(accented, 0, 0.1) > 1.08 * _centroid(plain, 0, 0.1)
    assert _centroid(untouched, 0, 0.1) == pytest.approx(_centroid(plain, 0, 0.1), rel=1e-6)
    assert _db(accented, 0, 0.3) - _db(plain, 0, 0.3) == pytest.approx(3.5, abs=0.8)


# ----- slurs and vibrato ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "settings"), [("trumpet", {}), ("violins", {"players": 1}), ("choir", {"singers": 1, "voices": "altos"}), ("soft_lead", {})])
def test_a_slur_is_one_note_whose_pitch_glides(name: str, settings: dict[str, object]) -> None:
    slurred = _stem("(A4 - C5 - E5 - A4 -) | .", name, tempo=96, vibrato=0, glide=0.1, **settings)
    hz = _pitch(slurred[: int(2.6 * RATE)], 380, 760)
    cents = 1200 * np.log2(hz / 440.0)
    at = [float(np.median(cents[int(t / 0.005) - 5 : int(t / 0.005) + 5])) for t in (0.4, 1.0, 1.6, 2.3)]
    assert at == pytest.approx([0, 300, 700, 0], abs=16)
    # on its way from A4 to C5: begun before the step at 0.625 s, there a little after it
    assert 60 < cents[int(0.60 / 0.005)] < 280 and cents[int(0.57 / 0.005)] < 40 and cents[int(0.68 / 0.005)] > 280
    # no new attack: the level near a join stays within 1.5 dB of the level before it
    level = np.array([_db(slurred, t, t + 0.02) for t in np.arange(0.3, 2.2, 0.005)])
    for join in (0.625, 1.25, 1.875):
        k = int((join - 0.3) / 0.005)
        near = level[k - 16 : k + 24] - np.median(level[k - 50 : k - 20])
        assert near.min() > -1.5 and near.max() < 1.5
    assert np.abs(slurred).max() < 1.3 * np.abs(slurred[int(0.3 * RATE) : int(0.5 * RATE)]).max()


def test_a_slur_reads_no_harmonic_above_its_pitch_and_the_note_memory_keys_on_the_phrase() -> None:
    for steps in ("(C5 - C6 - G6 - C5 -) .", "(G6 - C5 - C6 - G5 -) ."):
        y = _stem(steps, "trumpet", tempo=100, brightness=1.0, vibrato=0, breath=0, glide=0.2)
        power = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
        freqs = np.fft.rfftfreq(len(y), 1 / RATE)
        assert power[freqs > 16600].sum() < 1e-9 * power.sum()
    make = INSTRUMENTS["trumpet"].make
    assert make is not None
    s = {k: v.default for k, v in INSTRUMENTS["trumpet"].settings.items()}
    up, down, alone = (make(440.0, 30000, s, "seed", phrase=p) for p in (((12000, 3.0, 2880),), ((12000, -3.0, 2880),), ()))
    assert not np.allclose(up, down) and not np.allclose(up, alone)
    assert make(440.0, 30000, s, "seed", phrase=((12000, 3.0, 2880),)) is up and make(440.0, 30000, s, "seed") is alone


@pytest.mark.parametrize(("name", "settings", "low"), [("trumpet", {}, 380.0), ("violins", {"players": 1}, 380.0), ("soft_lead", {}, 380.0)])
def test_vibrato_speed_depth_and_delay_are_as_set(name: str, settings: dict[str, object], low: float) -> None:
    y = _stem("A4 - - - | - - . .", name, tempo=80, vibrato=30, vibrato_speed=7.0, vibrato_delay=0.9, **settings)
    cents = 1200 * np.log2(_pitch(y[: int(4.0 * RATE)], low, 520.0) / 440.0)
    early, late = cents[int(0.3 / 0.005) : int(0.85 / 0.005)], cents[int(2.2 / 0.005) : int(3.8 / 0.005)]
    assert np.ptp(early) < 12 and np.ptp(late) / 2 == pytest.approx(30.0, abs=4.0)
    wave = late - late.mean()
    crossings = np.sum((wave[:-1] < 0) & (wave[1:] >= 0))
    assert crossings / 1.6 == pytest.approx(7.0, abs=0.7)


# ----- settings per note, an instrument per section ------------------------------------------------


def test_a_setting_mark_plays_as_a_track_with_that_setting() -> None:
    marked = _stem("[pizzicato] D3 . [spiccato] D3 . [sustain] D3 - . .", "cellos", tempo=100, players=2)
    spiccato = _stem(". . D3 . . . . .", "cellos", tempo=100, players=2, stroke="spiccato")
    pizzicato = _stem("D3 . . . . . . .", "cellos", tempo=100, players=2, stroke="pizzicato")
    sustain = _stem(". . . . D3 - . .", "cellos", tempo=100, players=2)
    assert np.allclose(marked, pizzicato + spiccato + sustain, atol=1e-9)


def test_a_roll_into_a_hit_on_one_timpani_track_and_a_drums_pitch_per_hit() -> None:
    y = _stem("[roll pp <] A2 - - - - - - - | [hit ff] D2 . . . . . . .", "timpani", tempo=120, mallet=0.2)
    levels = [_db(y, t, t + 0.25) for t in np.arange(0.0, 2.0, 0.25)]
    assert np.all(np.diff(levels) > 0) and levels[-1] - levels[0] > 14
    assert _db(y, 2.0, 2.25) > levels[-1] + 2  # the hit on the other drum
    hit = y[int(2.3 * RATE) : int(3.3 * RATE)]
    freqs = np.fft.rfftfreq(len(hit), 1 / RATE)
    power = np.abs(np.fft.rfft(hit * np.hanning(len(hit)))) ** 2
    assert abs(freqs[np.argmax(power)] - 73.42 * 1.504) < 3 or abs(freqs[np.argmax(power)] - 73.42) < 3
    marked = _stem("x . [pitch=110] x . [default] x . . .", "taiko", tempo=100)
    low, high = _stem("x . . . x . . .", "taiko", tempo=100), _stem(". . x . . . . .", "taiko", tempo=100, pitch=110)
    assert np.allclose(marked, low + high, atol=1e-9)


def test_a_section_can_play_another_instrument_of_the_same_sort() -> None:
    def piece(track: dict[str, object]) -> np.ndarray:
        data = _score(track, tempo=160) | {"bars": None, "sections": [{"name": "a", "bars": 1}, {"name": "b", "bars": 1}]}
        data.pop("bars")
        score = parse_music_score(data)
        return np.asarray(render_track_stem(score, "t").piece, dtype=float)

    both = piece({"instrument": "trumpet", "octave": 3, "steps": "D4 - A3 .", "settings": {"brightness": 0.8},
                  "sections": {"b": {"instrument": "horn", "settings": {"players": 2}}}})
    trumpet = piece({"instrument": "trumpet", "octave": 3, "steps": "D4 - A3 .", "settings": {"brightness": 0.8}, "rest": ["b"]})
    horn = piece({"instrument": "horn", "steps": "D4 - A3 .", "settings": {"players": 2}, "rest": ["a"]})
    assert np.abs(horn).max() > 0 and np.allclose(both, trumpet + horn, atol=1e-12)


def test_a_duck_that_follows_its_hits_follows_their_dynamics() -> None:
    from vidgen.studio.render import _hit_times

    data = _score({"instrument": "kick", "steps": "x . [p] x . [sfz] x . X ."}, tempo=120)
    score = parse_music_score(data)
    levels = [level for _, level in _hit_times(score, {t.name: t for t in score.tracks}, "t")]
    assert levels == pytest.approx([1.0, 10 ** (-10 / 20), 10 ** (-3 / 20), 1.5 * 10 ** (-10 / 20)])


# ----- the range warning, the catalogue, the studio ------------------------------------------------


def test_notes_outside_the_written_range_are_reported_and_played() -> None:
    track = {"instrument": "horn", "steps": "A1 . D3 . G5 . A5 ."}
    score = parse_music_score(_score(track, tempo=200))
    lines = range_warnings(score)
    assert len(lines) == 2
    assert "tracks.t: 1 note below the written range of horn (B1 to F5): the lowest is A1 in section 'main'" in lines[0]
    assert "2 notes above the written range of horn (B1 to F5): the highest is A5" in lines[1]
    heard: list[str] = []
    assert np.abs(render_music_score(score, heard)).max() > 0 and heard == lines
    assert range_warnings(parse_music_score(_score({"instrument": "horn", "steps": "B1 . F5 ."}))) == []
    assert range_warnings(parse_music_score(_score({"instrument": "piano", "steps": "C0 . C8 ."}))) == []
    report = check_music_score(score)
    (finding,) = [f for f in report.findings if f.topic == "range"]
    assert finding.level == "note" and "below the written range of horn" in finding.text


def test_the_catalogue_lists_the_new_settings_and_the_studio_reads_a_marked_score() -> None:
    from vidgen.studio_app.song import describe_score

    by_name = {i["name"]: i for i in patch_catalog()["instruments"]}
    assert {"vibrato_speed", "vibrato_delay", "glide", "touch"} <= set(by_name["violins"]["settings"])
    assert by_name["violins"]["dynamics"] and by_name["violins"]["slurs"] and "slurs" not in by_name["timpani"] and "dynamics" not in by_name["organ"]
    assert "touch" in by_name["taiko"]["settings"] and "glide" in by_name["soft_lead"]["settings"]
    data = _score({"instrument": "cellos", "steps": "[p <] (C3 - E3 -) [f pizzicato] G3 . C3 ."})
    described = describe_score(parse_music_score(data), data)
    assert described["tracks"][0]["steps"] == "[p <] (C3 - E3 -) [f pizzicato] G3 . C3 ."
