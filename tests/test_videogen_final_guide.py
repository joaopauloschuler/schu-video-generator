"""A shot that sends the beat's finished render and the film's sound (DESIGN.md §113.18):
``guide: final`` (the scene rendered without overlays or placed takes, into ``build/final_source``)
and ``audio: mix`` (the rendered film's sound over the shot). Nothing renders or is sent: the
scene render is a stub, the film a small clip, the model list the fixture."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import minimal_config, write_clip

from vidgen.config import GeneratedShot
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen.compose import scene_placements
from vidgen.videogen.inputs import SceneRender, make_inputs, render_project
from vidgen.videogen.models import guide_opening_template
from vidgen.videogen.shots import GUIDE_PROMPTS, MIX_PROMPT, plan_shots, project_shots
from vidgen.videogen.takes import add_take, pick_take
from test_videogen_shots import CATALOG

MODEL = "bytedance/seedance-2.0-fast"


def quiet(_line: str) -> None:
    """An ``out`` that prints nothing."""


def config(**spec: Any) -> dict[str, Any]:
    """A project with one ``text_card`` scene whose beat ``a`` is a generated shot of ``spec``."""
    shot = {"kind": "establishing", "model": MODEL, "prompt": "a glider over the peaks", "guide": "final", "audio": "mix", **spec}
    return minimal_config(
        format={"width": 320, "height": 180, "fps": 10}, draft={"width": 160, "height": 90, "fps": 5},
        videogen={"provider": "mock", "budget_usd": 2.0},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"}, "beats": [{"id": "a", "text": "The glider holds its line.", "generated_shot": shot}]}],
    )


def stub_render(root: Path, kinds: list[str]) -> Callable[..., SceneRender]:
    """A ``render=`` hook noting the kind of each render asked for."""
    video = write_clip(root / "fake" / "scene.mp4", seconds=6.0, size="32x18", fps=5, audio=False)

    def render(_project: Project, _scene: str, _passes: tuple[str, ...], kind: str = "render") -> SceneRender:
        kinds.append(kind)
        return SceneRender(video, {"a": 0.5})

    return render


def fake_film(project: Project, start: float = 1.0) -> Path:
    """A rendered film (a clip with a tone) and its timings, beat ``a`` at ``start`` seconds."""
    film = write_clip(project.output_path(False), seconds=8.0, size="32x18", fps=5, audio=True)
    timings = project.render_dir(False) / "timings.json"
    timings.parent.mkdir(parents=True, exist_ok=True)
    timings.write_text(json.dumps({"scenes": [{"id": "s1", "beats": [{"id": "a", "start": start}]}]}), encoding="utf-8")
    return film


def blocked_by_change(project: Project) -> str:
    shot = plan_shots(project, catalog=CATALOG).shots[0].shot
    return next((b for b in shot.blocked if b.startswith("inputs changed")), "")


def test_final_and_mix_are_accepted_on_any_scene_and_mix_is_not_a_talking_voice() -> None:
    spec = GeneratedShot(kind="establishing", model=MODEL, guide="final", audio="mix")
    assert spec.guide_source == "final" and spec.audio_source == "mix" and spec.wants_audio
    with pytest.raises(ValueError, match="lip-synced to the beat's voice alone"):
        GeneratedShot(kind="talking", model=MODEL, audio="mix")
    with pytest.raises(ValueError, match="did you mean final"):
        GeneratedShot(kind="action", model=MODEL, guide="finale")


@pytest.mark.slow
def test_a_project_without_takes_renders_into_its_own_folder_without_overlays(make_project) -> None:
    project = Project.load(make_project(config()))
    source = project.without_takes()
    assert source.render_dir(False).name == "final_source" and not source.takes_shown and not source.bare
    assert source.config.overlays == [] and all(s.overlays is False for s in source.config.scenes)
    assert project.takes_shown and project.render_dir(False).name == "final"
    assert render_project(project, "final", "s1").render_dir(False).name == "final"   # nothing drawn over it: the film's own render
    with_overlay = Project.load(make_project(minimal_config(overlays=[{"type": "watermark", "text": "DRAFT"}], scenes=config()["scenes"])))
    assert render_project(with_overlay, "final", "s1").render_dir(False).name == "final_source"




@pytest.mark.slow
def test_a_picked_take_is_not_laid_into_the_render_without_takes(make_project, tmp_path: Path) -> None:
    root = make_project(config(place=True))
    assert render_project(Project.load(root), "final", "s1").render_dir(False).name == "final"
    take = write_clip(tmp_path / "take.mp4", seconds=3.0, size="64x36", fps=5, audio=False)
    add_take(root, "a", take, key="k1", model=MODEL, provider="mock", job_id="j", cost=0.1, length=2.0, width=320, height=180)
    pick_take(root, "a", "1", ["a"])
    project = Project.load(root)
    assert scene_placements(project, "s1") and scene_placements(project.without_takes(), "s1") == []
    assert render_project(project, "final", "s1").render_dir(False).name == "final_source"   # the take is in the film's render now


def test_the_plan_names_the_finished_render_and_the_films_sound_and_the_prompt_says_what_they_are(make_project) -> None:
    project = Project.load(make_project(config()))
    shot = project_shots(project, CATALOG)[0]
    inputs = {i.role: i for i in shot.inputs}
    assert inputs["guide"].path.name == "guide.final.mp4" and "silent finished render" in inputs["guide"].what
    assert inputs["audio"].path.name == "audio.mp3" and "the film's sound" in inputs["audio"].what
    assert GUIDE_PROMPTS["final"] in shot.prompt and MIX_PROMPT in shot.prompt


def test_in_the_guide_the_role_sentences_name_the_finished_render_and_the_soundtrack(make_project, tmp_path: Path) -> None:
    picture = write_clip(tmp_path / "x.mp4", seconds=1.0)   # any file: only the plan is made
    root = make_project(config(first_frame="start.png", first_frame_in="guide"))
    (root / "start.png").write_bytes(picture.read_bytes())
    shot = project_shots(Project.load(root), CATALOG)[0]
    template = guide_opening_template(MODEL)
    assert template is not None
    assert shot.prompt.startswith(template.opens_final.format(video="@video1"))
    assert template.soundtrack.format(audio="@audio1") in shot.prompt and MIX_PROMPT not in shot.prompt


def test_audio_mix_needs_the_rendered_film(make_project) -> None:
    project = Project.load(make_project(config(guide=False)))
    with pytest.raises(VidgenError, match="run `vidgen render` first"):
        make_inputs(project, project_shots(project, CATALOG), out=quiet)


@pytest.mark.slow
def test_the_films_sound_is_cut_at_the_beat_and_a_new_film_asks_for_a_new_cut(make_project) -> None:
    from vidgen.speech import audio_duration

    project = Project.load(make_project(config(guide=False)))
    film = fake_film(project, start=1.0)
    lines: list[str] = []
    make_inputs(project, project_shots(project, CATALOG), out=lines.append)
    shot = project_shots(project, CATALOG)[0]
    cut = project.root / "build" / "videogen" / "a" / "audio.mp3"
    assert abs(audio_duration(cut) - shot.length) < 0.1 and "from 1.00 s of" in lines[0]
    assert blocked_by_change(project) == ""
    os.utime(film, ns=(film.stat().st_atime_ns, film.stat().st_mtime_ns + 10**9))   # rendered again
    assert "audio.mp3: the rendered film changed" in blocked_by_change(project)


@pytest.mark.slow
def test_the_finished_render_is_cut_as_the_guide_and_recorded_against_it(make_project) -> None:
    project = Project.load(make_project(config(audio="none", first_frame="render")))
    kinds: list[str] = []
    written = make_inputs(project, project_shots(project, CATALOG), guide=True, out=quiet, render=stub_render(project.root, kinds))
    assert kinds == ["final"] and {p.name for p in written} >= {"guide.final.mp4", "first_frame.png"}
    record = json.loads((project.root / "build" / "videogen" / "a" / "inputs.json").read_text(encoding="utf-8"))["inputs"]
    assert record["guide.final.mp4"]["source"]["guide"] == "final" == record["first_frame.png"]["source"]["guide"]
    assert record["guide.final.mp4"]["source"]["draft"] == [320, 180, 10]   # the video's own size, not the draft's
    assert blocked_by_change(project) == ""
