"""Step 35: video clips (``vidgen.api``: ``probe_clip``, ``ClipTiming``, ``ClipMobject``,
``clip_audio``, ``fit_speed``) and the ``video_clip`` scene type (layout, timing contract: trim,
speed, loop / hold, fit_duration; clip sound under the narration; callouts; targets; lint)."""

from __future__ import annotations

import copy
import re
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import av
import numpy as np
import pytest
from manim import Group, tempconfig
from PIL import Image as PILImage
from pydantic import ValidationError

from conftest import clip_frame_index, minimal_config, write_clip
from test_actions import beat_total, beats, render
from test_builtin_scenes import cls_of
from test_schema import errors
from vidgen import api, registry, schema
from vidgen.cli import check_project
from vidgen.clips import ClipMobject, ClipReader, ClipTiming, atempo_chain, clip_audio, fit_speed, probe_clip
from vidgen.errors import VidgenError
from vidgen.lint import lint_project
from vidgen.project import Project
from vidgen.render.worker import frame_size
from vidgen.theme import Theme

FPS = 5
NARRATION = {"pad": 0.2, "words_per_second": 4.0}
WORDS12 = " ".join(["word"] * 12)  # 3 s at 4 words/s, + 0.2 s pad: 16 frames at 5 fps


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 4 s, 5 fps clip (20 frames, frame n a grey telling n) with a tone."""
    return write_clip(tmp_path_factory.mktemp("clip") / "grey.mp4")


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("media")


def grey(pixels: np.ndarray, x: int | None = None, y: int | None = None) -> int:
    """The clip frame number a pixel (default: the centre) shows."""
    h, w = pixels.shape[:2]
    return clip_frame_index(float(pixels[h // 2 if y is None else y, w // 2 if x is None else x, 0]))


def load(make_project, clip: Path, scenes: list[dict[str, Any]], **overrides: Any) -> Project:
    root = make_project(minimal_config(scenes=scenes, narration=NARRATION, **overrides))
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / "clip.mp4").write_bytes(clip.read_bytes())
    return Project.load(root)


def clip_scene(n_beats: int = 1, words: str = WORDS12, scene_id: str = "v", **params: Any) -> dict[str, Any]:
    return {"id": scene_id, "type": "video_clip", "params": {"path": "assets/clip.mp4", **params}, "beats": beats(*([None] * n_beats), words=words)}


def movie_frames(scene: Any) -> list[np.ndarray]:
    """Every frame of the scene's rendered movie (RGB)."""
    with av.open(str(scene.renderer.file_writer.movie_file_path)) as container:
        return [f.to_ndarray(format="rgb24") for f in container.decode(container.streams.video[0])]


def params(**changes: Any) -> Any:
    return cls_of("video_clip").validate_params({"path": "assets/clip.mp4", **changes}, Theme())


# ----- clip helpers --------------------------------------------------------------------------------


def test_probe_clip(clip: Path, tmp_path: Path) -> None:
    info = probe_clip(clip)
    assert (info.width, info.height, info.fps, info.audio) == (64, 36, 5.0, True)
    assert info.duration == pytest.approx(4.0, abs=0.05) and info.aspect == pytest.approx(64 / 36)
    assert probe_clip(write_clip(tmp_path / "mute.mp4", seconds=1, audio=False)).audio is False
    (tmp_path / "bad.mp4").write_bytes(b"not a video at all")
    with pytest.raises(VidgenError, match="cannot read video bad.mp4"):
        probe_clip(tmp_path / "bad.mp4")
    with pytest.raises(VidgenError, match="cannot read video"):
        probe_clip(tmp_path / "missing.mp4")


@pytest.mark.parametrize(
    ("timing", "played", "shown"),
    [
        (ClipTiming(0, 4), 1.0, 1.0),
        (ClipTiming(0, 4), 9.0, 4.0 - 5e-3),                 # held: the last frame before the end
        (ClipTiming(0, 4, speed=2), 1.5, 3.0),
        (ClipTiming(1, 3, loop=True), 2.5, 1.5),             # 2 s span: 2.5 s in is 0.5 s into pass 2
        (ClipTiming(1, 3, speed=0.5, loop=True), 5.0, 1.5),  # a pass takes 4 s
        (ClipTiming(1, 3), -1.0, 1.0),                       # before it starts: its first frame
    ],
)
def test_clip_timing(timing: ClipTiming, played: float, shown: float) -> None:
    assert timing.source_time(played) == pytest.approx(shown)


