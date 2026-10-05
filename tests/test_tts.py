"""TTS: ElevenLabs requests, caching, `vidgen tts`, audio status, variants. No network (urlopen mocked)."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config, write_files
from vidgen import tts
from vidgen.cli import main
from vidgen.config import VoiceConfig
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.tts.elevenlabs import ElevenLabsProvider

KEY = "sk_test_SECRET_key_1234567890"
KPHI3 = Path("/home/claude/work/kphi3_paper_video")


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def http_error(code: int, body: str, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://api.elevenlabs.io/x", code, "err", msg, io.BytesIO(body.encode()))


class FakeAPI:
    """Replaces urllib.request.urlopen. ``responses`` is a list of exceptions/bytes consumed in
    order; when exhausted, each call returns ``b"MP3:" + text``."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []
        self.responses: list[Any] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return FakeResponse(item)
        return FakeResponse(b"MP3:" + self.body(-1)["text"].encode())

    def body(self, i: int) -> dict[str, Any]:
        return json.loads(self.requests[i].data)

    def texts(self) -> list[str]:
        return [json.loads(r.data)["text"] for r in self.requests]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeAPI:
    fake = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("ELEVENLABS_API_KEY", KEY)
    return fake


@pytest.fixture
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


def provider(**voice: Any) -> ElevenLabsProvider:
    return ElevenLabsProvider(VoiceConfig(**voice), sleep=lambda s: None)


def all_files_text(root: Path) -> str:
    return "".join(p.read_bytes().decode("utf-8", errors="replace") for p in root.rglob("*") if p.is_file())


# ----- provider ---------------------------------------------------------------------------------


def test_request_url_body_headers(api: FakeAPI) -> None:
    p = provider(voice_id="abc", output_format="mp3_22050_32", settings={"stability": 0.3})
    assert p.synthesize("Hello.", "Before.", "After.") == b"MP3:Hello."
    (req,) = api.requests
    assert req.full_url == "https://api.elevenlabs.io/v1/text-to-speech/abc?output_format=mp3_22050_32"
    assert req.get_method() == "POST"
    assert req.get_header("Xi-api-key") == KEY
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("Accept") == "audio/mpeg"
    assert api.timeouts == [120.0]
    assert api.body(0) == {
        "text": "Hello.",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.3, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True},
        "previous_text": "Before.",
        "next_text": "After.",
    }


def test_context_off_and_edges(api: FakeAPI) -> None:
    provider(context=False).synthesize("A", "prev", "next")
    provider().synthesize("B", None, "next")
    assert "previous_text" not in api.body(0) and "next_text" not in api.body(0)
    assert "previous_text" not in api.body(1) and api.body(1)["next_text"] == "next"


def test_key_read_at_call_time(api: FakeAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    p = provider()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "  other_key\n")
    p.synthesize("x")
    assert api.requests[0].get_header("Xi-api-key") == "other_key"
    assert "other_key" not in repr(vars(p))


def test_http_error_message_has_status_and_body_but_no_key(api: FakeAPI) -> None:
    api.responses = [http_error(401, f'{{"detail": "invalid api key {KEY}"}}' + "x" * 2000)]
    with pytest.raises(VidgenError) as info:
        provider().synthesize("x")
    msg = str(info.value)
    assert "HTTP 401" in msg and "invalid api key" in msg
    assert KEY not in msg and "***" in msg
    assert len(msg) < 700
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert len(api.requests) == 1  # 401 is not retried


