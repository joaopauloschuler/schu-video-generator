"""Step 54: readback check — speech to text of the narration compared with the beat texts.

The providers are mocked (a fake faster_whisper module, a mocked urlopen for ElevenLabs); no
model is loaded and no request is sent."""

from __future__ import annotations

import io
import json
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from test_json_output import documented, run_json
from test_lint import fake_render
from vidgen.cli import main
from vidgen.config import ReadbackRule, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import RULES, SceneContext, lint_project
from vidgen.project import Project
from vidgen.pronunciation import Pronunciation, compile_rule
from vidgen.readback import align, cached_readback, compare_beat, hard_term, run_readback, word_error_rate
from vidgen.render import fingerprint
from vidgen.stt import Transcript, TranscriptWord, get_stt_provider, stt_settings
from vidgen.stt.elevenlabs import STT_URL, ElevenLabsSTTProvider, parse_response
from vidgen.stt.faster_whisper import FasterWhisperProvider
from vidgen.textnorm import english_number, normalize_text, number_words, portuguese_number

ROOT = Path(__file__).resolve().parents[1]
CONFIG_MD = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")


# ----- normaliser ---------------------------------------------------------------------------------


def test_english_numbers() -> None:
    assert english_number(0) == ["zero"]
    assert english_number(227) == "two hundred twenty seven".split()
    assert english_number(1_000_015) == "one million fifteen".split()
    assert english_number(2_520_000) == "two million five hundred twenty thousand".split()
    assert normalize_text("2.58 million, 1.08 and 1,000") == "two point five eight million one point zero eight and one thousand".split()
    assert normalize_text("77% of $5") == "seventy seven percent of five dollars".split()
    assert normalize_text("the 1st, 2nd, 3rd, 22nd and 40th") == "the first second third twenty second and fortieth".split()
    assert normalize_text("1,57") == ["one", "fifty", "seven"]  # not an English number: digit runs


def test_portuguese_numbers() -> None:
    assert portuguese_number(100) == ["cem"] and portuguese_number(101) == "cento e um".split()
    assert portuguese_number(227) == "duzentos e vinte e sete".split()
    assert portuguese_number(1000) == ["mil"] and portuguese_number(2020) == "dois mil e vinte".split()
    assert portuguese_number(2345) == "dois mil trezentos e quarenta e cinco".split()
    assert portuguese_number(1_000_000) == "um milhão".split() and portuguese_number(3_000_000) == "três milhões".split()
    assert normalize_text("1,57 e 2.022", "pt-BR") == "um virgula cinquenta e sete e dois mil e vinte e dois".split()
    assert normalize_text("100% e 1.000.000", "pt") == "cem por cento e um milhao".split()
    assert number_words("1,5", "pt") == ["um", "vírgula", "cinco"]  # accents folded only by normalize_text


def test_other_languages_keep_digits() -> None:
    assert normalize_text("Das kostet 1.000,5 Euro", "de") == ["das", "kostet", "1000", "5", "euro"]
    assert normalize_text("1,000.5 yen", "ja") == ["1000", "5", "yen"]


def test_case_punctuation_hyphens_acronyms_accents() -> None:
    assert normalize_text("So, are our networks over-parameterized?") == "so are our networks over parameterized".split()
    assert normalize_text("one-by-one/two") == "one by one two".split()
    assert normalize_text("The K-Phi-3 model") == ["the", "k", "phi", "three", "model"]
    gpu = ["a", "gpu"]
    assert normalize_text("a GPU") == normalize_text("a G.P.U.") == normalize_text("a G P U") == gpu
    assert normalize_text("Let's see the baseline’s loss") == "lets see the baselines loss".split()
    assert normalize_text("Você já viu São João Gómez? Ação!", "pt-BR") == "voce ja viu sao joao gomez acao".split()
    assert normalize_text("R&D + more = fun", "en") == "r and d plus more equals fun".split()
    assert normalize_text("A dense layer, I think") == "a dense layer i think".split()  # single capitals alone stay words


