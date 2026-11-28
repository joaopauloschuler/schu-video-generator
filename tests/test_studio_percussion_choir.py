"""Orchestral percussion and the choir of score files (Step 345): what makes
a drum a drum and a vowel a vowel is measured on single sounds (cheap: a score is rendered in
one test only)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import INSTRUMENTS, parse_music_score, patch_catalog, render_music_score
from vidgen.studio.choir import FORMANTS, KINDS, MORPHS, VOICES, VOWELS, formants, section, spectrum
from vidgen.studio.percussion import KETTLE, MEMBRANE, TAIKO, TIMPANO, ring_seconds, struck

A2, C3, C4 = 110.0, 130.81, 261.63
HIT, ROLL = 0.0, 1.0


def _settings(name: str, **settings: float) -> dict[str, float]:
    return {k: v.default for k, v in INSTRUMENTS[name].settings.items()} | settings


def _note(name: str, freq: float, seconds: float = 0.5, seed: str = "studio:1:t", **settings: float) -> np.ndarray:
    """One note of ``seconds`` held plus its ring, at the instrument's level."""
    instrument, s = INSTRUMENTS[name], _settings(name, **settings)
    assert instrument.make is not None and instrument.seeded
    return instrument.make(freq, int((seconds + s["ring"]) * RATE), s, seed) * instrument.level


def _drum(name: str, held: float = 0.25, **settings: float) -> np.ndarray:
    instrument = INSTRUMENTS[name]
    assert instrument.make is not None and instrument.kind == "drum"
    return np.asarray(instrument.make(_settings(name, **settings), held)) * instrument.level


def _mono(y: np.ndarray) -> np.ndarray:
    return y.mean(axis=1) if y.ndim == 2 else y


def _spectrum(y: np.ndarray, start: float, end: float, padded: int = 1) -> tuple[np.ndarray, np.ndarray]:
    part = _mono(y)[int(start * RATE) : int(end * RATE)]
    return np.fft.rfftfreq(padded * len(part), 1 / RATE), np.abs(np.fft.rfft(part * np.blackman(len(part)), padded * len(part))) ** 2


def _centroid(y: np.ndarray, start: float, end: float) -> float:
    freqs, power = _spectrum(y, start, end)
    return float(np.sum(freqs * power) / np.sum(power))


def _peak_near(y: np.ndarray, freq: float, start: float, end: float, within: float = 0.04) -> float:
    """The frequency of the strongest partial within ``within`` of ``freq``."""
    freqs, power = _spectrum(y, start, end, 8)
    near = np.abs(freqs / freq - 1) < within
    return float(freqs[near][np.argmax(power[near])])


def _db(y: np.ndarray, start: float, end: float) -> float:
    return 10 * math.log10(float(np.mean(_mono(y)[int(start * RATE) : int(end * RATE)] ** 2)) + 1e-30)


def _periods(y: np.ndarray, start: float, end: float) -> np.ndarray:
    """The lengths in samples of the waves of mono ``y`` between two seconds (from its rising zero crossings)."""
    part = y[int(start * RATE) : int(end * RATE)]
    crossings = np.flatnonzero((part[:-1] < 0) & (part[1:] >= 0))
    return np.diff(crossings + part[crossings] / (part[crossings] - part[crossings + 1]))


def _loudness(y: np.ndarray, start: float, end: float) -> float:
    from vidgen.loudness import integrated_loudness

    part = y[int(start * RATE) : int(end * RATE)]
    return integrated_loudness(part if part.ndim == 2 else np.stack([part, part], axis=1))


def _score(track: dict[str, object], bars: int = 1) -> dict[str, object]:
    return {"key": "A minor", "tempo": 120, "progression": "i", "loop": False, "sections": [{"name": "all", "bars": bars}], "tracks": {"t": track}}


# ----- struck heads ----------------------------------------------------------------------------------


