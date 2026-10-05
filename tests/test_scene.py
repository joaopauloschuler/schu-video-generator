"""NarratedScene: injection, params, beats, and narration timing (real renders, tiny size)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import av
import pytest
from manim import FadeIn, Square, tempconfig

from conftest import minimal_config
from vidgen import extensions, registry, runtime
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.scene import BeatTiming, NarratedScene, SceneParams, audio_duration

FPS = 5
FRAME = 1 / FPS


@pytest.fixture
def manim_config(tmp_path: Path) -> Iterator[None]:
    """Tiny, uncached, quiet Manim config writing into tmp_path."""
    with tempconfig(
        {
            "pixel_width": 160,
            "pixel_height": 90,
            "frame_rate": FPS,
            "media_dir": str(tmp_path / "media"),
            "disable_caching": True,
            "progress_bar": "none",
            "verbosity": "ERROR",
        }
    ):
        yield


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe is None:
        pytest.skip("ffmpeg not found on PATH")
    return exe


def make_tone(path: Path, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "libmp3lame", str(path)],
        check=True,
        capture_output=True,
    )
    return path


def project_with(make_project, scenes: list[dict], pad: float = 0.4) -> Project:
    return Project.load(make_project(minimal_config(scenes=scenes, narration={"pad": pad, "words_per_second": 2.0})))


def render(cls: type[NarratedScene], project: Project, scene_id: str, audio: bool = True) -> tuple[NarratedScene, Path]:
    with tempconfig({"output_file": f"{scene_id}_{'a' if audio else 'n'}"}):
        scene = cls(project.scene(scene_id), project, audio=audio)
        scene.render()
        return scene, Path(scene.renderer.file_writer.movie_file_path)


def media_info(path: Path) -> tuple[float, list[str]]:
    with av.open(str(path)) as c:
        return c.duration / av.time_base, [s.type for s in c.streams]


# ----- construction (no rendering) ------------------------------------------------------------------


class Panel(NarratedScene):
    class Params(SceneParams):
        values: dict[str, float]
        best: str | None = None


def test_injection_and_params(make_project, manim_config: None) -> None:
    project = project_with(make_project, [{"id": "s", "type": "panel", "params": {"values": {"a": 1}}, "beats": [{"text": "x"}]}])
    theme = runtime.set_context(project)
    scene = Panel(project.scene("s"))  # project and theme default to the runtime context
    assert scene.project is project and scene.theme is theme
    assert isinstance(scene.params, Panel.Params) and scene.params.values == {"a": 1.0}
    assert [b.id for b in scene.beats] == ["s_b1"] and scene.beat_log == [] and scene.audio_enabled


def test_theme_without_context_comes_from_project(make_project, manim_config: None) -> None:
    project = project_with(make_project, [{"id": "s", "type": "t", "beats": [{"text": "x"}]}])
    project.config.theme.colors["text"] = "#010203"
    scene = NarratedScene(project.scene("s"), project, audio=False)
    assert scene.theme.color("text") == "#010203" and not scene.audio_enabled
    assert scene.params == {}


def test_invalid_params_raise_on_construction(make_project, manim_config: None) -> None:
    project = project_with(make_project, [{"id": "s", "type": "panel", "params": {"values": 3}, "beats": [{"text": "x"}]}])
    with pytest.raises(VidgenError, match=r"scene 's': invalid params\n  params.values: "):
        Panel(project.scene("s"), project)


@pytest.mark.parametrize(
    ("spec", "text", "ok", "bad"),
    [
        (None, None, [0, 1, 7], []),
        (2, "exactly 2 beats", [2], [(1, "needs exactly 2 beats, got 1"), (3, "needs exactly 2 beats, got 3")]),
        (1, "exactly 1 beat", [1], [(0, "needs exactly 1 beat, got 0")]),
        ((1, None), "at least 1 beat", [1, 9], [(0, "needs at least 1 beat, got 0")]),
        ((2, 4), "2 to 4 beats", [2, 3, 4], [(5, "needs 2 to 4 beats, got 5")]),
    ],
)
def test_beat_count(spec, text, ok, bad) -> None:
    cls = type("Fixed", (NarratedScene,), {"beat_count": spec})
    assert cls.beat_count_text() == text
    assert all(cls.check_beat_count(n) is None for n in ok)
    assert [(n, cls.check_beat_count(n)) for n, _ in bad] == bad


def test_wrong_beat_count_raises_on_construction(make_project, manim_config: None) -> None:
    class TwoBeats(NarratedScene):
        beat_count = 2

    project = project_with(make_project, [{"id": "s", "type": "t", "beats": [{"text": "x"}]}])
    with pytest.raises(VidgenError, match=r"scene 's': needs exactly 2 beats, got 1"):
        TwoBeats(project.scene("s"), project)


def test_beat_lookup_and_durations(make_project, manim_config: None) -> None:
    project = project_with(
        make_project,
        [{"id": "s", "type": "t", "beats": [{"text": "one two three four"}, {"id": "named", "text": "a b"}]}],
    )
    tone = make_tone(project.audio_dir / "named.mp3", 0.6)
    scene = NarratedScene(project.scene("s"), project)
    assert scene.beat(0).id == "s_b1" and scene.beat("named").id == "named"
    assert scene.beat(scene.beats[1]) is scene.beats[1]
    assert scene.beat_audio(0) is None and scene.beat_audio("named") == tone
    assert scene.beat_duration(0) == pytest.approx(2.0)  # 4 words at 2 words/s
    assert scene.beat_duration("named") == pytest.approx(audio_duration(tone)) and 0.55 < audio_duration(tone) < 0.7
    with pytest.raises(VidgenError, match="beat index 2 out of range"):
        scene.beat(2)
    with pytest.raises(VidgenError, match=r"unknown beat 'nope' \(beats: s_b1, named\)"):
        scene.beat("nope")


def test_audio_duration_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio")
    with pytest.raises(VidgenError, match="cannot read audio file"):
        audio_duration(bad)


# ----- rendering ------------------------------------------------------------------------------------


@pytest.mark.render
def test_narrate_timing_with_audio_and_no_audio(make_project, manim_config: None) -> None:
    project = project_with(
        make_project,
        [{"id": "card", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "a"}, {"text": "b"}]}],
        pad=0.4,
    )
    d1 = audio_duration(make_tone(project.audio_dir / "card_b1.mp3", 1.0))
    d2 = audio_duration(make_tone(project.audio_dir / "card_b2.mp3", 0.6))
    with extensions.project_session(project):
        cls = registry.get("text_card").cls
        scene, movie = render(cls, project, "card")
        silent_scene, silent_movie = render(cls, project, "card", audio=False)

    log = scene.beat_log
    assert [entry.beat_id for entry in log] == ["card_b1", "card_b2"]
    assert log[0] == BeatTiming("card_b1", 0.0, pytest.approx(d1), "a")
    assert log[1].start == pytest.approx(d1 + 0.4, abs=FRAME / 2 + 1e-9)
    assert log[1].end == pytest.approx(log[1].start + d2)
    total = scene.timings()["duration"]
    assert total == pytest.approx(d1 + d2 + 2 * 0.4, abs=FRAME + 1e-9)
    duration, streams = media_info(movie)
    assert duration == pytest.approx(total, abs=FRAME) and "audio" in streams

    # --no-audio: identical timing, no sound in the file
    assert silent_scene.beat_log == log and silent_scene.timings() == scene.timings()
    duration, streams = media_info(silent_movie)
    assert duration == pytest.approx(total, abs=FRAME) and "audio" not in streams


class Estimated(NarratedScene):
    """Narrates by id and index; the first beat's animation outlasts its narration."""

    def construct(self) -> None:
        square = Square()
        with self.narrate("e_b1") as d:  # 3 words at 2 words/s = 1.5 s
            assert d == pytest.approx(1.5)
            self.play(FadeIn(square), run_time=2.4)  # longer than d + pad: no extra wait
        with self.narrate(1) as d:  # 2 words = 1.0 s
            assert d == pytest.approx(1.0)
        with pytest.raises(VidgenError, match="narrated twice"):
            with self.narrate(0):
                pass


