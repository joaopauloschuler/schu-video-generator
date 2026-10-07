"""Sound effects (Step 44, DESIGN.md §47): synthesis, levels, project sounds, the SFX track,
the ``sfx`` beat action, scene ``sfx:`` lists, ``NarratedScene.sfx``, ``vidgen list-sfx`` and
the mix in a rendered video."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml

from conftest import write_files
from vidgen import config, registry, sfx
from vidgen.actions import Action, ActionOptions, check_action_class, scene_actions
from vidgen.cli import main, project_problems
from vidgen.errors import VidgenError
from vidgen.extensions import load_builtins
from vidgen.project import Project
from vidgen.render.pipeline import render_project

ROOT = Path(__file__).resolve().parents[1]
RATE = sfx.RATE


# ----- synthesis -----------------------------------------------------------------------------------


def test_builtin_set() -> None:
    assert set(sfx.BUILTIN_SOUNDS) >= {"whoosh", "pop", "click", "tick", "riser", "chime"}
    for sound in sfx.BUILTIN_SOUNDS.values():
        lo, hi = sound.duration_range
        assert lo <= sound.duration <= hi
        assert len(sound.description) > 60 and sound.use, sound.name


def test_synthesis_is_deterministic() -> None:
    first = {name: sfx.synthesize(name).copy() for name in sfx.BUILTIN_SOUNDS}
    sfx._builtin.cache_clear()
    for name, samples in first.items():
        assert np.array_equal(sfx.synthesize(name), samples), name
    assert not sfx.synthesize("pop").flags.writeable  # cached arrays are shared: read-only


@pytest.mark.parametrize("name", list(sfx.BUILTIN_SOUNDS))
@pytest.mark.parametrize("intensity", [0.0, 0.5, 1.0])
def test_sound_is_clean(name: str, intensity: float) -> None:
    x = sfx.synthesize(name, intensity=intensity)
    assert x.dtype == np.float32 and x.ndim == 1
    assert len(x) == round(sfx.BUILTIN_SOUNDS[name].duration * RATE)
    assert np.all(np.isfinite(x))
    assert x[0] == 0.0 and x[-1] == 0.0  # the envelope starts and ends at zero: no click
    edge = int(0.0005 * RATE)
    assert np.abs(x[:edge]).max() < 0.25 * np.abs(x).max() and np.abs(x[-edge:]).max() < 0.25 * np.abs(x).max()
    assert abs(float(x.astype(np.float64).mean())) < 1e-6  # no DC offset
    assert sfx.peak_db(x) <= sfx.PEAK_CEILING + 0.01  # never clips, never louder than the ceiling
    expected = sfx.LOUDNESS_TARGET + (intensity - 0.5) * sfx.INTENSITY_DB
    level = sfx.loudness(x)
    assert level <= expected + 0.05
    assert level >= sfx.LOUDNESS_TARGET - 10  # only short, peak-limited sounds stay below the target


def test_params_change_the_sound() -> None:
    assert len(sfx.synthesize("whoosh", duration=1.5)) == round(1.5 * RATE)

    def centroid(x: np.ndarray) -> float:
        spectrum = np.abs(np.fft.rfft(x))
        return float((np.fft.rfftfreq(len(x), 1 / RATE) * spectrum).sum() / spectrum.sum())

    assert centroid(sfx.synthesize("chime", pitch=12)) == pytest.approx(2 * centroid(sfx.synthesize("chime")), rel=0.1)
    assert centroid(sfx.synthesize("chime", pitch=-5)) < centroid(sfx.synthesize("chime"))
    assert sfx.loudness(sfx.synthesize("whoosh", intensity=1.0)) == pytest.approx(sfx.loudness(sfx.synthesize("whoosh", intensity=0.0)) + 6, abs=0.1)
    with pytest.raises(VidgenError, match="unknown sound 'wooosh'; did you mean 'whoosh'"):
        sfx.synthesize("wooosh")


def test_sounds_stay_under_narration() -> None:
    """At gain 0 every sound is at least 5 dB under the quietest of real ElevenLabs narration
    beats (the committed kphi3 MP3s), loudest 400 ms against loudest 400 ms; at intensity 1
    still under it."""
    beats = sorted((ROOT / "examples" / "kphi3" / "audio").glob("*.mp3"))[:8]
    narration = min(sfx.loudness(sfx.decode_audio(p)) for p in beats)
    assert -24 < narration < -15
    for name in sfx.BUILTIN_SOUNDS:
        assert sfx.loudness(sfx.synthesize(name)) <= narration - 5, name
        assert sfx.loudness(sfx.synthesize(name, intensity=1.0)) <= narration - 2, name


def test_loudness_of_a_reference_tone() -> None:
    """A 1 kHz sine at -20 dBFS RMS reads about -20 LUFS (K-weighting is ~+0.7 dB at 1 kHz)."""
    t = np.arange(RATE) / RATE
    tone = math.sqrt(2) * 0.1 * np.sin(2 * np.pi * 1000 * t)
    assert sfx.loudness(tone) == pytest.approx(-20.0, abs=0.2)
    assert sfx.loudness(np.stack([tone, tone], axis=1)) == pytest.approx(-17.0, abs=0.2)  # channels add
    assert sfx.loudness(np.zeros(100)) == -math.inf


# ----- project sounds and checks -------------------------------------------------------------------


def _tone_wav(path: Path, seconds: float = 0.2, channels: int = 1, level: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    mono = level * np.sin(2 * np.pi * 440 * t)
    data = mono if channels == 1 else np.stack([mono, -mono], axis=1)
    sfx.write_wav(path, data)
    return data


def test_project_sounds(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    folder = tmp_path / "assets" / "sfx"
    _tone_wav(folder / "ding.wav")
    _tone_wav(folder / "pop.wav", channels=2)
    _tone_wav(folder / "ding.mp3")  # the .wav wins
    _tone_wav(folder / "bad name.wav")
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    library = sfx.SoundLibrary(tmp_path)
    assert list(library.custom) == ["ding", "pop"] and library.custom["ding"].suffix == ".wav"
    assert "not a valid sound name" in caplog.text
    assert library.names() == [*sfx.BUILTIN_SOUNDS, "ding"]
    assert library.audio("pop", {}).shape == (int(0.2 * RATE), 2)  # the project's file replaces the built-in
    ding = library.audio("ding", {})
    assert ding.shape == (int(0.2 * RATE), 1) and abs(sfx.peak_db(ding) - 20 * math.log10(0.5)) < 0.1
    assert library.problems("ding", {}) == []
    assert library.problems("ding", {"pitch": 2}) == [
        ("params", "params (pitch) shape the built-in sounds; 'ding' is the project's file assets/sfx/ding.wav")
    ]
    assert library.problems("chime", {"duration": 9.0}) == [("params.duration", "'chime' lasts 0.4 to 5 s, got 9")]
    [(key, message)] = library.problems("dong", {})
    assert key == "sound" and "did you mean 'ding'" in message and "assets/sfx/NAME.wav" in message
    assert sfx.SoundLibrary(None).names() == list(sfx.BUILTIN_SOUNDS)


def test_decode_errors(tmp_path: Path) -> None:
    bad = tmp_path / "x.wav"
    bad.write_bytes(b"not audio")
    with pytest.raises(VidgenError, match="cannot read sound file"):
        sfx.decode_audio(bad)


# ----- the track -----------------------------------------------------------------------------------


def test_stereo_pan_law() -> None:
    x = np.ones(4, dtype=np.float32)
    assert np.allclose(sfx.stereo(x), 1.0)  # centre: full level on both channels
    left = sfx.stereo(x, pan=-1.0)
    assert np.allclose(left[:, 0], math.sqrt(2)) and np.allclose(left[:, 1], 0, atol=1e-6)
    half = sfx.stereo(x, gain_db=-6.0206)
    assert np.allclose(half, 0.5, atol=1e-4)
    both = np.stack([x, x], axis=1)
    assert np.allclose(sfx.stereo(both, pan=0.5), [[0.5, 1.0]] * 4)


def test_track_places_every_sound_at_its_sample(tmp_path: Path) -> None:
    library = sfx.SoundLibrary(None)
    events = [
        sfx.SfxEvent(0.5, "pop"),
        sfx.SfxEvent(9.99, "chime", gain=-6.0, pan=0.5),  # crosses the 10 s block boundary
        sfx.SfxEvent(3.0, "riser", align="end", params={"duration": 1.0}),  # ends at 3.0
        sfx.SfxEvent(0.02, "whoosh", align="end"),  # mostly before the start: cut
        sfx.SfxEvent(12.0, "thud"),  # runs past the end: cut
    ]
    samples = round(12.2 * RATE)
    path = tmp_path / "sfx.wav"
    sfx.write_track(path, events, samples, library, master_db=-3.0)
    track = sfx.read_wav(path)
    assert track.shape == (samples, 2)
    expected = np.zeros((samples, 2), dtype=np.float64)
    for event in events:
        data = sfx.stereo(library.audio(event.sound, event.params), event.gain - 3.0, event.pan)
        start = round(event.time * RATE) - (len(data) if event.align == "end" else 0)
        lo, hi = max(start, 0), min(start + len(data), samples)
        expected[lo:hi] += data[lo - start : hi - start]
    assert np.abs(track - expected).max() < 1.5 / 32768  # 16-bit rounding only
    pop = sfx.stereo(sfx.synthesize("pop"), -3.0)
    start = round(0.5 * RATE)
    assert np.abs(track[:start]).max() > 0 and np.all(track[round(0.02 * RATE) : start] == 0)  # the cut whoosh's tail, then silence
    assert np.allclose(track[start : start + len(pop)], pop, atol=1.5 / 32768)
    riser = sfx.synthesize("riser", duration=1.0)
    assert np.argmax(np.abs(track[: 3 * RATE, 0])) < 3 * RATE  # the riser ends at 3 s, at its loudest
    assert np.abs(track[3 * RATE - len(riser) // 10 : 3 * RATE, 0]).max() > 0.05


def test_track_clips_instead_of_wrapping(tmp_path: Path) -> None:
    folder = tmp_path / "assets" / "sfx"
    _tone_wav(folder / "loud.wav", level=0.9)
    library = sfx.SoundLibrary(tmp_path)
    path = tmp_path / "track.wav"
    sfx.write_track(path, [sfx.SfxEvent(0.0, "loud"), sfx.SfxEvent(0.0, "loud")], RATE // 2, library)
    track = sfx.read_wav(path)
    assert track.max() == pytest.approx(32767 / 32768) and track.min() == -1.0


def test_event_json_round_trip() -> None:
    event = sfx.SfxEvent(1.25, "pop", gain=-2.0, pan=0.3, align="end", params={"pitch": 2.0}, beat="b1")
    assert sfx.SfxEvent.from_json(json.loads(json.dumps(event.to_json()))) == event
    assert event.shifted(10.0).time == 11.25


# ----- config ---------------------------------------------------------------------------------------


def _scene(**extra: Any) -> dict[str, Any]:
    return {"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "Hello there."}], **extra}


def test_config_models() -> None:
    cfg = config.parse_config({"title": "t", "sfx": {"auto": True, "gain": -3}, "scenes": [_scene(sfx=["pop", {"sound": "riser", "at": 1.5, "align": "end", "params": {"duration": 1}}])]})
    assert cfg.sfx.auto is True and cfg.sfx.gain == -3
    first, second = cfg.scenes[0].sfx
    assert first.sound == "pop" and first.at == 0 and first.params.model_dump(exclude_none=True) == {}
    assert second.align == "end" and second.params.duration == 1
    with pytest.raises(VidgenError, match=r"sfx\[0\]: at 3 s is not within the scene's duration \(2 s\)"):
        config.parse_config({"title": "t", "scenes": [{"id": "q", "type": "text_card", "duration": 2, "sfx": [{"sound": "pop", "at": 3}]}]})
    for bad in ({"sound": "pop", "gain": 20}, {"sound": "pop", "pan": 2}, {"sound": "a b"}, {"sound": "pop", "params": {"pitch": 30}}, {"sound": "pop", "volume": 1}):
        with pytest.raises(VidgenError):
            config.parse_config({"title": "t", "scenes": [_scene(sfx=[bad])]})


# ----- the sfx beat action ---------------------------------------------------------------------------


def _action_problems(actions: list[dict[str, Any]]) -> list[tuple[str, str]]:
    load_builtins()
    spec = config.parse_config({"title": "t", "scenes": [_scene(beats=[{"text": "Hello there.", "actions": actions}])]}).scenes[0]
    cls = registry.get("text_card").cls
    return scene_actions("text_card", cls, spec, cls.validate_params(spec.params), None)[1]


def test_sfx_action_checks() -> None:
    assert _action_problems([{"sfx": "whoosh"}, {"sfx": "pop", "at": 0.5, "gain": -3, "params": {"pitch": 2}}]) == []
    assert _action_problems([{"action": "sfx", "sound": "riser", "align": "end", "params": {"duration": 1.5}}]) == []
    problems = dict(_action_problems([{"sfx": "wosh"}]))
    assert "did you mean 'whoosh'" in problems["beats[0].actions[0].target"]  # not "unknown target"
    assert _action_problems([{"action": "sfx"}]) == [("beats[0].actions[0].target", "which sound? write `- sfx: NAME` (vidgen list-sfx lists them)")]
    assert _action_problems([{"sfx": ["pop", "tick"]}])[0][1].startswith("one sound per sfx action")
    assert _action_problems([{"sfx": "pop", "sound": "tick"}])[0][0] == "beats[0].actions[0].sound"
    assert _action_problems([{"sfx": "pop", "run_time": 1}])[0][0] == "beats[0].actions[0].run_time"
    assert _action_problems([{"sfx": "pop", "params": {"duration": 3}}]) == [("beats[0].actions[0].params.duration", "'pop' lasts 0.05 to 0.4 s, got 3")]
    assert _action_problems([{"sfx": "pop", "gain": 40}])[0][0] == "beats[0].actions[0].gain"


def test_non_animating_action_classes() -> None:
    class Silent(Action):
        animates = False

    with pytest.raises(VidgenError, match="implement cue"):
        check_action_class("silent", Silent)

    class Undoable(Action):
        animates = False
        reversible = True

        def cue(self, scene: Any, time: float) -> None: ...

        def revert(self, scene: Any, targets: Any) -> list[Any]:
            return []

    with pytest.raises(VidgenError, match="cannot be reversible"):
        check_action_class("undoable", Undoable)

    class Fine(Action):
        Options = ActionOptions
        animates = False

        def cue(self, scene: Any, time: float) -> None: ...

    check_action_class("fine", Fine)


# ----- validate and list-sfx -------------------------------------------------------------------------


def test_validate_reports_sounds(make_project: Any) -> None:
    root = make_project(
        {
            "title": "t",
            "scenes": [
                _scene(sfx=[{"sound": "chimes"}, {"sound": "chime", "params": {"duration": 0.1}}], beats=[{"text": "Hi there.", "actions": [{"sfx": "whosh"}]}])
            ],
        }
    )
    problems = {p.location: p.message for p in project_problems(Project.load(root))}
    assert "did you mean 'chime'" in problems["scenes[0].sfx[0].sound"]
    assert problems["scenes[0].sfx[1].params.duration"] == "'chime' lasts 0.4 to 5 s, got 0.1"
    assert "did you mean 'whoosh'" in problems["scenes[0].beats[0].actions[0].target"]
    _tone_wav(root / "assets" / "sfx" / "whosh.wav")  # the project's own sound
    problems = {p.location for p in project_problems(Project.load(root))}
    assert "scenes[0].beats[0].actions[0].target" not in problems


def test_list_sfx(tmp_path: Path, make_project: Any, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    _tone_wav(root / "assets" / "sfx" / "ding.wav")
    _tone_wav(root / "assets" / "sfx" / "click.wav", channels=2)
    previews = tmp_path / "previews"
    assert main(["list-sfx", str(root), "--json", "--render-dir", str(previews)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "list-sfx" and doc["ok"] and doc["count"] == len(sfx.BUILTIN_SOUNDS) + 1
    assert doc["loudness_target"] == sfx.LOUDNESS_TARGET and [p["name"] for p in doc["params"]] == ["duration", "pitch", "intensity"]
    sounds = {s["name"]: s for s in doc["sounds"]}
    whoosh = sounds["whoosh"]
    assert whoosh["origin"] == "builtin" and whoosh["description"].startswith("Air rushing past")
    assert whoosh["duration"] == 0.6 and whoosh["duration_range"] == [0.2, 3.0] and whoosh["channels"] == 1
    assert whoosh["loudness"] == pytest.approx(sfx.LOUDNESS_TARGET, abs=0.1) and whoosh["peak_db"] <= sfx.PEAK_CEILING
    assert sounds["click"]["origin"] == "assets/sfx/click.wav" and sounds["click"]["overrides_builtin"] and sounds["click"]["channels"] == 2
    assert sounds["ding"]["description"] is None and sounds["ding"]["duration_range"] is None
    assert Path(whoosh["preview"]) == previews / "whoosh.wav" and doc["previews"] == str(previews)
    assert np.allclose(sfx.read_wav(previews / "whoosh.wav")[:, 0], sfx.synthesize("whoosh"), atol=1.5 / 32768)
    assert len(list(previews.glob("*.wav"))) == doc["count"]
    assert main(["list-sfx", str(root)]) == 0
    out = capsys.readouterr().out
    assert "whoosh" in out and "description: Air rushing past" in out and "assets/sfx/click.wav  (overrides builtin)" in out
    assert "level at gain 0: -27 LUFS" in out


def test_list_scenes_shows_sfx_action(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list-scenes", "--json"]) == 0
    actions = {a["name"]: a for a in json.loads(capsys.readouterr().out)["actions"]}
    assert actions["sfx"]["animates"] is False and actions["sfx"]["scene_targets"] is False
    assert actions["reveal"]["animates"] is True
    assert main(["list-scenes"]) == 0
    assert "(at its time, does not animate)" in capsys.readouterr().out


def test_schema_has_sfx(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert "sfx" in schema["properties"] and "sfx" in schema["$defs"]["SceneConfig"]["properties"]
    assert "action.sfx" in schema["$defs"]


# ----- rendering --------------------------------------------------------------------------------------

FPS = 10

SFX_EXT = """
from vidgen.api import *