# ----- alignment and word error rate --------------------------------------------------------------


def test_align_and_wer() -> None:
    ref, hyp = "the cat sat on the mat".split(), "the cat sit on mat today".split()
    ops = align(ref, hyp)
    assert [o.op for o in ops] == ["equal", "equal", "substitute", "equal", "delete", "equal", "insert"]
    assert word_error_rate(ref, hyp) == pytest.approx(3 / 6)
    assert word_error_rate(ref, ref) == 0.0
    assert word_error_rate([], []) == 0.0 and word_error_rate([], ["x"]) == 1.0
    assert word_error_rate(["a"], []) == 1.0
    assert sorted(o.op for o in align(["a", "b"], ["x", "y", "z"])) == ["insert", "substitute", "substitute"]
    assert [(o.ref, o.hyp) for o in align(["a", "b"], ["a", "x", "b"])] == [(0, 0), (None, 1), (1, 2)]


# ----- comparing a beat ---------------------------------------------------------------------------

PRON = Pronunciation([compile_rule("K-Phi-3", "kay fye three", 0)])


def compare(text: str, heard: str | Transcript, pron: Pronunciation = PRON, language: str | None = None):
    transcript = heard if isinstance(heard, Transcript) else Transcript(heard)
    return compare_beat("s", "b", pron.apply(text), transcript, language)


def test_writing_differences_are_not_errors() -> None:
    text = "The two-layer K-Phi-3 has just 35 million. That's fifteen percent!"
    for heard in (
        "The two layer K Phi 3 has just 35 million. That's 15%.",  # STT wrote the term as written
        "the two-layer kay fye three has just thirty-five million thats fifteen percent",  # the spoken form
        "The twolayer KPhi3 has just 35,000,000. That's fifteen percent.",  # joined words, grouped digits
    ):
        result = compare(text, heard)
        assert (result.errors, result.edits) == (0, []), heard
    assert result.words == 14 and result.wer == 0.0  # the spoken text's words


def test_pronunciation_entry_misheard() -> None:
    result = compare("The two-layer K-Phi-3 has just 35 million.", "The two-layer kay five three has just 35 million.")
    (edit,) = result.edits
    assert (edit.kind, edit.written, edit.said, edit.expected, edit.heard) == (
        "substitution", "K-Phi-3", "kay fye three", "kay fye three", "kay five three")
    assert edit.term == "K-Phi-3" and edit.entry and edit.errors == 1
    assert 'pronunciation entry "K-Phi-3" (says "kay fye three")' in edit.suggestion
    assert edit.describe() == 'expected "K-Phi-3" (said "kay fye three"), heard "kay five three"'
    assert result.counts == {"substitutions": 1, "deletions": 0, "insertions": 0}


def test_term_without_entry_gets_a_suggestion() -> None:
    result = compare("Every experiment ran on a single NVIDIA L4 GPU.", "Every experiment ran on a single and video L4 GPU.")
    (edit,) = result.edits
    assert (edit.written, edit.heard, edit.term, edit.entry, edit.errors) == ("NVIDIA", "and video", "NVIDIA", False, 2)
    assert "add a pronunciation entry `NVIDIA: <how to say it>`" in edit.suggestion
    assert result.wer == pytest.approx(2 / 10)  # "L4": two words
    number = compare("It has 227 million.", "It has 207 million.").edits[0]
    assert number.term == "227" and "<the number in words>" in number.suggestion


def test_insertions_deletions_and_times() -> None:
    words = tuple(TranscriptWord(w, 0.5 * i, 0.5 * i + 0.4) for i, w in enumerate("Biological brains are the the opposite".split()))
    result = compare("Biological brains are the opposite. They connect.", Transcript("", words))
    assert [(e.kind, e.written, e.heard) for e in result.edits] == [
        ("insertion", "are", "are the"), ("deletion", "They connect", "")]
    extra, missing = result.edits
    assert extra.at == 1.5 and extra.term is None and "extra words heard" in extra.suggestion
    assert missing.at is None and "words missing from the audio" in missing.suggestion
    assert missing.describe() == 'expected "They connect", heard nothing'
    assert result.errors == 3 and result.words == 7


