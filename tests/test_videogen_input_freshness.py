"""Cut inputs that no longer match what they were cut from (DESIGN.md §113.9): the record beside
them, the plan's block, the refusal of ``run --pay``, free reuse of a cached clip. Nothing is sent
or paid, nothing renders: the scene render is a stub, the provider the mock."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import minimal_config, write_clip

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.videogen.freshness import RECORD_NAME
from vidgen.videogen.inputs import SceneRender, make_inputs
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
from vidgen.videogen.shots import ShotPlan, inputs_command, plan_shots, project_shots
from vidgen.videogen.takes import add_take, pick_take
from vidgen.videogen.workflow import run_shots
from test_videogen_3d_guide import guide_config, lossless_clip
from test_videogen_host import fake_cloudflared  # noqa: F401 - the fixture
from test_videogen_shots import CATALOG, tone

MODEL = "bytedance/seedance-2.0-fast"
VOICE_RECUT = "`vidgen generate inputs` (free)"
GUIDE_RECUT = "`vidgen generate inputs --guide` (free)"


def quiet(_line: str) -> None:
    """An ``out`` that prints nothing."""


def shot_of(beat: str, **spec: Any) -> dict[str, Any]:
    return {"id": beat, "text": f"The words of {beat} are here.", "generated_shot": {"kind": "action", "model": MODEL, **spec}}


def config(*beats: dict[str, Any], **videogen: Any) -> dict[str, Any]:
    """A 16:9 project with one ``text_card`` scene of ``beats`` and no sheets."""
    return minimal_config(
        format={"width": 320, "height": 180, "fps": 10}, draft={"width": 160, "height": 90, "fps": 5},
        videogen={"provider": "mock", "budget_usd": 2.0, **videogen},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"}, "beats": list(beats)}],
    )


def edit(root: Path, change: Callable[[dict[str, Any]], None]) -> None:
    """Change ``video.yaml`` by ``change``."""
    path = root / "video.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def stub_render(root: Path, seconds: float = 8.0, beats: dict[str, float] | None = None, passes: tuple[str, ...] = ()) -> Callable[..., SceneRender]:
    """A ``render=`` hook: a small clip for the scene (and lossless ones for ``passes``)."""
    video = write_clip(root / "fake" / "scene.mp4", seconds=seconds, size="32x18", fps=5, audio=False)
    lossless = {p: lossless_clip(root / "fake" / f"{p}.mkv", seconds, "32x18", 5) for p in passes}
    return lambda _project, _scene, _passes: SceneRender(video, beats or {"a": 0.0, "b": 2.0, "act": 1.0}, lossless)


def plan_of(root: Path, shot: str | None = None) -> ShotPlan:
    plan = plan_shots(Project.load(root), catalog=CATALOG, shot_ids=(shot,) if shot else ())
    return plan.shots[0]


def changed(item: ShotPlan) -> str:
    """The shot's blocked text about changed inputs (``""``: none)."""
    return next((b for b in item.shot.blocked if b.startswith("inputs changed")), "")


def cut(root: Path, guide: bool = False, render: Callable[..., SceneRender] | None = None) -> None:
    """``vidgen generate inputs`` on the project as it is now."""
    project = Project.load(root)
    make_inputs(project, project_shots(project, CATALOG), guide=guide, out=quiet, render=render)


def voice_project(make_project) -> Path:
    root = make_project(config(shot_of("a", audio="beat")))
    tone(root / "audio" / "a.mp3", 2.0)
    return root


@pytest.mark.slow
def test_a_new_cut_is_current_and_the_record_says_what_it_was_made_from(make_project) -> None:
    root = voice_project(make_project)
    cut(root)
    assert changed(plan_of(root)) == ""
    doc = json.loads((root / "build" / "videogen" / "a" / RECORD_NAME).read_text(encoding="utf-8"))
    entry = doc["inputs"]["audio.mp3"]
    assert doc["version"] == 1 and set(entry) == {"sha256", "source"} and set(entry["source"]) == {"narration_sha256", "offset", "length"}


