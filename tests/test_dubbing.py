"""Dubbing (DESIGN.md §80): per-language voices of the same kind, timings and lint per language,
``--all-languages``. No rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from vidgen import dubbing
from vidgen.cli import main, validate_warnings
from vidgen.config import parse_config
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videoplan import VideoPlan
from vidgen.voices import resolve_voice

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "cartoon-music-box"


def kokoro_cast(language: str | None = "pt-BR", voices: dict[str, Any] | None = None, **voice: Any) -> dict[str, Any]:
    """A Kokoro video with a narrator and three speakers (two of one kind), or the ``voices`` given."""
    voices = voices or {"fen": {"voice": "af_heart"}, "bram": {"voice": "bm_fable"}, "gus": {"voice": "am_fenrir"}}
    beats = [{"text": "One."}] + [{"text": f"Line {k}.", "voice": name} for k, name in enumerate(voices)]
    data: dict[str, Any] = {
        "title": "T",
        "voice": {"provider": "kokoro", "voice": "bf_emma", **voice},
        "voices": voices,
        "scenes": [{"id": "s", "type": "title", "params": {"title": "x"}, "beats": beats}],
    }
    if language is not None:
        data["language"] = language
    return data


def voices_of(config: Any) -> dict[str | None, str | None]:
    return {name: resolve_voice(config, name).voice for name in [None, *config.voices]}


# ----- per-language voice assignment --------------------------------------------------------------


def test_kokoro_voices_get_a_voice_of_the_language_of_the_same_kind() -> None:
    config = parse_config(kokoro_cast())
    assert voices_of(config) == {None: "pf_dora", "fen": "pf_dora", "bram": "pm_alex", "gus": "pm_alex"}
    dubs = dubbing.voice_dubs(config)
    assert [(d.source, d.target, d.how, d.kind, d.kind_kept) for d in dubs.values()] == [
        ("bf_emma", "pf_dora", "auto", "feminine", True),
        ("af_heart", "pf_dora", "auto", "feminine", True),
        ("bm_fable", "pm_alex", "auto", "masculine", True),
        ("am_fenrir", "pm_alex", "auto", "masculine", True),
    ]   # pm_santa is a novelty voice: never picked by itself
    voice = resolve_voice(config, "fen")
    assert (voice.lang, voice.dub) == ("p", None)


def test_the_least_used_voice_of_the_kind_first() -> None:
    config = parse_config(kokoro_cast("en-US", voice="pf_dora", voices={
        "a": {"voice": "pf_dora"}, "b": {"voice": "pm_alex"}, "c": {"voice": "pm_alex", "speed": 0.9}}))
    found = voices_of(config)
    assert found[None] == "af_heart" and found["a"] == "af_heart"   # one source voice, one dubbed voice
    assert found["b"] == found["c"] and found["b"].startswith("am_")
    two_women = parse_config(kokoro_cast("en", voice="pf_dora", voices={"a": {"voice": "if_sara"}}))
    first, second = voices_of(two_women).values()
    assert first.startswith("af_") and second.startswith("af_") and first != second


def test_given_dubs_win_and_followers_take_the_base_voices() -> None:
    data = kokoro_cast(dub={"pt": "pf_dora+bf_emma:0.4"})
    data["voices"]["gus"]["dub"] = {"pt": {"voice": "pm_santa", "speed": 0.9}, "pt-BR": "pm_alex", "es": "em_alex"}
    data["voices"]["echo"] = {"speed": 1.2}   # keeps the base voice: follows its dub
    config = parse_config(data)
    found = voices_of(config)
    assert found[None] == found["echo"] == "pf_dora+bf_emma:0.4"
    assert found["gus"] == "pm_alex"   # pt-BR is more specific than pt
    assert resolve_voice(config, "echo").speed == 1.2
    dubs = dubbing.voice_dubs(config)
    assert (dubs[None].how, dubs["echo"].how, dubs["gus"].how) == ("given", "base", "given")
    data["language"] = "pt-PT"
    found = voices_of(parse_config(data))
    assert found["gus"] == "pm_santa" and resolve_voice(parse_config(data), "gus").speed == 0.9


def test_no_dub_without_a_language_or_in_the_voices_own_language() -> None:
    assert dubbing.voice_dubs(parse_config(kokoro_cast(None))) == {}
    assert dubbing.voice_dubs(parse_config(kokoro_cast("en-GB"))) == {}   # American and British English
    config = parse_config(kokoro_cast(lang="b"))   # a lang written: the voice is kept on purpose
    assert voices_of(config)[None] == "bf_emma"
    config = parse_config(kokoro_cast(language=None) | {"language": "de"})   # Kokoro speaks no German
    assert dubbing.voice_dubs(config) == {}


def test_a_language_without_the_kind_takes_another_and_warns() -> None:
    config = parse_config(kokoro_cast("fr"))
    assert set(voices_of(config).values()) == {"ff_siwis"}
    assert not dubbing.voice_dubs(config)["bram"].kind_kept
    warnings = dubbing.config_dub_warnings(config, [None, "fen", "bram", "gus"])
    assert any("voices.bram (bm_fable, masculine) speaks with ff_siwis: Kokoro has no masculine voice of French" in w for w in warnings)
    assert any("speak with ff_siwis here" in w and "the base voice (bf_emma)" in w for w in warnings)


def test_merged_voices_warn_only_when_they_differed() -> None:
    config = parse_config(kokoro_cast())
    warnings = dubbing.config_dub_warnings(config, [None, "fen", "bram", "gus"])
    assert len(warnings) == 2
    assert "the base voice (bf_emma) and voices.fen (af_heart) speak with pf_dora here" in warnings[0]
    assert "pf_dora+af_heart:0.3" in warnings[0]
    data = kokoro_cast(dub={"pt": "pf_dora+bf_emma:0.4"})
    data["voices"]["gus"]["dub"] = {"pt": "pm_santa"}
    assert dubbing.config_dub_warnings(parse_config(data), [None, "fen", "bram", "gus"]) == []


def test_other_providers_keep_their_voices_unless_dubbed() -> None:
    data = {
        "title": "T", "language": "pt-BR", "voice": {"voice_id": "base_id", "dub": {"pt": "pt_id"}},
        "voices": {"ana": {"voice_id": "ana_id"}, "ben": {"voice_id": "ben_id", "dub": {"pt": {"voice_id": "ben_pt", "settings": {"style": 0.3}}}}},
        "scenes": [{"id": "s", "type": "title", "params": {"title": "x"}, "beats": [{"text": "x"}]}],
    }
    config = parse_config(data)
    assert {n: resolve_voice(config, n).voice_id for n in [None, "ana", "ben"]} == {None: "pt_id", "ana": "ana_id", "ben": "ben_pt"}
    assert resolve_voice(config, "ben").settings.style == 0.3
    assert resolve_voice(config, "ben").language_code is None   # eleven_multilingual_v2 takes none
    data["voices"]["ana"]["dub"] = {"pt": {"voice": "x", "lang": "p"}}
    with pytest.raises(VidgenError) as caught:
        parse_config(data)
    assert [p.location for p in caught.value.problems] == ["voices.ana.dub.pt.voice", "voices.ana.dub.pt.lang"]
    assert "voice is not an ElevenLabs setting" in str(caught.value)


def test_bad_dub_blend_is_a_problem() -> None:
    with pytest.raises(VidgenError) as caught:
        parse_config(kokoro_cast(dub={"pt": "pf_dora+"}))
    assert [p.location for p in caught.value.problems] == ["voice.dub.pt"]


# ----- a translated variant: audio, timings, warnings ---------------------------------------------


def dubbed_project(make_project, overlap: float | None = 0.3) -> Path:
    data = kokoro_cast(language=None)
    data["scenes"][0]["beats"][2]["overlap"] = overlap
    data["variants"] = {"pt": {"language": "pt-BR", "translations": "translations/pt.yaml"}, "wide": {"format": {"width": 1280, "height": 720}}}
    root = make_project(data)
    (root / "translations").mkdir()
    entries = {
        "scenes.s.beats.s_b2.text": "Dois, três, quatro, cinco, seis, sete.",
        "scenes.s.beats.s_b3.text": "Três.",
    }
    (root / "translations" / "pt.yaml").write_text(yaml.safe_dump({"version": 1, "language": "pt-BR", "entries": entries}), encoding="utf-8")
    return root


def test_variant_language_dubs_voices_into_its_own_audio_folder(make_project) -> None:
    root = dubbed_project(make_project)
    base, pt = Project.load(root), Project.load(root, variant="pt")
    assert base.beat_voice("s_b2").voice == "af_heart" and pt.beat_voice("s_b2").voice == "pf_dora"
    assert pt.audio_dir == root / "audio" / "pt" and Project.load(root, variant="wide").audio_dir == root / "audio"
    assert dubbing.language_variants(base) == [("pt", "pt-BR")]
    assert any("dub (pt-BR): the base voice (bf_emma) and voices.fen (af_heart) speak with pf_dora here" in w for w in validate_warnings(pt))
    assert dubbing.dub_summary(pt).startswith("default bf_emma -> pf_dora (auto), fen af_heart -> pf_dora (auto)")
    assert dubbing.dub_summary(base) is None


def test_timings_follow_each_languages_lines(make_project) -> None:
    root = dubbed_project(make_project)
    plans = {v: VideoPlan(Project.load(root, variant=v), 30).scene("s").beats for v in (None, "pt")}
    wps = 2.6   # narration.words_per_second's default
    for variant, beats in plans.items():
        two, three = beats[1], beats[2]
        words = len(two.text.split())
        assert two.end - two.start == pytest.approx(words / wps, abs=0.04)
        assert three.start == pytest.approx(two.end - 0.3, abs=0.04)   # the overlap, against this language's line
    assert plans["pt"][2].start - plans[None][2].start == pytest.approx(4 / wps, abs=0.07)   # 6 words instead of 2


def test_lint_per_language_sees_each_languages_timing(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """``vidgen lint --all-languages`` lints the base config and the pt variant (layout rendering
    replaced): an overlap longer than the Portuguese line fails only there."""
    from types import SimpleNamespace

    from vidgen import lint as lint_package

    root = dubbed_project(make_project, overlap=0.9)
    seen: list[tuple[str | None, float]] = []

    def fake_lint(project: Project, **_: Any) -> SimpleNamespace:
        beats = VideoPlan(project, 30).scene("s").beats
        seen.append((project.variant, beats[1].end - beats[1].start))
        return SimpleNamespace(failed=beats[1].end - beats[1].start < 0.9)

    monkeypatch.setattr(lint_package, "lint_project", fake_lint)
    monkeypatch.setattr(lint_package, "report_lines", lambda result, cwd: [f"failed={result.failed}"])
    assert main(["lint", str(root), "--all-languages"]) == 1
    out = capsys.readouterr().out
    assert "== base config (no language) ==\nfailed=True" in out and "== pt (pt-BR) ==\nfailed=False" in out
    assert [v for v, _ in seen] == [None, "pt"]
    assert main(["lint", str(root), "--all-languages", "--variant", "pt"]) == 1
    assert "leave out --variant" in capsys.readouterr().err


def test_tts_dry_run_for_every_language_as_json(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = dubbed_project(make_project)
    assert main(["tts", str(root), "--all-languages", "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "tts" and doc["ok"] and [d["variant"] for d in doc["languages"]] == [None, "pt"]
    voices = [{b["beat"]: b["provider_voice"] for b in d["beats"]} for d in doc["languages"]]
    assert voices[0] == {"s_b1": "bf_emma", "s_b2": "af_heart", "s_b3": "bm_fable", "s_b4": "am_fenrir"}
    assert voices[1] == {"s_b1": "pf_dora", "s_b2": "pf_dora", "s_b3": "pm_alex", "s_b4": "pm_alex"}


# ----- on-screen texts and the example ------------------------------------------------------------


def test_cards_and_bubbles_are_translated(make_project) -> None:
    from vidgen import extensions
    from vidgen.translation import project_texts

    data = kokoro_cast(language=None)
    data["characters"] = [{"name": "fen", "voice": "fen"}]
    data["scenes"] = [
        {"id": "open", "type": "card", "params": {"text": "Chapter One", "subtitle": "The box"}, "duration": 2},
        {"id": "yard", "type": "stage", "params": {"characters": [{"name": "fen"}]},
         "beats": [{"text": "Listen!", "voice": "fen", "actions": [{"say": "fen", "bubble": "Hey!"}]}]},
    ]
    data["variants"] = {"pt": {"language": "pt-BR", "translations": "pt.yaml"}}
    root = make_project(data)
    with extensions.project_session(Project.load(root)) as _:
        keys = {item.key: item.source for item in project_texts(Project.load(root))[0]}
    assert keys["scenes.open.params.text"] == "Chapter One" and keys["scenes.open.params.subtitle"] == "The box"
    bubble = next(k for k, v in keys.items() if v == "Hey!")
    entries = {"scenes.open.params.text": "Capítulo Um", bubble: "Ei!", "scenes.yard.beats.yard_b1.text": "Escuta!"}
    (root / "pt.yaml").write_text(yaml.safe_dump({"version": 1, "language": "pt-BR", "entries": entries}), encoding="utf-8")
    pt = Project.load(root, variant="pt")
    card, stage = pt.config.scenes
    assert card.params["text"] == "Capítulo Um" and stage.beats[0].actions[0].model_extra["bubble"] == "Ei!"
    assert stage.beats[0].text == "Escuta!" and pt.beat_voice("yard_b1").voice == "pf_dora"


def test_example_has_a_dubbed_portuguese_variant() -> None:
    assert (EXAMPLE / "video.yaml").stat().st_size <= 10_000
    base, pt = Project.load(EXAMPLE), Project.load(EXAMPLE, variant="pt")
    assert pt.translation is not None and not pt.translation.missing and not pt.translation.stale
    assert len(pt.translation.applied) == 12
    assert {name: pt.voice(name).voice for name in [None, *pt.config.voices]} == {
        None: "pf_dora+bf_emma:0.4", "fen_voice": "pf_dora", "bram_voice": "pm_alex", "gus_voice": "pm_santa"}
    assert {name: base.voice(name).voice for name in [None, *base.config.voices]} == {
        None: "bf_emma", "fen_voice": "af_heart", "bram_voice": "bm_fable", "gus_voice": "am_fenrir"}
    assert not [w for w in validate_warnings(pt) if w.startswith("dub")]
