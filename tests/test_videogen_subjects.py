"""Subjects and their sheet panels (``subjects:``, ``generated_shot.subjects``, ``vidgen generate
subjects``): the schema, the composed sheet and its prompt, the one batch with one unload at the
end, the records and when panels are made again, and the shot blocked until its sheet is ready.
ComfyUI is a fake transport; no render (the views are picture files, or the render is replaced)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image
from pydantic import ValidationError

from vidgen.config import GeneratedShot, Subject, VideoConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import sheet_layout
from vidgen.videogen.sheet_layout import SheetPanel, choose_grid, compose_sheet, place_words, sheet_prompt
from vidgen.videogen.subjects import PANEL_SIZE, PanelSources, make_panels, read_record, set_approval, subject_panels

LTX = "ltx-2.3-union-control"
URL = "http://127.0.0.1:8188"
GLIDER = {"look": "a grey jet glider with red wing tips", "views": [
    {"name": "rear", "image": "stills/rear.png", "crop": [0, 0, 64, 32], "text": "seen from behind and above"},
    {"name": "side", "image": "stills/side.png", "text": "side view, nose to the left"}]}
SEA = {"look": "a rough open sea under a low afternoon sun", "location": True, "views": [{"image": "stills/sea.png", "text": "seen from low over the water"}]}


class FakeTransport:
    """A ComfyUI that finishes every job at once; ``events`` records unloads and jobs in order."""

    where = "fake ComfyUI"
    compiler_fix = ""

    def __init__(self, fail: int | None = None) -> None:
        self.events: list[str] = []
        self.prompts: list[str] = []
        self.fail = fail

    def check(self) -> None:
        pass

    def submit(self, job: Any) -> str:
        if job.free_before:
            self.events.append("free")
        self.prompts.append(job.graph["9"]["inputs"]["prompt"])
        self.events.append(f"job{len(self.prompts)}")
        if job.free_after:
            self.events.append("free")
        return str(len(self.prompts))

    def outcome(self, job_id: str) -> dict[str, Any]:
        if self.fail is not None and int(job_id) == self.fail:
            return {"status": "failed", "seconds": None, "error": "boom", "output": None}
        return {"status": "completed", "seconds": 30.5, "error": None, "output": {"filename": "x.png"}}

    def download(self, job_id: str, dest: Path) -> int:
        Image.new("RGB", PANEL_SIZE, (10 * int(job_id), 20, 30)).save(dest)
        return dest.stat().st_size


def _project(make_project: Any, subject_map: dict[str, Any] | None = None, **shot: Any) -> Path:
    from conftest import minimal_config

    spec = {"kind": "establishing", "model": LTX, "guide": "canny", "first_frame": "none", "size": "768x448", "line": False,
            "subjects": ["glider", "sea"], "prompt": "a grey glider flies low over the sea", **shot}
    data = minimal_config(
        videogen={"provider": "comfyui", "comfyui": {"url": URL}}, subjects=subject_map if subject_map is not None else {"glider": GLIDER, "sea": SEA},
        scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"},
                 "beats": [{"id": "sea", "text": "Low over the open sea.", "generated_shot": spec}]}],
    )
    root = make_project(data)
    (root / "stills").mkdir()
    for name, colour in (("rear", (200, 0, 0)), ("side", (0, 200, 0)), ("sea", (0, 0, 200))):
        Image.new("RGB", (160, 90), colour).save(root / "stills" / f"{name}.png")
    return root


def _make(root: Path, transport: FakeTransport | None = None, **kw: Any) -> Any:
    return make_panels(Project.load(root), transport=transport or FakeTransport(), out=lambda line: None, sleep=lambda s: None, **kw)


def _plan(root: Path) -> Any:
    from vidgen.videogen.models import Catalog
    from vidgen.videogen.shots import plan_shots

    return plan_shots(Project.load(root), catalog=Catalog((), 0.0, "cache"))


# ----- the schema --------------------------------------------------------------------------------


def test_the_subject_schema_refuses_what_cannot_work() -> None:
    assert Subject(**GLIDER).view_names == ["rear", "side"]
    assert Subject(look="x", views=[{"image": "a.png", "text": "t"}, {"image": "b.png", "text": "u"}]).view_names == ["view1", "view2"]
    bad = [
        ({"look": "x", "views": [{"text": "t"}]}, "one of them"),
        ({"look": "x", "views": [{"image": "a.png", "from": {"scene": "s", "at": 1}, "text": "t"}]}, "one of them"),
        ({"look": "x", "views": [{"image": "a.png", "text": "t", "crop": [0, 0, 8, 40]}]}, "at least 16"),
        ({"look": "x", "location": True, "views": [{"image": "a.png", "text": "t"}, {"image": "b.png", "text": "u"}]}, "one view"),
        ({"look": "x", "views": [{"name": "a", "image": "a.png", "text": "t"}, {"name": "a", "image": "b.png", "text": "u"}]}, "unique"),
        ({"look": "x", "views": [{"image": "a.png", "text": "t"}] * 5}, "at most 4"),
    ]
    for data, match in bad:
        with pytest.raises(ValidationError, match=match):
            Subject(**data)


def test_a_shot_names_known_subjects_with_at_most_four_panels() -> None:
    from conftest import minimal_config

    shot = {"kind": "establishing", "model": LTX, "guide": "canny"}

    def config(subjects: dict[str, Any], names: list[str]) -> VideoConfig:
        return VideoConfig(**minimal_config(subjects=subjects, scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"},
                                                                        "beats": [{"text": "t", "generated_shot": {**shot, "subjects": names}}]}]))

    assert config({"glider": GLIDER, "sea": SEA}, ["glider", "sea"]).subjects["sea"].location
    with pytest.raises(ValidationError, match="unknown subject 'boat'"):
        config({"glider": GLIDER}, ["boat"])
    three = {"look": "x", "views": [{"image": "a.png", "text": "t"}] * 3}
    with pytest.raises(ValidationError, match="5 panels; a sheet holds at most 4"):
        config({"glider": GLIDER, "other": three}, ["glider", "other"])
    with pytest.raises(ValidationError, match="unknown scene 'nowhere'"):
        config({"g": {"look": "x", "views": [{"from": {"scene": "nowhere", "at": 1}, "text": "t"}]}}, ["g"])
    for kw, match in (({"sheet": "s.png"}, "not both"), ({"sheet_prompt": "p"}, "built from the subjects"),
                      ({"model": "bytedance/seedance-2.0-fast", "guide": False}, "subjects: is given to")):
        with pytest.raises(ValidationError, match=match):
            GeneratedShot(**{**shot, "subjects": ["glider"], **kw})


# ----- the composed sheet ------------------------------------------------------------------------


def test_the_grid_shows_the_panels_largest_and_names_their_places() -> None:
    sizes = [PANEL_SIZE]
    assert [choose_grid(768, 448, sizes * n) for n in (1, 2, 3, 4)] == [(1, 1), (1, 2), (2, 2), (2, 2)]
    assert [place_words(2, 2, k) for k in range(4)] == ["top left", "top right", "bottom left", "bottom right"]
    assert (place_words(1, 2, 1), place_words(1, 1, 0), place_words(3, 1, 1)) == ("bottom", "the whole sheet", "centre")
    with pytest.raises(VidgenError, match="1-4 panels"):
        choose_grid(768, 448, sizes * 5)
    panels = [SheetPanel(Path("a"), "a glider, from behind"), SheetPanel(Path("b"), "the same glider, side view"), SheetPanel(Path("c"), "the sea")]
    assert sheet_prompt(panels, 2, 2) == "top left, a glider, from behind; top right, the same glider, side view; bottom left, the sea"


def test_the_sheet_is_the_clips_size_on_black_with_one_panel_per_cell(tmp_path: Path) -> None:
    paths = []
    for k, colour in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
        paths.append(tmp_path / f"p{k}.png")
        Image.new("RGB", PANEL_SIZE, colour).save(paths[-1])
    dest = tmp_path / "sheet.png"
    assert compose_sheet([SheetPanel(p, "x") for p in paths], 768, 448, dest) == (2, 2)
    with Image.open(dest) as sheet:
        assert sheet.size == (768, 448)
        cell_w, cell_h = sheet_layout.cell_size(768, 448, 2, 2)
        centres = [(sheet_layout.GAP + c * (cell_w + sheet_layout.GAP) + cell_w // 2, sheet_layout.GAP + r * (cell_h + sheet_layout.GAP) + cell_h // 2)
                   for r in range(2) for c in range(2)]
        assert [sheet.getpixel(xy) for xy in centres] == [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)]
        assert sheet.getpixel((0, 0)) == sheet.getpixel((767, 447)) == sheet.getpixel((384, 2)) == (0, 0, 0)
    first = dest.read_bytes()
    compose_sheet([SheetPanel(p, "x") for p in paths], 768, 448, dest)
    assert dest.read_bytes() == first   # the same panels, the same bytes


# ----- making the panels -------------------------------------------------------------------------


def test_all_panels_are_made_in_one_batch_with_one_unload_after_the_last(make_project: Any) -> None:
    root = _project(make_project)
    fake = FakeTransport()
    result = _make(root, fake)
    assert fake.events == ["free", "job1", "job2", "job3", "free"]
    assert [o.action for o in result.outcomes] == ["made"] * 3 and result.batch_seconds is not None
    assert "product-style" in fake.prompts[0] and "a grey jet glider with red wing tips, seen from behind and above" in fake.prompts[0]
    assert "Show only the place itself" in fake.prompts[2]
    rear = root / "sheets" / "glider" / "rear.png"
    record = read_record(subject_panels(Project.load(root), "glider")[0])
    assert rear.is_file() and record["seed"] == 42 and record["usage"]["gpu_seconds"] == 30.5 and record["source"]["still"]["crop"] == [0, 0, 64, 32]
    assert set(record) >= {"model", "prompt", "still_sha256", "sha256", "seconds", "made"} and "approved" not in record["source"]
    again = FakeTransport()
    assert [o.action for o in _make(root, again).outcomes] == ["kept"] * 3 and again.events == []


@pytest.mark.slow
def test_a_changed_seed_text_or_picture_remakes_only_those_panels_and_force_remakes_all(make_project: Any) -> None:
    root = _project(make_project)
    _make(root)
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["subjects"]["sea"]["seed"] = 7
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    Image.new("RGB", (160, 90), (9, 9, 9)).save(root / "stills" / "side.png")
    sources = PanelSources(Project.load(root))
    states = {p.label: sources.state(p) for name in ("glider", "sea") for p in subject_panels(Project.load(root), name)}
    assert states == {"glider/rear": None, "glider/side": "its still changed (the scene, its time or crop, or the picture)", "sea/view1": "its look, text or seed changed"}
    fake = FakeTransport()
    assert [o.action for o in _make(root, fake).outcomes] == ["kept", "made", "made"] and fake.events == ["free", "job1", "job2", "free"]
    forced = FakeTransport()
    assert [o.action for o in _make(root, forced, force=True, names=["glider"]).outcomes] == ["made", "made"]
    assert forced.events == ["free", "job1", "job2", "free"]


@pytest.mark.slow
def test_a_view_from_a_scene_takes_the_frame_of_the_render_without_takes(make_project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen.videogen import inputs

    root = _project(make_project, {"sea": {**SEA, "views": [{"from": {"scene": "s1", "at": 1.5}, "text": "from low"}]}}, subjects=["sea"])
    taken: list[tuple[Path, float]] = []

    def frame_at(ffmpeg: str, source: Path, dest: Path, seconds: float) -> None:
        taken.append((source, seconds))
        Image.new("RGB", (640, 360), (0, 0, 200)).save(dest)

    monkeypatch.setattr(inputs, "frame_at", frame_at)
    rendered: list[tuple[bool, str]] = []

    def render(project: Project, scene: str) -> Path:
        rendered.append((project.takes_shown, scene))
        return root / "scene.mp4"

    from vidgen.render import fingerprint
    monkeypatch.setattr(fingerprint, "scene_fingerprint", lambda project, scene: ("after" if rendered else "before") + "0" * 58)   # a first render changes it
    result = make_panels(Project.load(root), transport=FakeTransport(), render=render, out=lambda line: None, sleep=lambda s: None)
    assert rendered == [(False, "s1")] and taken == [(root / "scene.mp4", 1.5)] and result.outcomes[0].action == "made"
    record = read_record(subject_panels(Project.load(root), "sea")[0])
    assert record["source"]["still"]["scene"] == "s1" and record["source"]["still"]["scene_fingerprint"] == "after" + "0" * 58


def test_a_failed_panel_stops_the_batch_and_says_the_model_may_be_loaded(make_project: Any) -> None:
    root = _project(make_project)
    with pytest.raises(VidgenError, match="panel glider/side failed: boom; the image model may still be loaded"):
        _make(root, FakeTransport(fail=2))


def test_panels_need_the_comfyui_server(make_project: Any) -> None:
    root = _project(make_project)
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["videogen"] = {}
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(VidgenError, match="made on the ComfyUI server"):
        _make(root)
    with pytest.raises(VidgenError, match="no subject 'boat'"):
        _make(root, names=["boat"])


# ----- the shot ----------------------------------------------------------------------------------


def test_a_shot_is_blocked_until_its_panels_are_made_and_its_sheet_composed(make_project: Any) -> None:
    from vidgen.videogen.inputs import make_inputs
    from vidgen.videogen.models import Catalog
    from vidgen.videogen.shots import project_shots

    root = _project(make_project)
    (item,) = _plan(root).shots
    assert item.shot.sheet is None and any("`vidgen generate subjects`" in b and "glider/rear: not made yet" in b for b in item.shot.blocked)
    lines = "\n".join(_plan(root).lines(root))
    assert "glider/rear: sheets/glider/rear.png - not made yet" in lines
    want = ("Reference sheet: top left, a grey jet glider with red wing tips, seen from behind and above; top right, the same glider, "
            "side view, nose to the left; bottom left, a rough open sea under a low afternoon sun, seen from low over the water. Generated video: ")
    assert item.shot.prompt.startswith(want)
    _make(root)
    (item,) = _plan(root).shots
    assert any("is not composed yet: `vidgen generate inputs` (free)" in b for b in item.shot.blocked)
    project = Project.load(root)
    written = make_inputs(project, project_shots(project, Catalog((), 0.0, "cache")), out=lambda line: None)
    sheet = root / "build" / "videogen" / "sea" / "sheet.png"
    assert sheet in written
    (item,) = _plan(root).shots
    assert item.shot.sheet == sheet and any("sheet panels not approved" in b for b in item.shot.blocked)   # composed, to look at
    set_approval(Project.load(root), [])
    (item,) = _plan(root).shots
    assert item.shot.sheet == sheet and item.shot.blocked == ["inputs not made yet: `vidgen generate inputs --guide`"] and item.request is not None and item.request.sheet is not None
    assert "composed from subjects glider, sea" in "\n".join(item.lines(root))
    with Image.open(sheet) as picture:
        assert picture.size == (768, 448)
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["subjects"]["glider"]["look"] = "a white glider"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (item,) = _plan(root).shots
    assert item.shot.sheet is None and any("glider/rear: its look, text or seed changed" in b for b in item.shot.blocked)


def test_a_project_without_subjects_plans_as_before(make_project: Any) -> None:
    from conftest import minimal_config

    root = make_project(minimal_config(videogen={"provider": "comfyui", "comfyui": {"url": URL}}))
    plan = _plan(root)
    assert plan.subject_lines == [] and not any("subjects" in line for line in plan.lines(root))
    assert Project.load(root).config.subjects == {}


# ----- approval ----------------------------------------------------------------------------------


def _blocked(root: Path) -> list[str]:
    (item,) = _plan(root).shots
    return item.shot.blocked


@pytest.mark.slow
def test_panels_are_approved_after_their_contact_picture_and_a_remade_panel_is_not(make_project: Any) -> None:
    from vidgen.videogen.subjects import is_approved

    root = _project(make_project)
    with pytest.raises(VidgenError, match="only current panels can be approved .*glider/rear: not made yet"):
        set_approval(Project.load(root), ["glider"])
    result = _make(root)
    contact = root / "sheets" / "glider" / "contact.png"
    assert result.contacts == [contact, root / "sheets" / "sea" / "contact.png"] and (root / "sheets" / "glider" / "rear.still.png").is_file()
    with Image.open(contact) as picture:
        assert picture.size[0] == 2 * 720 and picture.size[1] > 2 * 384   # two panels over their two stills, with the view names
    assert any("sheet panels not approved (glider/rear, glider/side, sea/view1): look at sheets/glider/contact.png, sheets/sea/contact.png, "
               "then `vidgen generate subjects --approve glider --approve sea`" in b for b in _blocked(root))
    assert "  glider/rear: sheets/glider/rear.png (current, not approved)" in _plan(root).lines(root)
    set_approval(Project.load(root), ["glider"])
    set_approval(Project.load(root), ["sea"])
    assert not any("approved" in b for b in _blocked(root)) and "  sea/view1: sheets/sea/view1.png (current, approved)" in _plan(root).lines(root)
    rear, side = subject_panels(Project.load(root), "glider")
    set_approval(Project.load(root), ["glider"], "rear", approve=False)
    assert not is_approved(rear) and is_approved(side) and any("not approved (glider/rear)" in b for b in _blocked(root))
    with pytest.raises(VidgenError, match="no view 'back'"):
        set_approval(Project.load(root), ["glider"], "back")
    set_approval(Project.load(root), [])   # --approve-all
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["subjects"]["glider"]["views"][1]["text"] = "side view, nose to the right"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(VidgenError, match="glider/side: its look, text or seed changed"):
        set_approval(Project.load(root), ["glider"])
    assert [(o.panel.label, o.action) for o in _make(root).outcomes] == [("glider/rear", "kept"), ("sea/view1", "kept"), ("glider/side", "made")]
    rear, side = subject_panels(Project.load(root), "glider")
    assert is_approved(rear) and not is_approved(side) and any("not approved (glider/side)" in b for b in _blocked(root))


def test_an_explicit_sheet_needs_no_approval_and_a_shot_without_a_sheet_gets_a_warning(make_project: Any) -> None:
    root = _project(make_project, subjects=None, sheet="hand.png", sheet_prompt="a grey glider")
    Image.new("RGB", (768, 448), (5, 5, 5)).save(root / "hand.png")
    plan = _plan(root)
    assert not any("approv" in b for b in plan.shots[0].shot.blocked) and plan.warnings == []
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    for key in ("sheet", "sheet_prompt"):
        del data["scenes"][0]["beats"][0]["generated_shot"][key]
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    plan = _plan(root)
    assert plan.warnings == ["shot sea: no subjects: and no sheet:, so nothing keeps its subject looking the same across shots (`vidgen guide outputs`, section Stylesheets)"]
    assert "warning: shot sea: no subjects:" in "\n".join(plan.lines(root))
    with pytest.raises(ValidationError, match="cannot be named contact"):
        Subject.model_validate({"look": "x", "views": [{"name": "contact", "image": "a.png", "text": "t"}]})


@pytest.mark.slow
def test_the_cli_approves_and_prints_the_panels_progress_also_with_json(make_project: Any, monkeypatch: pytest.MonkeyPatch,
                                                                        capsys: pytest.CaptureFixture[str]) -> None:
    import json

    from vidgen import cli
    from vidgen.videogen import subjects

    root = _project(make_project)

    def fake_make(project: Project, names: Any, *, force: bool, out: Any) -> Any:
        out("glider/rear: sheets/glider/rear.png (5 s GPU, 10 s door to door)")
        return subjects.PanelsResult()

    monkeypatch.setattr(subjects, "make_panels", fake_make)
    assert cli.main(["generate", "subjects", str(root), "--json"]) == 0   # what `vidgen remote` runs: the lines go to its log
    captured = capsys.readouterr()
    assert "glider/rear: sheets/glider/rear.png (5 s GPU" in captured.err and json.loads(captured.out)["ok"]
    assert cli.main(["generate", "subjects", str(root), "--approve", "glider"]) == 1
    assert "only current panels can be approved" in capsys.readouterr().err
    assert cli.main(["generate", "subjects", str(root), "--approve", "glider", "--force"]) == 1
    assert cli.main(["generate", "subjects", str(root), "--view", "rear"]) == 1
    _make(root)
    assert cli.main(["generate", "subjects", str(root), "--approve", "glider", "--view", "rear"]) == 0
    assert "glider/rear: approved" in capsys.readouterr().out
    assert subjects.is_approved(subject_panels(Project.load(root), "glider")[0])
    assert not subjects.is_approved(subject_panels(Project.load(root), "glider")[1])


@pytest.mark.slow
def test_generate_plan_and_run_with_json_print_their_lines_on_stderr_for_vidgen_remote(
        make_project: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`vidgen remote` adds --json and shows the VM's stderr: the plan's and the run's lines go there (Step 430)."""
    import json

    from vidgen import cli
    from vidgen.guide import find_topic
    from vidgen.videogen.models import Catalog

    root = _project(make_project)
    monkeypatch.setattr("vidgen.videogen.models.load_catalog", lambda *a, **k: Catalog((), 0.0, "cache"))
    assert cli.main(["generate", "plan", str(root), "--json"]) == 0
    captured = capsys.readouterr()
    assert "glider/rear: sheets/glider/rear.png - not made yet" in captured.err and json.loads(captured.out)["shots"][0]["id"] == "sea"
    assert cli.main(["generate", "run", str(root), "--json"]) == 0
    captured = capsys.readouterr()
    assert "shot sea: blocked (" in captured.err and json.loads(captured.out)["shots"][0]["status"] == "blocked"
    assert "### Stylesheets" in find_topic("outputs").text   # the section the no-sheet warning names


