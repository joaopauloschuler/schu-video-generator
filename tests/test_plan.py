"""``vidgen plan`` (Step 58): outline parsing, sentences and beats, compression, cue -> scene type
mapping, the commented YAML, the command and the committed example (a golden file)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen.cli import main, validate_all
from vidgen.languages import language_rules
from vidgen.outline import Code, Heading, Image, ListBlock, Math, Paragraph, Quote, Table, parse_outline, plain
from vidgen.plan import Plan, PlannedScene, PlanOptions, make_plan
from vidgen.plan_yaml import plan_config, plan_yaml, write_plan
from vidgen.project import Project
from vidgen.prose import compress, merge_short, narration_beats, split_long, split_sentences, words

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "plan"


def plan_of(text: str, **options: Any) -> Plan:
    return make_plan(parse_outline(text), PlanOptions(**options))


def scenes_of(text: str, **options: Any) -> list[PlannedScene]:
    return plan_of(text, **options).scenes


def one(text: str, kind: str, **options: Any) -> PlannedScene:
    """The only scene of type ``kind`` planned from ``text``."""
    found = [s for s in scenes_of(text, **options) if s.type == kind]
    assert len(found) == 1, [(s.type, s.params) for s in scenes_of(text, **options)]
    return found[0]


# ----- the outline reader -------------------------------------------------------------------------


def test_outline_blocks() -> None:
    text = """---
author: me
---
# Title

Intro line one
continues here.

Setext heading
--------------

<!-- a note
over lines -->
- one
- two
  more of two
  - nested

1. first
2) second

| a | b |
|---|---:|
| x | 1 |

```py
print(1)
```

$$
a = b \\\\
c = d
$$

$$x^2$$

![A chart](img/chart.png "The chart")

> Be brief.
> — Someone, Somewhere

