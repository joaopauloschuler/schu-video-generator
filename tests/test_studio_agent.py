"""``vidgen studio`` Step 198 (DESIGN.md §94.16): listening notes (pinned at a moment, placed in
later versions when sections change length), "Ask an agent" (the hand-off, pasted replies, the
inbox MCP agents write to, keep / discard) and the optional OpenRouter provider — mocked: no
network, no key read but a fake one set here. The MCP tools themselves are in ``test_mcp.py``."""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from vidgen.errors import VidgenError
from vidgen.studio_app import agent
from vidgen.studio_app.agent import agent_propose, agent_read, agent_sessions, find_session, parse_reply
from vidgen.studio_app.app import StudioApp
from vidgen.studio_app.notes import locate, place
from vidgen.studio_app.server import StudioServer, start_in_thread
from vidgen.studio_app.session import write_open_marker

#: Three two-bar sections of kicks at 120 BPM (a bar is 2 s): 12 s.
SCORE = """\
# three parts
title: Three
key: A minor
tempo: 120
sections: [{name: a, bars: 2}, {name: b, bars: 2}, {name: c, bars: 2}]
tracks:
  kick: {instrument: kick, steps: "x... x... x... x..."}
"""


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StudioApp:
    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv(agent.MODEL_ENV, raising=False)
    root = tmp_path / "root"
    root.mkdir()
    return StudioApp(root, studio=root / "build" / "studio")


def outline_of(app: StudioApp) -> dict[str, Any]:
    return app.state()["score"]["outline"]


# ----- notes --------------------------------------------------------------------------------


def test_locate_and_place_follow_the_sections(app: StudioApp) -> None:
    app.load(text=SCORE)
    outline = outline_of(app)
    at = locate(outline, 7.0)  # bar 4 of the piece = bar 2 of b, its second beat (a beat is 0.5 s)
    assert at == {"seconds": 7.0, "bar": 4, "beat": 3, "section": "b", "bar_in_section": 2, "frac": 0.5}
    note = {**at, "version": 1}
    assert place(outline, note)["moved"] is None and place(outline, note)["seconds"] == 7.0
    longer = {**outline, "sections": [{**outline["sections"][0], "bars": 4}, {**outline["sections"][1], "start": 8.0, "first_bar": 5},
                                      {**outline["sections"][2], "start": 12.0, "first_bar": 7}]}
    moved = place(longer, note)
    assert (moved["bar"], moved["section"], moved["seconds"]) == (6, "b", 11.0) and "was bar 4 on v1" in moved["moved"]
    shorter = {**outline, "sections": [outline["sections"][0], {**outline["sections"][1], "bars": 1}, {**outline["sections"][2], "start": 6.0, "first_bar": 4}]}
    assert "the b is 1 bar now" in place(shorter, note)["moved"] and place(shorter, note)["bar"] == 3
    gone = {**outline, "sections": [outline["sections"][0], {**outline["sections"][2], "start": 4.0, "first_bar": 3}]}
    assert place(gone, note)["bar"] == 4 and "the b is gone: kept at bar 4 (in the c)" == place(gone, note)["moved"]
    assert locate(outline, 99)["bar"] == 6  # past the end: the last bar


def test_notes_are_pinned_edited_resolved_and_carried_over(app: StudioApp) -> None:
    app.load(text=SCORE)
    revision = app.state()["revision"]
    doc = app.add_note(None, 7.0, "  this part   drags ")
    assert doc["note"] == "n1" and doc["revision"] > revision
    [note] = doc["notes"]
    assert (note["text"], note["bar"], note["beat"], note["section"], note["version"], note["status"]) == ("this part drags", 4, 3, "b", 1, "open")
    app.add_note(1, 0.2, "love the start")
    with pytest.raises(VidgenError, match="a few words"):
        app.add_note(1, 1.0, "   ")
    # a new version where section a is longer: the note stays in bar 2 of b, which is bar 6 now
    doc = app.edit(None, [{"op": "set", "path": "sections[0].bars", "value": 4}])
    n1 = next(n for n in doc["notes"] if n["id"] == "n1")
    assert n1["at"]["bar"] == 6 and n1["at"]["seconds"] == 11.0 and "changed length" in n1["at"]["moved"]
    doc = app.update_note("n1", text="drags a bit", status="resolved")
    assert next(n for n in doc["notes"] if n["id"] == "n1")["status"] == "resolved"
    with pytest.raises(VidgenError, match="status is one of"):
        app.update_note("n1", status="maybe")
    doc = app.update_note("n2", delete=True)
    assert [n["id"] for n in doc["notes"]] == ["n1"]
    with pytest.raises(VidgenError, match="no note 'n9'"):
        app.update_note("n9", text="x")
    assert json.loads((Path(doc["session"]["folder"]) / "notes.json").read_text(encoding="utf-8"))["next"] == 3


