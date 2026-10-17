"""Step 153: sounds on a platform level — the take-off, the landing, a coin's and a star's sound
at each pickup (timed through the move's easing), a key unlocking a locked door before it creaks,
a blocker shuffling aside (the schedule, no manim), the new built-in sounds, and a tiny render
checking the sounds land on the frames the story's events happen, with foley off per scene."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from conftest import minimal_config
from test_cartoon_stage import CAST, render_with_layout
from test_platform_props import LEVEL, STORY, STORY_PROPS
from vidgen import sfx
from vidgen.cartoon.foley import (
    ASIDE_STEP,
    BOING_GAIN,
    DOOR_OPEN_CREAK,
    LEVEL_LANDING_THUD,
    PICKUP_PITCH_MAX,
    UNLOCK_GAIN,
    UNLOCK_SECONDS,
    PlayedAction,
    foley_cues,
)
from vidgen.cartoon.holding import RESHAPE_SHARE
from vidgen.cartoon.motion import Phases
from vidgen.project import Project


def _cues(played: PlayedAction) -> list[tuple[str, float, dict[str, float]]]:
    return [(c.sound, round(c.time, 6), dict(c.params)) for c in foley_cues(played)]


# ----- the schedule (no manim) ----------------------------------------------------------------------


def test_a_walk_plays_a_sound_at_each_coin_and_star_it_picks_up() -> None:
    played = PlayedAction("walk_to", 1.0, 4.0, heights=0.0, phases=Phases(0.1, 0.1),
                          pickups=((0.5, "coin"), (0.6, "coin"), (0.7, "star")))
    cues = [c for c in _cues(played) if c[0] != "footstep"]
    assert [c[0] for c in cues] == ["coin", "coin", "twinkle"]
    assert cues[0][1] == pytest.approx(3.0)   # half the distance is half the time (the walk eases evenly)
    assert cues[0][2] == {} and cues[1][2] == {"pitch": 1.0} and cues[2][2] == {}   # the second coin a semitone higher
    assert cues[0][1] < cues[1][1] < cues[2][1] < 1.0 + 0.9 * 4.0
    many = PlayedAction("run_to", 0.0, 2.0, pickups=tuple((k / 10, "coin") for k in range(9)))
    assert max(c.params.get("pitch", 0.0) for c in foley_cues(many)) == PICKUP_PITCH_MAX


def test_a_level_jump_takes_off_lands_and_picks_up_mid_air() -> None:
    played = PlayedAction("jump", 0.0, 2.0, phases=Phases(0.2, 0.25), lift=1.0, lands=0.75, pickups=((0.5, "star"),))
    cues = _cues(played)
    assert [c[0] for c in cues] == ["boing", "twinkle", "thud", "footstep"]
    assert cues[0][1] == pytest.approx(0.4)                  # the take-off, after the crouch
    assert cues[1][1] == pytest.approx(2.0 * (0.2 + 0.55 * 0.5))   # half the flight (x moves evenly)
    assert cues[2][1] == cues[3][1] == pytest.approx(1.5)    # touch-down: the settle starts
    assert cues[2][2] == {**LEVEL_LANDING_THUD[1], "intensity": 0.45}   # louder after a longer drop
    big = foley_cues(PlayedAction("jump", 0.0, 2.0, phases=Phases(0.2, 0.25), lift=9.0, lands=0.75))
    assert big[1].params["intensity"] == 0.7
    plain = foley_cues(PlayedAction("jump", 0.0, 1.0, phases=Phases(0.2, 0.2), lift=0.5))
    assert [(c.sound, c.gain) for c in plain] == [("boing", BOING_GAIN)]   # a jump in place on a plain stage: as before


def test_a_key_clicks_the_lock_before_the_door_creaks() -> None:
    locked = foley_cues(PlayedAction("open", 2.0, 1.5, prop="door", unlocks=True))
    assert [(c.sound, c.time, c.gain) for c in locked] == [("unlock", 2.0, UNLOCK_GAIN), ("creak", 2.0 + UNLOCK_SECONDS, DOOR_OPEN_CREAK[0])]
    quick = foley_cues(PlayedAction("open", 0.0, 0.4, prop="door", unlocks=True))
    assert quick[1].time == pytest.approx(RESHAPE_SHARE * 0.4)   # never after the door swings
    assert [c.sound for c in foley_cues(PlayedAction("open", 0.0, 1.0, prop="door"))] == ["creak"]


def test_a_blocker_shuffles_aside() -> None:
    cues = foley_cues(PlayedAction("step_aside", 1.0, 1.2, heights=0.6, phases=Phases(0.1, 0.1)))
    assert cues[0].sound == "swoosh" and cues[0].time == 1.0 and cues[0].gain < -10   # soft and low
    steps = [c for c in cues if c.sound == "footstep"]
    assert steps and all(c.gain == ASIDE_STEP[0] and c.params["pitch"] <= ASIDE_STEP[1] for c in steps)


@pytest.mark.parametrize("name", ["unlock", "coin", "twinkle"])
def test_the_new_sounds_are_soft_and_at_the_library_level(name: str) -> None:
    x = sfx.synthesize(name)
    assert sfx.peak_db(x) <= sfx.PEAK_CEILING + 1e-3
    assert sfx.loudness(x) <= sfx.LOUDNESS_TARGET + 0.1
    spectrum = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sfx.RATE)
    assert spectrum[freqs > 8000].sum() < 0.05 * spectrum.sum()   # nothing shrill
    assert name in sfx.BUILTIN_SOUNDS and "platform level" in sfx.BUILTIN_SOUNDS[name].use


# ----- render ---------------------------------------------------------------------------------------


def _project(make_project, **params: Any) -> Project:
    stage = {"level": LEVEL, "idle": False, "props": STORY_PROPS, **params,
             "characters": [{"name": "pip", "at": "start"}, {"name": "kit", "at": "path", "facing": "left"}]}
    scenes = [{"id": "hills", "type": "stage", "params": stage, "beats": STORY}]
    return Project.load(make_project(minimal_config(characters=CAST, scenes=scenes)))


@pytest.mark.render
def test_the_story_sounds_on_its_events(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.cartoon.level_items import Collectible
    from vidgen.scenes.stage import Stage

    popped: dict[str, float] = {}
    scenes: list[Stage] = []
    collect, story = Collectible.collect, Stage._level_story

    def record(self: Collectible) -> None:
        if self.collected is None:   # the scene time of the frame drawn
            popped[self.kind if self.kind == "star" else self.name] = float(scenes[-1].renderer.time)
        collect(self)

    def level_story(self: Stage) -> Any:
        scenes.append(self)
        return story(self)

    monkeypatch.setattr(Collectible, "collect", record)
    monkeypatch.setattr(Stage, "_level_story", level_story)
    scene, _ = render_with_layout(_project(make_project), "hills", tmp_path / "media")
    log = scene.sfx_log
    frame = 1 / 5
    coins = [e for e in log if e.sound == "coin"]
    assert [e.params.get("pitch", 0.0) for e in coins] == [0.0, 1.0]
    assert [e.time for e in coins] == pytest.approx([popped["coin_1"], popped["coin_2"]], abs=frame + 1e-6)
    [star] = [e for e in log if e.sound == "twinkle"]
    assert star.time == pytest.approx(popped["star"], abs=frame + 1e-6)   # mid-air
    [boing] = [e for e in log if e.sound == "boing"]
    [thud] = [e for e in log if e.sound == "thud"]
    landing_step = [e for e in log if e.sound == "footstep" and e.time == thud.time]
    assert boing.beat == star.beat == thud.beat == "hills_b4" and boing.time < star.time < thud.time and landing_step
    [unlock] = [e for e in log if e.sound == "unlock"]
    [creak] = [e for e in log if e.sound == "creak"]
    assert creak.time == pytest.approx(unlock.time + UNLOCK_SECONDS) and unlock.beat == "hills_b3"
    assert any(e.sound == "swoosh" and e.beat == "hills_b5" for e in log)   # kit steps aside
    track = tmp_path / "sfx.wav"
    sfx.write_track(track, log, round((max(e.time for e in log) + 2.0) * sfx.RATE), scene.sounds)
    mixed = sfx.read_wav(track)
    assert sfx.peak_db(mixed) < -3.0 and sfx.loudness(mixed) < -20.0   # coins in a row stay well under narration

    quiet, _ = render_with_layout(_project(make_project, foley=False), "hills", tmp_path / "media2")
    assert quiet.sfx_log == [] and all(item.gone for item in quiet.level_pickups.values())