def test_retry_transient_then_success() -> None:
    sleeps: list[float] = []
    p = ElevenLabsProvider(VoiceConfig(), sleep=sleeps.append)
    fake = FakeAPI()
    fake.responses = [http_error(503, "busy"), TimeoutError("timed out"), http_error(429, "slow", {"Retry-After": "7"}), b"ok"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(urllib.request, "urlopen", fake)
        mp.setenv("ELEVENLABS_API_KEY", KEY)
        assert p.synthesize("x") == b"ok"
    assert sleeps == [2.0, 4.0, 7.0]
    assert len(fake.requests) == 4


def test_retry_gives_up(api: FakeAPI) -> None:
    sleeps: list[float] = []
    p = ElevenLabsProvider(VoiceConfig(), sleep=sleeps.append, retries=2)
    api.responses = [http_error(500, "boom") for _ in range(3)]
    with pytest.raises(VidgenError, match="HTTP 500: boom"):
        p.synthesize("x")
    assert len(sleeps) == 2 and len(api.requests) == 3


def test_network_error(api: FakeAPI) -> None:
    api.responses = [urllib.error.URLError(OSError("Name or service not known"))]
    with pytest.raises(VidgenError, match="cannot reach ElevenLabs: OSError: Name or service not known"):
        provider().synthesize("x")
    assert len(api.requests) == 1  # not transient: no retry


def test_unexpected_error_is_scrubbed(api: FakeAPI) -> None:
    api.responses = [ValueError(f"Invalid header value {KEY!r}")]
    with pytest.raises(VidgenError) as info:
        provider().synthesize("x")
    assert KEY not in str(info.value)


def test_empty_response(api: FakeAPI) -> None:
    api.responses = [b""]
    with pytest.raises(VidgenError, match="empty response"):
        provider().synthesize("x")


def test_cache_key_format() -> None:
    p = provider(voice_id="v", model_id="m", output_format="f")
    settings = json.dumps(
        {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}, sort_keys=True
    )
    assert p.cache_key("Hi") == hashlib.sha1(f"v|m|f|{settings}|Hi".encode()).hexdigest()
    legacy = hashlib.sha1(b"vmHi").hexdigest()
    assert provider(voice_id="v", model_id="m").matches("Hi", legacy + "\n")
    assert not provider(voice_id="v", model_id="m", settings={"style": 0.1}).matches("Hi", legacy)
    assert not provider(voice_id="v", model_id="m", output_format="mp3_22050_32").matches("Hi", legacy)
    assert not p.matches("Hi", "")


def test_get_provider() -> None:
    assert isinstance(tts.get_provider(VoiceConfig()), ElevenLabsProvider)
    with pytest.raises(VidgenError, match="unknown voice provider"):
        tts.get_provider(VoiceConfig.model_construct(provider="other"))


@pytest.mark.skipif(not (KPHI3 / "audio").is_dir(), reason="kphi3 reference project not available")
def test_kphi3_hash_files_are_accepted(tmp_path: Path) -> None:
    script = json.loads((KPHI3 / "script.json").read_text(encoding="utf-8"))
    data = {
        "title": "kphi3",
        "voice": {"voice_id": script["voice_id"], "model_id": script["model_id"]},
        "scenes": [
            {"id": f"s{i}", "type": "text_card", "beats": s["beats"]} for i, s in enumerate(script["scenes"], 1)
        ],
    }
    root = tmp_path / "kphi3"
    (root / "audio").mkdir(parents=True)
    (root / "video.json").write_text(json.dumps(data), encoding="utf-8")
    for h in (KPHI3 / "audio").glob("*.hash"):
        shutil.copy(h, root / "audio" / h.name)
        (root / "audio" / f"{h.stem}.mp3").write_bytes(b"x")  # status only checks that it exists
    project = Project.load(root)
    states = [s.state for s in tts.audio_status(project)]
    assert len(states) == 27 and set(states) == {"ok"}
    # a different voice setting invalidates them
    data["voice"]["settings"] = {"stability": 0.5}
    (root / "video.json").write_text(json.dumps(data), encoding="utf-8")
    assert {s.state for s in tts.audio_status(Project.load(root))} == {"stale"}


# ----- vidgen tts -------------------------------------------------------------------------------


def run(root: Path, *args: str) -> int:
    return main(["tts", str(root), *args])


def test_tts_generates_all_then_skips(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    assert run(root) == 0
    out = capsys.readouterr().out
    assert "[1/3] generated intro_b1.mp3 (12 chars)" in out
    assert "done: 3 beat(s) generated (43 characters), 0 up to date" in out
    assert api.texts() == ["Hello there.", "Second beat.", "One two three four."]
    # neighbours across scene boundaries
    assert api.body(1)["previous_text"] == "Hello there." and api.body(1)["next_text"] == "One two three four."
    assert "previous_text" not in api.body(0) and "next_text" not in api.body(2)
    audio = root / "audio"
    assert (audio / "custom.mp3").read_bytes() == b"MP3:One two three four."
    p = Project.load(root)
    assert (audio / "custom.hash").read_text(encoding="utf-8") == tts.get_provider(p.config.voice).cache_key(
        "One two three four."
    )
    assert not list(audio.glob(".*"))  # no temp files left
    assert run(root) == 0
    assert len(api.requests) == 3
    assert "nothing to do: 3 beat(s) up to date" in capsys.readouterr().out
    assert KEY not in all_files_text(root)


def edit(root: Path, fn) -> None:
    import yaml

    data = yaml.safe_load((root / "video.yaml").read_text(encoding="utf-8"))
    fn(data)
    (root / "video.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def test_text_change_regenerates_only_that_beat(make_project, api: FakeAPI) -> None:
    root = make_project()
    run(root)
    edit(root, lambda d: d["scenes"][0]["beats"][1].update(text="Changed second beat."))
    run(root)
    assert api.texts()[3:] == ["Changed second beat."]  # neighbours' context changed but not regenerated


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(voice={"voice_id": "other"}),
        lambda d: d.update(voice={"model_id": "eleven_turbo_v2"}),
        lambda d: d.update(voice={"output_format": "mp3_22050_32"}),
        lambda d: d.update(voice={"settings": {"style": 0.2}}),
    ],
)
def test_voice_change_regenerates_everything(make_project, api: FakeAPI, change) -> None:
    root = make_project()
    run(root)
    edit(root, change)
    run(root)
    assert len(api.requests) == 6


def test_context_flag_does_not_invalidate(make_project, api: FakeAPI) -> None:
    root = make_project()
    run(root)
    edit(root, lambda d: d.update(voice={"context": False}))
    run(root)
    assert len(api.requests) == 3


def test_force_and_beat(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    run(root, "--beat", "custom")
    assert api.texts() == ["One two three four."]
    assert api.body(0)["previous_text"] == "Second beat."  # context from the full beat list
    run(root, "--beat", "custom")
    assert len(api.requests) == 1
    run(root, "--force", "--beat", "custom", "--beat", "intro_b1")
    assert api.texts()[1:] == ["Hello there.", "One two three four."]  # video order
    run(root, "--force")
    assert len(api.requests) == 6
    capsys.readouterr()


def test_unknown_beat(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_project(), "--beat", "nope") == 1
    assert "unknown beat id(s): nope" in capsys.readouterr().err
    assert api.requests == []


def test_dry_run_needs_no_key(make_project, no_key, monkeypatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fail(*a: Any, **k: Any) -> None:
        raise AssertionError("network used")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    root = make_project()
    assert run(root, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would generate intro_b1.mp3 (12 chars)" in out
    assert "dry run: 3 beat(s) to generate, 43 characters; 0 up to date" in out
    assert not (root / "audio").exists()


def test_missing_key(make_project, no_key, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    assert run(root) == 1
    err = capsys.readouterr().err
    assert "ELEVENLABS_API_KEY" in err and "setx ELEVENLABS_API_KEY" in err and "export ELEVENLABS_API_KEY=" in err
    assert "Traceback" not in err


def test_no_key_needed_when_up_to_date(make_project, api: FakeAPI, monkeypatch, capsys) -> None:
    root = make_project()
    run(root)
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert run(root) == 0
    capsys.readouterr()


def test_http_error_via_cli(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    api.responses = [b"first", http_error(422, f"bad request for key {KEY}")]
    assert run(root) == 1
    err = capsys.readouterr().err
    assert "beat 'intro_b2': ElevenLabs returned HTTP 422: bad request" in err
    assert "1 of 3 done before the error" in err
    assert KEY not in err
    assert (root / "audio" / "intro_b1.hash").is_file()
    assert not (root / "audio" / "intro_b2.mp3").exists()
    assert KEY not in all_files_text(root)


def test_failed_write_leaves_no_hash(make_project, api: FakeAPI, monkeypatch, capsys) -> None:
    root = make_project()
    run(root, "--beat", "intro_b1")
    old_hash = (root / "audio" / "intro_b1.hash").read_text(encoding="utf-8")
    edit(root, lambda d: d["scenes"][0]["beats"][0].update(text="New text."))

    def broken_replace(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("vidgen.fileio.os.replace", broken_replace)
    assert run(root, "--beat", "intro_b1") == 1
    assert "disk full" in capsys.readouterr().err
    audio = root / "audio"
    assert (audio / "intro_b1.mp3").read_bytes() == b"MP3:Hello there."  # old audio intact
    assert (audio / "intro_b1.hash").read_text(encoding="utf-8") == old_hash
    assert not list(audio.glob(".*"))
    monkeypatch.undo()
    assert tts.audio_status(Project.load(root))[0].state == "stale"


def test_hash_written_only_after_mp3(make_project, api: FakeAPI, monkeypatch, capsys) -> None:
    from vidgen.tts import cache

    root = make_project()
    real = cache.atomic_write
    calls: list[str] = []

    def spy(path: Path, data: bytes) -> None:
        calls.append(path.name)
        if path.suffix == ".mp3":
            raise OSError("cannot write")
        real(path, data)

    monkeypatch.setattr("vidgen.tts.run.atomic_write", spy)
    assert run(root) == 1
    assert calls == ["intro_b1.mp3"]
    assert not (root / "audio" / "intro_b1.hash").exists()
    capsys.readouterr()


def test_orphans_reported_not_deleted(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    write_files(root, {"audio/old_beat.mp3": "x", "audio/old_beat.hash": "y"})
    run(root, "--dry-run")
    assert "orphaned audio in audio/ (no beat with that id; not deleted): old_beat.mp3" in capsys.readouterr().out
    run(root)
    assert "old_beat.mp3" in capsys.readouterr().out
    assert (root / "audio" / "old_beat.mp3").exists()


# ----- audio status / validate ------------------------------------------------------------------


def test_audio_status_and_validate_summary(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    run(root, "--beat", "intro_b1", "--beat", "intro_b2")
    edit(root, lambda d: d["scenes"][0]["beats"][1].update(text="Edited."))
    statuses = tts.audio_status(Project.load(root))
    assert [(s.beat_id, s.state) for s in statuses] == [("intro_b1", "ok"), ("intro_b2", "stale"), ("custom", "missing")]
    assert statuses[0].mp3 == root / "audio" / "intro_b1.mp3"
    (root / "audio" / "intro_b1.hash").unlink()
    assert tts.audio_status(Project.load(root))[0].state == "stale"
    capsys.readouterr()
    assert main(["validate", str(root)]) == 0
    assert "audio:     0 ok, 2 stale, 1 missing" in capsys.readouterr().out


def test_validate_audio_summary_without_key(make_project, no_key, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    write_files(root, {"audio/gone.mp3": "x"})
    assert main(["validate", str(root)]) == 0
    assert "audio:     0 ok, 0 stale, 3 missing (1 orphaned mp3)" in capsys.readouterr().out


# ----- variants ---------------------------------------------------------------------------------


def variant_config() -> dict[str, Any]:
    scenes = minimal_config()["scenes"]
    edited = json.loads(json.dumps(scenes))
    edited[1]["beats"][0]["text"] = "Uno dos tres cuatro."
    return minimal_config(
        variants={
            "vertical": {"format": {"width": 1080, "height": 1920}},
            "spanish": {"voice": {"voice_id": "es_voice"}},
            "same_voice": {"voice": {"voice_id": "nPczCjzI2devNBz1zQrb"}},
            "edited": {"scenes": edited},
        }
    )


def test_variant_audio_dir(make_project) -> None:
    root = make_project(variant_config())
    assert Project.load(root).audio_dir == root / "audio"
    assert Project.load(root, "vertical").audio_dir == root / "audio"
    assert Project.load(root, "same_voice").audio_dir == root / "audio"  # effective voice unchanged
    assert Project.load(root, "spanish").audio_dir == root / "audio" / "spanish"
    assert Project.load(root, "edited").audio_dir == root / "audio" / "edited"
    assert Project.load(root, "spanish").base_config.voice.voice_id == "nPczCjzI2devNBz1zQrb"


def test_tts_variant(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(variant_config())
    run(root)
    run(root, "--variant", "vertical")
    assert len(api.requests) == 3  # shares base audio
    run(root, "--variant", "spanish")
    assert len(api.requests) == 6
    assert "/es_voice?" in api.requests[-1].full_url
    assert (root / "audio" / "spanish" / "intro_b1.mp3").is_file()
    assert (root / "audio" / "intro_b1.mp3").read_bytes() == b"MP3:Hello there."
    capsys.readouterr()
    run(root, "--variant", "edited")
    out = capsys.readouterr().out
    assert api.texts()[6:] == ["Uno dos tres cuatro."]  # unchanged beats are copied from audio/
    assert "copied intro_b1.mp3 from audio/intro_b1.mp3" in out
    assert (root / "audio" / "edited" / "intro_b2.mp3").read_bytes() == b"MP3:Second beat."
    # base audio does not report the variant folders or the shared variant beats as orphans
    assert tts.orphaned_audio(Project.load(root)) == []
    assert main(["validate", str(root)]) == 0
    out = capsys.readouterr().out
    assert "audio:     3 ok, 0 stale, 0 missing" in out
    assert "audio [spanish]: 3 ok, 0 stale, 0 missing" in out
    assert "audio [edited]: 3 ok, 0 stale, 0 missing" in out
    assert "[vertical]" not in out


def test_unknown_variant(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(make_project(), "--variant", "nope", "--dry-run") == 1
    assert "unknown variant 'nope'" in capsys.readouterr().err


def test_narrated_scene_uses_variant_audio_dir(make_project) -> None:
    from types import SimpleNamespace

    from vidgen.scene import NarratedScene

    root = make_project(variant_config())
    write_files(root, {"audio/spanish/intro_b1.mp3": "x", "audio/intro_b2.mp3": "x"})
    project = Project.load(root, "spanish")
    fake = SimpleNamespace(project=project, beat=lambda b: project.beat(b))
    assert NarratedScene.beat_audio(fake, "intro_b1") == root / "audio" / "spanish" / "intro_b1.mp3"
    assert NarratedScene.beat_audio(fake, "intro_b2") is None


# ----- hooks ------------------------------------------------------------------------------------

HOOKS = """
    import json
    import os
    from vidgen.api import current_project, hook

    def log(entry):
        path = current_project().root / "hook_log.json"
        seen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        path.write_text(json.dumps(seen + [entry]), encoding="utf-8")

    @hook("pre_tts")
    def skip_custom(ctx):
        d = ctx.data
        log(["pre", list(d["beats"]), d["dry_run"], d["force"], d["audio_dir"].name])
        d["beats"].remove("custom")

    @hook("post_tts")
    def after(ctx):
        log(["post", ctx.data["generated"], sorted(ctx.data)])
        assert all(os.environ["ELEVENLABS_API_KEY"] not in str(v) for v in ctx.data.values())
"""


def test_hooks_from_extension(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    write_files(root, {"extensions/tts_hooks.py": HOOKS})
    assert run(root) == 0
    assert api.texts() == ["Hello there.", "Second beat."]
    assert json.loads((root / "hook_log.json").read_text(encoding="utf-8")) == [
        ["pre", ["intro_b1", "intro_b2", "custom"], False, False, "audio"],
        ["post", ["intro_b1", "intro_b2"], ["audio_dir", "generated"]],
    ]
    assert "done: 2 beat(s) generated" in capsys.readouterr().out
    (root / "hook_log.json").unlink()
    assert run(root, "--dry-run") == 0  # pre_tts runs on a dry run, post_tts does not
    assert json.loads((root / "hook_log.json").read_text(encoding="utf-8")) == [["pre", ["custom"], True, False, "audio"]]
    assert "dry run: 0 beat(s) to generate" in capsys.readouterr().out


def test_hook_error_aborts(make_project, api: FakeAPI, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project()
    write_files(root, {"extensions/bad.py": "from vidgen.api import hook\n@hook('pre_tts')\ndef bad(ctx):\n    ctx.data['beats'] = ['zzz']\n"})
    assert run(root) == 1
    assert "pre_tts hook added unknown beat id(s): zzz" in capsys.readouterr().err
    assert api.requests == []
