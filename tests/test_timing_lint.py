"""`vidgen lint` timing rules (Step 14): spoken words, speech bounds, the motion signal, each
rule on synthetic activity files, the runner (grouping, ignores, stills), and a render test."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from conftest import minimal_config
from test_json_output import run_json
from test_lint import fake_render
from test_render import write_project
from vidgen.activity import MotionTrack
from vidgen.config import LintRules
from vidgen.lint import RULES, SceneContext, lint_project
from vidgen.lint.timing_rules import speech_bounds, spoken_words, static_runs
from vidgen.project import Project
from vidgen.render.worker import scene_activity_path, scene_frames_dir

# ----- helpers -----------------------------------------------------------------------------------


def beat(bid: str, start: float, end: float, *, busy: float | None = None, text: str = "one two three four five six",
         source: str = "estimate") -> dict[str, Any]:
    return {"id": bid, "start": start, "end": end, "busy": end - start if busy is None else busy, "source": source,
            "text": text}


def activity(beats: list[dict[str, Any]], *, fps: int = 10, frames: int = 100, changes: list[list[float]] | None = None,
             plays: list[dict[str, Any]] | None = None, silent: dict[str, float] | None = None, pad: float = 0.3) -> dict[str, Any]:
    return {"version": 1, "scene": "s", "type": "t", "fps": fps, "frames": frames, "duration": frames / fps, "pad": pad,
            "silent": silent, "beats": beats, "plays": plays or [],
            "motion": {"step": 1, "grid": [96, 54], "level": 6, "changes": changes if changes is not None else [[0, 1.0]]}}


def play(start: float, end: float, beat_id: str | None, *names: str, wait: bool = False,
         requested: float | None = None) -> dict[str, Any]:
    return {"start": start, "end": end, "beat": beat_id, "animations": list(names), "wait": wait, "requested": requested}


def run(name: str, doc: dict[str, Any], audio_dir: Path = Path("."), **settings: Any) -> list[Any]:
    model = type(getattr(LintRules(), name))
    return list(RULES[name].check(SceneContext("s", doc, audio_dir), model(**settings)))


def tone_wav(path: Path, lead: float, speech: float, trail: float, rate: int = 16000) -> Path:
    """Silence, a 440 Hz tone, silence (mono 16-bit WAV)."""
    t = np.arange(int(speech * rate)) / rate
    samples = np.concatenate([np.zeros(int(lead * rate)), 0.5 * np.sin(2 * np.pi * 440 * t), np.zeros(int(trail * rate))])
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((samples * 32767).astype(np.int16).tobytes())
    return path


# ----- words, audio, motion ----------------------------------------------------------------------


def test_spoken_words_counts_numbers_acronyms_and_hyphens() -> None:
    assert spoken_words("Hello, world!") == 2
    assert spoken_words("K-Phi-3 is one-by-one") == 3 + 1 + 3
    assert spoken_words("227 million") == 3 + 1
    assert spoken_words("2.58 million") == 4 + 1  # two point five eight
    assert spoken_words("15% of 2024") == 3 + 1 + 3
    assert spoken_words("a GPU and an NVIDIA L4") == 1 + 1.5 + 1 + 1 + 1 + 2
    assert spoken_words("in 3 days — or less / more") == 2 + 1 + 3
    assert spoken_words("1,000,000") == 1 + 3 + 3 + 2


def test_speech_bounds_cut_leading_and_trailing_silence(tmp_path: Path) -> None:
    start, end = speech_bounds(tone_wav(tmp_path / "a.wav", 0.4, 1.5, 0.7))
    assert start == pytest.approx(0.4, abs=0.02) and end == pytest.approx(1.9, abs=0.02)


def test_motion_track_records_changed_frames_only() -> None:
    track = MotionTrack(samples=10, level=6)
    black = np.zeros((20, 40, 4), np.uint8)
    corner = black.copy()
    corner[:10, :10, :3] = 255
    track.observe(black, 0, 1)
    track.observe(black.copy(), 1, 1)
    track.observe(corner, 2, 5)  # a frozen wait: one frame written 5 times
    nudged = corner.copy()
    nudged[..., :3] = np.where(corner[..., :3] > 0, 252, 3)
    track.observe(nudged, 7, 1)  # every channel moved by 3, below the level: not a change
    assert track.step == 2 and track.grid == (20, 10) and track.frames == 8
    assert track.changes == [(0, 1.0), (2, 0.125)]
    assert track.to_json()["changes"] == [[0, 1.0], [2, 0.125]]


# ----- rules -------------------------------------------------------------------------------------


def test_static_runs_and_dead_air() -> None:
    doc = activity([beat("b1", 0, 4), beat("b2", 4.3, 9.0)], changes=[[0, 1.0], [5, 0.01], [12, 0.00005], [80, 0.2]])
    assert static_runs(doc, 0.0002) == [(0, 5), (5, 80), (80, 100)]
    [issue] = run("dead_air", doc)
    assert issue.beat == "b1" and issue.time == 0.5 and issue.value == 7.5 and issue.limit == 6.0
    assert "7.5 s (0.5-8.0 s) during beats b1, b2" in issue.message
    assert not run("dead_air", doc, max_seconds=8)
    assert len(run("dead_air", doc, min_change=0.00001, max_seconds=6)) == 1  # 12 splits it: 0.7 s + 6.8 s
    silent = activity([], frames=90, silent={"duration": 9.0, "busy": 9.0})
    [issue] = run("dead_air", silent)
    assert issue.beat is None and "(silent scene)" in issue.message and issue.value == 9.0


def test_animation_overrun() -> None:
    plays = [play(0, 1, "b1", "Write"), play(1, 4.5, "b1", "Transform"), play(4.5, 5.0, "b1", "Wait", wait=True)]
    doc = activity([beat("b1", 0, 3.0, busy=5.0), beat("b2", 5.0, 7.0, busy=1.0)], plays=plays)
    [issue] = run("animation_overrun", doc)
    assert issue.beat == "b1" and issue.time == 3.0 and issue.value == pytest.approx(1.7) and issue.limit == 0.1
    assert "take 5.0 s but its narration lasts 3.0 s (+0.3 s pad): 1.7 s of silence" in issue.message
    assert issue.message.endswith("Transform (1.0-4.5 s)")  # the Write ended before the narration did
    assert not run("animation_overrun", doc, tolerance=2.0)
    silent = activity([], silent={"duration": 4.0, "busy": 5.5}, plays=[play(0, 5.5, None, "FadeIn")])
    [issue] = run("animation_overrun", silent)
    assert issue.beat is None and "longer than its duration 4 s: FadeIn (0.0-5.5 s)" in issue.message


def test_rushed_animation() -> None:
    plays = [play(0, 0.2, "b1", "FadeIn", requested=1.2), play(0.4, 0.6, "b1", "Write", requested=1.2),
             play(1.0, 1.9, "b2", "FadeIn", requested=1.2), play(2, 2.1, "b2", "Indicate")]
    doc = activity([beat("b1", 0, 0.8), beat("b2", 1.0, 3.0)], plays=plays)
    [issue] = run("rushed_animation", doc)
    assert issue.beat == "b1" and issue.time == 0 and issue.value == 0.2
    assert issue.message.startswith("2 steps play in 0.20 s instead of 1.2 s (FadeIn, Write): the beat (0.8 s")
    assert len(run("rushed_animation", doc, min_run_time=1.0)) == 2  # b2's shortened FadeIn too, never the Indicate


def test_narration_speed_from_audio_and_estimates(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is needed by vidgen"
    wav = tone_wav(tmp_path / "fast.wav", 0.3, 2.0, 0.8)
    subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", str(wav), str(tmp_path / "fast.mp3")], check=True, capture_output=True)
    text = "one two three four five six seven eight nine ten"
    doc = activity([
        beat("fast", 0, 3.1, text=text, source="audio"),            # 10 words in 2 s of speech
        beat("ok", 3.5, 7.5, text=text),                            # estimate: 2.5 words/s
        beat("nums", 8, 9, text="In 2024, 37.5% of 128 GPUs"),     # estimate, 14.5 spoken words in 1 s
        beat("nums2", 9.5, 10.5, text="Then 1.5 and 2.25 and 3.75"),
        beat("short", 11, 11.2, text="Hi there"),                  # below min_words
    ])
    issues = run("narration_speed", doc, tmp_path)
    assert [(i.beat, i.severity, i.group) for i in issues] == [
        ("fast", None, None), ("nums", "info", ("estimate", True)), ("nums2", "info", ("estimate", True))]
    fast = issues[0]
    assert fast.value == pytest.approx(5.0, rel=0.06) and fast.limit == 3.5 and fast.time == 0  # MP3 adds ~50 ms
    assert "(10 spoken words in 2." in fast.message and "s of speech) is above 3.5: too fast" in fast.message
    assert "no audio yet" in issues[1].message
    slow = run("narration_speed", doc, tmp_path, min_rate=2.8, max_rate=20)
    assert [i.beat for i in slow] == ["ok"] and "below 2.8" in slow[0].message


# ----- runner ------------------------------------------------------------------------------------


def test_runner_reports_timing_findings(make_project) -> None:
    data = minimal_config(preview={"width": 854, "height": 480, "fps": 15})
    data["scenes"][0]["beats"] = [{"text": "In 2024, 37.5% of 128 GPUs"}, {"text": "Then 1.5 and 2.25 and 3.75 and 4.5"}]
    root = make_project(data)
    project = Project.load(root)
    fake_render(project, "intro", [[], []], activity={
        "beats": [beat("intro_b1", 0, 1, text=data["scenes"][0]["beats"][0]["text"]),
                  beat("intro_b2", 1.3, 2.3, text=data["scenes"][0]["beats"][1]["text"], busy=2.5)],
        "plays": [play(1.3, 3.8, "intro_b2", "Write")], "frames": 120,
        "motion": {"changes": [[0, 1.0], [10, 0.5]]}})
    fake_render(project, "main", [[]])
    result = lint_project(project, rules=["narration_speed", "dead_air", "animation_overrun"])
    summary = [(f.scene, f.rule, f.severity, f.beat, f.beats, f.scene_time) for f in result.findings]
    assert summary == [
        ("intro", "narration_speed", "info", "intro_b1", ["intro_b1", "intro_b2"], 0.0),  # grouped: one finding
        ("intro", "dead_air", "warning", "intro_b1", ["intro_b1"], 1.0),
        ("intro", "animation_overrun", "warning", "intro_b2", ["intro_b2"], 2.3),
    ]
    overrun = result.findings[2]
    assert overrun.still == scene_frames_dir(project, True, "intro") / "intro_b2-1.png" and overrun.bbox is None
    assert overrun.time == pytest.approx(2.3) and overrun.objects == ()
    as_json = overrun.to_json()
    assert as_json["object"] is None and as_json["bbox"] is None and Path(as_json["still"]).is_file()

    data["scenes"][0]["lint_ignore"] = ["dead_air", {"rule": "animation_overrun", "beat": "intro_b2"}]
    data["lint"] = {"rules": {"narration_speed": {"severity": "warning"}}}
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    result = lint_project(Project.load(root), rules=["narration_speed", "dead_air", "animation_overrun"])
    assert [(f.rule, f.severity) for f in result.findings] == [("narration_speed", "warning")] and result.ignored == 2


def test_missing_activity_means_stale(make_project) -> None:
    from vidgen.storyboard import stills_current

    root = make_project(minimal_config(preview={"width": 854, "height": 480, "fps": 15}))
    project = Project.load(root)
    fake_render(project, "intro", [[], []])
    assert stills_current(project, True, "intro", None)
    scene_activity_path(project, True, "intro").unlink()  # a render from before Step 14
    assert not stills_current(project, True, "intro", None)


# ----- rendering ---------------------------------------------------------------------------------

EXTENSION = '''
from vidgen.api import *

@scene("slowpoke")
class Slowpoke(NarratedScene):
    def construct(self):
        dots = [Dot(LEFT * 3 + RIGHT * i) for i in range(6)]
        with self.narrate(0) as d:
            self.play(FadeIn(dots[0]), run_time=d + 2.0)        # runs 2 s past the narration
        with self.narrate(1) as d:
            self.play_steps(d, [FadeIn(x) for x in dots[1:]])  # 5 steps in a short beat
        with self.narrate(2) as d:
            self.play(dots[0].animate.shift(UP), run_time=0.5)  # then nothing moves


@scene("still_card")
class StillCard(NarratedScene):
    def construct(self):
        self.add(Square())
        self.play(Rotate(self.mobjects[0], 0.5), run_time=1)
'''


@pytest.mark.render
@pytest.mark.slow
def test_timing_lint_on_a_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    long_text = " ".join(["word"] * 24)  # 8 s at 3 words/s
    root = write_project(
        tmp_path / "proj",
        {"scenes": [
            {"id": "slow", "type": "slowpoke", "beats": [{"text": "One two three."}, {"text": "Four five six."}, {"text": long_text}]},
            {"id": "card", "type": "still_card", "duration": 9},
        ]},
        {"extensions/slow.py": EXTENSION},
    )
    timing = ["--rule", "dead_air", "--rule", "animation_overrun", "--rule", "rushed_animation", "--rule", "narration_speed"]
    code, doc, _ = run_json(["lint", str(root), "--json", *timing], capsys)
    assert code == 0 and doc["rendered"] == ["slow", "card"]
    found = [(f["scene"], f["rule"], f["beat"]) for f in doc["findings"]]
    assert found == [
        ("slow", "animation_overrun", "slow_b1"),
        ("slow", "rushed_animation", "slow_b2"),
        ("slow", "dead_air", "slow_b3"),
        ("card", "dead_air", None),
    ]
    overrun, rushed, dead, card = doc["findings"]
    assert overrun["value"] == pytest.approx(2.0 - 0.3, abs=0.21) and "FadeIn (0.0-3.0 s)" in overrun["message"]
    assert rushed["value"] < 0.5 and "5 steps" in rushed["message"]
    assert dead["value"] > 7 and card["value"] == pytest.approx(8.0, abs=0.21)

    project = Project.load(root)
    data = json.loads(scene_activity_path(project, True, "slow").read_text(encoding="utf-8"))
    assert [b["id"] for b in data["beats"]] == ["slow_b1", "slow_b2", "slow_b3"]
    assert data["beats"][0]["busy"] == pytest.approx(3.0, abs=0.01) and data["beats"][0]["source"] == "estimate"
    first = data["plays"][0]
    assert (first["beat"], first["animations"], first["wait"]) == ("slow_b1", ["FadeIn"], False)
    assert any(p["animations"] == ["animate"] for p in data["plays"])
    assert any(p["wait"] for p in data["plays"]) and data["frames"] == round(data["duration"] * 5)
    assert data["motion"]["changes"][0] == [0, 1.0]
