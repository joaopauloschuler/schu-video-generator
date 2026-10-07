"""Transitions between scenes (Step 46, DESIGN.md §49): config, the planned timeline with
overlaps and holds, the voice track, the join's crossfades, in-render colour fades, and a
rendered video whose every time (SRT, captions, overlays, effects, narration) follows the plan."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest
import yaml

from vidgen import extensions, registry
from vidgen.cli import main, project_problems, validate_warnings
from vidgen.config import TransitionConfig, parse_config
from vidgen.errors import VidgenError
from vidgen.lint.timing_rules import static_runs
from vidgen.project import Project
from vidgen.render.ffmpeg import crossfade_graph
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.sfx import RATE, read_wav, write_wav
from vidgen.speech import speech_bounds
from vidgen.transitions import ColorFade, effective, join_overlaps, requested_frames, silent_tail, write_voice_track
from vidgen.videoplan import VideoPlan, video_chapters

ROOT = Path(__file__).resolve().parents[1]
KPHI3_AUDIO = ROOT / "examples" / "kphi3" / "audio"
FPS = 10


def _config(**extra: Any) -> dict[str, Any]:
    scenes = extra.pop("scenes", None) or [
        {"id": "a", "type": "title", "params": {"title": "A"}, "beats": [{"text": "one two three four five six"}]},
        {"id": "b", "type": "title", "params": {"title": "B"}, "beats": [{"text": "seven eight nine ten"}]},
        {"id": "card", "type": "chapter", "params": {"number": 1, "title": "Card"}, "duration": 2},
        {"id": "c", "type": "title", "params": {"title": "C"}, "beats": [{"text": "eleven twelve"}]},
    ]
    return {"title": "T", "format": {"width": 160, "height": 90, "fps": FPS}, **extra, "scenes": scenes}


def _project(make_project: Any, **extra: Any) -> Project:
    return Project.load(make_project(_config(**extra)))


# ----- config ------------------------------------------------------------------------------------------


def test_transition_forms_and_defaults() -> None:
    cfg = parse_config(_config(transition="crossfade"))
    assert cfg.transition == TransitionConfig(type="crossfade") and cfg.transition.seconds == 0.5
    assert TransitionConfig(type="fade_color").seconds == 1.0 and TransitionConfig().seconds == 0.0
    scenes = _config()["scenes"]
    scenes[2]["transition"] = {"type": "fade_color", "duration": 0.8, "color": "accent"}
    scenes[3]["transition"] = "cut"
    cfg = parse_config(_config(transition={"type": "crossfade", "duration": 0.7}, scenes=scenes))
    assert [effective(cfg, i).type for i in range(4)] == ["cut", "crossfade", "fade_color", "cut"]
    assert effective(cfg, 1).seconds == 0.7 and effective(cfg, 2).color == "accent"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"type": "cut", "duration": 1}, "a cut has no duration"),
        ({"type": "crossfade", "color": "accent"}, "color is only for fade_color"),
        ({"type": "crossfade", "duration": 6}, "less than or equal to 5"),
        ("dissolve", "transition"),
    ],
)
def test_transition_errors(value: Any, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        parse_config(_config(transition=value))


def test_first_scene_cannot_crossfade_but_can_fade_in() -> None:
    scenes = _config()["scenes"]
    scenes[0]["transition"] = "crossfade"
    with pytest.raises(VidgenError, match="first scene has no scene before it"):
        parse_config(_config(scenes=scenes))
    scenes[0]["transition"] = "fade_color"
    assert effective(parse_config(_config(transition="crossfade", scenes=scenes)), 0).type == "fade_color"
    # the video's default never applies to the first scene
    assert effective(parse_config(_config(transition="crossfade")), 0).type == "cut"


def test_validate_checks_colours_and_warns_about_holds(make_project: Any) -> None:
    scenes = _config()["scenes"]
    scenes[2]["transition"] = {"type": "fade_color", "color": "nope"}
    scenes[1]["transition"] = {"type": "crossfade", "duration": 2.0}
    project = Project.load(make_project(_config(scenes=scenes)))
    problems = [str(p) for p in project_problems(project)]
    assert any(p.startswith("scenes[2].transition.color: unknown theme color 'nope'") for p in problems)
    first, second = [w for w in validate_warnings(project) if "transition" in w]
    assert "scenes[1].transition: the crossfade into 'b' (2 s)" in first and "'a' is held 1.20 s longer" in first
    # b's own start is taken by that crossfade, so its silent end is short for the fade too
    assert second.startswith("scenes[2].transition: the fade_color into 'card'") and "'b' is held 0.10 s longer" in second


# ----- the plan ----------------------------------------------------------------------------------------


def test_plan_overlaps_crossfades_and_keeps_fades(make_project: Any) -> None:
    scenes = _config()["scenes"]
    scenes[2]["transition"] = "fade_color"
    project = _project(make_project, transition="crossfade", scenes=scenes)
    with extensions.project_session(project):
        plain = VideoPlan(Project.load(make_project(_config(), folder="plain")), FPS)
        plan = VideoPlan(project, FPS)
        slots = plan.scenes
        # every scene keeps its own length; a crossfade starts a scene 5 frames (0.5 s) early
        assert [s.duration for s in slots] == [s.duration for s in plain.scenes]
        assert [plan.transition(i).overlap for i in range(4)] == [0, 5, 0, 5]
        assert [(plan.transition(i).fade_out, plan.transition(i).fade_in) for i in range(4)] == [(0, 0), (0, 0), (5, 5), (0, 0)]
        assert slots[1].start == pytest.approx(slots[0].end - 0.5) and slots[2].start == pytest.approx(slots[1].end)
        assert slots[3].start == pytest.approx(slots[2].end - 0.5)
        assert plan.duration == pytest.approx(plain.duration - 1.0)
        assert slots[0].cut == pytest.approx(slots[1].start) and slots[1].cut == pytest.approx(slots[1].end)
        assert (slots[1].overlap_in, slots[1].overlap_out, slots[0].overlap_out) == (0.5, 0.0, 0.5)
        # chapters and from / to follow the overlapped starts
        [chapter] = plan.chapters
        assert chapter.start == pytest.approx(slots[2].start) and chapter.end == pytest.approx(plan.duration)
        assert plan.resolve("a", end=True) == pytest.approx(slots[1].start)
    assert video_chapters(project, FPS)[0].start == pytest.approx(slots[2].start)


def test_plan_holds_a_scene_whose_silence_is_too_short(make_project: Any) -> None:
    scenes = _config()["scenes"]
    scenes[1]["transition"] = {"type": "crossfade", "duration": 1.5}
    scenes[3]["transition"] = {"type": "fade_color", "duration": 3.6}
    project = _project(make_project, scenes=scenes)
    with extensions.project_session(project):
        plan = VideoPlan(project, FPS)
        # a: 6 words / 2.6 = 2.31 s of speech, + pad 0.35 -> 27 frames, + outro 0.5 -> 32 frames:
        # 8 silent frames after the speech; the crossfade needs 15 -> held 7 frames
        into_b = plan.transition(1)
        assert (into_b.overlap, into_b.hold) == (15, 7)
        assert plan.scene_duration(0) == pytest.approx(3.9)
        assert plan.scene("b").start == pytest.approx(3.9 - 1.5)
        # the silent card (20 frames, a cut into it) fades out over 18 frames: no hold; c fades
        # in over at most its own 16 frames
        into_c = plan.transition(3)
        assert (into_c.fade_out, into_c.fade_in, into_c.hold) == (18, 16, 0)


def test_silent_tail_and_join_overlaps_match_the_plan(make_project: Any) -> None:
    assert silent_tail(30, 2.0, 0, 10) == 10 and silent_tail(30, None, 4, 10) == 26 and silent_tail(30, 3.5, 0, 10) == 0
    assert requested_frames(TransitionConfig(type="fade_color", duration=1.0), 30) == 15
    project = _project(make_project, transition={"type": "crossfade", "duration": 1.2})
    with extensions.project_session(project):
        plan = VideoPlan(project, FPS)
        frames = [round(plan.scene_duration(i) * FPS) for i in range(4)]
        ends = [plan.scene(s.id).beats[-1].end if s.beats else None for s in project.config.scenes]
        assert join_overlaps(project.config, FPS, frames, ends) == [plan.transition(i).overlap for i in range(4)]
        # a render that ends with less silence than planned gets a shorter crossfade
        short = join_overlaps(project.config, FPS, [frames[0] - 10, *frames[1:]], ends)
        assert short[1] < plan.transition(1).overlap


def test_estimated_duration_subtracts_crossfades(make_project: Any) -> None:
    plain = _project(make_project).estimated_duration()
    faded = Project.load(make_project(_config(transition="crossfade"), folder="x")).estimated_duration()
    assert faded == pytest.approx(plain - 1.5)


def test_fingerprint_follows_the_next_transition(make_project: Any) -> None:
    root = make_project(_config())
    before = {sid: scene_fingerprint(Project.load(root), sid) for sid in ("a", "b", "card")}
    data = _config()
    data["scenes"][1]["transition"] = "crossfade"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    project = Project.load(root)
    assert scene_fingerprint(project, "a") != before["a"]  # it now ends held, not faded
    assert scene_fingerprint(project, "b") != before["b"]
    assert scene_fingerprint(project, "card") == before["card"]


# ----- pieces of the join and the render ---------------------------------------------------------------------


def test_voice_track_overlaps_and_fades_the_tail(tmp_path: Path) -> None:
    a = np.full((1000, 2), 0.25, dtype=np.float32)
    b = np.zeros((600, 2), dtype=np.float32)
    b[:, 0] = 0.5
    write_wav(tmp_path / "a.wav", a)
    write_wav(tmp_path / "b.wav", b)
    n = write_voice_track([tmp_path / "a.wav", tmp_path / "b.wav"], [0, 200], tmp_path / "v.wav", RATE)
    out = read_wav(tmp_path / "v.wav")
    assert n == len(out) == 1400
    assert np.allclose(out[:800], 0.25, atol=1e-4) and np.allclose(out[1000:, 0], 0.5, atol=1e-4)
    tail = out[800:1000, 1]  # a's tail fades out (raised cosine) under b's start
    assert tail[0] == pytest.approx(0.25, abs=0.01) and tail[-1] == pytest.approx(0.0, abs=0.01) and np.all(np.diff(tail) <= 1e-4)
    assert np.allclose(out[800:1000, 0] - tail, 0.5, atol=1e-3)


def test_crossfade_graph_offsets() -> None:
    graph, label = crossfade_graph([20, 15, 12], [5, 3], 10)
    assert label == "x2" and graph[0] == "[0:v]settb=AVTB,setpts=PTS-STARTPTS[r0]"
    assert graph[3] == "[r0][r1]xfade=transition=fade:duration=0.500000:offset=1.450000[x1]"
    assert graph[4] == "[x1][r2]xfade=transition=fade:duration=0.300000:offset=2.650000[x2]"  # 30 frames before it


def test_color_fade_weights() -> None:
    fade = ColorFade("#FF0000", 4, "#0000FF", 5, 20)
    weights = [fade.weight(k) for k in range(20)]
    assert [round(w, 2) for w, _ in weights[:5]] == [1.0, 0.75, 0.5, 0.25, 0.0]
    assert [round(w, 2) for w, _ in weights[15:]] == [0.2, 0.4, 0.6, 0.8, 1.0]
    frame = np.zeros((2, 2, 4), dtype=np.uint8)
    assert fade.apply(frame, 0)[0, 0, :3].tolist() == [255, 0, 0] and fade.apply(frame, 19)[0, 0, :3].tolist() == [0, 0, 255]
    assert fade.apply(frame, 10) is frame


def test_dead_air_stops_where_a_crossfade_starts() -> None:
    doc = {"frames": 100, "motion": {"changes": [[0, 1.0], [5, 0.1]]}, "overlap_out": 15}
    assert static_runs(doc, 0.0002) == [(0, 5), (5, 85)]


# ----- a rendered video ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rendered(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    """intro (silent) -crossfade-> talk (a real MP3) -fade_color(accent)-> more (a real MP3)
    -crossfade-> outro (silent, a chime at 0.5 s); progress bar, watermark and captions."""
    root = tmp_path_factory.mktemp("transitions") / "proj"
    (root / "audio").mkdir(parents=True)
    for beat in ("s1_b1", "s1_b2"):
        shutil.copy(KPHI3_AUDIO / f"{beat}.mp3", root / "audio" / f"{beat}.mp3")
    data = {
        "title": "Transitions",
        "output": "out",
        "format": {"width": 160, "height": 90, "fps": FPS},
        "preview": {"width": 160, "height": 90, "fps": FPS},
        "transition": "crossfade",
        "overlays": [{"type": "progress_bar"}, {"type": "watermark", "text": "wm"}, {"type": "captions"}],
        "scenes": [
            {"id": "intro", "type": "title", "params": {"title": "Intro"}, "duration": 2},
            {"id": "talk", "type": "title", "params": {"title": "Talk"}, "beats": [{"id": "s1_b1", "text": "First words."}]},
            {
                "id": "more", "type": "bullets", "params": {"title": "More", "items": ["x"]},
                "beats": [{"id": "s1_b2", "text": "Second words."}],
                "transition": {"type": "fade_color", "color": "accent"},
            },
            {"id": "outro", "type": "title", "params": {"title": "Bye"}, "duration": 2, "sfx": [{"sound": "chime", "at": 0.5}]},
        ],
    }
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    out = io.StringIO()
    with registry.isolated(), contextlib.redirect_stdout(out):
        assert main(["render", str(root), "--preview", "--json"]) == 0
    from vidgen import runtime

    runtime.clear_context()
    return root, json.loads(out.getvalue())


def _frames(path: Path) -> np.ndarray:
    with av.open(str(path)) as c:
        return np.stack([f.to_ndarray(format="rgb24").astype(np.int16) for f in c.decode(video=0)])


def _audio(path: Path) -> np.ndarray:
    with av.open(str(path)) as c:
        resampler = av.AudioResampler(format="flt", layout="stereo", rate=RATE)
        chunks = [g.to_ndarray().reshape(-1, 2) for f in c.decode(c.streams.audio[0]) for g in resampler.resample(f)]
    return np.concatenate(chunks)


def _plan(root: Path) -> VideoPlan:
    project = Project.load(root)
    with extensions.project_session(project):
        plan = VideoPlan(project, FPS)
        plan.scenes  # computed while the scene types are registered
    return plan


@pytest.mark.render
def test_rendered_times_follow_the_plan(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, doc = rendered
    plan = _plan(root)
    timings = json.loads((root / "build/preview/timings.json").read_text(encoding="utf-8"))
    starts = [s["start"] for s in timings["scenes"]]
    assert starts == pytest.approx([s.start for s in plan.scenes], abs=1e-6)
    assert timings["duration"] == pytest.approx(plan.duration) == pytest.approx(doc["duration"])
    durations = [s["duration"] for s in timings["scenes"]]
    assert timings["duration"] == pytest.approx(sum(durations) - 2 * 0.5)  # two crossfades
    assert [s.get("transition", {}).get("type") for s in timings["scenes"]] == [None, "crossfade", "fade_color", "crossfade"]
    assert timings["scenes"][1]["transition"] == {"type": "crossfade", "duration": 0.5, "overlap": 0.5}
    # the video and its audio have the planned length
    assert len(_frames(root / "out_preview.mp4")) == round(plan.duration * FPS)
    assert len(_audio(root / "out_preview.mp4")) == pytest.approx(plan.duration * RATE, abs=2048)
    # subtitles start where the overlapped scenes' beats start
    srt = (root / "out_preview.srt").read_text(encoding="utf-8")
    talk = plan.scene("talk").start
    assert f"00:00:0{int(talk)},{round((talk % 1) * 1000):03d} -->" in srt
    # the effects sit at their scene's overlapped start
    [chime] = timings["scenes"][3]["sfx"]
    assert chime["time"] == pytest.approx(plan.scene("outro").start + 0.5)


@pytest.mark.render
def test_audio_lands_where_planned(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    audio = _audio(root / "out_preview.mp4")
    level = np.abs(audio).max(axis=1)

    def onset(after: float, threshold: float) -> float:
        a = round(after * RATE)
        return (a + int(np.argmax(level[a:] > threshold))) / RATE

    lead, _ = speech_bounds(KPHI3_AUDIO / "s1_b1.mp3")
    talk = plan.scene("talk").start
    assert not (level[: round(talk * RATE)] > 0.01).any()  # nothing before the narration (silent intro)
    assert onset(talk, 0.01) == pytest.approx(talk + lead, abs=0.03)
    # the chime of the silent outro, which starts 0.5 s before "more" ends: no narration there
    outro = plan.scene("outro").start
    assert onset(plan.scene("more").start + plan.scene("more").beats[0].end + 0.05, 0.005) == pytest.approx(outro + 0.5, abs=0.02)


@pytest.mark.render
def test_mid_crossfade_frame_blends_both_scenes(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    video = _frames(root / "out_preview.mp4")
    a = _frames(root / "build/preview/scenes/intro.mp4")
    b = _frames(root / "build/preview/scenes/talk.mp4")
    start = round(plan.scene("talk").start * FPS)  # first shared frame; 5 frames, weights 0.1 .. 0.9
    mid = video[start + 2]
    expected = (a[start + 2] + b[2]) / 2
    assert np.abs(mid - expected).mean() < 2.0
    # where the two scenes differ (the intro's title, the talk's title being written), the
    # middle frame is halfway between them: both scenes are in it
    differ = np.abs(a[start + 2] - b[2]).max(axis=2) > 60
    assert differ.sum() > 30
    assert np.abs(mid - expected)[differ].mean() < 12
    assert np.abs(mid - a[start + 2])[differ].mean() > 25 and np.abs(mid - b[2])[differ].mean() > 25
    assert np.abs(video[start - 1] - a[start - 1]).mean() < 2.0 and np.abs(video[start + 5] - b[5]).mean() < 2.0
    # both scenes drew the same overlays in the frames they share (the incoming scene's), so the
    # blend cannot double or fade them: the silent intro shows the talk's caption over its last
    # frames, and the progress bar / watermark match
    background = b[0][45, 2]
    for j in range(5):
        bottom_a, bottom_b = a[start + j][62:], b[j][62:]
        assert (np.abs(bottom_b[:, 30:110] - background).max(axis=2) > 60).sum() > 20  # the caption is there
        assert np.abs(bottom_a - bottom_b).mean() < 2.0, j
        assert np.abs(a[start + j][:2] - b[j][:2]).mean() < 3.0, j
    assert (np.abs(a[start - 1][62:, 30:110] - background).max(axis=2) > 60).sum() < 5  # before it: no caption


@pytest.mark.render
def test_fade_color_dips_to_the_colour(rendered: tuple[Path, dict[str, Any]]) -> None:
    root, _ = rendered
    plan = _plan(root)
    video = _frames(root / "out_preview.mp4")
    cut = round(plan.scene("more").start * FPS)
    accent = np.array([0xFF, 0x6B, 0x6B])  # dark_tech accent
    for k in (cut - 1, cut):  # the last frame of talk and the first of more are the colour
        assert np.abs(video[k][40:50, 60:100] - accent).mean() < 6
    assert np.abs(video[cut - 6][40:50, 60:100] - accent).mean() > 60  # before the fade
    # the progress bar stays over the colour (overlays are drawn above the fade)
    assert np.abs(video[cut][0, :20] - accent).mean() > 30
