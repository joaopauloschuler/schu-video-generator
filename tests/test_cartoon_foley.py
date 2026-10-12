"""Step 86: foley (sounds tied to the characters' actions on a ``stage``) and a beat's music
``sting``: the action -> sound schedule (no manim), the new built-in sounds, the config, the
ducked SFX track, and one tiny render checking what a stage records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_acting import CAST, VOICES, acting_project
from test_cartoon_stage import render_with_layout
from vidgen import mix, registry, sfx
from vidgen.cartoon.acting import STEP_LENGTH, walk_progress
from vidgen.cartoon.foley import (
    BOING_GAIN,
    FOOTSTEP_GAIN,
    LAST_STEP_INTENSITY,
    PlayedAction,
    footfall_shares,
    foley_cues,
)
from vidgen.cartoon.motion import Phases, jump_phases, walk_phases
from vidgen.config import BeatConfig, StingCue, parse_config
from vidgen.extensions import load_builtins
from vidgen.project import Project

RATE = sfx.RATE


# ----- footfalls and the schedule (no manim) --------------------------------------------------------


def test_footfalls_land_every_step() -> None:
    """A foot lands each half step past a whole step of the distance walked, plus one at the stop
    when the walk ends between footfalls; the wind-up and settle are standing still."""
    heights = 2.1   # 6 steps: footfalls at 0.5 .. 5.5 steps, then the feet come together
    shares = footfall_shares(heights)
    assert len(shares) == 7 and shares[-1] == (1.0, True) and not any(last for _, last in shares[:-1])
    steps = [walk_progress(share) * heights / STEP_LENGTH for share, _ in shares[:-1]]
    assert steps == pytest.approx([k + 0.5 for k in range(6)])
    assert [s for s, _ in shares] == sorted(s for s, _ in shares)
    assert footfall_shares(5.5 * STEP_LENGTH)[-1][1] is False   # stops on a footfall: no extra step
    assert footfall_shares(0.0) == [] and footfall_shares(0.3 * STEP_LENGTH) == [(1.0, True)]   # a shuffle: one step
    phases = walk_phases(2.0, 1.0)
    wound = footfall_shares(heights, phases)
    move = 1 - phases.before - phases.after
    assert [s for s, _ in wound] == pytest.approx([phases.before + move * s for s, _ in shares])
    assert wound[0][0] > phases.before and wound[-1][0] == pytest.approx(1 - phases.after)


def test_walks_play_footsteps_timed_as_they_played() -> None:
    walk = PlayedAction("walk_to", 3.0, 2.0, heights=2.1)
    cues = foley_cues(walk)
    assert {c.sound for c in cues} == {"footstep"} and len(cues) == 7
    assert [c.time for c in cues] == pytest.approx([3.0 + 2.0 * s for s, _ in footfall_shares(2.1)])
    assert all(c.gain == FOOTSTEP_GAIN for c in cues)
    assert [c.params["pitch"] for c in cues[:3]] == [0.0, -1.5, 0.0]   # left, right, left
    assert cues[-1].params["intensity"] == LAST_STEP_INTENSITY
    rushed = foley_cues(PlayedAction("walk_to", 3.0, 1.0, heights=2.1))   # the beat shortened it
    assert [c.time - 3.0 for c in rushed] == pytest.approx([(c.time - 3.0) / 2 for c in cues])


def test_enter_exit_jump_and_surprise() -> None:
    enter = foley_cues(PlayedAction("enter", 1.0, 2.0, heights=1.0))
    assert enter[0].sound == "whoosh" and enter[0].time == 1.0 and {c.sound for c in enter[1:]} == {"footstep"}
    phases = walk_phases(1.0, 1.0)
    leave = foley_cues(PlayedAction("exit", 1.0, 2.0, heights=1.0, phases=phases))
    swoosh = [c for c in leave if c.sound == "swoosh"]
    assert len(swoosh) == 1 and swoosh[0].align == "end" and swoosh[0].time == pytest.approx(1.0 + 2.0 * (1 - phases.after))
    jump = jump_phases(0.6, 1.0)
    [boing] = foley_cues(PlayedAction("jump", 2.0, 1.0, phases=jump))
    assert boing.sound == "boing" and boing.time == pytest.approx(2.0 + jump.before) and boing.gain == BOING_GAIN
    assert foley_cues(PlayedAction("jump", 2.0, 0.6))[0].time == 2.0   # cartoon_motion none: no crouch
    assert [c.sound for c in foley_cues(PlayedAction("emote", 0.5, 0.5, expression="surprised"))] == ["pop"]
    assert [c.sound for c in foley_cues(PlayedAction("react", 0.5, 0.6, expression="surprised"))] == ["pop"]
    assert foley_cues(PlayedAction("emote", 0.5, 0.5, expression="happy")) == []
    for quiet in ("gesture", "say", "look_at", "pose", "zoom", "keyframes"):
        assert foley_cues(PlayedAction(quiet, 0.0, 1.0, heights=1.0, phases=Phases(0.2, 0.2))) == []


# ----- the sounds ------------------------------------------------------------------------------------


def test_new_builtin_sounds() -> None:
    """The foley and sting sounds are built-ins like the others (test_sfx checks every built-in
    for clicks, DC and level); each sting is the sound of its kind."""
    assert {"footstep", "boing", "sting_reveal", "sting_comic", "sting_sad"} <= set(sfx.BUILTIN_SOUNDS)
    assert set(sfx.STING_SOUNDS) == {"reveal", "comic", "sad"} and set(sfx.STING_SOUNDS.values()) <= set(sfx.BUILTIN_SOUNDS)
    comic = sfx.synthesize("sting_comic")
    cymbal = int(0.33 * RATE)
    spectrum = np.abs(np.fft.rfft(comic[cymbal : cymbal + int(0.1 * RATE)]))
    freqs = np.fft.rfftfreq(int(0.1 * RATE), 1 / RATE)
    assert spectrum[freqs > 4000].sum() > spectrum[freqs < 1000].sum()   # the splash is high
    sad = sfx.synthesize("sting_sad")

    def pitch(a: float, b: float) -> float:
        x = sad[int(a * RATE) : int(b * RATE)].astype(np.float64)
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 1 << 18))
        f = np.fft.rfftfreq(1 << 18, 1 / RATE)
        band = (f > 150) & (f < 260)
        return float(f[band][np.argmax(spec[band])])

    assert pitch(0.05, 0.35) > pitch(0.47, 0.77) > pitch(0.89, 1.19) > pitch(1.35, 1.8)   # falling notes


# ----- config ----------------------------------------------------------------------------------------


def test_sting_and_foley_config() -> None:
    assert BeatConfig(id="b", text="Hi.", sting="comic").sting == StingCue(kind="comic")
    assert StingCue(kind="reveal").placed_at == "start" and StingCue(kind="sad").placed_at == "end"
    assert StingCue(kind="reveal", at="end").placed_at == "end"
    with pytest.raises(ValueError):
        BeatConfig(id="b", text="Hi.", sting="drumroll")
    config = parse_config(minimal_config())
    assert config.foley is True and parse_config(minimal_config(foley=False)).foley is False
    load_builtins()
    stage = registry.get("stage").cls
    assert stage.validate_params({}).foley is None and stage.validate_params({"foley": False}).foley is False


# ----- the SFX track: stings duck under the narration -------------------------------------------------


def test_ducked_events_follow_the_narration(make_project, tmp_path: Path) -> None:
    """``mix.sting_ducking`` is the music's ducking curve (``duck_curve`` over ``speech_spans``)
    with :data:`mix.STING_DUCK`; ``write_track`` scales only the events marked ``duck``."""
    project = Project.load(make_project(minimal_config()))
    timings = {"scenes": [{"beats": [{"id": "nothing_here", "start": 1.0, "end": 2.0}]}]}   # no MP3: the whole beat
    total = 4 * RATE
    curve = mix.sting_ducking(project, timings, total)
    assert curve[50] == 0.0 and curve[150] == -mix.STING_DUCK.depth and curve[300] == 0.0
    assert np.array_equal(curve, mix.duck_curve([(1.0, 2.0)], total // mix.FRAME + 2, mix.STING_DUCK))
    library = sfx.SoundLibrary(None)
    events = [sfx.SfxEvent(1.2, "pop"), sfx.SfxEvent(1.5, "pop", duck=True), sfx.SfxEvent(3.0, "pop", duck=True)]
    assert sfx.SfxEvent.from_json(events[1].to_json()) == events[1] and "duck" not in events[0].to_json()
    path = tmp_path / "sfx.wav"
    sfx.write_track(path, events, total, library, ducking_db=curve)
    track = sfx.read_wav(path)

    def level(at: float) -> float:
        start = round(at * RATE)
        return sfx.peak_db(track[start : start + int(0.12 * RATE)])

    assert level(1.5) == pytest.approx(level(1.2) - mix.STING_DUCK.depth, abs=0.1)   # under speech: ducked
    assert level(3.0) == pytest.approx(level(1.2), abs=0.1)   # after the release: full level


# ----- a stage records its foley and stings (tiny render) --------------------------------------------


@pytest.mark.render
def test_a_stage_records_foley_and_a_sting(make_project, tmp_path: Path) -> None:
    beats: list[dict[str, Any]] = [
        {"text": "Pip walks over to the tree and jumps for joy.", "voice": "pip_voice", "sting": "comic",
         "actions": [{"walk_to": "pip", "to": "centre", "speed": 6}, {"jump": "pip", "at": 0.6}, {"emote": "kit", "to": "surprised"}]},
    ]
    project = acting_project(make_project, beats)
    scene, _ = render_with_layout(project, "park", tmp_path / "media")
    log = scene.sfx_log
    sounds = [e.sound for e in log]
    assert sounds.count("footstep") >= 3 and sounds.count("boing") == 1 and sounds.count("pop") == 1
    steps = [e.time for e in log if e.sound == "footstep"]
    boing = next(e for e in log if e.sound == "boing")
    walk = next(p for p in scene.play_log if "Walk" in p.animations)
    assert walk.start <= steps[0] and steps[-1] <= walk.end + 1e-6 < boing.time
    [sting] = [e for e in log if e.sound == "sting_comic"]
    beat = scene.beat_log[0]
    assert sting.duck and sting.time == pytest.approx(beat.end) and sting.beat == beat.beat_id   # when the line ends
    assert all(not e.duck for e in log if e is not sting)

    quiet = acting_project(make_project, beats, foley=False)
    scene, _ = render_with_layout(quiet, "park", tmp_path / "media2")
    assert [e.sound for e in scene.sfx_log] == ["sting_comic"]   # foley off; the sting stays