@scene("beeper")
class Beeper(NarratedScene):
    def construct(self):
        dot = Dot()
        self.wait_seconds(0.4)
        self.sfx("tick")                    # now: 0.4 s
        self.play(FadeIn(dot), run_time=0.5)
        self.sfx("chime", 1.3, gain=-6)     # at a given time
        self.wait_seconds(1.1)
        try:
            self.sfx("nope")
        except VidgenError as exc:
            self.sfx("click", pan=-1.0)     # 2.0 s
            assert "unknown sound 'nope'" in str(exc)
"""


def _write(root: Path, config_data: dict[str, Any], files: dict[str, str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = {
        "title": "SFX test",
        "output": "out",
        "format": {"width": 96, "height": 54, "fps": FPS},
        "preview": {"width": 96, "height": 54, "fps": FPS},
        "narration": {"pad": 0.3, "words_per_second": 3.0},
    }
    (root / "video.yaml").write_text(yaml.safe_dump({**base, **config_data}, sort_keys=False), encoding="utf-8")
    write_files(root, files or {})
    return root


def _mp4_audio(path: Path) -> np.ndarray:
    with av.open(str(path)) as c:
        resampler = av.AudioResampler(format="flt", layout="stereo", rate=RATE)
        chunks = [g.to_ndarray().reshape(-1, 2) for f in c.decode(c.streams.audio[0]) for g in resampler.resample(f)]
    return np.concatenate(chunks)


@pytest.fixture(scope="module")
def sfx_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three scenes: a silent card with a scene `sfx:` list, a narrated bullets scene with `sfx`
    actions (and an auto pop for its reveal action: `sfx: {auto: true}`), an extension scene
    calling `self.sfx`; rendered once (with sound)."""
    root = _write(
        tmp_path_factory.mktemp("sfx") / "proj",
        {
            "sfx": {"auto": True, "gain": -2.0},
            "scenes": [
                {"id": "card", "type": "chapter", "params": {"title": "One"}, "duration": 1.5, "sfx": [{"sound": "click", "at": 0.7}]},
                {
                    "id": "list",
                    "type": "bullets",
                    "params": {"heading": "Items", "items": ["One", "Two", "Three"]},
                    "beats": [
                        {
                            "text": "One two three four five six.",
                            "actions": [{"sfx": "whoosh"}, {"sfx": "pop", "at": 0.5, "params": {"pitch": 3}}, {"reveal": "item3", "at": 0.5}],
                        },
                        {"text": "Seven eight nine ten eleven twelve.", "actions": [{"highlight": "item1", "at": 0.3}]},
                    ],
                },
                {"id": "beep", "type": "beeper", "duration": 2.5},
            ],
        },
        {"extensions/beeper.py": SFX_EXT},
    )
    with registry.isolated():
        render_project(Project.load(root), preview=True)
    from vidgen import runtime

    runtime.clear_context()
    return root


