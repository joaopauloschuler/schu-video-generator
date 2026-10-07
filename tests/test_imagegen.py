"""Generated images (Step 55): requests and cache keys, prompt helpers, the OpenAI provider with a
mocked urlopen (success, errors, rate-limit retries), `vidgen imagegen`, validate warnings,
placeholders and the `image` scene's `generate:`. No network: the API is never called."""

from __future__ import annotations

import base64
import io
import json
import logging
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError

from conftest import minimal_config
from vidgen import extensions, registry
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.imagegen import (
    STYLE_PRESETS,
    GeneratedPicture,
    GenerateImage,
    ImageRequest,
    compose_prompt,
    generated_image,
    image_request,
    imagegen_warnings,
    scene_images,
    text_in_prompt,
)
from vidgen.imagegen.openai import API_KEY_ENV, OpenAIImageProvider, parse_response
from vidgen.imagegen.placeholder import draw_placeholder, placeholder_path
from vidgen.imagegen.run import plan_imagegen, run_imagegen
from vidgen.project import Project
from vidgen.theme import Theme

KEY = "sk-test-secret-123"
PROMPT = "a lighthouse on a cliff at dawn"


def png_bytes(size: tuple[int, int] = (24, 16), color: tuple[int, int, int] = (10, 200, 30), fmt: str = "PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


def api_body(data: bytes | None = None, revised: str | None = "a revised prompt") -> bytes:
    item: dict[str, Any] = {"b64_json": base64.b64encode(data if data is not None else png_bytes()).decode()}
    if revised is not None:
        item["revised_prompt"] = revised
    return json.dumps({"created": 1, "data": [item]}).encode()


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def http_error(code: int, body: str, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://api.openai.com/v1/images/generations", code, "err", msg, io.BytesIO(body.encode()))


class FakeAPI:
    """Replaces urlopen: ``responses`` (exceptions or bodies) are used in order, then a PNG."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return FakeResponse(item)
        return FakeResponse(api_body())

    def body(self, k: int = -1) -> dict[str, Any]:
        return json.loads(self.requests[k].data.decode())


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeAPI:
    fake = FakeAPI()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv(API_KEY_ENV, KEY)
    return fake


def provider(sleeps: list[float] | None = None) -> OpenAIImageProvider:
    return OpenAIImageProvider(sleep=(sleeps.append if sleeps is not None else lambda s: None))


def image_scene(generate: Any, scene_id: str = "pic", **params: Any) -> dict[str, Any]:
    return {"id": scene_id, "type": "image", "params": {"generate": generate, **params}, "beats": [{"text": "A picture."}]}


@pytest.fixture
def gen_project(make_project):
    def make(scenes: list[dict[str, Any]] | None = None, **overrides: Any) -> Project:
        scenes = scenes if scenes is not None else [image_scene({"prompt": PROMPT, "negative": "people"})]
        return Project.load(make_project(minimal_config(scenes=scenes, **overrides)))

    return make


def store(request: ImageRequest, data: bytes | None = None) -> None:
    request.path.parent.mkdir(parents=True, exist_ok=True)
    request.path.write_bytes(data if data is not None else png_bytes())


# ----- prompts and requests ------------------------------------------------------------------------


def test_compose_prompt_adds_style_and_negative() -> None:
    assert compose_prompt("  a  cat ") == "a cat."
    assert compose_prompt("A cat!", "flat colours.", "dogs") == "A cat! Style: flat colours. Avoid: dogs."


def test_generate_param_shorthand_and_limits() -> None:
    assert GenerateImage.model_validate("a cat").prompt == "a cat"
    with pytest.raises(ValidationError):
        GenerateImage.model_validate({"prompt": ""})
    with pytest.raises(ValidationError):
        GenerateImage.model_validate({"prompt": "x", "aspect": "wide"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        GenerateImage.model_validate({"prompt": "x", "colour": "red"})


def test_request_size_quality_and_style_from_config(gen_project) -> None:
    project = gen_project(imagegen={"style": "flat", "negative": "text, watermarks"})
    request = image_request(project, GenerateImage(prompt=PROMPT, negative="people"))
    assert (request.size, request.quality, request.model, request.provider) == ("1536x1024", "medium", "gpt-image-1", "openai")
    assert request.text == f"{PROMPT}. Style: {STYLE_PRESETS['flat']}. Avoid: people; text, watermarks."
    assert request.path == project.root / "assets" / "generated" / f"{request.key}.png"
    assert request.sidecar.name == f"{request.key}.json" and len(request.key) == 16
    assert request.estimated_cost == pytest.approx(0.063)
    # the scene's style replaces the project's; "none" drops it; own words are used as they are
    assert "Style" not in image_request(project, GenerateImage(prompt=PROMPT, style="none")).text
    assert "Style: chalk on a blackboard." in image_request(project, GenerateImage(prompt=PROMPT, style="chalk on a blackboard")).text


def test_size_follows_format_aspect_and_model(gen_project) -> None:
    gen = GenerateImage(prompt=PROMPT)
    assert image_request(gen_project(format={"width": 1080, "height": 1920}), gen).size == "1024x1536"
    assert image_request(gen_project(format={"width": 1080, "height": 1080}), gen).size == "1024x1024"
    assert image_request(gen_project(), GenerateImage(prompt=PROMPT, aspect="portrait")).size == "1024x1536"
    dalle = gen_project(imagegen={"model": "dall-e-3"})
    request = image_request(dalle, gen)
    assert (request.size, request.quality, request.estimated_cost) == ("1792x1024", "standard", pytest.approx(0.08))
    assert image_request(gen_project(imagegen={"size": "512x512", "model": "dall-e-2"}), gen).size == "512x512"
    assert image_request(gen_project(imagegen={"model": "my-model"}), gen).estimated_cost is None


def test_config_rejects_bad_imagegen(make_project) -> None:
    for bad in ({"provider": "midjourney"}, {"size": "big"}, {"modle": "x"}):
        with pytest.raises(VidgenError, match="imagegen"):
            Project.load(make_project(minimal_config(imagegen=bad)))


def test_cache_key_covers_what_changes_the_picture(gen_project) -> None:
    project = gen_project()
    base = GenerateImage(prompt=PROMPT, negative="people")
    key = image_request(project, base).key
    assert image_request(project, GenerateImage(prompt=f"  {PROMPT} ", negative="people")).key == key   # spacing only
    changed = [
        GenerateImage(prompt=PROMPT + " at night", negative="people"),
        GenerateImage(prompt=PROMPT, negative="birds"),
        GenerateImage(prompt=PROMPT, negative="people", seed=2),
        GenerateImage(prompt=PROMPT, negative="people", aspect="square"),
        GenerateImage(prompt=PROMPT, negative="people", style="photo"),
    ]
    keys = {image_request(project, g).key for g in changed}
    assert key not in keys and len(keys) == len(changed)
    for imagegen in ({"model": "dall-e-3"}, {"quality": "high"}, {"style": "photo"}, {"negative": "x"}):
        assert image_request(gen_project(imagegen=imagegen), base).key != key
    assert image_request(gen_project(format={"width": 1080, "height": 1920}), base).key != key


@pytest.mark.parametrize(
    ("prompt", "found"),
    [
        ('A shop sign that says "Open late"', "quotes text"),
        ("a poster with the title of the talk", "'title'"),
        ("a company logo on a mug", "'logo'"),
        ("a bar chart of sales", "chart"),
        ("a quiet street, no text, no logos", None),
        ("a desk without any lettering", None),
        ("a lighthouse on a cliff at dawn", None),
    ],
)
def test_text_in_prompt(prompt: str, found: str | None) -> None:
    reason = text_in_prompt(prompt)
    assert (reason is None) if found is None else (reason is not None and found in reason)


# ----- the image scene's params, validate and render warnings --------------------------------------


def test_image_params_need_path_or_generate() -> None:
    extensions.load_builtins()
    cls = registry.get("image").cls
    assert cls.validate_params({"generate": "a cat"}).generate.prompt == "a cat"
    with pytest.raises(ValidationError, match="path or generate is required"):
        cls.validate_params({"caption": "x"})
    with pytest.raises(ValidationError, match="not both"):
        cls.validate_params({"path": "a.png", "generate": "a cat"})


def test_scene_images_and_validate_warnings(gen_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = gen_project([image_scene({"prompt": PROMPT}), image_scene('a sign that says "Hi"', "sign"), {"id": "t", "type": "text_card", "params": {"text": "x"}, "duration": 1}])
    images = scene_images(project)
    assert [(i.scene_id, i.location) for i in images] == [("pic", "scenes[0].params.generate"), ("sign", "scenes[1].params.generate")]
    warnings = imagegen_warnings(project, images)
    assert warnings[0].startswith('scenes[1].params.generate.prompt: it quotes text ("Hi"); image generators render text poorly')
    assert warnings[1].startswith(f"generated images not made yet for pic ({images[0].request.key}.png), sign")
    assert main(["validate", str(project.root)]) == 0
    captured = capsys.readouterr()
    assert "run `vidgen imagegen`" in captured.err and "images:    0 generated, 2 missing" in captured.out
    for image in images:
        store(image.request)
    assert main(["validate", str(project.root)]) == 0
    captured = capsys.readouterr()
    assert "not made yet" not in captured.err and "images:    2 generated, 0 missing" in captured.out


def test_scene_types_without_params_model_and_extension_generate(gen_project) -> None:
    from conftest import write_files

    project = gen_project([
        {"id": "raw", "type": "raw_card", "params": {"anything": 1}, "duration": 1},
        {"id": "back", "type": "backdrop", "params": {"art": "a forest"}, "duration": 1},
    ])
    write_files(project.root, {"extensions/mine.py": """
        from vidgen.api import *

        @scene("raw_card")
        class RawCard(NarratedScene):
            def construct(self):
                self.wait(1)

        @scene("backdrop")
        class Backdrop(NarratedScene):
            class Params(SceneParams):
                art: GenerateImage

            def construct(self):
                self.wait(1)
    """})
    (image,) = scene_images(project)
    assert (image.scene_id, image.location, image.generate.prompt) == ("back", "scenes[1].params.art", "a forest")


def test_validate_lists_variant_images_that_differ(gen_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = gen_project(variants={"vertical": {"format": {"width": 1080, "height": 1920}}, "light": {"theme": {"preset": "light_academic"}}})
    assert main(["validate", str(project.root)]) == 0
    out = capsys.readouterr().out
    assert "images [vertical]: 0 generated, 1 missing" in out and "images [light]" not in out


def test_render_warns_about_missing_pictures(gen_project, caplog: pytest.LogCaptureFixture) -> None:
    from vidgen.render.pipeline import warn_images

    project = gen_project()
    with caplog.at_level(logging.WARNING, logger="vidgen"), extensions.project_session(project):
        warn_images(project)
    assert "generated image not made yet for pic; a placeholder is shown" in caplog.text


# ----- the OpenAI provider (mocked) ----------------------------------------------------------------


def test_provider_request_and_response(api: FakeAPI, gen_project) -> None:
    project = gen_project()
    request = image_request(project, GenerateImage(prompt=PROMPT))
    picture = provider().generate(request)
    sent = api.requests[0]
    assert sent.full_url == "https://api.openai.com/v1/images/generations" and sent.get_method() == "POST"
    assert sent.get_header("Authorization") == f"Bearer {KEY}" and sent.get_header("Content-type") == "application/json"
    assert api.body() == {"model": "gpt-image-1", "prompt": request.text, "n": 1, "size": "1536x1024", "quality": "medium"}
    assert picture.data.startswith(b"\x89PNG") and picture.revised_prompt == "a revised prompt"
    dalle = image_request(gen_project(imagegen={"model": "dall-e-2"}), GenerateImage(prompt=PROMPT))
    provider().generate(dalle)
    assert api.body() == {"model": "dall-e-2", "prompt": dalle.text, "n": 1, "size": "1024x1024", "response_format": "b64_json"}


def test_provider_converts_other_formats_and_rejects_bad_responses() -> None:
    picture = parse_response(api_body(png_bytes(fmt="JPEG"), revised=" "))
    assert picture.data.startswith(b"\x89PNG") and picture.revised_prompt is None
    for body in (b"{}", b"not json", json.dumps({"data": [{"b64_json": "!!"}]}).encode()):
        with pytest.raises(VidgenError, match="unreadable response"):
            parse_response(body)
    with pytest.raises(VidgenError, match="not a picture"):
        parse_response(api_body(b"hello"))


def test_rate_limit_is_retried_with_retry_after(api: FakeAPI, gen_project) -> None:
    api.responses = [http_error(429, '{"error": {"code": "rate_limit_exceeded"}}', {"Retry-After": "7"}), http_error(503, "busy")]
    sleeps: list[float] = []
    request = image_request(gen_project(), GenerateImage(prompt=PROMPT))
    assert provider(sleeps).generate(request).data.startswith(b"\x89PNG")
    assert sleeps == [7.0, 8.0] and len(api.requests) == 3   # Retry-After, then backoff 4 * 2**1


def test_timeouts_retried_then_given_up(api: FakeAPI, gen_project) -> None:
    request = image_request(gen_project(), GenerateImage(prompt=PROMPT))
    api.responses = [urllib.error.URLError(TimeoutError("timed out"))] * 4
    sleeps: list[float] = []
    with pytest.raises(VidgenError, match="cannot reach OpenAI: TimeoutError"):
        provider(sleeps).generate(request)
    assert sleeps == [4.0, 8.0, 16.0] and len(api.requests) == 4


def test_quota_and_client_errors_are_not_retried_and_hide_the_key(api: FakeAPI, gen_project) -> None:
    request = image_request(gen_project(), GenerateImage(prompt=PROMPT))
    api.responses = [http_error(429, '{"error": {"code": "insufficient_quota"}}')]
    with pytest.raises(VidgenError, match="OpenAI returned HTTP 429: .*insufficient_quota"):
        provider([]).generate(request)
    api.responses = [http_error(400, f'{{"error": {{"message": "rejected by the safety system", "key": "{KEY}"}}}}')]
    with pytest.raises(VidgenError) as info:
        provider([]).generate(request)
    assert "HTTP 400" in str(info.value) and "safety system" in str(info.value) and KEY not in str(info.value)
    assert len(api.requests) == 2


def test_missing_key(monkeypatch: pytest.MonkeyPatch, gen_project) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    calls: list[Any] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    project = gen_project()
    with pytest.raises(VidgenError, match=f"{API_KEY_ENV} is not set"):
        run_imagegen(project, out=lambda line: None)
    assert calls == [] and not (project.root / "assets" / "generated").exists()


# ----- vidgen imagegen ---------------------------------------------------------------------------


def test_dry_run_lists_prompts_and_cost_without_a_key(monkeypatch: pytest.MonkeyPatch, gen_project, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    project = gen_project([image_scene({"prompt": PROMPT}), image_scene({"prompt": PROMPT}, "again"), image_scene("a red door", "door")], imagegen={"style": "photo"})
    assert main(["imagegen", str(project.root), "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    first, door = scene_images(project)[0].request, scene_images(project)[2].request
    assert out[0] == f"would generate {first.key}.png for pic, again (1536x1024, gpt-image-1 medium, ~$0.063)"
    assert out[1] == f"    prompt: {first.text}" and f"Style: {STYLE_PRESETS['photo']}." in out[1]
    assert out[2].startswith(f"would generate {door.key}.png for door")
    assert out[-1].startswith("dry run: 2 picture(s) to generate, estimated $0.13 (OpenAI list prices")
    assert not (project.root / "assets" / "generated").exists()


def test_generate_store_skip_force_and_scene_filter(api: FakeAPI, gen_project) -> None:
    project = gen_project([image_scene({"prompt": PROMPT}), image_scene("a red door", "door")])
    lines: list[str] = []
    plan = run_imagegen(project, provider=provider(), out=lines.append)
    assert len(plan.todo) == 2 and len(api.requests) == 2
    request = scene_images(project)[0].request
    assert Image.open(request.path).format == "PNG"
    sidecar = json.loads(request.sidecar.read_text(encoding="utf-8"))
    assert sidecar["prompt"] == PROMPT and sidecar["sent_prompt"] == request.text and sidecar["revised_prompt"] == "a revised prompt"
    assert (sidecar["provider"], sidecar["model"], sidecar["size"], sidecar["scenes"]) == ("openai", "gpt-image-1", "1536x1024", ["pic"])
    assert len(sidecar["created"]) == 10 and KEY not in request.sidecar.read_text(encoding="utf-8")
    assert lines[0].startswith(f"[1/2] generated {request.key}.png for pic") and lines[-1].startswith("done: 2 picture(s) generated")
    # cached: nothing to do; --force and --scene make one again
    lines.clear()
    assert run_imagegen(project, provider=provider(), out=lines.append).todo == [] and lines == ["nothing to do: 2 picture(s) up to date in assets/generated/"]
    run_imagegen(project, provider=provider(), force=True, scene_ids=["door"], out=lines.append)
    assert len(api.requests) == 3 and api.body()["prompt"] == "a red door."
    with pytest.raises(VidgenError, match="unknown scene"):
        plan_imagegen(project, ["nope"])


def test_scene_without_generate_and_orphans(gen_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = gen_project([image_scene(PROMPT), {"id": "t", "type": "text_card", "params": {"text": "x"}, "duration": 1}])
    with pytest.raises(VidgenError, match="without a generate: param: t; scenes with one: pic"):
        plan_imagegen(project, ["t"])
    store(scene_images(project)[0].request)
    (project.root / "assets" / "generated" / "0123456789abcdef.png").write_bytes(png_bytes())
    assert main(["imagegen", str(project.root)]) == 0
    out = capsys.readouterr().out
    assert "no scene uses (not deleted): 0123456789abcdef.png" in out and "nothing to do: 1 picture(s)" in out


def test_variant_pictures_are_not_orphans(gen_project) -> None:
    project = gen_project(variants={"vertical": {"format": {"width": 1080, "height": 1920}}})
    vertical = Project.load(project.config_file, variant="vertical")
    for p in (project, vertical):
        store(scene_images(p)[0].request)
    assert plan_imagegen(project).orphans == [] and plan_imagegen(vertical).orphans == []


def test_error_midway_names_the_scene(api: FakeAPI, gen_project) -> None:
    project = gen_project([image_scene({"prompt": PROMPT}), image_scene("a red door", "door")])
    api.responses = [api_body(), http_error(400, "bad prompt")]
    with pytest.raises(VidgenError, match=r"picture for scene 'door': OpenAI returned HTTP 400: bad prompt\n\(1 of 2 done"):
        run_imagegen(project, provider=provider(), out=lambda line: None)
    assert scene_images(project)[0].request.exists and not scene_images(project)[1].request.exists


class StubProvider:
    name = "stub"

    def __init__(self) -> None:
        self.made: list[str] = []

    def check_credentials(self) -> None:
        return None

    def generate(self, request: ImageRequest) -> GeneratedPicture:
        self.made.append(request.key)
        return GeneratedPicture(png_bytes((30, 20)))


def test_provider_seam_accepts_any_provider(gen_project) -> None:
    project = gen_project()
    stub = StubProvider()
    run_imagegen(project, provider=stub, out=lambda line: None)
    assert stub.made == [scene_images(project)[0].request.key]


# ----- placeholders and the image scene -------------------------------------------------------------


def test_placeholder_card(gen_project) -> None:
    project = gen_project()
    request = image_request(project, GenerateImage(prompt=PROMPT, aspect="portrait"))
    theme = Theme()
    card = draw_placeholder(request, theme)
    assert card.size == (853, 1280)
    surface = tuple(int(theme.color("surface")[i : i + 2], 16) for i in (1, 3, 5))
    assert card.getpixel((2, 2)) == surface   # top edge of the gradient
    long_prompt = image_request(project, GenerateImage(prompt="word " * 400))
    assert draw_placeholder(long_prompt, theme).size == (1280, 853)
    path = placeholder_path(project, request, theme)
    assert path.parent == project.root / "build" / "imagegen" and path.is_file()
    mtime = path.stat().st_mtime_ns
    assert placeholder_path(project, request, theme) == path and path.stat().st_mtime_ns == mtime   # cached
    from vidgen.config import ThemeConfig

    assert placeholder_path(project, request, Theme(ThemeConfig(preset="light_academic"))) != path


def test_generated_image_is_the_picture_once_made(gen_project) -> None:
    project = gen_project()
    gen = GenerateImage(prompt=PROMPT)
    placeholder = generated_image(project, gen, Theme())
    assert "build" in placeholder.parts
    store(image_request(project, gen))
    assert generated_image(project, gen, Theme()) == image_request(project, gen).path


def test_fingerprint_follows_imagegen_and_the_picture(gen_project) -> None:
    from vidgen.render.fingerprint import scene_fingerprint

    project = gen_project()
    before = scene_fingerprint(project, "pic")
    store(scene_images(project)[0].request)
    made = scene_fingerprint(project, "pic")
    assert made != before
    styled = Project.load(project.root, variant=None)
    styled.config.imagegen.style = "photo"
    assert scene_fingerprint(styled, "pic") != made


def test_api_exports() -> None:
    from vidgen import api

    for name in ("GenerateImage", "generated_image"):
        assert name in api.__all__ and name in api.VIDGEN_NAMES and getattr(api, name).__doc__


@pytest.mark.render
def test_image_scene_renders_placeholder_then_picture(gen_project, tmp_path: Path) -> None:
    from test_builtin_scenes import render_scene

    project = gen_project([image_scene({"prompt": PROMPT}, caption="Caption", ken_burns=True), image_scene("a red door", "door", fit="cover")])
    media = tmp_path / "media"
    for scene_id in ("pic", "door"):
        scene, duration, _ = render_scene(project, scene_id, media, 160, 90)
        assert duration > 0 and scene.mobjects == []
    assert len(list((project.root / "build" / "imagegen").glob("*.png"))) == 2
    store(scene_images(project)[0].request, png_bytes((60, 40), (250, 0, 0)))
    scene, _, _ = render_scene(project, "pic", media, 90, 160)
    assert scene.beat_log
