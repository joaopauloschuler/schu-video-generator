"""The bowed strings of score files (Step 344): what makes them strings is
measured on single notes (cheap: a score is rendered in one slow test only)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import INSTRUMENTS, parse_music_score, patch_catalog, render_music_score
from vidgen.studio.additive import HIGHEST_PARTIAL, read_tables, wavetables
from vidgen.studio.strings import BASS, CELLO, STROKES, VIOLA, VIOLIN, _rosin_room, bowed, response

STRINGS = ("violins", "violas", "cellos", "double_basses")
SUSTAIN, SPICCATO, TREMOLO, PIZZICATO = (float(k) for k in range(4))
A4, G2 = 440.0, 98.0


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


def _harmonics(y: np.ndarray, freq: float, count: int, start: float = 0.3, end: float = 0.8) -> np.ndarray:
    """The power of the first ``count`` harmonics of ``freq`` in the held part."""
    freqs, power = _spectrum(y, start, end)
    return np.array([power[np.abs(freqs - h * freq) < 0.03 * h * freq + 6].sum() for h in range(1, count + 1)])


def _level(y: np.ndarray, window: float = 0.01) -> np.ndarray:
    size = int(window * RATE)
    return np.sqrt(np.convolve(_mono(y) ** 2, np.ones(size) / size, mode="same"))


def _score(track: dict[str, object], bars: int = 1) -> dict[str, object]:
    return {"key": "A minor", "tempo": 138, "progression": "i", "loop": False, "sections": [{"name": "all", "bars": bars}], "tracks": {"t": track}}


# ----- the body --------------------------------------------------------------------------------------


def test_wavetables_take_a_phase_per_harmonic() -> None:
    tables = wavetables(np.array([[1.0, 0.5]]), np.array([0.25, 0.5]))
    x = np.linspace(0.0, 2.0, 500)
    assert np.allclose(read_tables(tables, x), np.sin(2 * np.pi * (x + 0.25)) + 0.5 * np.sin(2 * np.pi * (2 * x + 0.5)), atol=1e-4)


@pytest.mark.parametrize("name,body,low", [("violins", VIOLIN, 55), ("cellos", CELLO, 36)])
def test_the_body_resonances_stay_where_they_are_when_the_pitch_changes(name: str, body: object, low: int) -> None:
    """A harmonic's level, less the string's own, is the body's response at that harmonic's
    frequency, whichever note it belongs to and whichever harmonic it is."""
    measured, expected = [], []
    for midi in range(low, low + 25, 3):
        freq = 440.0 * 2 ** ((midi - 69) / 12)
        got = _harmonics(_note(name, freq, players=1.0, vibrato=0.0, bow=0.0), freq, 8)
        string = bowed(body, freq, 0.5)[:8]  # type: ignore[arg-type]
        level, body_db = 10 * np.log10(got) - 20 * np.log10(string), response(body, freq * np.arange(1, 9))  # type: ignore[arg-type]
        measured += list(level - level.mean())  # every note is set to the same loudness: its own offset
        expected += list(body_db - body_db.mean())
    assert np.corrcoef(measured, expected)[0, 1] > 0.98 and float(np.abs(np.subtract(measured, expected)).max()) < 1.5
    # the body is not a filter that follows the note: the second harmonic is strong at one pitch and weak at another
    second = [float(np.diff(10 * np.log10(_harmonics(_note(name, f, players=1.0, vibrato=0.0, bow=0.0), f, 2)))[0]) for f in (body.air * 0.5, body.air * 0.72, body.air * 1.3)]  # type: ignore[attr-defined]
    assert max(second) - min(second) > 4.0


def test_the_four_bodies_have_their_air_resonance_and_bridge_hill_in_order() -> None:
    bodies = (VIOLIN, VIOLA, CELLO, BASS)
    assert [b.air for b in bodies] == sorted((b.air for b in bodies), reverse=True)
    for body in bodies:
        hill = body.formants[-1][0]
        freqs = np.array([0.4 * body.air, body.air, 0.55 * hill, hill, 4 * body.top])
        # averaged over the players' instruments (each has its own narrow resonances)
        db = np.mean([response(body, freqs, player) for player in range(8)], axis=0)
        assert db[0] < db[1] - 10 and db[3] > db[2] + 2 and db[4] < db[3] - 15
        muted = np.mean([response(body, freqs, player, 1.0) for player in range(8)], axis=0)
        assert muted[3] < db[3] - 8 and abs(muted[1] - db[1]) < 3


# ----- sustained notes -------------------------------------------------------------------------------


def test_vibrato_comes_late_and_moves_the_harmonics_levels() -> None:
    y = _note("violins", A4, 1.6, players=1.0, bow=0.0, vibrato=20.0)
    turned = y * np.exp(-2j * np.pi * A4 * np.arange(len(y)) / RATE)
    phase = np.unwrap(np.angle(np.convolve(turned, np.hanning(960) / 480, mode="same")))
    cents = 1200 * np.log2(1 + np.gradient(phase) * RATE / (2 * np.pi) / A4)
    assert np.ptp(cents[int(0.05 * RATE) : int(0.15 * RATE)]) < 6 and 30 < np.ptp(cents[int(0.8 * RATE) : int(1.5 * RATE)]) < 50

    def swing(note: np.ndarray, harmonic: int) -> float:
        window = np.hanning(int(0.03 * RATE))
        track = np.abs(np.convolve(note * np.exp(-2j * np.pi * harmonic * A4 * np.arange(len(note)) / RATE), window / window.sum(), mode="same"))
        part = track[int(0.8 * RATE) : int(1.5 * RATE)]
        return 20 * math.log10(float(part.max() / part.min()))

    still = _note("violins", A4, 1.6, players=1.0, bow=0.0, vibrato=0.0)
    assert max(swing(y, h) for h in (4, 6, 8, 10)) > 2.5 and max(swing(still, h) for h in (4, 6, 8, 10)) < 0.5


def test_attack_brightness_mute_and_release() -> None:
    def rise(attack: float) -> float:
        level = _level(_note("violas", 293.66, 1.4, players=1.0, attack=attack))
        return float(np.argmax(level > 0.9 * np.median(level[int(0.9 * RATE) : int(1.3 * RATE)]))) / RATE

    assert rise(0.03) < 0.035 and 0.05 < rise(0.1) < 0.1 and 0.3 < rise(0.5) < 0.5
    dark, plain, glassy = (_note("violins", A4, players=1.0, bow=0.0, vibrato=0.0, brightness=b) for b in (0.0, 0.5, 1.0))
    assert _centroid(dark, 0.3, 0.8) < 0.75 * _centroid(plain, 0.3, 0.8) and _centroid(glassy, 0.3, 0.8) > 1.8 * _centroid(plain, 0.3, 0.8)
    assert max(abs(_rms_db(y, 0.3, 0.8) - _rms_db(plain, 0.3, 0.8)) for y in (dark, glassy)) < 3.0
    muted = _note("violins", A4, players=1.0, bow=0.0, vibrato=0.0, mute=1.0)
    freqs, power = _spectrum(muted, 0.3, 0.8)
    _, open_power = _spectrum(plain, 0.3, 0.8)
    hill = (freqs > 2000) & (freqs < 3600)
    assert power[hill].sum() / power.sum() < 0.25 * open_power[hill].sum() / open_power.sum()
    # the release darkens as it dies, and both ends are silent
    assert _centroid(plain, 0.92, 1.02) < 0.9 * _centroid(plain, 0.3, 0.8)
    for y in (plain, _note("cellos", G2, 0.3), _note("violins", A4, 0.2, stroke=SPICCATO), _note("double_basses", 55.0, 0.3, stroke=PIZZICATO), _note("violas", 220.0, 0.4, stroke=TREMOLO)):
        peak = np.abs(y).max()
        assert np.abs(y[0]).max() < 1e-6 * peak and np.abs(y[-1]).max() < 1e-4 * peak


def test_a_slow_soft_swell_has_no_breath_above_its_tone() -> None:
    """Step 366: Parallel Space's `swell` (violas, F#3, attack 0.6, brightness 0.25, ring 1.2) made
    a "fo": the rosin hiss stood 1 to 27 dB over the dark tone above 4 kHz while it swelled in
    and died away. The hiss is now held within the tone's highs."""
    swell = {"attack": 0.6, "brightness": 0.25, "vibrato": 10.0, "ring": 1.2, "accent": 0.0}
    tone, played = (_mono(_note("violas", 185.0, 0.87, bow=bow, **swell)) for bow in (0.0, 1.0))
    noise = played - tone
    size = int(0.05 * RATE)
    highs = np.fft.rfftfreq(size, 1 / RATE) >= 4000

    def above_4k(y: np.ndarray, start: float) -> float:
        part = y[int(start * RATE) : int(start * RATE) + size] * np.hanning(size)
        return float(np.sum(np.abs(np.fft.rfft(part))[highs] ** 2))

    swelling_and_dying = [*np.arange(0.0, 0.55, 0.05), *np.arange(0.9, 1.9, 0.05)]
    worst = max(10 * math.log10(above_4k(noise, t) / above_4k(tone, t)) for t in swelling_and_dying)
    assert worst < -3.0  # Step 344: +27 dB
    assert 10 * math.log10(np.sum(noise**2) / np.sum(tone**2)) < -45.0  # Step 344: -33 dB
    # the noise does not lead the tone: it comes within 20 dB of its peak no sooner, and in the
    # note's first 150 ms (from 30 dB under the tone's peak) it stays far under the tone
    tone_level, noise_level = _level(tone, 0.025), _level(noise, 0.025)
    begins = int(np.argmax(tone_level > 10 ** (-30 / 20) * tone_level.max()))
    assert np.argmax(noise_level > 0.1 * noise_level.max()) >= np.argmax(tone_level > 0.1 * tone_level.max())
    first = slice(begins, begins + int(0.15 * RATE))
    assert 10 * math.log10(np.sum(noise[first] ** 2) / np.sum(tone[first] ** 2)) < -45.0  # Step 344: -32 dB


