"""Step 196 (DESIGN.md §94.14): the studio's stems — what a track's stem depends on, remixes equal
to ``render_music_score`` (within the stated rounding, the same 16-bit audio), volumes applied to
kept stems, listening mixes at the whole piece's gain and length, the late facts, meters and the
"under narration" file. Fast scores of a few seconds; the 17 templates are checked by a slow test."""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from vidgen.loudness import integrated_loudness, measure
from vidgen.sfx import RATE, wav_bytes
from vidgen.studio import parse_music_score, render_music_score
from vidgen.studio.render import MixFacts, mix_track_stems, render_music_stems, render_track_stem
from vidgen.studio_app.app import AUDIO_NAME, StudioApp, check_text
from vidgen.studio_app.stems import METER_FLOOR_DB, CachedStem, StemCache, frame_power, hit_inputs, plain_volume, score_stems, stem_bytes, track_keys

EFFECTS = """\
title: Effects
key: A minor
tempo: 120
progression: "i VI III VII"
sections: [{name: a, bars: 2}, {name: b, bars: 2}]
tracks:
  kick: {instrument: kick, steps: "x... x... x... x..."}
  pad: {instrument: pad, play: chords, duck: kick, lowpass: {from: 1200, to: 3000}, sections: {b: {volume: -3}}}
  arp: {instrument: pluck, steps: "1358 5313", spread: 0.25, echo: {delay: 0.75, feedback: 0.4, repeats: 3}, reverb: {size: 1.2, mix: 0.3}}
  hat: {instrument: hat, steps: "..x. ..x. ..x. ..x.", gate: {steps: "x.x.", duty: 0.5, floor: 0.1}, width: 1.4}
  bass: {instrument: synth_bass, steps: "1.1. 1.1. 1.1. 1.1.", volume: -4}
  high: {instrument: bell, steps: "1... ....", octave: 8, transpose: 36}
"""

#: How far a remix of stems may be from ``render_music_score`` (absolute, float32 samples at
#: −28 LUFS): plain tracks' notes are added into the piece one by one, the stems sum them first,
#: so a few samples round to the next float32 (measured on the 17 templates: at most 4.7e-10).
REMIX_TOLERANCE = 1e-9


def score_of(text: str):
    data, score, problems = check_text(text)
    assert score is not None, problems
    return data, score


def assert_remix_matches(score) -> None:
    """Every track's stem mixed equals the score's render within :data:`REMIX_TOLERANCE`, with
    the same warnings, and plays as the same 16-bit audio at the studio's audition level."""
    warnings: list[str] = []
    expected = render_music_score(score, warnings)
    mixed: list[str] = []
    remix, facts = mix_track_stems(score, [render_track_stem(score, t.name) for t in score.tracks], mixed)
    assert remix.shape == expected.shape and facts.samples == len(expected) and mixed == warnings
    assert float(np.abs(remix.astype(np.float64) - expected).max()) <= REMIX_TOLERANCE
    level = 10 ** (12 / 20)
    assert wav_bytes(np.clip(remix * level, -1, 1)) == wav_bytes(np.clip(expected * level, -1, 1))


@pytest.mark.parametrize("loop", [True, False])
def test_remixed_stems_are_the_render(loop: bool) -> None:
    _, score = score_of(EFFECTS if loop else EFFECTS.replace("tempo: 120", "tempo: 120\nloop: false"))
    assert_remix_matches(score)
    warnings: list[str] = []
    render_music_score(score, warnings)
    assert len(warnings) == 2 and all(w.startswith("tracks.high: 2 notes in section") for w in warnings)  # still reported


def test_threads_give_the_same_samples() -> None:
    from vidgen.music import _level_gain

    _, score = score_of(EFFECTS)
    stems = [render_track_stem(score, t.name) for t in score.tracks]
    one, facts_one = mix_track_stems(score, stems)
    two, facts_two = mix_track_stems(score, stems, threads=2)
    assert one.tobytes() == two.tobytes() and facts_one == facts_two
    x = np.random.default_rng(3).standard_normal((25 * RATE, 2)) * 0.1
    a, b = measure(len(x), lambda i, j: x[i:j]), measure(len(x), lambda i, j: x[i:j], threads=2)
    assert (a.integrated, a.true_peak) == (b.integrated, b.true_peak)
    assert integrated_loudness(x) == integrated_loudness(x, threads=2) and _level_gain(x) == _level_gain(x, 2)


