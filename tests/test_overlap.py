"""Step 100: overlapping speech and interruptions. The timeline maths, the mix plan, the caption
layout, validation, lint and directing without rendering; one tiny stage render (both mouths
during an overlap, the cut of an interruption). Also the wind updater removing itself (Step 99's
finding). Beats without the keys keep their timings and audio: tests/test_overlap_pinned.py."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config
from test_captions import built
from test_cartoon_acting import CAST, VOICES
from test_cartoon_stage import render_with_layout
from vidgen import extensions, registry
from vidgen.cartoon.directing import project_directions
from vidgen.cartoon.visemes import VisemeCue, VisemeTrack
from vidgen.cli import validate_warnings
from vidgen.config import LintConfig, VideoConfig
from vidgen.cues import CaptionCue, overlapping_beats, stack_cues
from vidgen.lint import timing_rules
from vidgen.lint.rules import SceneContext
from vidgen.overlap import (
    DIP_RAMP,
    INTERRUPT_FADE,
    INTERRUPT_LEAD,
    INTERRUPT_WORD_SHARE,
    MIN_WINDOW,
    OVERLAP_DIP_DB,
    BeatWindow,
    SpokenLine,
    VoiceShape,
    beat_windows,
    shape_voice,
    talked_over,
)
from vidgen.project import Project
from vidgen.speech import WordTime
from vidgen.subtitles import cues_from_timings
from vidgen.videoplan import VideoPlan

# ----- timeline maths ----------------------------------------------------------------------------


def test_windows_without_keys_are_d_plus_pad() -> None:
    lines = [SpokenLine(1.3, 1.1), SpokenLine(0.7, 0.7)]
    assert beat_windows(lines, 0.4) == [BeatWindow(1.3, 0.4, 1.3), BeatWindow(0.7, 0.4, 0.7)]
    assert beat_windows(lines, 0.4)[0].window == 1.3 + 0.4 and not beat_windows(lines, 0.4)[0].joined


def test_overlap_and_interrupt_windows() -> None:
    # speech of the first line ends at 1.8 s of 2.0 s (trailing silence); the second starts 0.5 s before
    first, second, third = beat_windows([SpokenLine(2.0, 1.8), SpokenLine(1.0, 1.0, overlap=0.5), SpokenLine(1.2, 1.2, interrupt=True)], 0.4)
    assert (first.body, first.rest, first.heard) == (pytest.approx(1.3), 0.0, 2.0)   # heard to its end, under the second
    assert first.shape == VoiceShape(dip_from=pytest.approx(1.3)) and first.joined
    assert (second.body, second.heard) == (pytest.approx(1.0 - INTERRUPT_LEAD), pytest.approx(1.0 - INTERRUPT_LEAD))   # cut where the third starts
    assert second.shape == VoiceShape(cut=pytest.approx(1.0 - INTERRUPT_LEAD)) and second.next_lead == pytest.approx(INTERRUPT_LEAD)
    assert third == BeatWindow(1.2, 0.4, 1.2)   # the last beat keeps its pad
    # an interrupt with an overlap; an overlap longer than the line keeps MIN_WINDOW
    assert beat_windows([SpokenLine(3.0, 3.0), SpokenLine(1.0, 1.0, overlap=1.2, interrupt=True)], 0.4)[0].shape.cut == pytest.approx(1.8)
    assert beat_windows([SpokenLine(0.5, 0.5), SpokenLine(1.0, 1.0, overlap=2.0)], 0.4)[0].body == MIN_WINDOW
    # overlap: 0 starts right as the speech ends, without the pad
    assert beat_windows([SpokenLine(2.0, 1.7), SpokenLine(1.0, 1.0, overlap=0.0)], 0.4)[0].window == pytest.approx(1.7)


def test_interrupt_without_overlap_cuts_inside_the_last_word() -> None:
    # the last word lasts 1.2-1.7 s: the cut is 0.7 of the way through it, not a fixed lead before the speech end
    said = SpokenLine(2.0, 1.8, last_word=(1.2, 1.7))
    first, _ = beat_windows([said, SpokenLine(1.0, 1.0, interrupt=True)], 0.4)
    assert first.shape.cut == pytest.approx(1.2 + INTERRUPT_WORD_SHARE * 0.5) and first.next_lead == pytest.approx(1.8 - 1.55)
    assert SpokenLine(1.0, 1.0, interrupt=True).lead_after(SpokenLine(2.0, 1.8)) == INTERRUPT_LEAD   # times estimated
    assert SpokenLine(1.0, 1.0, interrupt=True, overlap=0.6).lead_after(said) == 0.6                  # an explicit overlap wins
    assert SpokenLine(1.0, 1.0).lead_after(said) == 0.0


def _aligned_tone(audio_dir: Path, beat_id: str, seconds: float, words: list[tuple[str, float, float]]) -> None:
    """A tone MP3 for ``beat_id`` with stored word times ``(word, start, end)``."""
    from test_scene import make_tone
    from vidgen.speech import write_alignment

    make_tone(audio_dir / f"{beat_id}.mp3", seconds)
    timed: list[tuple[str, float, float]] = []
    for k, (word, start, end) in enumerate(words):
        if k:
            timed.append((" ", start, start))
        step = (end - start) / len(word)
        timed.extend((ch, start + step * i, start + step * (i + 1)) for i, ch in enumerate(word))
    text = " ".join(w for w, _, _ in words)
    alignment = {"characters": [c for c, _, _ in timed], "character_start_times_seconds": [s for _, s, _ in timed],
                 "character_end_times_seconds": [e for _, _, e in timed]}
    write_alignment(audio_dir, beat_id, text, (audio_dir / f"{beat_id}.mp3").read_bytes(), alignment)


def test_planned_interrupt_reads_the_stored_word_times(make_project) -> None:
    beats = [{"text": "one two", "voice": "pip_voice"}, {"text": "three", "voice": "kit_voice", "interrupt": True}]
    project = Project.load(make_project(_video(*beats)))
    _aligned_tone(project.audio_dir, "talk_b1", 1.0, [("one", 0.1, 0.4), ("two", 0.5, 0.9)])
    b1, b2 = VideoPlan(project, 10).scenes[0].beats
    assert b2.start == pytest.approx(0.8) and b1.end == pytest.approx(0.8)   # 0.5 + 0.7 * 0.4 = 0.78, in whole frames: "two" mostly heard


# ----- mix plan ----------------------------------------------------------------------------------


def test_voice_shapes() -> None:
    rate = 1000
    samples = np.ones((3000, 2), dtype=np.float32)
    assert shape_voice(samples, rate, VoiceShape()) is samples   # plain: untouched
    cut = shape_voice(samples, rate, VoiceShape(cut=1.0))
    assert len(cut) == round((1.0 + INTERRUPT_FADE) * rate) and cut.dtype == np.float32
    assert np.all(cut[:1000] == 1.0) and cut[-1, 0] < 0.01 and np.all(np.diff(cut[1000:, 0]) <= 1e-7)   # fades out from the cut
    dipped = shape_voice(samples, rate, VoiceShape(dip_from=1.0))
    assert len(dipped) == 3000 and np.all(dipped[:1000] == 1.0)
    low = 10 ** (-OVERLAP_DIP_DB / 20)
    assert dipped[round((1.0 + DIP_RAMP) * rate) + 1, 0] == pytest.approx(low, abs=1e-6) and dipped[-1, 1] == pytest.approx(low, abs=1e-6)
    gain = VoiceShape(cut=1.0, dip_from=0.5).gain(np.array([0.0, 0.7, 1.2]))
    assert gain[0] == 1.0 and gain[1] == pytest.approx(low) and gain[2] == 0.0


# ----- config ------------------------------------------------------------------------------------


def _video(*beats: dict[str, Any], **extra: Any) -> dict[str, Any]:
    scene = {"id": "talk", "type": "text_card", "params": {"text": "Hi"}, "beats": list(beats)}
    return minimal_config(scenes=[scene], voices=VOICES, narration={"pad": 0.4, "words_per_second": 2.0}, **extra)


def test_validation() -> None:
    ok = VideoConfig.model_validate(_video({"text": "one two", "voice": "pip_voice"}, {"text": "three", "voice": "kit_voice", "overlap": 0.3, "interrupt": True}))
    assert ok.scenes[0].beats[1].overlap == 0.3 and ok.scenes[0].beats[0].overlap is None and not ok.scenes[0].beats[0].interrupt
    for beat, message in [
        ({"text": "one", "overlap": 0.3}, "first beat of scene 'talk' has no beat before it"),
        ({"text": "one", "interrupt": True}, "beats\\[0\\] interrupt"),
    ]:
        with pytest.raises(ValidationError, match=message):
            VideoConfig.model_validate(_video(beat, {"text": "two"}))
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        VideoConfig.model_validate(_video({"text": "one"}, {"text": "two", "overlap": -0.2}))
    with pytest.raises(ValidationError, match="cuts nothing"):
        VideoConfig.model_validate(_video({"text": "one"}, {"text": "two", "overlap": 0, "interrupt": True}))


def test_same_voice_overlap_warns(make_project) -> None:
    project = Project.load(make_project(_video({"text": "one two", "voice": "pip_voice"}, {"text": "three", "voice": "pip_voice", "overlap": 0.3})))
    assert [w for w in validate_warnings(project) if "same voice" in w] == [
        "scene 'talk' beat 'talk_b2': overlap on a line of the same voice 'pip_voice' as the beat before (both lines would sound "
        "at once in one voice); give one of them another voice"
    ]


def test_planned_timeline(make_project) -> None:
    beats = [{"text": "one two three four"}, {"text": "five six", "overlap": 0.6}, {"text": "seven eight", "interrupt": True}]
    project = Project.load(make_project(_video(*beats)))
    (scene,) = VideoPlan(project, 10).scenes
    b1, b2, b3 = scene.beats
    assert (b1.start, b1.end) == (0.0, 2.0)            # heard whole (estimate: no silence)
    assert b2.start == pytest.approx(1.4)              # 0.6 s before the first line ends
    assert b3.start == pytest.approx(1.4 + 1.0 - INTERRUPT_LEAD) and b2.end == pytest.approx(b3.start)   # cut there
    assert scene.duration == pytest.approx(b3.start + 1.0 + 0.4)   # the last pad (no scene types loaded: no fade-out)


# ----- captions ----------------------------------------------------------------------------------


def _cue(start: float, end: float, text: str) -> CaptionCue:
    return CaptionCue(start, end, (text,), ())


def test_caption_stacks() -> None:
    a1, a2, b1, b2 = _cue(0.0, 1.0, "first part"), _cue(1.0, 2.0, "of a line"), _cue(1.5, 2.5, "Another"), _cue(2.5, 3.0, "voice")
    stacks = stack_cues([(0, a1), (0, a2), (1, b1), (1, b2)])
    assert [(s.start, s.end, [c.lines[0] for _, c in s.parts]) for s in stacks] == [
        (0.0, 1.0, ["first part"]),
        (1.0, 1.5, ["of a line"]),
        (1.5, 2.0, ["of a line", "Another"]),   # the earlier line on top
        (2.0, 2.5, ["Another"]),
        (2.5, 3.0, ["voice"]),
    ]
    # without overlaps: one stack per cue, as before
    alone = [(0, a1), (0, a2), (1, _cue(2.4, 3.0, "later"))]
    assert [(s.start, s.end, s.parts) for s in stack_cues(alone)] == [(c.start, c.end, ((k, c),)) for k, c in alone]
    assert overlapping_beats([(0.0, 2.0), (1.5, 3.0), (3.4, 4.0)]) == {0, 1}
    assert overlapping_beats([(0.0, 2.0), (2.4, 3.0)]) == set()


def test_srt_shows_both_lines(tmp_path: Path) -> None:
    long_line = "This is a fairly long line that goes on for a while so it needs two lines"
    timings = {"scenes": [{"beats": [
        {"id": "a", "start": 0.0, "end": 4.0, "text": long_line},
        {"id": "b", "start": 3.0, "end": 4.5, "text": "Wait, listen to me!"},
        {"id": "c", "start": 5.0, "end": 6.0, "text": "Fine."},
    ]}]}
    cues = cues_from_timings(timings)
    assert all("\n" not in cue.text for cue in cues)   # one line each where lines overlap
    assert [c.start for c in cues] == sorted(c.start for c in cues)
    under = [c for c in cues if c.start < 3.0 < c.end or c.start == 3.0]
    assert {c.text for c in under} >= {"Wait, listen to me!"} and len(under) == 2   # both lines shown at 3 s
    assert cues[-1].text == "Fine." and cues[-1].end == 6.0
    plain = cues_from_timings({"scenes": [{"beats": [timings["scenes"][0]["beats"][0]]}]})
    assert any("\n" in c.text for c in plain)   # alone it keeps two lines


def test_captions_overlay_stacks_both_lines(make_project) -> None:
    beats = [{"text": "You never listen to what I say about the garden", "voice": "pip_voice"},
             {"text": "I do listen!", "voice": "kit_voice", "overlap": 0.8}]
    scene = {"id": "talk", "type": "text_card", "params": {"text": "Hi"}, "beats": beats}
    project = Project.load(make_project(minimal_config(
        scenes=[scene], voices=VOICES, narration={"pad": 0.2, "words_per_second": 4.0},
        overlays=[{"type": "captions", "style": "karaoke", "speakers": "color"}],
    )))
    (cap,) = built(project, "talk")
    plan = VideoPlan(project, 10).scene("talk")
    first, second = plan.beats
    t = cap.at + (second.start + first.end) / 2   # type: ignore[attr-defined]
    k, words = cap.state(t)   # type: ignore[misc]
    assert len(words) == 2 and len(cap._cues[k].parts) == 2   # both lines
    mob = cap.built.submobjects[1 + k]   # type: ignore[attr-defined]
    plate, upper, lower = mob.submobjects
    glyph_colors = [{g.get_fill_color().to_hex() for g in line.submobjects if len(g.points)} for line in (upper, lower)]
    assert upper.get_center()[1] > lower.get_center()[1] and glyph_colors[0] != glyph_colors[1], glyph_colors   # each in its colour
    assert len(cap._cues[cap.state(cap.at + first.end + 0.05)[0]].parts) == 1   # type: ignore[attr-defined, index]
    posed = cap.pose(cap.built, (k, (0, 0)))   # type: ignore[attr-defined]
    assert posed is not mob   # a word of each line highlighted


# ----- lint ----------------------------------------------------------------------------------------


def _activity(beats: list[dict[str, Any]]) -> dict[str, Any]:
    return {"fps": 10, "pad": 0.4, "beats": beats, "plays": []}


def test_talked_over_rule(tmp_path: Path) -> None:
    first = {"id": "a", "start": 0.0, "end": 3.0, "busy": 1.0, "source": "estimate", "text": "one two three four five six", "window": 1.5}
    second = {"id": "b", "start": 1.5, "end": 2.5, "busy": 1.0, "source": "estimate", "text": "stop it", "overlap": 1.5}
    ctx = SceneContext("talk", _activity([first, second]), tmp_path)
    (issue,) = timing_rules.talked_over(ctx, LintConfig().rules.talked_over)
    assert issue.beat == "a" and issue.value == 3 and '"four five six"' in issue.message and "shorten the overlap" in issue.message
    second_short = {**second, "start": 2.6, "overlap": 0.4}
    assert list(timing_rules.talked_over(SceneContext("talk", _activity([{**first, "window": 2.6}, second_short]), tmp_path), LintConfig().rules.talked_over)) == []
    cut = {**second, "interrupt": True}
    assert list(timing_rules.talked_over(SceneContext("talk", _activity([first, cut]), tmp_path), LintConfig().rules.talked_over)) == []   # no audio: nothing to cut
    assert [w.text for w in talked_over([WordTime("a", 0.0, 0.4), WordTime("b", 0.5, 0.9), WordTime("c", 1.0, 1.4)], 0.45, 1.4)] == ["b", "c"]


def test_talked_over_reports_words_an_interrupt_cuts(tmp_path: Path) -> None:
    _aligned_tone(tmp_path, "a", 1.0, [("one", 0.1, 0.4), ("two", 0.5, 0.9)])
    line = {"id": "a", "start": 0.0, "busy": 0.1, "source": "audio", "text": "one two"}
    stop = {"id": "b", "start": 0.45, "end": 1.0, "busy": 0.1, "source": "estimate", "text": "stop", "overlap": 0.55, "interrupt": True}
    (issue,) = timing_rules.talked_over(SceneContext("talk", _activity([{**line, "end": 0.45, "window": 0.45}, stop]), tmp_path), LintConfig().rules.talked_over)
    assert issue.beat == "a" and issue.value == 1 and '"two"' in issue.message and "overlap below 0.50 s" in issue.message
    inside = {**stop, "start": 0.8, "overlap": 0.2}   # cut inside "two": its start is heard
    assert list(timing_rules.talked_over(SceneContext("talk", _activity([{**line, "end": 0.8, "window": 0.8}, inside]), tmp_path), LintConfig().rules.talked_over)) == []


def test_overrun_measures_the_window(tmp_path: Path) -> None:
    beat = {"id": "a", "start": 0.0, "end": 3.0, "busy": 2.0, "source": "estimate", "text": "x", "window": 1.5}
    (issue,) = timing_rules.animation_overrun(SceneContext("talk", _activity([beat]), tmp_path), LintConfig().rules.animation_overrun)
    assert "starts 0.5 s late" in issue.message
    assert list(timing_rules.animation_overrun(SceneContext("talk", _activity([{**beat, "window": 2.0}]), tmp_path), LintConfig().rules.animation_overrun)) == []


# ----- lip sync and directing ----------------------------------------------------------------------


def test_viseme_track_cut() -> None:
    track = VisemeTrack((VisemeCue(0.0, 0.3, "A"), VisemeCue(0.3, 0.6, "M"), VisemeCue(0.6, 1.0, "O")))
    cut = track.until(0.45)
    assert cut.duration == 0.45 and cut.at(0.4) == "M" and cut.at(0.5) == "rest" and track.at(0.7) == "O"


def _stage(beats: list[dict[str, Any]], **params: Any) -> dict[str, Any]:
    stage = {"background": "#88AACC", "idle": False, "characters": [{"name": "pip", "at": "left"}, {"name": "kit", "at": "right"}], **params}
    return {"id": "yard", "type": "stage", "params": stage, "beats": beats}


def test_no_reaction_in_a_pause_that_an_overlap_removes(make_project, tmp_path: Path) -> None:
    def reactions(second: dict[str, Any], folder: str) -> list[str]:
        beats = [{"text": "Is the box really empty?", "voice": "pip_voice"}, second]
        project = Project.load(make_project(minimal_config(scenes=[_stage(beats)], characters=CAST, voices=VOICES, auto_direct={"looks": False, "reactions": True, "gestures": False, "closeups": False, "effects": False}), folder=folder))
        with extensions.project_session(project):
            directed = project_directions(project).get("yard", [])
        return [f"{d.beat}:{a.action}" for d in directed for a in d.actions]

    assert reactions({"text": "It is.", "voice": "kit_voice"}, "a") == ["yard_b1:react"]   # kit reacts in the pause
    assert reactions({"text": "It is.", "voice": "kit_voice", "overlap": 0.3}, "b") == []   # no pause: kit already speaks


# ----- render ------------------------------------------------------------------------------------


@pytest.mark.render
def test_both_mouths_move_while_lines_overlap(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    beats = [
        {"text": "One two three four five six seven eight.", "voice": "pip_voice"},
        {"text": "Nine ten eleven twelve.", "voice": "kit_voice", "overlap": 1.0},
        {"text": "Stop right there.", "voice": "pip_voice", "interrupt": True, "overlap": 0.3},
    ]
    project = Project.load(make_project(minimal_config(scenes=[_stage(beats)], characters=CAST, voices=VOICES, narration={"pad": 0.4, "words_per_second": 4.0})))
    extensions.load_builtins()
    cls = registry.get("stage").cls
    monkeypatch.setattr(cls, "outro", 0)
    seen: list[tuple[float, bool, bool]] = []
    setup = cls.setup

    def recording(self: Any) -> None:
        setup(self)
        self.add_updater(lambda dt: seen.append((float(self.renderer.time), self.cast["pip"].lip_sync_track is not None,
                                                 self.cast["kit"].lip_sync_track is not None)) if hasattr(self, "cast") else None)

    monkeypatch.setattr(cls, "setup", recording)
    scene, _ = render_with_layout(project, "yard", tmp_path / "media")
    b1, b2, b3 = scene.beat_log
    assert b1.end == pytest.approx(2.0) and b2.start == pytest.approx(1.0) and b2.start < b1.end   # 1.0 s overlap
    assert b3.start == pytest.approx(1.8) and b2.end == pytest.approx(b3.start)   # kit cut by pip (0.7 s: 4 frames at 5 fps)
    assert b3.end == pytest.approx(b3.start + 0.75)
    during = [(pip, kit) for t, pip, kit in seen if b2.start + 0.1 < t < b3.start - 0.1]
    assert during and all(pip and kit for pip, kit in during)   # both mouths follow their tracks
    after_cut = [kit for t, _, kit in seen if b3.start + 0.1 < t]
    assert after_cut and not any(after_cut)   # kit's mouth stopped at the interruption
    timings = scene.timings()["beats"]
    assert [round(b["end"], 3) for b in timings] == [round(b1.end, 3), round(b2.end, 3), round(b3.end, 3)]


# ----- wind (Step 99's finding) --------------------------------------------------------------------


def test_wind_updater_removes_itself_once_calm() -> None:
    """The wind's scene updater removes itself on the frame nothing can move any more, like the
    light's (it was only removed when the next animation started, so a long wait kept it)."""
    extensions.load_builtins()
    stage = registry.get("stage").cls
    moving = {"now": True}
    blowing = SimpleNamespace(update=lambda t: None, moving=lambda a, b: moving["now"])
    scene = SimpleNamespace(blowing=blowing, renderer=SimpleNamespace(time=3.0), updaters=[])
    scene.remove_updater = lambda f: setattr(scene, "updaters", [u for u in scene.updaters if u is not f])
    scene._wind_updater = lambda dt: stage._wind_step(scene, dt)
    scene.updaters.append(scene._wind_updater)
    scene._wind_updater(0.2)
    assert scene._wind_updater in scene.updaters   # still blowing
    moving["now"] = False
    scene._wind_updater(0.2)
    assert scene.updaters == []   # calm and the spring at rest: gone, without waiting for an animation


