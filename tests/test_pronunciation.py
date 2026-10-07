"""Pronunciation dictionary, Step 42 (DESIGN.md §45): config and file entries, matching rules,
the TTS text and audio hash (urlopen mocked), word times mapped back to the written words
(alignment and estimate), SRT / captions keep the written text, lint's spoken words, validate
warnings, variants, render fingerprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_captions import alignment_of, built, load, narrated, timestamped, tone
from test_tts import FakeAPI, api, edit, run  # noqa: F401  (api: the mocked ElevenLabs fixture)
from vidgen import api as vidgen_api
from vidgen import tts
from vidgen.cli import main
from vidgen.config import LintRules, PronunciationEntry, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import RULES, SceneContext, timing_rules
from vidgen.pronunciation import Pronunciation, compile_rule, load_pronunciation, pronunciation_warnings
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.speech import WordTime, beat_word_times, estimate_word_times, map_word_times, read_alignment, write_alignment
from vidgen.subtitles import cues_from_timings
from vidgen.tts.run import run_tts

KPHI = {"K-Phi-3": "kay fye three"}


def rules(entries: dict[str, Any]) -> Pronunciation:
    return Pronunciation([compile_rule(term, value, i) for i, (term, value) in enumerate(entries.items())])


def config(**extra: Any) -> dict[str, Any]:
    scenes = [narrated("a", "K-Phi-3 is small.", "Plain words here."), narrated("b", "Another plain beat.")]
    return minimal_config(scenes=scenes, **extra)


# ----- matching ----------------------------------------------------------------------------------


def test_whole_words_case_and_longest_match() -> None:
    p = rules({"K-Phi-3": "kay fye three", "Phi": "fye", "GPU": "gee pee you", "C++": "see plus plus"})
    s = p.apply("K-Phi-3's loss beats Phi, on a GPU; GPUs and gpu stay. C++ too.")
    assert s.spoken == "kay fye three's loss beats fye, on a gee pee you; GPUs and gpu stay. see plus plus too."
    assert [r.term for r in s.replacements] == ["K-Phi-3", "Phi", "GPU", "C++"]
    assert s.changed and not p.apply("Nothing here.").changed
    assert Pronunciation().apply("GPU").spoken == "GPU" and not Pronunciation()
    # whole_word false matches inside words; case_sensitive false any case
    loose = rules({"phi": PronunciationEntry(say="fye", whole_word=False, case_sensitive=False)})
    assert loose.say("Phi and Delphi") == "fye and Delfye"


def test_regex_entries_and_one_pass() -> None:
    p = rules({r"v(\d+)\.(\d+)": PronunciationEntry(say=r"version \1 point \2", regex=True), "version": "VERSION"})
    # the replacement is not matched again by another entry
    assert p.say("Use v2.10 now; this version works.") == "Use version 2 point 10 now; this VERSION works."
    named = rules({r"(?P<n>\d+)p": PronunciationEntry(say=r"\g<n> pee", regex=True)})
    assert named.say("At 480p or 1080p.") == "At 480 pee or 1080 pee."


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ({r"v(\d": {"say": "x", "regex": True}}, "not a valid regular expression"),
        ({r"v(\d)": {"say": r"version \2", "regex": True}}, "not a valid replacement"),
        ({"a*": {"say": "x", "regex": True}}, "matches the empty string"),
        ({"": "x"}, "pronunciation"),
        ({"GPU": {"say": "x", "whole": True}}, "whole"),
    ],
)
def test_invalid_entries_are_config_errors(entries: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message) as info:
        parse_config(config(pronunciation=entries))
    assert info.value.problems[0].location.startswith("pronunciation")


# ----- word times back to the written words ----------------------------------------------------------


def test_spoken_words_map_back_to_written_words() -> None:
    p = rules({**KPHI, "e.g.": "for example", "(silent)": "", "New York": "noo york"})
    s = p.apply("K-Phi-3 is small, e.g. here (silent) in New York.")
    assert s.spoken == "kay fye three is small, for example here  in noo york."
    assert s.word_groups() == [[0, 1, 2], [3], [4], [5, 6], [7], [], [8], [9, 10], [9, 10]]
    times = estimate_word_times(s.spoken.split(), 0.0, 6.0)
    mapped = map_word_times(s, times)
    assert [w.text for w in mapped] == s.text.split()
    assert mapped[0] == WordTime("K-Phi-3", times[0].start, times[2].end)   # three spoken words, one written
    assert mapped[5].start == mapped[5].end == times[8].start            # said as nothing: where the next starts
    assert mapped[7].start == mapped[8].start == times[9].start          # one replacement for two words
    assert all(a.start <= b.start for a, b in zip(mapped, mapped[1:]))


def test_beat_word_times_use_the_alignment_of_the_spoken_text(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    text = "K-Phi-3 is small."
    spoken = rules(KPHI).apply(text)
    mp3 = tone(audio / "b1.mp3", 0.1, 2.5, 0.1)
    write_alignment(audio, "b1", spoken.spoken, mp3.read_bytes(), alignment_of(spoken.spoken, step=0.1))
    words = beat_word_times(audio, "b1", text, 10.0, 13.0, spoken)
    # "kay fye three" = characters 0-12, "is" from character 14
    assert [w.text for w in words] == ["K-Phi-3", "is", "small."]
    assert words[0].start == pytest.approx(10.0) and words[0].end == pytest.approx(11.3)
    assert words[1].start == pytest.approx(11.4)
    # without the pronunciation the alignment (of another text) is not used: estimated instead
    assert beat_word_times(audio, "b1", text, 10.0, 13.0)[1].start != pytest.approx(11.4)
    # no audio: the spoken syllables are estimated, the written words keep their order
    estimate = beat_word_times(None, "x", text, 0.0, 3.0, spoken)
    assert [w.text for w in estimate] == text.split() and estimate[-1].end == pytest.approx(3.0)
    assert estimate[0].end - estimate[0].start > estimate[1].end - estimate[1].start


def test_srt_keeps_the_written_text_timed_by_the_spoken(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    text = "K-Phi-3 is small. It saves memory on every layer of the model, which is a lot."
    p = rules(KPHI)
    spoken = p.say(text)
    mp3 = tone(audio / "b1.mp3", 0.0, 9.0, 0.0)
    write_alignment(audio, "b1", spoken, mp3.read_bytes(), alignment_of(spoken, step=0.1))
    timings = {"scenes": [{"beats": [{"id": "b1", "text": text, "start": 0.0, "end": 9.0}]}]}
    cues = cues_from_timings(timings, audio, p)
    assert " ".join(c.text.replace("\n", " ") for c in cues) == text and "kay" not in cues[0].text
    second = next(c for c in cues if c.text.startswith("It"))
    assert second.start == pytest.approx(spoken.index("It") * 0.1)


def test_karaoke_captions_highlight_the_written_word_while_it_is_said(make_project) -> None:
    project = load(make_project, [narrated("a", "K-Phi-3 is small.")], [{"type": "captions", "style": "karaoke"}], pronunciation=KPHI)
    spoken = project.pronunciation.say("K-Phi-3 is small.")
    mp3 = tone(project.audio_dir / "a_b1.mp3", 0.0, 2.6, 0.0)
    write_alignment(project.audio_dir, "a_b1", spoken, mp3.read_bytes(), alignment_of(spoken, step=0.1))
    (cap,) = built(project, "a", size=(180, 320))
    at = cap.at  # type: ignore[attr-defined]
    assert cap.state(at + 1.2) == (0, 0)   # still "kay fye three": K-Phi-3
    assert cap.state(at + 1.45) == (0, 1)  # "is"
    shown = [line.original_text for line in cap.built.submobjects[1].submobjects[1:]]  # type: ignore[attr-defined]
    assert " ".join(shown) == "K-Phi-3 is small."


# ----- TTS text and audio hash -----------------------------------------------------------------------


def test_tts_sends_the_spoken_text_and_hashes_it(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(config(pronunciation=KPHI))
    assert run(root) == 0
    assert api.texts() == ["kay fye three is small.", "Plain words here.", "Another plain beat."]
    assert api.body(1)["previous_text"] == "kay fye three is small."   # context as spoken too
    p = Project.load(root)
    provider = tts.get_provider(p.config.voice)
    assert (root / "audio" / "a_b1.hash").read_text(encoding="utf-8") == provider.cache_key("kay fye three is small.")
    # a beat no entry matches has the hash of its written text: adding a dictionary keeps its audio
    assert (root / "audio" / "a_b2.hash").read_text(encoding="utf-8") == provider.cache_key("Plain words here.")
    capsys.readouterr()

    # a new entry re-voices only the beats it changes; dry run shows them and what they say
    edit(root, lambda d: d["pronunciation"].update({"plain": {"say": "plane", "case_sensitive": False}}))
    assert [s.state for s in tts.audio_status(Project.load(root))] == ["ok", "stale", "stale"]
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would generate a_b2.mp3 (17 chars)\n    says: plane words here." in out
    assert "a_b1" not in out and "dry run: 2 beat(s) to generate, 36 characters; 1 up to date" in out
    assert run(root) == 0
    assert api.texts()[3:] == ["plane words here.", "Another plane beat."]
    # removing the entry again: those two are stale, K-Phi-3's beat is not
    edit(root, lambda d: d["pronunciation"].pop("plain"))
    assert [s.state for s in tts.audio_status(Project.load(root))] == ["ok", "stale", "stale"]


def test_tts_alignment_is_of_the_spoken_text(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.request

    fake = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test_x")
    root = make_project(minimal_config(scenes=[narrated("a", "K-Phi-3 is small.")], voice={"timestamps": True}, pronunciation=KPHI))
    fake.responses = [timestamped("kay fye three is small.", b"A1")]
    run_tts(Project.load(root), out=lambda s: None)
    assert read_alignment(root / "audio", "a_b1", "kay fye three is small.") is not None
    project = Project.load(root)
    words = beat_word_times(project.audio_dir, "a_b1", "K-Phi-3 is small.", 0.0, 3.0, project.pronunciation.apply("K-Phi-3 is small."))
    assert words[0].end == pytest.approx(1.3) and words[1].start == pytest.approx(1.4)


# ----- pronunciation files and variants ---------------------------------------------------------------


def test_pronunciation_file_merges_under_the_config(make_project) -> None:
    root = make_project(config(pronunciation={"Plain": "PLANE", "Another": None}, pronunciation_file="words.yaml"))
    (root / "words.yaml").write_text("K-Phi-3: kay fye three\nPlain: plain-ish\nAnother: {say: a nother}\n", encoding="utf-8")
    project = Project.load(root)
    assert [r.term for r in project.pronunciation.rules] == ["K-Phi-3", "Plain"]
    assert project.spoken_texts() == {"a_b1": "kay fye three is small.", "a_b2": "PLANE words here.", "b_b1": "Another plain beat."}
    # JSON files and lists of files
    (root / "more.json").write_text(json.dumps({"beat": {"say": "BEAT"}}), encoding="utf-8")
    edit(root, lambda d: d.update(pronunciation_file=["words.yaml", "more.json"]))
    assert Project.load(root).spoken_texts()["b_b1"] == "Another plain BEAT."


@pytest.mark.parametrize(
    ("content", "location", "message"),
    [
        (None, "pronunciation_file", "file not found: words.yaml"),
        ("- a list\n", "pronunciation_file (words.yaml)", "must be a mapping"),
        ("GPU: {sai: x}\n", "pronunciation_file (words.yaml)", "unknown key 'sai'; did you mean 'say'"),
        ("GPU: 3\n", "pronunciation_file (words.yaml)", "must be the spoken form"),
        ("'v(\\d': {say: x, regex: true}\n", "pronunciation_file (words.yaml)", "not a valid regular expression"),
        ("GPU: [unclosed\n", "pronunciation_file (words.yaml)", "invalid YAML"),
    ],
)
def test_bad_pronunciation_files(make_project, content: str | None, location: str, message: str) -> None:
    root = make_project(config(pronunciation_file="words.yaml"))
    if content is not None:
        (root / "words.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(VidgenError, match=message) as info:
        Project.load(root)
    assert info.value.problems[0].location.startswith(location)
    doc = json.loads(_validate_json(root))
    assert doc["ok"] is False and doc["problems"][0]["location"].startswith(location)


def _validate_json(root: Path) -> str:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(["validate", str(root), "--json"])
    return buffer.getvalue()


def test_a_variant_with_another_pronunciation_has_its_own_audio(make_project) -> None:
    variants = {"plain": {"pronunciation": {"K-Phi-3": None}}, "same": {"pronunciation": {"Unused": "x"}}, "british": {"pronunciation": {"K-Phi-3": "kay fee three"}}}
    root = make_project(config(pronunciation=KPHI, variants=variants))
    assert Project.load(root, variant="plain").has_own_audio
    assert Project.load(root, variant="british").has_own_audio
    assert not Project.load(root, variant="same").has_own_audio   # no beat says anything else
    assert Project.load(root, variant="plain").spoken_texts()["a_b1"] == "K-Phi-3 is small."


# ----- validate warnings, lint, fingerprint -----------------------------------------------------------


def test_validate_warns_about_unused_and_colliding_entries(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    entries = {
        **KPHI,
        "Phi": "fye",                                            # always inside K-Phi-3
        "Nowhere": "x",                                          # matches nothing
        "Plain": "plane",
        "plain": {"say": "PLANE", "case_sensitive": False},       # same text as "Plain" in a_b2
        "words here": "werds hear",
        "here": "hear",                                          # only ever inside "words here"
        "small. Plain": {"say": "x", "whole_word": False},       # spans two beats: never matches
    }
    root = make_project(config(pronunciation=entries))
    assert main(["validate", str(root)]) == 0
    err = capsys.readouterr().err
    assert "pronunciation: 'Nowhere' matches no beat's text" in err
    assert "pronunciation: 'Phi' never applies: every match is inside a longer entry ('K-Phi-3')" in err
    assert "pronunciation: 'Plain' and 'plain' match the same text in beat a_b2 ('Plain'); 'Plain' is used there" in err
    assert "'here' never applies" in err and "'small. Plain' matches no beat's text" in err
    assert err.count("pronunciation:") == 5   # K-Phi-3 and "words here" are fine
    # crossing matches
    crossing = rules({"big data": "B D", "data center": "D C"})
    warnings = pronunciation_warnings(crossing, [("b1", "A big data center.")])
    assert warnings == ["pronunciation: 'big data' and 'data center' overlap in beat b1 ('big data center'); 'big data' is used there"]
    # JSON: warnings, not problems
    doc = json.loads(_validate_json(root))
    assert doc["ok"] is True and any("Nowhere" in w["message"] for w in doc["warnings"])


def test_lint_counts_the_spoken_words() -> None:
    doc = {"fps": 5, "beats": [{"id": "b1", "start": 0.0, "end": 2.0, "busy": 0.0, "source": "estimate", "text": "SQL SQL SQL SQL SQL SQL"}]}
    model = type(LintRules().narration_speed)
    check = RULES["narration_speed"].check
    written = list(check(SceneContext("s", doc, Path(".")), model()))
    assert written and written[0].value == pytest.approx(9 / 2)   # acronyms: 1.5 words each
    said = rules({"SQL": "sequel"}).say(doc["beats"][0]["text"])
    assert list(check(SceneContext("s", doc, Path("."), {"b1": said}), model(max_rate=3.5))) == []   # 6 words / 2 s
    assert timing_rules.spoken_words(said) == 6


def test_render_fingerprint(make_project) -> None:
    plain = Project.load(make_project(config(), folder="plain"))
    said = Project.load(make_project(config(pronunciation=KPHI), folder="said"))
    # without overlays the pronunciation changes only the audio: renders stay valid
    assert scene_fingerprint(plain, "a") == scene_fingerprint(said, "a")
    with_captions = {"overlays": [{"type": "captions"}]}
    plain = Project.load(make_project(config(**with_captions), folder="plain2"))
    said = Project.load(make_project(config(pronunciation=KPHI, **with_captions), folder="said2"))
    assert scene_fingerprint(plain, "b") != scene_fingerprint(said, "b")   # captions' word times change


def test_the_documented_example_does_what_the_docs_say() -> None:
    import re

    import yaml

    text = (Path(__file__).resolve().parent.parent / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    block = re.search(r"```yaml\n(pronunciation:\n.*?)```", text, flags=re.S)
    assert block is not None
    data = yaml.safe_load(block.group(1))
    cfg = parse_config(minimal_config(pronunciation=data["pronunciation"]))
    p = load_pronunciation(cfg, Path("."))
    assert p.say("K-Phi-3's LaTeX, sql and Sql at 480p; Phis and DelPhi.") == (
        "kay fye three's lah-tek, sequel and sequel at 480 pee; fyes and Delfye."
    )


def test_load_pronunciation_and_api() -> None:
    cfg = parse_config(config(pronunciation=KPHI))
    assert load_pronunciation(cfg, Path(".")).say("K-Phi-3") == "kay fye three"
    for name in ("Pronunciation", "Spoken", "map_word_times"):
        assert name in vidgen_api.__all__ and getattr(vidgen_api, name).__doc__
