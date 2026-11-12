"""Step 288: sound design in audio-only renders (DESIGN.md §112): ambience beds per scene or
section with cross-fades, beds that start or stop on a word, repeated cues, cues in a room, and
the sounds of stage and video_clip scenes worked out without pictures (``audio.scene_sounds``).
Narration is mocked: each beat's "MP3" is a WAV tone (PyAV reads it by its content)."""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path
from typing import Any, get_args

import numpy as np
import pytest
import yaml

from vidgen import ambience, config, extensions, mix, schema
from vidgen.audio_only import plan_audio, render_audio
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.sfx import RATE, SfxEvent, SoundLibrary, placed, repeated, write_wav
from vidgen.sound_design import BeatSlot, SceneSlot, ambience_entries, clip_sound, scene_beds, stage_sounds
from vidgen.staging import cue_room, repeat_pans


def _write(root: Path, data: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


def _voice_all(project: Project, seconds: float = 1.2) -> None:
    t = np.arange(round(seconds * RATE)) / RATE
    for k, (_, beat) in enumerate(project.beats()):
        write_wav(project.audio_dir / f"{beat.id}.mp3", (0.2 * np.sin(2 * np.pi * (200 + 40 * k) * t)).astype(np.float32))


def _read_24(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as src:
        raw = np.frombuffer(src.readframes(src.getnframes()), dtype=np.uint8).reshape(-1, 3)
    ints = raw[:, 0].astype(np.int32) | raw[:, 1].astype(np.int32) << 8 | raw[:, 2].astype(np.int8).astype(np.int32) << 16
    return (ints / 8388608).reshape(-1, 2)


DRAMA: dict[str, Any] = {
    "title": "Drama",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voices": {"b": {"voice_id": "other", "pan": "right"}},
    "audio": {"ambience_crossfade": 2.0},
    "sections": [
        {"id": "street", "title": "Street", "room": "outdoors", "ambience": {"beds": ["rain", "city"], "gain": 2},
         "beats": [{"text": "the rain fell on the street", "actions": [{"sfx": "footstep", "at": "@street", "repeat": 4, "every": 0.4, "pan": "left"}]},
                   {"text": "where are my keys", "voice": "b"}]},
        {"id": "lab", "title": "Lab", "room": "small_office", "ambience": {"beds": {"hum": 0, "rain": -12}},
         "beats": [{"text": "the machines hummed", "actions": [{"sfx": "knock", "room": True}]},
                   {"text": "and then the rain stopped", "voice": "b", "ambience": {"stop": "rain", "at": "@stopped", "fade": 1.0}}]},
    ],
}


# ----- config ---------------------------------------------------------------------------------------------


def test_bed_names_match() -> None:
    assert get_args(config.AmbienceBedName) == ambience.AMBIENCE_BEDS


def test_settings_parse() -> None:
    scene = config.SceneConfig.model_validate({"id": "s", "type": "title", "duration": 1, "ambience": {"beds": {"hum": 0, "rain": -10}, "gain": -2, "width": 0.5}})
    assert scene_beds(scene) == {"hum": (-2.0, 0.5), "rain": (-12.0, 0.5)}
    assert scene_beds(config.SceneConfig.model_validate({"id": "s", "type": "title", "duration": 1, "ambience": ["rain", "rain", "city"]})) == {"rain": (0.0, None), "city": (0.0, None)}
    assert scene_beds(config.SceneConfig.model_validate({"id": "s", "type": "title", "duration": 1, "ambience": False})) == {}
    beat = config.BeatConfig.model_validate({"id": "b", "text": "the rain stopped", "ambience": [{"start": "hum"}, {"stop": "all", "at": "end"}]})
    assert [c.at for c in beat.ambience_changes] == [0.0, "end"] and beat.ambience_changes[1].stopped(["rain", "hum"]) == ["rain", "hum"]
    cue = config.SfxCue.model_validate({"sound": "knock", "pan": "far_left", "repeat": 3, "every": 0.2, "room": "hall"})
    assert cue.pan_value == -0.8 and cue.room == "hall"


@pytest.mark.parametrize(("data", "message"), [
    ({"id": "b", "text": "the rain fell", "ambience": {"start": "rain", "at": "@snow"}}, 'does not say "snow"'),
    ({"id": "b", "text": "x", "ambience": {"at": 0.5}}, "starts or stops beds"),
    ({"id": "b", "text": "x", "ambience": {"start": "drizzle"}}, "rain"),
])
def test_setting_errors(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        config.BeatConfig.model_validate(data)


@pytest.mark.slow
def test_sections_take_ambience_and_a_pause_takes_a_room(tmp_path: Path) -> None:
    data = {**DRAMA, "sections": [*DRAMA["sections"], {"pause": 2.0, "ambience": "crickets", "room": "hall", "sfx": [{"sound": "knock", "room": True}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    pause = project.config.scenes[-1]
    assert pause.ambience == "crickets" and pause.room == "hall" and pause.silent
    with pytest.raises(VidgenError, match="did you mean 'ambience'"):
        Project.load(_write(tmp_path / "q", {**DRAMA, "sections": [{"beats": ["x"], "ambiance": "rain"}]}))
    props = schema.config_schema([], [])["properties"]["sections"]["items"]["anyOf"]
    assert "ambience" in props[0]["properties"] and {"ambience", "room"} <= set(props[1]["properties"])


# ----- beds -----------------------------------------------------------------------------------------------


def _slots(project: Project) -> list[SceneSlot]:
    from vidgen.audio_only import scene_slots

    return scene_slots(project, plan_audio(project).scenes)


def test_beds_cross_fade_at_the_change_and_stop_on_a_word(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", DRAMA))
    _voice_all(project)
    plan = plan_audio(project)
    street, lab = plan.scenes
    change = lab.start
    entries = {(e["bed"], e["gain"]): e for e in street.ambience + lab.ambience}
    assert entries[("city", 2.0)]["start"] == 0.0 and entries[("city", 2.0)]["fade_in"] == ambience.BEDS["city"].fade_in   # from the start, its own fade
    assert entries[("city", 2.0)]["end"] == pytest.approx(change + 1.0) and entries[("city", 2.0)]["fade_out"] == 2.0       # centred on the change
    assert entries[("hum", 0.0)]["start"] == pytest.approx(change - 1.0) and entries[("hum", 0.0)]["fade_in"] == 2.0
    loud, quiet = entries[("rain", 2.0)], entries[("rain", -12.0)]                                                         # a new level: a cross-fade too
    assert loud["end"] == pytest.approx(change + 1.0) and quiet["start"] == pytest.approx(change - 1.0)
    words = plan.beats[-1]
    assert words.start < quiet["end"] - 1.0 < words.end and quiet["fade_out"] == 1.0                                       # it stops on "stopped"
    assert entries[("hum", 0.0)]["end"] == pytest.approx(plan.duration)
    assert [e["bed"] for e in lab.ambience] == ["hum", "rain"] and all("fade_in" in e for e in street.ambience)


def test_same_bed_plays_on_and_a_beat_starts_one(tmp_path: Path) -> None:
    data = {"title": "t", "narration": {"pad": 0.3, "words_per_second": 2}, "sections": [
        {"id": "a", "ambience": "room_tone", "beats": ["one two three"]},
        {"pause": 1.0, "ambience": "room_tone"},
        {"id": "b", "ambience": "room_tone", "beats": [{"text": "then it rained", "ambience": {"start": "rain", "at": 0.5, "gain": -3}}]},
    ]}
    project = Project.load(_write(tmp_path / "p", data))
    plan = plan_audio(project)
    tone = [e for s in plan.scenes for e in s.ambience if e["bed"] == "room_tone"]
    assert len(tone) == 1 and tone[0]["end"] == pytest.approx(plan.duration)                                               # no dip
    rain = [e for s in plan.scenes for e in s.ambience if e["bed"] == "rain"]
    beat = plan.scenes[2].beats[0]
    assert len(rain) == 1 and rain[0]["start"] == pytest.approx(beat.start + 0.5 * beat.body) and rain[0]["gain"] == -3


@pytest.mark.slow
def test_designed_beds_in_the_mix(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", {"title": "t", "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "duration": 6.0}]}))
    total = 6 * RATE
    entries = [{"bed": "city", "start": 0.0, "end": 4.0, "fade_in": 1.0, "fade_out": 2.0, "gain": 0.0},
               {"bed": "hum", "start": 2.0, "end": 6.0, "fade_in": 2.0, "fade_out": 0.5, "gain": -6.0, "width": 0.0}]
    timings = {"scenes": [{"id": "s", "start": 0.0, "duration": 6.0, "beats": [], "ambience": entries}]}
    assert ambience.ambience_spans(timings, "city") == []
    placements = mix.plan_ambience(project, timings, total)
    assert [(p.bed, p.start, p.end, p.width) for p in placements] == [("city", 0, 4 * RATE, None), ("hum", 2 * RATE, 6 * RATE, 0.0)]
    city, hum = placements
    assert city.gain[0] == 0.0 and city.gain[200] == pytest.approx(1.0) and city.gain[300] == pytest.approx(0.5)            # half-way through its fade out
    assert hum.gain[500] == pytest.approx(10 ** (-6 / 20))
    track = mix.MusicTrack(placements)
    x = track.read(5 * RATE, 5 * RATE + 4800)
    assert np.array_equal(x[:, 0], x[:, 1])                                                                                 # its own width: 0
    assert placements[0].summary().get("width") is None and placements[1].summary()["width"] == 0.0


# ----- cues -----------------------------------------------------------------------------------------------


def test_repeats_alternate_feet() -> None:
    steps = repeated("footstep", 1.0, 3, 0.5, {})
    assert [t for t, _ in steps] == [1.0, 1.5, 2.0] and [p["pitch"] for _, p in steps] == [0.0, -1.5, 0.0]
    assert repeated("footstep", 1.0, 2, 0.5, {"pitch": 3.0})[1][1]["pitch"] == 3.0
    assert repeated("knock", 0.0, 2, 1.0, {"duration": 0.5}) == [(0.0, {"duration": 0.5}), (1.0, {"duration": 0.5})]
    assert repeated("footstep", 0.25, 1, 0.5, {}) == [(0.25, {})]


def test_repeats_step_across_a_pan_move(tmp_path: Path) -> None:
    assert repeat_pans({"from": "far_left", "to": "far_right"}, 5) == [-0.8, -0.4, 0.0, 0.4, 0.8]
    assert repeat_pans(config.PanMove.model_validate({"from": -1, "to": 0}), 1) == [-1.0] and repeat_pans("left", 2) == [-0.5, -0.5]
    cue = config.SfxCue.model_validate({"sound": "footstep", "repeat": 3, "pan": {"from": "left", "to": 0.5}})
    assert cue.pans == [-0.5, 0.0, 0.5] and cue.pan_value == -0.5
    data = {"title": "t", "narration": {"words_per_second": 2}, "sections": [{"id": "a", "sfx": [{"sound": "knock", "repeat": 2, "pan": {"from": 1, "to": -1}}],
            "beats": [{"text": "she walks across", "actions": [{"sfx": "footstep", "at": "@walks", "repeat": 4, "every": 0.4, "pan": {"from": "left", "to": "right"}}]}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    _voice_all(project)
    events = plan_audio(project).scenes[0].events
    assert [e.pan for e in events if e.sound == "knock"] == [1.0, -1.0]
    assert [e.pan for e in events if e.sound == "footstep"] == pytest.approx([-0.5, -1 / 6, 1 / 6, 0.5], abs=1e-6)


def test_cue_rooms() -> None:
    cfg = config.VideoConfig.model_validate({"title": "t", "audio": {"room": "hall"}, "scenes": [
        {"id": "a", "type": "title", "duration": 1}, {"id": "b", "type": "title", "duration": 1, "room": {"use": "corridor", "amount": 0.5}}]})
    a, b = cfg.scenes
    assert cue_room(cfg, a, None) is None and cue_room(cfg, a, True) == "hall" and cue_room(cfg, b, True) == "corridor"
    assert cue_room(cfg, b, "car") == "car" and cue_room(cfg, b, False) is None and cue_room(cfg, b, "none") is None
    on = cfg.model_copy(update={"audio": cfg.audio.model_copy(update={"sfx_room": True})})
    assert cue_room(on, b, None) == "corridor" and cue_room(on, b, False) is None


def test_an_event_in_a_room() -> None:
    library = SoundLibrary(None)
    dry = SfxEvent(1.0, "knock", -3.0, -0.5)
    start, data = placed(dry, library)
    assert placed(SfxEvent(1.0, "knock", -3.0, -0.5, room=None), library)[1].tobytes() == data.tobytes()
    roomed = SfxEvent(1.0, "knock", -3.0, -0.5, room="hall")
    start_r, wet = placed(roomed, library)
    assert start_r == start and len(wet) > len(data) + RATE and np.abs(wet[len(data) + RATE // 2 :]).max() > 1e-4   # the hall rings on
    assert float(np.sum(wet[: len(data), 0] ** 2)) > float(np.sum(wet[: len(data), 1] ** 2))                       # still on the left
    assert SfxEvent.from_json(roomed.to_json()) == roomed and "room" not in dry.to_json()
    end = SfxEvent(1.0, "knock", room="hall", align="end")
    assert placed(end, library)[0] == RATE - len(data)                                                                  # the dry sound ends there


@pytest.mark.slow
@pytest.mark.render
def test_a_video_scene_repeats_and_rooms_its_cues(tmp_path: Path) -> None:
    from manim import tempconfig

    from vidgen import registry

    data = {"title": "t", "narration": {"pad": 0.3, "words_per_second": 2}, "audio": {"sfx_room": True}, "scenes": [
        {"id": "s", "type": "text_card", "params": {"text": "Hi"}, "room": "hall", "sfx": [{"sound": "knock", "at": 0.2, "repeat": 2, "every": 0.3, "room": False, "pan": {"from": "left", "to": "right"}}],
         "beats": [{"text": "one two three", "actions": [{"sfx": "footstep", "at": "@two", "repeat": 3, "every": 0.4, "pan": "right"}]}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    extensions.load_builtins()
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": 5, "media_dir": str(tmp_path / "media"),
                     "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}):
        with extensions.project_session(project):
            scene = registry.get("text_card").cls(project.scene("s"), project)
            scene.render()
    events = scene.timings()["sfx"]
    knocks = [e for e in events if e["sound"] == "knock"]
    steps = [e for e in events if e["sound"] == "footstep"]
    assert [e["time"] for e in knocks] == [0.2, 0.5] and all("room" not in e for e in knocks) and [e["pan"] for e in knocks] == [-0.5, 0.5]
    assert len(steps) == 3 and all(e["room"] == "hall" and e["pan"] == 0.5 for e in steps)
    assert [round(b["time"] - a["time"], 6) for a, b in zip(steps, steps[1:])] == [0.4, 0.4] and steps[1]["params"]["pitch"] == -1.5


@pytest.mark.slow
def test_render_with_beds_and_cues(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", DRAMA))
    _voice_all(project)
    result = render_audio(project)
    timings = json.loads(result.timings_file.read_text(encoding="utf-8"))
    street, lab = timings["scenes"]
    steps = [e for e in street["sfx"] if e["sound"] == "footstep"]
    assert len(steps) == 4 and all(e["pan"] == -0.5 and "room" not in e for e in steps)
    assert [round(b - a, 6) for a, b in zip([e["time"] for e in steps], [e["time"] for e in steps][1:])] == [0.4] * 3
    knock = next(e for e in lab["sfx"] if e["sound"] == "knock")
    assert knock["room"] == "small_office"
    assert {a["bed"] for a in timings["mix"]["ambience"]} == {"rain", "city", "hum"}
    x = _read_24(result.output)
    assert np.abs(x[: RATE // 2]).max() > 1e-4                                                                          # the beds before the first line


# ----- compatibility --------------------------------------------------------------------------------------

PIN: dict[str, Any] = {
    "title": "Pin",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "voices": {"b": {"voice_id": "other"}},
    "music": {"source": "calm"},
    "sections": [
        {"id": "one", "title": "One", "sfx": [{"sound": "chime", "at": 0.1}], "beats": ["one two three four", {"text": "a b c d", "voice": "b"}]},
        {"id": "two", "beats": [{"text": "e f g h", "sting": "reveal", "actions": [{"sfx": "pop", "at": 0.5}]}, {"text": "i j k l", "voice": "b"}]},
    ],
}


@pytest.mark.slow
def test_unset_options_change_nothing(tmp_path: Path) -> None:
    plain = Project.load(_write(tmp_path / "a", PIN))
    _voice_all(plain)
    same = {**PIN, "audio": {"ambience_crossfade": 5.0, "scene_sounds": True, "sfx_room": False}}
    same["sections"] = [{**PIN["sections"][0], "ambience": False}, PIN["sections"][1]]
    other = Project.load(_write(tmp_path / "b", same))
    _voice_all(other)
    assert render_audio(other).output.read_bytes() == render_audio(plain).output.read_bytes()


def test_fingerprint_ignores_ambience(tmp_path: Path) -> None:
    base = {"title": "t", "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "the rain"}]}]}
    plain = scene_fingerprint(Project.load(_write(tmp_path / "a", base)), "s")
    beds = {**base, "scenes": [{**base["scenes"][0], "ambience": "rain", "beats": [{"text": "the rain", "ambience": {"stop": "rain", "at": "@rain"}}]}]}
    assert scene_fingerprint(Project.load(_write(tmp_path / "b", beds)), "s") == plain


def test_the_video_join_adds_designed_beds(tmp_path: Path) -> None:
    from vidgen.render.pipeline import _add_designed_ambience

    data = {"title": "t", "narration": {"pad": 0.3, "words_per_second": 2}, "scenes": [
        {"id": "a", "type": "text_card", "params": {"text": "x"}, "ambience": "city", "beats": [{"text": "one two"}]},
        {"id": "b", "type": "text_card", "params": {"text": "y"}, "ambience": "hum", "beats": [{"text": "three four"}]}]}
    project = Project.load(_write(tmp_path / "p", data))
    scenes = [{"id": "a", "start": 0.0, "duration": 2.0, "beats": [{"id": "a_b1", "start": 0.0, "end": 1.3, "text": "one two"}],
               "ambience": [{"bed": "rain", "start": 0.0, "end": 2.0}]},
              {"id": "b", "start": 2.0, "duration": 2.0, "beats": [{"id": "b_b1", "start": 2.0, "end": 3.3, "text": "three four"}]}]
    _add_designed_ambience(project, scenes, 4.0)
    assert scenes[0]["ambience"][0] == {"bed": "rain", "start": 0.0, "end": 2.0}                                         # a stage's own bed stays
    assert [e["bed"] for e in scenes[0]["ambience"][1:]] == ["city"] and scenes[0]["ambience"][1]["end"] == 3.0
    assert scenes[1]["ambience"][0]["bed"] == "hum" and scenes[1]["ambience"][0]["start"] == 1.0


# ----- what scenes would sound like -----------------------------------------------------------------------

STAGE: dict[str, Any] = {
    "title": "Stage",
    "narration": {"pad": 0.3, "words_per_second": 2},
    "characters": [{"name": "pip", "look": {"body": "bean"}}, {"name": "kit", "look": {"body": "tall"}}],
    "scenes": [
        {"id": "yard", "type": "stage", "params": {"characters": [{"name": "pip", "at": "far_left"}, {"name": "kit", "at": "right"}], "particles": ["rain"]},
         "beats": [{"text": "pip walked over to kit", "actions": [{"walk_to": "pip", "to": "centre"}]},
                   {"text": "kit left and pip jumped", "actions": [{"exit": "kit", "to": "right"}, {"jump": "pip", "at": 0.5}]}]},
        {"id": "room", "type": "stage", "params": {"room": {"doors": [{"name": "front", "at": "left"}]}, "characters": ["pip"],
                                                    "props": [{"prop": "lamp", "name": "lamp", "at": "right"}], "light": "night"},
         "beats": [{"text": "someone knocked twice", "actions": [{"knock": "front", "at": "@knocked"}]},
                   {"text": "pip opened the door and switched the lamp on", "actions": [{"open": "front"}, {"switch_on": "lamp", "at": 0.5}]},
                   {"text": "pip was surprised", "actions": [{"emote": "pip", "to": "surprised"}, {"effect": "pip", "to": "idea"}]}]},
    ],
}


def test_stage_sounds_are_left_out_unless_asked(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", STAGE))
    plan = plan_audio(project)
    assert not any(s.events or s.ambience for s in plan.scenes) and "audio.scene_sounds: true plays most of them" in plan.left_out[0]


def test_stage_sounds_without_pictures(tmp_path: Path) -> None:
    project = Project.load(_write(tmp_path / "p", {**STAGE, "audio": {"scene_sounds": True, "sfx_room": True}}))
    with extensions.project_session(project):
        plan = plan_audio(project)
    yard, room = plan.scenes
    assert [a["bed"] for a in yard.ambience] == ["rain"] and [a["bed"] for a in room.ambience] == ["room_tone"]
    assert yard.ambience[0] == {"bed": "rain", "start": 0.0, "end": round(yard.duration, 6)}                       # as a video's stage: merged by the mix
    walk = [e for e in yard.events if e.sound == "footstep" and e.beat == yard.beats[0].id]
    assert len(walk) >= 3 and all(e.pan == walk[0].pan < 0 for e in walk)                                          # pip walks on the left half
    exit_steps = [e for e in yard.events if e.sound == "footstep" and e.beat == yard.beats[1].id]
    swoosh = [e for e in yard.events if e.sound == "swoosh"]
    assert exit_steps and all(e.pan > 0 for e in exit_steps) and swoosh                                          # kit leaves to the right
    first = yard.beats[0]
    assert walk[0].time > first.start + 0.5                                                                        # the set fades in first
    assert [e.sound for e in yard.events if e.sound == "boing"] == ["boing"]
    sounds = [e.sound for e in room.events]
    assert sounds == ["knock", "creak", "click", "pop", "chime"] and all(e.room is None for e in room.events)      # a stage's room is a set, no room: preset
    knock = room.events[0]
    assert room.beats[0].start < knock.time < room.beats[0].end
    assert "phones ringing" in plan.left_out[0]
    off = Project.load(_write(tmp_path / "q", {**STAGE, "foley": False, "audio": {"scene_sounds": True}}))
    with extensions.project_session(off):
        assert stage_sounds(off, _slots(off)[0]) == ([], [])


@pytest.mark.slow
def test_stage_sounds_in_the_render(tmp_path: Path) -> None:
    data = {**STAGE, "audio": {"scene_sounds": True}}
    data["scenes"] = [{**STAGE["scenes"][1], "room": "small_office"}]
    project = Project.load(_write(tmp_path / "p", data))
    _voice_all(project)
    result = render_audio(project)
    assert [e["sound"] for e in result.timings["scenes"][0]["sfx"]] == ["knock", "creak", "click", "pop", "chime"]
    assert result.timings["mix"]["ambience"][0]["bed"] == "room_tone"


@pytest.mark.slow
def test_clip_sound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import clips

    calls: list[dict[str, Any]] = []

    def fake_audio(path: Path, out: Path, timing: Any, *, length: float, volume: float, fade: float) -> bool:
        calls.append({"timing": timing, "length": length, "volume": volume, "fade": fade})
        write_wav(out, np.full((round(length * RATE), 2), 0.1, dtype=np.float32))
        return True

    monkeypatch.setattr(clips, "probe_clip", lambda path: clips.ClipInfo(64, 36, 25.0, 8.0, True, 2))
    monkeypatch.setattr(clips, "clip_audio", fake_audio)
    data = {"title": "t", "narration": {"pad": 0.3, "words_per_second": 2}, "audio": {"scene_sounds": True}, "scenes": [
        {"id": "c", "type": "video_clip", "params": {"path": "assets/a.mp4", "trim": [1.0, 5.0], "fit_duration": True}, "beats": [{"text": "one two three four"}]},
        {"id": "m", "type": "video_clip", "params": {"path": "assets/a.mp4", "mute": True}, "duration": 2.0},
        {"id": "s", "type": "video_clip", "params": {"path": "assets/a.mp4"}, "duration": 2.0}]}
    project = Project.load(_write(tmp_path / "p", data))
    slots = [SceneSlot(spec, 0.0, 4.0) for spec in project.config.scenes]
    assert clip_sound(project, slots[1], tmp_path / "clips") is None
    assert clip_sound(project, slots[0], tmp_path / "clips") == tmp_path / "clips" / "c.wav"
    assert calls[0]["timing"].speed == pytest.approx(1.0) and calls[0]["volume"] == 0.25 and calls[0]["timing"].start == 1.0
    clip_sound(project, slots[2], tmp_path / "clips")
    assert calls[1]["volume"] == 1.0                                                                                    # a silent scene: as recorded
    _voice_all(project)
    with extensions.project_session(project):
        plan = plan_audio(project)
    assert not plan.left_out or "video_clip" not in " ".join(plan.left_out)
    result = render_audio(project)
    voice = json.loads(result.timings_file.read_text(encoding="utf-8"))
    assert voice["duration"] > 4
    x = _read_24(result.output)
    start = round(plan.scenes[2].start * RATE)
    assert np.abs(x[start + RATE // 2 : start + RATE]).mean() > 0.01                                                   # the silent scene's clip is heard


def test_beat_slot_fraction_and_word(tmp_path: Path) -> None:
    from vidgen.sound_design import change_time

    project = Project.load(_write(tmp_path / "p", {"title": "t", "narration": {"words_per_second": 2},
                                                    "scenes": [{"id": "s", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": "one two three four"}]}]}))
    beat = project.config.scenes[0].beats[0]
    slot = BeatSlot(beat, 10.0, 12.0, 2.0)
    assert change_time(project, slot, 0.25) == 10.5 and change_time(project, slot, "end") == 12.0
    assert 10.5 < change_time(project, slot, "@three") < 11.5 and math.isclose(change_time(project, slot, "@three+0.2s") - change_time(project, slot, "@three"), 0.2)
    assert ambience_entries(project, [SceneSlot(project.config.scenes[0], 0.0, 3.0, [slot])], 3.0) == [[]]
