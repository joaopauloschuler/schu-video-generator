"""Step 100: beats without ``overlap`` / ``interrupt`` keep their timings and audio. The values
below were recorded on the code before Step 100 (HEAD e312f91) and must not change — except the
rendered timings, changed on purpose in Step 191 to match the plan (the half-frame fix)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from manim import tempconfig

from conftest import minimal_config
from test_scene import make_tone
from vidgen import extensions, registry
from vidgen.project import Project
from vidgen.sfx import decode_audio, stereo, write_wav
from vidgen.videoplan import VideoPlan

SCENES = [
    {"id": "card", "type": "text_card", "params": {"text": "Hi"},
     "beats": [{"text": "one two three"}, {"text": "four five"}, {"text": "six seven eight nine"}]},
    {"id": "end", "type": "text_card", "params": {"text": "Bye"}, "beats": [{"text": "ten eleven"}]},
]
#: (beat id, start, end) of every beat as VideoPlan planned it, and the scenes' starts (5 fps).
PLANNED = [("card_b1", 0.0, 1.5), ("card_b2", 2.0, 3.0), ("card_b3", 3.4, 5.4), ("end_b1", 0.0, 1.0)]
SCENE_STARTS = [0.0, 5.8]
#: ``scene.timings()`` of ``card`` rendered at 5 fps (word-count estimate, 2 words/s, pad 0.4).
#: Step 191: the beats now start where the plan puts them (``PLANNED``); before, a window of
#: half a frame (1.5 s + 0.4 s = 9.5 frames) was rounded as the time left after the beat's
#: entrance, so the render started ``card_b2`` at 1.8 s, one frame before the plan's 2.0 s.
TIMINGS = {
    "scene": "card",
    "duration": 5.8,
    "beats": [
        {"id": "card_b1", "start": 0.0, "end": 1.5, "text": "one two three"},
        {"id": "card_b2", "start": 2.0, "end": 3.0, "text": "four five"},
        {"id": "card_b3", "start": 3.4, "end": 5.4, "text": "six seven eight nine"},
    ],
}


@pytest.fixture
def tiny(tmp_path: Path) -> Iterator[None]:
    with tempconfig({"pixel_width": 160, "pixel_height": 90, "frame_rate": 5, "media_dir": str(tmp_path / "media"),
                     "disable_caching": True, "progress_bar": "none", "verbosity": "ERROR"}):
        yield


def _project(make_project) -> Project:
    return Project.load(make_project(minimal_config(scenes=SCENES, narration={"pad": 0.4, "words_per_second": 2.0})))


def _rounded(data: Any) -> Any:
    if isinstance(data, float):
        return round(data, 6)
    if isinstance(data, dict):
        return {k: _rounded(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_rounded(v) for v in data]
    return data


def test_planned_timeline_is_pinned(make_project) -> None:
    project = _project(make_project)
    plan = VideoPlan(project, 5)
    slots = [(b.id, round(b.start, 6), round(b.end, 6)) for s in plan.scenes for b in s.beats]
    assert slots == PLANNED
    assert [round(s.start, 6) for s in plan.scenes] == SCENE_STARTS


@pytest.mark.render
def test_rendered_timings_and_audio_are_pinned(make_project, tiny: None, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(make_project)
    with extensions.project_session(project):
        cls = registry.get("text_card").cls
        scene = cls(project.scene("card"), project, audio=False)
        scene.render()
        assert _rounded(scene.timings()) == TIMINGS

        # with audio: each beat's MP3 is added once, at its start, decoded as it is (no shaping)
        for beat, seconds in zip(("card_b1", "card_b2", "card_b3"), (1.0, 0.6, 0.8)):
            make_tone(project.audio_dir / f"{beat}.mp3", seconds)
        added: list[tuple[float, str]] = []
        add_sound = cls.add_sound

        def recording(self: Any, path: str, time_offset: float = 0, gain: Any = None, **kwargs: Any) -> None:
            added.append((round(float(self.renderer.time) + time_offset, 6), hashlib.sha1(Path(path).read_bytes()).hexdigest()))
            add_sound(self, path, time_offset, gain, **kwargs)

        monkeypatch.setattr(cls, "add_sound", recording)
        with tempconfig({"output_file": "card_audio"}):
            voiced = cls(project.scene("card"), project, audio=True)
            voiced.render()
    expected = []
    for entry in voiced.beat_log:
        wav = project.root / f"{entry.beat_id}.wav"
        write_wav(wav, stereo(decode_audio(project.audio_dir / f"{entry.beat_id}.mp3")))
        expected.append((round(entry.start, 6), hashlib.sha1(wav.read_bytes()).hexdigest()))
    assert added == expected
