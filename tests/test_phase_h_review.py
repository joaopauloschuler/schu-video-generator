"""Review of Phase H (Step 88): `examples/cartoon` end to end with a fake Kokoro — `vidgen tts`
(MP3s and lip sync tracks), `validate`, `storyboard` with mid-action stills, `lint`,
`character-sheet` and a preview render with foley — at 160x90, 5 fps; and the JSON Schema of
`stage` accepting the bare names `vidgen validate` accepts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from test_schema import builtin_schema, errors  # noqa: F401  (builtin_schema is a fixture)
from test_tts_kokoro import Factory, fake  # noqa: F401  (fake is a fixture)
from vidgen.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "cartoon" / "video.yaml"
TINY = {"format": {"width": 160, "height": 90, "fps": 5}, "preview": {"width": 160, "height": 90, "fps": 5}}
CARTOON_RULES = {"walk_overlap", "off_stage", "character_overlap", "bubble_overlap", "facing_away", "hidden_speaker", "mouth_without_voice"}


def json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def example_copy(root: Path) -> Path:
    """``examples/cartoon`` as a project in ``root``, at 160x90 and 5 fps."""
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data.update(TINY)
    root.mkdir(parents=True, exist_ok=True)
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return root


# ----- the stage's JSON Schema takes bare names ------------------------------------------------------


def stage_config(**params: Any) -> dict[str, Any]:
    return {
        "title": "T",
        "characters": [{"name": "pip"}],
        "scenes": [{"id": "s", "type": "stage", "params": params, "beats": [{"text": "Hi there."}]}],
    }


def test_stage_schema_accepts_bare_names(builtin_schema: dict[str, Any]) -> None:  # noqa: F811
    bare = stage_config(characters=["pip"], props=["cloud", {"prop": "tree", "at": 0.8}], particles=["snow"])
    assert errors(builtin_schema, bare) == []
    assert errors(builtin_schema, stage_config(props=["clowd"]))   # not a built-in prop
    assert errors(builtin_schema, stage_config(particles=["hail"]))
    assert errors(builtin_schema, stage_config(characters=["no spaces"]))


def test_example_uses_a_bare_prop_name() -> None:
    props = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))["scenes"][0]["params"]["props"]
    assert "cloud" in props


# ----- the example end to end ---------------------------------------------------------------------------


def test_example_voices_and_lip_sync_tracks(tmp_path: Path, fake: Factory, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    root = example_copy(tmp_path / "cartoon")
    assert main(["validate", str(root), "--json"]) == 0
    doc = json_out(capsys)
    assert doc["ok"] and doc["scenes"] == 2 and doc["beats"] == 12
    assert main(["tts", str(root)]) == 0
    assert "done: 12 beat(s) generated" in capsys.readouterr().out
    audio = root / "audio"
    beats = sorted(p.stem for p in audio.glob("*.mp3"))
    assert len(beats) == 12 and sorted(p.name.split(".")[0] for p in audio.glob("*.visemes.json")) == beats
    track = json.loads((audio / "yard_box.visemes.json").read_text(encoding="utf-8"))
    assert track["timing"] == "alignment"   # the fake's tokens carry times but no phonemes
    assert {c[2] for c in track["cues"]} - {"rest"}
    voices = {c["voice"] for p in fake.made for c in p.calls}
    assert voices == {"bf_emma", "af_bella", "am_michael"}


@pytest.mark.render
@pytest.mark.slow
def test_example_storyboard_lint_sheets_and_render(tmp_path: Path, fake: Factory, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    root = example_copy(tmp_path / "cartoon")
    assert main(["tts", str(root)]) == 0
    capsys.readouterr()

    assert main(["storyboard", str(root), "--json"]) == 0
    doc = json_out(capsys)
    video_sheets = [s for s in doc["sheets"] if s["kind"] == "video"]
    mids = sorted(f["mid"] for s in video_sheets for f in s["frames"] if f.get("mid"))
    assert mids == ["enter dot", "gesture dot", "jump dot", "jump moss", "move_along kite", "walk_to dot"]

    assert main(["lint", str(root), "--fail-on", "never", "--json"]) == 0
    doc = json_out(capsys)
    assert doc["stills"] == 12 and doc["rendered"] == []   # the storyboard's renders reused
    assert not [f for f in doc["findings"] if f["rule"] in CARTOON_RULES]

    assert main(["character-sheet", "--all", str(root), "--json"]) == 0
    doc = json_out(capsys)
    assert [s["character"] for s in doc["sheets"]] == ["dot", "moss"]
    assert all(Path(s["path"]).is_file() for s in doc["sheets"])

    assert main(["render", str(root), "--preview", "--json"]) == 0
    doc = json_out(capsys)
    assert doc["audio"] is True and Path(doc["outputs"]["video"]).is_file()
    sounds = set()
    for scene in ("yard", "hill"):
        timings = json.loads((root / "build" / "preview" / "timings" / f"{scene}.json").read_text(encoding="utf-8"))
        sounds |= {e["sound"] for e in timings["sfx"]}
    assert {"footstep", "whoosh", "boing", "pop"} <= sounds
