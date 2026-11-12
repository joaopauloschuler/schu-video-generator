"""Prompts of shots with a guide video (DESIGN.md §113.12): no close-up wording, the sheet's framing
instructions left out of the prompt (and noted in the plan), unguided shots unchanged, a shot paid
for under the earlier wording not paid again by itself. Nothing is sent, paid or rendered."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from typing import Any

import pytest

from vidgen import cli
from vidgen.project import Project
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
from vidgen.videogen.run import generate_clip
from vidgen.videogen.sheets import character_sheet
from vidgen.videogen.shots import EARLIER_WORDING_BLOCKED, GUIDE_PROMPTS, project_shots, without_framing
from vidgen.videogen.workflow import run_shots
from test_videogen_3d_guide import guide_config
from test_videogen_input_freshness import config, cut, edit, plan_of, quiet, shot_of, stub_render
from test_videogen_shots import CATALOG, TALK, shot_config

MODEL = "bytedance/seedance-2.0-fast"
APPEARANCE = "A cartoon woman with an oversized head, big round eyes, short black hair, a red jacket and dark trousers, soft film look"
FRAMING_SENTENCE = (
    "Exactly one single character, alone and centred in the middle of the picture, with one complete face and the whole body visible, "
    "not a split image, not two figures"
)
EXAMPLE = f"{APPEARANCE}. {FRAMING_SENTENCE}."
#: The prompt of an unguided talking shot on the code before guided wording existed (Step 312).
UNGUIDED_TALKING_PROMPT = (
    'Talking close-up of Ana, facing the camera, speaking. Characters: Ana (a tall woman in a yellow raincoat). Ana says: "One two three four five '
    'six seven eight." Style: palette teal, orange; present day; 35 mm; soft light. No on-screen text, captions, subtitles or logos.'
)


def guided_talking(guide: Any = True, *, sheet: str = EXAMPLE) -> dict[str, Any]:
    """:data:`TALK` as a seedance talking shot with a guide, no first frame, and ``sheet`` as Ana's sheet prompt."""
    beat = {**TALK, "generated_shot": {"kind": "talking", "model": MODEL, "guide": guide, "first_frame": "none"}}
    data = shot_config(beat)
    data["characters"][0]["reference_sheet"] = {"prompt": sheet, "views": ["front"]}
    return data


def the_shot(make_project, data: dict[str, Any], folder: str = "p"):
    (shot,) = project_shots(Project.load(make_project(data, folder=folder)), CATALOG)
    return shot


def paid_project(make_project):
    """A cut guided action shot with :data:`EXAMPLE`'s framing words and its clip paid under the earlier wording."""
    data = config(shot_of("a", guide=True, characters=["ana"], refs=[]))
    data["characters"] = [{"name": "ana", "reference_sheet": {"prompt": EXAMPLE, "views": ["front"]}}]
    root = make_project(data)
    cut(root, guide=True, render=stub_render(root))
    item = plan_of(root)
    api = MockOpenRouter()
    assert item.shot.earlier_prompt
    generate_clip(root, Project.load(root).config.videogen, replace(item.request, prompt=item.shot.earlier_prompt), pay=True, provider=MockVideoProvider(api), catalog=CATALOG)
    assert len(api.submits) == 1
    return root, api


# ----- the guided talking wording -------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("guide", [True, "render"])
def test_a_guided_talking_shot_asks_for_no_close_up(make_project, guide: Any) -> None:
    prompt = the_shot(make_project, guided_talking(guide)).prompt
    assert prompt.startswith("Ana, speaking.") and "close-up" not in prompt and "facing the camera" not in prompt


def test_an_unguided_talking_shot_is_byte_identical(make_project) -> None:
    shot = the_shot(make_project, shot_config(TALK))
    assert shot.prompt == UNGUIDED_TALKING_PROMPT and shot.earlier_prompt == "" and not any("left out" in n for n in shot.notes)


def test_a_guide_pass_keeps_its_sentence_and_loses_the_close_up(make_project) -> None:
    prompt = the_shot(make_project, guide_config("depth", kind="talking")).prompt
    assert GUIDE_PROMPTS["depth"] + "." in prompt and prompt.startswith("Ana, speaking.") and "close-up" not in prompt


# ----- the sheet's framing words --------------------------------------------------------------------


def test_the_example_sentence_is_left_out_and_the_appearance_kept() -> None:
    kept, removed = without_framing(EXAMPLE)
    assert kept == APPEARANCE and removed == [FRAMING_SENTENCE]