def test_an_ordinary_note_keeps_its_rosin_at_full_bow() -> None:
    """The limit of Step 366 leaves a note at full bow with ``brightness`` 0.5 or more as it was;
    it takes the hiss down only where the tone is darker (a dark note, a swell, a release)."""
    for name, body, freqs in (("violins", VIOLIN, (196.0, 440.0, 2093.0)), ("violas", VIOLA, (130.8, 293.7, 1318.5)), ("cellos", CELLO, (65.4, 196.0, 880.0)),
                              ("double_basses", BASS, (32.7, 55.0, 392.0))):
        s = {k: v.default for k, v in INSTRUMENTS[name].settings.items()}
        for freq in freqs:
            for change in ({}, {"mute": 1.0}, {"stroke": TREMOLO}):
                room = _rosin_room(body, freq, s | change, np.array([0.0, 1.0]))
                assert room[1] == 1.0 and room[0] < 1.0  # the release, darker, has less
            assert np.all(_rosin_room(body, freq, s | {"brightness": 0.8}, np.array([0.0, 1.0])) == 1.0)  # a bright note's release is as dark as an ordinary note
            assert _rosin_room(body, freq, s | {"brightness": 0.25}, np.array([1.0]))[0] < 0.3


@pytest.mark.parametrize("name,freqs", [("violins", (196.0, 440.0, 1318.5, 2093.0)), ("violas", (130.8, 293.7, 1318.5)), ("cellos", (65.4, 196.0, 880.0)),
                                        ("double_basses", (32.7, 55.0, 392.0))])
