"""Generated video shots, inputs and sheets (DESIGN.md §113.3): reference / style sheets made by
the image provider (a stub), approval, per-beat shot specs resolved into requests (lengths
snapped and split, inputs, prompts), validation with did-you-mean, the cut inputs, the dry-run
plan and the CLI. Nothing is sent: the model list is the fixture of 2026-11-07, the image
provider a stub."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import minimal_config, write_clip

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.imagegen import GeneratedPicture, ImageRequest
from vidgen.project import Project
from vidgen.videogen.inputs import SceneRender, cut_audio, first_frame, make_inputs
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.models import Catalog, parse_models
from vidgen.videogen.run import ledger_path
from vidgen.videogen.sheets import character_sheet, project_sheets, run_sheets, style_sheet
from vidgen.videogen.shots import pick_aspect, plan_shots, project_shots, shot_problems
from test_videogen_host import fake_cloudflared  # noqa: F401 - the fixture

DATA = Path(__file__).parent / "data" / "openrouter_video_models.json"
DOC = json.loads(DATA.read_text(encoding="utf-8"))
CATALOG = Catalog(tuple(parse_models(DOC)), 0.0, "cache")
SHEET = {"prompt": "a tall woman in a yellow raincoat", "views": ["front", "side"]}
STYLE = {"palette": ["teal", "orange"], "era": "present day", "lens": "35 mm", "notes": "soft light"}
LONG = " ".join(["word"] * 30)  # 30 words: 11.5 s + 0.35 s pad


def shot_config(*beats: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A 9:16 project with characters ana (sheet) and ben (no sheet) and one scene of ``beats``."""
    data = minimal_config(
        format={"width": 1080, "height": 1920, "fps": 30},
        voices={"ana_voice": {"voice_id": "a"}, "ben_voice": {"voice_id": "b"}},
        characters=[{"name": "ana", "voice": "ana_voice", "reference_sheet": SHEET}, {"name": "ben", "voice": "ben_voice"}],
        style_sheet=STYLE,
        videogen={"provider": "mock", "budget_usd": 2.0},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"}, "beats": list(beats)}],
    )
    data.update(overrides)
    return data


TALK = {"id": "talk", "text": "One two three four five six seven eight.", "voice": "ana_voice",
        "generated_shot": {"kind": "talking", "model": "heygen/avatar-iv"}}
ACT = {"id": "act", "text": "Nine ten eleven twelve.", "voice": "ana_voice",
       "generated_shot": {"kind": "action", "model": "bytedance/seedance-2.0-fast", "guide": True, "audio": "beat", "first_frame": "render", "seed": 3}}
WIDE = {"id": "wide", "text": "Thirteen fourteen fifteen.", "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lite", "setting": "a foggy harbour"}}


def png_bytes(key: str) -> bytes:
    """A small real PNG, coloured by ``key`` (so each sheet picture differs)."""
    import hashlib
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 96), tuple(hashlib.sha256(key.encode()).digest()[:3])).save(buffer, "PNG")
    return buffer.getvalue()


class StubImages:
    """An image provider that makes a tiny PNG and reports a cost (named mock: its own ledger)."""

    name = "mock"

    def __init__(self) -> None:
        self.made: list[str] = []

    def check_credentials(self) -> None:
        return None

    def generate(self, request: ImageRequest) -> GeneratedPicture:
        self.made.append(request.path.name)
        return GeneratedPicture(png_bytes(request.key), cost=0.04)