@pytest.mark.slow
def test_edited_narration_blocks_and_a_recut_clears_it(make_project) -> None:
    root = voice_project(make_project)
    cut(root)
    tone(root / "audio" / "a.mp3", 2.6)   # another take of the line
    item = plan_of(root)
    assert "audio.mp3: the beat's narration MP3 changed" in changed(item) and VOICE_RECUT in changed(item)
    cut(root)
    assert changed(plan_of(root)) == ""


@pytest.mark.slow
def test_narration_text_edited_without_tts_asks_for_tts_first(make_project) -> None:
    from vidgen.tts import beat_providers

    root = voice_project(make_project)
    project = Project.load(root)
    (root / "audio" / "a.hash").write_text(beat_providers(project)["a"].cache_key(project.spoken_texts()["a"]), encoding="utf-8")
    cut(root)
    assert changed(plan_of(root)) == ""   # the MP3 belongs to its text
    edit(root, lambda d: d["scenes"][0]["beats"][0].update(text="Completely different words now."))
    item = plan_of(root)
    assert "does not match its text or voice" in changed(item) and "`vidgen tts` for the beat's voice, then `vidgen generate inputs` (free)" in changed(item)
    cut(root)   # cutting the old MP3 again does not help
    assert "`vidgen tts`" in changed(plan_of(root))
    project = Project.load(root)
    tone(root / "audio" / "a.mp3", 2.4)
    (root / "audio" / "a.hash").write_text(beat_providers(project)["a"].cache_key(project.spoken_texts()["a"]), encoding="utf-8")
    assert "the beat's narration MP3 changed" in changed(plan_of(root))
    cut(root)
    assert changed(plan_of(root)) == ""


def test_a_deleted_narration_mp3_blocks_with_tts(make_project) -> None:
    root = voice_project(make_project)
    cut(root)
    (root / "audio" / "a.mp3").unlink()
    assert "`vidgen tts`" in changed(plan_of(root)) and "no narration MP3" in changed(plan_of(root))


def test_no_record_blocks_with_the_same_recut(make_project) -> None:
    root = voice_project(make_project)
    cut(root)
    record = root / "build" / "videogen" / "a" / RECORD_NAME
    record.unlink()   # as cut by an older vidgen
    item = plan_of(root)
    assert "no record of what it was cut from" in changed(item) and VOICE_RECUT in changed(item)
    record.write_text("not json", encoding="utf-8")
    assert "no record" in changed(plan_of(root))
    cut(root)
    assert changed(plan_of(root)) == ""


def test_a_file_changed_after_its_cut_blocks(make_project) -> None:
    root = voice_project(make_project)
    cut(root)
    (root / "build" / "videogen" / "a" / "audio.mp3").write_bytes(b"something else")
    assert "the file was changed after it was cut" in changed(plan_of(root))


@pytest.mark.slow
def test_guide_shot_edited_beat_or_scene_blocks_with_guide_and_a_recut_clears(make_project) -> None:
    root = make_project(config(shot_of("a", guide=True, first_frame="render"), shot_of("b", first_frame="render")))
    render = stub_render(root)
    cut(root, guide=True, render=render)
    assert changed(plan_of(root, "a")) == ""
    edit(root, lambda d: d["scenes"][0]["beats"][1].update(text="The other beat has new words today."))   # same scene
    for shot in ("a", "b"):
        item = plan_of(root, shot)
        assert "first_frame.png: the scene changed" in changed(item) and GUIDE_RECUT in changed(item)
    assert "guide.mp4: the scene changed" in changed(plan_of(root, "a"))
    edit(root, lambda d: d["scenes"][0]["params"].update(text="another card"))
    cut(root, guide=True, render=render)
    assert changed(plan_of(root, "a")) == "" and changed(plan_of(root, "b")) == ""