def test_clip_timing_lengths_and_fit_speed() -> None:
    timing = ClipTiming(1, 3, speed=0.5)
    assert (timing.span, timing.length) == (2, 4)
    assert fit_speed(4, 8) == 0.5 and fit_speed(4, 2) == 2.0 and fit_speed(4, 5) == pytest.approx(0.8)
    assert fit_speed(4, 1) == 2.0 and fit_speed(4, 100) == 0.5      # clamped to [0.5, 2]
    assert fit_speed(4, 1, 0.25, 4.0) == 4.0


@pytest.mark.parametrize("speed", [0.25, 0.4, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0])
def test_atempo_chain_multiplies_to_the_speed(speed: float) -> None:
    factors = [float(f.split("=")[1]) for f in atempo_chain(speed)]
    assert all(0.5 - 1e-9 <= f <= 2.0 + 1e-9 for f in factors)
    assert float(np.prod(factors)) == pytest.approx(speed)


def test_reader_decodes_in_order_seeks_back_and_crops(clip: Path) -> None:
    reader = ClipReader(clip, (32, 18))
    assert [grey(reader.frame(t)) for t in (0.0, 0.19, 0.2, 1.0, 3.9, 9.0)] == [0, 0, 1, 5, 19, 19]
    assert grey(reader.frame(0.4)) == 2                       # back: seeks (a loop)
    assert grey(reader.frame(3.0)) == 15                      # far ahead: seeks
    first = reader.frame(3.0)
    assert reader.frame(3.1) is first                         # the same frame: converted once
    assert first.shape == (18, 32, 4) and first.dtype == np.uint8
    reader.close()
    cropped = ClipReader(clip, (20, 18), crop=(0.25, 0.0, 0.5, 1.0))
    assert cropped.frame(0.0).shape == (18, 20, 4)
    cropped.close()


def test_clip_audio_hold_loop_speed_and_volume(clip: Path, tmp_path: Path) -> None:
    def levels(path: Path) -> list[float]:
        with wave.open(str(path)) as w:
            assert (w.getframerate(), w.getnchannels()) == (48000, 2)
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2) / 32768
        seconds = len(data) / 48000
        return [round(seconds, 2)] + [float(np.sqrt(np.mean(data[int(a * 48000) : int((a + 0.2) * 48000)] ** 2))) for a in (0.2, 1.4, 2.4)]

    out = tmp_path / "a.wav"
    assert clip_audio(clip, out, ClipTiming(0, 1), length=3.0, fade=0.5)
    length, early, after, late = levels(out)
    assert length == 3.0 and early > 0.03 and after < 1e-4 and late < 1e-4     # one pass, then silence
    clip_audio(clip, out, ClipTiming(0, 1, loop=True), length=3.0, fade=0.5)
    assert levels(out)[2] == pytest.approx(early, rel=0.1)                     # looped
    clip_audio(clip, out, ClipTiming(0, 2, speed=2), length=3.0, volume=0.5, fade=0)
    _, half, after, _ = levels(out)
    assert half == pytest.approx(0.5 * early, rel=0.1) and after < 1e-4        # half volume; a 1 s pass
    assert not clip_audio(write_clip(tmp_path / "mute.mp4", seconds=1, audio=False), out, ClipTiming(0, 1), length=1)


def test_clip_mobject_follows_the_clock_and_shares_its_playback(clip: Path) -> None:
    fake = SimpleNamespace(renderer=SimpleNamespace(time=0.0))
    mob = ClipMobject(clip, ClipTiming(0, 4, speed=2)).fit_box(4, 4, "contain")
    assert (mob.width, mob.height) == pytest.approx((4, 4 * 36 / 64))
    mob.set_resolution().play(fake)
    assert grey(mob.get_pixel_array()) == 0
    fake.renderer.time = 1.0
    assert grey(mob.get_pixel_array()) == 10 and mob.playback_time() == pytest.approx(2.0)
    twin = mob.copy()
    assert twin.playback is mob.playback and twin is not mob and grey(twin.get_pixel_array()) == 10
    assert copy.deepcopy(Group(mob))[0].playback is mob.playback
    mob.set_opacity(0.5)                                        # opacity lives in the modulation
    assert mob.pixel_array.shape == (1, 2, 4) and mob.get_pixel_array()[0, 0, 3] == 127
    mob.close()


