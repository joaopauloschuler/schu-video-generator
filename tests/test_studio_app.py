"""``vidgen studio`` (Step 193, DESIGN.md §94): the app's logic without HTTP (presets, sessions,
checking score text, rendering and the render cache) and the HTTP server (static files, JSON
API, range requests, the Host / Origin / content-type guards). Browser tests are in
``test_studio_ui.py``."""

from __future__ import annotations

import http.client
import json
import os
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.music import BUILTIN_BEDS
from vidgen.sfx import RATE
from vidgen.studio import music_template_text
from vidgen.studio_app.app import ONE_LINE_CHARS, StudioApp, check_text, line_of, one_line, render_key
from vidgen.studio_app.server import STATIC_DIR, StudioServer, _byte_range, _ApiError, start_in_thread
from vidgen.studio_app.session import OPEN_FILE, StudioSession, find_project_root, remove_open_marker, studio_dir, write_open_marker

#: Two one-bar sections of kicks at 120 BPM: 4 s, renders in a fraction of a second.
TINY = """\
# a tiny score
title: Tiny
key: A minor
tempo: 120
sections: [{name: a, bars: 1}, {name: b, bars: 1}]
tracks:
  kick: {instrument: kick, steps: "x... x... x... x..."}
"""


@pytest.fixture
def app(tmp_path: Path) -> StudioApp:
    return StudioApp(None, studio=tmp_path / "studio")


# ----- presets and session folders -------------------------------------------------------------


def test_presets_are_the_17_beds_with_one_line_descriptions(app: StudioApp) -> None:
    presets = app.presets()
    assert [p["name"] for p in presets] == list(BUILTIN_BEDS)
    assert len(presets) == 17
    for p in presets:
        assert 20 <= len(p["one_line"]) <= ONE_LINE_CHARS, p["one_line"]
        assert p["key"] and p["tempo"] and p["sections"] and p["tracks"] and p["use"]
    by_name = {p["name"]: p for p in presets}
    assert by_name["calm"]["one_line"] == "A slow, warm ambient pad with no beat"
    assert by_name["tidewater"]["score_bed"] and not by_name["momentum"]["score_bed"]


def test_one_line_cuts_at_a_comma() -> None:
    long = "A curious, forward-moving tech-documentary bed at 108 BPM in B minor, 4/4, written as a score file (made by an AI author)"
    assert one_line(long) == "A curious, forward-moving tech-documentary bed at 108 BPM in B minor, 4/4"
    assert one_line("A two-part bed at 112 BPM, that lifts 25.7 s into the loop. More.") == "A two-part bed at 112 BPM, that lifts 25.7 s into the loop"


def test_studio_dir_project_or_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path / "cache"))
    assert studio_dir(None) == tmp_path / "cache" / "studio"
    project = tmp_path / "proj"
    project.mkdir()
    assert find_project_root(None, project) is None
    (project / "video.yaml").write_text("title: x\n", encoding="utf-8")
    assert find_project_root(None, project) == project.resolve()
    assert find_project_root(str(project / "video.yaml"), tmp_path) == project.resolve()
    assert studio_dir(project) == project / "build" / "studio"
    with pytest.raises(VidgenError, match="project not found"):
        find_project_root(str(tmp_path / "nope"), tmp_path)


def test_load_a_preset_starts_a_session_with_version_1(app: StudioApp) -> None:
    doc = app.load(preset="tidewater")
    session = doc["session"]
    folder = Path(session["folder"])
    assert session["preset"] == "tidewater" and session["current"] == 1 and session["title"] == "Tidewater"
    assert (folder / "versions" / "v0001.yaml").read_text(encoding="utf-8") == music_template_text("tidewater")
    saved = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert saved["versions"][0] == {**saved["versions"][0], "number": 1, "parent": None, "origin": "preset"}
    score = doc["score"]
    assert score["version"] == 1 and score["problems"] == [] and score["text"].startswith("# Tidewater")
    outline = score["outline"]
    assert [s["name"] for s in outline["sections"]] == ["intro", "build", "lift", "outro"]
    assert [s["first_bar"] for s in outline["sections"]] == [1, 5, 13, 21]
    assert outline["progression"]["text"] == "i VI III VII" and outline["progression"]["written"] == "text"
    tracks = {t["name"]: t for t in outline["tracks"]}
    assert tracks["kick"]["steps"] == "x... x... x... x..." and tracks["pad"]["steps"] == "chords"
    assert tracks["pad"]["settings"] == {"tone": 1800, "air": 0.3}
    # a second load is a new session; the first stays on disk
    again = app.load(preset="calm")
    assert again["session"]["id"] != session["id"] and folder.is_dir()
    assert StudioSession.open(app.studio, session["id"]).preset == "tidewater"


