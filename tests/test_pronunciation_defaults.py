"""Built-in pronunciation lists, Step 165 (DESIGN.md §88): the shipped files, which list a beat's
voice uses, the order (built-in, files, `pronunciation:`), overrides, `null`, the opt-out,
validate, the audio hash and `vidgen tts`, readback hints and `vidgen list-pronunciation`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_tts_kokoro import KOKORO, Factory, fake  # noqa: F401  (fake: the Kokoro fixture)
from vidgen import kokoro_voices, tts
from vidgen.cli import main, validate_warnings
from vidgen.config import PronunciationEntry, VoiceConfig
from vidgen.pronunciation import (
    KOKORO_DIALECTS,
    build_pronunciation,
    builtin_entries,
    builtin_files,
    builtin_list_name,
    builtin_list_names,
    pronunciation_warnings,
)
from vidgen.project import Project
from vidgen.readback import TermReport, entry_hint
from vidgen.tts.run import plan_tts, run_tts


def project_config(*texts: str, voice: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    scenes = [{"id": "a", "type": "text_card", "params": {"text": "x"}, "beats": [{"text": t} for t in texts]}]
    return minimal_config(scenes=scenes, voice={**KOKORO, **(voice or {})}, **extra)


TEXTS = ("The first epoch ends.", "Plain words only.", "Save it as JSON.")


# ----- the shipped lists ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("voice", "language", "name"),
    [
        ({"provider": "kokoro"}, None, "kokoro-en-us"),
        ({"provider": "kokoro", "voice": "af_bella"}, "pt-BR", "kokoro-en-us"),  # the voice's G2P decides
        ({"provider": "kokoro", "voice": "bm_george"}, None, "kokoro-en-gb"),
        ({"provider": "kokoro"}, "en-GB", "kokoro-en-gb"),
        ({"provider": "kokoro", "voice": "pf_dora"}, "pt-BR", "kokoro-pt-br"),
        ({"provider": "kokoro", "lang": "e"}, None, "kokoro-es"),
        ({"provider": "elevenlabs"}, None, "elevenlabs-en"),
        ({"provider": "elevenlabs"}, "pt-BR", "elevenlabs-pt-br"),
    ],
)
def test_list_name_of_a_voice(voice: dict[str, Any], language: str | None, name: str) -> None:
    assert builtin_list_name(VoiceConfig.model_validate(voice), language) == name


def test_shipped_files_and_layers() -> None:
    assert builtin_files("kokoro-en-us") == ["kokoro-en.yaml", "kokoro-en-us.yaml"]
    assert builtin_files("kokoro-en-gb") == ["kokoro-en.yaml"]
    assert builtin_files("kokoro-pt-br") == builtin_files("elevenlabs-en") == []
    assert builtin_entries("elevenlabs-en") == {}
    us, gb = builtin_entries("kokoro-en-us"), builtin_entries("kokoro-en-gb")
    assert "epoch" in us and "epoch" not in gb   # British misaki already says ˈiːpɒk
    assert set(gb) < set(us) and us["README"] == "readme"
    assert builtin_list_names() == ["kokoro-en-gb", "kokoro-en-us"]
    assert set(KOKORO_DIALECTS) == set(kokoro_voices.langs())


@pytest.mark.parametrize("name", ["kokoro-en-us", "kokoro-en-gb"])
def test_every_builtin_entry_applies_to_its_term_alone(name: str) -> None:
    pronunciation = build_pronunciation({}, None, name)
    for rule in pronunciation.rules:
        spoken = pronunciation.apply(f"Here {rule.term} again.")
        assert [r.term for r in spoken.replacements] == [rule.term] and not spoken.conflicts, rule.term
        assert spoken.builtin_terms == (rule.term,)
    # one pass: a spoken form is not respelled again
    said = "Each E pock, the readme and Jason." if name == "kokoro-en-us" else "Each epoch, the readme and Jason."
    assert pronunciation.say("Each epoch, the README and JSON.") == said


# ----- order, overrides, null, language -----------------------------------------------------------


def test_project_entries_go_over_the_builtin_list() -> None:
    own = {"JSON": "jay son", "YAML": None, "Epoch": "EE pok", "TeX": PronunciationEntry(say="tex", language="pt")}
    p = build_pronunciation(own, None, "kokoro-en-us")
    assert p.builtin_list == "kokoro-en-us"
    assert p.say("JSON, YAML and TeX.") == "jay son, YAML and tek."   # replaced, removed, kept (TeX's entry is Portuguese)
    # a project entry matching the same text as a built-in one wins it, and validate is quiet
    spoken = p.apply("Epoch one, then epoch two.")
    assert spoken.spoken == "EE pok one, then E pock two."
    assert [(r.term, r.builtin) for r in spoken.replacements] == [("Epoch", False), ("epoch", True)]
    assert pronunciation_warnings(p, [("b1", "Epoch one, then epoch two."), ("b2", "Save the JSON.")]) == []
    # in a Portuguese video the project's TeX replaces the built-in one
    assert build_pronunciation(own, "pt-BR", "kokoro-en-us").say("TeX") == "tex"
    assert build_pronunciation(own, None, None).rules[0].builtin is False and build_pronunciation({}, None, None).builtin_list is None


def test_project_order_builtin_then_files_then_config(make_project) -> None:
    root = make_project(project_config(*TEXTS, "YAML and ReLU.", pronunciation_file="words.yaml", pronunciation={"YAML": None, "ReLU": "rel you"}))
    (root / "words.yaml").write_text("JSON: jay son\nReLU: from the file\n", encoding="utf-8")
    spoken = Project.load(root).spoken_texts()
    assert list(spoken.values()) == ["The first E pock ends.", "Plain words only.", "Save it as jay son.", "YAML and rel you."]


def test_opt_out_and_other_engines(make_project) -> None:
    off = Project.load(make_project(project_config(*TEXTS, pronunciation_defaults=False), folder="off"))
    assert list(off.spoken_texts().values()) == list(TEXTS) and off.builtin_changes() == {}
    eleven = Project.load(make_project(minimal_config(scenes=project_config(*TEXTS)["scenes"]), folder="eleven"))
    assert list(eleven.spoken_texts().values()) == list(TEXTS) and eleven.pronunciation.builtin_list is None


def test_each_beat_uses_its_own_voices_list(make_project) -> None:
    data = project_config(*TEXTS, voices={"gb": {"voice": "bm_george"}})
    data["scenes"][0]["beats"][0]["voice"] = "gb"
    data["scenes"][0]["beats"][2]["voice"] = "gb"
    data["variants"] = {"pt": {"language": "pt-BR", "voice": {"voice": "pf_dora"}, "voices": {"gb": {"voice": "pf_dora"}}}}
    project = Project.load(make_project(data))
    assert project.beat_pronunciation("a_b1").builtin_list == "kokoro-en-gb"
    assert project.beat_pronunciation("a_b2").builtin_list == "kokoro-en-us"
    # British says epoch right (no entry); JSON is respelled for both
    assert list(project.spoken_texts().values()) == ["The first epoch ends.", "Plain words only.", "Save it as Jason."]
    assert project.builtin_changes() == {"a_b3": ("JSON",)}
    dubbed = Project.load(project.config_file, variant="pt")   # Portuguese voices: no built-in list
    assert list(dubbed.spoken_texts().values()) == list(TEXTS) and dubbed.builtin_changes() == {}


# ----- validate ------------------------------------------------------------------------------------


def test_validate_is_quiet_about_builtin_entries_and_names_the_changes(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(project_config(*TEXTS, "One more epoch.", pronunciation={"Nowhere": "x"}))
    project = Project.load(root)
    warnings = [w for w in validate_warnings(project) if w.startswith("pronunciation:")]
    assert warnings == ["pronunciation: 'Nowhere' matches no beat's text"]   # no built-in entry is reported
    assert main(["validate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "pronounce: built-in kokoro-en-us changes 3 beat(s): epoch (2), JSON (1) (vidgen list-pronunciation)" in out
    assert main(["validate", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["pronunciation_defaults"] == {"a_b1": ["epoch"], "a_b3": ["JSON"], "a_b4": ["epoch"]}


def test_a_project_entry_a_builtin_one_hides_is_still_reported() -> None:
    p = build_pronunciation({"api": "a p i"}, None, "kokoro-en-us")
    assert pronunciation_warnings(p, [("b1", "The neural-api code.")]) == [
        "pronunciation: 'api' never applies: every match is inside a longer entry ('neural-api')"
    ]


# ----- audio hash and vidgen tts ---------------------------------------------------------------------


def test_only_beats_the_defaults_change_go_stale(make_project, fake: Factory, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(project_config(*TEXTS, pronunciation_defaults=False))
    run_tts(Project.load(root), out=lambda s: None)
    assert fake.texts() == list(TEXTS)
    # the audio made before built-in lists existed: the same hash as with the defaults turned off
    data = project_config(*TEXTS)
    (root / "video.yaml").write_text(json.dumps(data), encoding="utf-8")
    project = Project.load(root)
    assert [s.state for s in tts.audio_status(project)] == ["stale", "ok", "stale"]
    assert [b.id for b in plan_tts(project).todo] == ["a_b1", "a_b3"]
    lines: list[str] = []
    run_tts(project, dry_run=True, out=lines.append)
    assert "    says: The first E pock ends.  (built-in: epoch)" in lines
    assert any(line.startswith("dry run: 2 beat(s) to generate") for line in lines)
    lines.clear()
    run_tts(project, out=lines.append)
    assert fake.texts()[3:] == ["The first E pock ends.", "Save it as Jason."]
    assert any(line.startswith("[1/2] generated a_b1.mp3 (") and line.endswith(", built-in pronunciation: epoch)") for line in lines)
    assert [s.state for s in tts.audio_status(Project.load(root))] == ["ok", "ok", "ok"]
    assert main(["tts", str(root), "--dry-run", "--force", "--json"]) == 0
    beats = json.loads(capsys.readouterr().out)["beats"]
    assert [b["builtin_pronunciation"] for b in beats] == [["epoch"], [], ["JSON"]]


# ----- readback hints ------------------------------------------------------------------------------


def test_readback_hints_name_the_builtin_route() -> None:
    spoken = build_pronunciation({}, None, "kokoro-en-us").apply("The epoch ends.")
    hint = entry_hint(spoken, "epoch", 'is heard as "a pock"')
    assert hint.startswith('the built-in pronunciation entry "epoch" (says "E pock") is heard as "a pock": write your own in `pronunciation:`')
    assert "`epoch: null` to drop it" in hint
    own = build_pronunciation({"epoch": "ee pok"}, None, "kokoro-en-us").apply("The epoch ends.")
    assert entry_hint(own, "epoch", "is not heard clearly").startswith('the pronunciation entry "epoch" (says "ee pok") is not heard clearly: respell')
    assert "built-in" in TermReport("epoch", True, ["b1"], builtin=True).suggestion
    assert TermReport("NVIDIA", False, ["b1", "b2"]).suggestion.endswith("(other videos with it can share a pronunciation_file)")
    assert "share" not in TermReport("NVIDIA", False, ["b1"]).suggestion


# ----- vidgen list-pronunciation -----------------------------------------------------------------------


def test_list_pronunciation(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)   # no project here: every list
    assert main(["list-pronunciation"]) == 0
    out = capsys.readouterr().out
    assert "kokoro-en-gb: " in out and "kokoro-en-us: " in out and "  epoch       -> E pock  (any case)" in out
    root = make_project(project_config(*TEXTS, pronunciation={"JSON": "jay son", "YAML": None}))
    assert main(["list-pronunciation", str(root)]) == 0
    out = capsys.readouterr().out
    assert "kokoro-en-gb" not in out and "(kokoro-en.yaml, kokoro-en-us.yaml); 3 beat(s) use it" in out
    assert 'JSON        -> Jason  replaced by the project: "jay son"' in out
    assert "YAML        -> yammel  removed by the project (null)" in out
    assert "epoch       -> E pock  (any case)  changes a_b1" in out
    assert main(["list-pronunciation", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    (listing,) = doc["lists"]
    assert (doc["command"], doc["defaults"], listing["name"], listing["beats"]) == ("list-pronunciation", True, "kokoro-en-us", 3)
    states = {e["term"]: (e["state"], e["own"], e["beats"]) for e in listing["entries"]}
    assert states["JSON"] == ("replaced", "jay son", []) and states["YAML"] == ("removed", None, [])
    assert states["epoch"] == ("used", None, ["a_b1"])
    off = make_project(project_config(*TEXTS, pronunciation_defaults=False), folder="off")
    assert main(["list-pronunciation", str(off)]) == 0
    assert capsys.readouterr().out.startswith("pronunciation_defaults: false")