def test_a_timpano_rings_in_the_kettle_ratios_and_not_in_a_harmonic_series() -> None:
    hit = _note("timpani", A2, 2.0, mallet=0.9)
    main = _peak_near(hit, A2, 0.3, 2.0)
    assert abs(main / A2 - 1) < 0.003
    for ratio in KETTLE[1:6]:  # 1.5 : 1.99 : 2.44 : 2.91 : 3.36 above the note, each drum up to half a percent off
        assert abs(_peak_near(hit, A2 * ratio, 0.3, 2.0) / main / ratio - 1) < 0.008, ratio
    freqs, power = _spectrum(hit, 0.3, 2.0)
    at = lambda multiple: power[np.abs(freqs / (A2 * multiple) - 1) < 0.01].sum()  # noqa: E731
    assert at(2.44) > 30 * at(2.22) and at(1.504) > 30 * at(1.25) and at(2.91) > 10 * at(3.0)  # between and beside the modes: nothing
    assert at(0.85) < 0.01 * at(1.0)  # the thump under the note is gone after 0.3 s
    early = _spectrum(hit, 0.0, 0.12)
    assert early[1][np.abs(early[0] / (A2 * 0.85) - 1) < 0.08].sum() > 0.02 * early[1].sum()


def test_low_drums_ring_longer_and_a_short_ring_is_a_damped_note() -> None:
    assert ring_seconds(TIMPANO, 73.4) > 1.3 * ring_seconds(TIMPANO, 220.0) and ring_seconds(TAIKO, 62.0) > ring_seconds(TIMPANO, 220.0)
    low, high = _note("timpani", 73.4, 0.5), _note("timpani", 220.0, 0.5)
    assert _db(low, 1.5, 2.0) - _db(low, 0.0, 0.3) > _db(high, 1.5, 2.0) - _db(high, 0.0, 0.3) + 4
    damped = _note("timpani", A2, 0.25, ring=0.1)
    assert len(damped) == int(0.35 * RATE) and damped[0] == 0 and abs(damped[-1]) < 1e-6 and _db(damped, 0.2, 0.26) > -45
    assert low[0] == 0 and abs(low[-1]) < 1e-5 * np.abs(low).max()


def test_a_harder_mallet_is_brighter_at_about_the_same_level() -> None:
    for name, freq in (("timpani", A2), ("toms", C3)):
        soft, hard = _note(name, freq, mallet=0.1), _note(name, freq, mallet=0.9)
        assert _centroid(hard, 0.0, 0.05) > 1.3 * _centroid(soft, 0.0, 0.05), name
        assert abs(_db(soft, 0.0, 0.15) - _db(hard, 0.0, 0.15)) < 3.5, name
    assert _centroid(_drum("taiko", mallet=1.0), 0.0, 0.1) > 1.3 * _centroid(_drum("taiko", mallet=0.2), 0.0, 0.1)


def test_a_tom_falls_to_its_note_rings_as_a_membrane_and_is_even_over_its_range() -> None:
    hit = _note("toms", C3, 0.5, drop=2.0)
    first, settled = _peak_near(hit, C3 * 1.08, 0.0, 0.06, 0.15), _peak_near(hit, C3, 0.3, 0.6)
    assert 0.8 < 12 * math.log2(first / settled) < 1.9 and abs(settled / C3 - 1) < 0.004  # 2 semitones sharp at the blow, the note 0.3 s later
    assert abs(12 * math.log2(_peak_near(_note("toms", C3, 0.5, drop=0.0), C3, 0.0, 0.06, 0.15) / C3)) < 0.2
    hit = _note("toms", C3, 0.5, drop=0.0, mallet=0.9)
    assert abs(_peak_near(hit, C3 * MEMBRANE[1], 0.05, 0.4) / C3 / MEMBRANE[1] - 1) < 0.01  # 1.594, not 2
    levels = [_db(_note("toms", freq), 0.0, 0.15) for freq in (49.0, 98.0, 196.0, 392.0, 523.25)]  # G1 to C5: a kick ends at 160 -> 70 Hz
    assert max(levels) - min(levels) < 4.0
    assert _db(_note("toms", C3, shell=3.0), 0.0, 0.1) != _db(_note("toms", C3, shell=0.0), 0.0, 0.1)