def test_load_refuses_unknown_presets_and_bad_text(app: StudioApp) -> None:
    with pytest.raises(VidgenError, match="did you mean 'tidewater'"):
        app.load(preset="tidewatter")
    with pytest.raises(VidgenError, match="tracks.kick.instrument: unknown instrument"):
        app.load(text=TINY.replace("instrument: kick", "instrument: kik"))
    assert app.session is None
    with pytest.raises(VidgenError, match="give a preset or a score"):
        app.load()


def test_session_ids_are_checked(tmp_path: Path) -> None:
    with pytest.raises(VidgenError, match="not a studio session id"):
        StudioSession.open(tmp_path, "../x")


def test_open_marker_is_removed_only_by_its_writer(tmp_path: Path) -> None:
    write_open_marker(tmp_path, "http://127.0.0.1:1/", "s")
    doc = json.loads((tmp_path / OPEN_FILE).read_text(encoding="utf-8"))
    assert doc["pid"] == os.getpid() and doc["url"] == "http://127.0.0.1:1/"
    (tmp_path / OPEN_FILE).write_text(json.dumps({**doc, "pid": -1}), encoding="utf-8")
    remove_open_marker(tmp_path)
    assert (tmp_path / OPEN_FILE).exists()
    write_open_marker(tmp_path, "http://127.0.0.1:1/", None)
    remove_open_marker(tmp_path)
    assert not (tmp_path / OPEN_FILE).exists()


# ----- checking score text ---------------------------------------------------------------------


def test_validate_reports_problems_with_lines_and_did_you_mean(app: StudioApp) -> None:
    assert app.validate(TINY)["ok"]
    bad = TINY.replace("tempo: 120", "tempo: 400").replace("instrument: kick", "instrument: kik")
    doc = app.validate(bad)
    assert not doc["ok"] and doc["outline"] is None
    problems = {p["where"]: p for p in doc["problems"]}
    assert problems["tempo"]["line"] == 4 and "out of range" in problems["tempo"]["message"]
    assert problems["tracks.kick.instrument"]["line"] == 7 and "did you mean 'kick'" in problems["tracks.kick.instrument"]["message"]


def test_validate_yaml_syntax_error_has_its_line(app: StudioApp) -> None:
    doc = app.validate("key: A minor\ntracks: {kick: [\n")
    assert not doc["ok"] and doc["problems"][0]["message"].startswith("not valid YAML")
    assert doc["problems"][0]["line"] == 3


def test_line_of_paths() -> None:
    text = "sections:\n  - {name: a, bars: 1}\n  - name: b\n    bars: 2\ntracks:\n  kick:\n    steps: x\n"
    assert line_of(text, "sections[1].bars") == 4
    assert line_of(text, "tracks.kick.steps") == 7
    assert line_of(text, "tracks.kick.volume") == 6  # missing: its parent
    assert line_of(text, "nope") is None


def test_render_key_ignores_comments_and_layout() -> None:
    data, score, _ = check_text(TINY)
    other, _, _ = check_text(TINY.replace("# a tiny score\n", "").replace("tempo: 120", "tempo:   120   # fast"))
    assert score is not None and render_key(data) == render_key(other)
    changed, _, _ = check_text(TINY.replace("tempo: 120", "tempo: 121"))
    assert render_key(changed) != render_key(data)


# ----- rendering ---------------------------------------------------------------------------------


