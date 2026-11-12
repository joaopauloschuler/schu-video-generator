"""A quick tunnel's secret path never reaches the user or disk (DESIGN.md §115.6), and the mock
provider never opens a tunnel. A real local server and a fake cloudflared; no rendering, no
network, no real tunnel, no key."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_videogen import CATALOG, FAST, request, settings
from test_videogen_host import FAKE_HOST, HostedStandIn, fake_cloudflared, local_fetch, sources  # noqa: F401 - the fixture
from test_videogen_input_freshness import config, cut, plan_of, shot_of, tone

from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import MediaInput, request_hash
from vidgen.videogen.host import HostSettings, ShareOptions
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
from vidgen.videogen.openrouter import Response
from vidgen.videogen.redaction import redact_shared_addresses
from vidgen.videogen.run import generate_clip, ledger_path
from vidgen.videogen.shots import NO_HOST_BLOCKED
from vidgen.videogen.workflow import run_shots

HOST_SETTINGS = HostSettings(url_timeout=10, verify_timeout=1.0, verify_interval=0.05)
PATH = "Q2hlY2tfdGhlX3NlY3JldF9wYXJ0XzEy/0123456789abcdef.mp3"
ADDRESS = f"https://{FAKE_HOST}/{PATH}"
HIDDEN = f"https://{FAKE_HOST}/<secret>"
SECRET = PATH.split("/")[0]


def audio_request(audio: Path) -> Any:
    return request(model=FAST, resolution="720p", references=(MediaInput("audio", audio),))


def url_in(body: bytes | None) -> str:
    return json.loads(body or b"{}")["input_references"][-1]["audio_url"]["url"]


def quoting_provider(api: MockOpenRouter, *, status: int | None = None) -> tuple[HostedStandIn, list[str]]:
    """A provider whose every answer quotes the address it was sent: in the failed job's error, or
    with ``status`` in the answer to the submit. Also quotes the bare secret. Returns the addresses."""
    seen: list[str] = []
    provider = HostedStandIn(api)

    def transport(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
        if method == "POST":
            seen.append(url_in(body))
            text = f"could not fetch {seen[-1]} (token {seen[-1].split('/')[3]})"
            api.error = text
            if status is not None:
                api.submit_error = (status, text)
        return api(method, url, headers, body, timeout)

    provider._transport = transport
    return provider, seen


def assert_hidden(where: str, url: str) -> None:
    assert url.split("/")[3] not in where and url.rsplit("/", 1)[-1] not in where


# ----- the text ----------------------------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    (f"cannot fetch {ADDRESS}.", f"cannot fetch {HIDDEN}"),
    (f'{{"url": "{ADDRESS}"}}', f'{{"url": "{HIDDEN}"}}'),
    (f"url=https%3A%2F%2F{FAKE_HOST}%2F{SECRET}%2F0123456789abcdef.mp3&x=1", f"url=https%3A%2F%2F{HIDDEN.removeprefix('https://')}"),
    (ADDRESS.replace("/", "\\/"), HIDDEN.replace("https://", "https:\\/\\/")),
    (f"truncated https://{FAKE_HOST}/{SECRET[:20]}", f"truncated {HIDDEN}"),
    (f"path /{PATH} not found", "path /<secret> not found"),
])
def test_every_form_of_the_address_is_hidden(text: str, expected: str) -> None:
    assert redact_shared_addresses(text) == expected
    assert redact_shared_addresses(expected) == expected


def test_other_text_is_left_alone() -> None:
    for text in (f"host {FAKE_HOST} is up", "https://openrouter.ai/api/v1/videos/job-1", "no reason given", "the job failed: a/b/c"):
        assert redact_shared_addresses(text) == text


def test_a_ledger_line_never_holds_the_address(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append("failed", job_id="job-1", note=f"see {ADDRESS}", nested={"urls": [ADDRESS]}, cost_usd=0.5, host=FAKE_HOST)
    (event,) = ledger.events()
    assert SECRET not in ledger.path.read_text(encoding="utf-8")
    assert event["note"] == f"see {HIDDEN}" and event["cost_usd"] == 0.5 and event["host"] == FAKE_HOST


# ----- a paid run with a tunnel --------------------------------------------------------------------


def run_failing(tmp_path: Path, fake: list[str], api: MockOpenRouter, status: int | None) -> tuple[VidgenError, str, Ledger]:
    project, audio, _ = sources(tmp_path)
    provider, seen = quoting_provider(api, status=status)
    share = ShareOptions(HOST_SETTINGS, executable=fake, fetch=local_fetch(tmp_path))
    with pytest.raises(VidgenError) as caught:
        generate_clip(project, settings(host="quick_tunnel"), audio_request(audio), pay=True, provider=provider, catalog=CATALOG, share=share)
    return caught.value, seen[0], Ledger(ledger_path(project, provider.name))


def test_a_failed_job_quoting_the_address(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    error, url, ledger = run_failing(tmp_path, fake_cloudflared, MockOpenRouter(states=("pending", "failed")), None)
    message = str(error)
    assert_hidden(message, url)
    assert f"https://{FAKE_HOST}/<secret>" in message and "(token <secret>)" in message and message.startswith("video job")
    assert_hidden(json.dumps(error.details), url)
    assert_hidden(ledger.path.read_text(encoding="utf-8"), url)
    assert ledger.events()[-1]["event"] == "failed" and "host_close" in [e["event"] for e in ledger.events()]


@pytest.mark.parametrize("status", [400, 500])
def test_a_submit_error_quoting_the_address(tmp_path: Path, fake_cloudflared: list[str], status: int) -> None:
    error, url, ledger = run_failing(tmp_path, fake_cloudflared, MockOpenRouter(), status)
    message = str(error)
    assert_hidden(message, url)
    assert f"HTTP {status}" in message and f"https://{FAKE_HOST}/<secret>" in message and "(token <secret>)" in message
    assert_hidden(ledger.path.read_text(encoding="utf-8"), url)
    assert bool(ledger.unresolved_intents()) is (status == 500)   # 400: no job exists; 500: outcome unknown


@pytest.mark.slow
def test_exception_details_are_redacted(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    project, audio, _ = sources(tmp_path)
    provider = HostedStandIn(MockOpenRouter())
    urls: list[str] = []

    def failing_submit(*args: Any, **kwargs: Any) -> Any:
        urls.append(provider.uploader(audio))  # type: ignore[misc]
        raise VidgenError(f"refused {urls[0]}", details={"reply": {"urls": [urls[0]]}, "count": 1})

    monkeypatch.setattr(provider, "submit", failing_submit)
    share = ShareOptions(HOST_SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path))
    with pytest.raises(VidgenError) as caught:
        generate_clip(project, settings(host="quick_tunnel"), audio_request(audio), pay=True, provider=provider, catalog=CATALOG, share=share)
    assert_hidden(str(caught.value) + json.dumps(caught.value.details), urls[0])
    assert caught.value.details["count"] == 1


@pytest.mark.slow
def test_a_failed_shot_shows_no_address_in_its_outcome(make_project, tmp_path: Path, fake_cloudflared: list[str]) -> None:
    root = make_project(config(shot_of("a", audio="beat"), host="quick_tunnel", cloudflared=fake_cloudflared[1]))
    tone(root / "audio" / "a.mp3", 2.0)
    cut(root)
    project = Project.load(root)
    project.config.videogen = project.config.videogen.model_copy(update={"provider": "openrouter"})
    api = MockOpenRouter(states=("pending", "failed"))
    provider, seen = quoting_provider(api)
    share = ShareOptions(HOST_SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path))
    with pytest.raises(VidgenError) as caught:
        run_shots(project, pay=True, provider=provider, catalog=CATALOG, share=share, out=lambda line: None)
    (outcome,) = caught.value.details["shots"]
    assert outcome["status"] == "failed" and "<secret>" in outcome["message"]
    assert_hidden(str(caught.value), seen[0])
    assert_hidden(json.dumps(caught.value.details), seen[0])


def test_a_job_polled_by_a_later_run_has_no_host_and_is_still_redacted(tmp_path: Path) -> None:
    project, audio, _ = sources(tmp_path)
    req = audio_request(audio)
    api = MockOpenRouter(states=("failed",), error=f"could not fetch {ADDRESS}")
    api.jobs["job-1"] = 0
    ledger = Ledger(ledger_path(project, "openrouter"))
    ledger.append("submit", job_id="job-1", provider="openrouter", model=FAST, request_hash=request_hash(req), estimate_usd=0.2)
    with pytest.raises(VidgenError) as caught:
        generate_clip(project, settings(), req, pay=True, provider=HostedStandIn(api), catalog=CATALOG)
    assert SECRET not in str(caught.value) and HIDDEN in str(caught.value)
    assert SECRET not in ledger.path.read_text(encoding="utf-8")


# ----- the mock provider never shares ------------------------------------------------------------


class NoShare:
    """Fails the test when a host is opened."""

    def __init__(self, settings: HostSettings = HOST_SETTINGS) -> None:
        self.settings = settings

    def host(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("mock opened a tunnel")


def no_cloudflared(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("mock looked for cloudflared")

    monkeypatch.setattr("vidgen.videogen.host.find_cloudflared", refuse)
    monkeypatch.setattr("vidgen.videogen.host._start_process", refuse)


def test_mock_with_quick_tunnel_starts_no_cloudflared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    no_cloudflared(monkeypatch)
    project, audio, _ = sources(tmp_path)
    api = MockOpenRouter(video=b"fake clip")
    for share in (None, NoShare()):   # from the config, and passed in
        result = generate_clip(project, settings(host="quick_tunnel"), audio_request(audio), pay=True, provider=MockVideoProvider(api), catalog=CATALOG, share=share, again=True)  # type: ignore[arg-type]
        assert result.paid or result.plan.cached
        if result.plan.cached:
            continue
        assert url_in(json.dumps(api.submits[-1].body).encode()) == f"https://mock.invalid/{audio.name}"
    events = [e["event"] for e in Ledger(ledger_path(project, "mock")).events()]
    assert "host_open" not in events and "submit" in events


@pytest.mark.parametrize("videogen", [{"host": "quick_tunnel", "cloudflared": "nowhere/cloudflared"}, {}], ids=["quick_tunnel", "no_host"])
def test_mock_plan_shares_nothing_and_does_not_block(make_project, monkeypatch: pytest.MonkeyPatch, videogen: dict[str, Any]) -> None:
    no_cloudflared(monkeypatch)
    root = make_project(config(shot_of("a", audio="beat"), **videogen))
    tone(root / "audio" / "a.mp3", 2.0)
    cut(root)
    item = plan_of(root)
    text = "\n".join(item.lines(root))
    assert item.shot.blocked == [] and item.shot.share_minutes is None and NO_HOST_BLOCKED not in item.shot.blocked
    assert "would share" not in text and "Cloudflare" not in text
    assert "mock provider: these inputs stay on this machine" in text


@pytest.mark.slow
def test_mock_runs_a_voice_shot_end_to_end_for_free(make_project, monkeypatch: pytest.MonkeyPatch) -> None:
    no_cloudflared(monkeypatch)
    root = make_project(config(shot_of("a", audio="beat"), host="quick_tunnel"))
    tone(root / "audio" / "a.mp3", 2.0)
    cut(root)
    report = run_shots(Project.load(root), pay=True, catalog=CATALOG, out=lambda line: None)
    assert [s.status for s in report.shots] == ["paid"] and report.shots[0].take is not None
