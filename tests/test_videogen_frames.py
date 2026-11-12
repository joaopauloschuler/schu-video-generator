"""Step 319: ``vidgen generate frames`` and ``vidgen split-sheet`` (DESIGN.md §113.15-113.16).
Nothing is sent or paid: the image model is a stand-in, the layout comes from a stub render."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from test_imagegen_openrouter import info
from test_videogen_first_frame_in import in_guide_project, picture_file, the_shot
from test_videogen_input_freshness import stub_render
from test_videogen_shots import CATALOG

from vidgen.errors import VidgenError
from vidgen.imagegen import GeneratedPicture, ImageRequest
from vidgen.imagegen.openrouter import ModelInfo, check_request, request_body
from vidgen.project import Project
from vidgen.videogen.frames import paint_prompt, paint_references, run_frames, select_paint_shots
from vidgen.videogen.shots import project_sheet_map, project_shots
from vidgen.videogen.split_sheet import grid_boxes, split_sheet


def paint_project(make_project, **paint: Any) -> Path:
    root = in_guide_project(make_project)
    data_path = root / "video.yaml"
    import yaml

    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    shot = data["scenes"][0]["beats"][0]["generated_shot"]
    shot["first_frame"] = "painted"
    shot["paint_first_frame"] = {"prompt": "she stands on the left", "refs": [{"file": "assets/start.png", "shows": "ana"}], **paint}
    data_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    picture_file(root)
    return root


def priced(models: list[str]) -> dict[str, ModelInfo]:
    """The ``lookup=`` hook: OpenRouter's recorded answer for each model (its price and what it takes)."""
    return {model: info(model) for model in models}


class Painter:
    name = "openrouter"
    key_via_proxy = False

    def __init__(self) -> None:
        self.calls: list[ImageRequest] = []

    def check_credentials(self) -> None:
        return None

    def generate(self, request: ImageRequest) -> GeneratedPicture:
        self.calls.append(request)
        return GeneratedPicture(Image.new("RGB", (8, 8)).tobytes(), cost=0.04)


def _png() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.slow
def test_prompt_numbers_pictures_after_the_layout(make_project) -> None:
    root = paint_project(make_project)
    project = Project.load(root)
    (shot,) = project_shots(project, CATALOG)
    references, problems, blocked = paint_references(project, shot, project_sheet_map(project))
    assert not problems and not blocked
    prompt = paint_prompt(project, shot, references)
    assert "Reference picture 1 is a plain layout" in prompt and "Reference picture 2 shows Ana" in prompt


def test_frames_pays_once_and_never_twice(make_project) -> None:
    root = paint_project(make_project)
    project = Project.load(root)
    project.config.videogen.budget_usd = 1.0
    shots = select_paint_shots(project_shots(project, CATALOG), ())
    painter = Painter()
    painter.generate = lambda request: (painter.calls.append(request), GeneratedPicture(_png(), cost=0.04))[1]  # type: ignore[method-assign]
    run_frames(project, shots, pay=True, provider=painter, out=lambda line: None, lookup=priced, render=stub_render(root))
    assert len(painter.calls) == 1 and painter.calls[0].input_references
    again = select_paint_shots(project_shots(project, CATALOG), ())
    result = run_frames(project, again, pay=True, provider=painter, out=lambda line: None, lookup=priced, render=stub_render(root))
    assert len(painter.calls) == 1 and not result.plan.todo


def test_frames_refuses_without_budget(make_project) -> None:
    root = paint_project(make_project)
    project = Project.load(root)
    project.config.videogen.budget_usd = None   # the guide project sets one
    shots = select_paint_shots(project_shots(project, CATALOG), ())
    painter = Painter()
    with pytest.raises(VidgenError, match="budget"):
        run_frames(project, shots, pay=True, provider=painter, out=lambda line: None, lookup=priced, render=stub_render(root))
    assert not painter.calls


def test_frames_refuses_a_shot_without_paint(make_project) -> None:
    root = in_guide_project(make_project)
    with pytest.raises(VidgenError, match="paint_first_frame"):
        select_paint_shots([the_shot(root)], ("act",))


#: What the stand-in model takes for the shape and size :func:`_request` asks for.
SIZE_PARAMS = {"aspect_ratio": {"type": "enum", "values": ["9:16"]}, "resolution": {"type": "enum", "values": ["2K"]}}


def _info() -> ModelInfo:
    return ModelInfo("author/model", ({"supported_parameters": {"input_references": {"type": "range", "min": 0, "max": 2}, **SIZE_PARAMS}},))


def _request(tmp_path: Path, count: int) -> ImageRequest:
    path = tmp_path / "ref.png"
    path.write_bytes(_png())
    return ImageRequest("openrouter", "author/model", "9x16", None, 1, "p", "", "", "p", "k", tmp_path / "o.png", tmp_path / "o.json", "9:16", "2K", False, "png", (path,) * count)


def test_input_references_go_in_the_body_as_data_urls(tmp_path: Path) -> None:
    body = request_body(_request(tmp_path, 2), _info())
    url = body["input_references"][0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,") and base64.b64decode(url.partition(",")[2]) == _png()


def test_too_many_input_references_are_a_problem(tmp_path: Path) -> None:
    assert check_request(_request(tmp_path, 2), _info()).problems == []
    (problem,) = check_request(_request(tmp_path, 3), _info()).problems
    assert "at most 2" in problem


def test_a_model_without_input_references_is_a_problem(tmp_path: Path) -> None:
    info = ModelInfo("author/model", ({"supported_parameters": SIZE_PARAMS},))
    (problem,) = check_request(_request(tmp_path, 1), info).problems
    assert "takes no input pictures" in problem


def test_grid_boxes_reproduces_the_owners_cut() -> None:
    boxes = grid_boxes(2000, 581, 6, 1, 10)
    assert [b[0] for b in boxes] == [0, 335, 670, 1005, 1340, 1675] and all(b[2:] == (325, 581) for b in boxes)


def test_split_sheet_writes_named_scaled_panels(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    Image.new("RGB", (60, 30), (10, 20, 30)).save(sheet)
    panels = split_sheet(sheet, out_dir=tmp_path / "out", names=["a", "b"], columns=2, scale=2)
    assert [p.path.name for p in panels] == ["a.png", "b.png"] and Image.open(panels[0].path).size == (60, 60)


@pytest.mark.parametrize("kwargs, words", [
    ({"columns": 7, "gap": 1}, "whole pixels"),   # (60 - 6 * 1) / 7 is not a whole number
    ({"boxes": ["0,0,999,999"]}, "not inside"),
    ({"columns": 2, "names": ["a"]}, "name"),
    ({"columns": 2, "names": ["a", "../x"]}, "file name"),
    ({"columns": 2, "boxes": ["0,0,1,1"]}, "either"),
    ({}, "say how"),
    ({"columns": 2, "scale": 0}, "scale"),
])
def test_split_sheet_refuses_bad_input(tmp_path: Path, kwargs: dict[str, Any], words: str) -> None:
    sheet = tmp_path / "sheet.png"
    Image.new("RGB", (60, 30)).save(sheet)
    with pytest.raises(VidgenError, match=words):
        split_sheet(sheet, out_dir=tmp_path / "out", **kwargs)


def test_file_refs_label_the_role_sentence_in_input_order(make_project) -> None:
    root = in_guide_project(make_project, refs=[{"file": "assets/start.png", "shows": "ben"}])
    prompt = the_shot(root).prompt
    assert "@image1 shows ben." in prompt   # `shows` is written as given when it names no character of the cast