def test_strings_are_as_loud_at_every_pitch_and_alias_nothing(name: str, freqs: tuple[float, ...]) -> None:
    from vidgen.loudness import integrated_loudness

    loud = []
    for freq in freqs:
        y = _note(name, freq, 1.1)
        loud.append(integrated_loudness(y))
        assert y.shape[1] == 2
    assert max(loud) - min(loud) < 1.0 and -17.6 < float(np.mean(loud)) < -15.8, loud  # the level of the brass (about -16.5 LUFS)
    y = _note(name, freqs[-1], 1.0, players=1.0, vibrato=0.0, bow=0.0, brightness=1.0)
    spectrum_freqs, power = _spectrum(y, 0.3, 0.9)
    assert power[spectrum_freqs > HIGHEST_PARTIAL + 300].sum() < 1e-10 * power.sum()
    top = freqs[-1]
    near = np.abs(spectrum_freqs / top - np.round(spectrum_freqs / top)) * top < np.maximum(spectrum_freqs * 0.035, 14.0)
    assert power[~near].sum() < 1e-7 * power.sum()


def test_a_section_is_wide_beats_in_its_harmonics_and_holds_its_level() -> None:
    solo, section = _note("violins", A4, 2.0, players=1.0), _note("violins", A4, 2.0)
    assert solo.ndim == 1 and section.shape[1] == 2
    assert 0.3 < np.corrcoef(section[24000:96000, 0], section[24000:96000, 1])[0, 1] < 0.9
    frames = [[_rms_db(y, a, a + 0.1) for a in np.arange(0.4, 1.9, 0.1)] for y in (solo, section)]
    assert np.ptp(frames[0]) < 1.0 and np.ptp(frames[1]) < 1.0  # no slow swell and fade by chance
    assert abs(float(np.mean(frames[0])) - float(np.mean(frames[1]))) < 1.0  # six players are as loud as one
    sides = _rms_db(section[:, 0], 0.4, 1.9) - _rms_db(section[:, 1], 0.4, 1.9)
    assert abs(sides) < 0.6  # it does not lean to one side

    def swing(note: np.ndarray) -> float:
        window = np.hanning(int(0.03 * RATE))
        track = np.abs(np.convolve(_mono(note) * np.exp(-2j * np.pi * 3 * A4 * np.arange(len(note)) / RATE), window / window.sum(), mode="same"))
        part = track[int(0.5 * RATE) : int(1.9 * RATE)]
        return 20 * math.log10(float(np.percentile(part, 95) / np.percentile(part, 5)))

    assert swing(section) > 4 * swing(_note("violins", A4, 2.0, players=1.0, vibrato=0.0)) and swing(section) > 6.0  # the players beat against each other


