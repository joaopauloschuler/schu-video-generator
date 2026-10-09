"""Review of Phase F (Step 63): the OpenRouter providers end to end with mocked APIs —
`vidgen imagegen` then `vidgen render` (PNG and SVG with `draw` / `recolor`), `vidgen tts` then
`vidgen render` with burned-in captions, a variant switching the narration provider, the
one-provider-per-video errors, the dry-run JSON over MCP (offline) — and the key never reaching
an error message (`httpapi`, `read_api_key`)."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_imagegen import PROMPT, image_scene
from test_imagegen_openrouter import SEEDREAM, VECTOR, FakeRouter, router_body
from test_tts_openrouter import KEY, MODEL, VOICE, FakeOpenRouter
from test_vector_images import HILLS
from vidgen import httpapi
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.imagegen import openrouter as orr
from vidgen.imagegen import scene_images
from vidgen.project import Project

SMALL = {"format": {"width": 160, "height": 90, "fps": 5}, "preview": {"width": 96, "height": 54, "fps": 5}}


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> FakeRouter:
    fake = FakeRouter()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv(orr.API_KEY_ENV, KEY)
    return fake


@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> FakeOpenRouter:
    fake = FakeOpenRouter()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv(orr.API_KEY_ENV, KEY)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    return fake


def json_out(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


# ----- the key never reaches a message -------------------------------------------------------------


def test_scrub_hides_the_key_also_as_python_escapes_it() -> None:
    key = "sk-or-v1-ab\ncd"
    rejected = f"Invalid header value {('Bearer ' + key).encode()!r}"   # what http.client raises
    assert "ab" not in httpapi.scrub(rejected, key).split("Bearer ")[1]
    assert httpapi.scrub(f"x {key} y", key) == "x *** y" and httpapi.scrub("x", "") == "x"


def test_get_scrubs_the_key_from_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(request: urllib.request.Request, timeout: float) -> Any:
        raise ValueError(f"Invalid header value {request.get_header('Authorization').encode()!r}")

    monkeypatch.setattr(urllib.request, "urlopen", broken)
    with pytest.raises(VidgenError) as info:
        httpapi.get("https://openrouter.ai/api/v1/generation?id=gen-1", headers={"Authorization": f"Bearer {KEY}"},
                    service="OpenRouter", timeout=1, secret=KEY)
    assert KEY not in str(info.value) and "***" in str(info.value)


@pytest.mark.parametrize("bad", ["sk-or-v1 abc", "sk-or-v1-a\x1bb", "sk-or-v1-a\tb", "sk-or-v1-ç"])
def test_a_garbled_key_is_refused_without_quoting_it(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv(orr.API_KEY_ENV, bad)
    with pytest.raises(VidgenError, match="contains spaces, control or non-ASCII characters") as info:
        orr.read_api_key("tts")
    assert "sk-or-v1" not in str(info.value)


def test_live_check_tool_never_prints_the_key() -> None:
    source = (Path(__file__).parents[1] / "tools" / "live_check_openrouter.py").read_text(encoding="utf-8")
    assert "os.environ.get(orr.API_KEY_ENV" in source   # only to say whether it is set
    assert source.count("os.environ") == 1
    assert source.count("{key}") == 1 and 'f"Bearer {key}"' in source   # the key goes into the header only
    assert source.count("secret=key") == 1 and source.count("httpapi.scrub(") == 2   # and is removed from what is printed


# ----- pictures: imagegen -> render ----------------------------------------------------------------


@pytest.mark.render
@pytest.mark.slow
def test_generated_png_and_svg_render(router: FakeRouter, make_project, capsys: pytest.CaptureFixture[str]) -> None:
    scenes = [
        image_scene({"prompt": PROMPT}, "photo", caption="A boat"),
        image_scene({"prompt": "flat hills", "format": "svg"}, "drawn", draw=True, recolor="theme"),
    ]
    imagegen = {"provider": "openrouter", "model": SEEDREAM, "svg_model": VECTOR}
    root = make_project(minimal_config(scenes=scenes, imagegen=imagegen, **SMALL))
    assert main(["imagegen", str(root), "--dry-run", "--json"]) == 0
    doc = json_out(capsys)
    assert [(i["format"], i["model"], i["estimated_cost"]) for i in doc["images"]] == [("png", SEEDREAM, 0.04), ("svg", VECTOR, 0.08)]
    assert router.posts == []

    router.responses = [router_body(cost=0.04), router_body(HILLS.read_bytes(), media_type="image/svg+xml", cost=0.08)]
    assert main(["imagegen", str(root)]) == 0
    assert "done: 2 picture(s) generated ($0.12 charged by openrouter)" in capsys.readouterr().out
    png, svg = (i.request.path for i in scene_images(Project.load(root)))
    assert png.suffix == ".png" and svg.suffix == ".svg" and svg.read_bytes() == HILLS.read_bytes()

    assert main(["render", str(root), "--no-audio", "--frames", "--json"]) == 0
    doc = json_out(capsys)
    assert Path(doc["outputs"]["video"]).is_file() and Path(doc["outputs"]["frames"]).is_file()
    assert [(s["id"], s["status"]) for s in doc["scenes"]] == [("photo", "rendered"), ("drawn", "rendered")]
    frames = json.loads(Path(doc["outputs"]["frames"]).read_text(encoding="utf-8"))
    assert [(s["id"], len(s["frames"])) for s in frames["scenes"]] == [("photo", 1), ("drawn", 1)]


# ----- narration: tts -> render with captions, a variant switching provider -------------------------


def or_project(make_project, **extra: Any) -> Path:
    scenes = [{"id": "s", "type": "text_card", "params": {"text": "Hi"}, "beats": [{"text": "Hello there, viewers."}, {"text": "Second beat here."}]}]
    return make_project(minimal_config(scenes=scenes, voice=VOICE, overlays=[{"type": "captions"}], **SMALL, **extra))


@pytest.mark.render
@pytest.mark.slow
def test_openrouter_narration_renders_with_captions(speech: FakeOpenRouter, make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = or_project(make_project)
    assert main(["tts", str(root), "--dry-run", "--json"]) == 0
    doc = json_out(capsys)
    assert doc["provider"] == "openrouter" and doc["estimated_cost"] == round(38 * 0.0000176, 6)
    assert speech.posts() == []
    assert main(["tts", str(root)]) == 0
    assert "$0.0004 charged by openrouter" in capsys.readouterr().out
    assert main(["render", str(root), "--json"]) == 0
    doc = json_out(capsys)
    srt = Path(doc["outputs"]["subtitles"]).read_text(encoding="utf-8")
    assert "Hello there, viewers." in srt and "Second beat here." in srt
    assert doc["audio"] is True and Path(doc["outputs"]["video"]).is_file()
    assert KEY not in "".join(p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*") if p.is_file() and p.suffix in {".json", ".yaml", ".hash", ".srt"})


@pytest.mark.render
@pytest.mark.slow
def test_variant_switches_the_narration_provider(speech: FakeOpenRouter, make_project, capsys: pytest.CaptureFixture[str]) -> None:
    variants = {"routed": {"voice": VOICE, "voices": {"guest": {"voice_id": None, "voice": "gb_oliver_curious"}}}}
    scenes = [{"id": "s", "type": "text_card", "params": {"text": "Hi"},
               "beats": [{"text": "Hello there."}, {"text": "A guest speaks.", "voice": "guest"}]}]
    root = make_project(minimal_config(scenes=scenes, voices={"guest": {"voice_id": "abc123"}}, variants=variants, **SMALL))
    assert main(["validate", str(root)]) == 0
    capsys.readouterr()
    assert main(["tts", str(root), "--variant", "routed"]) == 0
    assert [(b["model"], b.get("voice")) for b in speech.bodies()] == [(MODEL, "en_paul_neutral"), (MODEL, "gb_oliver_curious")]
    assert sorted(p.name for p in (root / "audio" / "routed").glob("*.mp3")) == ["s_b1.mp3", "s_b2.mp3"]
    assert not list((root / "audio").glob("*.mp3"))   # the ElevenLabs base keeps its own (empty) folder
    capsys.readouterr()
    assert main(["render", str(root), "--variant", "routed", "--preview", "--json"]) == 0
    doc = json_out(capsys)
    assert doc["variant"] == "routed" and doc["audio"] is True and Path(doc["outputs"]["video"]).is_file()


def test_one_provider_per_video_errors(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    mixed = make_project(minimal_config(voices={"guest": {"provider": "openrouter", "model": MODEL}}), folder="mixed")
    assert main(["validate", str(mixed)]) != 0
    assert "voices.guest.provider: one TTS provider per video" in capsys.readouterr().err
    keys = make_project(minimal_config(voice=VOICE, voices={"guest": {"voice_id": "abc"}}), folder="keys")
    assert main(["validate", str(keys)]) != 0
    assert "voices.guest.voice_id" in capsys.readouterr().err


# ----- dry-run JSON over MCP (the server runs in its own process: offline there) ---------------------


def test_mcp_dry_runs_for_openrouter_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_mcp import doc_of, error_text, run_session

    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")   # every lookup fails fast: prices unknown, nothing paid
    for name in ("NO_PROXY", "no_proxy", orr.API_KEY_ENV, "ELEVENLABS_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "root"
    config = minimal_config(voice=VOICE, imagegen={"provider": "openrouter", "model": SEEDREAM},
                            scenes=[image_scene({"prompt": PROMPT}), *minimal_config()["scenes"]], **SMALL)
    (root / "proj").mkdir(parents=True)
    (root / "proj" / "video.yaml").write_text(json.dumps(config), encoding="utf-8")
    assert os.environ.get("HTTPS_PROXY")

    async def body(client: Any) -> None:
        tts = doc_of(await client.call_tool("tts", {"project": "proj"}))
        assert tts["dry_run"] is True and tts["provider"] == "openrouter" and tts["unknown_cost"] == 4
        assert tts["voices"]["default"]["voice_id"] is None   # no ElevenLabs default id in an OpenRouter video
        assert tts["beats"][0]["model"] == MODEL and tts["beats"][0]["provider_voice"] == "en_paul_neutral"
        assert "price unknown" in tts["prices"][MODEL]["basis"]
        images = doc_of(await client.call_tool("imagegen", {"project": "proj"}))
        assert images["dry_run"] is True and images["images"][0]["model"] == SEEDREAM and images["images"][0]["estimated_cost"] is None
        for tool in ("tts", "imagegen"):
            assert "confirm_cost=true" in error_text(await client.call_tool(tool, {"project": "proj", "dry_run": False}))
        assert not (root / "proj" / "audio").exists() and not (root / "proj" / "assets").exists()

    run_session(root, body)
