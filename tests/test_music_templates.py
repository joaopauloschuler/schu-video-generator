"""Templates of the built-in beds (Step 186, DESIGN.md §93.8): the score-file features they need
(voicing notes, notes played together, the bass an octave up, the pads' swell and centred sub,
the snap), ``vidgen music template``, and each template against its bed by measurements."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen import cli, loudness, music
from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio import load_music_score, measure, music_template_catalog, music_template_text, parse_music_score, render_music_score
from vidgen.studio.patterns import ACCENT_GAIN, SOFT_GAIN, parse_steps
from vidgen.studio.render import _Voicer
from vidgen.studio.templates import TEMPLATE_DIR, template_path

#: The beds' measurements (:func:`profile`), kept so the tests render only the templates: the
#: beds are byte-identical (``tests/test_music.py`` fingerprints) and one is measured again below.
BED_MEASURES = Path(__file__).parent / "data" / "studio" / "bed_measures.json"


def _score(tracks: dict[str, Any], **changes: Any) -> Any:
    data: dict[str, Any] = {
        "key": "D minor", "tempo": 120, "bars": 4, "chord_bars": 2, "seed": 2,
        "progression": [{"chord": "Dm(add9)", "notes": ["D3", "A3", "E4", "F4"], "bass": "D2"}, "Bb"],
        "tracks": tracks,
    }
    data.update(changes)
    return parse_music_score(data)


# ----- the format's new pieces -------------------------------------------------------------------------


def test_voicing_notes_stacks_and_octave_hits_are_read() -> None:
    (bar,) = parse_steps("v1 v3' v9, v2+v3+v4? x' X, C4+E4!", "s")
    assert [(s.kind, s.value, s.octaves) for s in bar[:3]] == [("voice", 1, 0), ("voice", 3, 1), ("voice", 9, -1)]
    stack = bar[3]
    assert stack.kind == "stack" and [p.value for p in stack.parts] == [2, 3, 4] and stack.gain == SOFT_GAIN and stack.pitched
    assert (bar[4].kind, bar[4].octaves, bar[4].pitched) == ("hit", 1, True)
    assert (bar[5].octaves, bar[5].gain) == (-1, ACCENT_GAIN)
    assert [p.kind for p in bar[6].parts] == ["note", "note"] and bar[6].gain == ACCENT_GAIN
    assert not parse_steps("x X o", "s")[0][0].pitched
    for bad, words in (("+v1", "must join"), ("v1+", "ends with '+'"), ("v1+x", "cannot follow '+'"), ("v1+|v2", "before '|'"),
                       ("v0", "v1 to v9"), (".'", "only a hit"), ("v1++v2", "must join")):
        with pytest.raises(VidgenError, match=words.replace("+", r"\+").replace("|", r"\|")):
            parse_steps(bad, "s")


def test_voicing_notes_follow_the_written_or_played_voicing() -> None:
    score = _score({"arp": {"instrument": "pluck", "steps": "v1 v2 v4 v5 v6' x' v2+v3"}})
    part = score.tracks[0].parts["main"]
    (bar,) = part.steps
    written, played = score.sections[0].chords  # Dm(add9) written out, then Bb voiced by the track
    voicer = _Voicer()
    pitches = [voicer.pitches(step, written, part) for step in bar]
    # D3 A3 E4 F4: v5 starts again an octave up (D4), v6' is A3 two octaves up; x' the written bass D2 up an octave
    assert pitches == [(50,), (57,), (65,), (62,), (81,), (50,), (57, 64)]
    assert voicer.pitches(bar[0], played, part) == (62,)  # Bb voiced in the pluck's octave 4, led from Dm(add9): D4 F4 Bb4
    with pytest.raises(VidgenError, match="has no pitch"):
        _score({"k": {"instrument": "kick", "steps": "x' . . ."}})


def test_pad_swell_moves_the_airy_layer_and_the_sub_is_centred() -> None:
    def airy_level(swell: float) -> np.ndarray:
        score = _score({"pad": {"instrument": "pad", "play": "chords", "settings": {"tone": 5000, "air": 1.0, "swell": swell, "sub": 0.5}}})
        x = render_music_score(score).astype(np.float64)
        f = np.fft.rfftfreq(len(x), 1 / RATE)
        high = np.fft.irfft(np.fft.rfft(x, axis=0) * (f > 3000)[:, None], len(x), axis=0)
        low = np.fft.irfft(np.fft.rfft(x, axis=0) * (f < 60)[:, None], len(x), axis=0)
        assert np.corrcoef(low[:, 0], low[:, 1])[0, 1] > 0.99  # the sub is the same on both sides
        quarter = len(x) // 4
        return np.array([np.sqrt(np.mean(high[k * quarter : (k + 1) * quarter] ** 2)) for k in range(4)])

    steady, swelling = airy_level(0), airy_level(4)
    assert steady.max() / steady.min() < 1.5
    assert swelling[1] > 3 * swelling[0] and swelling[2] > 3 * swelling[3]  # silent at the start and end, full in the middle


def test_pad_sub_width_gives_each_side_its_own_sub() -> None:
    """Step 190: ``sub_width: 1`` brings back the Step 185 sub (its own phases on each side; the
    built-in ``skyline`` keeps it); 0, the default, is the centred sub; between, a cross-fade."""
    def low_correlation(width: float) -> float:
        data = {"key": "A minor", "tempo": 120, "bars": 2, "progression": "i",
                "tracks": {"pad": {"instrument": "pad", "play": "chords", "settings": {"tone": 300, "air": 0, "sub": 1.0, "sub_width": width}}}}
        x = render_music_score(parse_music_score(data)).astype(np.float64)
        f = np.fft.rfftfreq(len(x), 1 / RATE)
        low = np.fft.irfft(np.fft.rfft(x, axis=0) * ((f > 80) & (f < 160))[:, None], len(x), axis=0)
        return float(np.corrcoef(low[:, 0], low[:, 1])[0, 1])

    centred, half, wide = low_correlation(0), low_correlation(0.5), low_correlation(1)
    assert centred > 0.999 and wide < 0.9 and wide < half < centred


def test_pad_sub_plays_the_written_bass() -> None:
    def sub_peak(bass: str) -> float:
        data = {"key": "A minor", "tempo": 120, "bars": 2, "progression": [{"chord": "Am", "notes": ["A3", "C4", "E4"], "bass": bass}],
                "tracks": {"pad": {"instrument": "pad", "play": "chords", "settings": {"tone": 300, "air": 0, "sub": 1.0}}}}
        x = render_music_score(parse_music_score(data)).astype(np.float64).mean(axis=1)
        f = np.fft.rfftfreq(len(x), 1 / RATE)
        power = np.abs(np.fft.rfft(x)) ** 2 * (f < 150)
        return float(f[np.argmax(power)])

    assert sub_peak("A1") == pytest.approx(55.0, abs=1.0)
    assert sub_peak("A2") == pytest.approx(110.0, abs=1.0)


# ----- the templates and the command ---------------------------------------------------------------------


def test_every_bed_has_a_template_that_reads() -> None:
    catalog = music_template_catalog()
    assert [t["name"] for t in catalog] == list(music.BUILTIN_BEDS)
    for t in catalog:
        bed = music.BUILTIN_BEDS[t["name"]]
        text = music_template_text(t["name"])
        assert text.startswith(f"# {t['title'].split(' (')[0]}: a score-file template of vidgen's built-in bed `{t['name']}`")
        assert sum(line.lstrip().startswith("#") for line in text.splitlines()) >= 5  # comments explain the parts
        assert t["tempo"] == (bed.tempo or 64) and t["seconds"] == pytest.approx(bed.seconds, rel=1e-3)
        assert t["key"].split()[0] == bed.key.replace("F-sharp", "F#").split()[0]
    with pytest.raises(VidgenError, match="did you mean 'neon'"):
        template_path("noen")


def test_music_template_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["music", "template"]) == 0
    listing = capsys.readouterr().out
    assert all(name in listing for name in music.BUILTIN_BEDS) and "ascent        A minor     136 BPM" in listing
    out = tmp_path / "my_theme.yaml"
    assert cli.main(["music", "template", "lullaby", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Lullaby (template): F major, 64 BPM, 3/4, 16 bars = 45.00 s" in text and f"wrote: {out}" in text
    assert out.read_text(encoding="utf-8") == (TEMPLATE_DIR / "lullaby.yaml").read_text(encoding="utf-8")
    assert cli.main(["music", "template", "lullaby", "--out", str(out)]) == 1
    assert "exists" in capsys.readouterr().err
    assert cli.main(["music", "template", "neon", "--out", str(out), "--force", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["action"] == "template" and doc["template"]["name"] == "neon" and len(doc["templates"]) == 17
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["title"] == "Neon (template)"
    assert cli.main(["music", "template", "--json"]) == 0
    assert "template" not in json.loads(capsys.readouterr().out)
    assert cli.main(["music", "template", "lulaby"]) == 1
    assert "did you mean 'lullaby'" in capsys.readouterr().err
    assert cli.main(["music", "template", "neon", "--out", str(tmp_path / "x.txt")]) == 1
    # Step 192: time_of_flight's template is its bed's own score
    tof = tmp_path / "tof.yaml"
    assert cli.main(["music", "template", "time_of_flight", "--out", str(tof)]) == 0
    assert "Time of Flight: B minor, 108 BPM, 4/4, 24 bars = 53.33 s" in capsys.readouterr().out
    assert tof.read_text(encoding="utf-8") == (TEMPLATE_DIR / "time_of_flight.yaml").read_text(encoding="utf-8")


# ----- each template against its bed --------------------------------------------------------------------
#
# Tolerances (the measured values, Step 186, are in DESIGN.md §93.8; each limit leaves room for the
# pads' different random phases and the noises' different seeds, and is far below what a wrong
# chord, a missing part or a wrong level would cause):
# - length: the bars of the bed (old beds' beats are not whole sixteenths: at most 0.01 % shorter);
# - tempo: the onsets repeat at the bed's detected tempo, within 1 % (measured: identical);
# - key: the whole loop's pitch-class profile within cosine 0.97 of the bed's (measured >= 0.98; a
#   wrong chord or bass in one of 12 chords costs about 0.01-0.03), per chord on average 0.95
#   (measured >= 0.968), and the bed's key fits the template within 0.1 of how it fits the bed
#   (measured <= 0.08, lab: the pads' random phases make a low note and the sub under it add up
#   differently per chord; a wrong key fits 0.3 or more worse);
# - loudness over time: the loudness of every two bars within 2 dB of the bed's, 0.75 dB on
#   average (measured <= 1.35 / 0.46 dB; a part missing in a section changes it by 2-6 dB);
# - spectrum: the five bands below 6 kHz within 1.5 dB of the bed's share (measured <= 0.7), the
#   band above (the hats' sizzle, 40-95 dB down) within 5 dB.


def chord_bars(name: str) -> int:
    """Bars per chord of a bed (the per-chord chroma's block)."""
    return 1 if name in ("cartoon", "lullaby") else 2


def profile(x: np.ndarray, bars: int, per_chord: int) -> dict[str, Any]:
    """What the comparison measures of a loop of ``bars`` bars: detected tempo, chroma (whole and
    every ``per_chord`` bars), the key fits, the loudness of every two bars and the band balance."""
    bar = len(x) // bars
    whole = measure.chroma(x)
    return {
        "tempo": measure.tempo(x),
        "chroma": whole.tolist(),
        "chords": [measure.chroma(x[b * bar : (b + per_chord) * bar]).tolist() for b in range(0, bars, per_chord)],
        "key_fits": measure.key_fits(whole),
        "loudness": measure.loudness_curve(x, 2 * bar).tolist(),
        "bands": measure.band_balance(x).tolist(),
    }


#: The beds made in Python (their templates are re-creations); ``tidewater`` and ``skyline``
#: (Step 190) and ``time_of_flight`` (Step 192) are their score files.
PYTHON_BEDS = [name for name, bed in music.BUILTIN_BEDS.items() if not bed.score]


def test_bed_measures_are_current() -> None:
    """The kept measurements still describe the beds (one measured again; all are fingerprinted)."""
    kept = json.loads(BED_MEASURES.read_text(encoding="utf-8"))
    assert list(kept) == PYTHON_BEDS
    fresh = profile(music.bed_loop("momentum").astype(np.float64), 24, 2)
    for key, value in fresh.items():
        if isinstance(value, dict):
            assert kept["momentum"][key] == pytest.approx(value, abs=1e-6)
        else:
            assert np.allclose(np.asarray(kept["momentum"][key], dtype=float), np.asarray(value, dtype=float), atol=1e-6)


@pytest.mark.slow
@pytest.mark.parametrize("name", [name for name, bed in music.BUILTIN_BEDS.items() if bed.score])
def test_score_bed_is_its_template(name: str) -> None:
    """Step 190: the template of a bed written as a score file is the bed, sample for sample."""
    assert np.array_equal(render_music_score(load_music_score(template_path(name))), music.bed_loop(name))


@pytest.mark.slow
@pytest.mark.parametrize("name", PYTHON_BEDS)
def test_template_is_close_to_its_bed(name: str) -> None:
    score = load_music_score(TEMPLATE_DIR / f"{name}.yaml")
    warnings: list[str] = []
    tpl = render_music_score(score, warnings).astype(np.float64)
    bed = json.loads(BED_MEASURES.read_text(encoding="utf-8"))[name]
    # renders, loops cleanly, -28 LUFS
    assert not warnings and len(tpl) == score.samples
    assert abs(score.seconds - music.BUILTIN_BEDS[name].seconds) <= 1e-4 * score.seconds
    assert loudness.integrated_loudness(tpl) == pytest.approx(music.MUSIC_LEVEL, abs=0.05)
    steps = np.abs(np.diff(tpl, axis=0))
    assert (np.abs(tpl[0] - tpl[-1]) <= np.quantile(steps, 0.999, axis=0)).all()
    got = profile(tpl, score.bars, chord_bars(name))
    # tempo
    assert (bed["tempo"] is None) == (got["tempo"] is None)
    if bed["tempo"] is not None:
        assert got["tempo"] == pytest.approx(bed["tempo"], rel=0.01)
    # key and chroma
    assert measure.chroma_similarity(np.array(got["chroma"]), np.array(bed["chroma"])) >= 0.97
    per_chord = [measure.chroma_similarity(np.array(a), np.array(b)) for a, b in zip(got["chords"], bed["chords"])]
    assert len(per_chord) == len(bed["chords"]) and np.mean(per_chord) >= 0.95
    stated = music.BUILTIN_BEDS[name].key.replace("F-sharp", "F#").split(" to ")[0]
    assert got["key_fits"][stated] >= bed["key_fits"][stated] - 0.1
    # loudness over time, two bars at a time
    diff = np.abs(np.array(got["loudness"]) - np.array(bed["loudness"]))
    assert diff.max() <= 2.0 and diff.mean() <= 0.75
    # spectrum balance
    bands = np.array(got["bands"]) - np.array(bed["bands"])
    assert np.abs(bands[:5]).max() <= 1.5 and abs(bands[5]) <= 5.0