def _timings(root: Path) -> dict[str, Any]:
    return json.loads((root / "build" / "preview" / "timings.json").read_text(encoding="utf-8"))


@pytest.mark.render
def test_events_are_timed_in_frames(sfx_project: Path) -> None:
    timings = _timings(sfx_project)
    card, lst, beep = timings["scenes"]
    assert [(e["sound"], e["time"], e["gain"]) for e in card["sfx"]] == [("whoosh", 0.0, -3.0), ("click", 0.7, 0.0)]  # auto chapter whoosh
    b1, b2 = lst["beats"]
    d1 = b1["end"] - b1["start"]
    start = lst["start"]
    pop_time = b1["start"] + round(0.5 * d1 * FPS) / FPS
    events = [(e["sound"], e["beat"], e["gain"]) for e in lst["sfx"]]
    # beat 1 has its own sounds (its reveal gets no automatic pop); beat 2's highlight ticks
    assert events == [("whoosh", "list_b1", 0.0), ("pop", "list_b1", 0.0), ("tick", "list_b2", -3.0)]
    assert lst["sfx"][0]["time"] == pytest.approx(b1["start"]) and lst["sfx"][1]["time"] == pytest.approx(pop_time)
    assert lst["sfx"][1]["params"] == {"pitch": 3.0}
    assert b2["start"] + 0.3 * (b2["end"] - b2["start"]) - 0.01 <= lst["sfx"][2]["time"] < b2["end"]
    s = beep["start"]
    assert [(e["sound"], round(e["time"] - s, 6), e["gain"], e["pan"]) for e in beep["sfx"]] == [
        ("tick", 0.4, 0.0, 0.0), ("chime", 1.3, -6.0, 0.0), ("click", 2.0, 0.0, -1.0)
    ]
    scene_file = json.loads((sfx_project / "build/preview/timings/beep.json").read_text(encoding="utf-8"))
    assert [e["time"] for e in scene_file["sfx"]] == [0.4, 1.3, 2.0]  # scene times in the scene's file
    assert start == pytest.approx(card["duration"])


