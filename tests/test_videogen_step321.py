"""Step 321 (DESIGN.md §113.17): readable overlays, the film's disclosure, the fast music list,
the plan's voice note, orphaned audio of a config without beats. Cheap: nothing is rendered."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from vidgen.music import BUILTIN_BEDS, music_entries
from vidgen.tts.cache import orphaned_audio
from vidgen.videogen.compose import clip_takes, credit_line
from vidgen.videogen.inputs import CHANGE_LEVELS, changed_mask
from vidgen.videogen.shots import _check_sound


def _frames(moved: bool = True, whole: bool = False) -> tuple[Image.Image, Image.Image]:
    size = (64, 36)
    first = Image.new("L", size, 40)
    last = Image.new("L", size, 40)
    if whole:
        last.paste(200, (0, 0, *size))
    elif moved:
        last.paste(40 + CHANGE_LEVELS + 9, (10, 10, 20, 20))
    return first, last


def test_changed_mask_finds_a_small_change_and_ignores_none_or_everything() -> None:
    mask = changed_mask(*_frames())
    assert mask is not None and np.asarray(mask).max() == 255
    assert changed_mask(*_frames(moved=False)) is None
    assert changed_mask(*_frames(whole=True)) is None   # a camera move or a fade


def _project(root: Path, *paths: str) -> SimpleNamespace:
    scenes = [SimpleNamespace(type="video_clip", id=f"s{i}", params={"path": path}, beats=[]) for i, path in enumerate(paths)]
    return SimpleNamespace(root=root, config=SimpleNamespace(scenes=scenes), draft=False)


def test_a_video_clip_of_a_take_is_disclosed(tmp_path: Path) -> None:
    folder = tmp_path / "takes" / "a"
    folder.mkdir(parents=True)
    (folder / "2.mp4").write_bytes(b"x")
    (folder / "2.json").write_text(json.dumps({"model": "m/n"}), encoding="utf-8")
    project = _project(tmp_path, "takes/a/2.mp4", "assets/other.mp4")
    assert clip_takes(project) == [("a", 2, "m/n")]
    assert clip_takes(project, "s1") == []
    assert credit_line(project) == "Includes AI-generated footage (m/n)."


def test_a_clip_outside_takes_is_not_disclosed(tmp_path: Path) -> None:
    assert credit_line(_project(tmp_path, "assets/other.mp4")) == ""


def test_list_music_text_needs_no_synthesis() -> None:
    entries = music_entries(None, analyse=False)
    beds = [e for e in entries if e["origin"] == "builtin"]
    assert [e["name"] for e in beds] == list(BUILTIN_BEDS)
    assert all(e["loudness"] is None and e["loop_seconds"] == round(BUILTIN_BEDS[e["name"]].seconds, 3) for e in beds)


def test_a_config_without_beats_reports_no_orphans(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "shot1.mp3").write_bytes(b"x")
    project = SimpleNamespace(audio_dir=audio, beats=lambda: [])
    assert orphaned_audio(project) == []


def _sound_shot(*, line: bool = True, wants_audio: bool = False) -> SimpleNamespace:
    return SimpleNamespace(sound="model", model=SimpleNamespace(id="m/n", generate_audio=True), spec=SimpleNamespace(place=False, line=line, wants_audio=wants_audio), notes=[], blocked=[])


def test_the_plan_notes_a_spoken_line_with_no_voice_input() -> None:
    shot = _sound_shot()
    _check_sound(shot)
    assert any("no voice input" in n for n in shot.notes)
    for kept in (_sound_shot(line=False), _sound_shot(wants_audio=True)):
        _check_sound(kept)
        assert not any("no voice input" in n for n in kept.notes)
