"""Syllables, a soloist and a whisper for the choir (Step 361, DESIGN.md §121.4): measured on
single notes (cheap); one short track through the renderer."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import INSTRUMENTS, parse_music_score
from vidgen.studio.choir import VOICES, VOWELS, held_vowels
from vidgen.studio.render import render_track_stem
from vidgen.studio.singing import CONSONANTS, SYLLABLES, bursts, is_plain, mouth, read_yes_no, syllable_parts

CHOIR = INSTRUMENTS["choir"]
D3, A3, C4 = 146.83, 220.0, 261.63


def _settings(**settings: float | str) -> dict[str, float]:
    out = {k: v.default for k, v in CHOIR.settings.items()}
    for name, value in settings.items():
        out[name] = float(CHOIR.settings[name].choices.index(value)) if isinstance(value, str) else float(value)
    return out


def _note(freq: float, held: float = 0.6, **settings: float | str) -> np.ndarray:
    s = _settings(**settings)
    assert CHOIR.make is not None
    return np.asarray(CHOIR.make(freq, int((held + s["ring"]) * RATE), s, "studio:1:t"), dtype=float)


def _mono(y: np.ndarray) -> np.ndarray:
    return y.mean(axis=1) if y.ndim == 2 else y


def _harmonics(y: np.ndarray, f0: float, start: float, end: float) -> np.ndarray:
    """dB of harmonics 1, 2, ... of ``f0`` (up to 4 kHz) between two seconds."""
    part = _mono(y)[int(start * RATE) : int(end * RATE)]
    power = np.abs(np.fft.rfft(part * np.hanning(len(part)), 8 * len(part))) ** 2
    freqs = np.fft.rfftfreq(8 * len(part), 1 / RATE)
    return np.array([10 * math.log10(power[np.abs(freqs / (h * f0) - 1) < 0.04].max() + 1e-30) for h in range(1, int(4000 / f0) + 1)])


def _strongest(levels: np.ndarray, f0: float, low: float, high: float) -> float:
    hz = f0 * np.arange(1, len(levels) + 1)
    inside = (hz >= low) & (hz <= high)
    return float(hz[inside][np.argmax(levels[inside])])


def _share(y: np.ndarray, start: float, end: float, low: float, high: float) -> float:
    part = _mono(y)[int(start * RATE) : int(end * RATE)]
    power = np.abs(np.fft.rfft(part * np.hanning(len(part)))) ** 2
    freqs = np.fft.rfftfreq(len(part), 1 / RATE)
    return 10 * math.log10(power[(freqs >= low) & (freqs < high)].sum() / power.sum())


def _off_harmonics(y: np.ndarray, f0: float, start: float, end: float) -> float:
    """dB of the power between the harmonics against the power on them (air against tone)."""
    part = _mono(y)[int(start * RATE) : int(end * RATE)]
    power = np.abs(np.fft.rfft(part * np.hanning(len(part)))) ** 2
    multiple = np.fft.rfftfreq(len(part), 1 / RATE) / f0
    on, keep = np.abs(multiple - np.round(multiple)) < 0.06, (multiple > 0.5) & (multiple * f0 < 12000)
    return 10 * math.log10(power[keep & ~on].sum() / power[keep & on].sum())


def _loudness(y: np.ndarray, start: float, end: float) -> float:
    from vidgen.loudness import integrated_loudness

    part = y[int(start * RATE) : int(end * RATE)]
    return integrated_loudness(part if part.ndim == 2 else np.stack([part, part], axis=1))


def _periods(y: np.ndarray, start: float, end: float) -> np.ndarray:
    part = _mono(y)[int(start * RATE) : int(end * RATE)]
    crossings = np.flatnonzero((part[:-1] < 0) & (part[1:] >= 0))
    return np.diff(crossings + part[crossings] / (part[crossings] - part[crossings + 1]))


def _score(steps: str, **settings: object) -> dict[str, object]:
    track: dict[str, object] = {"instrument": "choir", "steps": steps}
    if settings:
        track["settings"] = settings
    return {"key": "C major", "tempo": 120, "progression": "I", "loop": False, "sections": [{"name": "all", "bars": 1}], "tracks": {"t": track}}


# ----- names ------------------------------------------------------------------------------------------


def test_syllables_are_spelt_from_a_consonant_and_vowels_and_name_nothing_else() -> None:
    assert syllable_parts("la") == ("l", ("aah",)) and syllable_parts("noo") == ("n", ("ooh",)) and syllable_parts("dee") == ("d", ("ee",))
    assert syllable_parts("mm-ah") == ("", ("mm", "aah")) and syllable_parts("ah-oh") == ("", ("aah", "oh"))
    assert SYLLABLES[0] == "vowel" and {"la", "na", "da", "ma", "mm-ah", "ah-oh", "oo-ah"} <= set(SYLLABLES)
    for name in SYLLABLES[1:]:
        onset, vowels = syllable_parts(name)
        assert (onset in CONSONANTS or not onset) and all(v in VOWELS for v in vowels)
    others = {c for k, s in CHOIR.settings.items() if k != "syllable" for c in s.choices}
    assert not others & set(SYLLABLES)  # so [la] names one setting
    assert [read_yes_no(v, "x") for v in (True, False, "yes", "off", 1, 0.0)] == [1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    with pytest.raises(VidgenError, match="expected true or false"):
        read_yes_no("maybe", "x")


def test_a_note_that_asks_for_nothing_new_is_step_345s() -> None:
    s = _settings(vowel="aah")
    assert is_plain(s) and not is_plain(_settings(syllable="la")) and not is_plain(_settings(whisper=0.2)) and not is_plain(_settings(soloist=1))
    assert not is_plain(s, ((4800, 2.0, 2880, (1.0, 0.0)),)) and is_plain(s, ((4800, 2.0, 2880),))
    n = int(0.5 * RATE)
    assert np.array_equal(_note(C4, 0.1, vowel="aah"), held_vowels(C4, int((0.1 + s["ring"]) * RATE), s, "studio:1:t"))
    assert np.array_equal(CHOIR.make(C4, n, {**s, "singers": 1.0}, "x"), held_vowels(C4, n, {**s, "singers": 1.0}, "x"))


# ----- the mouth ----------------------------------------------------------------------------------------


def test_the_mouth_moves_from_the_consonant_into_the_vowel() -> None:
    keys = mouth(RATE, int(0.8 * RATE), _settings(syllable="na"))
    times = [at / RATE for at, _, _ in keys]
    assert keys[0][1] == (("h", "n", "aah"),) and keys[-1][1] == (("v", "aah"),) and keys[0][2] == CONSONANTS["n"].level and keys[-1][2] == 1.0
    assert times == sorted(times) and abs(times[-1] - CONSONANTS["n"].hold - CONSONANTS["n"].move) < 0.004
    assert bursts(keys) == [] and len(bursts(mouth(RATE, int(0.8 * RATE), _settings(syllable="da")))) == 1
    turned = mouth(2 * RATE, 2 * RATE, _settings(syllable="ah-oh", turn=0.25))
    assert turned[0][1] == (("v", "aah"),) and turned[-1][1] == (("v", "oh"),)
    assert abs((turned[1][0] + turned[-1][0]) / 2 / RATE - 0.5) < 0.01  # halfway at a quarter of the note


@pytest.mark.parametrize(("syllable", "zero"), [("ma", 950.0), ("na", 1800.0)])
def test_a_nasal_murmur_has_its_antiformant_and_opens_into_the_vowel(syllable: str, zero: float) -> None:
    note = _note(D3, 0.4, syllable=syllable, voices="tenors", singers=1, vibrato=0, breath=0)
    murmur, vowel = _harmonics(note, D3, 0.012, 0.05), _harmonics(note, D3, 0.25, 0.4)
    k = int(round(zero * 1.06 / D3)) - 1
    assert murmur[k] < (murmur[k - 2] + murmur[k + 2]) / 2 - 8  # a dip at the antiformant
    assert vowel[k] > (vowel[k - 2] + vowel[k + 2]) / 2 - 6  # gone in the vowel
    loud = lambda a, b: 10 * math.log10(float(np.mean(note[int(a * RATE) : int(b * RATE)] ** 2)))  # noqa: E731
    assert loud(0.015, 0.045) < loud(0.25, 0.4) - 6


def test_l_and_d_move_the_formants_as_they_open() -> None:
    lateral = _note(D3, 0.4, syllable="la", voices="tenors", singers=1, vibrato=0, breath=0)
    assert _strongest(_harmonics(lateral, D3, 0.012, 0.045), D3, 150, 1000) < 400 < _strongest(_harmonics(lateral, D3, 0.25, 0.4), D3, 150, 1000)
    stop = _note(D3, 0.4, syllable="da", voices="tenors", singers=1, vibrato=0, breath=0)
    closure = 10 * math.log10(float(np.mean(stop[int(0.005 * RATE) : int(0.03 * RATE)] ** 2)))
    vowel = 10 * math.log10(float(np.mean(stop[int(0.25 * RATE) : int(0.4 * RATE)] ** 2)))
    assert closure < vowel - 15 and _share(stop, 0.034, 0.045, 1500, 4000) > _share(stop, 0.25, 0.4, 1500, 4000) + 3  # a closure, then a soft burst
    assert _strongest(_harmonics(stop, D3, 0.04, 0.06), D3, 1300, 2500) > 1500  # the second formant starts high (the alveolar locus)


def _hiss(y: np.ndarray) -> float:
    """dB of the loudest 10 ms of a note above 5 kHz against its loudest 10 ms in all (onset,
    consonant, vowel and release alike)."""
    m = _mono(y)
    frames = m[np.arange(480)[None, :] + 240 * np.arange((len(m) - 480) // 240)[:, None]] * np.hanning(480)
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    return 10 * math.log10(power[:, np.fft.rfftfreq(480, 1 / RATE) >= 5000].sum(axis=1).max() / power.sum(axis=1).max())


@pytest.mark.parametrize(("voices", "freq"), [("basses", D3), ("sopranos", 2 * D3)])
def test_a_d_opens_softly_without_a_hiss_above_the_voice(voices: str, freq: float) -> None:
    # Step 363: the d's burst was noise up to 12 kHz over a voice with little above 4 kHz,
    # 22-26 dB under the note in this measure, heard as "sht" (a 2-3 s hiss in a hall's reverb).
    for syllable in ("la", "da", "de"):
        assert _hiss(_note(freq, 0.25, syllable=syllable, voices=voices)) < -50, syllable
    whispered = [_hiss(_note(freq, 0.25, syllable=syllable, voices=voices, whisper=1)) for syllable in ("la", "da")]
    assert whispered[1] < whispered[0] + 3  # whispered, a d is no louder up there than the whisper itself


def test_two_vowels_glide_at_turn_and_keep_the_level() -> None:
    note = _note(D3, 2.0, syllable="oo-ah", voices="tenors", singers=1, vibrato=0, breath=0)
    assert _strongest(_harmonics(note, D3, 0.6, 0.9), D3, 150, 1000) < 350 < _strongest(_harmonics(note, D3, 1.1, 1.4), D3, 150, 1000)
    rms = [float(np.mean(note[int(t * RATE) : int((t + 0.05) * RATE)] ** 2)) for t in np.arange(0.3, 1.8, 0.05)]
    assert 10 * math.log10(max(rms) / min(rms)) < 2.5


# ----- soloist and whisper ----------------------------------------------------------------------------


def test_a_soloist_is_one_brighter_voice_with_a_wider_later_vibrato_and_a_scoop() -> None:
    solo = _note(A3, 2.0, soloist=1, voices="tenors", breath=0)
    one = _note(A3, 2.0, singers=1, voices="tenors", breath=0)
    assert solo.ndim == 1 and _share(solo, 0.6, 1.6, 2000, 4000) > _share(one, 0.6, 1.6, 2000, 4000) + 6  # the singer's formant

    def swing(y: np.ndarray, start: float) -> float:
        periods = _periods(y, start, start + 0.2)
        return float(1200 * np.log2(periods.max() / periods.min()))

    assert swing(solo, 1.5) > 1.4 * swing(one, 1.5) and swing(solo, 0.35) < 0.7 * swing(one, 0.35)
    assert float(np.mean(_periods(solo, 0.0, 0.03))) > (RATE / A3) * 2 ** (20 / 1200)  # 20 cents or more under the note as it starts
    assert abs(_loudness(solo, 0.5, 1.5) - _loudness(_note(A3, 2.0, voices="tenors"), 0.5, 1.5)) < 1.5


def test_whisper_turns_the_tone_into_breath_at_about_the_same_loudness() -> None:
    sung, breathy, whispered = (_note(C4, 1.0, vowel="aah", whisper=w) for w in (0.0, 0.5, 1.0))
    ratios = [_off_harmonics(y, C4, 0.3, 0.9) for y in (sung, breathy, whispered)]
    assert ratios[0] < -18 and ratios[0] + 10 < ratios[1] < ratios[2] - 6 and ratios[2] > 6  # 6 dB: the share of noise between the harmonics
    louds = [_loudness(y, 0.3, 0.9) for y in (sung, breathy, whispered)]
    assert max(louds) - min(louds) < 2.0
    assert _share(whispered, 0.3, 0.9, 500, 1200) > _share(whispered, 0.3, 0.9, 1500, 2200) + 3  # the noise keeps the vowel's formants


# ----- in a score ----------------------------------------------------------------------------------


def test_syllables_and_the_new_settings_are_read_in_a_score_with_their_errors() -> None:
    score = parse_music_score(_score("[la] C4 [mm-ah] D4 [syllable=da] E4 [default] F4", syllable="na", soloist=True, whisper=0.3))
    part = next(iter(score.tracks[0].parts.values()))
    assert part.settings["syllable"] == SYLLABLES.index("na") and part.settings["soloist"] == 1.0 and part.settings["whisper"] == 0.3
    steps = [s for s in part.steps[0] if s.sounds]
    assert [dict(s.changes).get("syllable") for s in steps] == [SYLLABLES.index(n) for n in ("la", "mm-ah", "da")] + [None]
    for steps, words, settings in (("[lah] C4", "unknown mark; did you mean 'la'?", {}), ("[syllable=nah] C4", "unknown name 'nah'; did you mean 'na'?", {}),
                                   ("C4", "unknown name 'mm-aah'; did you mean 'mm-ah'?", {"syllable": "mm-aah"}),
                                   ("[soloist=perhaps] C4", "expected true or false", {}), ("C4", "expected true or false", {"soloist": "loud"}),
                                   ("(C4 [whisper=1] D4)", "only glide, syllable and vowel may change there", {})):
        with pytest.raises(VidgenError, match=words.replace("?", r"\?").replace("(", r"\(")):
            parse_music_score(_score(steps, **settings))


def test_a_slurred_note_sings_a_consonant_only_where_one_is_written() -> None:
    def track(steps: str) -> np.ndarray:
        return _mono(np.asarray(render_track_stem(parse_music_score(_score(steps, singers=1, breath=0, vibrato=0)), "t").piece, dtype=float))

    on, written = track("[la] (C4 - - - D4 - - -)"), track("[la] (C4 - - - [na] D4 - - -)")
    level = lambda y, a, b: 10 * math.log10(float(np.mean(y[int(a * RATE) : int(b * RATE)] ** 2)))  # noqa: E731
    assert np.allclose(on[: int(0.97 * RATE)], written[: int(0.97 * RATE)], rtol=0, atol=1e-12)  # the same until the vowel closes into the n
    assert level(written, 1.01, 1.05) < level(on, 1.01, 1.05) - 5 and abs(level(on, 1.01, 1.05) - level(on, 0.6, 0.9)) < 1.5
    assert abs(level(written, 1.3, 1.8) - level(on, 1.3, 1.8)) < 1.0