# ----- short strokes, tremolo ------------------------------------------------------------------------


@pytest.mark.parametrize("name,low", [("violins", 57), ("cellos", 38)])
def test_spiccato_is_the_same_at_every_pitch_and_every_time(name: str, low: int) -> None:
    held = 0.108  # a sixteenth at 138 BPM
    energies, sides = [], []
    for midi in range(low, low + 13):
        y = _note(name, 440.0 * 2 ** ((midi - 69) / 12), held, stroke=SPICCATO, bow=0.0)
        energies.append(10 * math.log10(float(np.sum(y**2))))
        sides.append(10 * math.log10(float(np.sum(y[:, 0] ** 2) / np.sum(y[:, 1] ** 2))))
        level = _level(y, 0.02)
        peak = int(np.argmax(level))
        assert peak < 0.09 * RATE and level[int(0.3 * RATE)] < 0.1 * level[peak]  # a stroke, then it rings out
    assert np.ptp(energies) < 2.0 and np.std(energies) < 0.7 and np.abs(sides).max() < 0.8, energies
    y = _note(name, A4 / 2, held, stroke=SPICCATO)
    assert np.array_equal(y, _note(name, A4 / 2, held, stroke=SPICCATO))
    solo = _note(name, A4 / 2, held, stroke=SPICCATO, players=1.0)
    level = _level(solo, 0.004)
    assert np.argmax(level > 0.5 * level.max()) < 0.012 * RATE  # the bow bites within a hundredth of a second
    longer = _note(name, A4 / 2, 0.3, stroke=SPICCATO, players=1.0, length=0.2)
    assert _rms_db(longer, 0.12, 0.2) > _rms_db(_note(name, A4 / 2, 0.3, stroke=SPICCATO, players=1.0), 0.12, 0.2) + 6
    hard, smooth = (_note(name, A4 / 2, held, stroke=SPICCATO, players=1.0, accent=a) for a in (2.0, 0.0))
    assert _rms_db(hard, 0.0, 0.03) > _rms_db(smooth, 0.0, 0.03) + 1.5 and _centroid(hard, 0.0, 0.03) > 1.15 * _centroid(smooth, 0.0, 0.03)


def test_tremolo_is_fast_bow_strokes_and_a_section_shimmers() -> None:
    def strokes(y: np.ndarray) -> tuple[float, float]:
        level = _level(y, 0.012)[int(0.6 * RATE) : int(2.4 * RATE)]
        spectrum = np.abs(np.fft.rfft((level - level.mean()) * np.hanning(len(level)), 1 << 18))
        freqs = np.fft.rfftfreq(1 << 18, 1 / RATE)
        band = (freqs > 4) & (freqs < 30)
        return float(freqs[band][np.argmax(spectrum[band])]), 20 * math.log10(float(np.percentile(level, 95) / np.percentile(level, 5)))

    solo = _note("violins", A4, 2.6, stroke=TREMOLO, players=1.0)
    speed, dip = strokes(solo)
    assert 12.0 < speed < 14.0 and 4.0 < dip < 12.0
    assert 8.0 < strokes(_note("violins", A4, 2.6, stroke=TREMOLO, players=1.0, speed=9.0))[0] < 10.0
    assert strokes(_note("violins", A4, 2.6, stroke=TREMOLO))[1] < dip  # the players are not in step
    assert abs(_rms_db(solo, 0.6, 2.4) - _rms_db(_note("violins", A4, 2.6, players=1.0), 0.6, 2.4)) < 1.0