# ----- the hand-off and replies ---------------------------------------------------------------


def test_ask_writes_the_hand_off(app: StudioApp) -> None:
    app.load(text=SCORE)
    app.edit(None, [{"op": "set", "path": "tempo", "value": 100}])
    app.add_note(None, 1.0, "kick too stiff")
    app.add_note(None, 9.0, "lift it here")
    app.update_note("n2", status="resolved")
    doc = app.ask()
    request = doc["request"]
    assert request["base"] == 2 and [n["id"] for n in request["notes"]] == ["n1"] and request["check"] is None
    assert request["diff"]["parent"] == 1 and "+tempo: 100" in request["diff"]["diff"] and request["diff"]["changed_lines"] == 2
    saved = json.loads(Path(doc["file"]).read_text(encoding="utf-8"))
    assert saved["score"] == app.state()["score"]["text"] and saved["id"] == request["id"]
    prompt = doc["prompt"]
    assert '- n1: bar 1, beat 2, in the a (1.0 s): "kick too stiff"' in prompt and "lift it here" not in prompt
    assert "```yaml\n# three parts" in prompt and "one line per note" in prompt and "(not checked yet)" in prompt
    assert doc["provider"] == {"name": "OpenRouter", "key_env": "OPENROUTER_API_KEY", "key_set": False, "model": None, "model_env": agent.MODEL_ENV}


def test_parse_reply_reads_the_usual_shapes() -> None:
    reply = "summary: softer kick\nHere it is:\n```yaml\ntitle: X\ntracks: {}\n```\n- **n1**: lowered the kick by 3 dB so it sits back\nn2 — nothing: it was fine\n"
    parsed = parse_reply(reply)
    assert parsed == {"score": "title: X\ntracks: {}\n", "explanations": {"n1": "lowered the kick by 3 dB so it sits back", "n2": "nothing: it was fine"},
                      "summary": "softer kick"}
    assert parse_reply("```\nkey: A\n```\n```yaml\ntracks: {}\n```")["score"] == "tracks: {}\n"  # the yaml block wins
    assert parse_reply(SCORE)["score"] == SCORE  # no code block: the whole text when it reads as a score
    assert parse_reply("I could not do it.") == {"score": None, "explanations": {}, "summary": None}


def test_pasted_reply_becomes_a_proposal_to_keep(app: StudioApp) -> None:
    app.load(text=SCORE)
    app.add_note(None, 1.0, "kick too loud")
    app.add_note(None, 5.0, "b is fine")
    with pytest.raises(VidgenError, match="ask an agent first"):
        app.paste_reply("x")
    request = app.ask()["request"]
    louder = SCORE.replace('steps: "x... x... x... x..."}', 'steps: "x... x... x... x...", volume: -3}')
    doc = app.paste_reply(f"summary: kick down\n```yaml\n{louder}```\nn1: kick volume -3 dB\nn7: who?\n")
    [proposal] = doc["proposals"]
    assert (proposal["status"], proposal["base"], proposal["version"], proposal["source"], proposal["request"]) == ("pending", 1, 2, "paste", request["id"])
    assert proposal["unknown_notes"] == ["n7"] and proposal["summary"] == "kick down"
    session = doc["session"]
    assert session["current"] == 1 and session["versions"][-1]["origin"] == "agent" and session["versions"][-1]["label"] == "agent: kick down"
    n1 = next(n for n in doc["notes"] if n["id"] == "n1")
    assert n1["answers"] == [{"proposal": "p1", "version": 2, "by": "paste", "text": "kick volume -3 dB", "status": "pending"}]
    doc = app.decide_proposal("p1", keep=True)
    assert doc["session"]["current"] == 2 and doc["proposals"][0]["status"] == "kept"
    assert {n["id"]: n["status"] for n in doc["notes"]} == {"n1": "resolved", "n2": "open"}
    assert doc["notes"][0]["answers"][0]["status"] == "kept"
    with pytest.raises(VidgenError, match="already kept"):
        app.decide_proposal("p1", keep=False)