def approve(root: Path) -> None:
    """Set approved: true on every sheet of the project's video.yaml."""
    path = root / "video.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for entry in data["characters"]:
        if "reference_sheet" in entry:
            entry["reference_sheet"]["approved"] = True
    data["style_sheet"]["approved"] = True
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def tone(path: Path, seconds: float) -> Path:
    """A sine MP3 of ``seconds`` (a stand-in for a beat's narration)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f=330:d={seconds}", "-c:a", "libmp3lame", str(path)], check=True)
    return path


def seconds_of(path: Path) -> float:
    from vidgen.speech import audio_duration

    return audio_duration(path)


# ----- config ------------------------------------------------------------------------------------


def test_config_parses_and_rejects(make_project) -> None:
    project = Project.load(make_project(shot_config(TALK)))
    spec = project.config.scenes[0].beats[0].generated_shot
    assert spec is not None and spec.wants_audio and spec.first_frame_source == "sheet"
    assert project.config.characters[0].reference_sheet.views == ["front", "side"]
    assert project.config.style_sheet.words() == "palette teal, orange; present day; 35 mm; soft light"
    bad = {**TALK, "generated_shot": {"kind": "talking", "model": "heygen/avatar-iv", "audio": "none"}}
    with pytest.raises(VidgenError, match="lip-synced"):
        Project.load(make_project(shot_config(bad), folder="b"))
    with pytest.raises(VidgenError, match="author/name"):
        Project.load(make_project(shot_config({**WIDE, "generated_shot": {"kind": "establishing", "model": "veo"}}), folder="c"))
    with pytest.raises(VidgenError, match="kind"):
        Project.load(make_project(shot_config({**WIDE, "generated_shot": {"kind": "talkin", "model": "a/b"}}), folder="d"))
    with pytest.raises(VidgenError, match="listed twice"):
        Project.load(make_project(shot_config(WIDE, characters=[{"name": "ana", "reference_sheet": {"prompt": "x", "views": ["side", "side"]}}]), folder="e"))


def test_sheets_and_shots_do_not_change_renders(make_project) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    plain = dict(shot_config({"id": "talk", "text": TALK["text"], "voice": "ana_voice"}))
    plain.pop("style_sheet")
    plain["characters"] = [{"name": "ana", "voice": "ana_voice"}, {"name": "ben", "voice": "ben_voice"}]
    a = Project.load(make_project(plain, folder="a"))
    b = Project.load(make_project(shot_config(TALK), folder="b"))
    assert scene_fingerprint(a, "s1") == scene_fingerprint(b, "s1")


# ----- sheets ------------------------------------------------------------------------------------


def test_sheet_pictures_prompts_and_status(make_project) -> None:
    project = Project.load(make_project(shot_config(TALK)))
    ana = character_sheet(project, "ana")
    assert ana is not None and [p.label for p in ana.pictures] == ["front", "side"]
    assert ana.paths[0].parent == project.root / "assets" / "sheets" and ana.paths[0].name.startswith("ana_front_")
    text = ana.pictures[1].request.text
    assert "side view: strict 90-degree profile, facing left" in text and "yellow raincoat" in text
    assert "Style: colour palette: teal, orange (colours only, not objects" in text and "era: present day" in text
    assert character_sheet(project, "ben") is None
    style = style_sheet(project)
    assert style is not None and [p.label for p in style.pictures] == ["frame1"]
    assert [s.owner for s in project_sheets(project)] == ["ana", "style"]
    assert "2 of 2 pictures not made yet" in ana.status() and ana.problem() is not None


def test_character_prompts_are_clean_references(make_project) -> None:
    """Step 295: the paid run drew lamps from the palette, a ticket booth and "SELD FICKETS" from
    the role, cut figures and blurred backgrounds from the lens words."""
    style = {"palette": ["slate blue", "warm lamp orange"], "era": "present day", "lens": "35 mm, natural handheld feel, shallow depth of field",
             "notes": "soft overcast morning light, light film grain, realistic", "frame_prompt": "a quay with a ticket hut"}
    sheet = {"prompt": "a man who sells ferry tickets, round glasses", "views": ["front", "three_quarter", "side", "back"], "expressions": ["happy"]}
    project = Project.load(make_project(shot_config(TALK, style_sheet=style, characters=[{"name": "ana", "voice": "ana_voice", "reference_sheet": sheet}])))
    pictures = character_sheet(project, "ana").pictures
    for picture in pictures:
        text = picture.request.text
        assert "plain seamless light grey studio backdrop" in text and "nothing else in the picture" in text
        assert "Who the person is (draw only the person and their clothes): a man who sells ferry tickets, round glasses. No props." in text
        assert "colour palette: slate blue, warm lamp orange (colours only, not objects: the colours of the clothing and the lighting tint)" in text
        assert "light film grain, realistic" in text and "era: present day" in text
        for shot_only in ("35 mm", "handheld", "depth of field", "overcast morning light"):
            assert shot_only not in text
        avoid = text.split("Avoid: ")[1]
        for word in ("text", "letters", "signs", "logos", "labels", "props", "furniture", "lamps", "scenery"):
            assert word in avoid
        assert picture.request.negative.startswith("text, letters")
    by_label = {p.label: p.request.text for p in pictures}
    assert "full body from head to toe, whole figure in frame" in by_label["front"] and "facing the camera squarely" in by_label["front"]
    assert "turned 45 degrees to the left" in by_label["three_quarter"] and "seen straight from behind" in by_label["back"]
    assert "head and shoulders" in by_label["happy"] and "happy expression" in by_label["happy"]
    frame = style_sheet(project).pictures[0].request.text
    assert "35 mm, natural handheld feel, shallow depth of field" in frame and "(colours only, not objects)" in frame and "clothing" not in frame
    assert "no writing anywhere" in frame and "Avoid: text, letters, words, numbers, signs, signage, logos" in frame and "props" not in frame


def test_sheet_costs_reported_or_marked_estimated(make_project) -> None:
    """The cost OpenRouter reports (``usage.cost``) is recorded; without one the estimate is
    counted and marked as one (ledger, sidecar, the printed line)."""
    root = make_project(shot_config(TALK))

    class Unreported(StubImages):
        def generate(self, request: ImageRequest) -> GeneratedPicture:
            self.made.append(request.path.name)
            return GeneratedPicture(png_bytes(request.key), cost=None if len(self.made) == 1 else 0.023, usage={"cost": 0.023} if len(self.made) > 1 else None)

    lines: list[str] = []
    run_sheets(Project.load(root), ["ana"], pay=True, provider=Unreported(), out=lines.append)
    events = [e for e in Ledger(ledger_path(root, "mock")).events() if e["event"] == "completed"]
    assert [(e["cost_usd"], e["cost_source"]) for e in events] == [(None, "estimate"), (0.023, "reported")]
    assert Ledger(ledger_path(root, "mock")).spent() == pytest.approx(0.063 + 0.023)   # gpt-image-1 portrait estimate + reported
    front = json.loads(next((root / "assets" / "sheets").glob("ana_front_*.json")).read_text(encoding="utf-8"))
    side = json.loads(next((root / "assets" / "sheets").glob("ana_side_*.json")).read_text(encoding="utf-8"))
    assert (front["cost_usd"], front["cost_source"]) == (pytest.approx(0.063), "estimate") and "usage" not in front
    assert (side["cost_usd"], side["cost_source"], side["usage"]) == (0.023, "reported", {"cost": 0.023})
    assert "estimated $0.063 (not reported by mock)" in lines[-3] and "$0.023 reported by mock" in lines[-2]
    assert lines[-1].startswith("done: 2 picture(s) made ($0.023 reported by mock + $0.063 estimated (not reported))")


def test_run_sheets_dry_run_pays_nothing_and_pay_needs_a_budget(make_project) -> None:
    root = make_project(shot_config(TALK, videogen={"provider": "mock"}))
    stub = StubImages()
    lines: list[str] = []
    result = run_sheets(Project.load(root), provider=stub, out=lines.append)
    assert stub.made == [] and len(result.plan.todo) == 3
    assert any("sheets: 3 picture(s) to make, estimated $0.189" in line for line in lines)  # gpt-image-1 medium portrait $0.063
    with pytest.raises(VidgenError, match="paying needs a budget"):
        run_sheets(Project.load(root), pay=True, provider=stub, out=lambda line: None)
    assert stub.made == []


def test_pay_makes_pictures_records_them_and_approval_freezes_them(make_project) -> None:
    root = make_project(shot_config(TALK))
    stub = StubImages()
    run_sheets(Project.load(root), ["ana"], pay=True, provider=stub, out=lambda line: None)
    assert len(stub.made) == 2 and character_sheet(Project.load(root), "ana").missing == []
    ledger = Ledger(ledger_path(root, "mock"))
    assert [j.status for j in ledger.jobs()] == ["completed", "completed"] and ledger.spent() == pytest.approx(0.08)
    assert json.loads(next((root / "assets" / "sheets").glob("ana_front_*.json")).read_text(encoding="utf-8"))["cost_usd"] == 0.04
    run_sheets(Project.load(root), ["ana"], pay=True, provider=stub, out=lambda line: None)
    assert len(stub.made) == 2  # made once: never paid twice
    with pytest.raises(VidgenError, match="did you mean ana"):
        run_sheets(Project.load(root), ["anna"], provider=stub, out=lambda line: None)
    approve(root)
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["characters"][0]["reference_sheet"]["prompt"] = "a short man"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    result = run_sheets(Project.load(root), ["ana"], pay=True, provider=stub, out=lambda line: None)
    assert result.blocked and len(stub.made) == 2  # approved: not made again
    assert "set approved: false" in character_sheet(Project.load(root), "ana").status()


def test_pay_refuses_over_budget(make_project) -> None:
    root = make_project(shot_config(TALK, videogen={"provider": "mock", "budget_usd": 0.1}))
    with pytest.raises(VidgenError, match="more than the budget has left"):
        run_sheets(Project.load(root), pay=True, provider=StubImages(), out=lambda line: None)


# ----- shots -------------------------------------------------------------------------------------


def test_talking_shot_follows_its_audio_and_sends_the_portrait_as_a_reference(make_project) -> None:
    project = Project.load(make_project(shot_config(TALK)))
    (shot,) = project_shots(project, CATALOG)
    assert shot.length == pytest.approx(round((8 / 2.6 + 0.35) * 30) / 30)
    assert shot.duration is None and shot.priced_seconds == 4.0 and shot.resolution == "720p" and shot.aspect_ratio == "9:16"
    roles = [(i.role, i.kind, i.frame) for i in shot.inputs]
    assert roles == [("portrait", "image", False), ("audio", "audio", False)]  # avatar-iv lists no frame images
    assert shot.inputs[0].path.name.startswith("ana_front_") and shot.inputs[1].path == project.root / "build" / "videogen" / "talk" / "audio.mp3"
    assert shot.speaker == "ana" and shot.prompt.startswith("Talking close-up of Ana, facing the camera, speaking.")
    assert 'Ana says: "One two three four five six seven eight."' in shot.prompt and "No on-screen text" in shot.prompt
    assert "Style: palette teal, orange" in shot.prompt and "yellow raincoat" in shot.prompt


def test_action_shot_inputs_and_snapped_length(make_project) -> None:
    project = Project.load(make_project(shot_config(ACT)))
    (shot,) = project_shots(project, CATALOG)
    assert shot.duration == 4 and shot.length < 4 and shot.resolution == "480p"
    kinds = [(i.role, i.frame) for i in shot.inputs]
    assert kinds == [("first_frame", True), ("reference", False), ("reference", False), ("reference", False), ("audio", False), ("guide", False)]
    request = shot.request()
    assert request is not None and len(request.frame_images) == 1 and request.seed == 3 and request.duration == 4
    assert {r.kind for r in request.references} == {"image", "audio", "video"}


def test_long_beats_are_split_and_lengths_snap(make_project) -> None:
    long_wide = {"id": "wide", "text": LONG, "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lite"}}
    project = Project.load(make_project(shot_config(long_wide)))
    shots = project_shots(project, CATALOG)
    window = round((30 / 2.6 + 0.35) * 30) / 30
    assert [s.id for s in shots] == ["wide_p1", "wide_p2"] and [s.duration for s in shots] == [6, 6]
    assert shots[1].offset == pytest.approx(window / 2) and shots[1].start == pytest.approx(window / 2)
    assert "split into 2 parts" in shots[0].notes[0]
    assert shots[0].characters == [] and [i.role for i in shots[0].inputs] == ["reference"]  # the style frame


def test_aspect_ratio_nearest_listed(make_project) -> None:
    project = Project.load(make_project(shot_config(WIDE, format={"width": 1080, "height": 1350, "fps": 30})))
    assert pick_aspect(project.config, CATALOG.find("bytedance/seedance-2.0-fast")) == "3:4"
    assert pick_aspect(project.config, CATALOG.find("google/veo-3.1-lite")) == "9:16"


def test_validation_names_unknown_things_with_did_you_mean(make_project) -> None:
    beats = [
        {"id": "b1", "text": "a b c", "generated_shot": {"kind": "action", "model": "google/veo-3.1-lite", "characters": ["anna"], "refs": ["bne", "style", "pics/none.png"]}},
        {"id": "b2", "text": "a b c", "generated_shot": {"kind": "talking", "model": "heygen/avatar-iv"}},
        {"id": "b3", "text": "a b c", "voice": "ben_voice", "generated_shot": {"kind": "talking", "model": "heygen/avatar-iv"}},
        {"id": "b4", "text": "a b c", "generated_shot": {"kind": "establishing", "model": "google/veo-3.1-lit"}},
    ]
    project = Project.load(make_project(shot_config(*beats)))
    messages = [f"{loc}: {msg}" for loc, msg in shot_problems(project)]
    text = "\n".join(messages)
    assert "unknown character 'anna' (did you mean ana?)" in text
    assert "unknown character 'bne' (did you mean ben?)" in text
    assert "no picture pics/none.png" in text
    assert "scenes[0].beats[1].generated_shot: a talking shot needs a speaker" in text
    assert "character 'ben' has no reference_sheet" in text
    shots = project_shots(project, CATALOG)
    assert "did you mean google/veo-3.1-lite?" in shots[-1].problems[0]
    problems, _ = cli.validate_all(project, keep_going=True)
    assert any("did you mean ana" in p.message for p in problems)


# ----- inputs ------------------------------------------------------------------------------------


def test_cut_audio_is_exact_and_padded(tmp_path: Path) -> None:
    from vidgen.render.ffmpeg import find_ffmpeg

    source = tone(tmp_path / "voice.mp3", 1.0)
    cut_audio(find_ffmpeg(), source, tmp_path / "a.mp3", 0.0, 2.5)
    cut_audio(find_ffmpeg(), source, tmp_path / "b.mp3", 0.5, 0.25)
    assert seconds_of(tmp_path / "a.mp3") == pytest.approx(2.5, abs=0.06)
    assert seconds_of(tmp_path / "b.mp3") == pytest.approx(0.25, abs=0.06)


def test_first_frame_skips_a_fade_in(tmp_path: Path) -> None:
    from vidgen.render.ffmpeg import find_ffmpeg

    clip = tmp_path / "fade.mp4"
    video = "color=c=black:s=32x32:r=10:d=2,format=yuv420p,geq=lum='if(lt(N,4),0,200)':cb=128:cr=128"
    subprocess.run([find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", video, "-c:v", "libx264", "-qp", "0", str(clip)], check=True)
    assert first_frame(find_ffmpeg(), clip, tmp_path / "f.png") == pytest.approx(0.4)
    assert (tmp_path / "f.png").is_file()


def test_make_inputs_cuts_voice_and_guide(make_project) -> None:
    root = make_project(shot_config(TALK, ACT))
    project = Project.load(root)
    tone(project.audio_dir / "talk.mp3", 3.0)
    shots = project_shots(project, CATALOG)
    with pytest.raises(VidgenError, match="vidgen tts"):
        make_inputs(project, shots, out=lambda line: None)
    tone(project.audio_dir / "act.mp3", 1.5)
    lines: list[str] = []
    written = make_inputs(project, shots, out=lines.append)
    assert [p.name for p in written] == ["audio.mp3", "audio.mp3"] and any("--guide" in line for line in lines)
    scene_clip = write_clip(root / "fake" / "s1.mp4", seconds=8.0, size="54x96", audio=False)
    act = shots[1]

    def render(_project: Project, scene_id: str, passes: tuple[str, ...]) -> SceneRender:
        assert scene_id == "s1" and passes == ()
        return SceneRender(scene_clip, {"talk": 0.0, "act": shots[0].length})

    written = make_inputs(project, [act], guide=True, out=lambda line: None, render=render)
    assert [p.name for p in written] == ["audio.mp3", "guide.mp4", "first_frame.png"]
    from vidgen.render.ffmpeg import probe

    info = probe(root / "build" / "videogen" / "act" / "guide.mp4")
    assert info.duration == pytest.approx(act.length, abs=0.25) and (info.width, info.height) == (54, 96)
    assert seconds_of(root / "build" / "videogen" / "act" / "audio.mp3") == pytest.approx(act.length, abs=0.06)


# ----- the plan ----------------------------------------------------------------------------------


def test_plan_prices_every_shot_and_counts_the_budget(make_project) -> None:
    root = make_project(shot_config(TALK, ACT, WIDE, videogen={"provider": "openrouter", "budget_usd": 2.0}))
    plan = plan_shots(Project.load(root), catalog=CATALOG)
    talk, act, wide = plan.shots
    assert talk.estimate.cost == pytest.approx(0.20)  # $0.05/s x 4 s
    assert wide.estimate.cost == pytest.approx(0.12)  # $0.03/s x 4 s at 720p
    assert act.estimate.cost == pytest.approx(480 * 854 * 24 * (4 + 4) / 1024 * 0.000002475)  # the output and its video reference
    assert plan.sheets_todo == 3 and plan.sheets_cost == pytest.approx(0.063 * 3)
    assert plan.total == pytest.approx(plan.clips_cost + plan.sheets_cost) and plan.total < 2.0
    assert wide.left_after == pytest.approx(2.0 - plan.total)
    assert any("ana sheet: 2 of 2 pictures not made yet" in b for b in talk.shot.blocked)
    assert any("hosted URL" in b for b in act.shot.blocked) and not any("hosted URL" in b for b in wide.shot.blocked)
    text = "\n".join(plan.lines(root))
    assert "shot talk (talking, scene s1, beat talk, 0:00.00-0:03.43, 3.43 s): heygen/avatar-iv, 720p, 9:16" in text
    assert "length: follows the audio (3.43 s; heygen/avatar-iv takes no duration), priced as 4 s" in text
    assert "length: asks for 4 s, trimmed to" in text and "dry run: nothing was sent or paid; 3 shot(s) blocked" in text
    tight = plan_shots(Project.load(root), catalog=CATALOG, budget_usd=0.3)
    assert tight.shots[-1].over_budget and "OVER THE BUDGET" in "\n".join(tight.lines(root))
    with pytest.raises(VidgenError, match="did you mean talk"):
        plan_shots(Project.load(root), catalog=CATALOG, shot_ids=["tlak"])


def test_plan_is_ready_once_sheets_are_approved_and_inputs_made(make_project) -> None:
    from vidgen.videogen.pictures import PICTURES_DIR

    pictures = {"id": "pics", "text": "Nine ten eleven twelve.", "voice": "ana_voice",
                "generated_shot": {"kind": "action", "model": "bytedance/seedance-2.0-fast", "characters": ["ana"]}}
    root = make_project(shot_config(pictures))
    run_sheets(Project.load(root), pay=True, provider=StubImages(), out=lambda line: None)
    project = Project.load(root)
    plan = plan_shots(project, catalog=CATALOG)
    assert any("not approved yet" in b for b in plan.shots[0].shot.blocked) and plan.budget.spent_usd == pytest.approx(0.12)
    approve(root)
    project = Project.load(root)
    plan = plan_shots(project, catalog=CATALOG)
    (shot,) = plan.shots
    assert shot.shot.blocked == [] and shot.shot.problems == [] and not shot.cached
    assert shot.left_after == pytest.approx(2.0 - 0.12 - shot.cost)
    assert {i.kind for i in shot.shot.inputs} == {"image"}
    copies = list((root / PICTURES_DIR).iterdir())  # the small PNGs go as JPEG copies
    assert 0 < shot.request_bytes < 100_000 and copies and all(c.suffix == ".jpg" for c in copies)
    assert "  request: 0.0 MB with its inline pictures (vidgen sends at most 21 MB)" in plan.lines(root)


def test_inline_audio_is_a_problem_and_run_pay_refuses_it(make_project) -> None:
    from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
    from vidgen.videogen.shots import INLINE_AUDIO_VIDEO_PROBLEM
    from vidgen.videogen.workflow import run_shots

    root = make_project(shot_config(TALK, videogen={"provider": "mock", "budget_usd": 2.0, "inline_media": "all"}))
    run_sheets(Project.load(root), pay=True, provider=StubImages(), out=lambda line: None)
    approve(root)
    project = Project.load(root)
    tone(project.audio_dir / "talk.mp3", 3.0)
    make_inputs(project, project_shots(project, CATALOG), out=lambda line: None)
    (talk,) = plan_shots(project, catalog=CATALOG).shots
    assert talk.shot.blocked == [] and talk.shot.problems == [f"scenes[0].beats[0].generated_shot: {INLINE_AUDIO_VIDEO_PROBLEM}"]
    assert talk.estimate.cost == pytest.approx(0.20)
    api = MockOpenRouter()
    with pytest.raises(VidgenError, match="(?s)not paying: fix these shots first.*https URLs"):
        run_shots(project, pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=lambda line: None)
    assert api.submits == []
    hosted = Project.load(make_project(shot_config(TALK, videogen={"provider": "openrouter", "budget_usd": 2.0}), folder="hosted"))
    (talk,) = plan_shots(hosted, catalog=CATALOG).shots
    assert talk.shot.problems == [] and any("OpenRouter refuses inline audio / video" in b for b in talk.shot.blocked)


MINI = "bytedance/seedance-2.0-mini"
SOUND = {"id": "act", "text": "Nine ten eleven twelve.", "voice": "ana_voice", "generated_shot": {"kind": "action", "model": MINI, "place": False}}


def _sound_shot(make_project, shot: dict[str, Any] | None = None, **videogen: Any) -> Any:
    beat = {**SOUND, "generated_shot": {**SOUND["generated_shot"], **(shot or {})}}
    data = shot_config(beat)
    data["videogen"] = {"provider": "mock", "budget_usd": 2.0, **videogen}
    return Project.load(make_project(data))


@pytest.mark.parametrize(
    ("shot", "videogen", "sound"),
    [
        ({}, {}, "mix"),
        ({}, {"sound": "model"}, "model"),
        ({}, {"models": {MINI: {"sound": "model"}}}, "model"),
        ({}, {"sound": "model", "models": {MINI: {"sound": "mix"}}}, "mix"),
        ({}, {"models": {"google/veo-3.1-lite": {"sound": "model"}}}, "mix"),
        ({"sound": "mix"}, {"sound": "model", "models": {MINI: {"sound": "model"}}}, "mix"),
        ({"sound": "model"}, {"sound": "mix", "models": {MINI: {"sound": "mix"}}}, "model"),
    ],
)
def test_sound_precedence_and_request(make_project, shot: dict[str, Any], videogen: dict[str, Any], sound: str) -> None:
    project = _sound_shot(make_project, shot, **videogen)
    (found,) = project_shots(project, CATALOG)
    request = found.request()
    assert found.sound == sound and request is not None and request.generate_audio is (sound == "model")


def test_plan_shows_sound_and_blocks_a_model_that_cannot_make_it(make_project) -> None:
    project = _sound_shot(make_project)
    lines = plan_shots(project, catalog=CATALOG).lines(project.root)
    assert any(line.startswith("  sound: mix") for line in lines)
    avatar = "heygen/avatar-iv"             # the list says generate_audio: false
    project = Project.load(make_project(shot_config({**TALK, "generated_shot": {**TALK["generated_shot"], "sound": "model"}})))
    plan = plan_shots(project, catalog=CATALOG)
    assert plan.shots[0].shot.model.id == avatar and any("cannot make sound" in b for b in plan.shots[0].shot.blocked)
    assert "sound: model (the model makes the clip's own sound" in "\n".join(plan.lines(project.root))
    unknown = "x-ai/grok-imagine-video-1.5-lite"    # generate_audio not listed: a note, not blocked
    project = _sound_shot(make_project, {"model": unknown, "sound": "model"})
    plan = plan_shots(project, catalog=CATALOG)
    assert not any("cannot make sound" in b for b in plan.shots[0].shot.blocked)
    assert any("does not say whether it can make sound" in n for n in plan.shots[0].shot.notes)


def test_plan_warns_a_placed_sound_take_and_unlisted_models(make_project) -> None:
    project = _sound_shot(make_project, {"sound": "model", "place": True}, models={"bytedance/seedance-20-mini": {"sound": "model"}})
    plan = plan_shots(project, catalog=CATALOG)
    assert any("a placed take plays vidgen's mix" in n for n in plan.shots[0].shot.notes)
    assert any("bytedance/seedance-20-mini" in w and "did you mean" in w for w in plan.warnings)
    assert any(line.startswith("warning: videogen.models") for line in plan.lines(project.root))


def test_cli_plan_text_and_json(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path / "cache"))
    cache = tmp_path / "cache" / "openrouter" / "video_models.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"fetched_at": time.time(), "doc": DOC}), encoding="utf-8")
    root = make_project(shot_config(TALK, WIDE))
    assert cli.main(["generate", "plan", str(root)]) == 0
    out = capsys.readouterr().out
    assert "shot wide (establishing" in out and "total: 2 shot(s)" in out and "budget $2.000" in out
    assert cli.main(["generate", "plan", str(root), "--json", "--shot", "wide"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["action"] == "plan" and [s["id"] for s in doc["shots"]] == ["wide"] and doc["shots"][0]["duration"] == 4 and doc["shots"][0]["sound"] == "mix"
    assert cli.main(["generate", "sheets", str(root)]) == 0
    assert "sheets: 3 picture(s) to make" in capsys.readouterr().out
    assert cli.main(["generate", "plan", str(root), "--pay"]) != 0
    assert "never pays" in capsys.readouterr().err


# ----- hosted audio / video through a quick tunnel (DESIGN.md §115.2) ----------------------------------


def test_quick_tunnel_shares_only_the_shots_voice_while_its_job_runs(
    make_project, tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import tempfile

    from test_videogen_host import FAKE_HOST, HostedStandIn, local_fetch

    from vidgen.videogen.host import HostSettings, ShareOptions
    from vidgen.videogen.mock import MockOpenRouter
    from vidgen.videogen.openrouter import Response
    from vidgen.videogen.shots import NO_HOST_BLOCKED
    from vidgen.videogen.workflow import run_shots

    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))   # the share folders land here
    videogen = {"provider": "openrouter", "budget_usd": 2.0, "host": "quick_tunnel", "cloudflared": fake_cloudflared[1]}
    root = make_project(shot_config(TALK, WIDE, videogen=videogen))
    run_sheets(Project.load(root), pay=True, provider=StubImages(), out=lambda line: None)
    approve(root)
    project = Project.load(root)
    tone(project.audio_dir / "talk.mp3", 3.0)
    make_inputs(project, project_shots(project, CATALOG), out=lambda line: None)
    audio = root / "build" / "videogen" / "talk" / "audio.mp3"

    # the plan: not blocked; exactly the voice would be shared, for at most 20 min; pictures are not
    talk, wide = plan_shots(project, catalog=CATALOG).shots
    assert talk.shot.blocked == [] and talk.shot.problems == [] and talk.shot.share_minutes == 20
    assert [i.path for i in talk.shot.shared] == [audio] and wide.shot.share_minutes is None
    text = "\n".join(talk.lines(root))
    assert "would share through a public Cloudflare quick tunnel, only while this shot's job runs (at most 20 min" in text
    assert f"    build/videogen/talk/audio.mp3 ({audio.stat().st_size:,} bytes)" in text
    monkeypatch.setattr("vidgen.videogen.models.load_catalog", lambda *a, **k: CATALOG)
    assert cli.main(["generate", "plan", str(root), "--json", "--shot", "talk"]) == 0
    (doc,) = json.loads(capsys.readouterr().out)["shots"]
    assert doc["shared"] == [{"path": "build/videogen/talk/audio.mp3", "bytes": audio.stat().st_size}] and doc["share_max_minutes"] == 20
    # without the host: blocked with the way out; without cloudflared: blocked with the install hints
    off = Project.load(make_project(shot_config(TALK, videogen={"provider": "openrouter", "budget_usd": 2.0}), folder="off"))
    assert NO_HOST_BLOCKED in plan_shots(off, catalog=CATALOG).shots[0].shot.blocked
    missing = Project.load(make_project(shot_config(TALK, videogen={**videogen, "cloudflared": "nowhere/cloudflared"}), folder="missing"))
    assert any("winget install Cloudflare.cloudflared" in b for b in project_shots(missing, CATALOG)[0].blocked)

    fetch = local_fetch(tmp_path)
    settings = HostSettings(url_timeout=10, verify_timeout=1.0, verify_interval=0.05)
    lines: list[str] = []
    share = ShareOptions(settings, out=lines.append, executable=fake_cloudflared, fetch=fetch)
    ledger = Ledger(ledger_path(root, "openrouter"))
    start = len(ledger.events())   # the sheet pictures

    def audio_url(body: bytes | None) -> str:
        return json.loads(body or b"{}")["input_references"][-1]["audio_url"]["url"]

    # a provider error quoting the URL: the secret is not passed on; the tunnel is closed; nothing paid
    def refusing(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
        return Response(400, json.dumps({"error": {"code": 400, "message": f"Invalid reference URL: {audio_url(body)}"}}).encode(), {})

    provider = HostedStandIn(MockOpenRouter())
    provider._transport = refusing
    with pytest.raises(VidgenError) as caught:
        run_shots(project, pay=True, shot_ids=["talk"], provider=provider, catalog=CATALOG, share=share, out=lines.append)
    message = str(caught.value)
    assert "Invalid reference URL: https://" in message and "/<secret>" in message
    names = [e["event"] for e in ledger.events()[start:]]
    assert names[0] == "host_open" and names[-1] == "host_close"
    assert sorted(names[1:-1]) == ["host_fetch", "intent_resolved", "submit_intent"]   # the check's HEAD; a refused submit; no job
    assert ledger.events()[-1]["reason"] == "error: VidgenError" and list(temp.iterdir()) == []

    # the paid run: the provider fetches the voice through the tunnel when the job is submitted
    api = MockOpenRouter(cost=0.2)
    got: list[tuple[str, Response]] = []

    def provider_side(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
        if method == "POST":
            got.append((audio_url(body), fetch("GET", audio_url(body), 5)))
        return api(method, url, headers, body, timeout)

    provider = HostedStandIn(api)
    provider._transport = provider_side
    before = len(ledger.events())
    report = run_shots(project, pay=True, shot_ids=["talk"], provider=provider, catalog=CATALOG, share=share, out=lines.append)
    assert [s.status for s in report.shots] == ["paid"] and provider.uploader is None
    ((url, answer),) = got
    assert url.startswith(f"https://{FAKE_HOST}/") and url.endswith(".mp3") and "audio" not in url
    assert answer.status == 200 and answer.body == audio.read_bytes()
    assert list(temp.iterdir()) == [], "the share folder was not deleted"
    events = ledger.events()[before:]
    names = [e["event"] for e in events]
    assert names.index("host_open") < names.index("submit") < names.index("host_close") < names.index("completed")
    assert [(e["method"], e["status"]) for e in events if e["event"] == "host_fetch"] == [("HEAD", 200), ("GET", 200)]
    closed = next(e for e in events if e["event"] == "host_close")
    assert closed["reason"] == "done" and closed["folder_deleted"] is True   # closed once the job ended, before the download
    secret = url.split("/")[3]
    assert secret not in ledger.path.read_text(encoding="utf-8") and all(secret not in line for line in lines)
    assert any("at most 20 min" in line for line in lines) and any("quick tunnel closed (done)" in line for line in lines)