def test_portuguese_accents_and_names() -> None:
    text = "Este relatório, de João Paulo Schwarz Schuler, mostra que é possível: 1,57."
    result = compare(text, "Este relatorio de Joao Paulo Schwarz Schuler mostra que e possivel, um vírgula cinquenta e sete", language="pt-BR")
    assert result.errors == 0
    result = compare(text, "Este relatório de João Paulo Schwartz Shuler mostra que é possível 1,57", language="pt-BR")
    assert [(e.written, e.heard, e.term) for e in result.edits] == [("Schwarz Schuler", "schwartz shuler", "Schwarz")]


def test_hard_terms() -> None:
    words = "So the NVIDIA GPU of Microsoft's LaMini, João and Phi-3 at 1.57. Then I said".split()
    assert [w for i, w in enumerate(words) if hard_term(words, i)] == ["NVIDIA", "GPU", "Microsoft's", "LaMini,", "João", "Phi-3", "1.57."]


# ----- STT settings and providers ----------------------------------------------------------------


def test_stt_settings_defaults(make_project) -> None:
    project = Project.load(make_project())
    assert stt_settings(project) == {"provider": "faster_whisper", "model": "small.en", "language": "en"}
    project = Project.load(make_project(minimal_config(language="pt-BR")))
    assert stt_settings(project) == {"provider": "faster_whisper", "model": "small", "language": "pt"}
    project = Project.load(make_project(minimal_config(stt={"language": "auto", "model": "base"})))
    assert stt_settings(project) == {"provider": "faster_whisper", "model": "base", "language": None}
    project = Project.load(make_project(minimal_config(stt={"provider": "elevenlabs", "language": "es-419"})))
    assert stt_settings(project) == {"provider": "elevenlabs", "model": "scribe_v1", "language": "es"}
    assert isinstance(get_stt_provider(project), ElevenLabsSTTProvider)
    for bad in ({"provider": "whisper"}, {"language": "english"}, {"device": "gpu"}, {"modle": "x"}):
        with pytest.raises(VidgenError, match="stt"):
            parse_config(minimal_config(stt=bad))


class FakeWhisper:
    """A stand-in for faster_whisper.WhisperModel."""

    calls: list[dict[str, Any]] = []
    loaded: list[tuple[str, str]] = []

    def __init__(self, model: str, device: str = "auto") -> None:
        if model == "missing":
            raise OSError("no such model")
        FakeWhisper.loaded.append((model, device))

    def transcribe(self, path: str, **options: Any) -> tuple[Any, Any]:
        FakeWhisper.calls.append({"path": path, **options})
        word = types.SimpleNamespace
        segments = [
            types.SimpleNamespace(text=" Hello there.", words=[word(word=" Hello", start=0.1, end=0.4), word(word=" there.", start=0.5, end=0.9)]),
            types.SimpleNamespace(text=" Bye", words=[word(word=" Bye", start=1.2, end=1.5)]),
        ]
        return iter(segments), types.SimpleNamespace(language="en")


@pytest.fixture
def fake_faster_whisper(monkeypatch: pytest.MonkeyPatch) -> type[FakeWhisper]:
    FakeWhisper.calls, FakeWhisper.loaded = [], []
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisper))
    return FakeWhisper