@pytest.mark.slow
def test_voice_recut_without_guide_leaves_the_guide_record(make_project) -> None:
    root = make_project(config(shot_of("a", audio="beat", guide=True)))
    tone(root / "audio" / "a.mp3", 2.0)
    cut(root, guide=True, render=stub_render(root))
    assert changed(plan_of(root)) == ""
    cut(root)   # only the voice this time: guide.mp4's record stays
    assert changed(plan_of(root)) == ""


def test_shot_prompt_edit_does_not_block(make_project) -> None:
    root = voice_project(make_project)
    cut(root)
    edit(root, lambda d: d["scenes"][0]["beats"][0]["generated_shot"].update(prompt="a brand new prompt", seed=7))
    assert changed(plan_of(root)) == ""


@pytest.mark.slow
def test_draft_size_change_blocks_a_guide(make_project) -> None:
    root = make_project(config(shot_of("a", guide=True)))
    cut(root, guide=True, render=stub_render(root))
    edit(root, lambda d: d.update(draft={"width": 80, "height": 46, "fps": 5}))
    assert "guide.mp4: the draft's size or frame rate changed" in changed(plan_of(root))


@pytest.mark.slow
def test_3d_params_edit_blocks_and_the_guide_choice_is_recorded(make_project) -> None:
    root = make_project(guide_config("depth"))
    render = stub_render(root, beats={"act": 1.0}, passes=("depth", "outline"))
    cut(root, guide=True, render=render)
    assert changed(plan_of(root)) == ""
    edit(root, lambda d: d["scenes"][0]["params"]["camera"].update(position=[1, 2.5, 6]))
    assert "guide.depth.mp4: the scene changed" in changed(plan_of(root)) and GUIDE_RECUT in changed(plan_of(root))
    edit(root, lambda d: d["scenes"][0]["beats"][0]["generated_shot"].update(guide="outline"))
    item = plan_of(root)
    assert "inputs not made yet: `vidgen generate inputs --guide`" in item.shot.blocked and changed(item) == ""
    cut(root, guide=True, render=render)
    assert changed(plan_of(root)) == ""
    edit(root, lambda d: d["scenes"][0]["beats"][0]["generated_shot"].update(guide="depth"))
    assert "guide.depth.mp4: the scene changed" in changed(plan_of(root))   # the depth file was cut before the camera moved


@pytest.mark.slow
def test_picking_a_take_does_not_block_other_shots(make_project, tmp_path: Path) -> None:
    root = make_project(config(shot_of("a", guide=True), shot_of("b", guide=True)))
    cut(root, guide=True, render=stub_render(root))
    before = scene_fingerprint(Project.load(root), "s1")
    take = write_clip(tmp_path / "take.mp4", seconds=4.0, size="64x36", fps=5, audio=False)
    add_take(root, "b", take, key="k1", model=MODEL, provider="mock", job_id="j", cost=0.1, length=2.0, width=320, height=180)
    pick_take(root, "b", "1", ["a", "b"])
    assert scene_fingerprint(Project.load(root), "s1") != before   # the final render's fingerprint does change
    assert changed(plan_of(root, "a")) == "" and changed(plan_of(root, "b")) == ""


