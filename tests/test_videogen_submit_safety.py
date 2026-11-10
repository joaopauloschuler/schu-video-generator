"""Money safety of a paid submit (DESIGN.md §113.10, §115.4): the quick tunnel stays open for a
job's whole wait (a real local server and a fake cloudflared, with real sleeps), a submit is
refused on a host that is closed or almost out of time, and a submit with no known outcome is
never paid twice. No rendering, no network, no real tunnel."""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any

import pytest
from test_videogen import CATALOG, FAST, request, settings
from test_videogen_host import SETTINGS, HostedStandIn, fake_cloudflared, local_fetch, sources  # noqa: F401 - the fixture
from test_videogen_shots import WIDE, shot_config

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.project import Project
from vidgen.videogen import MediaInput, request_hash
from vidgen.videogen.host import HostSettings, QuickTunnelHost, ShareOptions
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.mock import MockOpenRouter, MockVideoProvider
from vidgen.videogen.openrouter import Response
from vidgen.videogen.run import generate_clip, ledger_path, plan_clip
from vidgen.videogen.shots import plan_shots
from vidgen.videogen.workflow import run_shots, status_lines

RESOLVE = "vidgen generate resolve --intent"


class CapturingShare(ShareOptions):
    """Share options that remember the host they made."""

    def host(self, *args: Any, **kwargs: Any) -> QuickTunnelHost:
        made = super().host(*args, **kwargs)
        object.__setattr__(self, "made", made)
        return made


def audio_request(audio: Path) -> Any:
    return request(model=FAST, resolution="720p", references=(MediaInput("audio", audio),))


def url_in(body: bytes | None) -> str:
    return json.loads(body or b"{}")["input_references"][-1]["audio_url"]["url"]


# ----- the tunnel stays open for the job's whole wait ----------------------------------------------


