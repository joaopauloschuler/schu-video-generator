"""OpenRouter text-to-speech provider (Step 62, DESIGN.md §66). Every request is mocked:
``urllib.request.urlopen`` is replaced by :class:`FakeOpenRouter`, which answers the speech
endpoint with a tiny MP3 (or raw PCM) made by ffmpeg and the public lookups with fixtures
saved from OpenRouter on 2026-10-08 (``tests/data/openrouter_tts.json``)."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import minimal_config
from vidgen import tts
from vidgen.cli import main, validate_warnings
from vidgen.config import VoiceConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.tts import openrouter as ortts
from vidgen.tts.run import plan_tts, run_tts

KEY = "sk-or-v1-TEST_secret_key_0123456789"
FIXTURES = json.loads((Path(__file__).parent / "data" / "openrouter_tts.json").read_text(encoding="utf-8"))
MODEL = "mistralai/voxtral-mini-tts-2603"
VOICE = {"provider": "openrouter", "model": MODEL, "voice": "en_paul_neutral"}


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    assert exe, "ffmpeg is needed by vidgen"
    return exe


def make_audio(fmt: str, seconds: float = 0.4) -> bytes:
    """A short 440 Hz tone as MP3 (``mp3``) or raw 16-bit 24 kHz mono PCM (``pcm``)."""
    args = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    out = ["-f", "mp3", "-codec:a", "libmp3lame"] if fmt == "mp3" else ["-f", "s16le", "-ar", "24000", "-ac", "1"]
    done = subprocess.run([ffmpeg(), "-v", "error", *args, *out, "-"], check=True, capture_output=True)
    return done.stdout


MP3 = make_audio("mp3")
PCM = make_audio("pcm")


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.body = body
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://openrouter.ai/x", code, "err", Message(), io.BytesIO(body.encode()))


class FakeOpenRouter:
    """Replaces ``urlopen``: ``speech`` answers (bytes or an exception, consumed in order; then
    the MP3) for ``POST /audio/speech``, the fixtures for the public lookups, ``costs`` for
    ``GET /generation``; ``offline`` makes every lookup fail."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self.speech: list[Any] = []
        self.offline = False
        self.costs: dict[str, Any] = {}
        self.count = 0

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        url = request.full_url
        if url.endswith("/audio/speech"):
            item = self.speech.pop(0) if self.speech else MP3
            if isinstance(item, BaseException):
                raise item
            self.count += 1
            kind = "audio/pcm" if item is PCM else "audio/mpeg"
            return FakeResponse(item, {"Content-Type": kind, "X-Generation-Id": f"gen-tts-{self.count}"})
        if self.offline:
            raise urllib.error.URLError(OSError("Name or service not known"))
        if "/generation?" in url:
            gen = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["id"][0]
            cost = self.costs.get(gen, 0.0002)
            if isinstance(cost, BaseException):
                raise cost
            return FakeResponse(json.dumps({"data": {"id": gen, "api_type": "tts", "total_cost": cost}}).encode())
        if "output_modalities=speech" in url:
            return FakeResponse(json.dumps(FIXTURES["speech_models"]).encode())
        if url.endswith("/endpoints/zdr"):
            return FakeResponse(json.dumps(FIXTURES["zdr"]).encode())
        if url.endswith("/endpoints"):
            model = urllib.parse.unquote(url.split("/models/", 1)[1].rsplit("/endpoints", 1)[0])
            if model in FIXTURES["endpoints"]:
                return FakeResponse(json.dumps(FIXTURES["endpoints"][model]).encode())
            raise http_error(404, '{"error":{"message":"Model not found","code":404}}')
        raise AssertionError(f"unexpected request {url}")

    def posts(self) -> list[urllib.request.Request]:
        return [r for r in self.requests if r.get_method() == "POST"]

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.data) for r in self.posts()]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeOpenRouter:
    fake = FakeOpenRouter()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    return fake


