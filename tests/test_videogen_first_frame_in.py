"""``first_frame_in`` (DESIGN.md §113.13): the starting picture spliced into the guide video, the
role sentence, the block on a first frame plus references for a model known to separate the modes,
and the warning about hosted files the provider never downloaded. Nothing is sent or paid."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import write_clip
from PIL import Image
from test_videogen import FAST, request, settings
from test_videogen_3d_guide import guide_config
from test_videogen_host import SETTINGS, HostedStandIn, fake_cloudflared, local_fetch, sources  # noqa: F401 - the fixture
from test_videogen_input_freshness import changed, edit, plan_of, stub_render
from test_videogen_shots import CATALOG, png_bytes, tone

from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.render.ffmpeg import decode_gray_frames, find_ffmpeg, probe
from vidgen.videogen import MediaInput
from vidgen.videogen.host import ShareOptions
from vidgen.videogen.inputs import make_inputs, make_opening_guide
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
from vidgen.videogen.openrouter import Response
from vidgen.videogen.run import generate_clip, unfetched_warnings
from vidgen.videogen.shots import project_shots
from vidgen.videogen.takes import add_take
from vidgen.videogen.workflow import run_shots

VEO = "google/veo-3.1-lite"
OPENS = "@video1 opens on the exact starting picture of this scene"


def picture_file(root: Path, name: str = "assets/start.png") -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes("start"))
    return name


def in_guide_project(make_project, folder: str = "p", model: str | None = None, **shot: Any) -> Path:
    """A depth-guided action shot of Ana with ``first_frame_in: guide`` and a picture file."""
    data = guide_config("depth", first_frame_in="guide", first_frame="assets/start.png", **shot)
    if model:
        data["scenes"][0]["beats"][0]["generated_shot"]["model"] = model
    root = make_project(data, folder=folder)
    picture_file(root)
    return root


def the_shot(root: Path) -> Any:
    (shot,) = project_shots(Project.load(root), CATALOG)
    return shot


# ----- the setting ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shot_value", "model_value", "default", "expected"),
    [(None, None, "frame", "frame"), (None, None, "guide", "guide"), (None, "guide", "frame", "guide"), ("frame", "guide", "guide", "frame")],
)
def test_first_frame_in_precedence_like_sound(shot_value: str | None, model_value: str | None, default: str, expected: str) -> None:
    from vidgen.config import VideogenConfig

    videogen = VideogenConfig(first_frame_in=default, models={FAST: {"first_frame_in": model_value}})
    assert videogen.first_frame_in_for(FAST, shot_value) == expected
    assert VideogenConfig().first_frame_in_for(FAST) == "frame"


def test_guide_mode_sends_the_combined_guide_and_no_frame_image(make_project) -> None:
    shot = the_shot(in_guide_project(make_project))
    assert shot.first_frame_in == "guide" and shot.opening_picture is not None and shot.opening_picture.name == "start.png"
    assert not any(i.frame for i in shot.inputs) and shot.opening_dissolve_seconds == 0.4
    (guide,) = [i for i in shot.inputs if i.role == "guide"]
    assert guide.path.name == "guide.depth.opening.mp4" and "opening on your picture" in guide.what
    request_ = shot.request()
    assert request_ is not None and not request_.frame_images


def test_the_default_keeps_a_frame_shot_as_it_was(make_project) -> None:
    root = make_project(guide_config("depth"), folder="plain")
    (shot,) = project_shots(Project.load(root), CATALOG)
    assert shot.first_frame_in == "frame" and shot.opening_picture is None
    assert not any("opening" in i.path.name for i in shot.inputs) and "@video" not in shot.prompt


def test_guide_mode_keeps_the_first_frame_picture_available_as_a_reference(make_project) -> None:
    root = in_guide_project(make_project)
    edit(root, lambda data: data["scenes"][0]["beats"][0]["generated_shot"].update(first_frame="sheet", refs=["ana"]))
    shot = the_shot(root)
    assert shot.opening_picture is not None and any(i.path == shot.opening_picture and i.owner == "ana" for i in shot.inputs)


@pytest.mark.parametrize(
    ("change", "text"),
    [
        ({"guide": False}, "first_frame_in: guide needs a guide video"),
        ({"first_frame": None}, "first_frame_in: guide needs a starting picture"),
        ({"first_frame": "none"}, "first_frame_in: guide needs a starting picture"),
    ],
)
def test_guide_mode_needs_a_guide_and_a_picture(make_project, change: dict[str, Any], text: str) -> None:
    root = in_guide_project(make_project)
    edit(root, lambda data: data["scenes"][0]["beats"][0]["generated_shot"].update(change))
    shot = the_shot(root)
    assert any(text in p for p in shot.problems), shot.problems


def test_first_frame_in_can_come_from_the_model_entry(make_project) -> None:
    data = guide_config("depth", first_frame="assets/start.png")
    data["videogen"]["models"] = {FAST: {"first_frame_in": "guide"}}
    root = make_project(data, folder="by_model")
    picture_file(root)
    assert the_shot(root).first_frame_in == "guide"


# ----- the combined guide --------------------------------------------------------------------------


def test_the_combined_guide_is_as_long_as_the_guide_and_starts_on_the_picture(tmp_path: Path) -> None:
    guide = write_clip(tmp_path / "guide.mp4", seconds=2.0, size="54x96", fps=5, audio=False)
    picture = tmp_path / "white.png"
    Image.new("RGB", (64, 96), (255, 255, 255)).save(picture)
    dest = tmp_path / "out" / "guide.opening.mp4"
    make_opening_guide(find_ffmpeg(), picture, guide, dest, 0.4)
    info, plain = probe(dest), probe(guide)
    assert (info.width, info.height, info.fps) == (plain.width, plain.height, plain.fps)
    assert info.duration == pytest.approx(plain.duration, abs=1e-3)   # a whole number of frames: exactly as long
    frames = decode_gray_frames(dest, 32, 5.0, plain.duration)
    assert frames[0].mean() > 200   # the first frame is the (white) picture
    assert frames[-1].mean() < frames[0].mean() - 30   # the guide takes over


def test_a_dissolve_longer_than_the_guide_never_lengthens_it(tmp_path: Path) -> None:
    guide = write_clip(tmp_path / "g.mp4", seconds=0.6, size="32x18", fps=5, audio=False)
    picture = tmp_path / "p.png"
    Image.new("RGB", (32, 18), (0, 0, 0)).save(picture)
    dest = tmp_path / "opening.mp4"
    make_opening_guide(find_ffmpeg(), picture, guide, dest, 1.5)
    assert probe(dest).duration <= probe(guide).duration + 1e-6


# ----- the inputs and their freshness -------------------------------------------------------------


def in_guide_inputs(make_project) -> tuple[Path, Any]:
    root = in_guide_project(make_project)
    render = stub_render(root, passes=("depth",))
    project = Project.load(root)
    make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=render)
    return root, render


def test_make_inputs_makes_the_combined_guide_and_records_the_picture(make_project) -> None:
    root, _ = in_guide_inputs(make_project)
    folder = root / "build" / "videogen" / "act"
    assert (folder / "guide.depth.opening.mp4").is_file() and (folder / "guide.depth.mp4").is_file()
    assert changed(plan_of(root)) == ""
    item = plan_of(root)
    (guide,) = [i for i in item.shot.inputs if i.role == "guide"]
    assert guide.ready and any("starting picture: assets/start.png" in line and "dissolve" in line for line in item.lines(root))


def test_changing_the_picture_makes_the_guide_stale_and_a_recut_clears_it(make_project) -> None:
    root, render = in_guide_inputs(make_project)
    (root / "assets" / "start.png").write_bytes(png_bytes("another start"))
    item = plan_of(root)
    assert "guide.depth.opening.mp4: the starting picture changed" in changed(item) and "--guide" in changed(item)
    assert item.changed_inputs is not None   # a run cannot pay for it
    project = Project.load(root)
    make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=render)
    assert changed(plan_of(root)) == ""


def test_changing_the_dissolve_makes_the_guide_stale(make_project) -> None:
    root, _ = in_guide_inputs(make_project)
    edit(root, lambda data: data["videogen"].update(first_frame_dissolve=0.8))
    assert "guide.depth.opening.mp4: the dissolve length changed" in changed(plan_of(root))


def test_a_missing_starting_picture_is_named(make_project) -> None:
    root = in_guide_project(make_project)
    edit(root, lambda data: data["scenes"][0]["beats"][0]["generated_shot"].update(first_frame="sheet", refs=[]))
    render = stub_render(root, passes=("depth",))
    project = Project.load(root)
    with pytest.raises(VidgenError, match="the starting picture .* does not exist yet"):
        make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=render)


def test_a_first_frame_render_works_in_guide_mode(make_project) -> None:
    root = in_guide_project(make_project)
    edit(root, lambda data: data["scenes"][0]["beats"][0]["generated_shot"].update(first_frame="render"))
    project = Project.load(root)
    written = make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=stub_render(root, passes=("depth",)))
    assert sorted(p.name for p in written) == ["first_frame.png", "guide.depth.mp4", "guide.depth.opening.mp4", "overlay.png"]
    assert changed(plan_of(root)) == ""


# ----- the role sentence ---------------------------------------------------------------------------


def role_shot(make_project, folder: str = "role", model: str | None = None, **shot: Any) -> Any:
    root = in_guide_project(make_project, folder=folder, model=model, audio="beat", **shot)
    project = Project.load(root)
    tone(project.audio_dir / "act.mp3", 2.0)
    return project_shots(project, CATALOG)[0]


def test_the_role_sentence_follows_the_order_of_the_inputs(make_project) -> None:
    shot = role_shot(make_project)
    assert shot.prompt.startswith(OPENS)
    assert "follow the layout's positions and movement. @image1 shows Ana. @audio1 is the narrator's voice. " in shot.prompt, shot.prompt


def test_the_role_sentence_names_the_speaker(make_project) -> None:
    root = in_guide_project(make_project, folder="spoken", audio="beat")

    def give_voice(data: dict[str, Any]) -> None:
        data["voices"] = {"ana_voice": {"voice_id": "a"}}
        data["characters"][0]["voice"] = "ana_voice"
        data["scenes"][0]["voice"] = "ana_voice"

    edit(root, give_voice)
    assert "@image1 shows Ana. @audio1 is Ana's voice." in the_shot(root).prompt


def test_a_model_without_a_template_gets_no_sentence(make_project) -> None:
    shot = role_shot(make_project, folder="veo", model=VEO)
    assert "@video1" not in shot.prompt and "@audio1" not in shot.prompt


def test_a_frame_shot_prompt_is_untouched(make_project) -> None:
    root = make_project(guide_config("depth", first_frame="assets/start.png"), folder="frame")
    picture_file(root)
    shot = project_shots(Project.load(root), CATALOG)[0]
    assert "@" not in shot.prompt


def test_several_pictures_of_one_character_are_named_together(make_project) -> None:
    root = in_guide_project(make_project, folder="two", refs=["ana"])
    edit(root, lambda data: data["characters"][0]["reference_sheet"].update(views=["front", "side"]))
    prompt = the_shot(root).prompt
    assert "@image1 and @image2 show Ana." in prompt


# ----- the block on a first frame with references -------------------------------------------------


def frame_with_references_project(make_project, folder: str = "fr", **videogen: Any) -> Path:
    data = guide_config("depth", first_frame="assets/start.png")
    data["videogen"].update(videogen)
    root = make_project(data, folder=folder)
    picture_file(root)
    return root


def test_a_first_frame_with_references_is_a_problem_on_seedance(make_project) -> None:
    item = plan_of(frame_with_references_project(make_project))
    assert any("first_frame_in: guide" in p and "bytedance/seedance-2.0-fast" in p for p in item.shot.problems), item.shot.problems


def test_the_block_can_be_overridden_per_model(make_project) -> None:
    root = frame_with_references_project(make_project, folder="o", models={FAST: {"first_frame_with_references": True}})
    assert not plan_of(root).shot.problems


def test_no_block_for_a_model_with_no_evidence(make_project) -> None:
    data = guide_config("depth", first_frame="assets/start.png")
    data["scenes"][0]["beats"][0]["generated_shot"]["model"] = VEO
    root = make_project(data, folder="veo_plain")
    picture_file(root)
    assert not any("first_frame_in" in p for p in plan_of(root).shot.problems)


def test_a_paid_run_is_refused_by_the_block(make_project) -> None:
    root = frame_with_references_project(make_project)
    with pytest.raises(VidgenError, match="first_frame_in: guide"):
        run_shots(Project.load(root), pay=True, provider=MockVideoProvider(), catalog=CATALOG, out=lambda line: None)


def test_a_shot_already_paid_for_only_gets_a_note(make_project) -> None:
    root = frame_with_references_project(make_project, folder="paid")
    edit(root, lambda data: data["scenes"][0]["beats"][0]["generated_shot"].update(characters=[], refs=[]))
    project = Project.load(root)
    make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=stub_render(root, passes=("depth",)))
    from vidgen.videogen import request_hash
    from vidgen.videogen.run import clip_path

    item = plan_of(root)
    clip = clip_path(root, request_hash(item.request))
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"x")
    item = plan_of(root)
    assert item.cached and not any("first_frame_in" in p for p in item.shot.problems)
    assert any("first_frame_in: guide" in n and "already paid" in n for n in item.shot.notes)


def test_a_shot_paid_under_earlier_wording_only_gets_a_note(make_project) -> None:
    from dataclasses import replace

    from test_videogen_input_freshness import config as freshness_config
    from test_videogen_input_freshness import shot_of

    data = freshness_config(shot_of("a", guide=True, characters=["ana"], refs=[], first_frame="assets/start.png"))
    data["characters"] = [{"name": "ana", "reference_sheet": {"prompt": "Exactly one character, centred in the frame. A woman in red.", "views": ["front"]}}]
    root = make_project(data, folder="earlier")
    picture_file(root)
    project = Project.load(root)
    make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=stub_render(root))
    item = plan_of(root)
    assert item.shot.earlier_prompt
    generate_clip(root, Project.load(root).config.videogen, replace(item.request, prompt=item.shot.earlier_prompt), pay=True, provider=MockVideoProvider(), catalog=CATALOG)
    item = plan_of(root)
    assert not any("first_frame_in" in p for p in item.shot.problems) and any("first_frame_in: guide" in n for n in item.shot.notes)


# ----- what the provider really downloaded ----------------------------------------------------------


def test_unfetched_warning_counts_only_successful_gets() -> None:
    events = [
        {"event": "host_fetch", "file": "a.mp3", "method": "HEAD", "status": 200},
        {"event": "host_fetch", "file": "g.mp4", "method": "GET", "status": 206},
        {"event": "host_fetch", "file": "a.mp3", "method": "GET", "status": 404},
    ]
    assert unfetched_warnings(events, ["a.mp3", "g.mp4"], {"a.mp3": "audio", "g.mp4": "video"}) == [
        "the provider never downloaded the voice (vidgen hosted them for this job; the clip may not use them)"
    ]
    assert unfetched_warnings(events, ["g.mp4"], {"g.mp4": "video"}) == []


def _hosted_request(audio: Path, guide: Path) -> Any:
    return request(model=FAST, resolution="720p", references=(MediaInput("audio", audio), MediaInput("video", guide)))


def test_a_job_whose_files_were_never_downloaded_warns(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, guide = sources(tmp_path)
    share = ShareOptions(SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path))
    provider = HostedStandIn(MockOpenRouter(cost=0.2), sleep=lambda seconds: None)
    result = generate_clip(project, settings(host="quick_tunnel"), _hosted_request(audio, guide), pay=True, provider=provider, catalog=CATALOG, share=share)
    assert result.paid and result.warnings == ["the provider never downloaded the voice and the guide (vidgen hosted them for this job; the clip may not use them)"]
    assert not any("trycloudflare" in warning for warning in result.warnings)


def test_a_job_whose_files_were_downloaded_does_not_warn(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, guide = sources(tmp_path)
    fetch = local_fetch(tmp_path)
    share = ShareOptions(SETTINGS, executable=fake_cloudflared, fetch=fetch)
    api = MockOpenRouter(cost=0.2)

    def provider_side(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
        if method == "POST":
            import json

            for ref in json.loads(body or b"{}")["input_references"]:
                address = ref.get("audio_url", ref.get("video_url", {}))["url"]
                assert fetch("GET", address, 5).status == 200
        return api(method, url, headers, body, timeout)

    provider = HostedStandIn(api, sleep=lambda seconds: None)
    provider._transport = provider_side
    result = generate_clip(project, settings(host="quick_tunnel"), _hosted_request(audio, guide), pay=True, provider=provider, catalog=CATALOG, share=share)
    assert result.paid and result.warnings == []


def test_the_mock_provider_never_warns(make_project) -> None:
    root = in_guide_project(make_project, characters=[], refs=[])
    project = Project.load(root)
    render = stub_render(root, passes=("depth",))
    make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=render)
    result = run_shots(project, pay=True, provider=MockVideoProvider(), catalog=CATALOG, out=lambda line: None)
    assert result.shots[0].status == "paid" and result.shots[0].message == ""


def test_a_warning_reaches_the_run_output_and_the_take(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    import vidgen.videogen.run as run_module

    real = run_module.generate_clip

    def with_warning(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        result.warnings = ["the provider never downloaded the guide (vidgen hosted them for this job; the clip may not use them)"]
        return result

    monkeypatch.setattr(run_module, "generate_clip", with_warning)
    root = in_guide_project(make_project, characters=[], refs=[])
    project = Project.load(root)
    make_inputs(project, project_shots(project, CATALOG), guide=True, out=lambda line: None, render=stub_render(root, passes=("depth",)))
    lines: list[str] = []
    report = run_shots(project, pay=True, provider=MockVideoProvider(), catalog=CATALOG, out=lines.append)
    run = report.shots[0]
    assert "never downloaded the guide" in run.message and any("warning:" in line and "never downloaded" in line for line in lines)
    assert run.take is not None and run.take.info["warnings"] == [run.message]


def test_add_take_without_warnings_writes_no_warnings_field(make_project) -> None:
    root = make_project(guide_config(False), folder="take")
    clip = root / "c.mp4"
    write_clip(clip, seconds=1.0, size="32x18", fps=5, audio=False)
    take, is_new = add_take(root, "act", clip, key="k", model=FAST, provider="mock", job_id=None, cost=None, length=1.0, width=32, height=18)
    assert is_new and "warnings" not in take.info