def test_an_in_flight_fetch_and_a_repeat_keep_the_host_open(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    audio.write_bytes(b"x" * (30 * 1024 * 1024))
    fetch = local_fetch(tmp_path)
    with QuickTunnelHost([audio], root=project, settings=SETTINGS, executable=fake_cloudflared, fetch=fetch) as host:
        url = host.url_of(audio)
        assert fetch("GET", url, 10).status == 200   # a complete GET: the old grace period would start here
        assert not host.wait_closed(0.4), "the host closed after a complete fetch"
        path = url.removeprefix(f"https://{host.host_name}")
        with socket.create_connection(("127.0.0.1", host.server.port)) as slow:   # a second GET, reading slowly
            slow.sendall(f"GET {path} HTTP/1.0\r\n\r\n".encode())
            assert slow.recv(65536)
            assert not host.wait_closed(0.5), "the host closed with a fetch in flight"
            assert host.is_open and host.close_reason is None
        fetch("HEAD", url, 5)                       # a late HEAD
        assert not host.wait_closed(0.2)
    assert host.close_reason == "done"


def test_a_paid_run_does_not_close_the_tunnel_after_a_fetch(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    fetch = local_fetch(tmp_path)
    api = MockOpenRouter(states=("pending", "pending", "completed"), cost=0.2)
    share = CapturingShare(HostSettings(url_timeout=10, verify_timeout=2.0, verify_interval=0.05), executable=fake_cloudflared, fetch=fetch)
    provider = HostedStandIn(api, sleep=lambda seconds: time.sleep(0.3))   # real pauses longer than the old grace
    fetched: list[tuple[str, bool]] = []

    def provider_side(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
        if method == "POST":
            address = url_in(body)
            fetched.append(("validate", fetch("GET", address, 5).status == 200))
            time.sleep(0.5)                          # the provider queues the job, then fetches again
            fetched.append(("after queue", share.made.is_open and fetch("GET", address, 5).status == 200))
        return api(method, url, headers, body, timeout)

    provider._transport = provider_side
    result = generate_clip(project, settings(host="quick_tunnel"), audio_request(audio), pay=True, provider=provider, catalog=CATALOG, share=share)
    assert result.paid and fetched == [("validate", True), ("after queue", True)]
    assert share.made.close_reason == "done"


# ----- no paid submit without a live tunnel ------------------------------------------------------


def test_a_host_nearly_out_of_time_refuses_the_submit_without_a_post(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    local = local_fetch(tmp_path)

    def slow_public(method: str, url: str, timeout: float) -> Response:
        time.sleep(1.2)                             # the slow public check of a brand new address
        return local(method, url, timeout)

    api = MockOpenRouter()
    provider = HostedStandIn(api, poll_timeout=0.1)
    host_settings = HostSettings(url_timeout=1.0, verify_timeout=5.0, verify_interval=0.05, max_seconds=1.4, submit_margin=0.25)
    share = CapturingShare(host_settings, executable=fake_cloudflared, fetch=slow_public)
    with pytest.raises(VidgenError, match="(?s)quick tunnel.*nothing was sent or paid"):
        generate_clip(project, settings(host="quick_tunnel"), audio_request(audio), pay=True, provider=provider, catalog=CATALOG, share=share)
    assert api.requests == []
    ledger = Ledger(ledger_path(project, "openrouter"))
    assert ledger.intents() == [] and [e["event"] for e in ledger.events() if e["event"] == "submit"] == []
    assert share.made.close_reason is not None and not share.made.is_open


def test_url_of_and_the_time_check_on_a_closed_host(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    host = QuickTunnelHost([audio], root=project, settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path))
    host.open()
    host.ensure_time_for_job(1.0)                   # plenty of time left
    with pytest.raises(VidgenError, match="only .* s left"):
        host.ensure_time_for_job(10_000.0)
    host.close("max lifetime")
    with pytest.raises(VidgenError, match=r"closed \(max lifetime\)"):
        host.url_of(audio)
    with pytest.raises(VidgenError, match="already closed"):
        host.ensure_time_for_job(1.0)


def test_lifetime_must_cover_the_wait() -> None:
    defaults = HostSettings()                       # 20 min against poll_timeout 900 s: enough
    assert defaults.lifetime_problem(900.0) is None
    short = HostSettings(max_seconds=900.0)
    problem = short.lifetime_problem(900.0)
    assert problem is not None and "host_max_minutes (15 min)" in problem and "left waiting on a closed tunnel" in problem and "poll_timeout to at most 660 s" in problem
    assert short.lifetime_problem(660.0) is None


def test_generate_refuses_a_lifetime_too_short_before_opening(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    api = MockOpenRouter()
    share = CapturingShare(HostSettings(max_seconds=900.0), executable=fake_cloudflared, fetch=local_fetch(tmp_path))
    with pytest.raises(VidgenError, match="closed tunnel"):
        generate_clip(project, settings(host="quick_tunnel"), audio_request(audio), pay=True, provider=HostedStandIn(api), catalog=CATALOG, share=share)
    assert api.requests == [] and not hasattr(share, "made")   # no tunnel was opened


# ----- a submit with no known outcome is never paid twice ------------------------------------------


def interrupted(root: Path, cfg: Any = None) -> tuple[MockOpenRouter, Ledger]:
    """A POST that reaches the provider (a job exists) and is then cut off by Ctrl+C."""
    api = MockOpenRouter(cost=0.2)
    provider = MockVideoProvider(api)

    def cut_off(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
        api(method, url, headers, body, timeout)
        raise KeyboardInterrupt

    provider._transport = cut_off
    with pytest.raises(KeyboardInterrupt):
        generate_clip(root, cfg or settings(), request(), pay=True, provider=provider, catalog=CATALOG)
    return api, Ledger(ledger_path(root, "mock"))


def test_interrupted_submit_keeps_an_intent_and_is_not_paid_again(tmp_path: Path) -> None:
    api, ledger = interrupted(tmp_path)
    assert len(api.submits) == 1 and [e["event"] for e in ledger.events()] == ["submit_intent"]
    (intent,) = ledger.unresolved_intents()
    assert intent.model == request().model and intent.estimate_usd == pytest.approx(0.12)
    # counted at its estimate in the budget, and not in the jobs (older readers see no job either)
    assert ledger.spent() == pytest.approx(0.12) and ledger.jobs() == []
    plan = plan_clip(tmp_path, settings(), request(), catalog=CATALOG)
    assert plan.unresolved_intent == intent and plan.previous_job is None and plan.budget.spent_usd == pytest.approx(0.12)
    assert any("no known outcome" in line for line in plan.lines()) and any(RESOLVE in line for line in plan.lines())
    # the re-run refuses before any request, with the way out
    again = MockOpenRouter(cost=0.2)
    with pytest.raises(VidgenError, match=f"(?s)no known outcome.*{RESOLVE} {intent.intent_id} --not-charged"):
        generate_clip(tmp_path, settings(), request(), pay=True, provider=MockVideoProvider(again), catalog=CATALOG)
    with pytest.raises(VidgenError, match="no known outcome"):   # again= (an expired output) does not bypass it
        generate_clip(tmp_path, settings(), request(), pay=True, provider=MockVideoProvider(again), catalog=CATALOG, again=True)
    assert again.requests == []


def test_network_failure_keeps_the_intent_and_a_refused_submit_clears_it(tmp_path: Path) -> None:
    def fails(status: int | None) -> Any:
        def transport(method: str, url: str, headers: Any, body: bytes | None, timeout: float) -> Response:
            if status is None:
                raise VidgenError("the connection was reset")
            return Response(status, b'{"error": {"message": "nope"}}', {})

        return transport

    unknown = MockVideoProvider(MockOpenRouter())
    unknown._transport = fails(None)
    with pytest.raises(VidgenError, match="(?s)connection was reset.*no known outcome"):
        generate_clip(tmp_path / "net", settings(), request(), pay=True, provider=unknown, catalog=CATALOG)
    assert len(Ledger(ledger_path(tmp_path / "net", "mock")).unresolved_intents()) == 1

    server_error = MockVideoProvider(MockOpenRouter())
    server_error._transport = fails(500)
    with pytest.raises(VidgenError, match="no known outcome"):
        generate_clip(tmp_path / "s500", settings(), request(), pay=True, provider=server_error, catalog=CATALOG)
    assert len(Ledger(ledger_path(tmp_path / "s500", "mock")).unresolved_intents()) == 1

    too_large = MockVideoProvider(MockOpenRouter())
    too_large.request_body = lambda *a, **k: {"x": "y" * (22 * 1024 * 1024)}   # stopped before anything is sent
    with pytest.raises(VidgenError, match="more than vidgen sends"):
        generate_clip(tmp_path / "big", settings(), request(), pay=True, provider=too_large, catalog=CATALOG)
    assert Ledger(ledger_path(tmp_path / "big", "mock")).events() == []


def test_a_crash_after_the_answer_is_covered_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api = MockOpenRouter()
    original = Ledger.append

    def full_disk(self: Ledger, event: str, **fields: Any) -> None:
        if event == "submit":
            raise OSError(28, "No space left on device")
        original(self, event, **fields)

    monkeypatch.setattr(Ledger, "append", full_disk)
    with pytest.raises(OSError):
        generate_clip(tmp_path, settings(), request(), pay=True, provider=MockVideoProvider(api), catalog=CATALOG)
    monkeypatch.undo()
    assert len(api.submits) == 1 and len(Ledger(ledger_path(tmp_path, "mock")).unresolved_intents()) == 1


def test_resolve_lets_the_owner_proceed(tmp_path: Path) -> None:
    # --not-charged: the budget gets it back and the next run pays
    _, ledger = interrupted(tmp_path / "free")
    (intent,) = ledger.unresolved_intents()
    ledger.resolve_intent(intent.intent_id, "not_charged")
    assert ledger.spent() == 0.0
    fresh = MockOpenRouter(cost=0.2)
    assert generate_clip(tmp_path / "free", settings(), request(), pay=True, provider=MockVideoProvider(fresh), catalog=CATALOG).paid
    assert len(fresh.submits) == 1 and ledger.unresolved_intents() == []
    # --job: the next run polls that job and pays nothing
    api, ledger = interrupted(tmp_path / "job")
    (intent,) = ledger.unresolved_intents()
    ledger.resolve_intent(intent.intent_id, "job", job_id="mock-job-1")
    assert [j.job_id for j in ledger.jobs()] == ["mock-job-1"] and ledger.spent() == pytest.approx(0.12)
    result = generate_clip(tmp_path / "job", settings(), request(), pay=True, provider=MockVideoProvider(api), catalog=CATALOG)
    assert result.paid is True and result.plan.previous_job is not None and len(api.submits) == 1   # no new POST
    # --charged with the amount: counts that amount; a later run may pay for the request again
    _, ledger = interrupted(tmp_path / "charged")
    (intent,) = ledger.unresolved_intents()
    ledger.resolve_intent(intent.intent_id, "charged", cost_usd=0.5)
    assert ledger.spent() == 0.5
    # errors: an unknown id names what is open, a second answer is refused, a known job id is refused
    with pytest.raises(VidgenError, match=r"no intent 'intent-nope'.*unresolved: none"):
        ledger.resolve_intent("intent-nope", "not_charged")
    with pytest.raises(VidgenError, match="already resolved"):
        ledger.resolve_intent(intent.intent_id, "not_charged")
    _, other = interrupted(tmp_path / "dup")
    (dup,) = other.unresolved_intents()
    other.resolve_intent(dup.intent_id, "job", job_id="mock-job-1")
    with pytest.raises(VidgenError, match="already resolved"):
        other.resolve_intent(dup.intent_id, "job", job_id="mock-job-1")
    other.append("submit_intent", intent_id="intent-b", provider="mock", model="m", request_hash="h", estimate_usd=0.1)
    with pytest.raises(VidgenError, match="already in the ledger"):
        other.resolve_intent("intent-b", "job", job_id="mock-job-1")


def test_old_ledger_lines_still_read(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    ledger.append("submit", job_id="a", provider="openrouter", model="m/x", request_hash="h", estimate_usd=0.5)   # no intent_id
    ledger.append("completed", job_id="a", cost_usd=0.4, is_byok=False)
    assert ledger.intents() == [] and ledger.spent() == pytest.approx(0.4)


# ----- every reader of the ledger shows it: plan, run, status, generate ledger, resolve ------------


def test_plan_run_status_ledger_and_cli_show_it(make_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(shot_config(WIDE, style_sheet=None))
    project = Project.load(root)
    monkeypatch.setattr("vidgen.videogen.models.load_catalog", lambda *a, **k: CATALOG)
    first = plan_shots(project, catalog=CATALOG).shots[0]
    ledger = Ledger(ledger_path(root, "mock"))
    intent = ledger.record_intent("mock", first.request.model, request_hash(first.request), 0.3)
    orphan = ledger.record_intent("mock", "m/other", "other-hash", 0.1)   # an edited request: nothing to block, still counted

    item = plan_shots(project, catalog=CATALOG).shots[0]
    assert item.unresolved_intent == intent and item.cost == 0.0
    assert any("no known outcome" in b for b in item.shot.blocked)
    plan = plan_shots(project, catalog=CATALOG)
    assert plan.budget.spent_usd == pytest.approx(0.4) and {i.intent_id for i in plan.unresolved_intents} == {intent.intent_id, orphan.intent_id}
    assert any("unresolved submit" in line for line in plan.lines(root))
    api = MockOpenRouter()
    with pytest.raises(VidgenError, match="not paying: an earlier submit has no known outcome"):
        run_shots(project, pay=True, provider=MockVideoProvider(api), catalog=CATALOG, out=lambda line: None)
    assert api.requests == []
    assert run_shots(project, pay=False, provider=MockVideoProvider(api), catalog=CATALOG, out=lambda line: None).shots[0].status == "blocked"

    lines, doc = status_lines(project, CATALOG)
    assert any("unresolved submit" in line and intent.intent_id in line for line in lines) and doc["spent_usd"] == pytest.approx(0.4)
    assert {i["intent_id"] for i in doc["unresolved_intents"]} == {intent.intent_id, orphan.intent_id}

    assert cli.main(["generate", "ledger", str(root)]) == 0
    out = capsys.readouterr().out
    assert "unresolved submit: " in out and intent.intent_id in out and "counted at the estimate $0.300" in out and "spent $0.400" in out
    assert cli.main(["generate", "ledger", str(root), "--json"]) == 0
    assert {i["intent_id"] for i in json.loads(capsys.readouterr().out)["intents"]} == {intent.intent_id, orphan.intent_id}
    assert cli.main(["generate", "plan", str(root), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["shots"][0]["unresolved_intent"] == intent.intent_id and len(doc["unresolved_intents"]) == 2

    # CLI resolve: the options are checked, then the shot is free to run again
    assert cli.main(["generate", "resolve", str(root)]) != 0
    capsys.readouterr()
    assert cli.main(["generate", "resolve", str(root), "--intent", intent.intent_id, "--not-charged", "--job", "x"]) != 0
    capsys.readouterr()
    assert cli.main(["generate", "resolve", str(root), "--intent", intent.intent_id, "--not-charged"]) == 0
    assert "not charged" in capsys.readouterr().out
    assert cli.main(["generate", "resolve", str(root), "--intent", orphan.intent_id, "--charged", "--cost", "0.2", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["intent"]["outcome"] == "charged"
    assert ledger.unresolved_intents() == [] and ledger.spent() == pytest.approx(0.2)
    item = plan_shots(project, catalog=CATALOG).shots[0]
    assert item.unresolved_intent is None and not any("no known outcome" in b for b in item.shot.blocked) and item.cost > 0