def test_render_writes_a_cached_audition_wav_and_cuts_sections(app: StudioApp) -> None:
    app.load(text=TINY)
    first = app.render()
    assert not first["cached"] and first["seconds"] == 4.0 and first["loop"]
    assert abs(first["loudness"] + 28) < 0.1 and first["audition_gain_db"] == 12.0
    wav_path = app.audio_file(f"{first['key']}.wav")
    assert wav_path is not None and first["url"] == f"/audio/{first['key']}.wav"
    with wave.open(str(wav_path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (2, 2, RATE, 4 * RATE)
        whole = w.readframes(w.getnframes())
    assert app.render()["cached"]
    part = app.render(section="b")
    assert part["section"] == {"name": "b", "start": 2.0, "seconds": 2.0}
    cut = app.audio_file(part["url"].rsplit("/", 1)[1])
    assert cut is not None
    with wave.open(str(cut)) as w:
        assert w.readframes(w.getnframes()) == whole[2 * RATE * 4 :]  # bit-exact: 4 bytes a frame
    with pytest.raises(VidgenError, match="no section 'c'"):
        app.render(section="c")


def test_render_needs_a_session_and_audio_names_are_checked(app: StudioApp) -> None:
    with pytest.raises(VidgenError, match="load a preset first"):
        app.render()
    app.load(text=TINY)
    for name in ("../session.json", "x.wav", "0123456789abcdef0123.mp3", "0123456789abcdef0123-../a.wav"):
        assert app.audio_file(name) is None
    assert app.audio_file("0123456789abcdef0123.wav") is None  # well-formed, not rendered


# ----- the HTTP server ---------------------------------------------------------------------------


@pytest.fixture
def server(app: StudioApp) -> Iterator[StudioServer]:
    srv, thread = start_in_thread(app)
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(5)


def request(srv: StudioServer, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    data = None
    sent = {"Host": f"127.0.0.1:{srv.port}", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        sent.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=data, headers=sent)
    response = conn.getresponse()
    out = response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    conn.close()
    return out


def test_server_serves_the_page_and_the_api(server: StudioServer) -> None:
    status, headers, body = request(server, "GET", "/")
    assert status == 200 and headers["content-type"].startswith("text/html") and b"vidgen studio" in body
    assert "default-src 'self'" in headers["content-security-policy"]
    for name in ("app.js", "api.js", "player.js", "yaml_view.js", "studio.css", "favicon.svg"):
        status, headers, _ = request(server, "GET", f"/static/{name}")
        assert status == 200, name
    assert request(server, "GET", "/static/app.js")[1]["content-type"].startswith("text/javascript")
    assert request(server, "GET", "/fonts/Inter-Regular.ttf")[0] == 200
    status, _, body = request(server, "GET", "/api/presets")
    assert status == 200 and len(json.loads(body)["result"]) == 17
    patches = json.loads(request(server, "GET", "/api/patches")[2])["result"]
    assert {"instruments", "effects"} <= set(patches)
    assert json.loads(request(server, "GET", "/api/session")[2])["result"] == {"session": None, "score": None}


def test_server_refuses_what_it_must(server: StudioServer) -> None:
    assert request(server, "GET", "/", headers={"Host": "evil.example:80"})[0] == 403
    assert request(server, "GET", "/static/../app.py")[0] == 404
    assert request(server, "GET", "/static/%2e%2e/app.py")[0] == 404
    assert request(server, "GET", "/audio/../session.json")[0] == 404
    assert request(server, "POST", "/api/load", {"preset": "calm"}, headers={"Origin": "http://evil.example"})[0] == 403
    assert request(server, "POST", "/api/load", {"preset": "calm"}, headers={"Content-Type": "text/plain"})[0] == 415
    status, _, body = request(server, "POST", "/api/render", {})
    assert status == 400 and "load a preset first" in json.loads(body)["error"]
    status, _, body = request(server, "POST", "/api/validate", {"text": 3})
    assert status == 400 and "expected text" in json.loads(body)["error"]


def test_server_loads_renders_and_streams_ranges(server: StudioServer) -> None:
    status, _, body = request(server, "POST", "/api/load", {"text": TINY}, headers={"Origin": f"http://localhost:{server.port}"})
    assert status == 200 and json.loads(body)["result"]["session"]["current"] == 1
    render = json.loads(request(server, "POST", "/api/render", {"version": 1})[2])["result"]
    status, headers, whole = request(server, "GET", render["url"])
    assert status == 200 and headers["accept-ranges"] == "bytes" and headers["content-type"] == "audio/wav"
    assert int(headers["content-length"]) == len(whole) == 44 + 4 * RATE * 4
    status, headers, part = request(server, "GET", render["url"], headers={"Range": "bytes=100-199"})
    assert status == 206 and part == whole[100:200] and headers["content-range"] == f"bytes 100-199/{len(whole)}"
    status, _, tail = request(server, "GET", render["url"], headers={"Range": "bytes=-10"})
    assert status == 206 and tail == whole[-10:]
    assert request(server, "GET", render["url"], headers={"Range": f"bytes={len(whole)}-"})[0] == 416
    score = json.loads(request(server, "GET", "/api/score?version=1")[2])["result"]
    assert score["text"] == TINY and score["render_key"] == render["key"]
    assert request(server, "GET", "/api/score?version=x")[0] == 400


def test_a_port_in_use_is_a_clear_error(server: StudioServer, app: StudioApp) -> None:
    with pytest.raises(VidgenError, match=f"cannot listen on 127.0.0.1:{server.port}.*another --port"):
        StudioServer(app, server.port)


def test_byte_range() -> None:
    assert _byte_range(None, 10) is None
    assert _byte_range("bytes=2-", 10) == (2, 9)
    assert _byte_range("bytes=2-50", 10) == (2, 9)
    assert _byte_range("bytes=-3", 10) == (7, 9)
    assert _byte_range("bytes=0-1,4-5", 10) is None  # several ranges: the whole file
    with pytest.raises(_ApiError):
        _byte_range("bytes=10-", 10)


def test_static_dir_ships_the_page() -> None:
    names = {p.name for p in STATIC_DIR.iterdir()}
    assert {"index.html", "studio.css", "app.js", "api.js", "player.js", "yaml_view.js", "favicon.svg"} <= names
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html  # works offline: no CDN


def test_cli_studio_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Any] = []
    monkeypatch.setattr("vidgen.studio_app.run_studio", lambda root, port, open_browser: calls.append((root, port, open_browser)))
    monkeypatch.chdir(tmp_path)
    assert cli.main(["studio", "--port", "8765", "--no-browser"]) == 0
    assert calls == [(None, 8765, False)]
    assert cli.main(["studio", "--port", "70000"]) == 1