def test_faster_whisper_provider(fake_faster_whisper: type[FakeWhisper], tmp_path: Path) -> None:
    provider = FasterWhisperProvider("small.en", "en", device="cpu")
    provider.check_available()
    transcript = provider.transcribe(tmp_path / "b.mp3")
    assert transcript == Transcript(
        "Hello there. Bye", (TranscriptWord("Hello", 0.1, 0.4), TranscriptWord("there.", 0.5, 0.9), TranscriptWord("Bye", 1.2, 1.5)), "en")
    provider.transcribe(tmp_path / "c.mp3")
    assert fake_faster_whisper.loaded == [("small.en", "cpu")]  # loaded once
    call = fake_faster_whisper.calls[0]
    assert call["path"] == str(tmp_path / "b.mp3") and call["language"] == "en"
    assert call["word_timestamps"] is True and call["condition_on_previous_text"] is False
    with pytest.raises(VidgenError, match="cannot load the Whisper model 'missing': OSError: no such model"):
        FasterWhisperProvider("missing", None).transcribe(tmp_path / "b.mp3")


def test_faster_whisper_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import raises ImportError
    with pytest.raises(VidgenError, match=r'pip install "schu-video-generator\[stt\]"'):
        FasterWhisperProvider("small", "en").check_available()


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_elevenlabs_stt_request_and_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sent: list[urllib.request.Request] = []
    reply = {
        "language_code": "eng", "text": "Hello there.",
        "words": [{"text": "Hello", "start": 0.1, "end": 0.4, "type": "word"}, {"text": " ", "start": 0.4, "end": 0.5, "type": "spacing"},
                  {"text": "there.", "start": 0.5, "end": 0.9, "type": "word"}, {"text": "(laughs)", "start": 1, "end": 2, "type": "audio_event"}],
    }

    def urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
        sent.append(request)
        return FakeResponse(json.dumps(reply).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-test")
    mp3 = tmp_path / "s1_b1.mp3"
    mp3.write_bytes(b"ID3fake-audio")
    transcript = ElevenLabsSTTProvider("scribe_v1", "en").transcribe(mp3)
    assert transcript == Transcript("Hello there.", (TranscriptWord("Hello", 0.1, 0.4), TranscriptWord("there.", 0.5, 0.9)), "eng")
    (request,) = sent
    assert request.full_url == STT_URL and request.get_header("Xi-api-key") == "sk-test"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=vidgen-")
    body = request.data
    assert isinstance(body, bytes)
    for part in (b'name="model_id"\r\n\r\nscribe_v1', b'name="language_code"\r\n\r\nen', b'name="timestamps_granularity"\r\n\r\nword',
                 b'filename="s1_b1.mp3"\r\nContent-Type: audio/mpeg\r\n\r\nID3fake-audio\r\n'):
        assert part in body
    assert b"language_code" not in ElevenLabsSTTProvider("scribe_v1", None).form_fields().__repr__().encode()


def test_elevenlabs_stt_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(VidgenError, match="ELEVENLABS_API_KEY"):
        ElevenLabsSTTProvider("scribe_v1", None).check_available()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-test")

    def refuse(request: urllib.request.Request, timeout: float) -> FakeResponse:
        raise urllib.error.HTTPError(STT_URL, 401, "Unauthorized", None, io.BytesIO(b'{"detail": "bad key sk-test"}'))  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    (tmp_path / "a.mp3").write_bytes(b"x")
    with pytest.raises(VidgenError, match=r"HTTP 401: \{\"detail\": \"bad key \*\*\*\"\}"):
        ElevenLabsSTTProvider("scribe_v1", None, sleep=lambda s: None).transcribe(tmp_path / "a.mp3")
    with pytest.raises(VidgenError, match="unreadable speech-to-text response"):
        parse_response(b"{}")


# ----- the command: cache, skipped beats, suggestions --------------------------------------------

TEXTS = {
    "intro_b1": "The two-layer K-Phi-3 has just 35 million.",
    "intro_b2": "Every experiment ran on a single NVIDIA L4 GPU.",
    "custom": "K-Phi-3 needs only 53 million, or twenty-three percent.",
}
HEARD = {
    "intro_b1": "The two-layer kay five three has just 35 million.",
    "intro_b2": "Every experiment ran on a single and video L4 GPU.",
    "custom": "Kay five tree needs only 53 million or 23%.",
}


class FakeSTT:
    """A provider hearing ``HEARD`` (by the MP3's beat id), counting its calls."""

    name = "fake"

    def __init__(self, heard: dict[str, str] | None = None) -> None:
        self.heard = HEARD if heard is None else heard
        self.calls: list[str] = []

    def check_available(self) -> None:
        pass

    def transcribe(self, path: Path) -> Transcript:
        self.calls.append(path.stem)
        return Transcript(self.heard[path.stem])


def readback_config(**overrides: Any) -> dict[str, Any]:
    data = minimal_config(pronunciation={"K-Phi-3": "kay fye three"}, **overrides)
    data["scenes"][0]["beats"] = [{"text": TEXTS["intro_b1"]}, {"text": TEXTS["intro_b2"]}]
    data["scenes"][1]["beats"] = [{"id": "custom", "text": TEXTS["custom"]}]
    return data


def write_audio(project: Project, beats: list[str]) -> None:
    """Fake MP3s with up-to-date hash files (the bytes are never decoded here)."""
    from vidgen.tts import beat_providers

    providers, spoken = beat_providers(project), project.spoken_texts()
    project.audio_dir.mkdir(parents=True, exist_ok=True)
    for beat in beats:
        (project.audio_dir / f"{beat}.mp3").write_bytes(f"audio of {beat}".encode())
        (project.audio_dir / f"{beat}.hash").write_text(providers[beat].cache_key(spoken[beat]), encoding="utf-8")


@pytest.fixture
def rb_project(make_project) -> Path:
    root = make_project(readback_config())
    write_audio(Project.load(root), ["intro_b1", "intro_b2", "custom"])
    return root


def test_run_readback_flags_and_suggests(rb_project: Path) -> None:
    stt = FakeSTT()
    lines: list[str] = []
    result = run_readback(Project.load(rb_project), provider=stt, log=lines.append)
    assert stt.calls == ["intro_b1", "intro_b2", "custom"] and (result.transcribed, result.cached) == (3, 0)
    assert lines[0].startswith("[1/3] transcribed intro_b1 (")
    b1, b2, custom = result.beats
    assert [b.flagged for b in result.beats] == [False, True, True]  # 1/11, 2/10, 2/12 against 0.1
    assert b1.wer == pytest.approx(1 / 11) and b2.wer == pytest.approx(2 / 10) and custom.wer == pytest.approx(2 / 12)
    assert [(e.written, e.heard) for e in custom.edits] == [("K-Phi-3", "kay five tree")]  # "23%" = "twenty-three percent"
    assert b2.suggestions == ['"NVIDIA" is heard as "and video": add a pronunciation entry `NVIDIA: <how to say it>`, then `vidgen tts`']
    assert [b.beat for b in result.worst()] == ["intro_b2", "custom", "intro_b1"]
    (term, nvidia) = result.terms()
    assert (term.term, term.entry, term.beats, term.consistent) == ("K-Phi-3", True, ["intro_b1", "custom"], True)
    assert "misheard in 2 beats despite its pronunciation entry" in term.suggestion
    assert not nvidia.consistent and nvidia.beats == ["intro_b2"]


def test_transcripts_are_cached_by_audio_and_settings(rb_project: Path) -> None:
    project = Project.load(rb_project)
    run_readback(project, provider=FakeSTT(), log=lambda s: None)
    files = sorted((rb_project / "build" / "readback").glob("*.json"))
    assert len(files) == 3
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["version"] == 1 and doc["stt"] == {"provider": "faster_whisper", "model": "small.en", "language": "en"}
    assert set(doc["transcript"]) == {"text", "language", "words"}

    stt = FakeSTT()
    again = run_readback(project, provider=stt, log=lambda s: None)
    assert stt.calls == [] and (again.transcribed, again.cached) == (0, 3) and all(b.cached for b in again.beats)
    assert [b.wer for b in again.beats] == [b.wer for b in run_readback(project, provider=FakeSTT(), log=lambda s: None).beats]

    run_readback(project, provider=stt, force=True, log=lambda s: None)
    assert stt.calls == ["intro_b1", "intro_b2", "custom"]

    (project.audio_dir / "intro_b2.mp3").write_bytes(b"new audio")  # new audio: only that beat again
    stt = FakeSTT()
    result = run_readback(project, provider=stt, log=lambda s: None)
    assert stt.calls == ["intro_b2"] and result.beats[1].audio == "ok"

    data = readback_config(stt={"model": "base.en"})  # other settings: all again
    (rb_project / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    stt = FakeSTT()
    run_readback(Project.load(rb_project), provider=stt, beat_ids=["custom"], log=lambda s: None)
    assert stt.calls == ["custom"]


def test_missing_stale_and_unknown_beats(make_project) -> None:
    root = make_project(readback_config())
    project = Project.load(root)
    write_audio(project, ["intro_b1", "custom"])
    (project.audio_dir / "custom.hash").write_text("outdated", encoding="utf-8")
    result = run_readback(project, provider=FakeSTT(), log=lambda s: None)
    assert result.skipped == [("intro_b2", "no audio (run `vidgen tts`)")]
    custom = result.beats[1]
    assert custom.audio == "stale" and custom.suggestions[0].startswith("the audio is stale")
    assert run_readback(project, provider=FakeSTT(), beat_ids=["intro_b1"], log=lambda s: None).beats[0].beat == "intro_b1"
    with pytest.raises(VidgenError, match="unknown beat"):
        run_readback(project, provider=FakeSTT(), beat_ids=["nope"])
    with pytest.raises(VidgenError, match="max-wer"):
        run_readback(project, provider=FakeSTT(), max_wer=1.5)


def test_nothing_to_transcribe_needs_no_provider(rb_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = Project.load(rb_project)
    run_readback(project, provider=FakeSTT(), log=lambda s: None)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # not installed: fine while all is cached
    assert run_readback(project, log=lambda s: None).cached == 3
    with pytest.raises(VidgenError, match="schu-video-generator\\[stt\\]"):
        run_readback(project, force=True, log=lambda s: None)


def test_cli_human_and_json(rb_project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("vidgen.stt.get_stt_provider", lambda project: FakeSTT())
    assert main(["readback", str(rb_project)]) == 0
    out = capsys.readouterr().out
    assert "readback: 3 beats (faster_whisper small.en, language en); 3 transcribed, 0 cached; word error rate" in out
    assert "flagged (word error rate above 10%): 2" in out
    assert '    expected "NVIDIA", heard "and video"' in out and "    fix: " in out
    assert "worst: intro_b2 20%, custom 17%, intro_b1 9%" in out
    assert "  K-Phi-3: 2 beats (intro_b1, custom)" in out

    code, doc, _ = run_json(["readback", str(rb_project), "--json", "--max-wer", "0.05"], capsys)
    assert code == 0 and doc["ok"] and doc["command"] == "readback"
    assert doc["stt"] == {"provider": "faster_whisper", "model": "small.en", "language": "en"}
    assert (doc["transcribed"], doc["cached"], doc["max_wer"]) == (0, 3, 0.05)
    assert doc["summary"]["flagged"] == ["intro_b1", "intro_b2", "custom"] and doc["summary"]["words"] == 33
    beat = doc["beats"][1]
    assert beat["edits"][0] == {
        "kind": "substitution", "expected": "nvidia", "heard": "and video", "written": "NVIDIA", "said": None, "after": None,
        "errors": 2, "at": None, "term": "NVIDIA", "entry": False, "suggestion": beat["suggestions"][0]}
    assert doc["terms"][0]["term"] == "K-Phi-3" and doc["terms"][0]["consistent"]
    documented(*[k for k in doc if k not in ("version", "vidgen", "command", "ok", "warnings")])
    documented(*beat, *beat["edits"][0], *doc["summary"], *doc["terms"][0])

    code, doc, _ = run_json(["readback", str(rb_project), "--json", "--beat", "nope"], capsys)
    assert code == 1 and "unknown beat" in doc["error"]["message"]


# ----- the lint rule ------------------------------------------------------------------------------


def test_readback_rule_reads_only_cached_transcripts(make_project) -> None:
    root = make_project(readback_config(preview={"width": 854, "height": 480, "fps": 15}))
    project = Project.load(root)
    write_audio(project, ["intro_b1", "intro_b2", "custom"])
    project = Project.load(root)
    fake_render(project, "intro", [[], []])
    fake_render(project, "main", [[]])
    assert lint_project(project, rules=["readback"]).findings == []  # no transcripts yet: nothing

    run_readback(project, provider=FakeSTT(), log=lambda s: None)
    result = lint_project(project, rules=["readback"])
    assert [(f.beat, f.severity, f.value, f.limit) for f in result.findings] == [
        ("intro_b2", "warning", 0.2, 0.1), ("custom", "warning", round(2 / 12, 4), 0.1)]
    message = result.findings[0].message
    assert message.startswith('the audio is heard differently from the text: 2 of 10 words (20%): expected "NVIDIA", heard "and video"')
    assert message.endswith("(details: `vidgen readback --beat intro_b2`)") and "fix: " in message
    assert result.findings[0].scene_time == 1.0  # the beat's start (fake activity file)

    data = readback_config(preview={"width": 854, "height": 480, "fps": 15}, lint={"rules": {"readback": {"max_wer": 0.3}}})
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert lint_project(Project.load(root), rules=["readback"]).findings == []  # lint settings: no re-render needed
    data["lint"] = {"rules": {"readback": {"severity": "off"}}}
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert lint_project(Project.load(root), rules=["readback"]).findings == []


def test_readback_rule_unit(rb_project: Path) -> None:
    project = Project.load(rb_project)
    assert cached_readback(project, ["intro_b1"]) == {}
    run_readback(project, provider=FakeSTT(), log=lambda s: None)
    cached = cached_readback(project, ["intro_b1", "intro_b2", "nope"])
    assert sorted(cached) == ["intro_b1", "intro_b2"] and all(b.cached for b in cached.values())
    activity = {"beats": [{"id": "intro_b1", "start": 0.0}, {"id": "intro_b2", "start": 2.5}]}
    ctx = SceneContext("intro", activity, project.audio_dir, readback=cached)
    issues = list(RULES["readback"].check(ctx, ReadbackRule(max_wer=0.05)))
    assert [(i.beat, i.time) for i in issues] == [("intro_b1", 0.0), ("intro_b2", 2.5)]


def test_stt_settings_do_not_change_the_fingerprint(make_project) -> None:
    root = make_project(minimal_config())
    before = fingerprint.scene_fingerprint(Project.load(root), "intro")
    (root / "video.yaml").write_text(yaml.safe_dump(minimal_config(stt={"provider": "elevenlabs"})), encoding="utf-8")
    assert fingerprint.scene_fingerprint(Project.load(root), "intro") == before
    package = Path(fingerprint.__file__).resolve().parent.parent
    for rel in ("readback.py", "textnorm.py", "stt/__init__.py", "lint/readback_rule.py"):
        assert not fingerprint._render_input(package / rel), rel


def test_docs_describe_readback() -> None:
    assert "## Readback (`vidgen readback`)" in CONFIG_MD
    block = CONFIG_MD[CONFIG_MD.index("```yaml\nstt:") :]
    documented_stt = yaml.safe_load(block[8 : block.index("```", 8)])["stt"]
    assert documented_stt == parse_config(minimal_config()).stt.model_dump()
