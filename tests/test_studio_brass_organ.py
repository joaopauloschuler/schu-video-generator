"""The brass and organ instruments of score files (Step 343, DESIGN.md §120.4): what makes them
brass and organ is measured on single notes (cheap: no score is rendered except in one test)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import INSTRUMENTS, parse_music_score, patch_catalog, render_music_score
from vidgen.studio.additive import HIGHEST_PARTIAL, read_tables, wavetables
from vidgen.studio.organ import REGISTRATION_NAMES, read_drawbars

BRASS = ("trumpet", "horn", "low_brass")
A4, A3, C6 = 440.0, 220.0, 1046.502


def _note(name: str, freq: float, seconds: float = 0.8, seed: str = "studio:1:t", **settings: float) -> np.ndarray:
    """One note of ``seconds`` held plus its ring, at the instrument's level."""
    instrument = INSTRUMENTS[name]
    s = {k: v.default for k, v in instrument.settings.items()} | settings
    assert instrument.make is not None and instrument.seeded
    return instrument.make(freq, int((seconds + s["ring"]) * RATE), s, seed) * instrument.level


def _mono(y: np.ndarray) -> np.ndarray:
    return y.mean(axis=1) if y.ndim == 2 else y


def _rms_db(y: np.ndarray, start: float, end: float) -> float:
    return 10 * math.log10(float(np.mean(y[int(start * RATE) : int(end * RATE)] ** 2)) + 1e-30)