***
"""
    blocks = parse_outline(text)
    assert blocks[0] == Heading(1, "Title")
    assert blocks[1] == Paragraph("Intro line one\ncontinues here.")
    assert blocks[2] == Heading(2, "Setext heading")
    lst = blocks[3]
    assert isinstance(lst, ListBlock) and not lst.ordered
    assert [i.text for i in lst.items] == ["one", "two more of two"] and lst.items[1].children == ("nested",)
    numbered = blocks[4]
    assert isinstance(numbered, ListBlock) and numbered.ordered and [i.text for i in numbered.items] == ["first", "second"]
    assert blocks[5] == Table(("a", "b"), (("x", "1"),))
    assert blocks[6] == Code("print(1)", "py")
    assert blocks[7] == Math(("a = b", "c = d"))
    assert blocks[8] == Math(("x^2",))
    assert blocks[9] == Image("A chart", "img/chart.png", "The chart")
    assert blocks[10] == Quote("Be brief.", "Someone", "Somewhere")
    assert len(blocks) == 11


def test_plain_text_script_headings() -> None:
    blocks = parse_outline("The title\n\nA first paragraph.\nStill it.\n\nPart two\n\nMore text here.\n", plain=True)
    assert blocks == [Heading(1, "The title"), Paragraph("A first paragraph.\nStill it."), Heading(2, "Part two"), Paragraph("More text here.")]


def test_plain_removes_inline_markdown_and_collects_links() -> None:
    result = plain("Use **bold**, *it*, `code`, [the docs](https://x.org/a) and <https://y.org>, see https://z.org/b. snake_case stays")
    assert result.text == "Use bold, it, code, the docs and https://y.org, see https://z.org/b. snake_case stays"
    assert result.links == ["https://x.org/a", "https://y.org", "https://z.org/b"]


# ----- sentences, beats, compression ------------------------------------------------------------------


def test_sentences_english() -> None:
    text = "Dr. Smith measured 3.5 ms, e.g. in tests. It works! J. R. R. Tolkien wrote it. The U.S. Army agreed. Done?"
    assert split_sentences(text) == ["Dr. Smith measured 3.5 ms, e.g. in tests.", "It works!", "J. R. R. Tolkien wrote it.", "The U.S. Army agreed.", "Done?"]
    assert split_sentences("We tested apples, pears, etc. Then we ate.") == ["We tested apples, pears, etc.", "Then we ate."]
    assert split_sentences("Wait... what happened") == ["Wait... what happened"]


def test_sentences_portuguese() -> None:
    text = "O Sr. Silva chegou às 3,5 h, p.ex. cedo. Depois saiu. Custou R$ 3,50 etc. Fim."
    assert split_sentences(text, "pt-BR") == ["O Sr. Silva chegou às 3,5 h, p.ex. cedo.", "Depois saiu.", "Custou R$ 3,50 etc.", "Fim."]


def test_beats_follow_the_pacing_rule() -> None:
    text = (
        "Most teams think their deploys are fast, but when you measure the time from a merged pull request "
        "to running in production, the median is more than two days. That is slow. Really slow."
    )
    beats = narration_beats(text)
    assert " ".join(beats) == " ".join(text.split())
    assert all(6 <= words(b) <= 15 for b in beats), beats
    assert beats[0].endswith(",")  # cut at a clause mark


def test_split_long_prefers_phrase_boundaries() -> None:
    sentence = "The cache keeps every answer close to the code, and the database only sees the rare misses that remain"
    pieces = split_long(sentence)
    assert pieces == ["The cache keeps every answer close to the code,", "and the database only sees the rare misses that remain"]
    assert split_long("Short sentence here.") == ["Short sentence here."]


def test_merge_short_joins_tiny_beats() -> None:
    assert merge_short(["That is slow.", "Really slow.", "Then we fixed the whole pipeline in a week."]) == [
        "That is slow. Really slow. Then we fixed the whole pipeline in a week."
    ]
    long = ["We measured every request for a whole week.", "Ok.", "Then we cached the slowest endpoint of the app."]
    merged = merge_short(long)
    assert all(6 <= words(b) <= 15 for b in merged) and " ".join(merged) == " ".join(long)
    assert merge_short([]) == []


def test_beats_in_portuguese() -> None:
    text = "Equipes com testes entregam mais rápido, e os erros caem pela metade quando o pipeline bloqueia o merge de código sem testes."
    beats = narration_beats(text, "pt-BR")
    assert len(beats) == 2 and all(words(b) <= 15 for b in beats)
    assert beats[1].split()[0] in language_rules("pt-BR").conjunctions  # cut before a conjunction ("quando")


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("In this video we will look at why small models win", 6, "Look at why small models win"),
        ("Slow reviews: waiting two days for a review", 6, "Slow reviews"),
        ("Step 2: Measure the baseline", 6, "Measure the baseline"),
        ("Why does it matter?", 6, "Why does it matter?"),
        ("Basically, there are three really important steps to follow", 6, "Three important steps to follow"),
        ("On a miss, query the database", 3, "Query the database"),
        ("Store the result with an expiry time", 3, "Store result"),
        ("Account balances and stock levels must always be exact", 6, "Account balances and stock levels"),
        ("Sign in", 3, "Sign in"),
        ("The model (a small one) works", 6, "The model works"),
    ],
)
def test_compress(text: str, limit: int, expected: str) -> None:
    assert compress(text, limit) == expected


def test_compress_portuguese() -> None:
    assert compress("Neste vídeo vamos ver por que os modelos pequenos ganham sempre", 5, "pt-BR") == "Ver por que modelos pequenos"
    assert compress("Rode os testes a cada commit", 3, "pt-BR") == "Rode testes"


# ----- cues -> scene types ----------------------------------------------------------------------------


def test_bullet_list_becomes_bullets_with_one_beat_per_item() -> None:
    scene = one("## Tips\n\n- Keep each function under twenty lines long\n- Name things after what they do\n- Delete dead code without mercy\n", "bullets")
    assert scene.params["heading"] == "Tips"
    assert all(words(i) <= 6 for i in scene.params["items"])
    assert scene.beats == ["Keep each function under twenty lines long.", "Name things after what they do.", "Delete dead code without mercy."]
    assert any("repeats the items" in t for t in scene.todos)


def test_short_nouns_with_icons_become_icon_grid() -> None:
    scene = one("## Benefits\n\nIt pays off.\n\n- Speed\n- Cost\n- Security\n\nAnswers come back faster. The bill gets smaller. Fewer moving parts can break.\n", "icon_grid")
    assert [i["label"] for i in scene.params["items"]] == ["Speed", "Cost", "Security"]
    assert all(i["icon"] for i in scene.params["items"]) and len({i["icon"] for i in scene.params["items"]}) == 3
    assert scene.beats[0] == "It pays off. Answers come back faster."  # a short intro joins the first beat
    assert any("icon choice" in t for t in scene.todos)


def test_short_nouns_without_icons_stay_bullets() -> None:
    scene = one("## Names\n\n- Qwxyz\n- Blorpt\n", "bullets")
    assert scene.params["items"] == ["Qwxyz", "Blorpt"]
    assert any("placeholder" in t for t in scene.todos)


def test_numbered_steps_become_process() -> None:
    scene = one("## Ship it\n\n1. Write the code\n2. Run the tests\n3. Deploy to production\n", "process")
    assert scene.params["stages"] == ["Write the code", "Run the tests", "Deploy to production"]
    assert len(scene.beats) == 3


def test_dated_items_become_timeline() -> None:
    scene = one("## History\n\n- 1957: Sputnik reaches orbit\n- 1961: Gagarin flies\n- July 1969: Apollo 11 lands\n", "timeline")
    assert [e["date"] for e in scene.params["events"]] == [1957, 1961, "July 1969"]
    assert scene.params["events"][0]["title"] == "Sputnik reaches orbit"


def test_long_numbered_list_becomes_numbered_bullets() -> None:
    items = "\n".join(f"{n}. Item number {n} of the list" for n in range(1, 10))
    scene = one(f"## Many\n\n{items}\n", "bullets")
    assert scene.params["numbered"] is True and scene.params["dim_previous"] is True
    assert any("limit is 5" in t for t in scene.todos)


def test_table_becomes_table() -> None:
    text = "## Results\n\n| Model | Params | Accuracy |\n|---|---|---|\n| Base | 110 | 0.812 |\n| Sparse | 55 | 0.809 |\n\nThe base model is big. The sparse one is half.\n"
    scene = one(text, "table")
    assert scene.params["header"] == ["Model", "Params", "Accuracy"]
    assert scene.params["rows"] == [["Base", 110, 0.812], ["Sparse", 55, 0.809]]
    assert len(scene.beats) == 2 and "reveal" not in scene.params


def test_table_with_few_beats_reveals_all() -> None:
    text = "## Results\n\n| A | B | C |\n|---|---|---|\n| x | y | z |\n| u | v | w |\n| p | q | r |\n"
    scene = one(text, "table")
    assert scene.params["reveal"] == "all" and len(scene.beats) == 1


def test_numeric_two_column_table_becomes_bar_chart() -> None:
    text = "## Latency\n\n| Where | Time |\n|---|---|\n| Memory | 0.1 ms |\n| Disk | 10 ms |\n| Network | 250 ms |\n\nEach step is slower. The network is the slowest.\n"
    scene = one(text, "bar_chart")
    assert scene.params["labels"] == ["Memory", "Disk", "Network"]
    assert scene.params["values"] == [0.1, 10, 250] and scene.params["unit"] == " ms"
    assert scene.params["highlight"] == "Network"  # named by the last beat


def test_money_column_gets_a_value_format() -> None:
    scene = one("## Cost\n\n| Plan | Price |\n|---|---|\n| Basic | $1,200 |\n| Pro | $2,500 |\n", "bar_chart")
    assert scene.params["values"] == [1200, 2500] and scene.params["value_format"] == "${:,.0f}"


def test_short_code_becomes_code_with_highlights() -> None:
    text = "## Code\n\nWe load the data.\n\n```python\ndata = load()\n\nmodel = fit(data)\nsave(model)\n```\n\nThen we fit and save.\n"
    scene = one(text, "code")
    assert scene.params["language"] == "python" and scene.params["highlight"] == ["1", "3-4"]
    assert scene.beats == ["We load the data.", "Then we fit and save."]


def test_long_code_becomes_walkthrough() -> None:
    code = "\n\n".join(f"def f{n}():\n    a = {n}\n    return a" for n in range(6))
    scene = one(f"## Walk\n\n```py\n{code}\n```\n", "code_walkthrough")
    assert len(scene.params["steps"]) == len(scene.beats) == 6
    assert scene.params["steps"][0] == {"lines": "1-3"} and scene.params["language"] == "python"


def test_maths() -> None:
    assert one("## F\n\n$$E = mc^2$$\n", "equation").params["latex"] == "E = mc^2"
    assert one("## F\n\n$$a = b$$\n\n$$b = c$$\n", "equation").params["latex"] == ["a = b", "b = c"]
    scene = one("## Solve\n\n$$\n2x + 3 = 11 \\\\\n2x = 8 \\\\\nx = 4\n$$\n", "equation_derivation")
    assert scene.params["steps"] == ["2x + 3 = 11", "2x = 8", "x = 4"] and len(scene.beats) == 3


def test_image_found_is_copied_else_generated(tmp_path: Path) -> None:
    (tmp_path / "pics").mkdir()
    (tmp_path / "pics" / "lab.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    plan = plan_of("## Lab\n\n![Our lab](pics/lab.png)\n\nEverything ran here.\n", base=tmp_path)
    scene = next(s for s in plan.scenes if s.type == "image")
    assert scene.params["path"] == "assets/lab.png" and scene.params["caption"] == "Our lab"
    assert plan.assets == {"assets/lab.png": (tmp_path / "pics" / "lab.png").resolve()}
    missing = one("## Harbour\n\n![a quiet harbour at dawn](nowhere.png)\n", "image", base=tmp_path)
    assert missing.params["generate"] == "a quiet harbour at dawn" and any("not found" in t for t in missing.todos)


def test_quote_keeps_two_beats() -> None:
    scenes = scenes_of(
        "## Simple\n\n> Simplicity is prerequisite for reliability.\n> — Edsger W. Dijkstra\n\n"
        "Simple systems fail less often than clever ones. They are easier to fix at three in the morning. "
        "And they are easier to explain to a new team.\n"
    )
    quote = next(s for s in scenes if s.type == "quote")
    assert quote.params == {"text": "Simplicity is prerequisite for reliability.", "author": "Edsger W. Dijkstra"}
    assert len(quote.beats) == 2
    assert scenes[-1].type in ("bullets", "text_card") and scenes[-1] is not quote


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Teams that automate deploys ship 46% more often than the rest.", {"value": 46, "suffix": "%", "label": "more often than the rest"}),
        ("A cache makes the page 40x faster.", {"value": 40, "suffix": "x"}),
        ("The bill went from 120 to 15 dollars a month.", {"value": 15, "comparison": {"value": 120, "kind": "before"}}),
        ("The startup raised $3.5 million last year.", {"prefix": "$", "value": 3.5, "suffix": "M"}),
    ],
)
def test_prominent_numbers_become_stat(sentence: str, expected: dict[str, Any]) -> None:
    scene = one(f"## Numbers\n\n{sentence}\n", "stat")
    assert expected.items() <= scene.params.items()


def test_portuguese_stat_uses_decimal_comma() -> None:
    scene = one("## Números\n\nO tempo caiu para 3,5 vezes menos.\n", "stat", language="pt-BR")
    assert scene.params["value"] == 3.5 and scene.params["decimal_mark"] == "," and scene.params["thousands"] == "."


def test_vs_heading_with_two_lists_becomes_comparison() -> None:
    text = "## Monolith vs Microservices\n\nMonolith:\n\n- One deploy\n- Simple setup\n\nMicroservices:\n\n- Many deploys\n- Network failures\n"
    scene = one(text, "comparison")
    assert [c["heading"] for c in scene.params["columns"]] == ["Monolith", "Microservices"]
    assert scene.params["columns"][1]["points"] == ["Many deploys", "Network failures"] and scene.params["vs"] == "vs"


def test_pros_and_cons_lists_become_comparison() -> None:
    text = "## Remote work\n\nPros:\n\n- No commute\n- Quiet focus\n\nCons:\n\n- Lonely days\n"
    scene = one(text, "comparison")
    assert [c.get("tone") for c in scene.params["columns"]] == ["positive", "negative"] and "vs" not in scene.params


def test_vs_heading_over_prose_becomes_comparison() -> None:
    text = "## Tabs vs Spaces\n\nTabs let every reader pick a width. Spaces look the same everywhere you paste them.\n"
    scene = one(text, "comparison")
    assert [len(c["points"]) for c in scene.params["columns"]] == [1, 1]


def test_arrow_chain_becomes_diagram() -> None:
    scene = one("## Flow\n\nRequest -> Cache -> Database\nCache -> Logs\n", "diagram")
    assert [n["id"] for n in scene.params["nodes"]] == ["request", "cache", "database", "logs"]
    assert scene.params["edges"] == ["request -> cache", "cache -> database", "cache -> logs"]


def test_prose_without_cues() -> None:
    assert one("## Idea\n\nOne thought on its own here.\n", "text_card").params["text"] == "Idea"
    scene = one(
        "## Why\n\nMeetings are cheap to schedule and expensive to attend. Nobody ever sees the total bill of them. "
        "Calendars fill up one small invitation at a time.\n",
        "bullets",
    )
    assert len(scene.params["items"]) == len(scene.beats) == 3


# ----- structure ----------------------------------------------------------------------------------------


def test_title_subtitle_and_hook() -> None:
    scenes = scenes_of("# Caching\n\nA short explainer.\n\nYour app feels slow, and the database is why.\n")
    assert scenes[0].type == "title" and scenes[0].params == {"title": "Caching", "subtitle": "A short explainer"}
    assert scenes[0].beats == ["Your app feels slow, and the database is why."]


def test_an_opening_number_comes_before_the_title() -> None:
    scenes = scenes_of("# Meetings\n\nEngineers spend 30% of their week in meetings.\n")
    assert [s.type for s in scenes] == ["stat", "title"]
    assert any("placeholder" in t for t in scenes[1].todos)


def test_title_option_and_default_title() -> None:
    assert plan_of("# Doc title\n\nText here for the title.\n", title="Mine").title == "Mine"
    assert plan_of("Just a paragraph of text.\n", default_title="My file").title == "My file"


def test_summary_ends_with_end_card_and_links() -> None:
    text = "## Part\n\nSome words here to say.\n\n## Conclusion\n\n- Measure first\n- Cache second\n- Expire always\n\nTry it today. Code at [GitHub](https://github.com/me/x).\n"
    scenes = scenes_of(text)
    assert scenes[-1].type == "end_card"
    assert scenes[-1].params["lines"] == ["github.com/me/x"] and scenes[-1].beats == ["Try it today. Code at GitHub."]
    assert scenes[-2].type in ("bullets", "icon_grid")


def test_no_closing_section_is_noted() -> None:
    plan = plan_of("## Only part\n\nNothing else to say here.\n")
    assert any("no closing section" in n for n in plan.notes)


def long_outline(sections: int = 4) -> str:
    prose = " ".join(f"This is sentence number {n} of the section, and it carries about twelve words." for n in range(8))
    parts = "\n\n".join(f"## Section {k}\n\n{prose}" for k in range(1, sections + 1))
    return f"# Long video\n\n{parts}\n\n## Summary\n\nThanks for watching this one.\n"


def test_long_videos_get_chapter_cards_and_a_progress_bar() -> None:
    plan = plan_of(long_outline())
    cards = [s for s in plan.scenes if s.type == "chapter"]
    assert plan.chapters and [c.params["number"] for c in cards] == [1, 2, 3, 4]
    assert all(c.duration and not c.beats for c in cards)
    assert plan_config(plan)["overlays"] == [{"type": "progress_bar"}]
    short = plan_of("# Short\n\n## A\n\nWords.\n\n## B\n\nWords.\n\n## C\n\nWords.\n")
    assert not short.chapters and not any(s.type == "chapter" for s in short.scenes)


def test_subheadings_are_scene_boundaries() -> None:
    text = "## Part\n\n### First\n\n- Alpha item here\n- Beta item here\n\n### Second\n\n- Gamma item here\n- Delta item here\n"
    headings = [s.params.get("heading") for s in scenes_of(text) if s.type == "bullets"]
    assert headings == ["First", "Second"]


def test_scene_ids_are_unique_and_valid() -> None:
    plan = plan_of(long_outline(5))
    ids = [s.id for s in plan.scenes]
    assert len(ids) == len(set(ids)) and all(i.replace("_", "").isalnum() and i.isascii() for i in ids)


def test_long_beats_and_parentheses_get_todos() -> None:
    scene = one("## Note\n\nThis sentence (with an aside) is fine.\n", "text_card")
    assert any("parentheses" in t for t in scene.todos)


# ----- YAML and validation ------------------------------------------------------------------------------

RICH = """# Rich outline

