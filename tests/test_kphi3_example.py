"""The migrated kphi3 paper video (examples/kphi3): config, committed audio, and a tiny render.

The full-resolution regression comparison against the original video is documented in
examples/kphi3/REGRESSION.md; these tests only guard that the example keeps working.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from vidgen import tts
from vidgen.cli import check_project, main
from vidgen.project import Project
from vidgen.scene import audio_duration

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "kphi3"
SCENES = ["title", "sparsity", "equivalence", "method", "setup", "params", "loss", "conclusion"]
BEATS_PER_SCENE = [2, 4, 3, 5, 4, 3, 3, 3]


def test_example_validates_with_custom_scene_types_only() -> None:
    project = Project.load(EXAMPLE)
    assert check_project(project) == []
    assert [s.id for s in project.config.scenes] == SCENES
    assert [len(s.beats) for s in project.config.scenes] == BEATS_PER_SCENE
    assert all(s.type.startswith("kphi_") for s in project.config.scenes)
    # beat ids kept from the original script.json, so the committed MP3s match
    assert [b.id for _, b in project.beats()] == [f"s{i}_b{j}" for i, n in enumerate(BEATS_PER_SCENE, 1) for j in range(1, n + 1)]


def test_committed_audio_is_up_to_date(capsys: pytest.CaptureFixture[str]) -> None:
    project = Project.load(EXAMPLE)
    statuses = tts.audio_status(project)
    assert len(statuses) == 27 and {s.state for s in statuses} == {"ok"}
    assert tts.orphaned_audio(project) == []
    assert main(["tts", str(EXAMPLE), "--dry-run"]) == 0
    assert "dry run: 0 beat(s) to generate, 0 characters; 27 up to date" in capsys.readouterr().out


def tiny_copy(tmp_path: Path) -> Path:
    """The example without renders, with a 160x90 @ 5 fps preview format."""
    root = tmp_path / "kphi3"
    shutil.copytree(EXAMPLE / "extensions", root / "extensions", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(EXAMPLE / "audio", root / "audio")
    data = yaml.safe_load((EXAMPLE / "video.yaml").read_text(encoding="utf-8"))
    data["preview"] = {"width": 160, "height": 90, "fps": 5}
    (root / "video.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return root


@pytest.mark.render
@pytest.mark.parametrize("scene_id", ["title", "params"])
def test_kphi_scene_beats_last_audio_plus_pad(tmp_path: Path, scene_id: str) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not found on PATH")
    root = tiny_copy(tmp_path)
    subprocess.run(
        [sys.executable, "-m", "vidgen.render.worker", str(root), scene_id, "--quality", "preview", "--no-audio"],
        check=True,
        capture_output=True,
    )
    project = Project.load(root)
    timings = json.loads((project.render_dir(True) / "timings" / f"{scene_id}.json").read_text(encoding="utf-8"))
    spec = project.scene(scene_id)
    pad, frame = project.config.narration.pad, 1 / 5
    assert [b["id"] for b in timings["beats"]] == [b.id for b in spec.beats]
    starts = [b["start"] for b in timings["beats"]]
    assert starts[0] == 0
    for beat, entry, next_start in zip(spec.beats, timings["beats"], starts[1:]):
        d = audio_duration(root / "audio" / f"{beat.id}.mp3")
        assert entry["end"] - entry["start"] == pytest.approx(d, abs=1e-6)
        # the kphi scenes' animations fit inside every beat, so each beat lasts d + pad
        assert next_start - entry["start"] == pytest.approx(d + pad, abs=frame / 2 + 1e-6)
    assert (project.render_dir(True) / "scenes" / f"{scene_id}.mp4").is_file()