def test_every_blow_at_the_same_settings_is_the_same_and_another_track_is_another_drum() -> None:
    first, again = _note("timpani", A2, 0.3), _note("timpani", A2, 0.3)
    assert np.array_equal(first, again) and not np.array_equal(first, _note("timpani", A2, 0.3, seed="studio:1:other"))
    assert struck("taiko", 62.0, 0.7, 1.0, 1.5) is struck("taiko", 62.0, 0.7, 1.0, 1.5) and not struck("taiko", 62.0, 0.7, 1.0, 1.5).flags.writeable
    for name in ("taiko", "bass_drum", "frame_drum", "snare_drum"):
        assert np.array_equal(_drum(name), _drum(name)) and _drum(name)[0] == 0, name


def test_a_roll_is_fast_blows_for_its_held_steps_at_the_level_of_a_blow() -> None:
    roll, hit = _note("timpani", A2, 2.0, stroke=ROLL, speed=10.0, ring=0.5), _note("timpani", A2, 0.5)
    assert len(roll) == int(2.5 * RATE) and abs(roll[-1]) < 1e-6
    assert abs(_db(roll, 0.8, 2.0) - _db(hit, 0.0, 0.15)) < 4.5 and _db(roll, 2.3, 2.45) < _db(roll, 1.0, 2.0) - 3
    level = np.abs(np.fft.rfft(np.abs(roll[int(0.5 * RATE) : int(2.0 * RATE)])))
    beats = np.fft.rfftfreq(int(1.5 * RATE), 1 / RATE)
    wanted = (beats > 4) & (beats < 30)
    assert abs(beats[wanted][np.argmax(level[wanted])] - 10.0) < 1.0
    snare = _drum("snare_drum", 1.0, stroke=ROLL)
    assert len(snare) > RATE and _db(snare, 0.3, 1.0) > _db(snare, 1.3, 1.5) + 20


