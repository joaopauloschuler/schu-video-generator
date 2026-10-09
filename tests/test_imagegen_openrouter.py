"""OpenRouter image provider (Step 61): config, requests and cache keys, the request body, the
provider with a mocked urlopen (success, errors, retried rate limits), prices from the public
model records (real samples in tests/data, fetched 2026-10-08), `vidgen imagegen` dry runs (human
and JSON, online and offline) and real runs. No network: OpenRouter is never called."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from conftest import minimal_config
from test_imagegen import PROMPT, FakeResponse, http_error, image_scene, png_bytes
from vidgen.cli import main
from vidgen.config import ImagegenConfig
from vidgen.errors import VidgenError
from vidgen.imagegen import GenerateImage, image_request, request_key, scene_images
from vidgen.imagegen import openrouter as orr
from vidgen.imagegen.run import price_plan, run_imagegen
from vidgen.project import Project

KEY = "sk-or-test-secret-456"
RECORDS: dict[str, Any] = json.loads((Path(__file__).parent / "data" / "openrouter_endpoints.json").read_text(encoding="utf-8"))["records"]
SEEDREAM = "bytedance-seed/seedream-4.5"     # $0.04 per image, seed, resolution 1K/2K/4K, no quality
FLUX = "black-forest-labs/flux.2-klein-4b"   # $0.014 per megapixel, seed, output_format png/jpeg
GPT2 = "openai/gpt-image-2"                  # per token, quality, no seed
MINI = "openai/gpt-image-1-mini"             # aspect ratios 1:1, 3:2, 2:3 only
VECTOR = "recraft/recraft-v4.1-vector"       # SVG only
LAYER = "inclusionai/ming-image-0.1-design-layer"   # needs an input picture


def router_body(data: bytes | None = None, media_type: str | None = "image/png", cost: float | None = 0.04) -> bytes:
    item: dict[str, Any] = {"b64_json": base64.b64encode(data if data is not None else png_bytes()).decode()}
    if media_type is not None:
        item["media_type"] = media_type
    doc: dict[str, Any] = {"created": 1748372400, "data": [item]}
    if cost is not None:
        doc["usage"] = {"prompt_tokens": 0, "completion_tokens": 4175, "total_tokens": 4175, "cost": cost}
    return json.dumps(doc).encode()


class FakeRouter:
    """Replaces urlopen: GETs of model records come from ``records`` (404 for others, or
    ``offline``); POSTs use ``responses`` in order (exceptions or bodies), then a PNG."""

    def __init__(self) -> None:
        self.records = dict(RECORDS)
        self.responses: list[Any] = []
        self.offline = False
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        if request.get_method() == "GET":
            if self.offline:
                raise urllib.error.URLError(TimeoutError("timed out"))
            model = request.full_url.removeprefix(f"{orr.API_BASE}/images/models/").removesuffix("/endpoints")
            if model not in self.records:
                raise http_error(404, json.dumps({"error": {"message": f'No image model found for "{model}"', "code": 404}}))
            return FakeResponse(json.dumps(self.records[model]).encode())
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return FakeResponse(item)
        return FakeResponse(router_body())

    @property
    def posts(self) -> list[urllib.request.Request]:
        return [r for r in self.requests if r.get_method() == "POST"]

    @property
    def gets(self) -> list[urllib.request.Request]:
        return [r for r in self.requests if r.get_method() == "GET"]

    def body(self, k: int = -1) -> dict[str, Any]:
        return json.loads(self.posts[k].data.decode())


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> FakeRouter:
    fake = FakeRouter()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv(orr.API_KEY_ENV, KEY)
    return fake


@pytest.fixture
def or_project(make_project):
    def make(scenes: list[dict[str, Any]] | None = None, imagegen: dict[str, Any] | None = None, **overrides: Any) -> Project:
        scenes = scenes if scenes is not None else [image_scene({"prompt": PROMPT, "negative": "people"})]
        settings = {"provider": "openrouter", "model": SEEDREAM, **(imagegen or {})}
        return Project.load(make_project(minimal_config(scenes=scenes, imagegen=settings, **overrides)))

    return make


def provider(sleeps: list[float] | None = None) -> orr.OpenRouterImageProvider:
    return orr.OpenRouterImageProvider(sleep=(sleeps.append if sleeps is not None else lambda s: None))


def info(model: str) -> orr.ModelInfo:
    return orr.ModelInfo(model, tuple(RECORDS[model]["endpoints"]))


# ----- config and requests ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("imagegen", "message"),
    [
        ({"provider": "openrouter"}, "provider openrouter needs a model"),
        ({"provider": "openrouter", "model": "seedream"}, "look like author/name"),
        ({"provider": "openrouter", "model": SEEDREAM, "quality": "hd"}, "not an OpenRouter quality"),
        ({"provider": "openrouter", "model": SEEDREAM, "size": "1024x1024", "resolution": "2K"}, "not both"),
        ({"resolution": "1K"}, "resolution is an openrouter option"),
        ({"provider": "replicate", "model": "a/b"}, "openrouter"),
    ],
)
def test_config_errors(make_project, imagegen: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        Project.load(make_project(minimal_config(imagegen=imagegen)))


def test_validate_reports_missing_model(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(imagegen={"provider": "openrouter"}))
    assert main(["validate", str(root)]) != 0
    assert "imagegen" in capsys.readouterr().err


def test_schema_lists_the_provider_and_resolution() -> None:
    props = ImagegenConfig.model_json_schema()["properties"]
    assert "openrouter" in json.dumps(props["provider"]) and "OPENROUTER_API_KEY" in props["provider"]["description"]
    assert "2K" in json.dumps(props["resolution"])


def test_openai_keys_are_unchanged(make_project) -> None:
    # pinned before Step 61: existing OpenAI pictures keep their file names
    assert request_key("openai", "gpt-image-1", "1536x1024", "medium", None, "a cat.") == "834a61963bcbaf9e"
    assert request_key("openai", "dall-e-3", "1024x1792", "hd", 7, "A lighthouse. Style: x. Avoid: y.") == "c4b5118c19763cf5"
    project = Project.load(make_project(minimal_config(scenes=[image_scene("a cat")])))
    request = image_request(project, GenerateImage(prompt="a cat"))
    assert (request.key, request.explicit_size, request.aspect_ratio, request.shape) == ("834a61963bcbaf9e", True, None, "1536x1024")


def test_openrouter_request_shapes_and_keys(or_project) -> None:
    gen = GenerateImage(prompt=PROMPT)
    request = image_request(or_project(), gen)
    assert (request.provider, request.model, request.aspect_ratio, request.resolution, request.quality) == ("openrouter", SEEDREAM, "16:9", None, None)
    assert (request.size, request.explicit_size, request.shape, request.estimated_cost) == ("1024x576", False, "16:9", None)
    assert image_request(or_project(format={"width": 1080, "height": 1920}), gen).aspect_ratio == "9:16"
    assert image_request(or_project(format={"width": 1080, "height": 1080}), gen).aspect_ratio == "1:1"
    assert image_request(or_project(format={"width": 1440, "height": 1080}), gen).aspect_ratio == "4:3"
    assert image_request(or_project(), GenerateImage(prompt=PROMPT, aspect="portrait")).aspect_ratio == "9:16"
    tiered = image_request(or_project(imagegen={"resolution": "2K"}), gen)
    assert (tiered.size, tiered.shape) == ("2048x1152", "16:9, 2K")
    explicit = image_request(or_project(imagegen={"size": "1024x1024"}), gen)
    assert (explicit.explicit_size, explicit.aspect_ratio, explicit.shape) == (True, None, "1024x1024")
    keys = {r.key for r in (request, tiered, explicit, image_request(or_project(imagegen={"model": FLUX}), gen))}
    assert len(keys) == 4
    assert image_request(or_project(), gen).key == request.key   # stable


def test_request_body(or_project) -> None:
    project = or_project(imagegen={"quality": "high", "resolution": "2K"})
    seeded = image_request(project, GenerateImage(prompt=PROMPT, seed=5))
    body = orr.request_body(seeded)
    assert body == {"model": SEEDREAM, "prompt": seeded.text, "n": 1, "aspect_ratio": "16:9", "resolution": "2K", "quality": "high", "seed": 5}
    assert "seed" not in orr.request_body(seeded, info(GPT2))     # the model takes no seed
    assert orr.request_body(seeded, info(FLUX))["output_format"] == "png"
    explicit = image_request(or_project(imagegen={"size": "1024x1024"}), GenerateImage(prompt=PROMPT))
    assert orr.request_body(explicit) == {"model": SEEDREAM, "prompt": explicit.text, "n": 1, "size": "1024x1024"}


# ----- the provider (mocked) ---------------------------------------------------------------------------


def test_provider_request_headers_and_response(router: FakeRouter, or_project) -> None:
    request = image_request(or_project(), GenerateImage(prompt=PROMPT))
    router.responses = [router_body(png_bytes(fmt="JPEG"), media_type="image/jpeg", cost=0.04)]
    picture = provider().generate(request)
    sent = router.posts[0]
    assert sent.full_url == "https://openrouter.ai/api/v1/images" and sent.get_method() == "POST"
    assert sent.get_header("Authorization") == f"Bearer {KEY}" and sent.get_header("Content-type") == "application/json"
    assert sent.get_header("Http-referer") == orr.APP_URL and sent.get_header("X-openrouter-title") == "schu-video-generator"
    assert router.gets[0].full_url == f"{orr.API_BASE}/images/models/bytedance-seed/seedream-4.5/endpoints"
    assert router.gets[0].get_header("Authorization") is None   # the free lookup sends no key
    assert router.body() == {"model": SEEDREAM, "prompt": request.text, "n": 1, "aspect_ratio": "16:9"}
    assert picture.data.startswith(b"\x89PNG") and picture.cost == 0.04 and picture.revised_prompt is None


def test_responses_without_a_picture_or_with_svg() -> None:
    for body in (b"{}", b"not json", json.dumps({"data": [{"b64_json": "!!"}]}).encode(), json.dumps({"data": []}).encode()):
        with pytest.raises(VidgenError, match="OpenRouter returned an unreadable response"):
            orr.parse_response(body)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>'
    for media in ("image/svg+xml", None):
        with pytest.raises(VidgenError, match="vector \\(SVG\\)"):
            orr.parse_response(router_body(svg, media_type=media))
    with pytest.raises(VidgenError, match="OpenRouter returned data that is not a picture"):
        orr.parse_response(router_body(b"hello"))
    raw = orr.decode_response(router_body(cost=None))
    assert (raw.media_type, raw.cost) == ("image/png", None)


def test_rate_limit_and_overload_are_retried(router: FakeRouter, or_project) -> None:
    router.responses = [http_error(429, '{"error": {"code": 429, "message": "Rate limit exceeded"}}', {"Retry-After": "3"}), http_error(529, "overloaded")]
    sleeps: list[float] = []
    request = image_request(or_project(), GenerateImage(prompt=PROMPT))
    assert provider(sleeps).generate(request).data.startswith(b"\x89PNG")
    assert sleeps == [3.0, 8.0] and len(router.posts) == 3


def test_credit_and_client_errors_are_not_retried_and_hide_the_key(router: FakeRouter, or_project) -> None:
    request = image_request(or_project(), GenerateImage(prompt=PROMPT))
    router.responses = [http_error(402, '{"error": {"code": 402, "message": "Insufficient credits. Add more using https://openrouter.ai/credits"}}')]
    with pytest.raises(VidgenError, match="OpenRouter returned HTTP 402: .*Insufficient credits"):
        provider([]).generate(request)
    router.responses = [http_error(400, f'{{"error": {{"message": "bad aspect", "key": "{KEY}"}}}}')]
    with pytest.raises(VidgenError) as err:
        provider([]).generate(request)
    assert "HTTP 400" in str(err.value) and KEY not in str(err.value) and len(router.posts) == 2


def test_missing_key(monkeypatch: pytest.MonkeyPatch, or_project) -> None:
    monkeypatch.delenv(orr.API_KEY_ENV, raising=False)
    calls: list[Any] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    project = or_project()
    with pytest.raises(VidgenError, match=r"OPENROUTER_API_KEY is not set(.|\n)*setx OPENROUTER_API_KEY(.|\n)*export OPENROUTER_API_KEY"):
        run_imagegen(project, out=lambda line: None)
    assert calls == [] and not (project.root / "assets" / "generated").exists()


# ----- model records and prices ------------------------------------------------------------------------


def test_quotes_per_image_megapixel_token_and_free(or_project) -> None:
    request = image_request(or_project(), GenerateImage(prompt=PROMPT))
    q = orr.quote(request, info(SEEDREAM))
    assert q.cost == pytest.approx(0.04) and q.basis == "OpenRouter: $0.04 per image"
    flux = image_request(or_project(imagegen={"model": FLUX}), GenerateImage(prompt=PROMPT))
    q = orr.quote(flux, info(FLUX))
    assert q.cost == pytest.approx(0.014 * 1024 * 576 / 1e6) and "per megapixel x 0.59 MP (nominal 1024x576)" in q.basis
    q = orr.quote(request, info(GPT2))
    assert q.cost is None and q.basis.startswith("price unknown: OpenRouter lists $0.00003 per output token") and "not listed" in q.basis
    assert orr.quote(request, info(LAYER)).cost == 0.0
    q = orr.quote(request, orr.LookupFailure("OpenRouter's model list could not be reached (timed out)"))
    assert q.cost is None and q.basis.startswith("price unknown: OpenRouter's model list could not be reached")


def test_quotes_pick_the_resolution_tier_and_the_highest_provider(or_project) -> None:
    tiered = {"pricing": [
        {"billable": "output_image", "unit": "image", "cost_usd": 0.03, "variant": "1k"},
        {"billable": "output_image", "unit": "image", "cost_usd": 0.06, "variant": "2k"},
        {"billable": "input_image", "unit": "image", "cost_usd": 0.5},
    ]}
    model = orr.ModelInfo("a/b", (tiered,))
    two_k = image_request(or_project(imagegen={"resolution": "2K"}), GenerateImage(prompt=PROMPT))
    assert orr.quote(two_k, model).cost == pytest.approx(0.06) and "(2k)" in orr.quote(two_k, model).basis
    default = image_request(or_project(), GenerateImage(prompt=PROMPT))
    assert orr.quote(default, model).cost == pytest.approx(0.06)   # no tier asked: the highest
    cheap = {"pricing": [{"billable": "output_image", "unit": "image", "cost_usd": 0.02}]}
    both = orr.quote(default, orr.ModelInfo("a/b", (cheap, tiered)))
    assert both.cost == pytest.approx(0.06) and "the highest of 2 providers" in both.basis


def test_lookup_stops_when_offline() -> None:
    calls: list[str] = []

    def fetch(model: str, timeout: float) -> orr.Lookup:
        calls.append(model)
        return orr.LookupFailure("cannot reach") if model == "a/one" else orr.ModelInfo(model, ())

    found = orr.lookup_models(["a/one", "a/two", "a/one"], fetch=fetch)
    assert calls == ["a/one"] and found["a/two"] == found["a/one"]


def test_fetch_model_info(router: FakeRouter) -> None:
    assert isinstance(orr.fetch_model_info(SEEDREAM), orr.ModelInfo)
    missing = orr.fetch_model_info("nobody/no-such-model")
    assert isinstance(missing, orr.LookupFailure) and missing.missing and "no image model" in missing.reason
    router.offline = True
    offline = orr.fetch_model_info(SEEDREAM)
    assert isinstance(offline, orr.LookupFailure) and not offline.missing and "TimeoutError" in offline.reason


def test_check_request_problems_and_notes(or_project) -> None:
    project = or_project(imagegen={"quality": "high", "resolution": "4K"})
    request = image_request(project, GenerateImage(prompt=PROMPT, seed=3))
    seedream = orr.check_request(request, info(SEEDREAM))
    assert seedream.problems == [f"{SEEDREAM} has no quality setting: remove imagegen.quality (high)"] and seedream.notes == []
    gpt2 = orr.check_request(request, info(GPT2))
    assert any("has no resolution setting" in p for p in gpt2.problems)
    assert gpt2.notes == [f"{GPT2} takes no seed: the seed only names another picture (not sent)"]
    plain = image_request(or_project(), GenerateImage(prompt=PROMPT))
    assert "no 16:9 ratio (1:1, 3:2, 2:3): the provider picks its nearest" in orr.check_request(plain, info(MINI)).notes[0]
    assert "vector (SVG)" in orr.check_request(plain, info(VECTOR)).problems[0]
    assert "edits an input picture" in orr.check_request(plain, info(LAYER)).problems[0]
    bad_tier = image_request(or_project(imagegen={"resolution": "512"}), GenerateImage(prompt=PROMPT))
    assert orr.check_request(bad_tier, info(SEEDREAM)).problems == [f"{SEEDREAM} takes resolution 1K, 2K, 4K, not 512 (imagegen.resolution)"]


# ----- vidgen imagegen ---------------------------------------------------------------------------------


def test_dry_run_with_prices(router: FakeRouter, monkeypatch: pytest.MonkeyPatch, or_project, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(orr.API_KEY_ENV, raising=False)
    project = or_project([image_scene({"prompt": PROMPT}), image_scene("a red door", "door")])
    assert main(["imagegen", str(project.root), "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    first = scene_images(project)[0].request
    assert out[0] == f"would generate {first.key}.png for pic (16:9, openrouter {SEEDREAM}, ~$0.040)"
    assert out[1] == "    price: OpenRouter: $0.04 per image" and out[2] == f"    prompt: {first.text}"
    assert out[-1].startswith("dry run: 2 picture(s) to generate, estimated $0.080 (OpenRouter prices of 20")
    assert router.posts == [] and len(router.gets) == 1   # one free lookup per model, no paid call
    for request in router.gets:
        assert request.get_header("Authorization") is None


def test_dry_run_offline_says_price_unknown(router: FakeRouter, or_project, capsys: pytest.CaptureFixture[str]) -> None:
    router.offline = True
    project = or_project()
    assert main(["imagegen", str(project.root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "price unknown)" in out and "price: price unknown: OpenRouter's model list could not be reached" in out
    assert "estimated $0.00 + 1 of unknown price (OpenRouter prices unknown (its model list could not be reached))" in out


def test_dry_run_json(router: FakeRouter, or_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = or_project(imagegen={"model": MINI, "quality": "low"}, scenes=[image_scene({"prompt": PROMPT, "seed": 2})])
    assert main(["imagegen", str(project.root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    (image,) = doc["images"]
    assert (image["provider"], image["model"], image["aspect_ratio"], image["resolution"], image["quality"]) == ("openrouter", MINI, "16:9", None, "low")
    assert image["estimated_cost"] is None and image["price_basis"].startswith("price unknown: OpenRouter lists $0.000008 per output token")
    assert image["problems"] == [] and "no 16:9 ratio" in image["notes"][0] and "takes no seed" in image["notes"][1]
    assert doc["unknown_cost"] == 1 and doc["price_note"].startswith("OpenRouter prices of ") and doc["charged"] is None


def test_dry_run_flags_what_a_run_would_refuse(router: FakeRouter, or_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = or_project(imagegen={"model": "nobody/no-such-model"})
    assert main(["imagegen", str(project.root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "    problem: OpenRouter has no image model 'nobody/no-such-model'" in out and "1 would be refused" in out


def test_real_run_stores_png_sidecar_and_cost(router: FakeRouter, or_project) -> None:
    project = or_project([image_scene({"prompt": PROMPT}), image_scene("a red door", "door")], imagegen={"resolution": "2K"})
    router.responses = [router_body(cost=0.04), router_body(png_bytes(fmt="WEBP"), media_type="image/webp", cost=0.04)]
    lines: list[str] = []
    plan = run_imagegen(project, provider=provider(), out=lines.append)
    assert len(router.posts) == 2 and len(router.gets) == 1 and plan.charged == pytest.approx(0.08)
    request = scene_images(project)[1].request
    assert request.path.read_bytes().startswith(b"\x89PNG")
    sidecar = json.loads(request.sidecar.read_text(encoding="utf-8"))
    assert (sidecar["provider"], sidecar["model"], sidecar["aspect_ratio"], sidecar["resolution"], sidecar["size"]) == ("openrouter", SEEDREAM, "16:9", "2K", None)
    assert sidecar["cost_usd"] == 0.04 and sidecar["key"] == request.key and KEY not in request.sidecar.read_text(encoding="utf-8")
    assert lines[0].endswith(", $0.040)") and lines[-1].startswith("done: 2 picture(s) generated ($0.080 charged by openrouter)")
    assert run_imagegen(project, provider=provider(), out=lines.append).todo == []   # cached


def test_real_run_refuses_before_paying(router: FakeRouter, or_project) -> None:
    for imagegen, message in (({"model": "nobody/no-such-model"}, "no image model"), ({"quality": "high"}, "has no quality setting")):
        project = or_project(imagegen=imagegen)
        with pytest.raises(VidgenError, match=f"cannot generate with these settings:\n  .*{message}"):
            run_imagegen(project, provider=provider(), out=lambda line: None)
    assert router.posts == []


def test_real_run_offline_lookup_does_not_block(router: FakeRouter, or_project, monkeypatch: pytest.MonkeyPatch) -> None:
    project = or_project([image_scene({"prompt": PROMPT, "seed": 9})])
    calls: list[str] = []

    def offline(model: str, timeout: float) -> orr.Lookup:
        calls.append(model)
        return orr.LookupFailure("cannot reach")

    router.responses = [router_body(cost=None)]
    lines: list[str] = []
    run_imagegen(project, provider=orr.OpenRouterImageProvider(sleep=lambda s: None, fetch=offline), out=lines.append)
    assert calls == [SEEDREAM] and router.body()["seed"] == 9   # sent as asked: nothing known about the model
    assert "cost not reported by openrouter" in lines[-1]


def test_get_image_provider_and_price_plan_mixing(or_project) -> None:
    from vidgen.imagegen import get_image_provider

    project = or_project()
    assert get_image_provider(project).name == "openrouter"
    from vidgen.imagegen.run import plan_imagegen

    plan = price_plan(plan_imagegen(project), lookup=lambda models: {m: info(SEEDREAM) for m in models})
    assert plan.cost == (pytest.approx(0.04), 0) and plan.price_note.startswith("OpenRouter prices of ")