@pytest.mark.render
def test_interrupted_voice_is_cut_in_the_scene_sound(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import wave

    from manim import tempconfig

    from test_scene import make_tone
    from vidgen.speech import speech_bounds

    project = Project.load(make_project(_video({"text": "one two", "voice": "pip_voice"}, {"text": "three", "voice": "kit_voice", "interrupt": True, "overlap": 0.4})))
    first = make_tone(project.audio_dir / "talk_b1.mp3", 1.0)
    make_tone(project.audio_dir / "talk_b2.mp3", 0.6)
    extensions.load_builtins()
    cls = registry.get("text_card").cls
    lengths: list[tuple[float, int]] = []
    add_sound = cls.add_sound

    def recording(self: Any, path: str, time_offset: float = 0, gain: Any = None, **kwargs: Any) -> None:
        with wave.open(path, "rb") as wav:
            lengths.append((float(self.renderer.time), wav.getnframes()))
        add_sound(self, path, time_offset, gain, **kwargs)

    monkeypatch.setattr(cls, "add_sound", recording)
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": 5, "media_dir": str(tmp_path / "media"),
                     "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}):
        with extensions.project_session(project):
            scene = cls(project.scene("talk"), project)
            scene.render()
    cut = round((speech_bounds(first)[1] - 0.4) * 5) / 5
    (t1, n1), (t2, n2) = lengths
    assert t1 == 0.0 and n1 == int(np.ceil((cut + INTERRUPT_FADE) * 48000))   # cut, with its fade
    assert t2 == pytest.approx(cut) and n2 > 0.55 * 48000                       # the interrupting line whole
    b1, b2 = scene.beat_log
    assert b1.end == pytest.approx(cut) and b2.start == pytest.approx(cut)