@pytest.mark.render
def test_narrate_timing_from_word_estimate(make_project, manim_config: None) -> None:
    project = project_with(
        make_project, [{"id": "e", "type": "estimated", "beats": [{"text": "one two three"}, {"text": "four five"}]}], pad=0.4
    )
    runtime.set_context(project)
    scene, movie = render(Estimated, project, "e")
    b1, b2 = scene.beat_log
    assert (b1.start, b1.end) == (0.0, pytest.approx(1.5))
    assert b2.start == pytest.approx(2.4)  # the long animation pushed beat 2 back
    assert b2.end == pytest.approx(3.4)
    assert scene.timings()["duration"] == pytest.approx(2.4 + 1.0 + 0.4, abs=FRAME / 2 + 1e-9)
    duration, streams = media_info(movie)
    assert duration == pytest.approx(scene.timings()["duration"], abs=FRAME) and "audio" not in streams


@pytest.mark.render
def test_silent_scene_is_held_for_duration(make_project, manim_config: None) -> None:
    project = project_with(make_project, [{"id": "quiet", "type": "text_card", "params": {"text": "..."}, "duration": 1.4}])
    with extensions.project_session(project):
        scene, movie = render(registry.get("text_card").cls, project, "quiet")
    assert scene.beat_log == []
    assert scene.timings() == {"scene": "quiet", "duration": pytest.approx(1.4), "beats": []}
    assert media_info(movie)[0] == pytest.approx(1.4, abs=FRAME)


class PartlyNarrated(NarratedScene):
    def construct(self) -> None:
        with self.narrate(0):
            pass


@pytest.mark.render
def test_unnarrated_beats_are_reported(make_project, manim_config: None, caplog: pytest.LogCaptureFixture) -> None:
    project = project_with(make_project, [{"id": "p", "type": "x", "beats": [{"text": "a"}, {"text": "b"}]}], pad=0.0)
    with caplog.at_level("WARNING", logger="vidgen.scene"):
        scene, _ = render(PartlyNarrated, project, "p", audio=False)
    assert "scene 'p' never narrated beats: p_b2" in caplog.text
    assert [t.beat_id for t in scene.beat_log] == ["p_b1"]