def test_invalid_or_unchanged_proposals_are_shown_and_never_kept(app: StudioApp) -> None:
    app.load(text=SCORE)
    app.add_note(None, 1.0, "kick")
    app.ask()
    doc = app.paste_reply("```yaml\n" + SCORE.replace("instrument: kick", "instrument: kik") + "```\nn1: tried")
    bad = doc["proposals"][0]
    assert bad["status"] == "invalid" and bad["version"] is None and "did you mean 'kick'" in bad["problems"][0]["message"]
    assert len(doc["session"]["versions"]) == 1 and "text" not in bad
    with pytest.raises(VidgenError, match="cannot be kept"):
        app.decide_proposal(bad["id"], keep=True)
    assert app.paste_reply("```yaml\n" + SCORE + "```")["proposals"][1]["problems"][0]["message"] == "the score is the same as v1: nothing changed"
    assert "holds no score" in app.paste_reply("sorry")["proposals"][2]["problems"][0]["message"]
    doc = app.decide_proposal(bad["id"], keep=False)
    assert doc["proposals"][0]["status"] == "discarded"


def test_discarded_proposal_stays_in_the_history(app: StudioApp) -> None:
    app.load(text=SCORE)
    app.ask()
    app.paste_reply("```yaml\n" + SCORE.replace("tempo: 120", "tempo: 110") + "```")
    doc = app.decide_proposal("p1", keep=False)
    assert doc["session"]["current"] == 1 and doc["session"]["versions"][1]["label"].startswith("discarded · agent:")


# ----- the inbox (what MCP agents write) --------------------------------------------------------


def test_mcp_side_reads_proposes_and_the_studio_picks_it_up(app: StudioApp, tmp_path: Path) -> None:
    root = app.project_root
    assert root is not None
    with pytest.raises(VidgenError, match="no studio has a session open"):
        find_session(root, None)
    app.load(text=SCORE)
    app.url = "http://127.0.0.1:9/"
    write_open_marker(app.studio, app.url, app.session.id)  # type: ignore[union-attr]
    app.add_note(None, 1.0, "kick too stiff")
    app.ask()
    listed = agent_sessions(root)["sessions"]
    assert listed[0]["id"] == app.session.id and listed[0]["open"] and listed[0]["open_notes"] == 1  # type: ignore[union-attr]
    assert listed[0]["request"]["answered"] is False and listed[0]["url"] == "http://127.0.0.1:9/"
    read = agent_read(root)
    assert read["base"] == 1 and read["notes"][0]["id"] == "n1" and read["id"] and "studio_propose" in read["how_to_answer"]
    assert read["check"] is None and "studio_check" in read["check_note"]

    with pytest.raises(VidgenError, match="did you mean 'kick'"):
        agent_propose(root, SCORE.replace("instrument: kick", "instrument: kik"))
    with pytest.raises(VidgenError, match="the same as v1"):
        agent_propose(root, SCORE)
    with pytest.raises(VidgenError, match="not a note id"):
        agent_propose(root, SCORE, {"note1": "x"})
    with pytest.raises(VidgenError, match="no studio session 20990101"):
        agent_propose(root, SCORE, session_id="20990101-000000-abcd")
    swung = SCORE.replace('"x... x... x... x..."', '"x... ..x. x... ..x."')
    doc = agent_propose(root, swung, {"n1": "moved two kicks off the beat"}, "swing the kick", "test-agent")
    assert doc["studio_open"] and doc["base"] == 1 and doc["missing_notes"] == [] and Path(doc["file"]).is_file()
    assert agent_sessions(root)["sessions"][0]["pending_proposals"] == 1

    revision = app.state()["revision"]
    polled = app.poll(revision)
    assert polled["made"] == ["p1"] and not Path(doc["file"]).exists()
    proposal = polled["proposals"][0]
    assert (proposal["source"], proposal["agent"], proposal["version"], proposal["request"]) == ("mcp", "test-agent", 2, read["id"])
    assert polled["session"]["versions"][1]["label"] == "agent: swing the kick" and polled["session"]["current"] == 1
    assert app.poll(polled["revision"]) == {"revision": polled["revision"], "unchanged": True}
    assert agent_sessions(root)["sessions"][0]["request"]["answered"] is True
    assert agent_read(root, version=2)["score"] == swung


def test_unreadable_inbox_file_becomes_an_invalid_proposal(app: StudioApp) -> None:
    app.load(text=SCORE)
    inbox = Path(app.state()["session"]["folder"]) / "inbox"
    inbox.mkdir()
    (inbox / "20260101-000000-abcdef.json").write_text("{nope", encoding="utf-8")
    (inbox / "ignored.txt").write_text("x", encoding="utf-8")
    doc = app.poll(None)
    assert doc["proposals"][0]["status"] == "invalid" and "could not be read" in doc["proposals"][0]["problems"][0]["message"]
    assert (inbox / "ignored.txt").exists() and not (inbox / "20260101-000000-abcdef.json").exists()