@pytest.mark.render
def test_track_and_video_hold_the_sounds(sfx_project: Path) -> None:
    timings = _timings(sfx_project)
    track = sfx.read_wav(sfx_project / "build/preview/padded/sfx.wav")
    assert len(track) == round(timings["duration"] * RATE)
    library = sfx.SoundLibrary(sfx_project)
    expected = np.zeros_like(track, dtype=np.float64)
    for scene in timings["scenes"]:
        for e in scene.get("sfx", []):
            event = sfx.SfxEvent.from_json(e)
            start, data = sfx.placed(event, library, -2.0)
            expected[start : start + len(data)] += data[: len(track) - start]
    assert np.abs(track - expected).max() < 1.5 / 32768
    # the final video: narration (none here: no MP3s) + effects; onsets where the timings say
    audio = _mp4_audio(sfx_project / "out_preview.mp4")
    beep = timings["scenes"][2]
    for offset, channel in ((0.4, 1), (2.0, 0)):
        at = beep["start"] + offset
        lo = int((at - 0.05) * RATE)
        window = np.abs(audio[lo : int((at + 0.05) * RATE), channel])
        onset = (lo + int(np.argmax(window > 0.08))) / RATE
        assert onset == pytest.approx(at, abs=0.003)
    click = audio[int((beep["start"] + 2.0) * RATE) : int((beep["start"] + 2.05) * RATE)]
    assert np.abs(click[:, 0]).max() > 5 * np.abs(click[:, 1]).max()  # panned hard left