def test_clip_mobject_cover_crops_and_resolution(clip: Path) -> None:
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_width": 160 / 90 * 8, "frame_height": 8}):
        mob = ClipMobject(clip).fit_box(4, 4, "cover")
        assert (mob.width, mob.height) == pytest.approx((4, 4))
        x, y, w, h = mob.crop
        assert (y, h) == (0.0, 1.0) and w == pytest.approx(36 / 64) and x == pytest.approx((1 - 36 / 64) / 2)
        mob.set_resolution(3.0)                         # 45 px shown; the crop has 36: no more detail
        assert mob.playback.size == (45, 45)
        assert mob.resampling_algorithm == PILImage.Resampling.NEAREST
        mob.set_resolution(1.0)
        assert mob.get_pixel_array().shape == (45, 45, 4)
        mob.close()


def test_api_exports() -> None:
    for name in ("CLIP_SUFFIXES", "ClipInfo", "ClipMobject", "ClipTiming", "clip_audio", "fit_speed", "probe_clip"):
        assert name in api.__all__ and name in api.VIDGEN_NAMES and getattr(api, name).__doc__ or name == "CLIP_SUFFIXES"


# ----- params and validate -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"trim": [3, 1]}, "0 <= start < end"),
        ({"trim": [-1, 1]}, "0 <= start < end"),
        ({"speed": 8}, "less than or equal to 4"),
        ({"fit_duration": True, "speed": 2}, "fit_duration chooses the speed"),
        ({"fit_range": [0.1, 2]}, "within 0.25-4"),
        ({"fit_range": [2, 1]}, "within 0.25-4"),
        ({"region": "bleed", "frame": "window"}, "a frame needs a region"),
        ({"region": "header"}, "region"),
        ({"url": "x.org"}, "only a browser frame"),
        ({"volume": 3}, "less than or equal to 2"),
        ({"fit": "stretch"}, "'contain' or 'cover'"),
        ({"steps": [{"magnifier": [0.1, 0.1, 0.2, 0.2]}]}, "a magnifier needs a still picture"),
        ({"steps": [{"box": [0.9, 0.1, 0.2, 0.2]}]}, "not inside the clip"),
    ],
)
def test_params_errors(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        params(**changes)


def test_params_defaults_and_targets() -> None:
    p = params()
    assert (p.region, p.fit, p.trim, p.speed, p.loop, p.volume, p.mute, p.fit_range) == ("body", "contain", None, 1.0, False, None, False, (0.5, 2.0))
    assert params(fit_duration=True, fit_range=[0.25, 4]).fit_duration
    cls = cls_of("video_clip")
    full = params(title="T", caption="C", steps=[{"box": [0.1, 0.1, 0.2, 0.2], "label": "Box"}, [{"arrow": [0.5, 0.5]}, {"spotlight": [0, 0, 0.5, 0.5]}]])
    assert cls.target_names(full) == ["title", "clip", "caption", "callout1", "callout:Box", "callout2", "callout3", "step1", "step2"]
    assert cls.target_names(params()) == ["clip"]
    assert cls.target_patterns == ("title", "clip", "caption", "callout<N>", "callout:<label>", "step<N>")


def test_schema_has_the_scene_and_its_shorthands() -> None:
    cls_of("video_clip")
    doc = schema.params_schema(registry.get("video_clip"), [Theme()])
    item = {"path": "a.mp4", "trim": [1, 2], "steps": [{"box": [0.1, 0.1, 0.2, 0.2], "label": "x"}, [{"arrow": [0.5, 0.5]}]]}
    assert errors(doc, item) == []
    assert errors(doc, {"path": "a.mp4", "speed": 9})


def test_validate_project(make_project, clip: Path, tmp_path: Path) -> None:
    project = load(make_project, clip, [
        clip_scene(trim=[1, 9]),
        clip_scene(scene_id="p", units="px", steps=[{"box": [60, 10, 10, 10]}]),
        {"id": "m", "type": "video_clip", "params": {"path": "assets/nope.mp4"}, "duration": 1},
        {"id": "g", "type": "video_clip", "params": {"path": "assets/clip.gif"}, "duration": 1},
        {"id": "b", "type": "video_clip", "params": {"path": "assets/bad.mp4"}, "duration": 1},
    ])
    (project.root / "assets" / "clip.gif").write_bytes(b"GIF89a")
    (project.root / "assets" / "bad.mp4").write_bytes(b"nope")
    problems = check_project(project)
    assert any("trim: [1.0, 9.0] ends after the clip (4.00 s)" in p for p in problems)
    assert any("area: [60.0, 10.0, 10.0, 10.0] is not inside the clip (64 x 36 px)" in p for p in problems)
    assert any("path: file not found: assets/nope.mp4" in p for p in problems)
    assert any("path: unsupported video type '.gif'" in p for p in problems)
    assert any("path: cannot read video bad.mp4" in p for p in problems)


# ----- renders ---------------------------------------------------------------------------------------


def shown_indices(scene: Any, frames: range) -> list[int]:
    movie = movie_frames(scene)
    return [grey(movie[n]) for n in frames]


def expected_indices(timing: ClipTiming, frames: range) -> list[int]:
    return [min(int((timing.source_time(n / FPS) + 2e-3) * 5), 19) for n in frames]  # 20 frames


AFTER_FADE = range(9, 16)  # the clip has faded in (1.5 s) and the 3.2 s beat is still running


@pytest.mark.render
@pytest.mark.parametrize(
    ("changes", "timing"),
    [
        ({"speed": 2}, ClipTiming(0, 4, speed=2)),                          # 2 s pass, then holds
        ({"trim": [1, 2], "loop": True}, ClipTiming(1, 2, loop=True)),      # frames 5-9 again and again
        ({"fit_duration": True}, ClipTiming(0, 4, speed=4 / 3.2)),          # 4 s fitted into 3.2 s
        ({}, ClipTiming(0, 4)),
    ],
    ids=["speed-hold", "trim-loop", "fit", "plain"],
)
def test_the_clip_plays_on_the_scene_clock(changes: dict[str, Any], timing: ClipTiming, make_project, clip: Path, media: Path) -> None:
    project = load(make_project, clip, [clip_scene(region="bleed", fit="cover", mute=True, **changes)])
    scene = render(project, "v", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    assert scene._img.timing.speed == pytest.approx(timing.speed)
    assert shown_indices(scene, AFTER_FADE) == expected_indices(timing, AFTER_FADE)


@pytest.mark.render
def test_a_long_hold_warns(make_project, clip: Path, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    project = load(make_project, clip, [clip_scene(trim=[0, 0.4], mute=True)])
    render(project, "v", media)
    assert "its last frame holds for 2.8 s (loop: true or fit_duration: true keep it moving)" in caplog.text


@pytest.mark.render
@pytest.mark.parametrize("size", [(160, 90), (90, 160)], ids=["landscape", "portrait"])
@pytest.mark.parametrize(
    "changes",
    [
        {"title": "A clip", "caption": "Under it", "frame": "browser", "url": "example.org", "fit": "cover", "region": "left"},
        {"title": "Bleed", "caption": "On a plate", "region": "bleed", "fit": "contain"},
        {"frame": "phone", "region": "center"},
    ],
    ids=["framed", "bleed", "phone"],
)
@pytest.mark.slow
def test_layouts_render_with_callouts(changes: dict[str, Any], size: tuple[int, int], make_project, clip: Path, media: Path) -> None:
    steps = [{"box": [0.1, 0.1, 0.3, 0.3], "label": "Box"},
             {"callouts": [{"spotlight": [0.5, 0.5, 0.4, 0.4]}, {"arrow": [0.7, 0.7], "label": "Here"}], "focus": True},
             {"circle": [0.5, 0.5], "label": "Back"}]
    project = load(make_project, clip, [clip_scene(n_beats=3, words="one two three four", steps=steps, **changes)])
    scene = render(project, "v", media, size=size, fade=True)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene) + scene.outro, abs=1.5 / FPS)
    assert sorted({n for t in scene.targets for n in t.names}) == sorted(type(scene).target_names(scene.params))
    clip_mob = scene._img
    fw, fh = frame_size(*size)
    if changes.get("region") == "bleed":   # contain: as wide or as high as the frame
        assert clip_mob.width == pytest.approx(fw) or clip_mob.height == pytest.approx(fh)
    else:
        with tempconfig({"frame_width": fw, "frame_height": fh}):
            assert scene.safe_area.contains(clip_mob)
    assert scene.mobjects == []
    assert clip_mob.playback.reader is None   # closed after rendering


@pytest.mark.render
def test_cover_moves_callout_areas_into_the_shown_crop(make_project, clip: Path, media: Path, caplog: pytest.LogCaptureFixture) -> None:
    project = load(make_project, clip, [clip_scene(region="bleed", fit="cover", mute=True, steps=[{"box": [0.25, 0.25, 0.5, 0.5]}, {"box": [0.0, 0.0, 0.1, 0.1]}], n_beats=2)])
    scene = render(project, "v", media, size=(90, 160))   # portrait: the 16:9 clip is cut at the sides
    area, units = scene._spec_area(scene.params.steps[0].callouts[0])
    x, _, w, _ = scene._img.crop
    assert units == "fraction" and area == pytest.approx([(0.25 - x) / w, 0.25, 0.5 / w, 0.5])
    assert "callout 2 (box) is partly outside the part of the clip that fit: cover shows" in caplog.text


@pytest.mark.render
def test_clip_sound_is_mixed_under_the_narration(make_project, clip: Path, media: Path) -> None:
    def sound(**changes: Any) -> Any:
        project = load(make_project, clip, [clip_scene(region="bleed", **changes)])
        writer = render(project, "v", media).renderer.file_writer
        return writer.audio_segment if writer.includes_sound else None

    under, full = sound(), sound(volume=1)
    assert under is not None and full is not None
    assert under.duration_seconds == pytest.approx(3.2 + 0.5, abs=0.05)          # beats + the fade-out
    assert under.rms / full.rms == pytest.approx(0.25, rel=0.1)
    assert sound(mute=True) is None and sound(volume=0) is None


@pytest.mark.render
def test_actions_dim_and_highlight_the_moving_clip(make_project, clip: Path, media: Path) -> None:
    acts = [[{"dim": "clip", "until": "v_b3"}], [{"highlight": "clip", "color": "#FF0000"}], None]
    scene_cfg = clip_scene(region="bleed", fit="cover", mute=True)
    scene_cfg["beats"] = beats(*acts, words="one two three four five six")
    project = load(make_project, clip, [scene_cfg])
    scene = render(project, "v", media)
    movie = movie_frames(scene)
    starts = [round(t.start * FPS) for t in scene.beat_log]
    dimmed, tinted = movie[starts[1] - 1], movie[starts[2] - 1]
    assert dimmed[45, 80, 0] < 0.6 * movie[starts[0] + 6][45, 80, 0] + 30          # faded towards the background
    assert int(tinted[45, 80, 0]) - int(tinted[45, 80, 1]) > 30                   # tinted red
    assert scene._img.pixel_array.shape == (1, 2, 4)


@pytest.mark.render
@pytest.mark.slow
def test_dead_air_sees_clip_motion_and_a_held_frame(make_project, clip: Path) -> None:
    words = " ".join(["word"] * 30)   # 7.5 s
    project = load(make_project, clip, [clip_scene(scene_id="held", words=words, trim=[0, 1]),
                                        clip_scene(scene_id="looped", words=words, trim=[0, 1], loop=True)],
                   preview={"width": 160, "height": 90, "fps": 5})
    result = lint_project(project, rules=["dead_air"])
    assert [(f.scene, f.rule) for f in result.findings] == [("held", "dead_air")]


@pytest.mark.render
def test_extending_clip_example_renders(make_project, clip: Path, media: Path) -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "EXTENDING.md").read_text(encoding="utf-8")
    code = re.search(r"\*\*Video clips\.\*\*.*?```python\n(.*?)```", text, re.S).group(1)
    project = load(make_project, clip, [{"id": "a", "type": "clip_and_note", "beats": beats(None, None, words=WORDS12)}])
    (project.root / "extensions").mkdir(exist_ok=True)
    (project.root / "extensions" / "clip_note.py").write_text("from vidgen.api import *\n\n\n" + code, encoding="utf-8")
    scene = render(Project.load(project.root), "a", media)
    assert float(scene.renderer.time) == pytest.approx(beat_total(scene), abs=1.5 / FPS)
    movie = movie_frames(scene)
    x = round(movie[0].shape[1] * (scene.clip.get_x() / 14.222 + 0.5))
    shown = [grey(movie[n], x=x) for n in (12, 15, 22, 25)]
    assert shown == [2, 5, 2, 5] and scene.clip.playback.reader is None   # a 2 s loop, closed