# ----- the provider (mocked: no network) --------------------------------------------------------


def test_provider_is_mocked_and_its_reply_becomes_a_proposal(app: StudioApp, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import httpapi

    app.load(text=SCORE)
    app.add_note(None, 1.0, "kick too stiff")
    app.ask()
    sent: list[dict[str, Any]] = []
    reply = "summary: lighter kick\n```yaml\n" + SCORE.replace("tempo: 120", "tempo: 118") + "```\nn1: a touch slower"

    def fake_post(url: str, data: bytes, **kw: Any) -> bytes:
        sent.append({"url": url, "body": json.loads(data), "headers": kw["headers"], "secret": kw["secret"]})
        return json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}]}).encode()

    monkeypatch.setattr(httpapi, "post_with_retries", fake_post)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(VidgenError, match="OPENROUTER_API_KEY is not set"):
        app.send_to_provider("vendor/model")
    assert sent == []
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-a-key")
    with pytest.raises(VidgenError, match="name an OpenRouter model"):
        app.send_to_provider("  ")
    assert app.info()["provider"]["key_set"] is True and "sk-or" not in json.dumps(app.info())
    doc = app.send_to_provider("vendor/model")
    [call] = sent
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions" and call["body"]["model"] == "vendor/model"
    assert call["body"]["messages"][0]["content"].startswith("# Music to change") and call["secret"] == "sk-or-test-not-a-key"
    proposal = doc["proposals"][0]
    assert (proposal["status"], proposal["source"], proposal["agent"], proposal["summary"]) == ("pending", "openrouter", "vendor/model", "lighter kick")
    monkeypatch.setattr(httpapi, "post_with_retries", lambda url, data, **kw: b'{"choices": []}')
    with pytest.raises(VidgenError, match="not a chat reply"):
        app.send_to_provider("vendor/model")


# ----- routes -----------------------------------------------------------------------------------


@pytest.fixture
def server(app: StudioApp) -> Iterator[StudioServer]:
    srv, thread = start_in_thread(app)
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(5)


def call(srv: StudioServer, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    headers = {"Host": f"127.0.0.1:{srv.port}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
    response = conn.getresponse()
    out = response.status, json.loads(response.read())
    conn.close()
    return out


def test_routes(server: StudioServer, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import httpapi

    # never the real provider, whatever this machine's environment holds (Step 201)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(httpapi, "post_with_retries", lambda *a, **kw: pytest.fail("no network in tests"))
    assert call(server, "POST", "/api/load", {"text": SCORE})[0] == 200
    status, doc = call(server, "POST", "/api/notes", {"seconds": 3.0, "text": "here"})
    assert status == 200 and doc["result"]["notes"][0]["bar"] == 2
    assert call(server, "POST", "/api/notes", {"seconds": "x", "text": "here"})[0] == 400
    revision = doc["result"]["revision"]
    assert call(server, "GET", f"/api/session?since={revision}")[1]["result"] == {"revision": revision, "unchanged": True}
    status, doc = call(server, "POST", "/api/notes/update", {"id": "n1", "status": "resolved"})
    assert doc["result"]["notes"][0]["status"] == "resolved"
    status, doc = call(server, "POST", "/api/ask", {})
    assert status == 200 and doc["result"]["prompt"].startswith("# Music to change")
    status, doc = call(server, "POST", "/api/proposal/paste", {"reply": "```yaml\n" + SCORE.replace("tempo: 120", "tempo: 90") + "```"})
    assert status == 200 and doc["result"]["proposals"][0]["version"] == 2
    assert call(server, "POST", "/api/proposal/decide", {"id": "p1", "keep": "yes"})[0] == 400
    status, doc = call(server, "POST", "/api/proposal/decide", {"id": "p1", "keep": True})
    assert doc["result"]["session"]["current"] == 2
    status, doc = call(server, "POST", "/api/proposal/send", {"model": "x/y"})
    assert status == 400 and "confirm" in doc["error"]  # it costs money: only after the person confirmed
    status, doc = call(server, "POST", "/api/proposal/send", {"model": "x/y", "confirm": True})
    assert status == 400 and "OPENROUTER_API_KEY" in doc["error"]