def test_pizzicato_rings_longer_on_low_strings_and_loses_its_highs_first() -> None:
    def fallen(name: str, freq: float) -> float:
        level = _level(_note(name, freq, 3.0, stroke=PIZZICATO, players=1.0), max(0.006, 2 / freq))
        peak = int(np.argmax(level))
        return float(np.argmax(level[peak:] < 0.1 * level[peak])) / RATE

    assert fallen("double_basses", 55.0) > 2 * fallen("violins", A4) > 4 * 0.05
    y = _note("cellos", G2, 1.5, stroke=PIZZICATO, players=1.0)
    assert _centroid(y, 0.5, 0.9) < 0.75 * _centroid(y, 0.0, 0.1)
    assert int(np.sum(_harmonics(y, G2, 40, 0.0, 0.08) > 1e-4 * _harmonics(y, G2, 40, 0.0, 0.08).max())) > 12  # the old `pizzicato` has five
    damped = _note("cellos", G2, 0.2, stroke=PIZZICATO, players=1.0)
    assert _rms_db(damped, 0.4, 0.45) < _rms_db(y, 0.4, 0.45) - 20  # it rings until its steps end


# ----- the same note, the same sound ---------------------------------------------------------------------


@pytest.mark.parametrize("name", STRINGS)
def test_a_string_note_depends_on_its_seed_pitch_and_settings_only(name: str) -> None:
    for stroke in (SUSTAIN, SPICCATO, TREMOLO, PIZZICATO):
        again = [_note(name, 220.0, 0.15, stroke=stroke) for _ in range(2)]
        assert np.array_equal(again[0], again[1])
        assert not np.array_equal(again[0], _note(name, 220.0, 0.15, stroke=stroke, seed="studio:1:other"))
    make, s = INSTRUMENTS[name].make, {k: v.default for k, v in INSTRUMENTS[name].settings.items()}
    assert make is not None
    short = make(220.0, 4800, s, "x")
    assert make(220.0, 4800, dict(s), "x") is short and not short.flags.writeable  # a short note is made once


# ----- in a score ----------------------------------------------------------------------------------


def test_strokes_are_named_in_a_score_and_the_catalogue_lists_the_family() -> None:
    score = parse_music_score(_score({"instrument": "cellos", "steps": "1 5 8 5", "settings": {"stroke": "spiccato"},
                                      "sections": {"all": {"settings": {"stroke": "tremolo", "players": 1}}}}))
    part = next(iter(score.tracks[0].parts.values()))
    assert part.settings["stroke"] == float(STROKES.index("tremolo")) and score.tracks[0].instrument.range == ("C2", "A5")
    for settings, message in (({"stroke": "spicato"}, r"unknown name 'spicato'; did you mean 'spiccato'\? \(one of: sustain, spiccato, tremolo, pizzicato\)"),
                              ({"players": 13}, "players"), ({"bowing": 1}, r"settings.bowing: unknown key")):
        with pytest.raises(VidgenError, match=message):
            parse_music_score(_score({"instrument": "violins", "steps": "1", "settings": settings}))
    by_name = {i["name"]: i for i in patch_catalog()["instruments"]}
    assert [by_name[n]["group"] for n in STRINGS] == ["strings"] * 4
    assert [by_name[n]["range"] for n in STRINGS] == [["G3", "C7"], ["C3", "E6"], ["C2", "A5"], ["C1", "G4"]]
    assert by_name["violins"]["settings"]["stroke"]["choices"] == list(STROKES)
    assert by_name["pizzicato"]["group"] == "plucks and keys"  # the old pluck stays


@pytest.mark.slow
def test_an_ostinato_of_sixteenths_repeats_exactly_and_is_made_from_few_notes() -> None:
    track = {"instrument": "cellos", "octave": 2, "settings": {"stroke": "spiccato"}, "steps": "1 5 8 1 5 8 5 3 1 5 8 1 5 8 5 3"}
    score = parse_music_score(_score(track, bars=3))
    audio = render_music_score(score)
    bar = score.samples // 3
    second, third = audio[bar : 2 * bar], audio[2 * bar : 3 * bar]
    assert np.abs(second).max() > 0 and np.allclose(second[: bar - 2000], third[: bar - 2000], atol=1e-3 * np.abs(second).max())
    step = bar / 16
    energy = [float(np.sum(second[int(k * step) : int((k + 1) * step)] ** 2)) for k in range(16)]
    assert 10 * math.log10(max(energy) / min(energy)) < 3.0  # four pitches, their tails overlapping
