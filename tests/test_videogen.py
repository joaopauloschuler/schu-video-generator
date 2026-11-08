"""Generated video, the provider layer (DESIGN.md §113): requests and cache keys, the public
model list (a real copy of 2026-11-07), checks and estimates, the mock API, submit / poll /
download, the cache, the ledger and budget cap, errors, key and proxy modes, the CLI. No
network: every paid endpoint is the mock."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest
from conftest import minimal_config

from vidgen import cli, config
from vidgen.errors import VidgenError
from vidgen.videogen import MediaInput, VideoRequest, canonical_request, request_hash
from vidgen.videogen.ledger import BudgetState, Ledger
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
from vidgen.videogen.models import Catalog, check_request, estimate, load_catalog, parse_models, price_lines, snap_duration
from vidgen.videogen.openrouter import OpenRouterVideoProvider
from vidgen.videogen.run import clip_path, generate_clip, ledger_path, plan_clip

DATA = Path(__file__).parent / "data" / "openrouter_video_models.json"
DOC = json.loads(DATA.read_text(encoding="utf-8"))
CATALOG = Catalog(tuple(parse_models(DOC)), 0.0, "cache")
KEY = "sk-or-v1-test0secret0value"
FAST = "bytedance/seedance-2.0-fast"


def request(**changes: object) -> VideoRequest:
    fields: dict[str, object] = {"model": "google/veo-3.1-lite", "prompt": "a lighthouse at dusk", "duration": 4, "resolution": "720p", "aspect_ratio": "9:16"}
    fields.update(changes)
    return VideoRequest(**fields)  # type: ignore[arg-type]


def settings(**changes: object) -> config.VideogenConfig:
    return config.VideogenConfig(**{"provider": "mock", "budget_usd": 2.0, **changes})  # type: ignore[arg-type]


def run(root: Path, req: VideoRequest, api: MockOpenRouter, **kw: object):
    provider = MockVideoProvider(api)
    return generate_clip(root, kw.pop("cfg", settings()), req, pay=kw.pop("pay", True), provider=provider, catalog=CATALOG, **kw)  # type: ignore[arg-type]


# ----- requests and keys ---------------------------------------------------------------------------


def test_cache_key_follows_contents_not_names(tmp_path: Path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"picture")
    b.write_bytes(b"picture")
    first = request(frame_images=(MediaInput("image", a, frame_type="first_frame"),))
    same = request(frame_images=(MediaInput("image", b, frame_type="first_frame"),))
    assert request_hash(first) == request_hash(same)
    b.write_bytes(b"another picture")
    assert request_hash(first) != request_hash(same)
    assert request_hash(request()) != request_hash(request(seed=3))
    assert canonical_request(request())["generate_audio"] is False


def test_request_errors() -> None:
    with pytest.raises(VidgenError, match="author/name"):
        VideoRequest(model="veo")
    with pytest.raises(VidgenError, match="not both"):
        request(size="720x1280")
    with pytest.raises(VidgenError, match="frame_type"):
        request(frame_images=(MediaInput("image", url="https://x.invalid/a.png"),))
    with pytest.raises(VidgenError, match="only pictures"):
        MediaInput("audio", url="https://x.invalid/a.mp3", frame_type="first_frame")


# ----- the model list, checks, estimates -----------------------------------------------------------


def test_model_list_and_did_you_mean() -> None:
    assert len(CATALOG.models) == 33
    fast = CATALOG.find(FAST)
    assert fast.durations == tuple(range(4, 16)) and fast.resolutions == ("480p", "720p") and fast.frame_types == ("first_frame", "last_frame")
    with pytest.raises(VidgenError, match="did you mean bytedance/seedance-2.0-fast"):
        CATALOG.find("bytedance/seedance-2-fast")


def test_checks_with_did_you_mean() -> None:
    model = CATALOG.find("bytedance/seedance-2.5")
    check = check_request(request(model=model.id, duration=3, resolution="1080", aspect_ratio="9:16"), model)
    assert any("4-30 s, not 3 (did you mean 4?)" in p for p in check.problems)
    assert any("takes resolution 480p, 720p, not 1080" in p for p in check.problems)
    veo_fast = CATALOG.find("google/veo-3.1-fast")
    assert any("not 1080 (did you mean 1080p?)" in p for p in check_request(request(model=veo_fast.id, resolution="1080"), veo_fast).problems)
    assert snap_duration(4.3, (4, 6, 8)) == 6 and snap_duration(9, (4, 6, 8)) == 8
    veo = CATALOG.find("google/veo-3.1-lite")
    assert check_request(request(duration=5), veo).problems == ["google/veo-3.1-lite makes clips of 4, 6, 8 s, not 5 (did you mean 6?)"]
    avatar = CATALOG.find("heygen/avatar-iv")
    check = check_request(request(model=avatar.id, duration=5), avatar)
    assert "duration" in check.drop and not check.problems
    grok = CATALOG.find("x-ai/grok-imagine-video-1.5-lite")
    last = request(model=grok.id, duration=5, resolution="480p", frame_images=(MediaInput("image", url="https://x.invalid/a.png", frame_type="last_frame"),))
    assert any("not a last_frame" in p for p in check_request(last, grok).problems)
    opts = request(provider_options={"google-vertex": {"taks": "x"}})
    assert any("no option 'taks'" in p for p in check_request(opts, veo).problems)


def test_estimates() -> None:
    veo = CATALOG.find("google/veo-3.1-lite")
    assert estimate(request(), veo).cost == pytest.approx(0.12)            # 720p without audio $0.03/s x 4
    assert estimate(request(resolution="1080p"), veo).cost == pytest.approx(0.20)   # untiered without audio $0.05/s
    grok = CATALOG.find("x-ai/grok-imagine-video-1.5-lite")
    frame = (MediaInput("image", url="https://x.invalid/a.png", frame_type="first_frame"),)
    assert estimate(request(model=grok.id, duration=5, resolution="480p", frame_images=frame), grok).cost == pytest.approx(0.11)
    seedance = CATALOG.find("bytedance/seedance-2.5")
    est = estimate(request(model=seedance.id, duration=5, resolution="480p", aspect_ratio="16:9"), seedance)
    assert est.cost == pytest.approx(0.514, abs=0.01) and "tokens" in est.basis    # ~$0.10/s as listed
    avatar = CATALOG.find("heygen/avatar-iv")
    assert estimate(request(model=avatar.id, duration=None), avatar, duration=6).cost == pytest.approx(0.30)
    assert estimate(request(model=avatar.id, duration=None, resolution=None), avatar).cost is None
    aleph = CATALOG.find("runway/aleph-2")
    assert estimate(request(model=aleph.id, duration=1, resolution=None), aleph).cost == pytest.approx(0.56)  # the minimum
    nothing_set = estimate(request(model=FAST, duration=None, resolution=None), CATALOG.find(FAST))
    assert nothing_set.cost is not None and "15 s" in nothing_set.basis       # priced at the longest, largest
    assert price_lines(veo) == ["720p $0.030/s", "1080p $0.050/s"]
    assert price_lines(aleph) == ["$0.280/s", "at least $0.560 per clip"]


def test_catalog_cache_and_offline(tmp_path: Path) -> None:
    path = tmp_path / "models.json"
    calls: list[int] = []

    def fetch() -> object:
        calls.append(1)
        return DOC

    def offline() -> object:
        raise VidgenError("cannot reach OpenRouter: offline")

    with pytest.raises(VidgenError, match="no copy is cached"):
        load_catalog(cache_path=path, fetch=offline)
    live = load_catalog(cache_path=path, fetch=fetch, now=lambda: 1000.0)
    assert live.source == "live" and len(live.models) == 33 and path.is_file()
    again = load_catalog(cache_path=path, fetch=fetch, now=lambda: 2000.0)
    assert again.source == "cache" and len(calls) == 1
    stale = load_catalog(cache_path=path, fetch=offline, now=lambda: 1e9)
    assert stale.source == "cache" and stale.note and "offline" in stale.note
    load_catalog(cache_path=path, fetch=fetch, refresh=True, now=lambda: 2000.0)
    assert len(calls) == 2


# ----- the mock flow: submit, poll, download, cache, ledger -----------------------------------------


def test_paid_flow_with_the_mock(tmp_path: Path) -> None:
    api = MockOpenRouter()
    result = run(tmp_path, request(), api)
    assert result.paid and result.path == clip_path(tmp_path, request_hash(request()))
    assert result.path.read_bytes() == api.content("mock-job-1") and result.cost == 0.25
    statuses = [r.url.rsplit("/", 1)[-1] for r in api.requests]
    assert [r.method for r in api.requests] == ["POST", "GET", "GET", "GET"] and statuses[-1] == "content?index=0"
    body = api.submits[0].body
    assert body == {"model": "google/veo-3.1-lite", "prompt": "a lighthouse at dusk", "duration": 4, "resolution": "720p", "aspect_ratio": "9:16", "generate_audio": False}
    events = Ledger(ledger_path(tmp_path, "mock")).events()
    assert [e["event"] for e in events] == ["submit_intent", "submit", "completed"]
    assert events[1]["estimate_usd"] == pytest.approx(0.12) and events[2]["cost_usd"] == 0.25
    assert events[1]["intent_id"] == events[0]["intent_id"]
    sidecar = json.loads(result.path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["job_id"] == "mock-job-1" and sidecar["cost_usd"] == 0.25
    assert not (tmp_path / "videogen-ledger.jsonl").exists()            # the mock keeps its own ledger


def test_cache_hit_submits_nothing(tmp_path: Path) -> None:
    api = MockOpenRouter()
    run(tmp_path, request(), api)
    second = run(tmp_path, request(), api)
    assert second.plan.cached and not second.paid and len(api.submits) == 1 and len(api.requests) == 4


def test_dry_run_sends_nothing(tmp_path: Path) -> None:
    api = MockOpenRouter()
    result = run(tmp_path, request(), api, pay=False)
    assert api.requests == [] and result.path is None
    text = "\n".join(result.plan.lines(tmp_path))
    assert "would generate assets/generated_video/" in text and "estimate: $0.120" in text and "left $2.000" in text


def test_budget_cap_and_estimate_refusals(tmp_path: Path) -> None:
    api = MockOpenRouter(cost=0.25)
    with pytest.raises(VidgenError, match="paying needs a budget"):
        run(tmp_path, request(), api, cfg=settings(budget_usd=None))
    run(tmp_path, request(), api, cfg=settings(budget_usd=0.4))                    # spends 0.25
    with pytest.raises(VidgenError, match=r"estimate \$0.200 is more than the budget has left .*left \$0.150"):
        run(tmp_path, request(resolution="1080p"), api, cfg=settings(budget_usd=0.4))
    with pytest.raises(VidgenError, match="estimate"):
        run(tmp_path, request(seed=1), api, cfg=settings(budget_usd=5.0), budget_usd=0.3)   # the lower cap wins
    assert len(api.submits) == 1
    with pytest.raises(VidgenError, match="price of this heygen/avatar-iv clip is unknown"):
        run(tmp_path, request(model="heygen/avatar-iv", duration=None, resolution=None), api)
    with pytest.raises(VidgenError, match="did you mean 6"):
        run(tmp_path, request(duration=5), api)
    assert len(api.submits) == 1


def test_ledger_counts_estimates_of_unreported_jobs(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    ledger.append("submit", job_id="a", provider="openrouter", model="m/x", request_hash="h1", estimate_usd=0.5)
    ledger.append("submit", job_id="b", provider="openrouter", model="m/x", request_hash="h2", estimate_usd=0.3)
    ledger.append("completed", job_id="b", cost_usd=0.2, is_byok=False)
    assert ledger.spent() == pytest.approx(0.7) and BudgetState(1.0, ledger.spent()).remaining_usd == pytest.approx(0.3)
    (tmp_path / "l.jsonl").write_text("not json\n", encoding="utf-8")
    with pytest.raises(VidgenError, match="line 1 is not a ledger event"):
        ledger.spent()


def test_timeout_then_resume_without_paying_twice(tmp_path: Path) -> None:
    api = MockOpenRouter()
    ticks = iter(range(0, 100000, 1000))
    slow = MockVideoProvider(api, clock=lambda: float(next(ticks)))
    with pytest.raises(VidgenError, match="still pending after 900 s; it was paid for"):
        generate_clip(tmp_path, settings(), request(), pay=True, provider=slow, catalog=CATALOG)
    assert [e["event"] for e in Ledger(ledger_path(tmp_path, "mock")).events()] == ["submit_intent", "submit"]
    plan = plan_clip(tmp_path, settings(), request(), catalog=CATALOG)
    assert plan.previous_job is not None and "not paid again" in "\n".join(plan.lines())
    result = run(tmp_path, request(), api)
    assert result.path is not None and result.path.is_file() and len(api.submits) == 1
    assert [e["event"] for e in Ledger(ledger_path(tmp_path, "mock")).events()] == ["submit_intent", "submit", "completed"]


# ----- errors ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, message, expected",
    [
        (402, "Insufficient credits", "not enough credits"),
        (429, "Rate limit exceeded", "rate limited.*not retried automatically"),
        (413, "Payload too large", "too large.*host the inputs"),
        (400, "Prompt rejected by content policy", "content policy"),
    ],
)
def test_submit_errors_are_clear_and_not_retried(tmp_path: Path, status: int, message: str, expected: str) -> None:
    api = MockOpenRouter(submit_error=(status, message))
    with pytest.raises(VidgenError, match=expected):
        run(tmp_path, request(), api)
    assert len(api.submits) == 1 and [e["event"] for e in Ledger(ledger_path(tmp_path, "mock")).events()] == ["submit_intent", "intent_resolved"]
    assert Ledger(ledger_path(tmp_path, "mock")).spent() == 0.0 and Ledger(ledger_path(tmp_path, "mock")).unresolved_intents() == []


def test_failed_and_expired_jobs(tmp_path: Path) -> None:
    api = MockOpenRouter(states=("pending", "failed"), error="Output flagged by moderation", cost=None)
    with pytest.raises(VidgenError, match="refused under the provider's content policy: Output flagged"):
        run(tmp_path, request(), api)
    assert [e["event"] for e in Ledger(ledger_path(tmp_path, "mock")).events()] == ["submit_intent", "submit", "failed"]
    api = MockOpenRouter(states=("pending", "expired"), error="output expired")
    with pytest.raises(VidgenError, match="expired before its video was downloaded.*new paid job"):
        run(tmp_path, request(seed=2), api)


def test_polls_are_retried_on_429(tmp_path: Path) -> None:
    api = MockOpenRouter(poll_error=(429, "slow down"), poll_errors=2)
    result = run(tmp_path, request(), api)
    assert result.paid and len(api.submits) == 1


# ----- inputs ----------------------------------------------------------------------------------


def test_inline_pictures_hosted_audio(tmp_path: Path) -> None:
    picture, voice = tmp_path / "face.png", tmp_path / "line.mp3"
    picture.write_bytes(b"\x89PNG fake")
    voice.write_bytes(b"ID3 fake")
    provider = MockVideoProvider()
    frame = MediaInput("image", picture, frame_type="first_frame")
    body = provider.request_body(request(frame_images=(frame,), references=(MediaInput("video", url="https://x.invalid/guide.mp4"),)))
    assert body["frame_images"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body["input_references"] == [{"type": "video_url", "video_url": {"url": "https://x.invalid/guide.mp4"}}]
    audio = request(references=(MediaInput("audio", voice),))
    with pytest.raises(VidgenError, match="must be hosted: audio/video references must be https URLs"):
        provider.request_body(audio)
    hosted = MockVideoProvider(uploader=lambda path: f"https://host.invalid/{path.name}")
    assert hosted.request_body(audio)["input_references"][0]["audio_url"]["url"] == "https://host.invalid/line.mp3"


def big_picture(path: Path, size: tuple[int, int] = (2048, 3642), *, alpha: bool = False, noisy: bool = False) -> Path:
    """A picture shaped like a reference sheet picture; ``noisy``: random pixels, which PNG cannot
    shrink (a sheet picture's 5-7 MB), else plain (fast to write)."""
    import numpy as np
    from PIL import Image

    channels = 4 if alpha else 3
    if noisy:
        pixels = np.random.default_rng(1).integers(0, 256, (size[1], size[0], channels), dtype=np.uint8)
    else:
        pixels = np.full((size[1], size[0], channels), 90, dtype=np.uint8)
    if alpha:
        pixels[..., 3] = 128
    Image.fromarray(pixels, "RGBA" if alpha else "RGB").save(path, compress_level=1)
    return path


def test_pictures_are_sent_as_smaller_cached_copies(tmp_path: Path) -> None:
    from PIL import Image

    from vidgen.videogen.pictures import PICTURE_MAX_SIDE, PICTURES_DIR, sendable_picture

    sheet = big_picture(tmp_path / "sheet.png")
    before = sheet.read_bytes()
    copy = sendable_picture(sheet, tmp_path)
    assert copy.parent == tmp_path / PICTURES_DIR and copy.suffix == ".jpg" and sheet.read_bytes() == before
    with Image.open(copy) as image:
        assert image.format == "JPEG" and max(image.size) == PICTURE_MAX_SIDE and image.size == (720, 1280)
    stamp = copy.stat().st_mtime_ns
    assert sendable_picture(sheet, tmp_path) == copy and copy.stat().st_mtime_ns == stamp  # cached, not made again
    clear = sendable_picture(big_picture(tmp_path / "logo.png", (1600, 400), alpha=True), tmp_path)
    with Image.open(clear) as image:
        assert image.format == "PNG" and image.mode == "RGBA" and image.size == (1280, 320)
    small = tmp_path / "small.jpg"
    Image.new("RGB", (640, 480), (10, 20, 30)).save(small)
    assert sendable_picture(small, tmp_path) == small  # a JPEG within the limit is sent as it is


def test_inline_pictures_shrink_the_request(tmp_path: Path) -> None:
    from vidgen.videogen.openrouter import MAX_INLINE_BYTES, request_bytes

    sheet = MediaInput("image", big_picture(tmp_path / "sheet.png", noisy=True))
    sheets = (sheet, sheet)
    req = request(model=FAST, resolution="480p", references=sheets)
    full = len(json.dumps(MockVideoProvider().request_body(req)).encode("utf-8"))
    small = request_bytes(req, tmp_path)
    assert full > MAX_INLINE_BYTES and small < full / 10
    api = MockOpenRouter()
    result = run(tmp_path, req, api)
    sent = api.submits[0].body["input_references"]
    assert result.paid and [r["image_url"]["url"][:23] for r in sent] == ["data:image/jpeg;base64,"] * 2
    assert len(json.dumps(api.submits[0].body).encode("utf-8")) == small
    assert result.plan.key == request_hash(req)  # the key follows the sources, not the copies


# ----- the key -------------------------------------------------------------------------------------


def test_proxy_mode_sends_no_authorization(tmp_path: Path) -> None:
    for provider in (
        OpenRouterVideoProvider(key_via_proxy=True, transport=MockOpenRouter(), environ={}, sleep=lambda s: None),
        OpenRouterVideoProvider(transport=MockOpenRouter(), environ={"VIDGEN_OPENROUTER_KEY_VIA_PROXY": "1"}, sleep=lambda s: None),
    ):
        provider.name = "mock"
        generate_clip(tmp_path / str(id(provider)), settings(), request(), pay=True, provider=provider, catalog=CATALOG)
        api = provider._transport
        assert isinstance(api, MockOpenRouter) and len(api.requests) == 4
        assert all("authorization" not in {k.lower() for k in r.headers} for r in api.requests)


def test_env_key_is_sent_but_never_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    api = MockOpenRouter()
    provider = OpenRouterVideoProvider(transport=api, environ={"OPENROUTER_API_KEY": KEY}, sleep=lambda s: None)
    provider.name = "mock"
    generate_clip(tmp_path, settings(), request(), pay=True, provider=provider, catalog=CATALOG)
    assert all(r.headers["Authorization"] == f"Bearer {KEY}" for r in api.requests)
    echo = OpenRouterVideoProvider(transport=MockOpenRouter(submit_error=(402, f"no credits for key {KEY}")), environ={"OPENROUTER_API_KEY": KEY})
    with pytest.raises(VidgenError) as info:
        echo.submit(request())
    assert KEY not in str(info.value) and "***" in str(info.value)
    files = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json*"))
    assert KEY not in caplog.text and KEY not in files and "submitted video job mock-job-1" in caplog.text
    with pytest.raises(VidgenError, match="(?s)OPENROUTER_API_KEY is not set.*key_via_proxy"):
        OpenRouterVideoProvider(environ={}).check_credentials()


# ----- config and CLI ----------------------------------------------------------------------------


def test_config_section() -> None:
    cfg = config.VideoConfig.model_validate(minimal_config())
    assert cfg.videogen.provider == "openrouter" and cfg.videogen.budget_usd is None and cfg.videogen.inline_media == "images"
    with pytest.raises(Exception, match="provider"):
        config.VideoConfig.model_validate(minimal_config(videogen={"provider": "sora"}))
    with pytest.raises(Exception, match="budget_usd"):
        config.VideoConfig.model_validate(minimal_config(videogen={"budget_usd": -1}))


def test_videogen_settings_do_not_change_renders(make_project) -> None:
    from vidgen.project import Project
    from vidgen.render.fingerprint import NOT_RENDER_INPUTS, scene_fingerprint

    plain = Project.load(make_project(minimal_config(), folder="a"))
    with_video = Project.load(make_project(minimal_config(videogen={"provider": "mock", "budget_usd": 2.0}), folder="b"))
    assert scene_fingerprint(plain, "intro") == scene_fingerprint(with_video, "intro")
    assert "videogen" in NOT_RENDER_INPUTS


def test_cli_models_from_cache_and_ledger(make_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path / "cache"))
    cache = tmp_path / "cache" / "openrouter" / "video_models.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"fetched_at": time.time(), "doc": DOC}), encoding="utf-8")
    assert cli.main(["generate", "models"]) == 0
    out = capsys.readouterr().out
    assert "33 video models on OpenRouter" in out and "cache" in out
    assert "google/veo-3.1-lite | 4, 6, 8 s | 720p/1080p | 16:9 9:16 | frames: first+last | 720p $0.030/s, 1080p $0.050/s" in out
    assert cli.main(["generate", "models", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["command"] == "generate" and doc["source"] == "cache" and len(doc["models"]) == 33
    root = make_project(minimal_config(videogen={"provider": "mock", "budget_usd": 1.0}))
    run(root, request(), MockOpenRouter())
    assert cli.main(["generate", "ledger", str(root)]) == 0
    out = capsys.readouterr().out
    assert "mock-job-1 google/veo-3.1-lite completed: $0.250" in out and "budget $1.000, spent $0.250, left $0.750" in out
    assert cli.main(["generate", "ledger", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["spent_usd"] == 0.25 and doc["jobs"][0]["status"] == "completed"