def test_render_music_stems_still_hands_out_each_track() -> None:
    _, score = score_of(EFFECTS)
    seen: dict[str, np.ndarray] = {}
    mix, gain = render_music_stems(score, lambda name, sound: seen.__setitem__(name, sound))
    assert list(seen) == [t.name for t in score.tracks] and all(s.shape == (score.samples, 2) for s in seen.values())
    assert gain == pytest.approx(10 ** ((-28 - integrated_loudness(np.asarray(mix, dtype=np.float64) / gain)) / 20), rel=1e-6)


@pytest.mark.slow
@pytest.mark.parametrize("name", ["calm", "pulse", "bright", "cartoon", "lullaby", "discovery", "breakthrough", "enigma", "momentum", "lab", "ascent",
                                  "horizon", "beacon", "neon", "tidewater", "skyline", "time_of_flight"])
def test_every_template_remixes_to_its_render(name: str) -> None:
    from vidgen.studio import music_template_text

    _, score = score_of(music_template_text(name))
    assert_remix_matches(score)


# ----- what a stem depends on ----------------------------------------------------------------------


def keys_of(text: str) -> dict[str, str]:
    data, score = score_of(text)
    return {name: k.key for name, k in track_keys(data, score).items()}


def test_a_stem_key_names_exactly_what_the_track_hears() -> None:
    base = keys_of(EFFECTS)
    assert len(set(base.values())) == len(base)

    def changed(old: str, new: str) -> set[str]:
        assert old in EFFECTS
        after = keys_of(EFFECTS.replace(old, new))
        return {n for n in base if after[n] != base[n]}

    assert changed("title: Effects", "title: Other") == set()
    assert changed("tempo: 120\n", "tempo: 120\nmaster: {lowpass: 3000}\n") == set()  # the mix's, not a track's
    assert changed('volume: -4}', 'volume: -5}') == {"bass"}
    assert changed('"1358 5313"', '"1358 5315"') == {"arp"}
    assert changed("tempo: 120", "tempo: 100") == set(base)
    assert changed("tempo: 120", "tempo: 120\nseed: 4") == set(base)
    assert changed('"i VI III VII"', '"i iv III VII"') == set(base)
    assert changed("{name: b, bars: 2}", "{name: b, bars: 3}") == set(base)
    # the pad ducks under the kick: it follows the kick's hits, not its sound
    assert changed('kick, steps: "x... x... x... x..."}', 'kick, steps: "x.x. x... x... x..."}') == {"kick", "pad"}
    assert changed('kick, steps: "x... x... x... x..."}', 'kick, steps: "x... x... x... x...", volume: -2}') == {"kick"}
    assert changed('kick, steps: "x... x... x... x..."}', 'kick, steps: "x... x... x... x...", rest: [b]}') == {"kick", "pad"}


def test_hit_inputs_keep_when_a_track_hits() -> None:
    spec = {"instrument": "kick", "steps": "x...", "volume": -3, "settings": {"tone": 1}, "rest": ["a"],
            "sections": {"b": {"steps": "x.x.", "volume": 2}, "c": {"settings": {"tone": 2}}}}
    assert hit_inputs(spec) == {"steps": "x...", "rest": ["a"], "sections": {"b": {"steps": "x.x."}, "c": {}}}


def test_plain_volume() -> None:
    assert plain_volume({"instrument": "kick"}) == 0.0 and plain_volume({"volume": -4}) == -4.0
    assert plain_volume({"volume": -4, "sections": {"b": {"steps": "x"}}}) == -4.0
    assert plain_volume({"volume": {"from": -3, "to": 0}}) is None  # a curve
    assert plain_volume({"volume": -4, "sections": {"b": {"volume": -2}}}) is None
    assert plain_volume({"volume": True}) is None and plain_volume("kick") is None


