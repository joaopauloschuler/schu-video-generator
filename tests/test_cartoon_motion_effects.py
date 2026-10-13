"""Step 108: motion effects (dust, speed lines, impact stars, whoosh arcs) and ``run_to``: when each
effect fires and its shapes (no manim), the run's gait, the effects following their movers (manim,
no render), lint and the layout dump, validate, and tiny renders: effects on, and off
(``motion_effects: false``) pixel for pixel as without the effect code."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from test_cartoon_acting import acting_project, figure
from test_cartoon_effects import symbol
from test_cartoon_lint import check, fig
from test_cartoon_stage import render_with_layout
from vidgen.cartoon.acting import GESTURE_SECONDS, RUN_SPEED, RUNNING, STEP_LENGTH, WALK_SPEED, WALKING, walk_cycle, walk_seconds
from vidgen.cartoon.foley import PlayedAction, foley_cues, footfall_shares
from vidgen.cartoon.motion import MOTION_LEVELS, jump_phases, walk_motion_seconds, walk_phases
from vidgen.cartoon.motion_effects import (
    DUST_SECONDS,
    FAST_SPEED,
    HARD_LANDING,
    IMPACT_SECONDS,
    arc_band,
    dust_puffs,
    effect_scale,
    impact_stars,
    motion_effect_cues,
    motion_seed,
    speed_lines,
)
from vidgen.cartoon.transition import Gesture, Walk
from vidgen.cli import check_project

LIVELY, CALM, NONE = MOTION_LEVELS["lively"], MOTION_LEVELS["calm"], MOTION_LEVELS["none"]


def walk(action: str, top_speed: float, *, start: float = 2.0, strength: float = LIVELY) -> PlayedAction:
    """A walk of 3 heights whose top speed is ``top_speed`` heights per second, as it played."""
    feet = walk_seconds(3.0, top_speed)
    phases = walk_phases(feet, strength)
    return PlayedAction(action, start, walk_motion_seconds(feet, strength), heights=3.0, phases=phases)


def kinds(cues: list[Any]) -> list[tuple[str, str]]:
    return [(c.kind, c.toward) for c in cues]


# ----- when each effect fires (no manim) ------------------------------------------------------------


def test_a_fast_walk_raises_dust_at_both_ends_and_leaves_speed_lines() -> None:
    assert motion_effect_cues(walk("walk_to", 0.7), LIVELY) == []   # a walk at the default speed: nothing
    assert motion_effect_cues(walk("walk_to", FAST_SPEED * 0.99), LIVELY) == []
    played = walk("run_to", 1.7)
    cues = motion_effect_cues(played, LIVELY)
    assert kinds(cues) == [("dust", "back"), ("speed_lines", "both"), ("dust", "front")]
    set_off = played.start + played.phases.before * played.seconds
    stop = played.start + (1 - played.phases.after) * played.seconds
    assert cues[0].time == pytest.approx(set_off) and cues[2].time == pytest.approx(stop) and cues[0].seconds == DUST_SECONDS
    assert set_off < cues[1].time < cues[1].time + cues[1].seconds < stop   # lines only near full speed
    assert motion_effect_cues(walk("walk_to", 1.7), LIVELY) == cues   # a fast walk counts as a run
    assert kinds(motion_effect_cues(walk("enter", 1.7), LIVELY)) == [("speed_lines", "both"), ("dust", "front")]   # set off unseen
    assert kinds(motion_effect_cues(walk("exit", 1.7), LIVELY)) == [("dust", "back"), ("speed_lines", "both")]   # stops unseen


def test_jumps_land_in_dust_and_hard_landings_throw_stars() -> None:
    phases = jump_phases(0.6, LIVELY)
    hop = PlayedAction("jump", 1.0, 1.08, phases=phases, lift=0.4)
    (dust,) = motion_effect_cues(hop, LIVELY)
    assert (dust.kind, dust.toward) == ("dust", "both") and dust.time == pytest.approx(1.0 + (1 - phases.after) * 1.08)
    hard = motion_effect_cues(PlayedAction("jump", 1.0, 1.08, phases=phases, lift=HARD_LANDING), LIVELY)
    assert [c.kind for c in hard] == ["dust", "impact"] and hard[1].seconds == IMPACT_SECONDS and hard[1].time == dust.time


def test_flying_props_and_big_gestures() -> None:
    (lines,) = motion_effect_cues(PlayedAction("throw", 0.0, 2.0, flight=(0.25, 0.75)), LIVELY)
    assert (lines.kind, lines.time, lines.seconds) == ("speed_lines", 0.5, 1.0)
    assert [c.kind for c in motion_effect_cues(PlayedAction("blow_away", 0.0, 2.0, flight=(0.0, 1.0)), LIVELY)] == ["speed_lines"]
    assert motion_effect_cues(PlayedAction("put_down", 0.0, 1.0), LIVELY) == []   # no flight
    wave = motion_effect_cues(PlayedAction("gesture", 3.0, 1.6, gesture="wave", big=True), LIVELY)
    assert [(c.kind, c.arm) for c in wave] == [("whoosh", None)] and 3.0 < wave[0].time < 3.0 + 0.25 * 1.6
    shrug = motion_effect_cues(PlayedAction("gesture", 0.0, 1.0, gesture="shrug", big=True), LIVELY)
    assert [c.arm for c in shrug] == ["arm_left", "arm_right"]
    assert motion_effect_cues(PlayedAction("gesture", 0.0, 1.6, gesture="wave"), LIVELY) == []   # not big
    assert motion_effect_cues(PlayedAction("gesture", 0.0, 0.9, gesture="nod", big=True), LIVELY) == []   # no sweep


def test_cartoon_motion_none_turns_every_effect_off_and_calm_draws_them_smaller() -> None:
    playeds = [
        walk("run_to", 2.0, strength=NONE), PlayedAction("jump", 0.0, 0.6, lift=1.0),
        PlayedAction("throw", 0.0, 1.0, flight=(0.2, 1.0)), PlayedAction("gesture", 0.0, 1.0, gesture="point", big=True),
    ]
    assert all(motion_effect_cues(p, NONE) == [] for p in playeds)
    assert all(motion_effect_cues(p, CALM) != [] for p in playeds)
    assert effect_scale(NONE) < effect_scale(CALM) < effect_scale(LIVELY) == 1.0


# ----- shapes (no manim) ----------------------------------------------------------------------------


def test_shapes_are_seeded_and_end() -> None:
    seed = motion_seed("park", "pip", "dust", 1.25)
    assert seed == motion_seed("park", "pip", "dust", 1.25) != motion_seed("park", "kit", "dust", 1.25)
    assert dust_puffs(0.2, seed, "back") == dust_puffs(0.2, seed, "back") != dust_puffs(0.2, seed + 1, "back")
    back, front = dust_puffs(0.3, seed, "back"), dust_puffs(0.3, seed, "front")
    assert back and all(p.x < 0 for p in back) and all(p.x > 0 for p in front)   # blown away from the step
    both = dust_puffs(0.3, seed, "both")
    assert min(p.x for p in both) < 0 < max(p.x for p in both) and all(p.y > 0 and 0 < p.opacity <= 1 for p in both)
    assert dust_puffs(0.0, seed) == [] and dust_puffs(DUST_SECONDS, seed) == []
    late = dust_puffs(DUST_SECONDS * 0.9, seed)
    assert late and max(p.opacity for p in late) < 0.2   # fading out
    stars = impact_stars(0.25, seed)
    assert len(stars) == 4 and all(s.y > 0 and s.size > 0 for s in stars) and impact_stars(IMPACT_SECONDS, seed) == []
    assert speed_lines(0.0, 1.0, seed) == [] == speed_lines(1.0, 1.0, seed)
    lines = speed_lines(0.5, 1.0, seed)
    assert len(lines) == 3 and all(line.length > 0 and line.behind > 0 and line.opacity == 1.0 for line in lines)
    assert sorted(line.across for line in lines) == [line.across for line in lines]   # three lanes, bottom to top


def test_arc_band_tapers_to_the_hand() -> None:
    band = arc_band(0.0, 0.0, 1.0, 0.0, 90.0, 0.2)
    area = 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(band, [*band[1:], band[0]]))
    assert area > 0   # counterclockwise
    radii = [float(np.hypot(x, y)) for x, y in band]
    assert min(radii) == pytest.approx(0.9) and max(radii) == pytest.approx(1.1)
    tail = [r for (x, y), r in zip(band, radii) if abs(y) < 1e-9]
    assert tail == pytest.approx([1.0])   # nothing wide at the start of the arc


# ----- run_to's gait (no manim) ---------------------------------------------------------------------


def test_a_run_has_longer_strides_bigger_swings_and_its_own_footfalls() -> None:
    assert walk_cycle(0.5, 0.8, WALKING) == walk_cycle(0.5, 0.8)   # a walk is unchanged
    walking, running = walk_cycle(0.5, 1.0), walk_cycle(0.5, 1.0, RUNNING)
    assert running.thigh_angle == pytest.approx(walking.thigh_angle * RUNNING.swing)
    assert running.arm_angle > walking.arm_angle and walk_cycle(1.0, 1.0, RUNNING).knee_bends[1] > walk_cycle(1.0).knee_bends[1]
    assert RUN_SPEED > 2 * WALK_SPEED and RUNNING.stride > 1 and RUNNING.lean > 0
    assert len(footfall_shares(3.0, step_length=STEP_LENGTH * RUNNING.stride)) < len(footfall_shares(3.0))
    steps = [c for c in foley_cues(PlayedAction("run_to", 0.0, 2.0, heights=3.0, step_length=STEP_LENGTH * RUNNING.stride)) if c.sound == "footstep"]
    assert len(steps) == len(footfall_shares(3.0, step_length=STEP_LENGTH * RUNNING.stride))


# ----- manim, no render ------------------------------------------------------------------------------


def test_a_run_leans_forward() -> None:
    pip = figure()
    pip.motion = "none"
    body = pip.pose_of("body").angle
    run = Walk(pip, float(pip.feet()[0]) + 6.0, speed=RUN_SPEED, gait=RUNNING)
    assert run.step_length == pytest.approx(STEP_LENGTH * RUNNING.stride)
    run.begin()
    run.interpolate(0.5)
    assert pip.pose_of("body").angle == pytest.approx(body - RUNNING.lean)   # full speed: leaning forward
    run.interpolate(1.0)
    run.finish()
    assert pip.pose_of("body").angle == pytest.approx(body)


def test_effects_follow_their_mover_and_leave_it_alone() -> None:
    from manim import Circle

    from vidgen.cartoon.motion_effect_shapes import MotionEffect
    from vidgen.cartoon.motion_effects import MotionEffectCue

    pip = figure()
    family = list(pip.get_family())
    feet = pip.feet().copy()
    dust = MotionEffect(MotionEffectCue("dust", 0.5, DUST_SECONDS, "back"), pip, delay=0.5, seed=3, effect_of="pip")
    dust.update(0.3)
    assert not dust.family_members_with_points()   # not started yet
    dust.update(0.4)
    assert dust.family_members_with_points() and dust.get_center()[0] < feet[0]   # behind pip, who faces right
    pip.shift([3.0, 0.0, 0.0])
    dust.update(0.05)
    assert dust.get_center()[0] < feet[0] + 0.5   # dust stays where it rose
    dust.update(1.0)
    assert dust.done and not dust.family_members_with_points()
    lines = MotionEffect(MotionEffectCue("speed_lines", 0.0, 1.0), pip, delay=0.0, seed=3)
    lines.update(0.5)
    assert lines.get_right()[0] < pip.get_left()[0]   # behind its back, going along with it
    assert list(pip.get_family()) == family   # nothing added to the character (DESIGN.md §69.22)

    ball = Circle(radius=0.15)
    flying = MotionEffect(MotionEffectCue("speed_lines", 0.0, 1.0), ball, delay=0.0, seed=4)
    for _ in range(5):
        ball.shift([0.3, 0.1, 0.0])
        flying.update(0.1)
    assert flying.family_members_with_points() and flying.get_center()[0] < ball.get_center()[0]

    waver = figure()
    wave = Gesture(waver, "wave")
    whoosh = MotionEffect(MotionEffectCue("whoosh", 0.0, 0.6), waver, delay=0.0, seed=5)
    wave.begin()
    drawn = []
    for k in range(1, 31):
        wave.interpolate(k * 0.02 / GESTURE_SECONDS["wave"] * 1.0)
        whoosh.update(0.02)
        drawn.append(bool(whoosh.family_members_with_points()))
    assert any(drawn)


# ----- lint and the layout dump (no render) -------------------------------------------------------------


def motion(box: list[float], kind: str = "speed_lines", of: str = "pip", order: int = 20) -> dict[str, Any]:
    return {**symbol(box, of=of, order=order), "kind": "motion_effect", "class": "MotionEffect", "name": kind, "motion_effect": kind}


def test_lint_leaves_motion_effects_alone() -> None:
    assert check("off_frame", [motion([-60, 200, 40, 220])]) == []   # an exit's lines leave the frame
    speaker = fig("pip", [100, 100, 200, 400], order=5, speaking=True, face=[110, 100, 190, 200])
    assert check("hidden_speaker", [speaker, motion([90, 120, 210, 160], order=9)]) == []
    from vidgen.lint.layout_rules import describe

    assert describe(motion([0, 0, 1, 1], "dust", "moss")) == "motion effect 'dust' of 'moss'"


def test_validate_run_to_and_big_gestures(make_project) -> None:
    good = acting_project(make_project, [
        {"text": "Pip runs over and waves.", "actions": [{"run_to": "pip", "to": "centre"}, {"gesture": "pip", "to": "wave", "big": True, "at": 0.6}]},
        {"text": "Kit runs back.", "actions": [{"run_to": "kit", "to": 0.9, "speed": 8}]},
    ], motion_effects=False)
    assert check_project(good) == []
    bad = acting_project(make_project, [{"text": "Hello.", "actions": [{"run_to": "pip", "to": "nowhere"}, {"run_to": "tree", "to": 0.5}]}])
    problems = check_project(bad)
    assert problems[0].startswith("scenes[0].beats[0].actions[0].to: unknown mark 'nowhere'"), problems
    assert problems[1].startswith("scenes[0].beats[0].actions[1].target: 'tree' is not a character; run_to acts on characters"), problems


# ----- renders --------------------------------------------------------------------------------------------

BEATS: list[dict[str, Any]] = [
    {"text": "Pip runs across to the tree and back.", "actions": [{"run_to": "pip", "to": 0.6}]},
    {"text": "Kit jumps up high and lands.", "actions": [{"jump": "kit", "height": 0.9}]},
]


def frame_hashes(project: Any, media: Path, monkeypatch) -> tuple[Any, list[str], list[Any]]:
    """Render ``park`` at 160x90: the scene, a hash per frame written and every still's objects."""
    from manim.scene.scene_file_writer import SceneFileWriter

    from vidgen.introspect import LayoutRecorder

    hashes: list[str] = []
    write = SceneFileWriter.write_frame

    def recording(self: Any, frame: Any, num_frames: int = 1) -> None:
        hashes.extend([hashlib.sha1(np.asarray(frame).tobytes()).hexdigest()] * num_frames)
        write(self, frame, num_frames)

    monkeypatch.setattr(SceneFileWriter, "write_frame", recording)
    recorder = LayoutRecorder()
    scene, _ = render_with_layout(project, "park", media, recorder)
    monkeypatch.setattr(SceneFileWriter, "write_frame", write)
    return scene, hashes, [o for f in recorder.frames for o in f["objects"]]