def _spectrum(y: np.ndarray, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
    part = _mono(y)[int(start * RATE) : int(end * RATE)]
    return np.fft.rfftfreq(len(part), 1 / RATE), np.abs(np.fft.rfft(part * np.blackman(len(part)))) ** 2


def _centroid(y: np.ndarray, start: float, end: float) -> float:
    freqs, power = _spectrum(y, start, end)
    return float(np.sum(freqs * power) / np.sum(power))


def _harmonic(y: np.ndarray, freq: float) -> np.ndarray:
    """The amplitude over time of the partial at ``freq`` Hz (20 ms window)."""
    mono = _mono(y)
    window = np.hanning(int(0.02 * RATE))
    return 2 * np.abs(np.convolve(mono * np.exp(-2j * np.pi * freq * np.arange(len(mono)) / RATE), window / window.sum(), mode="same"))


def _score(track: dict[str, Any]) -> dict[str, Any]:
    return {"key": "A minor", "tempo": 120, "progression": "i", "loop": False, "sections": [{"name": "all", "bars": 1}], "tracks": {"t": track}}


# ----- the wave tables -----------------------------------------------------------------------------


def test_wavetables_hold_exactly_the_harmonics_asked_for() -> None:
    amplitudes = np.array([[1.0, 0.0, 0.5], [0.0, 1.0, 0.0]])
    tables = wavetables(amplitudes)
    x = np.arange(tables.shape[1] - 1) / (tables.shape[1] - 1)
    assert np.allclose(tables[0, :-1], np.sin(2 * np.pi * x) + 0.5 * np.sin(6 * np.pi * x), atol=1e-9)
    phase = np.linspace(0.0, 3.0, 1000)
    assert np.allclose(read_tables(tables, phase, np.full(1000, 1.0)), np.sin(4 * np.pi * phase), atol=1e-4)
    assert np.allclose(read_tables(tables, phase, np.full(1000, 0.5)), 0.5 * (read_tables(tables[:1], phase) + np.sin(4 * np.pi * phase)), atol=1e-4)


# ----- brass ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,freq", [("trumpet", A4), ("horn", A3), ("low_brass", 110.0)])
def test_brass_gets_brighter_when_blown_harder_and_no_louder(name: str, freq: float) -> None:
    soft, loud = (_note(name, freq, brightness=b, breath=0.0, vibrato=0.0, players=1.0) for b in (0.1, 1.0))
    assert _centroid(loud, 0.4, 0.8) > 1.8 * _centroid(soft, 0.4, 0.8)
    assert abs(_rms_db(loud, 0.4, 0.8) - _rms_db(soft, 0.4, 0.8)) < 1.5


def test_a_brass_note_opens_as_it_speaks_and_starts_a_little_flat() -> None:
    y = _note("trumpet", A4, attack=0.1, breath=0.0, vibrato=0.0)
    first, eighth = _harmonic(y, A4), _harmonic(y, 8 * A4)
    half = [int(np.argmax(h > 0.5 * np.median(h[int(0.4 * RATE) : int(0.7 * RATE)]))) / RATE for h in (first, eighth)]
    assert 0.02 < half[0] < half[1] - 0.01 < 0.1  # the fundamental first, the eighth harmonic at least 10 ms later
    assert _centroid(y, 0.0, 0.03) < 0.75 * _centroid(y, 0.3, 0.6)
    # the lips: the phase of the fundamental runs slow in the first 40 ms (flat), then on pitch
    phase = np.unwrap(np.angle(np.convolve(y * np.exp(-2j * np.pi * A4 * np.arange(len(y)) / RATE), np.hanning(480) / 240, mode="same")))
    slope = lambda a, b: (phase[int(b * RATE)] - phase[int(a * RATE)]) / (2 * np.pi * (b - a))  # noqa: E731  (Hz off the note)
    assert -6.0 < slope(0.015, 0.04) < -0.8 and abs(slope(0.3, 0.6)) < 0.5


def test_brass_attack_setting_and_delayed_vibrato() -> None:
    def rise(attack: float) -> float:
        y = _note("horn", A3, 1.2, attack=attack, breath=0.0)
        level = np.sqrt(np.convolve(y**2, np.ones(480) / 480, mode="same"))
        return float(np.argmax(level > 0.9 * np.median(level[int(0.8 * RATE) : int(1.1 * RATE)]))) / RATE

    assert rise(0.03) < 0.04 and 0.2 < rise(0.3) < 0.3
    y = _note("trumpet", A4, 1.6, vibrato=20.0, breath=0.0)
    phase = np.unwrap(np.angle(np.convolve(y * np.exp(-2j * np.pi * A4 * np.arange(len(y)) / RATE), np.hanning(960) / 480, mode="same")))
    cents = 1200 * np.log2(1 + np.gradient(phase) * RATE / (2 * np.pi) / A4)
    early, late = cents[int(0.1 * RATE) : int(0.27 * RATE)], cents[int(0.8 * RATE) : int(1.5 * RATE)]
    assert np.ptp(early) < 6 and 30 < np.ptp(late) < 50  # none before 0.28 s, then +-20 cents (and the drift)


@pytest.mark.parametrize("name,freq", [("trumpet", C6), ("trumpet", 1760.0), ("horn", 698.46), ("low_brass", 41.2)])
def test_brass_has_no_partial_near_nyquist_and_nothing_between_its_harmonics(name: str, freq: float) -> None:
    y = _note(name, freq, 1.0, brightness=1.0, breath=0.0, vibrato=0.0, players=1.0)
    freqs, power = _spectrum(y, 0.4, 0.9)
    assert power[freqs > HIGHEST_PARTIAL + 300].sum() < 1e-10 * power.sum()
    near = np.abs(freqs / freq - np.round(freqs / freq)) * freq < np.maximum(freqs * 0.035, 14.0)  # 60 cents: the pitch drifts a little
    assert power[~near].sum() < 1e-7 * power.sum()  # aliases would lie between the harmonics: under -70 dB


def test_brass_is_even_across_its_range_and_starts_and_ends_at_zero() -> None:
    for name, freqs in (("trumpet", (164.8, 440.0, 1046.5)), ("horn", (61.7, 220.0, 698.5)), ("low_brass", (41.2, 110.0, 349.2))):
        levels = [_rms_db(_note(name, f, 0.9), 0.5, 0.9) for f in freqs]
        assert max(levels) - min(levels) < 0.5, (name, levels)
        y = _note(name, freqs[1], 0.3)
        peak = np.abs(y).max()
        assert np.abs(y[0]).max() < 1e-6 * peak and np.abs(y[-1]).max() < 1e-4 * peak
        assert np.abs(np.diff(y[:96], axis=0)).max() < 0.002 * peak and np.abs(np.diff(y[-96:], axis=0)).max() < 0.002 * peak


def test_a_section_is_stereo_a_solo_mono_and_a_tuba_sounds_an_octave_under() -> None:
    assert _note("trumpet", A4, 0.3).ndim == 1 and _note("horn", A3, 0.3).ndim == 1
    section = _note("horn", A3, 0.6, players=4.0)
    assert section.shape[1] == 2 and not np.allclose(section[:, 0], section[:, 1])
    assert abs(_rms_db(section, 0.3, 0.6) - _rms_db(_note("horn", A3, 0.6), 0.3, 0.6)) < 0.5  # four players are as loud as one
    starts = [_rms_db(_note("horn", 110.0 * 2 ** (k / 12), 0.25, players=4.0), 0.1, 0.25) for k in range(0, 12, 2)]
    assert max(starts) - min(starts) < 1.5  # no note of a section is weak because its players began out of step
    without, with_tuba = (_note("low_brass", 110.0, 0.6, tuba=level, breath=0.0) for level in (0.0, 1.0))
    low = [float(p[(f > 45) & (f < 65)].sum() / p.sum()) for f, p in (_spectrum(y, 0.2, 0.6) for y in (without, with_tuba))]
    assert low[0] < 1e-4 and low[1] > 0.02  # the tuba's fundamental at 55 Hz
    muted = _note("trumpet", A4, mute=1.0, breath=0.0)
    freqs, power = _spectrum(muted, 0.4, 0.8)
    _, open_power = _spectrum(_note("trumpet", A4, breath=0.0), 0.4, 0.8)
    low = freqs < 700
    assert power[low].sum() / power.sum() < 0.3 * open_power[low].sum() / open_power.sum()


# ----- organ ---------------------------------------------------------------------------------------


def test_the_organ_holds_steadily_and_registrations_are_equally_loud() -> None:
    levels = []
    for k, name in enumerate(REGISTRATION_NAMES):
        y = _note("organ", 261.63, 1.2, registration=float(k))
        assert y.shape[1] == 2
        assert abs(_rms_db(y, 0.4, 0.6) - _rms_db(y, 1.0, 1.2)) < 0.1, name  # no decay while the key is down
        levels.append(_rms_db(y, 0.4, 1.2))
        peak = np.abs(y).max()
        assert np.abs(y[0]).max() < 1e-6 * peak and np.abs(y[-1]).max() < 1e-4 * peak, name
    assert max(levels) - min(levels) < 0.3, levels
    beating = _note("organ", 261.63, 1.2, registration=2.0, chorus=1.0)
    assert abs(_rms_db(beating, 0.4, 0.6) - _rms_db(beating, 1.0, 1.2)) > 0.3 or abs(_rms_db(beating, 0.6, 0.8) - _rms_db(beating, 0.8, 1.0)) > 0.3  # the chorus beats


def test_drawbars_set_the_ranks() -> None:
    y = _note("organ", 220.0, 0.8, registration=float(REGISTRATION_NAMES.index("drawbar")), drawbars=read_drawbars("00 8050 000", "x"))
    freqs, power = _spectrum(y, 0.2, 0.8)
    ranks = [float(power[np.abs(freqs - 220.0 * ratio) < 20].sum()) for ratio in (0.5, 1.0, 2.0, 3.0, 4.0)]
    assert ranks[0] < 1e-8 * ranks[1] and ranks[2] < 1e-8 * ranks[1] and ranks[4] < 1e-8 * ranks[1]  # only the 8' and the 2 2/3' sound
    assert 10 * math.log10(ranks[3] / ranks[1]) == pytest.approx(-9.0, abs=0.3)  # bar 5 is three steps of 3 dB under bar 8
    freqs, power = _spectrum(_note("organ", 130.81, 0.8, registration=0.0, chiff=0.0), 0.3, 0.8)  # cathedral: a 16' under the note
    assert power[(freqs > 60) & (freqs < 70)].sum() > 0.1 * power[(freqs > 125) & (freqs < 136)].sum()


def test_the_organ_has_no_click_unless_asked_and_no_aliases_at_the_top() -> None:
    drawbar = float(REGISTRATION_NAMES.index("drawbar"))
    quiet, clicked = (_note("organ", 261.63, 0.3, registration=drawbar, click=level) for level in (0.0, 1.0))

    def highs(y: np.ndarray) -> float:
        freqs, power = _spectrum(np.concatenate([np.zeros((480, 2)), y[: int(0.02 * RATE)]]), 0.0, 0.03)
        return float(power[freqs > 2000].sum())

    assert highs(clicked) > 1000 * highs(quiet)
    for k in range(len(REGISTRATION_NAMES)):
        y = _note("organ", 2093.0, 0.8, registration=float(k), chiff=0.0)
        freqs, power = _spectrum(y, 0.3, 0.7)
        assert power[freqs > HIGHEST_PARTIAL + 300].sum() < 1e-10 * power.sum()
        grid = 2093.0 / 16  # every rank and harmonic is a multiple of a sixteenth of the note (folded ranks too)
        near = np.abs(freqs / grid - np.round(freqs / grid)) * grid < 30.0
        assert power[~near].sum() < 1e-7 * power.sum(), REGISTRATION_NAMES[k]


# ----- the same note, the same sound ---------------------------------------------------------------------


@pytest.mark.parametrize("name", [*BRASS, "organ"])
def test_a_note_depends_on_its_seed_pitch_and_settings_only(name: str) -> None:
    again = [_note(name, A3, 0.3) for _ in range(2)]
    assert np.array_equal(again[0], again[1])
    assert not np.array_equal(again[0], _note(name, A3, 0.3, seed="studio:1:other"))
    make, s = INSTRUMENTS[name].make, {k: v.default for k, v in INSTRUMENTS[name].settings.items()}
    assert make is not None
    short = make(A3, 4800, s, "x")
    assert make(A3, 4800, dict(s), "x") is short and not short.flags.writeable  # a short note is made once
    assert make(A3, 3 * RATE, s, "x") is not make(A3, 3 * RATE, s, "x")


# ----- in a score ----------------------------------------------------------------------------------


def test_registration_names_and_drawbars_are_read() -> None:
    score = parse_music_score(_score({"instrument": "organ", "steps": "*", "settings": {"registration": "flute", "drawbars": "00 8400 000"},
                                      "sections": {"all": {"settings": {"registration": 3}}}}))
    track = score.tracks[0]
    assert track.instrument.range == ("C1", "C7") and next(iter(track.parts.values())).settings["drawbars"] == 8400000.0
    assert next(iter(track.parts.values())).settings["registration"] == 3.0
    assert read_drawbars(888000000, "x") == 888000000.0 and read_drawbars(0, "x") == 0.0 and read_drawbars("0", "x") == 0.0
    for settings, message in (
        ({"registration": "flutes"}, r"unknown name 'flutes'; did you mean 'flute'\? \(one of: cathedral, principal"),
        ({"registration": 1.5}, "registration"),
        ({"registration": 9}, "registration"),
        ({"drawbars": "00 8900 000"}, "nine drawbar digits 0 to 8 in quotes"),
        ({"drawbars": 8400000}, "quote it"),
        ({"drawbars": True}, "nine drawbar digits"),
        ({"stops": 1}, r"settings.stops: unknown key \(allowed: registration, drawbars"),
    ):
        with pytest.raises(VidgenError, match=message):
            parse_music_score(_score({"instrument": "organ", "steps": "*", "settings": settings}))
    with pytest.raises(VidgenError, match="players"):
        parse_music_score(_score({"instrument": "trumpet", "steps": "1", "settings": {"players": 9}}))


def test_the_catalogue_names_ranges_and_registrations() -> None:
    by_name = {i["name"]: i for i in patch_catalog()["instruments"]}
    assert [by_name[n]["group"] for n in (*BRASS, "organ")] == ["brass", "brass", "brass", "organ"]
    assert by_name["trumpet"]["range"] == ["E3", "C6"] and "range" not in by_name["piano"]
    assert by_name["organ"]["settings"]["registration"]["choices"] == list(REGISTRATION_NAMES)
    assert "choices" not in by_name["organ"]["settings"]["tone"]


@pytest.mark.slow
def test_two_tracks_in_unison_are_two_players_and_a_repeated_note_is_the_same_note() -> None:
    track = {"instrument": "trumpet", "steps": "A4 . A4 . A4 - - -", "settings": {"vibrato": 0}}
    one = parse_music_score({"key": "A minor", "tempo": 120, "bars": 1, "progression": "i", "loop": False, "tracks": {"a": track}})
    audio = render_music_score(one)
    step = one.samples // 8
    first, second = audio[:step], audio[2 * step : 3 * step]
    assert np.abs(first).max() > 0 and np.allclose(first[2000 : step - 2000], second[2000 : step - 2000], atol=1e-3 * np.abs(first).max())
    two = parse_music_score({"key": "A minor", "tempo": 120, "bars": 1, "progression": "i", "loop": False, "tracks": {"a": track, "b": dict(track)}})
    # the piece is brought to -28 LUFS either way: the same player twice would give the same samples
    assert not np.allclose(render_music_score(two)[:step], first, atol=1e-2 * np.abs(first).max())