def test_a_volume_change_scales_the_kept_stem() -> None:
    cache = StemCache()
    data, score = score_of(EFFECTS)
    first = score_stems(cache, data, score)
    assert set(first.rendered) == {t.name for t in score.tracks} and first.scaled == {}
    data2, score2 = score_of(EFFECTS.replace("volume: -4}", "volume: -10}"))
    second = score_stems(cache, data2, score2)
    assert second.rendered == {} and set(second.scaled) == {"bass"}
    rendered = render_track_stem(score2, "bass")
    assert np.allclose(second.stems["bass"].stem.data, rendered.data, rtol=1e-12, atol=1e-15)
    assert np.allclose(second.stems["bass"].power, frame_power(rendered.piece), rtol=1e-9)
    # the remix with the scaled stem is still the render
    remix, _ = mix_track_stems(score2, [second.stems[t.name].stem for t in score2.tracks])
    assert float(np.abs(remix.astype(np.float64) - render_music_score(score2)).max()) <= REMIX_TOLERANCE
    # a pad whose volume changes in a section is rendered again
    data3, score3 = score_of(EFFECTS.replace("duck: kick,", "duck: kick, volume: -2,"))
    third = score_stems(cache, data3, score3)
    assert set(third.rendered) == {"pad"} and third.scaled == {}


def test_the_stem_cache_keeps_to_its_budget() -> None:
    data, score = score_of(EFFECTS)
    one = stem_bytes(score)
    item_bytes = one + frame_power(np.zeros((score.samples, 2))).nbytes
    cache = StemCache(budget=3 * item_bytes)
    stems = score_stems(cache, data, score)
    assert len(cache) == 6  # a mix's stems all stay, even over the budget
    item = stems.stems["kick"]
    assert isinstance(item, CachedStem) and item.nbytes == item_bytes
    # another version (every track changes): room is made first, the least recently used go
    cache.budget = 7 * item_bytes
    data2, score2 = score_of(EFFECTS.replace("tempo: 120", "tempo: 120\nseed: 2"))
    stems2 = score_stems(cache, data2, score2)
    assert len(cache) == 7 and cache.nbytes <= cache.budget
    assert all(cache.get(k.key) is not None for k in stems2.keys.values()) and cache.get(stems.keys["high"].key) is not None
    cache.make_room(6 * item_bytes, keep=[stems2.keys["kick"].key])
    assert len(cache) == 1 and cache.get(stems2.keys["kick"].key) is not None


