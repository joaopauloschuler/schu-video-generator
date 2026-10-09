"""Vector (SVG) generated images (Step 61b): the SVG sanitiser, `generate: {format: svg}` requests,
keys and storage, the OpenRouter SVG path and the data-policy (ZDR) error with a mocked urlopen,
loading as shapes (recolor, strokes, draw), the layout dump and image scene renders at tiny
resolution. The test picture `tests/data/vector_hills.svg` is hand-written for these tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from manim import DrawBorderThenFill
from pydantic import ValidationError

from conftest import minimal_config
from test_imagegen import PROMPT, FakeResponse, http_error, image_scene
from test_imagegen_openrouter import KEY, SEEDREAM, VECTOR, FakeRouter, info, router_body
from test_introspect import FakeScene, objects, small_config  # noqa: F401 - fixture
from vidgen.cli import main
from vidgen.errors import VidgenError
from vidgen.imagegen import GenerateImage, image_request, imagegen_warnings, orphaned_images, scene_images
from vidgen.imagegen import openrouter as orr
from vidgen.imagegen.run import run_imagegen
from vidgen.project import Project
from vidgen.svgclean import MAX_SHAPES, sanitize_svg, theme_color
from vidgen.theme import Theme

HILLS = Path(__file__).parent / "data" / "vector_hills.svg"
SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">'
POLICY_404 = (
    '{"error":{"message":"No endpoints available matching your guardrail restrictions and data policy. 0 endpoints: '
    'ZDR violation (account settings). Configurable at https://openrouter.ai/settings/privacy","code":404}}'
)


def svg(body: str) -> bytes:
    return f"{SVG_HEAD}{body}</svg>".encode()


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> FakeRouter:
    fake = FakeRouter()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setenv(orr.API_KEY_ENV, KEY)
    return fake


@pytest.fixture
def svg_project(make_project):
    def make(scenes: list[dict[str, Any]] | None = None, imagegen: dict[str, Any] | None = None, **overrides: Any) -> Project:
        scenes = scenes if scenes is not None else [image_scene({"prompt": PROMPT, "format": "svg"})]
        settings = {"provider": "openrouter", "model": SEEDREAM, "svg_model": VECTOR, **(imagegen or {})}
        return Project.load(make_project(minimal_config(scenes=scenes, imagegen=settings, **overrides)))

    return make


def provider(**kwargs: Any) -> orr.OpenRouterImageProvider:
    return orr.OpenRouterImageProvider(sleep=lambda s: None, **kwargs)


# ----- the sanitiser -----------------------------------------------------------------------------------


def test_fixture_is_cleaned_and_boxed() -> None:
    clean = sanitize_svg(HILLS.read_bytes(), where="hills.svg")
    assert (clean.view_box, clean.shapes, clean.notes) == ((0.0, 0.0, 160.0, 90.0), 7, ())
    assert clean.warnings == ("hills.svg: 1 gradient / pattern fill(s) flattened to one colour",)
    text = clean.data.decode()
    assert 'fill="#5E9CD2"' in text and "url(" not in text and "linearGradient" not in text   # average of #2B6CB0, #90CDF4
    assert text.index('<rect x="0.0" y="0.0" width="160.0" height="90.0"') < text.index("<circle")   # the box comes first
    assert "stroke:none;stroke-width:0" in text   # Manim draws stroke:none white otherwise


def test_unsafe_and_unsupported_parts_are_removed() -> None:
    data = svg(
        '<script>alert(1)</script><foreignObject><div>x</div></foreignObject>'
        '<image href="data:image/png;base64,AAAA" width="10" height="10"/>'
        '<defs><filter id="blur"><feGaussianBlur stdDeviation="3"/></filter>'
        '<radialGradient id="r"><stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/></radialGradient>'
        '<linearGradient id="l" xlink:href="#r"/><pattern id="p"><rect width="2" height="2" fill="#00ff00"/></pattern>'
        '<clipPath id="c"><rect width="5" height="5"/></clipPath></defs>'
        '<rect width="100" height="100" fill="url(#l)" filter="url(#blur)" onload="steal()" clip-path="url(#c)"/>'
        '<circle cx="50" cy="50" r="20" style="fill:url(#p);filter:url(#blur)" mask="url(#m)"/>'
        '<path d="M0 0 L 10 10" stroke="url(#missing)"/>'
        '<text x="10" y="10">Hello</text><use href="other.svg#x"/><a href="https://example.com"><rect width="3" height="3"/></a>'
        '<animate attributeName="x" from="0" to="9"/>'
    )
    clean = sanitize_svg(data, where="bad.svg")
    text = clean.data.decode()
    for gone in ("script", "foreignObject", "<image", "filter", "onload", "clip", "mask", "Hello", "other.svg", "example.com", "animate", "url("):
        assert gone not in text, gone
    assert 'fill="#800080"' in text and "fill:#00FF00" in text and 'stroke="#888888"' in text   # averaged, pattern, unknown
    messages = "\n".join(clean.warnings)
    for what in ("scripts removed", "embedded HTML", "embedded raster pictures removed", "filters (blur, shadows) removed",
                 "clip paths removed (shapes they hid may show)", "masks removed", "its text was removed", "links to other files removed",
                 "3 gradient / pattern fill(s) flattened"):
        assert what in messages, what
    assert clean.shapes == 4   # rect, circle, path, the linked rect (kept, the link dropped)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "x">]><svg/>', "declares XML entities"),
        (b"<html><body/></html>", "not an SVG file"),
        (b"<svg", "not a readable SVG"),
        (svg('<text x="1" y="1">only words</text>'), "draws nothing vidgen can show"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>', "give the <svg> a viewBox"),
    ],
)
def test_unusable_svgs_are_refused(data: bytes, message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        sanitize_svg(data, where="x.svg")


def test_huge_svgs_are_capped_and_simplified() -> None:
    tiny = "".join(f'<rect x="{i % 50}" y="{i // 50}" width="0.5" height="0.5" fill="#123456"/>' for i in range(MAX_SHAPES + 200))
    data = svg('<rect width="100" height="100" fill="#ffffff"/>' + tiny)
    capped = sanitize_svg(data, where="big.svg")
    assert capped.shapes == MAX_SHAPES and "1701 shapes, more than the 1500 vidgen draws: the 201 smallest were dropped" in capped.warnings[0]
    assert 'fill="#ffffff"' in capped.data.decode()   # the big background stays
    simple = sanitize_svg(data, where="big.svg", simplify=True)
    assert simple.shapes == 1 and simple.warnings == () and "simplify dropped 1700 shape(s) smaller than 0.05% of the picture" in simple.notes[0]
    wiggle = "M0 0 " + " ".join(f"L {i % 100} {(i * 7) % 100}" for i in range(400)) + " Z"
    thinned = sanitize_svg(svg(f'<path d="{wiggle}" fill="#ff0000"/>'), where="w.svg", max_segments=100)
    assert thinned.segments <= 100 and "401 curve segments, more than the 100 vidgen draws: paths keep 1 point in 5" in thinned.warnings[0]


def test_theme_colors_keep_lightness() -> None:
    theme = Theme()
    colors = theme.colors
    assert theme_color("#FFFFFF", theme) == colors["text"] and theme_color("#101010", theme) == theme.background
    assert theme_color("#808080", theme) == colors["dim"]
    red_dark, red_light = theme_color("#8B0000", theme), theme_color("#FF9090", theme)
    assert red_dark != red_light and red_dark.startswith("#") and int(red_dark[1:3], 16) < int(red_light[1:3], 16)
    assert theme_color("none", theme) == "none"


# ----- requests, keys, validation ----------------------------------------------------------------------


def test_svg_requests_keys_and_paths(svg_project) -> None:
    project = svg_project()
    vector = image_request(project, GenerateImage(prompt=PROMPT, format="svg"))
    raster = image_request(project, GenerateImage(prompt=PROMPT))
    assert (vector.model, vector.format, vector.path.name, vector.quality, vector.resolution) == (VECTOR, "svg", f"{vector.key}.svg", None, None)
    assert (vector.aspect_ratio, vector.size, vector.shape, vector.explicit_size) == ("16:9", "1024x576", "16:9, SVG", False)
    assert (raster.model, raster.path.suffix) == (SEEDREAM, ".png") and raster.key != vector.key
    # the png key is the one Step 61 gave (format is only in svg keys)
    plain = svg_project(imagegen={"svg_model": None})
    assert image_request(plain, GenerateImage(prompt=PROMPT)).key == raster.key
    tiered = svg_project(imagegen={"resolution": "2K", "quality": "high"})
    assert image_request(tiered, GenerateImage(prompt=PROMPT, format="svg")).key == vector.key   # vectors have no tier


@pytest.mark.parametrize(
    ("imagegen", "message"),
    [
        ({"svg_model": VECTOR}, "svg_model is an openrouter option"),
        ({"provider": "openrouter", "model": SEEDREAM, "svg_model": "recraft"}, "look like author/name"),
    ],
)
def test_svg_model_config_errors(make_project, imagegen: dict[str, Any], message: str) -> None:
    with pytest.raises(VidgenError, match=message):
        Project.load(make_project(minimal_config(imagegen=imagegen)))


def test_vector_params_need_a_vector_picture(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    from vidgen.scenes.image import Image

    with pytest.raises(ValidationError, match="draw, recolor work on vector pictures only"):
        Image.Params.model_validate({"path": "a.png", "draw": True, "recolor": "theme"})
    assert Image.Params.model_validate({"path": "a.svg", "draw": True, "simplify": 0.2}).vector()
    assert Image.Params.model_validate({"generate": {"prompt": "x", "format": "svg"}, "recolor": "theme"}).vector()
    with pytest.raises(ValidationError):
        Image.Params.model_validate({"path": "a.svg", "simplify": 9})
    root = make_project(minimal_config(scenes=[image_scene({"prompt": PROMPT, "format": "svg"})]))
    assert main(["validate", str(root)]) != 0
    assert "generate.format: svg needs imagegen.provider: openrouter" in capsys.readouterr().err


def test_validate_warns_about_svg_models(svg_project) -> None:
    unknown = svg_project(imagegen={"svg_model": None})
    warnings = imagegen_warnings(unknown)
    assert any(f"format: svg with {SEEDREAM}, which is not known to make SVG pictures" in w and "recraft/recraft-v4.1-vector ($0.08)" in w for w in warnings)
    only_svg = svg_project([image_scene(PROMPT)], imagegen={"model": VECTOR, "svg_model": None})
    assert any(f"{VECTOR} makes only SVG pictures: add format: svg" in w for w in imagegen_warnings(only_svg))
    good = svg_project()
    assert not any("SVG" in w for w in imagegen_warnings(good))


def test_validate_reports_what_loading_a_stored_svg_removes(svg_project) -> None:
    project = svg_project([image_scene({"prompt": PROMPT, "format": "svg"}, simplify=True)])
    request = scene_images(project)[0].request
    request.path.parent.mkdir(parents=True)
    request.path.write_bytes(svg('<rect width="100" height="100" fill="#fff"/><text>Hi</text>'))
    warnings = imagegen_warnings(project)
    assert any("its text was removed" in w and request.path.name in w for w in warnings)
    assert not any("not made yet" in w for w in warnings)
    assert orphaned_images(project, set()) == [request.path]


def test_svg_check_request_and_body(svg_project) -> None:
    project = svg_project()
    vector = image_request(project, GenerateImage(prompt=PROMPT, format="svg", seed=4))
    assert orr.check_request(vector, info(VECTOR)).problems == []
    # no seed: Recraft lists none; no quality / resolution: vectors have none
    assert orr.request_body(vector, info(VECTOR)) == {"model": VECTOR, "prompt": vector.text, "n": 1, "aspect_ratio": "16:9", "output_format": "svg"}
    wrong = orr.check_request(vector, info(SEEDREAM)).problems
    assert wrong and f"{SEEDREAM} makes no SVG pictures (format: svg)" in wrong[0] and "set imagegen.svg_model" in wrong[0]
    png = image_request(project, GenerateImage(prompt=PROMPT))
    assert "add format: svg" in orr.check_request(png, info(VECTOR)).problems[0]


# ----- generating (mocked) ------------------------------------------------------------------------------


def test_svg_response_parsing() -> None:
    data = HILLS.read_bytes()
    picture = orr.parse_response(router_body(data, media_type="image/svg+xml", cost=0.08), "svg")
    assert picture.data == data and picture.cost == 0.08
    with pytest.raises(VidgenError, match="returned a raster picture \\(image/png\\) though SVG was asked for"):
        orr.parse_response(router_body(), "svg")
    with pytest.raises(VidgenError, match="draws nothing"):
        orr.parse_response(router_body(svg("<text>x</text>"), media_type="image/svg+xml"), "svg")
    with pytest.raises(VidgenError, match="add format: svg to the generate:"):
        orr.parse_response(router_body(data, media_type="image/svg+xml"))


def test_dry_run_and_run_store_the_svg(router: FakeRouter, svg_project, capsys: pytest.CaptureFixture[str]) -> None:
    project = svg_project([image_scene({"prompt": PROMPT, "format": "svg"}), image_scene("a red door", "door")])
    vector, raster = (i.request for i in scene_images(project))
    assert main(["imagegen", str(project.root), "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"would generate {vector.key}.svg for pic (16:9, SVG, openrouter {VECTOR}, ~$0.080)"
    assert out[1] == "    price: OpenRouter: $0.08 per image"
    assert out[-1].startswith("dry run: 2 picture(s) to generate, estimated $0.12 (OpenRouter prices of")
    assert main(["imagegen", str(project.root), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert [(i["format"], i["model"], i["estimated_cost"]) for i in doc["images"]] == [("svg", VECTOR, 0.08), ("png", SEEDREAM, 0.04)]
    assert router.posts == []

    router.responses = [router_body(HILLS.read_bytes(), media_type="image/svg+xml", cost=0.08), router_body(cost=0.04)]
    lines: list[str] = []
    plan = run_imagegen(project, provider=provider(), out=lines.append)
    assert (router.body(0)["output_format"], router.body(0)["model"]) == ("svg", VECTOR) and "output_format" not in router.body(1)
    assert vector.path.read_bytes() == HILLS.read_bytes() and raster.path.read_bytes().startswith(b"\x89PNG")
    sidecar = json.loads(vector.sidecar.read_text(encoding="utf-8"))
    assert (sidecar["format"], sidecar["model"], sidecar["cost_usd"], sidecar["resolution"]) == ("svg", VECTOR, 0.08, None)
    assert "format" not in json.loads(raster.sidecar.read_text(encoding="utf-8"))
    assert lines[0].startswith(f"[1/2] generated {vector.key}.svg for pic") and plan.charged == pytest.approx(0.12)


def test_svg_with_openai_is_refused_before_paying(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    project = Project.load(make_project(minimal_config(scenes=[image_scene({"prompt": PROMPT, "format": "svg"})])))
    with pytest.raises(VidgenError, match="format: svg needs imagegen.provider: openrouter"):
        run_imagegen(project, out=lambda line: None)
    lines: list[str] = []
    run_imagegen(project, dry_run=True, out=lines.append)
    assert any("problem: format: svg needs" in line for line in lines) and calls == []


# ----- the account's data policy (ZDR) -----------------------------------------------------------------


def test_policy_error_explains_privacy_settings(router: FakeRouter, svg_project) -> None:
    project = svg_project()
    raster = image_request(project, GenerateImage(prompt=PROMPT))
    router.responses = [http_error(404, POLICY_404)]
    asked: list[bool] = []

    def zdr(svg: bool = False) -> list[str]:
        asked.append(svg)
        return ["bytedance-seed/seedream-5-0-flash", "google/gemini-2.5-flash-image"]

    with pytest.raises(VidgenError) as err:
        provider(zdr=zdr).generate(raster)
    message = str(err.value)
    assert f"no provider for {SEEDREAM} that your account's privacy settings allow" in message
    assert "Zero Data Retention" in message and "https://openrouter.ai/settings/privacy" in message
    assert "Image models with a ZDR endpoint now: bytedance-seed/seedream-5-0-flash, google/gemini-2.5-flash-image" in message
    assert KEY not in message and asked == [False] and len(router.posts) == 1   # not retried
    router.responses = [http_error(404, POLICY_404)]
    with pytest.raises(VidgenError, match="No SVG image model has a ZDR endpoint now: allow non-ZDR providers for this one, or use format: png"):
        provider(zdr=lambda svg=False: []).generate(image_request(project, GenerateImage(prompt=PROMPT, format="svg")))
    router.responses = [http_error(404, POLICY_404)]
    with pytest.raises(VidgenError, match="could not be reached to suggest models"):
        provider(zdr=lambda svg=False: None).generate(raster)
    router.responses = [http_error(404, '{"error":{"message":"No endpoints found for x","code":404}}')]
    with pytest.raises(VidgenError, match="OpenRouter returned HTTP 404: .*No endpoints found"):
        provider(zdr=zdr).generate(raster)


def test_zdr_image_models_from_the_public_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    zdr = {"data": [{"model_id": "bytedance-seed/seedream-5-0-flash", "provider_name": "Seed"}, {"model_id": "some/text-model"},
                    {"model_id": "acme/vector-zdr"}]}
    images = {"data": [{"id": "bytedance-seed/seedream-5-0-flash"}, {"id": VECTOR, "supported_parameters": {"output_format": {"values": ["svg"]}}},
                       {"id": "acme/vector-zdr", "supported_parameters": {"output_format": {"type": "enum", "values": ["svg"]}}}]}
    seen: list[str] = []

    def fake(request: urllib.request.Request, timeout: float) -> FakeResponse:
        seen.append(request.full_url)
        assert request.get_header("Authorization") is None and timeout == orr.LOOKUP_TIMEOUT
        return FakeResponse(json.dumps(zdr if request.full_url == orr.ZDR_URL else images).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert orr.zdr_image_models() == ["acme/vector-zdr", "bytedance-seed/seedream-5-0-flash"]
    assert orr.zdr_image_models(svg=True) == ["acme/vector-zdr"]
    assert seen[:2] == ["https://openrouter.ai/api/v1/endpoints/zdr", "https://openrouter.ai/api/v1/images/models"]

    def offline(request: urllib.request.Request, timeout: float) -> FakeResponse:
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    assert orr.zdr_image_models() is None
    assert orr.is_policy_error(f"OpenRouter returned HTTP 404: {POLICY_404}") and not orr.is_policy_error("OpenRouter returned HTTP 400: data policy")


# ----- loading as shapes ---------------------------------------------------------------------------------


def test_load_vector_box_strokes_and_recolor(small_config: None) -> None:  # noqa: F811 - fixture
    from vidgen.vector_mobject import load_vector

    pic = load_vector(HILLS, height=3.0)
    assert len(pic.parts) == 7 and pic.box.get_fill_opacity() == 0 and pic.box.get_stroke_opacity() == 0
    assert pic.height == pytest.approx(3.0) and pic.width == pytest.approx(3.0 * 160 / 90)
    sun = pic.parts[1]
    assert sun.get_stroke_width() == pytest.approx(2 * 3.0 / 90 / 0.01)   # 2 viewBox units at a 3-unit-high picture
    pic.scale(2)
    assert sun.get_stroke_width() == pytest.approx(2 * 6.0 / 90 / 0.01)   # strokes scale with the picture
    hill = pic.parts[2]
    assert (hill.get_stroke_width(), hill.get_stroke_opacity(), hill.get_stroke_color().to_hex()) == (0, 1, hill.get_fill_color().to_hex())
    theme = Theme()
    themed = load_vector(HILLS, recolor="theme", theme=theme)
    assert themed.parts[2].get_fill_color().to_hex() != hill.get_fill_color().to_hex()
    assert themed.parts[6].get_stroke_color().to_hex().upper() == theme.colors["text"].upper()   # the white line


def test_draw_traces_outlines_then_fills(small_config: None) -> None:  # noqa: F811 - fixture
    from vidgen.vector_mobject import load_vector

    pic = load_vector(HILLS, height=3.0)
    anim = DrawBorderThenFill(pic)
    anim.begin()
    anim.interpolate(0.25)
    hill = pic.parts[2]
    assert hill.get_fill_opacity() == 0 and hill.get_stroke_width() > 0 and hill.get_stroke_opacity() > 0   # outline first
    assert pic.box.get_stroke_opacity() == 0   # the box never shows
    anim.interpolate(1.0)
    anim.finish()
    assert hill.get_fill_opacity() == 1 and hill.get_stroke_width() == 0


def test_layout_dump_reports_one_vector_object(small_config: None) -> None:  # noqa: F811 - fixture
    from vidgen.vector_mobject import load_vector

    pic = load_vector(HILLS, height=3.0)
    [item] = objects(FakeScene(pic))
    assert (item["kind"], item["class"], item["parts"], item["fill"]["color"]) == ("vector", "VectorPicture", 7, "#5E9CD2")


# ----- the image scene -----------------------------------------------------------------------------------


@pytest.mark.render
def test_image_scene_draws_svg_files_and_generated_svgs(svg_project, tmp_path: Path) -> None:
    from test_builtin_scenes import render_scene

    drawn = image_scene({"prompt": PROMPT, "format": "svg"}, draw=True, recolor="theme", caption="Hills")
    drawn["beats"] = [{"text": "Green hills roll under a bright summer sun while a lone pine stands guard."}]
    project = svg_project(
        [
            drawn,
            {"id": "file", "type": "image", "params": {"path": "assets/hills.svg", "fit": "cover", "ken_burns": True, "simplify": True},
             "beats": [{"text": "A file."}]},
        ]
    )
    (project.root / "assets").mkdir(exist_ok=True)
    (project.root / "assets" / "hills.svg").write_bytes(HILLS.read_bytes())
    media = tmp_path / "media"
    scene, _, _ = render_scene(project, "pic", media, 160, 90)   # not generated yet: the placeholder fades in
    assert "DrawBorderThenFill" not in [a for r in scene.play_log for a in r.animations]
    request = scene_images(project)[0].request
    request.path.parent.mkdir(parents=True, exist_ok=True)
    request.path.write_bytes(HILLS.read_bytes())
    scene, duration, _ = render_scene(project, "pic", media, 160, 90)
    names = [a for r in scene.play_log for a in r.animations]
    assert "DrawBorderThenFill" in names and duration > 0 and scene.mobjects == []
    draw = next(r for r in scene.play_log if "DrawBorderThenFill" in r.animations)
    assert draw.end - draw.start > 1.0   # a draw takes longer than a fade
    scene, _, _ = render_scene(project, "file", media, 90, 160)
    assert "DrawBorderThenFill" not in [a for r in scene.play_log for a in r.animations] and scene.beat_log


def test_validate_checks_svg_files(make_project, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(scenes=[{"id": "f", "type": "image", "params": {"path": "assets/bad.svg"}, "beats": [{"text": "x"}]}]))
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / "bad.svg").write_bytes(svg("<text>words only</text>"))
    assert main(["validate", str(root)]) != 0
    assert "draws nothing vidgen can show" in capsys.readouterr().err
    (root / "assets" / "bad.svg").write_bytes(HILLS.read_bytes())
    assert main(["validate", str(root)]) == 0
