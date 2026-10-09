"""Step 65: local Kokoro-82M narration (``voice.provider: kokoro``, DESIGN.md §68).

Everything runs with a fake ``KPipeline`` (no PyTorch, no model); the one real synthesis test
is skipped unless the ``kokoro`` package is importable (the optional extra)."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from conftest import minimal_config
from vidgen import DIST_NAME, kokoro_voices, tts
from vidgen.cli import main, validate_warnings
from vidgen.config import VoiceConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.speech import beat_word_times, read_alignment
from vidgen.tts import kokoro as kk
from vidgen.tts.run import plan_tts, run_tts

KOKORO = {"provider": "kokoro"}


class Token:
    """What misaki's ``MToken`` gives the pipeline's caller."""

    def __init__(self, text: str, whitespace: str, start: float | None, end: float | None) -> None:
        self.text, self.whitespace, self.start_ts, self.end_ts = text, whitespace, start, end


class Result:
    def __init__(self, audio: Any, tokens: list[Token] | None) -> None:
        self.audio, self.tokens = audio, tokens


def tone(seconds: float) -> np.ndarray:
    n = int(seconds * kk.SAMPLE_RATE)
    return (0.3 * np.sin(2 * math.pi * 220 * np.arange(n) / kk.SAMPLE_RATE)).astype(np.float32)


class FakePipeline:
    """Like ``KPipeline(lang_code=...)``: 0.3 s per word / speed; English yields word tokens with
    timings (punctuation as its own token, as misaki does), other languages none."""

    def __init__(self, lang: str, device: str, model: Any) -> None:
        self.lang, self.device = lang, device
        self.model = model if model is not None else object()
        self.calls: list[dict[str, Any]] = []

    def __call__(self, text: str, voice: str, speed: float, split_pattern: Any) -> Any:
        self.calls.append({"text": text, "voice": voice, "speed": speed, "split_pattern": split_pattern})
        words = text.split()
        step = 0.3 / speed
        tokens: list[Token] = []
        t = 0.1
        for word in words:
            core, tail = word.rstrip(".,!?"), word[len(word.rstrip(".,!?")):]
            tokens.append(Token(core, "" if tail else " ", t, t + step * 0.8))
            if tail:
                tokens.append(Token(tail, " ", t + step * 0.8, t + step))
            t += step
        yield Result(tone(t + 0.1), tokens if self.lang in "ab" else None)


class Factory:
    def __init__(self) -> None:
        self.made: list[FakePipeline] = []

    def __call__(self, lang: str, device: str, model: Any) -> FakePipeline:
        pipeline = FakePipeline(lang, device, model)
        self.made.append(pipeline)
        return pipeline

    def texts(self) -> list[str]:
        return [c["text"] for p in self.made for c in p.calls]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Factory:
    """A fake Kokoro: pipelines from :class:`Factory`, the extra 'installed', an empty HF cache."""
    factory = Factory()
    monkeypatch.setattr(kk, "load_pipeline", factory)
    monkeypatch.setattr(kk, "_ENGINES", {})
    monkeypatch.setattr(kk, "module_available", lambda name: True)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf-cache"))
    for name in ("ELEVENLABS_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return factory


def kokoro_config(voice: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    return minimal_config(voice={**KOKORO, **(voice or {})}, **overrides)


def write(root: Path, data: dict[str, Any]) -> None:
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def problems_of(exc: pytest.ExceptionInfo[VidgenError]) -> list[str]:
    return [str(p) for p in exc.value.problems]


# ----- config, languages, one provider per video --------------------------------------------------


def test_config_keys_and_defaults() -> None:
    voice = VoiceConfig(provider="kokoro")
    assert (voice.voice, voice.lang, voice.speed, voice.device) == (None, None, None, "cpu")
    assert VoiceConfig(provider="kokoro", lang="p", device="auto", speed=1.2).lang == "p"
    for bad in ({"lang": "x"}, {"device": "gpu"}, {"speed": 9}):
        with pytest.raises(ValueError):
            VoiceConfig(provider="kokoro", **bad)
    assert VoiceConfig().provider == "elevenlabs"  # the default is unchanged


@pytest.mark.parametrize(
    ("voice", "language", "expected"),
    [
        ({}, None, ("af_heart", "a")),
        ({}, "en-US", ("af_heart", "a")),
        ({}, "en-GB", ("bf_emma", "b")),
        ({}, "pt-BR", ("pf_dora", "p")),
        ({}, "pt-PT", ("pf_dora", "p")),
        ({}, "es", ("ef_dora", "e")),
        ({}, "ja", ("jf_alpha", "j")),
        ({"voice": "bm_george"}, None, ("bm_george", "b")),
        ({"voice": "ff_siwis"}, "de", ("ff_siwis", "f")),
        ({"lang": "i"}, None, ("if_sara", "i")),
        ({"voice": "af_bella,af_heart"}, None, ("af_bella,af_heart", "a")),
    ],
)
def test_voice_and_lang_resolution(make_project, voice: dict[str, Any], language: str | None, expected: tuple[str, str]) -> None:
    extra = {"language": language} if language else {}
    resolved = Project.load(make_project(kokoro_config(voice, **extra))).voice()
    assert (resolved.voice, resolved.lang, resolved.speed, resolved.language_code) == (*expected, 1.0, None)


def test_language_kokoro_does_not_speak_is_a_config_error(make_project) -> None:
    root = make_project(kokoro_config(language="de", voices={"ana": {"speed": 1.1}}))
    with pytest.raises(VidgenError) as info:
        Project.load(root)
    found = problems_of(info)
    assert found[0].startswith("voice.lang: Kokoro has no voice for the video's language de: set lang (Kokoro speaks a American English")
    assert found[1].startswith("voices.ana.lang:")


def test_named_voice_takes_its_own_voices_language(make_project) -> None:
    data = kokoro_config({"voice": "af_heart", "lang": "a"}, voices={"brit": {"voice": "bm_george"}, "slow": {"speed": 0.8}})
    data["scenes"][1]["voice"] = "brit"
    project = Project.load(make_project(data))
    assert (project.voice("brit").voice, project.voice("brit").lang) == ("bm_george", "b")
    assert (project.voice("slow").voice, project.voice("slow").lang, project.voice("slow").speed) == ("af_heart", "a", 0.8)


def test_one_provider_per_video(make_project) -> None:
    data = kokoro_config(voices={"ana": {"provider": "openrouter", "model": "a/b"}, "ben": {"voice_id": "x", "instructions": "calm"}})
    with pytest.raises(VidgenError) as info:
        Project.load(make_project(data))
    found = problems_of(info)
    assert found[0].startswith("voices.ana.provider: one TTS provider per video: the base voice uses kokoro")
    assert "a named voice changes voice, speed, lang only" in found[0]
    assert any(p.startswith("voices.ben.voice_id: voice_id is an ElevenLabs setting") for p in found)
    assert any(p.startswith("voices.ben.instructions: instructions is an OpenRouter setting") for p in found)
    # Kokoro keys in an ElevenLabs video
    with pytest.raises(VidgenError) as info:
        Project.load(make_project(minimal_config(voices={"ana": {"lang": "b"}, "ben": {"voice": "af_bella"}}), folder="el"))
    found = problems_of(info)
    assert found[0].startswith("voices.ana.lang: lang is a Kokoro setting, but this video's voices use elevenlabs")
    assert found[1].startswith("voices.ben.voice: voice is an OpenRouter or Kokoro setting")


def test_variant_may_switch_to_kokoro_and_device_shares_audio(make_project) -> None:
    root = make_project(minimal_config(variants={"local": {"voice": KOKORO}, "gpu": {"voice": {"device": "cuda"}}}))
    local = Project.load(root, variant="local")
    assert local.voice().provider == "kokoro" and local.audio_dir == root / "audio" / "local"
    assert isinstance(tts.get_provider(local.voice()), kk.KokoroProvider)
    root2 = make_project(kokoro_config(variants={"gpu": {"voice": {"device": "cuda"}}}), folder="p2")
    assert not Project.load(root2, variant="gpu").has_own_audio  # where it runs is not what it sounds like


# ----- hashes -------------------------------------------------------------------------------------


def test_other_providers_hashes_are_unchanged() -> None:
    """Pinned: adding Kokoro must not change an ElevenLabs or OpenRouter cache key."""
    assert tts.get_provider(VoiceConfig()).cache_key("Hello there.") == "e07179cc8214a9008a163a96e3ab594f0d3da455"
    routed = VoiceConfig(provider="openrouter", model="mistralai/voxtral-mini-tts-2603", voice="en_paul_neutral")
    assert tts.get_provider(routed).cache_key("Hello there.") == "ed12a9d42adbd729f424fb9c6b73f406f5b27aaa"
    assert {s.state for s in tts.audio_status(Project.load(Path(__file__).parent.parent / "examples" / "kphi3"))} == {"ok"}


def test_cache_key_covers_model_voice_lang_speed_not_device() -> None:
    def key(text: str = "Hi", **voice: Any) -> str:
        return kk.KokoroProvider(VoiceConfig(**{**KOKORO, **voice})).cache_key(text)

    spec = {"lang": "a", "model": "hexgrad/Kokoro-82M", "provider": "kokoro", "speed": 1.0, "voice": "af_heart", "weights": "kokoro-v1_0.pth"}
    assert key() == hashlib.sha1(f"{json.dumps(spec, sort_keys=True)}|Hi".encode()).hexdigest()
    assert key("Hello there.") == "05cb88daec48cc27a4841b20f737de3c7cb847c4"  # pinned (Step 65)
    keys = {key(), key("Hi!"), key(voice="af_bella"), key(lang="b"), key(speed=1.1)}
    assert len(keys) == 5
    assert key(device="cuda") == key() == key(voice="af_heart", lang="a", speed=1.0)
    provider = kk.KokoroProvider(VoiceConfig(**KOKORO))
    assert provider.matches("Hi", key() + "\n") and not provider.matches("Hi", "")


# ----- nothing heavy without the extra ------------------------------------------------------------


def test_validate_and_render_paths_never_import_kokoro(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    before = {name for name in ("kokoro", "torch", "misaki") if name in sys.modules}
    root = make_project(kokoro_config())
    assert main(["validate", str(root)]) == 0
    assert main(["tts", str(root), "--dry-run"]) == 0
    capsys.readouterr()
    assert {name for name in ("kokoro", "torch", "misaki") if name in sys.modules} == before


def test_missing_extra_is_a_clear_error(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(kk, "module_available", lambda name: False)
    root = make_project(kokoro_config())
    assert main(["tts", str(root)]) == 1
    err = capsys.readouterr().err
    assert f'pip install "{DIST_NAME}[kokoro]"' in err and "Traceback" not in err
    assert not (root / "audio").exists() or not list((root / "audio").glob("*.mp3"))
    assert any(w.startswith(f'voice.provider: voice.provider kokoro needs the optional extra: pip install "{DIST_NAME}[kokoro]"')
               for w in validate_warnings(Project.load(root)))
    monkeypatch.setattr(kk, "NEWEST_PYTHON", (3, 9))
    assert "supports Python 3.10-3.12" in kk.install_message() and "--ignore-requires-python" in kk.install_message()


def test_language_packages_and_espeak_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kk, "module_available", lambda name: name == "kokoro")
    with pytest.raises(VidgenError, match=r'needs more packages: pip install "misaki\[ja\]"'):
        kk.check_installed("j")
    with pytest.raises(VidgenError, match="espeak-ng could not be loaded .* lang p \\(Brazilian Portuguese\\)"):
        kk.check_installed("p")
    kk.check_installed("a")  # English needs neither
    message = kk.explain(RuntimeError("espeak not installed on your system"), "e", "cpu")
    assert "sudo apt install espeak-ng" in message and "espeak-ng .msi" in message and "espeakng-loader" in message
    assert "misaki[zh]" in kk.explain(ModuleNotFoundError("No module named 'jieba'", name="jieba"), "z", "cpu")
    assert "set voice.device: cpu" in kk.explain(RuntimeError("CUDA requested but not available"), "a", "cuda")
    xet = kk.explain(RuntimeError("Task error: CAS Client Error: Request middleware error: error sending request"), "a", "cpu")
    assert xet.startswith("cannot download Kokoro-82M from Hugging Face") and "HF_HUB_DISABLE_XET=1" in xet
    assert "first run needs the internet" in kk.explain(OSError("httpx.ProxyError: 403 Forbidden"), "a", "cpu")
    assert kk.explain(ValueError("odd"), "a", "cpu") == "Kokoro could not voice the text: ValueError: odd"


# ----- alignment from Kokoro's word timings -------------------------------------------------------


def test_alignment_from_tokens() -> None:
    text = "Hello, big world."
    timed = [("Hello", 0.1, 0.5), (",", 0.5, 0.6), ("big", 0.7, 0.9), ("world", 1.0, 1.4), (".", 1.4, 1.5)]
    doc = kk.alignment_from_tokens(text, timed)
    assert doc is not None and "".join(doc["characters"]) == text
    starts, ends = doc["character_start_times_seconds"], doc["character_end_times_seconds"]
    assert (starts[0], ends[4]) == (0.1, 0.5) and (starts[7], ends[9]) == (0.7, 0.9)
    assert starts[6] == ends[6] == 0.6  # the space takes the previous end
    assert all(e >= s for s, e in zip(starts, ends)) and ends[-1] == 1.5
    assert kk.alignment_from_tokens(text, [("Hello", 0.1, 0.5)]) is None  # too little of the text
    assert kk.alignment_from_tokens("", []) is None


def test_chunks_are_timed_one_after_another(fake: Factory) -> None:
    class TwoChunks(FakePipeline):
        def __call__(self, text: str, voice: str, speed: float, split_pattern: Any) -> Any:
            yield Result(tone(1.0), [Token("One", " ", 0.1, 0.5), Token("two", "", 0.5, 0.9)])
            yield Result(tone(1.0), [Token("three", "", 0.1, 0.6)])

    engine = kk.KokoroEngine("cpu", lambda lang, device, model: TwoChunks(lang, device, model))
    audio, alignment = kk.KokoroProvider(VoiceConfig(**KOKORO), engine=engine).synthesize_timed("One two three")
    assert audio[:3] == b"ID3" or audio[0] == 0xFF
    assert alignment is not None
    assert alignment["character_start_times_seconds"][8] == pytest.approx(1.1)  # "three" in the second second


# ----- vidgen tts with the fake pipeline ----------------------------------------------------------


def run(root: Path, *args: str) -> int:
    return main(["tts", str(root), *args])


def test_tts_writes_mp3_hash_and_timings_loading_once(make_project, fake: Factory, capsys: pytest.CaptureFixture[str]) -> None:
    data = kokoro_config({"voice": "af_bella", "speed": 1.25}, voices={"guest": {"voice": "am_michael"}})
    data["scenes"][1]["voice"] = "guest"
    root = make_project(data)
    assert run(root) == 0
    out = capsys.readouterr().out
    assert "note: Kokoro-82M runs on this computer (cpu): free, no API key" in out
    assert "note: the first run downloads Kokoro-82M from Hugging Face (kokoro-v1_0.pth, 327 MB" in out
    assert "[1/3] generated intro_b1.mp3 (12 chars, with timings)" in out
    assert "done: 3 beat(s) generated (43 characters), 0 up to date, audio in audio/" in out
    assert len(fake.made) == 1  # one model and one English pipeline for both voices
    calls = fake.made[0].calls
    assert [(c["voice"], c["speed"], c["split_pattern"]) for c in calls] == [("af_bella", 1.25, None), ("af_bella", 1.25, None), ("am_michael", 1.25, None)]
    audio = root / "audio"
    project = Project.load(root)
    providers = tts.beat_providers(project)
    assert (audio / "custom.hash").read_text(encoding="utf-8") == providers["custom"].cache_key("One two three four.")
    assert read_alignment(audio, "custom", "One two three four.") is not None
    assert {s.state for s in tts.audio_status(project)} == {"ok"}
    assert run(root) == 0
    assert "nothing to do: 3 beat(s) up to date" in capsys.readouterr().out
    # speed is in the hash: every beat of that voice is voiced again
    data["voice"]["speed"] = 1.0
    write(root, data)
    assert [b.id for b in plan_tts(Project.load(root)).todo] == ["intro_b1", "intro_b2", "custom"]


def test_two_languages_share_one_model(make_project, fake: Factory) -> None:
    data = kokoro_config(voices={"ana": {"voice": "pf_dora"}})
    data["scenes"][1]["voice"] = "ana"
    root = make_project(data)
    run_tts(Project.load(root), out=lambda s: None)
    assert [p.lang for p in fake.made] == ["a", "p"]
    assert fake.made[1].model is fake.made[0].model  # the second pipeline got the first one's model
    assert read_alignment(root / "audio", "custom", "One two three four.") is None  # no timings in Portuguese


def test_pronunciation_and_captions_use_kokoro_timings(make_project, fake: Factory) -> None:
    root = make_project(kokoro_config(pronunciation={"Hello": "Hullo there"}))
    project = Project.load(root)
    run_tts(project, out=lambda s: None)
    assert fake.texts()[0] == "Hullo there there."  # pronunciation applied before synthesis
    spoken = project.pronunciation.apply("Hello there.")
    times = beat_word_times(project.audio_dir, "intro_b1", "Hello there.", 2.0, 4.0, spoken=spoken)
    # the fake says each word at 0.1 + 0.3 k s: "Hello" = "Hullo there" (two spoken words)
    assert [t.text for t in times] == ["Hello", "there."]
    assert times[0].start == pytest.approx(2.1) and times[0].end == pytest.approx(2.1 + 0.3 + 0.24)
    assert times[1].start == pytest.approx(2.7)


def test_failures_are_vidgen_errors(make_project, fake: Factory, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def broken(lang: str, device: str, model: Any) -> Any:
        raise RuntimeError("Task error: CAS Client Error: error sending request for url (https://cas-server.xethub.hf.co/...)")

    monkeypatch.setattr(kk, "load_pipeline", broken)
    root = make_project(kokoro_config())
    assert run(root) == 1
    err = capsys.readouterr().err
    assert "beat 'intro_b1': cannot download Kokoro-82M from Hugging Face" in err and "0 of 3 done before the error" in err


def test_stdout_stays_clean_for_json(make_project, fake: Factory, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    import os

    class Noisy(FakePipeline):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            print("Collecting en-core-web-sm==3.8.0")  # what spaCy's model install prints
            os.write(1, b"Successfully installed en-core-web-sm\n")  # a child process writing to fd 1

    monkeypatch.setattr(kk, "load_pipeline", lambda lang, device, model: Noisy(lang, device, model))
    root = make_project(kokoro_config())
    assert run(root, "--json") == 0
    out, err = capfd.readouterr()
    doc = json.loads(out)
    assert doc["ok"] and doc["generated"] == ["intro_b1", "intro_b2", "custom"]
    assert "Collecting en-core-web-sm" in err and "Successfully installed" in err


# ----- dry run, JSON, validate, MCP ---------------------------------------------------------------


def test_dry_run_says_free_local_and_the_download(make_project, fake: Factory, tmp_path: Path, capsys) -> None:
    root = make_project(kokoro_config({"voice": "bf_emma"}))
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "  voice default (kokoro bf_emma (lang b, British English), speed 1, cpu): 3 beat(s), 43 characters" in out
    assert "  note: the first run downloads Kokoro-82M from Hugging Face" in out
    assert "  cost: free (local): Kokoro-82M runs on this computer" in out
    assert not fake.made  # a dry run loads nothing
    assert main(["tts", str(root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert (doc["provider"], doc["estimated_cost"], doc["unknown_cost"], doc["charged"]) == ("kokoro", 0, 0, None)
    assert doc["price_note"] == "free (local): Kokoro-82M runs on this computer"
    beat = doc["beats"][0]
    assert (beat["provider"], beat["model"], beat["provider_voice"], beat["speed"], beat["lang"], beat["device"]) == (
        "kokoro", "hexgrad/Kokoro-82M", "bf_emma", 1.0, "b", "cpu")
    assert beat["estimated_cost"] == 0 and doc["voices"]["default"]["voice_id"] is None
    assert any("first run downloads" in n for n in doc["notes"])
    # once the weights are in the Hugging Face cache, no download note
    weights = tmp_path / "hf-cache" / "models--hexgrad--Kokoro-82M" / "snapshots" / "abc" / "kokoro-v1_0.pth"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"x")
    assert kk.model_downloaded()
    assert main(["tts", str(root), "--dry-run", "--json"]) == 0
    assert not any("first run downloads" in n for n in json.loads(capsys.readouterr().out)["notes"])


def test_hf_cache_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("HF_HUB_CACHE", "HF_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(name, raising=False)
    assert kk.hf_cache_dir() == Path.home() / ".cache" / "huggingface" / "hub"
    monkeypatch.setenv("HF_HOME", str(tmp_path / "home"))
    assert kk.hf_cache_dir() == tmp_path / "home" / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "cache"))
    assert kk.hf_cache_dir() == tmp_path / "cache"


def test_validate_warnings(make_project, fake: Factory) -> None:
    data = kokoro_config({"voice": "af_hart", "lang": "a"}, language="pt-BR",
                         voices={"brit": {"voice": "bf_emma", "lang": "a"}, "jp": {"voice": "jf_alpha", "timestamps": True}})
    data["scenes"][1]["voice"] = "brit"
    data["scenes"][0]["beats"][1]["voice"] = "jp"
    warnings = validate_warnings(Project.load(make_project(data)))
    assert any(w.startswith("voice.voice: 'af_hart' is not among Kokoro-82M's voices of 2026-10-09 (did you mean af_heart?") for w in warnings)
    assert any(w.startswith("voices.brit.voice: 'bf_emma' is a British English voice but lang is a (American English)") for w in warnings)
    assert any(w.startswith("voice.lang: a (American English) but the video's language is pt-BR (Kokoro lang p") for w in warnings)
    assert any(w.startswith("voices.jp.timestamps: Kokoro gives word timings for English only") for w in warnings)
    clean = make_project(kokoro_config({"voice": "pf_dora"}, language="pt-BR"), folder="clean")
    assert not [w for w in validate_warnings(Project.load(clean)) if w.startswith(("voice", "voices"))]


def test_bundled_voice_list() -> None:
    catalog = kokoro_voices.catalog()
    assert catalog["date"] == "2026-10-09" and len(catalog["voices"]) == 54 and catalog["weights_bytes"] == 327212226
    for lang, entry in kokoro_voices.langs().items():
        assert entry["default_voice"] in catalog["voices"] and entry["default_voice"].startswith(lang)
    assert kokoro_voices.voices_of("a")[:2] == ["af_heart", "af_bella"]
    assert kokoro_voices.lang_of_voice("zed") is None and kokoro_voices.lang_of_voice("my_voice.pt") is None


def test_readback_and_narration_speed_work_with_its_audio(make_project, fake: Factory) -> None:
    from test_readback import FakeSTT
    from test_timing_lint import activity, beat
    from vidgen.config import LintRules
    from vidgen.lint import RULES, SceneContext
    from vidgen.readback import run_readback

    root = make_project(kokoro_config())
    project = Project.load(root)
    run_tts(project, out=lambda s: None)
    heard = {"intro_b1": "Hello there.", "intro_b2": "Second beat.", "custom": "One two tree four."}
    result = run_readback(Project.load(root), provider=FakeSTT(heard), log=lambda s: None)
    assert result.transcribed == 3 and [b.flagged for b in result.beats] == [False, False, True]
    text = "one two three four five six seven eight nine ten"
    doc = activity([beat("custom", 0, 3.0, text=text, source="audio")])
    [issue] = RULES["narration_speed"].check(SceneContext("main", doc, project.audio_dir), LintRules().narration_speed)
    assert issue.beat == "custom" and "s of speech) is above" in issue.message


def test_mcp_tts_runs_kokoro_without_confirm_cost(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_mcp import doc_of, error_text, run_session
    from vidgen.mcp_server import tts_provider

    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf"))
    root = tmp_path / "root"
    for name, voice in (("local", KOKORO), ("paid", {})):
        (root / name).mkdir(parents=True)
        (root / name / "video.yaml").write_text(json.dumps(minimal_config(voice=voice)), encoding="utf-8")
    assert tts_provider(root / "local", None) == "kokoro" and tts_provider(root / "paid", None) == "elevenlabs"
    assert tts_provider(root / "missing", None) is None

    async def body(client: Any) -> None:
        dry = doc_of(await client.call_tool("tts", {"project": "local"}))
        assert dry["provider"] == "kokoro" and dry["estimated_cost"] == 0 and dry["price_note"].startswith("free (local)")
        real = error_text(await client.call_tool("tts", {"project": "local", "dry_run": False}))
        assert "confirm_cost" not in real  # the run itself was attempted (no extra in the test venv: it says so)
        if not kk.module_available("kokoro"):
            assert f"{DIST_NAME}[kokoro]" in real
        paid = error_text(await client.call_tool("tts", {"project": "paid", "dry_run": False}))
        assert "confirm_cost=true" in paid

    if kk.module_available("kokoro"):
        pytest.skip("the real-run branch is checked where the extra is not installed")
    run_session(root, body)


# ----- the real model (only with the extra installed) ---------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not kk.module_available("kokoro"), reason='needs the kokoro extra: pip install ".[kokoro]"')
def test_real_kokoro_synthesis(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    """One English sentence through the real model (downloads it on first use) and back."""
    from vidgen.speech import speech_bounds

    scenes = [{"id": "s", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Kokoro speaks this short sentence for vidgen."}]}]
    root = make_project(minimal_config(voice={"provider": "kokoro", "voice": "af_heart"}, scenes=scenes))
    assert main(["tts", str(root)]) == 0
    assert "[1/1] generated s_b1.mp3 (" in capsys.readouterr().out
    mp3 = root / "audio" / "s_b1.mp3"
    start, end = speech_bounds(mp3)
    assert 1.5 < end - start < 6.0
    alignment = read_alignment(root / "audio", "s_b1", "Kokoro speaks this short sentence for vidgen.")
    assert alignment is not None and alignment["ends"][-1] > 1.0