def test_meters_are_the_stems_level_per_frame() -> None:
    from vidgen.studio_app.stems import meter_levels

    piece = np.zeros((RATE, 2))
    piece[: RATE // 2] = 0.1  # 0.5 s at -20 dBFS, then silence
    power = frame_power(piece)
    assert len(power) == 20
    levels = meter_levels(power, 22, 2.0)
    assert levels[0] == pytest.approx(-20 + 20 * math.log10(2), abs=0.05) and levels[15:] == [METER_FLOOR_DB] * 7


# ----- the studio ------------------------------------------------------------------------------------


def test_an_edit_renders_only_its_track_and_mutes_remix(tmp_path: Path) -> None:
    app = StudioApp(None, studio=tmp_path)
    try:
        app.load(text=EFFECTS)
        first = app.render()
        assert set(first["timing"]["tracks"]) == {"kick", "pad", "arp", "hat", "bass", "high"} and first["facts_pending"]
        assert list(first["meters"]) == ["kick", "pad", "arp", "hat", "bass", "high"] and first["meter_seconds"] == 0.05
        assert all(len(m) == math.ceil(first["samples"] / (0.05 * RATE)) for m in first["meters"].values())
        assert max(first["meters"]["kick"]) > -30 and max(first["meters"]["high"]) == METER_FLOOR_DB  # its notes are left out
        app.edit(None, [{"op": "set", "path": "tracks.arp.settings", "value": {"decay": 0.4}}])
        second = app.render()
        assert set(second["timing"]["tracks"]) == {"arp"} and not second["cached"]
        # the render is the score's render
        data, score = score_of(app.session.text(2))
        with wave.open(str(app.audio_file(f"{second['key']}.wav")), "rb") as w:
            heard = w.readframes(w.getnframes())
        assert heard == wav_bytes(np.clip(render_music_score(score) * 10 ** (12 / 20), -1, 1))[44:]
        # mute: a listening mix of the kept stems, nothing rendered
        mixed = app.render(mute=["kick"])
        assert mixed["timing"]["tracks"] == {} and mixed["timing"]["listening_mix"] > 0 and mixed["muted"] == ["kick"]
        assert app.render(mute=["kick"])["timing"]["listening_mix"] == 0.0  # the file is kept
        facts = app.facts(second["key"])
        assert facts["loudness"] == pytest.approx(-28, abs=0.1) and len(facts["energy"]) == 4
        assert json.loads((app.session.renders / f"{second['key']}.json").read_text(encoding="utf-8"))["energy"] == facts["energy"]
        assert app.render(version=2)["facts_pending"] is False
        with pytest.raises(Exception, match="not a render key"):
            app.facts("../x")
    finally:
        app.close()


def test_a_one_shot_mute_mix_keeps_the_tails(tmp_path: Path) -> None:
    app = StudioApp(None, studio=tmp_path)
    try:
        app.load(text=EFFECTS.replace("tempo: 120", "tempo: 120\nloop: false"))
        whole = app.render()
        assert whole["samples"] > 8 * RATE  # 4 bars of 2 s and the tails
        mix = app.render(mute=["kick", "pad", "hat", "bass", "high"])  # the arp alone, its echoes and reverb
        path = app.audio_file(mix["url"][len("/audio/"):])
        with wave.open(str(path), "rb") as w:
            frames = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2).astype(float)
        assert len(frames) == whole["samples"]
        tail = frames[8 * RATE : 8 * RATE + RATE // 2]
        assert np.sqrt(np.mean(tail**2)) > 30  # the echoes ring on after the last bar
        # the kept stems at the whole piece's gain: the arp as loud as in the whole mix
        data, score = score_of(app.session.text(1))
        stems = [render_track_stem(score, "arp")]
        expected, _ = mix_track_stems(score, stems, whole=MixFacts(whole["mix_gain"], whole["samples"]))
        assert np.abs(frames / 32767 - np.clip(np.asarray(expected) * 10 ** (12 / 20), -1, 1)).max() < 2 / 32767
    finally:
        app.close()


def test_under_narration(tmp_path: Path) -> None:
    from vidgen.studio_app.narration import _voice, under_narration

    voice, gain = _voice()
    peak = measure(len(voice), lambda a, b: voice[a:b]).true_peak
    assert 20 * math.log10(gain) + peak == pytest.approx(-1.5, abs=1e-9)
    music = np.full((30 * RATE, 2), 0.01)
    mixed = under_narration(music)
    assert mixed.shape == music.shape
    bed = mixed - voice[np.arange(len(music)) % len(voice)] * gain  # the music as it plays
    assert bed[3 * RATE, 0] < 0.01 * gain * 10 ** (-11 / 20)  # ducked 12 dB while the voice speaks
    assert bed[18 * RATE + RATE // 2, 0] == pytest.approx(0.01 * gain, rel=1e-6)  # the sample's quiet end
    app = StudioApp(None, studio=tmp_path)
    try:
        app.load(text=EFFECTS)
        r = app.render(narration=True)
        assert r["url"].endswith(".n.wav") and r["narration"] and app.audio_file(r["url"][len("/audio/"):]) is not None
        part = app.render(mute=["kick"], narration=True, section="b")
        assert AUDIO_NAME.match(part["url"][len("/audio/"):]) and part["url"].endswith(".n-b.wav")
    finally:
        app.close()


def test_audio_names_with_narration() -> None:
    key = "0123456789abcdef0123"
    for name in (f"{key}.n.wav", f"{key}.m0123456789.n.wav", f"{key}.n-lift.wav", f"{key}.m0123456789.n-a.wav"):
        assert AUDIO_NAME.match(name), name
    for name in (f"{key}.n.n.wav", f"{key}.x.wav", f"{key}.n.m0123456789.wav"):
        assert not AUDIO_NAME.match(name), name


def test_the_score_data_is_untouched_by_track_keys() -> None:
    data, score = score_of(EFFECTS)
    before = yaml.safe_dump(data)
    track_keys(data, score)
    assert yaml.safe_dump(data) == before
    assert parse_music_score(data).tracks[0].name == "kick"