@pytest.mark.slow
def test_plan_text_and_json_show_the_block(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = voice_project(make_project)
    cut(root)
    tone(root / "audio" / "a.mp3", 2.6)
    monkeypatch.setattr("vidgen.videogen.models.load_catalog", lambda *a, **k: CATALOG)
    assert cli.main(["generate", "plan", str(root)]) == 0
    assert "blocked: inputs changed since they were cut" in capsys.readouterr().out
    assert cli.main(["generate", "plan", str(root), "--json"]) == 0
    (doc,) = json.loads(capsys.readouterr().out)["shots"]
    assert any(VOICE_RECUT in b for b in doc["blocked"])


def test_run_pay_refuses_before_submit_or_tunnel(make_project, fake_cloudflared: list[str]) -> None:  # noqa: F811
    root = make_project(config(shot_of("a", audio="beat"), host="quick_tunnel", cloudflared=fake_cloudflared[1]))
    tone(root / "audio" / "a.mp3", 2.0)
    cut(root)
    tone(root / "audio" / "a.mp3", 2.6)

    class NoShare:
        def host(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("a tunnel was opened")

    api = MockOpenRouter()
    with pytest.raises(VidgenError, match=r"(?s)not paying: inputs changed since they were cut \(nothing was sent or paid\).*a: inputs changed.*generate inputs"):
        run_shots(Project.load(root), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, share=NoShare(), out=quiet)  # type: ignore[arg-type]
    assert api.submits == []
    lines: list[str] = []
    report = run_shots(Project.load(root), provider=MockVideoProvider(api), catalog=CATALOG, share=NoShare(), out=lines.append)  # type: ignore[arg-type]
    assert report.shots[0].status == "blocked" and "inputs changed" in report.shots[0].message and any("blocked" in line for line in lines)


@pytest.mark.slow
def test_a_paid_request_is_reused_free_with_a_note_and_a_recut_is_a_new_request(make_project) -> None:
    root = make_project(config(shot_of("a", first_frame="render")))
    render = stub_render(root)
    cut(root, guide=True, render=render)
    api = MockOpenRouter()
    report = run_shots(Project.load(root), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=quiet)
    assert report.shots[0].status == "paid" and len(api.submits) == 1
    edit(root, lambda d: d["scenes"][0]["params"].update(text="edited after the job"))
    item = plan_of(root)
    assert item.cached and changed(item) == "" and item.changed_inputs is None
    assert any("reused free" in n and "generate inputs --guide" in n for n in item.shot.notes)
    report = run_shots(Project.load(root), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=quiet)
    assert report.shots[0].status == "cached" and len(api.submits) == 1   # nothing refused, nothing paid
    cut(root, guide=True, render=stub_render(root, beats={"a": 1.0}))   # the scene really looks different now
    item = plan_of(root)
    assert not item.cached and changed(item) == "" and not any("reused free" in n for n in item.shot.notes)


@pytest.mark.slow
def test_an_earlier_job_is_not_blocked_either(make_project) -> None:
    root = make_project(config(shot_of("a", first_frame="render")))
    cut(root, guide=True, render=stub_render(root))
    api = MockOpenRouter()
    run_shots(Project.load(root), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=quiet)
    shutil.rmtree(root / "assets" / "generated_video")   # the clip is gone, the job is in the ledger
    edit(root, lambda d: d["scenes"][0]["params"].update(text="edited"))
    item = plan_of(root)
    assert item.previous_job and changed(item) == "" and any("reused free" in n for n in item.shot.notes)


@pytest.mark.slow
@pytest.mark.render
def test_a_real_draft_render_is_current_until_the_scene_is_edited(make_project) -> None:
    """The worker's recorded fingerprint is the one the plan computes."""
    root = make_project(config(shot_of("a", guide=True)))
    cut(root, guide=True)
    record = json.loads((root / "build" / "videogen" / "a" / RECORD_NAME).read_text(encoding="utf-8"))
    assert set(record["inputs"]) == {"guide.mp4", "first_frame.png"} and changed(plan_of(root)) == ""
    edit(root, lambda d: d["scenes"][0]["params"].update(text="edited"))
    assert GUIDE_RECUT in changed(plan_of(root))


def test_inputs_command_names_the_variant(make_project) -> None:
    root = make_project(config(shot_of("a", guide=True)))
    assert inputs_command(Project.load(root), True) == "vidgen generate inputs --guide"
    project = Project.load(root)
    project.variant = "vertical"
    assert inputs_command(project, False) == "vidgen generate inputs --variant vertical"