The whole tour.

Every scene type the planner knows, in one file.

## Lists

- Speed
- Cost
- Security

1. Write the code
2. Run the tests

- 1957: Sputnik
- 1969: Apollo 11

## Data

| Where | Time |
|---|---|
| Memory | 0.1 ms |
| Network | 250 ms |

| Model | Params | Accuracy |
|---|---|---|
| Base | 110 | 0.812 |

## Why it matters

Teams ship 46% more often with tests.

## Code and maths

```python
x = 1
y = 2
```

$$E = mc^2$$

## Pictures

![a quiet harbour at dawn](missing.png)

> Simplicity is prerequisite for reliability.
> — Edsger W. Dijkstra

Request -> Cache -> Database

## Tabs vs Spaces

Tabs:

- Pick a width

Spaces:

- Same everywhere

## Summary

Try it today at https://example.org.
"""


@pytest.mark.parametrize("fmt", ["16:9", "9:16"])
def test_rich_outline_validates(tmp_path: Path, fmt: str) -> None:
    plan = plan_of(RICH)
    types = {s.type for s in plan.scenes}
    assert types >= {"title", "icon_grid", "process", "timeline", "bar_chart", "table", "stat", "code", "equation", "image", "quote", "diagram", "comparison", "end_card"}
    result = write_plan(plan, tmp_path / "proj", fmt=fmt, preset="light_academic", source="rich.md")
    project = Project.load(result.config)
    problems, _ = validate_all(project)
    assert problems == []
    assert project.config.format.height == (1920 if fmt == "9:16" else 1080)


def test_yaml_round_trips_with_comments() -> None:
    plan = plan_of(RICH, language="en")
    text = plan_yaml(plan, source="rich.md")
    assert yaml.safe_load(text) == plan_config(plan)
    assert text.count("# TODO:") == plan.todo_count
    assert text.count("  # plan:") == len(plan.scenes)
    assert "from rich.md" in text and "\nlanguage: en\n" in text
    assert "code: |-\n        x = 1\n        y = 2\n" in text  # code as a literal block


def test_yaml_writer_edge_cases() -> None:
    params = {
        "code": "    indented first line\nback\n\nafter a blank",
        "latex": "\\frac{a}{b} = it's",
        "words": ["yes", "no", "null", "on", "plain", "with: colon", "#hash", "1.5"],
        "numbers": [0.1, 1e-07, 3, -2.5, True, None],
        "nested": [{"a": 1, "b": [1, 2]}, {"only": "x"}],
        "empty": [],
        "long": ["word " * 30],
    }
    plan = Plan("T: a title", [PlannedScene("s", "text_card", params, ["Ünïcode — and \"quotes\"."], reason="why", todos=["check"])])
    text = plan_yaml(plan)
    assert yaml.safe_load(text) == plan_config(plan)


def test_plan_is_deterministic() -> None:
    assert plan_yaml(plan_of(RICH)) == plan_yaml(plan_of(RICH))


def test_portuguese_outline_validates(tmp_path: Path) -> None:
    text = "# Testes\n\nUm guia rápido.\n\n## Como começar\n\n1. Escreva um teste para cada bug\n2. Rode os testes a cada commit\n\n## Conclusão\n\nComece hoje com um único teste.\n"
    plan = plan_of(text, language="pt-BR")
    result = write_plan(plan, tmp_path / "pt.yaml")
    project = Project.load(result.config)
    assert project.config.language == "pt-BR" and validate_all(project)[0] == []
    process = next(s for s in plan.scenes if s.type == "process")
    assert process.params["stages"] == ["Escreva teste", "Rode testes"]


def test_write_plan_refuses_to_overwrite(tmp_path: Path) -> None:
    from vidgen.errors import VidgenError

    plan = plan_of("## A\n\nSome words to say here.\n")
    target = tmp_path / "proj"
    result = write_plan(plan, target)
    assert result.created and (target / ".gitignore").is_file() and (target / "assets").is_dir()
    with pytest.raises(VidgenError, match="not empty"):
        write_plan(plan, target)
    again = write_plan(plan, target, force=True)
    assert not again.created
    (tmp_path / "x.yaml").write_text("title: x\n", encoding="utf-8")
    with pytest.raises(VidgenError, match="already exists"):
        write_plan(plan, tmp_path / "x.yaml")


# ----- the command ----------------------------------------------------------------------------------------


def test_cli_plan_human(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "talk.md"
    source.write_text(RICH, encoding="utf-8")
    out_dir = tmp_path / "talk"
    assert main(["plan", str(source), "--output", str(out_dir), "--title", "My talk"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("planned ") and "TODOs to review" in out and f"created project in {out_dir}" in out
    assert yaml.safe_load((out_dir / "video.yaml").read_text(encoding="utf-8"))["title"] == "My talk"


def test_cli_plan_json_and_image_copy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "pic.png").write_bytes((ROOT / "src" / "vidgen" / "data" / "gallery" / "picture.png").read_bytes())
    source = tmp_path / "talk.txt"
    source.write_text("Talk\n\nA picture follows.\n\n![The lab](pic.png)\n", encoding="utf-8")
    assert main(["plan", str(source), "-o", str(tmp_path / "out" / "video.yaml"), "--json", "--language", "pt-br", "--format", "9:16"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["command"] == "plan" and doc["language"] == "pt-BR" and doc["format"] == "9:16"
    assert doc["scene_count"] == len(doc["scenes"]) and doc["beat_count"] >= 2 and doc["estimated_duration"] > 0
    assert doc["todo_count"] >= 1 and doc["problems"] == [] and doc["assets"] == ["assets/pic.png"]
    assert {"id", "type", "beats", "words", "estimated_duration", "reason", "todos"} <= doc["scenes"][0].keys()
    assert (tmp_path / "out" / "assets" / "pic.png").is_file()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["missing.md"], "no such file"),
        (["{src}", "--preset", "dark_tek"], "did you mean 'dark_tech'"),
        (["{src}", "--language", "not a tag"], "--language"),
    ],
)
def test_cli_plan_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], message: str) -> None:
    source = tmp_path / "a.md"
    source.write_text("## A\n\nWords here.\n", encoding="utf-8")
    argv = ["plan", *(a.replace("{src}", str(source)) for a in args), "-o", str(tmp_path / "p")]
    assert main(argv) == 1
    assert message in capsys.readouterr().err


# ----- the example (golden file) ----------------------------------------------------------------------------


def test_example_draft_is_current() -> None:
    """examples/plan/video.yaml is what `vidgen plan examples/plan/outline.md -o examples/plan/video.yaml
    --force` writes today; regenerate it after changing the planner."""
    blocks = parse_outline((EXAMPLE / "outline.md").read_text(encoding="utf-8"))
    plan = make_plan(blocks, PlanOptions(default_title="Outline", base=EXAMPLE))
    assert plan_yaml(plan, source="outline.md") == (EXAMPLE / "video.yaml").read_text(encoding="utf-8")


def test_example_draft_is_a_good_start() -> None:
    project = Project.load(EXAMPLE)
    assert validate_all(project)[0] == []
    types = [s.type for s in project.config.scenes]
    assert types[0] == "title" and types[-1] == "end_card" and types.count("chapter") >= 3
    assert {"stat", "icon_grid", "diagram", "process", "bar_chart", "equation", "code", "comparison", "quote"} <= set(types)
    assert 120 <= project.estimated_duration() <= 180
    beats = [b.text for s in project.config.scenes for b in s.beats]
    assert all(words(b) <= 20 for b in beats)