# ----- the sheet's background (Step 431) ---------------------------------------------------------


def test_a_background_replaces_the_black_around_the_panels_and_keeps_the_panels(tmp_path: Path) -> None:
    from vidgen.videogen.sheet_layout import colour_background, location_background

    obj = Image.new("RGB", (180, 96), (0, 0, 0))
    obj.paste((250, 10, 10), (65, 35, 115, 61))   # an object on black
    obj.save(tmp_path / "obj.png")
    Image.new("RGB", (180, 96), (60, 40, 20)).save(tmp_path / "room.png")
    panels = [SheetPanel(tmp_path / "obj.png", "x"), SheetPanel(tmp_path / "room.png", "y")]
    dest = tmp_path / "sheet.png"
    compose_sheet(panels, 192, 112, dest, colour_background("#3a2a1a", 192, 112))
    with Image.open(dest) as sheet:
        assert sheet.getpixel((0, 0)) == sheet.getpixel((96, 1)) == sheet.getpixel((10, 20)) == (0x3a, 0x2a, 0x1a)   # gaps, the object's black
        assert sheet.getpixel((96, 28)) == (250, 10, 10) and sheet.getpixel((96, 84)) == (60, 40, 20)   # the panels as they were
    background = location_background(tmp_path / "room.png", 192, 112)
    lifted = background.getpixel((10, 10))
    assert 0.299 * lifted[0] + 0.587 * lifted[1] + 0.114 * lifted[2] > 50 and lifted[0] > lifted[2]   # brighter than the room, its colour
    compose_sheet(panels, 192, 112, dest, background)
    first = dest.read_bytes()
    compose_sheet(panels, 192, 112, dest, location_background(tmp_path / "room.png", 192, 112))
    assert dest.read_bytes() == first   # deterministic