def test_the_prompt_note_and_the_sheet_of_the_example(make_project) -> None:
    root = make_project(guided_talking())
    project = Project.load(root)
    (shot,) = project_shots(project, CATALOG)
    assert f"Characters: Ana ({APPEARANCE})." in shot.prompt and "centred" not in shot.prompt and "split image" not in shot.prompt
    (note,) = [n for n in shot.notes if "left out" in n]
    assert FRAMING_SENTENCE in note and "the guide decides" in note and "sheet itself is unchanged" in note
    sheet = character_sheet(project, "ana")
    assert sheet is not None and sheet.notes == EXAMPLE.rstrip(".")   # the sheet's own text
    assert "centred in the middle of the picture" in sheet.pictures[0].request.prompt


def test_the_plan_text_and_json_show_the_note(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(guided_talking())
    monkeypatch.setattr("vidgen.videogen.models.load_catalog", lambda *a, **k: CATALOG)
    assert cli.main(["generate", "plan", str(root)]) == 0
    assert "note: Ana's sheet words left out" in capsys.readouterr().out
    assert cli.main(["generate", "plan", str(root), "--json"]) == 0
    (doc,) = json.loads(capsys.readouterr().out)["shots"]
    assert any(n.startswith("Ana's sheet words left out") for n in doc["notes"])


def test_a_sheet_without_framing_words_adds_no_note_and_is_unchanged(make_project) -> None:
    words = "A tall woman in a yellow raincoat, short curly hair. She walks with a limp; soft voice"
    shot = the_shot(make_project, guided_talking(sheet=words))
    assert f"Characters: Ana ({words})." in shot.prompt and not any("left out" in n for n in shot.notes)
    assert without_framing(words) == (words, [])


def test_an_unguided_shot_keeps_the_framing_sentence(make_project) -> None:
    data = shot_config(TALK)
    data["characters"][0]["reference_sheet"] = {"prompt": EXAMPLE, "views": ["front"]}
    shot = the_shot(make_project, data)
    assert FRAMING_SENTENCE in shot.prompt and not any("left out" in n for n in shot.notes)


@pytest.mark.parametrize(("text", "kept"), [
    ("A woman in a red jacket, centred in the frame, full body", "A woman in a red jacket"),
    ("Full-body portrait of a woman in a red jacket", "Full-body portrait of a woman in a red jacket"),   # appearance in the framing clause: left whole
    ("Dark-haired woman, centred; walks with a limp", "Dark-haired woman, walks with a limp"),
    ("Tall, wiry man. Front view, head and shoulders. Grey beard", "Tall, wiry man. Grey beard"),
])
def test_appearance_stays_when_framing_shares_its_sentence(text: str, kept: str) -> None:
    assert without_framing(text)[0] == kept


@pytest.mark.parametrize("text", ["A self-centred clerk in a grey suit", "A woman with a centre parting", "Dark-framed glasses, full-bodied red wine in hand"])
def test_ordinary_words_are_not_framing(text: str) -> None:
    assert without_framing(text) == (text, [])


# ----- a shot paid for under the earlier wording ---------------------------------------------------


@pytest.mark.slow
def test_a_paid_guided_shot_is_blocked_not_paid_again(make_project) -> None:
    root, api = paid_project(make_project)
    item = plan_of(root)
    assert item.shot.blocked == [EARLIER_WORDING_BLOCKED] and not item.cached and item.previous_job is None
    report = run_shots(Project.load(root), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=quiet)
    assert [s.status for s in report.shots] == ["blocked"] and len(api.submits) == 1


@pytest.mark.slow
def test_a_job_in_the_ledger_counts_without_its_clip(make_project) -> None:
    root, _api = paid_project(make_project)
    shutil.rmtree(root / "assets" / "generated_video")
    assert plan_of(root).shot.blocked == [EARLIER_WORDING_BLOCKED]


@pytest.mark.slow
def test_a_new_seed_lets_the_new_wording_be_paid(make_project) -> None:
    root, api = paid_project(make_project)
    edit(root, lambda d: d["scenes"][0]["beats"][0]["generated_shot"].update(seed=7))
    assert plan_of(root).shot.blocked == []
    report = run_shots(Project.load(root), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=quiet)
    assert [s.status for s in report.shots] == ["paid"] and len(api.submits) == 2


def test_a_guided_shot_never_paid_is_not_blocked(make_project) -> None:
    data = config(shot_of("a", guide=True, characters=["ana"], refs=[]))
    data["characters"] = [{"name": "ana", "reference_sheet": {"prompt": EXAMPLE, "views": ["front"]}}]
    root = make_project(data)
    cut(root, guide=True, render=stub_render(root))
    assert plan_of(root).shot.blocked == []
