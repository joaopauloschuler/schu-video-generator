"""Step 141: flag badly spoken words — low recogniser confidence, unusual pauses and differences
with the text, per beat, with times and a suggested fix (``vidgen readback``, ``vidgen lint
--readback``). The recogniser is mocked: no model is loaded."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from conftest import minimal_config
from test_json_output import documented, run_json
from test_lint import fake_render
from test_readback import readback_config, write_audio, write_sine
from vidgen.cli import main
from vidgen.config import UnclearSpeechRule, parse_config
from vidgen.errors import VidgenError
from vidgen.lint import lint_project
from vidgen.project import Project
from vidgen.pronunciation import Pronunciation, compile_rule
from vidgen.readback import audio_digest, cache_path, compare_beat, report_lines, run_readback, write_cached
from vidgen.render import fingerprint
from vidgen.speech_flags import WordFlag, flag_words
from vidgen.stt import Transcript, TranscriptWord, stt_settings
from vidgen.stt.faster_whisper import SAMPLE_RATE, FasterWhisperProvider, load_audio

SETTINGS = UnclearSpeechRule()
NO_ENTRIES = Pronunciation([])
Word = tuple[str, float, float, float | None]


def heard(*items: Word) -> Transcript:
    return Transcript(" ".join(i[0] for i in items), tuple(TranscriptWord(*i) for i in items))


def flags_of(text: str, transcript: Transcript, pron: Pronunciation = NO_ENTRIES, pauses: set[int] | None = None) -> list[WordFlag]:
    spoken = pron.apply(text)
    return flag_words(compare_beat("s", "b", spoken, transcript), spoken, SETTINGS, pauses or set())


def summary(flags: list[WordFlag]) -> list[tuple[str, str, str, list[str]]]:
    return [(f.word, f.written, f.level, f.reasons) for f in flags]


# ----- the flags of a beat ------------------------------------------------------------------------


def test_low_probability_words_are_unclear_or_doubtful() -> None:
    transcript = heard(("One,", 0.0, 0.3, 0.99), ("two,", 0.5, 0.8, 0.22), ("three.", 1.0, 1.3, 0.6),
                       ("That", 2.0, 2.2, 0.95), ("is", 2.25, 2.4, 0.9), ("all.", 2.45, 2.8, 0.98))
    flags = flags_of("One, two, three. That is all.", transcript)
    assert summary(flags) == [("two", "two", "unclear", ["low_probability"]), ("three", "three", "doubtful", ["low_probability"])]
    two = flags[0]
    assert (two.start, two.end, two.probability, two.gap) == (0.5, 0.8, 0.22, None)
    assert two.detail == '"two", heard with probability 0.22'
    assert two.suggestion.startswith('listen to "two": if it is slurred, change how the beat is said')
    assert "`two: <respelling>`" in two.suggestion
    # the 0.7 s pause after "three." is at a full stop: expected
    assert two.to_json() == {
        "scene": "s", "beat": "b", "word": "two", "written": "two", "level": "unclear", "reasons": ["low_probability"],
        "time": 0.5, "end": 0.8, "video_time": None, "probability": 0.22, "gap": None, "detail": two.detail,
        "suggestion": two.suggestion,
    }


def test_pause_inside_a_sentence() -> None:
    def transcript(gap: float, word: str = "is") -> Transcript:
        return heard(("The", 0.0, 0.2, 0.99), ("box", 0.25, 0.5, 0.99), (word, 0.55, 0.7, 0.99),
                     ("humming", 0.7 + gap, 1.1 + gap, 0.99), ("a", 1.15 + gap, 1.2 + gap, 0.99), ("song.", 1.25 + gap, 1.6 + gap, 0.99))

    (flag,) = flags_of("The box is humming a song.", transcript(0.8))
    assert summary([flag]) == [("humming", "humming", "unclear", ["gap"])]
    assert flag.gap == pytest.approx(0.8) and flag.detail == '"humming", after a 0.80 s pause inside the sentence'
    assert flag.suggestion.startswith('listen to the pause before "humming"') and "write a comma there" in flag.suggestion
    assert flags_of("The box is humming a song.", transcript(0.4)) == []  # not above max_gap
    assert flags_of("The box is, humming a song.", transcript(0.8)) == []  # a comma in the text
    assert flags_of("The box is humming a song.", transcript(0.8, "is,")) == []  # a comma in the transcript
    assert flags_of("The box is humming a song.", transcript(0.8), pauses={3}) == []  # a voice sound before "humming"


def test_difference_merged_with_its_words() -> None:
    transcript = heard(("Every", 0.0, 0.3, 0.99), ("run", 0.35, 0.6, 0.99), ("used", 0.65, 0.9, 0.99), ("one", 0.95, 1.1, 0.99),
                       ("and", 1.2, 1.3, 0.3), ("video", 1.35, 1.7, 0.8), ("GPU.", 1.8, 2.3, 0.97))
    (flag,) = flags_of("Every run used one NVIDIA GPU.", transcript)
    assert summary([flag]) == [("and video", "NVIDIA", "unclear", ["low_probability", "mismatch"])]
    assert (flag.start, flag.end, flag.probability) == (1.2, 1.7, 0.3)
    assert flag.detail == 'expected "NVIDIA", heard "and video", heard with probability 0.30'
    assert flag.suggestion == '"NVIDIA" is heard as "and video": add a pronunciation entry `NVIDIA: <how to say it>`, then `vidgen tts`'

    one_word = heard(("the", 0.0, 0.2, 0.95), ("cat", 0.25, 0.5, 0.95), ("sit", 0.55, 0.8, 0.95))
    assert summary(flags_of("the cat sat", one_word)) == [("sit", "sat", "doubtful", ["mismatch"])]  # maybe a slip


def test_words_not_heard() -> None:
    transcript = heard(*((w, 0.5 * i, 0.5 * i + 0.4, 0.99) for i, w in enumerate("Biological brains are the opposite.".split())))
    (flag,) = flags_of("Biological brains are the opposite. They connect.", transcript)
    assert summary([flag]) == [("", "They connect", "unclear", ["mismatch"])]
    assert flag.start == flag.end == 2.4  # the end of the last word heard before them
    assert flag.detail == 'expected "They connect", heard nothing'


def test_suggestions_for_terms() -> None:
    pron = Pronunciation([compile_rule("K-Phi-3", "kay fye three", 0)])
    transcript = heard(("The", 0.0, 0.2, 0.99), ("kay", 0.3, 0.5, 0.9), ("fye", 0.55, 0.8, 0.3), ("three", 0.85, 1.1, 0.9),
                       ("model.", 1.2, 1.6, 0.99))
    (flag,) = flags_of("The K-Phi-3 model.", transcript, pron)
    assert (flag.word, flag.written, flag.level) == ("fye", "K-Phi-3", "unclear")
    assert flag.suggestion.startswith('the pronunciation entry "K-Phi-3" (says "kay fye three") is not heard clearly: respell')

    transcript = heard(("Ask", 0.0, 0.2, 0.99), ("Bram", 0.3, 0.6, 0.4), ("now.", 0.7, 1.0, 0.99))
    (flag,) = flags_of("Ask Bram now.", transcript)
    assert flag.suggestion == '"Bram" is not heard clearly: add a pronunciation entry `Bram: <how to say it>` (a respelling), then `vidgen tts`'


def test_without_probabilities_or_times() -> None:
    no_probabilities = heard(("The", 0.0, 0.2, None), ("box", 0.25, 0.5, None), ("hums.", 0.55, 0.9, None))
    assert flags_of("The box hums.", no_probabilities) == []  # ElevenLabs: no probabilities, only pauses and differences
    (flag,) = flags_of("The box hums.", Transcript("The fox hums."))
    assert summary([flag]) == [("fox", "box", "doubtful", ["mismatch"])] and flag.start is None


def test_not_a_render_input() -> None:
    package = Path(fingerprint.__file__).resolve().parent.parent
    assert not fingerprint._render_input(package / "speech_flags.py")


def test_settings() -> None:
    assert parse_config(minimal_config()).lint.rules.unclear_speech == UnclearSpeechRule(min_probability=0.5, doubtful_probability=0.75, max_gap=0.5)
    for bad in ({"min_probability": 0.8, "doubtful_probability": 0.6}, {"max_gap": 0}, {"min_probability": 1.5}):
        with pytest.raises(VidgenError, match="unclear_speech"):
            parse_config(minimal_config(lint={"rules": {"unclear_speech": bad}}))


# ----- transcripts and the faster-whisper provider ------------------------------------------------


def test_transcript_keeps_probabilities() -> None:
    transcript = heard(("Hi", 0.1, 0.3, 0.87654), ("there", 0.4, 0.7, None))
    doc = transcript.to_json()
    assert doc["words"] == [["Hi", 0.1, 0.3, 0.8765], ["there", 0.4, 0.7]]
    back = Transcript.from_json(doc)
    assert back.word_probabilities() == [0.8765, None] and back.has_probabilities
    old = Transcript.from_json({"text": "Hi", "words": [["Hi", 0.1, 0.3]]})  # cached before Step 141
    assert old.word_probabilities() == [None] and not old.has_probabilities
    assert Transcript("a b").word_probabilities() == [None, None]


class ProbabilityWhisper:
    """A stand-in for faster_whisper.WhisperModel whose words have probabilities."""

    audio: list[Any] = []

    def __init__(self, model: str, device: str = "auto") -> None:
        pass

    def transcribe(self, audio: Any, **options: Any) -> tuple[Any, Any]:
        ProbabilityWhisper.audio.append(audio)
        word = types.SimpleNamespace
        segment = types.SimpleNamespace(text=" Hello there.", words=[word(word=" Hello", start=0.1, end=0.4, probability=0.91),
                                                                      word(word=" there.", start=0.5, end=0.9, probability=0.22)])
        return iter([segment]), types.SimpleNamespace(language="en")


def test_faster_whisper_words_have_probabilities(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=ProbabilityWhisper))
    transcript = FasterWhisperProvider("small", "en").transcribe(write_sine(tmp_path / "b.mp3", 1.0))
    assert [(w.text, w.probability) for w in transcript.words] == [("Hello", 0.91), ("there.", 0.22)]


def test_load_audio_decodes_with_ffmpeg_not_pyav(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def no_pyav(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("decoded with PyAV")

    monkeypatch.setattr("vidgen.sfx.decode_audio", no_pyav)
    audio = load_audio(write_sine(tmp_path / "b.mp3", 1.5))
    assert audio.ndim == 1 and audio.dtype == np.float32 and abs(len(audio) - 1.5 * SAMPLE_RATE) < 0.1 * SAMPLE_RATE
    assert 0.2 < np.abs(audio).max() < 0.5


# ----- vidgen readback ------------------------------------------------------------------------------

WORDS: dict[str, list[Word]] = {
    "intro_b1": [("The", 0.0, 0.2, 0.99), ("two-layer", 0.25, 0.6, 0.95), ("kay", 0.7, 0.8, 0.9), ("fye", 0.85, 1.0, 0.9),
                 ("three", 1.05, 1.3, 0.9), ("has", 2.1, 2.3, 0.97), ("just", 2.35, 2.5, 0.97), ("35", 2.55, 2.9, 0.97),
                 ("million.", 2.95, 3.4, 0.97)],
    "intro_b2": [("Every", 0.0, 0.3, 0.99), ("experiment", 0.35, 0.9, 0.99), ("ran", 0.95, 1.1, 0.99), ("on", 1.15, 1.25, 0.99),
                 ("a", 1.3, 1.35, 0.99), ("single", 1.4, 1.7, 0.6), ("NVIDIA", 1.75, 2.2, 0.99), ("L4", 2.25, 2.6, 0.99),
                 ("GPU.", 2.65, 3.0, 0.99)],
    "custom": [("K-Phi-3", 0.0, 0.6, 0.99), ("needs", 0.65, 0.9, 0.99), ("only", 0.95, 1.1, 0.99), ("53", 1.15, 1.5, 0.99),
               ("million,", 1.55, 2.0, 0.99), ("or", 2.4, 2.5, 0.99), ("23%.", 2.55, 3.2, 0.99)],
}


class WordSTT:
    """A provider hearing ``WORDS`` (by the MP3's beat id), counting its calls."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def check_available(self) -> None:
        pass

    def transcribe(self, path: Path) -> Transcript:
        self.calls.append(path.stem)
        return heard(*WORDS[path.stem])


@pytest.fixture
def project_root(make_project) -> Path:
    root = make_project(readback_config(preview={"width": 854, "height": 480, "fps": 15}))
    write_audio(Project.load(root), ["intro_b1", "intro_b2", "custom"])
    return root


def test_readback_flags_words(project_root: Path) -> None:
    project = Project.load(project_root)
    result = run_readback(project, provider=WordSTT(), log=lambda s: None)
    flags = result.flags
    # intro_b1: 0.8 s pause before "has" (inside the sentence); intro_b2: "single" doubtful
    assert [(f.beat, f.word, f.level, f.reasons) for f in flags] == [
        ("intro_b1", "has", "unclear", ["gap"]), ("intro_b2", "single", "doubtful", ["low_probability"])]
    assert flags[0].gap == pytest.approx(0.8) and flags[0].video_time is None  # no render yet
    lines = report_lines(result)
    assert "words to check: 1 unclear, 1 doubtful (probability below 0.5 / 0.75, pauses over 0.5 s inside a sentence, differences)" in lines
    assert '  unclear  intro_b1 @ 2.10s: "has", after a 0.80 s pause inside the sentence' in lines

    fake_render(project, "intro", [[], []])  # timings: intro 0-3 s, both beats from 0 s; main from 3 s
    fake_render(project, "main", [[]])
    result = run_readback(Project.load(project_root), provider=WordSTT(), log=lambda s: None)
    assert [f.video_time for f in result.flags] == [2.1, 1.4]
    assert '  unclear  intro_b1 @ 2.10s (video 2.10s): "has", after a 0.80 s pause inside the sentence' in report_lines(result)


def test_readback_thresholds_from_lint_settings(project_root: Path) -> None:
    data = readback_config(lint={"rules": {"unclear_speech": {"doubtful_probability": 0.5, "max_gap": 1.0}}})
    (project_root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert run_readback(Project.load(project_root), provider=WordSTT(), log=lambda s: None).flags == []


def test_old_cached_transcripts_without_probabilities_are_redone(project_root: Path) -> None:
    project = Project.load(project_root)
    settings = stt_settings(project)
    for beat in ("intro_b1", "intro_b2"):
        mp3 = project.audio_dir / f"{beat}.mp3"
        digest = audio_digest(mp3)
        words = tuple(TranscriptWord(t, s, e) for t, s, e, _ in WORDS[beat])
        probabilities = beat == "intro_b2"
        stored = heard(*WORDS[beat]) if probabilities else Transcript("x", words)
        write_cached(cache_path(project, digest, settings), digest, settings, stored, beat)
    stt = WordSTT()
    result = run_readback(project, provider=stt, log=lambda s: None)
    assert stt.calls == ["intro_b1", "custom"] and result.cached == 1  # faster_whisper: redone (local, free)


def test_readback_json(project_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("vidgen.stt.get_stt_provider", lambda project: WordSTT())
    code, doc, _ = run_json(["readback", str(project_root), "--json"], capsys)
    assert code == 0 and doc["flag_thresholds"] == {"min_probability": 0.5, "doubtful_probability": 0.75, "max_gap": 0.5}
    assert (doc["summary"]["unclear"], doc["summary"]["doubtful"]) == (1, 1)
    flag = doc["beats"][0]["flags"][0]
    assert (flag["beat"], flag["word"], flag["time"], flag["gap"], flag["level"]) == ("intro_b1", "has", 2.1, 0.8, "unclear")
    documented("flag_thresholds", "unclear", "doubtful", "flags", *flag)
    documented(*doc["flag_thresholds"])


# ----- vidgen lint --readback -----------------------------------------------------------------------


def test_lint_runs_unclear_speech_only_when_asked(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stt = WordSTT()
    monkeypatch.setattr("vidgen.stt.get_stt_provider", lambda project: stt)
    project = Project.load(project_root)
    fake_render(project, "intro", [[], []])
    fake_render(project, "main", [[]])
    result = lint_project(project, rules=["readback", "dead_air"])
    assert "unclear_speech" not in result.rules and stt.calls == []
    assert "unclear_speech" not in lint_project(project).rules and stt.calls == []

    lines: list[str] = []
    result = lint_project(project, rules=["readback"], readback=True, log=lines.append)
    assert stt.calls == ["intro_b1", "intro_b2", "custom"] and lines[0].startswith("[1/3] transcribed intro_b1")
    found = [(f.rule, f.beat, f.severity, f.scene_time, f.value, f.limit) for f in result.findings if f.rule == "unclear_speech"]
    # activity beats start at 0 s and 1 s in the scene: the flags' times are added
    assert found == [("unclear_speech", "intro_b1", "warning", 2.1, 0.8, 0.5), ("unclear_speech", "intro_b2", "info", 2.4, 0.6, 0.75)]
    message = next(f.message for f in result.findings if f.rule == "unclear_speech")
    assert message.startswith('unclear speech at 2.10 s into the beat: "has", after a 0.80 s pause inside the sentence; fix: listen')

    stt.calls.clear()
    assert lint_project(project, rules=["unclear_speech"]).rules == ["unclear_speech"] and stt.calls == []  # cached
    data = readback_config(preview={"width": 854, "height": 480, "fps": 15}, lint={"rules": {"unclear_speech": {"severity": "off"}}})
    (project_root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert lint_project(Project.load(project_root), rules=["unclear_speech"], readback=True).findings == []


def test_lint_readback_cli(project_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("vidgen.stt.get_stt_provider", lambda project: WordSTT())
    project = Project.load(project_root)
    fake_render(project, "intro", [[], []])
    fake_render(project, "main", [[]])
    code, doc, err = run_json(["lint", str(project_root), "--readback", "--rule", "dead_air", "--json", "--fail-on", "warning"], capsys)
    assert code == 1 and "[1/3] transcribed intro_b1" in err
    assert [f["rule"] for f in doc["findings"]].count("unclear_speech") == 2 and "unclear_speech" in doc["rules"]

    monkeypatch.undo()  # the configured provider, without its package: everything is cached
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert main(["lint", str(project_root), "--readback", "--rule", "dead_air", "--fail-on", "never"]) == 0


def test_mcp_lint_readback_asks_before_a_paid_provider(tmp_path: Path) -> None:
    from test_mcp import attr, error_text, run_session

    root = tmp_path / "root"
    (root / "proj").mkdir(parents=True)
    (root / "proj" / "video.yaml").write_text(yaml.safe_dump(minimal_config(stt={"provider": "elevenlabs"})), encoding="utf-8")

    async def body(client: Any) -> None:
        lint = next(t for t in (await client.list_tools()).tools if t.name == "lint")
        properties = attr(lint, "input_schema", "inputSchema")["properties"]
        assert properties["readback"]["default"] is False and properties["confirm_cost"]["default"] is False
        for arguments in ({"readback": True}, {"rule": ["unclear_speech"]}):
            message = error_text(await client.call_tool("lint", {"project": "proj", **arguments}))
            assert "paid speech-to-text API" in message and "confirm_cost=true" in message
        assert not (root / "proj" / "build").exists()

    run_session(root, body)