def or_config(voice: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    return minimal_config(voice=dict(VOICE if voice is None else voice), **overrides)


def all_files_text(root: Path) -> str:
    return "".join(p.read_bytes().decode("utf-8", errors="replace") for p in root.rglob("*") if p.is_file())


def write(root: Path, data: dict[str, Any]) -> None:
    (root / "video.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def problems_of(exc: pytest.ExceptionInfo[VidgenError]) -> list[str]:
    return [str(p) for p in exc.value.problems]


# ----- config ------------------------------------------------------------------------------------


def test_config_defaults_and_required_model() -> None:
    assert VoiceConfig().provider == "elevenlabs" and VoiceConfig().model is None
    voice = VoiceConfig(**VOICE, instructions="calm", speed=1.1)
    assert (voice.model, voice.voice, voice.instructions, voice.speed) == (MODEL, "en_paul_neutral", "calm", 1.1)
    with pytest.raises(ValueError, match="provider openrouter needs a model"):
        VoiceConfig(provider="openrouter")
    with pytest.raises(ValueError, match="author/name"):
        VoiceConfig(provider="openrouter", model="voxtral")
    with pytest.raises(ValueError):
        VoiceConfig(**VOICE, speed=9)


def test_elevenlabs_hashes_are_unchanged() -> None:
    """Pinned before Step 62: adding OpenRouter keys must not change an ElevenLabs cache key."""
    assert tts.get_provider(VoiceConfig()).cache_key("Hello there.") == "e07179cc8214a9008a163a96e3ab594f0d3da455"
    pt = VoiceConfig(voice_id="abc", settings={"stability": 0.3}, language_code="pt")
    assert tts.get_provider(pt).cache_key("Olá.") == "cce00e8bfcafdb30029d3c9c8a839066445f77b6"


def test_kphi3_example_audio_stays_ok() -> None:
    project = Project.load(Path(__file__).parent.parent / "examples" / "kphi3")
    assert {s.state for s in tts.audio_status(project)} == {"ok"}


def test_named_voice_cannot_switch_provider(make_project) -> None:
    data = or_config(voices={"ana": {"provider": "elevenlabs", "voice_id": "x"}, "ben": {"voice_id": "y", "settings": {"style": 0.2}}})
    data["scenes"][1]["voice"] = "ana"
    root = make_project(data)
    with pytest.raises(VidgenError) as info:
        Project.load(root)
    found = problems_of(info)
    assert any(p.startswith("voices.ana.provider: one TTS provider per video: the base voice uses openrouter") for p in found)
    assert any(p.startswith("voices.ben.voice_id: voice_id is an ElevenLabs setting") for p in found)
    assert any(p.startswith("voices.ben.settings:") for p in found)
    assert "a variant may switch the provider" in str(info.value)


def test_named_voice_of_elevenlabs_video_cannot_use_openrouter_keys(make_project) -> None:
    root = make_project(minimal_config(voices={"ana": {"provider": "openrouter", "model": MODEL}, "ben": {"instructions": "calm"}}))
    with pytest.raises(VidgenError) as info:
        Project.load(root)
    found = problems_of(info)
    assert found[0].startswith("voices.ana.provider: one TTS provider per video: the base voice uses elevenlabs")
    assert found[1].startswith("voices.ben.instructions: instructions is an OpenRouter setting")


def test_variant_may_switch_provider_with_its_own_audio(make_project) -> None:
    data = minimal_config(voice={"voice_id": "abc", "settings": {"stability": 0.4}}, variants={"or": {"voice": VOICE}})
    root = make_project(data)
    base, variant = Project.load(root), Project.load(root, variant="or")
    assert base.voice().provider == "elevenlabs" and variant.voice().provider == "openrouter"
    assert variant.has_own_audio and variant.audio_dir == root / "audio" / "or"
    assert isinstance(tts.get_provider(variant.voice()), ortts.OpenRouterTTSProvider)
    # and the other way round: an OpenRouter video with an ElevenLabs variant
    root2 = make_project(or_config(variants={"el": {"voice": {"provider": "elevenlabs"}}}), folder="p2")
    assert Project.load(root2, variant="el").voice().provider == "elevenlabs"


def test_language_code_is_never_sent(make_project) -> None:
    root = make_project(or_config(language="pt-BR"))
    voice = Project.load(root).voice()
    assert voice.language_code is None
    assert "language_code" not in ortts.OpenRouterTTSProvider(voice).request_body("Olá")


# ----- the provider ------------------------------------------------------------------------------


def provider(**voice: Any) -> ortts.OpenRouterTTSProvider:
    return ortts.OpenRouterTTSProvider(VoiceConfig(**{**VOICE, **voice}), sleep=lambda s: None, zdr=lambda: ["mistralai/voxtral-mini-tts-2603"])


def test_request_body_headers_and_mp3(api: FakeOpenRouter) -> None:
    p = provider(instructions="warm, unhurried explainer", speed=1.1)
    assert p.synthesize("Hello.", "Before.", "After.") == MP3
    (req,) = api.posts()
    assert req.full_url == "https://openrouter.ai/api/v1/audio/speech"
    assert req.get_header("Authorization") == f"Bearer {KEY}"
    assert req.get_header("Http-referer") == "https://github.com/joaopauloschuler/schu-video-generator"
    assert req.get_header("X-openrouter-title") == "schu-video-generator"
    assert api.bodies() == [{
        "model": MODEL, "input": "Hello.", "response_format": "mp3", "voice": "en_paul_neutral",
        "instructions": "warm, unhurried explainer", "speed": 1.1,
    }]  # no neighbouring beats, no language_code
    assert p.generations == ["gen-tts-1"]
    assert KEY not in repr(vars(p))
    minimal = ortts.OpenRouterTTSProvider(VoiceConfig(provider="openrouter", model=MODEL)).request_body("x")
    assert minimal == {"model": MODEL, "input": "x", "response_format": "mp3"}


def test_cache_key_covers_model_voice_instructions_speed() -> None:
    base = provider()
    spec = json.dumps({"instructions": None, "model": MODEL, "provider": "openrouter", "speed": None, "voice": "en_paul_neutral"}, sort_keys=True)
    assert base.cache_key("Hi") == hashlib.sha1(f"{spec}|Hi".encode()).hexdigest()
    keys = {base.cache_key("Hi"), base.cache_key("Hi!"), provider(voice="gb_oliver_neutral").cache_key("Hi"),
            provider(model="hexgrad/kokoro-82m").cache_key("Hi"), provider(instructions="calm").cache_key("Hi"),
            provider(speed=1.2).cache_key("Hi")}
    assert len(keys) == 6
    assert base.matches("Hi", base.cache_key("Hi") + "\n") and not base.matches("Hi", "")
    assert base.cache_key("Hi") != tts.get_provider(VoiceConfig()).cache_key("Hi")


def test_pcm_only_model_is_converted_to_mp3(api: FakeOpenRouter, tmp_path: Path) -> None:
    api.speech = [PCM]
    p = provider(model="google/gemini-3.8-flash-lite-tts", voice="Kore")
    audio = p.synthesize("Hello.")
    assert api.bodies()[0]["response_format"] == "pcm"
    assert ortts.audio_kind(audio, None, "mp3") == "mp3"
    out = tmp_path / "a.mp3"
    out.write_bytes(audio)
    probe = subprocess.run([ffmpeg(), "-v", "error", "-i", str(out), "-f", "null", "-"], capture_output=True)
    assert probe.returncode == 0


def test_mp3_refused_then_pcm(api: FakeOpenRouter) -> None:
    api.speech = [http_error(400, '{"error":{"code":400,"message":"Gemini TTS only supports response_format=\\"pcm\\""}}'), PCM]
    p = provider(model="other/pcm-model")
    assert ortts.audio_kind(p.synthesize("Hi"), None, "mp3") == "mp3"
    assert [b["response_format"] for b in api.bodies()] == ["mp3", "pcm"]
    p.synthesize("Again")
    assert api.bodies()[-1]["response_format"] == "pcm"  # remembered


def test_audio_kinds() -> None:
    assert ortts.audio_kind(MP3, "audio/mpeg", "mp3") == "mp3"
    assert ortts.audio_kind(b"RIFF\x00\x00\x00\x00WAVEfmt ", None, "mp3") == "wav"
    assert ortts.audio_kind(PCM, "audio/pcm", "pcm") == "pcm"
    assert ortts.audio_kind(b'{"error": 1}', "application/json", "pcm") == "unknown"
    assert ortts.pcm_rate("audio/pcm;rate=16000") == 16000 and ortts.pcm_rate(None) == 24000
    with pytest.raises(VidgenError, match="no audio vidgen can read"):
        ortts.as_mp3(b"<html>oops</html>", "text/html", "mp3")


def test_retries_and_errors_without_key(api: FakeOpenRouter) -> None:
    api.speech = [http_error(429, "slow down"), http_error(529, "overloaded"), MP3]
    assert provider().synthesize("x") == MP3
    assert len(api.posts()) == 3
    api.speech = [http_error(402, f'{{"error":{{"message":"Insufficient credits {KEY}"}}}}')]
    with pytest.raises(VidgenError) as info:
        provider().synthesize("x")
    assert "HTTP 402" in str(info.value) and KEY not in str(info.value)


def test_data_policy_error_names_zdr_tts_models(api: FakeOpenRouter) -> None:
    body = ('{"error":{"message":"No endpoints found matching your data policy (Paid model training). '
            'Configure: https://openrouter.ai/settings/privacy","code":404}}')
    api.speech = [http_error(404, body)]
    p = ortts.OpenRouterTTSProvider(VoiceConfig(**{**VOICE, "model": "minimax/speech-2.8-turbo"}), sleep=lambda s: None)
    with pytest.raises(VidgenError) as info:
        p.synthesize("x")
    msg = str(info.value)
    assert "privacy settings" in msg and "https://openrouter.ai/settings/privacy" in msg
    # live lookups (mocked): the ZDR list ∩ the speech models of the fixture
    assert "Text-to-speech models with a ZDR endpoint now: " in msg
    assert "mistralai/voxtral-mini-tts-2603" in msg and "minimax/speech-2.8-turbo" not in msg.split("now: ")[1]
    api.speech, api.offline = [http_error(404, body)], True
    with pytest.raises(VidgenError, match="could not be reached to suggest models"):
        p.synthesize("x")


def test_missing_key_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(VidgenError, match="OPENROUTER_API_KEY is not set") as info:
        provider().check_credentials()
    assert "`vidgen tts --dry-run` works without it" in str(info.value)


def test_reported_cost(api: FakeOpenRouter) -> None:
    p = provider()
    p.synthesize("a")
    p.synthesize("b")
    api.costs = {"gen-tts-2": http_error(404, "not yet")}
    assert p.reported_cost() == (0.0002, 1)  # the second one is asked twice, then given up
    gets = [r for r in api.requests if "/generation?" in r.full_url]
    assert len(gets) == 3 and gets[0].get_header("Authorization") == f"Bearer {KEY}"


# ----- prices and lookups ------------------------------------------------------------------------


def test_lookup_and_character_rate(api: FakeOpenRouter) -> None:
    found = ortts.lookup_speech_models([MODEL, "hexgrad/kokoro-82m", "google/gemini-3.8-flash-lite-tts", "nobody/none"])
    vox, kokoro, gemini, missing = (found[k] for k in found)
    assert isinstance(vox, ortts.SpeechModel) and "en_paul_neutral" in (vox.voices or ())
    rate = ortts.character_rate(vox)
    assert rate.cost == pytest.approx(0.0000176) and rate.basis == "OpenRouter: $0.0000176 per character; the highest of 3 providers"
    assert ortts.character_rate(kokoro).cost == pytest.approx(0.000004)  # Together's price, not the list price
    gem = ortts.character_rate(gemini)  # no endpoint fixture: the list price, which bills audio tokens too
    assert gem.cost is None and "also bills the generated audio" in gem.basis
    assert isinstance(missing, ortts.LookupFailure) and missing.missing and "no text-to-speech model 'nobody/none'" in missing.reason
    api.offline = True
    offline = ortts.lookup_speech_models([MODEL])[MODEL]
    assert isinstance(offline, ortts.LookupFailure) and not offline.missing
    assert ortts.character_rate(offline).basis.startswith("price unknown: OpenRouter's model list could not be reached")


def test_voice_notes() -> None:
    model = ortts.SpeechModel(MODEL, ("en_paul_neutral", "gb_oliver_neutral"), ())
    assert ortts.voice_notes(VoiceConfig(**VOICE), model) == []
    [note] = ortts.voice_notes(VoiceConfig(**{**VOICE, "voice": "zed"}), model)
    assert "is not among the voices" in note
    [note] = ortts.voice_notes(VoiceConfig(provider="openrouter", model=MODEL), model)
    assert "voice: is not set" in note
    assert ortts.voice_notes(VoiceConfig(**VOICE), ortts.SpeechModel(MODEL, None, ())) == []
    ignored = ortts.voice_notes(VoiceConfig(**VOICE, instructions="calm", speed=1.2), model)
    assert [n.split(" may ignore ")[1][:5] for n in ignored] == ["instr", "speed"]
    gemini = VoiceConfig(provider="openrouter", model="google/gemini-3.8-flash-tts", voice="Kore", instructions="calm")
    assert ortts.voice_notes(gemini, ortts.LookupFailure("offline")) == []


def test_snapshot() -> None:
    snap = ortts.snapshot()
    assert snap["date"] == "2026-10-08" and MODEL in snap["models"]
    assert snap["models"][MODEL]["zdr"] and "en_paul_neutral" in (ortts.known_voices(MODEL) or [])


# ----- vidgen tts --------------------------------------------------------------------------------


def run(root: Path, *args: str) -> int:
    return main(["tts", str(root), *args])


def test_tts_generates_mp3s_hashes_and_reports_cost(make_project, api: FakeOpenRouter, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(or_config())
    assert run(root) == 0
    out = capsys.readouterr().out
    assert "[1/3] generated intro_b1.mp3 (12 chars)" in out
    assert "done: 3 beat(s) generated (43 characters, $0.0006 charged by openrouter), 0 up to date" in out
    assert [b["input"] for b in api.bodies()] == ["Hello there.", "Second beat.", "One two three four."]
    audio = root / "audio"
    assert (audio / "custom.mp3").read_bytes() == MP3
    project = Project.load(root)
    assert (audio / "custom.hash").read_text(encoding="utf-8") == tts.get_provider(project.voice()).cache_key("One two three four.")
    assert not list(audio.glob("*.align.json"))  # no character timings from this provider
    assert {s.state for s in tts.audio_status(project)} == {"ok"}
    assert run(root) == 0
    assert "nothing to do: 3 beat(s) up to date" in capsys.readouterr().out
    assert len(api.posts()) == 3
    assert KEY not in all_files_text(root)

    # instructions are in every beat's hash: all three are voiced again
    data = or_config({**VOICE, "instructions": "slow and warm"})
    write(root, data)
    assert {s.state for s in tts.audio_status(Project.load(root))} == {"stale"}
    assert run(root) == 0
    assert len(api.posts()) == 6 and api.bodies()[-1]["instructions"] == "slow and warm"


def test_dry_run_lists_provider_model_voice_and_cost(make_project, api: FakeOpenRouter, monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY")
    root = make_project(or_config())
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would generate intro_b1.mp3 (12 chars, ~$0.0002112)" in out
    assert "dry run: 3 beat(s) to generate, 43 characters; 0 up to date" in out
    assert f"  voice default (openrouter {MODEL}, voice en_paul_neutral): 3 beat(s), 43 characters" in out
    assert f"  price of {MODEL}: OpenRouter: $0.0000176 per character; the highest of 3 providers" in out
    assert "  cost: estimated $0.0007568 (OpenRouter prices of " in out
    assert not api.posts()

    assert main(["tts", str(root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["provider"] == "openrouter" and doc["characters"] == 43 and doc["unknown_cost"] == 0
    assert doc["estimated_cost"] == pytest.approx(43 * 0.0000176, abs=1e-6)
    assert doc["prices"][MODEL]["per_character"] == pytest.approx(0.0000176)
    assert doc["price_note"].startswith("OpenRouter prices of ") and doc["charged"] is None
    beat = doc["beats"][0]
    assert (beat["provider"], beat["model"], beat["provider_voice"], beat["characters"]) == ("openrouter", MODEL, "en_paul_neutral", 12)
    assert beat["estimated_cost"] == pytest.approx(12 * 0.0000176, abs=1e-6)
    assert doc["voices"]["default"]["model"] == MODEL


def test_dry_run_offline_and_unknown_model(make_project, api: FakeOpenRouter, capsys) -> None:
    root = make_project(or_config())
    api.offline = True
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "(12 chars, price unknown)" in out
    assert "  cost: price unknown (OpenRouter prices unknown (its model list could not be reached))" in out

    api.offline = False
    root2 = make_project(or_config({**VOICE, "model": "nobody/none"}), folder="p2")
    assert run(root2, "--dry-run") == 0
    assert "  problem: OpenRouter has no text-to-speech model 'nobody/none'" in capsys.readouterr().out
    assert run(root2) == 1  # refused before paying
    assert "cannot generate with these settings" in capsys.readouterr().err
    assert not api.posts()


def test_elevenlabs_dry_run_text_unchanged(make_project, api: FakeOpenRouter, capsys) -> None:
    root = make_project()
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "dry run: 3 beat(s) to generate, 43 characters; 0 up to date"
    assert not api.requests  # no lookup for ElevenLabs
    assert main(["tts", str(root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["provider"] == "elevenlabs" and doc["beats"][0]["model"] == "eleven_multilingual_v2"
    assert doc["unknown_cost"] == 3 and "ElevenLabs bills" in doc["price_note"]


def test_pronunciation_and_named_voices(make_project, api: FakeOpenRouter) -> None:
    data = or_config(
        {**VOICE, "instructions": "warm narrator"},
        pronunciation={"Hello": "Hullo"},
        voices={"guest": {"voice": "gb_oliver_neutral", "instructions": "curious guest", "speed": 1.2}},
    )
    data["scenes"][1]["voice"] = "guest"
    root = make_project(data)
    assert run(root) == 0
    bodies = api.bodies()
    assert bodies[0]["input"] == "Hullo there."  # pronunciation applied before sending
    assert (bodies[0]["voice"], bodies[0]["instructions"]) == ("en_paul_neutral", "warm narrator")
    assert (bodies[2]["voice"], bodies[2]["instructions"], bodies[2]["speed"]) == ("gb_oliver_neutral", "curious guest", 1.2)
    project = Project.load(root)
    providers = tts.beat_providers(project)
    assert (root / "audio" / "intro_b1.hash").read_text(encoding="utf-8") == providers["intro_b1"].cache_key("Hullo there.")
    # editing the guest re-voices only its beat
    data["voices"]["guest"]["instructions"] = "excited guest"
    write(root, data)
    plan = plan_tts(Project.load(root))
    assert [b.id for b in plan.todo] == ["custom"]


def test_timestamps_fall_back_to_estimates(make_project, api: FakeOpenRouter) -> None:
    from vidgen.speech import beat_word_times, estimate_word_times, read_alignment, speech_bounds

    root = make_project(or_config({**VOICE, "timestamps": True}))
    project = Project.load(root)
    assert "voice.timestamps: OpenRouter returns no word timings; captions use estimated timings" in validate_warnings(project)
    run_tts(project, out=lambda s: None)
    audio = root / "audio"
    assert read_alignment(audio, "intro_b1", "Hello there.") is None
    s0, s1 = speech_bounds(audio / "intro_b1.mp3")
    times = beat_word_times(audio, "intro_b1", "Hello there.", 0.0, 1.0)
    assert times == estimate_word_times(["Hello", "there."], s0, min(s1, 1.0))


def test_validate_warnings_for_model_and_voice(make_project) -> None:
    root = make_project(or_config({**VOICE, "voice": "zed"}, voices={"guest": {"voice": "nobody"}}))
    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    data["scenes"][1]["voice"] = "guest"
    write(root, data)
    warnings = validate_warnings(Project.load(root))
    assert any(w.startswith(f"voice.voice: 'zed' is not among the voices OpenRouter listed for {MODEL} on 2026-10-08") for w in warnings)
    assert any(w.startswith("voices.guest.voice: 'nobody'") for w in warnings)
    root2 = make_project(or_config({**VOICE, "model": "mistralai/voxtral-mini-tts"}), folder="p2")
    [warning] = [w for w in validate_warnings(Project.load(root2)) if w.startswith("voice.model")]
    assert f"did you mean {MODEL}?" in warning
    root3 = make_project(or_config(), folder="p3")
    assert not [w for w in validate_warnings(Project.load(root3)) if w.startswith("voice")]


def test_readback_and_narration_speed_work_with_its_audio(make_project, api: FakeOpenRouter) -> None:
    from test_readback import FakeSTT
    from test_timing_lint import activity, beat
    from vidgen.config import LintRules
    from vidgen.lint import RULES, SceneContext
    from vidgen.readback import run_readback

    api.speech = [PCM, PCM, PCM]  # converted to MP3 by ffmpeg
    root = make_project(or_config())
    project = Project.load(root)
    run_tts(project, out=lambda s: None)
    heard = {"intro_b1": "Hello there.", "intro_b2": "Second beat.", "custom": "One two tree four."}
    result = run_readback(Project.load(root), provider=FakeSTT(heard), log=lambda s: None)
    assert result.transcribed == 3 and [b.flagged for b in result.beats] == [False, False, True]

    text = "one two three four five six seven eight nine ten"
    doc = activity([beat("custom", 0, 3.0, text=text, source="audio")])
    [issue] = RULES["narration_speed"].check(SceneContext("main", doc, project.audio_dir), LintRules().narration_speed)
    assert issue.beat == "custom" and "s of speech) is above" in issue.message  # 10 words in ~0.4 s of tone


def test_mcp_tts_still_needs_confirm_cost() -> None:
    from vidgen.mcp_tools import cost_refusal

    assert "confirm_cost=true" in cost_refusal("tts", "calls the paid text-to-speech API")
    source = (Path(__file__).parent.parent / "src" / "vidgen" / "mcp_server.py").read_text(encoding="utf-8")
    assert 'raise ToolError(cost_refusal("tts"' in source and "OpenRouter with voice.provider: openrouter" in source