@pytest.mark.render
def test_no_audio_render_has_no_effects(sfx_project: Path) -> None:
    with registry.isolated():
        render_project(Project.load(sfx_project), preview=True, scenes=["card"], no_audio=True)
    assert not (sfx_project / "build/preview/padded/sfx.wav").exists()
    assert np.abs(_mp4_audio(sfx_project / "out_preview.mp4")).max() < 1e-4
    assert _timings(sfx_project)["scenes"][0]["sfx"]  # still recorded


@pytest.mark.render
def test_extending_example(tmp_path: Path) -> None:
    """The "Sound effects" example of docs/EXTENDING.md renders and records its sounds."""
    import re

    text = (ROOT / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    code = re.search(r"\*\*Sound effects\*\*.*?```python\n(.*?)```", text, re.S).group(1)
    root = _write(tmp_path / "ext", {"scenes": [{"id": "c", "type": "countdown", "duration": 3}]}, {"extensions/countdown.py": "from vidgen.api import *\n\n\n" + code})
    with registry.isolated():
        render_project(Project.load(root), preview=True)
    [scene] = _timings(root)["scenes"]
    assert [(e["sound"], e["time"]) for e in scene["sfx"]] == [("whoosh", 0.0), ("tick", 0.5), ("tick", 0.8), ("tick", 1.1), ("success", 1.6)]
    assert [e["params"].get("pitch") for e in scene["sfx"][1:4]] == [2.0, 4.0, 6.0]


@pytest.mark.render
def test_scene_sfx_errors(tmp_path: Path) -> None:
    ext = """
    from vidgen.api import *

    @scene("bad")
    class Bad(NarratedScene):
        def construct(self):
            self.sfx("pop", params_typo=1)
    """
    root = _write(tmp_path / "bad", {"scenes": [{"id": "x", "type": "bad", "duration": 1}]}, {"extensions/bad.py": ext})
    with registry.isolated(), pytest.raises(VidgenError, match="params_typo"):
        render_project(Project.load(root), preview=True)