@pytest.mark.render
def test_motion_effects_on_a_stage(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()

    stage = registry.get("stage").cls
    added: list[Any] = []
    add = stage._add_motion_effect
    monkeypatch.setattr(stage, "_add_motion_effect", lambda self, effect, mover, behind: (added.append(effect), add(self, effect, mover, behind=behind)))
    scene, _, objects = frame_hashes(acting_project(make_project, BEATS), tmp_path / "on", monkeypatch)
    assert {e.kind for e in added} == {"dust", "speed_lines", "impact"} and {e.effect_of for e in added} == {"pip", "kit"}
    assert any(o["kind"] == "motion_effect" and o["effect_of"] == "pip" for o in objects)   # the mid-run still shows them
    assert scene.motion_effects == [] and not [m for m in scene.mobjects if type(m).__name__ == "MotionEffect"]   # swept off
    assert scene._motion_sweep not in scene.updaters
    added.clear()
    frame_hashes(acting_project(make_project, BEATS, cartoon_motion="none"), tmp_path / "none", monkeypatch)
    assert added == []   # cartoon_motion: none, no effects


@pytest.mark.render
def test_motion_effects_off_render_as_without_them(make_project, tmp_path: Path, monkeypatch) -> None:
    from vidgen import extensions, registry

    extensions.load_builtins()

    _, off, _ = frame_hashes(acting_project(make_project, BEATS, motion_effects=False), tmp_path / "off", monkeypatch)
    monkeypatch.setattr(registry.get("stage").cls, "action_motion_effects", lambda *args: None)
    _, without, _ = frame_hashes(acting_project(make_project, BEATS), tmp_path / "without", monkeypatch)
    assert len(off) > 10 and off == without   # pixel for pixel
