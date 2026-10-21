"""Step 163: the narration-picture lint rules (``said_before_shown``, ``unsaid_reveal``): word
matching, labels from the layout dump, actions narrowing a label's arrival, the rules, the
config and the runner (faked renders, no Manim)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from test_lint import fake_render, text
from vidgen.config import LINT_RULES, SaidBeforeShownRule, UnsaidRevealRule, parse_config
from vidgen.lint import RULES, SceneContext, lint_project
from vidgen.lint.narration_rule import (
    NarrationPicture,
    ShowingAction,
    content_stems,
    first_mention,
    narration_picture,
    said_before_shown,
    shown_labels,
    spoken_words,
    stem,
    unsaid_reveal,
    words_of,
)
from vidgen.project import Project


def frame(beat: str, time: float, *objects: dict[str, Any], k: int = 1, n: int = 1) -> dict[str, Any]:
    return {"beat": beat, "k": k, "n": n, "time": time, "objects": list(objects)}


def label(oid: str, words: str, **keys: Any) -> dict[str, Any]:
    return {**text(oid, [0, 0, 10, 10], words), **keys}


def said(beat: str, start: float, sentence: str, step: float = 0.3) -> list[Any]:
    return spoken_words(beat, [(w, start + i * step) for i, w in enumerate(sentence.split())])


def context(labels: list[Any], spoken: list[Any], beats: list[str]) -> SceneContext:
    activity = {"fps": 10, "beats": [{"id": b, "start": 3.0 * i, "end": 3.0 * i + 2.5} for i, b in enumerate(beats)]}
    ctx = SceneContext("s", activity, Path("."))
    ctx.narration = NarrationPicture(labels, spoken, beats[0])
    return ctx


# ----- words ------------------------------------------------------------------------------------


def test_stems_case_plurals_and_verb_endings() -> None:
    assert {stem(w) for w in ("move", "moves", "moving", "moved")} == {"mov"}
    assert stem("databases") == stem("database") and stem("caches") == stem("cache") and stem("boxes") == stem("box")
    assert stem("queries") == stem("query") and stem("running") == stem("run") and stem("loss") == stem("losses") == "loss"
    assert stem("parameters", "pt") == "parameter" and stem("classe", "pt") == "classe"  # other languages: the plural s only
    assert words_of("Gómez's GPU-cache, 2.5x!") == ["gomez's", "gpu", "cache", "x"]
    assert content_stems(words_of("The Learning rate of a model")) == ["learn", "rat", "model"]
    assert content_stems(words_of("f(x) = x²")) == []   # single letters and numbers name nothing
    assert content_stems(words_of("o custo da rede"), "pt-BR") == ["custo", "rede"]


def test_first_mention_needs_every_word_close_together() -> None:
    spoken = said("b1", 0.0, "The learning rate sets how far each step of learning goes, at a rate we choose.")
    hit = first_mention(frozenset(content_stems(["learning", "rate"])), spoken)
    assert [w.word for w in hit] == ["learning", "rate"] and hit[0].time == pytest.approx(0.3)
    far = said("b1", 0.0, "Learning is slow when the step size is small, whatever the rate.")
    assert first_mention(frozenset(content_stems(["learning", "rate"])), far) == []
    across = said("b1", 0.0, "We start learning.") + said("b2", 2.0, "Rate matters.")
    assert first_mention(frozenset(content_stems(["learning", "rate"])), across) == []  # not across beats
    phrase = said("b1", 0.0, "What if a large language model could learn?")
    assert [w.word for w in first_mention(frozenset(content_stems(words_of("in Large Language Models"))), phrase)] == ["large", "language", "model"]


# ----- labels -----------------------------------------------------------------------------------


def dump(*frames: dict[str, Any]) -> dict[str, Any]:
    return {"frames": list(frames)}


def test_labels_from_the_layout_dump() -> None:
    title = label("t", "How a cache works")
    frames = dump(
        frame("b1", 2.8, title, label("r", "Request"), label("cap", "Then the cloud did it", overlay="captions")),
        frame("b2", 5.8, title, label("r", "Request"), label("c", "Cache"), label("v", "slope 0.50")),
        frame("b3", 8.8, title, label("r", "Request"), label("c", "Cache"), label("d", "Database"), label("v", "slope 1.20"),
              label("s", "A long sentence of a bullet point here"), label("q", "Boxes. Do not. Fly.", bubble="Ann"),
              label("n", "0.75"), label("faint", "Ghost", opacity=0.05)),
    )
    labels = shown_labels(frames)
    assert [(lb.text, lb.beat, lb.hidden_until) for lb in labels] == [
        ("How a cache works", "b1", None), ("Request", "b1", None), ("Cache", "b2", 2.8), ("slope 0.50", "b2", 2.8), ("Database", "b3", 5.8),
    ]   # no overlays, bubbles, sentences, numbers or faint texts; the live label is one label
    database = labels[-1]
    assert database.screen and not database.on_screen_elsewhere()
    assert labels[2].on_screen_elsewhere()   # the title already says "cache"


def test_actions_narrow_a_labels_arrival() -> None:
    frames = dump(frame("b1", 2.8, label("t", "Title")), frame("b2", 5.8, label("t", "Title"), label("c", "Cache hit"), label("d", "Decoder")))
    actions = [
        ShowingAction("b2", 4.4, label=frozenset(content_stems(["cache", "hit"]))),   # a callout with that label
        ShowingAction("b2", 5.0, anchor=frozenset(content_stems(["decoder"]))),       # a reveal at "@decoder"
        ShowingAction("b1", 1.0, anchor=frozenset(content_stems(["decoder"]))),       # another beat's: not it
    ]
    found = {lb.text: lb.hidden_until for lb in shown_labels(frames, actions)}
    assert found == {"Title": None, "Cache hit": 4.4, "Decoder": 5.0}


def test_mid_beat_stills_narrow_too() -> None:
    frames = dump(frame("b1", 2.8, label("t", "Title")), frame("b2", 4.0, label("t", "Title"), k=1, n=2),
                  frame("b2", 5.8, label("t", "Title"), label("d", "Decoder"), k=2, n=2))
    assert shown_labels(frames)[1].hidden_until == 4.0


# ----- the rules --------------------------------------------------------------------------------


def run_rule(labels: list[Any], spoken: list[Any], beats: list[str], **settings: Any) -> list[Any]:
    return list(said_before_shown(context(labels, spoken, beats), SaidBeforeShownRule(**settings)))


def test_said_before_shown_flags_a_label_named_beats_early() -> None:
    labels = shown_labels(dump(frame("b1", 4.8, label("r", "Request")), frame("b2", 7.8, label("r", "Request"), label("d", "Database"))))
    spoken = said("b1", 0.0, "A request asks the cache, and a miss goes to the database.", step=0.2) + said("b2", 5.0, "On the way back it is stored.")
    issues = run_rule(labels, spoken, ["b1", "b2"])
    assert len(issues) == 1
    issue = issues[0]
    assert issue.beat == "b1" and issue.time == pytest.approx(2.2) and issue.objects[0]["text"] == "Database"
    assert issue.message.startswith("beat 'b1' says \"database\" at 2.2 s, but 'Database' appears only in beat 'b2': show it on the word")
    assert 'at: "@database"' in issue.message and issue.value == pytest.approx(2.6) and issue.limit == 1.5
    assert run_rule(labels, spoken, ["b1", "b2"], min_lead=3.0) == []   # within min_lead of its arrival: fine


def test_said_before_shown_leaves_passing_mentions_and_on_screen_words() -> None:
    labels = shown_labels(dump(frame("b1", 2.8, label("h", "From config to video")), frame("b2", 5.8, label("h", "From config to video"), label("r", "Render"))))
    early = said("b1", 0.0, "A render starts by checking the config.")
    assert run_rule(labels, early + said("b2", 3.0, "Each scene is rendered on its own."), ["b1", "b2"], max_words=1) == []
    assert run_rule(labels, early + said("b2", 3.0, "Each scene is rendered on its own."), ["b1", "b2"]) == []   # named again as it shows
    assert len(run_rule(labels, early + said("b2", 3.0, "Each scene runs on its own."), ["b1", "b2"])) == 1
    titled = shown_labels(dump(frame("b1", 2.8, label("h", "Render farm")), frame("b2", 5.8, label("h", "Render farm"), label("r", "Render"))))
    assert run_rule(titled, early + said("b2", 3.0, "Each scene runs on its own."), ["b1", "b2"]) == []   # the heading says it


def test_said_before_shown_within_a_beat_on_a_word() -> None:
    frames = dump(frame("b1", 6.0, label("t", "Title"), label("g", "gradient")))
    spoken = said("b1", 0.0, "The gradient points uphill, so we step the other way down.", step=0.5)
    late = ShowingAction("b1", 4.5, anchor=frozenset(content_stems(["down"])))   # at: "@down" — no word of the label: not it
    assert run_rule(shown_labels(frames, [late]), spoken, ["b1"]) == []
    callout = ShowingAction("b1", 4.5, label=frozenset(content_stems(["gradient"])))   # a callout "gradient" at 4.5 s
    issues = run_rule(shown_labels(frames, [callout]), spoken, ["b1"])
    assert len(issues) == 1 and "'gradient' appears 4.0 s later" in issues[0].message


def test_unsaid_reveal() -> None:
    labels = shown_labels(dump(frame("b1", 2.8, label("t", "Pipeline")), frame("b2", 5.8, label("t", "Pipeline"), label("p", "Lisbon"), label("w", "Warsaw")),
                               frame("b3", 8.8, label("t", "Pipeline"), label("p", "Lisbon"), label("w", "Warsaw"), label("o", "Oslo"))))
    spoken = said("b1", 0.0, "Our servers.") + said("b2", 3.0, "Two more sites.") + said("b3", 6.0, "And one in Oslo.")
    issues = list(unsaid_reveal(context(labels, spoken, ["b1", "b2", "b3"]), UnsaidRevealRule()))
    assert [(i.beat, i.time) for i in issues] == [("b2", 3.0)]
    assert "beat 'b2' shows 'Lisbon', 'Warsaw', which the narration never names" in issues[0].message


# ----- config and runner ------------------------------------------------------------------------


def test_config_names_and_defaults() -> None:
    assert LINT_RULES[-3:-1] == ("said_before_shown", "unsaid_reveal") and list(RULES)[-3:-1] == ["said_before_shown", "unsaid_reveal"]
    assert RULES["said_before_shown"].default == "warning" and RULES["unsaid_reveal"].default == "info"
    rules = parse_config(minimal_config(lint={"rules": {"said_before_shown": {"min_lead": 2.5, "max_words": 3}, "unsaid_reveal": {"severity": "info"}}})).lint.rules
    assert rules.said_before_shown.min_lead == 2.5 and rules.unsaid_reveal.severity == "info"
    assert parse_config(minimal_config()).lint.rules.unsaid_reveal.severity == "off"


def diagram_project(make_project: Any, beats: list[dict[str, Any]], **extra: Any) -> Project:
    """A project whose first scene's render is faked: 'Request' from beat 1, 'Database' from
    beat 2 (beat-end stills at 2.8 s and 5.8 s; narration 0-2.5 s and 3-5.5 s)."""
    import json

    from vidgen.render.worker import scene_layout_path

    data = minimal_config(preview={"width": 854, "height": 480, "fps": 15}, **extra)
    data["scenes"][0]["beats"] = beats
    root = make_project(data)
    project = Project.load(root)
    request, database = text("r", [10, 10, 90, 30], "Request"), text("d", [10, 50, 90, 70], "Database")
    fake_render(project, "intro", [[request], [request, database]],
                activity={"beats": [{"id": b, "start": 3.0 * i, "end": 3.0 * i + 2.5, "busy": 2.5, "source": "estimate", "text": "x"}
                                    for i, b in enumerate(["intro_b1", "intro_b2"])]})
    path = scene_layout_path(project, True, "intro")
    doc = json.loads(path.read_text(encoding="utf-8"))
    for f, time in zip(doc["frames"], (2.8, 5.8)):
        f["time"] = time
    path.write_text(json.dumps(doc), encoding="utf-8")
    fake_render(project, "main", [[]])
    return project


def test_runner_reports_and_ignores(make_project: Any) -> None:
    beats = [{"text": "The database is asked only when the cache misses."}, {"text": "On the way back the answer is stored."}]
    project = diagram_project(make_project, beats)
    picture = narration_picture(project, *_dumps(project), max_words=4)
    assert [lb.text for lb in picture.labels] == ["Request", "Database"] and picture.first_beat == "intro_b1"
    assert [w.word for w in picture.spoken[:2]] == ["database", "asked"] and picture.spoken[0].time < 0.5
    result = lint_project(project, rules=["said_before_shown", "unsaid_reveal"])
    assert [(f.scene, f.rule, f.beat) for f in result.findings] == [("intro", "said_before_shown", "intro_b1")]
    finding = result.findings[0]
    assert finding.to_json()["object"]["text"] == "Database" and finding.still is not None
    raw = yaml.safe_load((project.root / "video.yaml").read_text(encoding="utf-8"))
    raw["scenes"][0]["lint_ignore"] = [{"rule": "said_before_shown", "object": "Database"}]
    raw["lint"] = {"rules": {"unsaid_reveal": {"severity": "info"}}}
    (project.root / "video.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    result = lint_project(Project.load(project.root), rules=["said_before_shown", "unsaid_reveal"])
    assert result.findings == [] and result.ignored == 1   # the database is named, so no unsaid_reveal


def test_runner_on_a_word_anchor(make_project: Any) -> None:
    beats = [{"text": "A request comes in."},
             {"text": "Then the database, yes the database, answers it.", "actions": [{"highlight": "text", "at": "@database#2"}]}]
    project = diagram_project(make_project, beats)
    labels = narration_picture(project, *_dumps(project), max_words=4).labels
    assert labels[1].hidden_until == 2.8   # a highlight shows nothing
    raw = yaml.safe_load((project.root / "video.yaml").read_text(encoding="utf-8"))
    raw["scenes"][0]["beats"][1]["actions"] = [{"reveal": "text", "at": "@database#2"}]
    (project.root / "video.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    project = Project.load(project.root)
    labels = narration_picture(project, *_dumps(project), max_words=4).labels
    shown = 3.0 + project.beat("intro_b2").actions[0].fraction * 2.5
    assert labels[1].hidden_until == pytest.approx(shown) and shown > 4.0   # on the word: the second "database"
    found = lint_project(project, rules=["said_before_shown"]).findings
    assert found == []   # named again as it shows (the anchor's word)


def _dumps(project: Project) -> tuple[dict[str, Any], dict[str, Any]]:
    import json

    from vidgen.render.worker import scene_activity_path, scene_layout_path

    return (json.loads(scene_layout_path(project, True, "intro").read_text(encoding="utf-8")),
            json.loads(scene_activity_path(project, True, "intro").read_text(encoding="utf-8")))