@pytest.mark.slow
def test_sheet_background_is_checked_named_in_the_prompt_and_part_of_the_sheets_source(make_project: Any) -> None:
    from vidgen.videogen.inputs import make_inputs
    from vidgen.videogen.models import Catalog
    from vidgen.videogen.shots import project_shots

    with pytest.raises(ValidationError, match="this shot has no subjects"):
        GeneratedShot(kind="establishing", model=LTX, guide="canny", sheet_background="location")
    from conftest import minimal_config

    shot = {"kind": "establishing", "model": LTX, "guide": "canny", "subjects": ["glider"], "sheet_background": "location"}
    with pytest.raises(ValidationError, match="needs a location subject"):
        VideoConfig(**minimal_config(subjects={"glider": GLIDER}, scenes=[{"id": "s1", "type": "text_card", "params": {"text": "x"},
                                                                         "beats": [{"text": "t", "generated_shot": shot}]}]))
    root = _project(make_project, sheet_background="location")
    (item,) = _plan(root).shots
    assert "over the water; the panels sit on a softly blurred sea. Generated video: " in item.shot.prompt
    _make(root)
    set_approval(Project.load(root), [])
    project = Project.load(root)
    make_inputs(project, project_shots(project, Catalog((), 0.0, "cache")), out=lambda line: None)
    (item,) = _plan(root).shots
    assert item.shot.sheet is not None and not any("sheet" in b for b in item.shot.blocked)
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][0]["beats"][0]["generated_shot"]["sheet_background"] = "#102030"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (item,) = _plan(root).shots
    assert any("is not composed from the current panels" in b for b in item.shot.blocked) and "softly blurred" not in item.shot.prompt
    data["scenes"][0]["beats"][0]["generated_shot"]["sheet_background"] = "nowhere.png"
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (item,) = _plan(root).shots
    assert any("is not black, location, a colour" in p for p in item.shot.problems)


def test_the_default_restyle_prompt_is_neutral_and_names_the_shot_and_a_prompt_may_stay_with_first_frame_none(make_project: Any) -> None:
    from vidgen.videogen.inputs import restyle_prompt
    from vidgen.videogen.qwen_graph import RESTYLE_PROMPT

    assert not any(word in RESTYLE_PROMPT.lower() for word in ("sea", "water", "sunlight", "aerial", "haze"))
    root = _project(make_project, first_frame_prompt="keep it dry")   # first_frame: none: kept, not used
    (item,) = _plan(root).shots
    assert any("first_frame_prompt: is not used with first_frame: none" in n for n in item.shot.notes)
    shot = item.shot.model_copy() if hasattr(item.shot, "model_copy") else item.shot
    shot.spec = shot.spec.model_copy(update={"first_frame_prompt": None})
    assert restyle_prompt(shot).endswith("The picture shows: a grey glider flies low over the sea.")
    with pytest.raises(ValidationError, match="first_frame_prompt: is the edit instruction"):
        GeneratedShot(kind="establishing", model=LTX, first_frame="render", first_frame_prompt="x")