def test_big_drums_differ_and_an_ensemble_is_wide() -> None:
    taiko, bass, frame, rim = _drum("taiko"), _drum("bass_drum"), _drum("frame_drum"), _drum("frame_drum", edge=1.0)
    assert taiko.ndim == 1 and len(bass) > len(taiko) > len(frame) > len(rim)
    assert _centroid(bass, 0.0, 0.5) < _centroid(taiko, 0.0, 0.5) < _centroid(frame, 0.0, 0.5) < _centroid(rim, 0.0, 0.5)
    assert abs(_peak_near(taiko, 62.0, 0.2, 1.2) / 62.0 - 1) < 0.01 and abs(_peak_near(_drum("frame_drum", pitch=240.0), 240.0, 0.1, 0.4) / 240.0 - 1) < 0.01
    above = lambda start, end: (lambda f, p: p[f > 500].sum() / p.sum())(*_spectrum(taiko, start, end))  # noqa: E731
    assert above(0.0, 0.03) > 0.004 and above(0.3, 1.0) < 1e-6 and _db(taiko, 0.5, 1.0) > _db(taiko, 0.0, 0.1) - 30  # a hard attack, then the low tail
    four = _drum("taiko", players=4.0)
    assert four.ndim == 2 and float(np.corrcoef(four[: RATE // 2, 0], four[: RATE // 2, 1])[0, 1]) < 0.95
    assert abs(_db(four, 0.0, 0.4) - _db(taiko, 0.0, 0.4)) < 3.0  # as loud as one drum
    assert len(_drum("taiko", players=4.0, apart=0.0)) <= len(four) < len(_drum("taiko", players=4.0, apart=0.06))


def test_a_snare_drum_is_a_head_and_its_wires() -> None:
    on, off = _drum("snare_drum"), _drum("snare_drum", snares=0.0)
    freqs, power = _spectrum(on, 0.0, 0.2)
    assert power[freqs > 1000].sum() > 0.5 * power.sum() and power[freqs > 16000].sum() < 1e-3 * power.sum()
    assert _centroid(off, 0.0, 0.2) < 0.5 * _centroid(on, 0.0, 0.2)
    assert _drum("snare_drum", players=4.0).ndim == 2


def test_metal_is_inharmonic_loses_its_highs_first_and_a_swell_grows_to_its_end() -> None:
    crash = _drum("cymbal", decay=0.3)
    assert crash.ndim == 2 and _centroid(crash, 0.0, 0.3) > 2500 and _centroid(crash, 0.0, 0.3) > 1.5 * _centroid(crash, 1.0, 1.4)
    freqs, power = _spectrum(crash, 0.05, 0.6)
    low = power[(freqs > 280) & (freqs < 1500)]
    peaks = freqs[(freqs > 280) & (freqs < 1500)][np.argsort(low)[-6:]]
    assert np.abs(peaks / peaks.min() - np.round(peaks / peaks.min())).max() > 0.08  # its strongest low partials are no harmonic series
    assert power[freqs > 16000].sum() < 1e-4 * power.sum()
    assert _centroid(_drum("cymbal", decay=0.3, mallet=1.0), 0.0, 0.2) > _centroid(_drum("cymbal", decay=0.3, mallet=0.1), 0.0, 0.2)
    swell = _drum("cymbal", 2.0, stroke=1.0, decay=0.3)
    assert _db(swell, 1.6, 2.0) > _db(swell, 0.2, 0.6) + 12 and _db(swell, 1.7, 2.1) > _db(swell, 2.6, 3.0) + 3
    assert abs(_db(swell, 1.75, 2.15) - _db(crash, 0.0, 0.4)) < 3.0  # it arrives at about the level of a blow
    gong = _drum("tam_tam", decay=0.5)
    highs = lambda y, start, end: (lambda f, p: 10 * math.log10(p[f > 1500].sum()))(*_spectrum(y, start, end))  # noqa: E731
    assert highs(gong, 0.4, 0.6) > highs(gong, 0.0, 0.2) + 5  # the highs arrive after the blow
    assert highs(_drum("tam_tam", decay=0.5, bloom=0.0), 0.4, 0.6) < highs(gong, 0.4, 0.6) - 10


# ----- the choir -------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind, freq", [("basses", 98.0), ("tenors", 146.83), ("altos", 220.0), ("sopranos", 293.66)])
def test_formants_stay_where_they_are_when_the_pitch_moves(kind: str, freq: float) -> None:
    for vowel, which in (("aah", 0), ("ooh", 0), ("eeh", 0), ("eeh", 1)):  # the first formant, and eeh's second (it stands alone)
        formant = FORMANTS[kind][vowel][which][0]
        for hz in (freq, freq * 2 ** (2 / 12), freq * 2 ** (5 / 12)):
            assert formants(kind, vowel, hz)[0][which] == max(formant, hz)  # a note above the first formant takes it along
            levels = spectrum(kind, vowel, hz, 1.0) * np.arange(1, len(spectrum(kind, vowel, hz, 1.0)) + 1)  # the folds' fall taken out
            harmonics = hz * np.arange(1, len(levels) + 1)
            near = (harmonics > formant - hz) & (harmonics < formant + hz)
            assert abs(harmonics[near][np.argmax(levels[near])] - max(formant, hz)) <= 0.75 * hz, (vowel, hz, formant)


def test_a_sung_note_has_the_spectrum_of_its_vowel() -> None:
    note = _note("choir", 110.0, 1.0, voices=float(VOICES.index("basses")), vowel=float(VOWELS.index("aah")), singers=1.0, vibrato=0.0, breath=0.0)
    freqs, power = _spectrum(note, 0.5, 1.0)
    measured = np.array([power[np.abs(freqs - 110.0 * h) < 12].sum() for h in range(1, 25)])
    wanted = spectrum("basses", "aah", 110.0, INSTRUMENTS["choir"].settings["brightness"].default)[:24] ** 2
    off = 10 * np.log10(measured / measured.max()) - 10 * np.log10(wanted / wanted.max())
    assert np.abs(off[wanted > 1e-4 * wanted.max()]).max() < 1.5
    assert int(np.argmax(measured[2:])) + 3 in (5, 6)  # 550 or 660 Hz: the first formant of a bass's aah at 600


def test_vowels_differ_and_a_high_soprano_note_follows_its_first_formant() -> None:
    sung = {vowel: _note("choir", C4, 0.8, vowel=float(k)) for k, vowel in enumerate(VOWELS)}
    centroid = {vowel: _centroid(y, 0.4, 0.8) for vowel, y in sung.items()}
    assert centroid["mm"] < centroid["ooh"] < centroid["oh"] < centroid["aah"] and centroid["ooh"] < centroid["eeh"]
    freqs, _ = _spectrum(sung["eeh"], 0.4, 0.8)
    second = (freqs > 1400) & (freqs < 2300)  # the second formant of eeh and ee, where ooh and aah have none
    share = {vowel: (lambda p: p[second].sum() / p.sum())(_spectrum(y, 0.4, 0.8)[1]) for vowel, y in sung.items()}
    assert min(share["eeh"], share["ee"]) > 20 * max(share["ooh"], share["mm"]) and share["eeh"] > 5 * share["aah"]
    hz, width = formants("sopranos", "ooh", 880.0)  # A5 is far above an ooh's first formant (325 Hz)
    assert hz[0] == 880.0 and hz[1] >= 1.33 * 880.0 and width[0] > 100
    high = spectrum("sopranos", "ooh", 880.0, 0.5)
    assert np.argmax(high) == 0 and formants("basses", "aah", 98.0)[0][0] == 600.0


def test_a_mixed_choir_gives_each_note_to_the_voices_that_reach_it() -> None:
    assert set(section("mixed", 40, 8)) == {"basses"} and set(section("mixed", 84, 8)) == {"sopranos"}
    assert sorted(set(section("mixed", 60, 8))) == ["altos", "tenors"] and section("mixed", 60, 8).count("tenors") == 4
    assert set(section("men", 72, 6)) == {"tenors"} and set(section("women", 45, 6)) == {"altos"}  # out of reach: the nearest kind
    assert section("altos", 30, 5) == ["altos"] * 5
    for midi in range(36, 90):
        assert len(section("mixed", midi, 7)) == 7
    assert KINDS == ("basses", "tenors", "altos", "sopranos") and MORPHS[0] == "none"


def test_a_section_is_wide_and_steady_a_single_voice_mono_with_a_late_vibrato() -> None:
    many = _note("choir", C4, 1.6)
    assert many.ndim == 2 and float(np.corrcoef(many[RATE // 2 :, 0], many[RATE // 2 :, 1])[0, 1]) < 0.9
    frames = [10 * math.log10(float(np.mean(many[int(t * RATE) : int((t + 0.1) * RATE)] ** 2))) for t in np.arange(0.6, 1.5, 0.1)]
    assert max(frames) - min(frames) < 3.0
    one = _note("choir", C4, 1.6, singers=1.0, vibrato=30.0, breath=0.0)
    assert one.ndim == 1

    def cents(start: float) -> float:
        periods = _periods(one, start, start + 0.18)
        return float(1200 * np.log2(periods.max() / periods.min()))

    assert cents(0.1) < 12 and cents(1.2) > 35
    assert many[0, 0] == 0 and np.abs(many[-1]).max() < 1e-6 and _db(many, 0.0, 0.05) < _db(many, 0.5, 1.0) - 12  # a slow attack


def test_the_choir_is_as_loud_at_every_pitch_and_aliases_nothing() -> None:
    levels = []
    for freq in (82.41, 130.81, 220.0, 392.0, 659.26, 1046.5):  # E2 to C6
        note = _note("choir", freq, 0.9, vowel=float(VOWELS.index("aah")))
        freqs, power = _spectrum(note, 0.5, 0.9)
        levels.append(_loudness(note, 0.4, 0.9))
        assert power[freqs > 16500].sum() < 1e-7 * power.sum(), freq
    assert max(levels) - min(levels) < 2.5


def test_a_held_note_can_open_from_a_hum_to_a_vowel() -> None:
    plain = _note("choir", C4, 2.0, vowel=float(VOWELS.index("mm")))
    morphed = _note("choir", C4, 2.0, vowel=float(VOWELS.index("mm")), morph=float(MORPHS.index("aah")))
    assert abs(_centroid(morphed, 0.1, 0.3) / _centroid(plain, 0.1, 0.3) - 1) < 0.25
    assert _centroid(morphed, 1.6, 1.9) > 2.0 * _centroid(plain, 1.6, 1.9)
    assert abs(_db(morphed, 1.5, 1.9) - _db(plain, 1.5, 1.9)) < 3.0


def test_a_choir_note_depends_on_its_seed_pitch_and_settings_only() -> None:
    again = [_note("choir", 220.0, 0.2) for _ in range(2)]
    assert np.array_equal(again[0], again[1]) and not np.array_equal(again[0], _note("choir", 220.0, 0.2, seed="studio:1:other"))
    make, s = INSTRUMENTS["choir"].make, _settings("choir")
    assert make is not None
    short = make(220.0, 4800, s, "x")
    assert make(220.0, 4800, dict(s), "x") is short and not short.flags.writeable


# ----- in a score ----------------------------------------------------------------------------------


def test_names_are_read_in_a_score_and_the_catalogue_lists_the_families() -> None:
    score = parse_music_score({**_score({"instrument": "choir", "steps": "*", "settings": {"vowel": "aah", "voices": "women", "morph": "ooh"}}),
                               "tracks": {"t": {"instrument": "choir", "steps": "*", "settings": {"vowel": "aah", "voices": "women", "morph": "ooh"}},
                                          "timp": {"instrument": "timpani", "steps": "A2 - - -", "settings": {"stroke": "roll"}},
                                          "cym": {"instrument": "cymbal", "steps": "x - - -", "settings": {"stroke": "swell"}},
                                          "taiko": {"instrument": "taiko", "steps": "X..x", "settings": {"players": 4}}}})
    parts = {t.name: next(iter(t.parts.values())) for t in score.tracks}
    assert parts["t"].settings["vowel"] == 1.0 and parts["t"].settings["voices"] == 2.0 and parts["t"].settings["morph"] == 1.0
    assert parts["timp"].settings["stroke"] == 1.0 and parts["cym"].settings["stroke"] == 1.0
    for instrument, settings, message in (("choir", {"vowel": "ah"}, r"unknown name 'ah'; did you mean '(aah|oh)'\?"),
                                          ("choir", {"voices": "sopranos", "singers": 17}, "singers"),
                                          ("timpani", {"stroke": "rol"}, r"unknown name 'rol'; did you mean 'roll'\? \(one of: hit, roll\)"),
                                          ("taiko", {"pitch": 500}, "pitch")):
        with pytest.raises(VidgenError, match=message):
            parse_music_score(_score({"instrument": instrument, "steps": "x", "settings": settings}))
    with pytest.raises(VidgenError, match="taiko has no pitch"):
        parse_music_score(_score({"instrument": "taiko", "steps": "A2"}))
    by_name = {i["name"]: i for i in patch_catalog()["instruments"]}
    percussion = ("timpani", "toms", "taiko", "bass_drum", "frame_drum", "snare_drum", "cymbal", "tam_tam")
    assert [i["name"] for i in patch_catalog()["instruments"] if i["group"] == "percussion"] == list(percussion)
    assert [by_name[n]["kind"] for n in percussion] == ["note", "note"] + ["drum"] * 6 and by_name["choir"]["group"] == "choir"
    assert by_name["timpani"]["range"] == ["D2", "A3"] and by_name["toms"]["range"] == ["G1", "C5"] and by_name["choir"]["range"] == ["E2", "C6"]
    assert by_name["choir"]["settings"]["vowel"]["choices"] == list(VOWELS) and by_name["kick"]["settings"]["high"]["high"] == 160  # the old kick stays


def test_a_dense_pattern_of_drums_repeats_exactly() -> None:
    tracks = {"taiko": {"instrument": "taiko", "steps": "X.xx x.xx X.x. xxxx"}, "toms": {"instrument": "toms", "steps": "C3 . G2 G2 C3 . G2 . C3 C3 G2 . E3 E3 C3 G2"},
              "timp": {"instrument": "timpani", "steps": "A2 . . . E2 . . . A2 . A2 . E2 . E2 E2", "settings": {"ring": 0.3}}}
    score = parse_music_score({**_score({}, bars=3), "tracks": tracks})
    audio = render_music_score(score)
    bar = score.samples // 3
    second, third = audio[bar : 2 * bar], audio[2 * bar : 3 * bar]
    assert np.abs(second).max() > 0 and np.allclose(second[: bar - 2000], third[: bar - 2000], atol=2e-3 * np.abs(second).max())
