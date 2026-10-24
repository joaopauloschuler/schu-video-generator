"""Step 201 (DESIGN.md §94.19): the review of Phase T (vidgen studio) — one test per attack checked
(Host / Origin, request bodies, path names of every kind, Windows device names, links out, hostile
YAML, the paid provider's confirmation), Windows-minded behaviour (line ends, a running studio's
session left alone by cleaning), the studio's quick FFT lengths (the same samples within 1e-9 at worst;
videos and beds untouched), long pieces' stems streamed, exports made block by block."""

from __future__ import annotations

import http.client
import json
import math
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from vidgen.errors import VidgenError
from vidgen.sfx import RATE, wav_bytes
from vidgen.studio import effects as fx
from vidgen.studio import music_template_text, parse_music_score, render_music_score
from vidgen.studio.render import _master_filter, mix_track_stems, render_track_stem
from vidgen.studio_app import clean_studio_folder
from vidgen.studio_app.agent import agent_propose, find_session
from vidgen.studio_app.app import MAX_YAML_NODES, StudioApp, check_text
from vidgen.studio_app.exports import EXPORT_NAME, export_audio, save_to_project
from vidgen.studio_app.server import MAX_BODY_BYTES, StudioServer, start_in_thread
from vidgen.studio_app.session import OPEN_FILE, StudioSession, studio_dir
from vidgen.studio_app.stems import StemCache

TINY = """\
# a tiny score
title: Tiny
key: A minor
tempo: 120
progression: "i VI"
sections: [{name: a, bars: 1}, {name: b, bars: 1}]
tracks:
  kick: {instrument: kick, steps: "x... x... x... x..."}
"""


@pytest.fixture
def app(tmp_path: Path) -> Iterator[StudioApp]:
    studio = StudioApp(None, studio=tmp_path / "studio")
    yield studio
    studio.close()


@pytest.fixture
def server(app: StudioApp) -> Iterator[StudioServer]:
    srv, thread = start_in_thread(app)
    yield srv
    srv.shutdown()
    srv.server_close()
    thread.join(5)


def request(srv: StudioServer, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None, raw: bytes | None = None) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    sent = {"Host": f"127.0.0.1:{srv.port}", **(headers or {})}
    data = raw
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        sent.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=data, headers=sent)
    response = conn.getresponse()
    out = response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    conn.close()
    return out


def raw_exchange(srv: StudioServer, data: bytes, wait: float = 5.0) -> bytes:
    """Send raw bytes on one connection; what came back before it closed (or ``wait`` passed)."""
    with socket.create_connection(("127.0.0.1", srv.port), timeout=wait) as sock:
        sock.sendall(data)
        chunks = []
        try:
            while chunk := sock.recv(65536):
                chunks.append(chunk)
        except TimeoutError:
            pass
    return b"".join(chunks)


# ----- the server's guards ------------------------------------------------------------------------


def test_only_this_servers_host_is_answered(server: StudioServer) -> None:
    port = server.port
    for host in ("evil.example", f"evil.example:{port}", f"127.0.0.1:{port + 1}", f"[::1]:{port}", f"127.0.0.1.nip.io:{port}", f"LOCALHOST:{port}", ""):
        assert request(server, "GET", "/api/info", headers={"Host": host})[0] == 403, host
    assert request(server, "GET", "/api/info", headers={"Host": f"localhost:{port}"})[0] == 200
    # no Host header at all (HTTP/1.0 style): refused too
    reply = raw_exchange(server, b"GET /api/info HTTP/1.0\r\n\r\n")
    assert reply.startswith(b"HTTP/1.1 403") or reply.startswith(b"HTTP/1.0 403")


def test_cross_site_posts_are_refused(server: StudioServer) -> None:
    port = server.port
    for origin in ("http://evil.example", "null", f"http://127.0.0.1:{port + 1}", "file://", f"http://localhost.evil.example:{port}"):
        assert request(server, "POST", "/api/load", {"preset": "calm"}, headers={"Origin": origin})[0] == 403, origin
    for kind in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", ""):
        assert request(server, "POST", "/api/load", raw=b'{"preset": "calm"}', headers={"Content-Type": kind})[0] == 415, kind


def test_request_bodies_are_bounded_and_a_bad_length_never_hangs(server: StudioServer) -> None:
    port = server.port
    head = f"POST /api/validate HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\n"
    reply = raw_exchange(server, (head + "Content-Length: -1\r\n\r\n{}").encode())  # read(-1) used to wait for ever
    assert reply.startswith(b"HTTP/1.1 400") and b"bad Content-Length" in reply
    reply = raw_exchange(server, (head + f"Content-Length: {MAX_BODY_BYTES + 1}\r\n\r\n").encode())
    assert reply.startswith(b"HTTP/1.1 413") and b"Connection: close" in reply  # refused before reading, then closed
    reply = raw_exchange(server, (head + "Content-Length: abc\r\n\r\n").encode())
    assert reply.startswith(b"HTTP/1.1 400")
    status, _, body = request(server, "POST", "/api/validate", raw=b"[1, 2]", headers={"Content-Type": "application/json"})
    assert status == 400 and b"JSON object" in body
    assert request(server, "GET", "/api/info")[0] == 200  # still answering


def test_numbers_must_be_finite_whole_where_whole(server: StudioServer) -> None:
    assert request(server, "POST", "/api/load", {"text": TINY})[0] == 200
    for raw in (b'{"seconds": NaN, "text": "x"}', b'{"seconds": Infinity, "text": "x"}', b'{"seconds": -Infinity, "text": "x"}'):
        status, _, body = request(server, "POST", "/api/notes", raw=raw, headers={"Content-Type": "application/json"})
        assert status == 400 and b"expected a number" in body, raw
    for version in ("Infinity", "NaN", "true", "1.5"):
        status, _, body = request(server, "POST", "/api/current", raw=f'{{"version": {version}}}'.encode(), headers={"Content-Type": "application/json"})
        assert status == 400 and b"whole number" in body, version
    assert request(server, "POST", "/api/current", {"version": 1.0})[0] == 200


# ----- names that reach the file system -------------------------------------------------------------


TRAVERSALS = ("../session.json", "..%2fsession.json", "..\\session.json", "%2e%2e/session.json", "C:\\Windows\\win.ini", "C:win.ini",
              "\\\\server\\share\\x.wav", "//server/share/x.wav", "/etc/passwd", "versions/v0001.yaml", "a/../../x.wav", "x.wav%00.yaml")


def test_no_route_reaches_outside_its_folder(server: StudioServer, app: StudioApp) -> None:
    request(server, "POST", "/api/load", {"text": TINY})
    key = json.loads(request(server, "POST", "/api/render", {})[2])["result"]["key"]
    assert request(server, "GET", f"/audio/{key}.wav")[0] == 200
    for prefix in ("/audio/", "/media/", "/download/", "/static/", "/fonts/"):
        for name in TRAVERSALS:
            assert request(server, "GET", prefix + name)[0] == 404, prefix + name
    # the app's own name checks (a decoded name with a newline, a backslash, a drive...)
    for name in (f"{key}.wav\n", f"{key}\\..\\x.wav", f"C:{key}.wav", f"{key}.wav/..", f"{key}-a\n.wav", f"{key.upper()}.wav"):
        assert app.audio_file(name) is None, name
    assert app.download_file("..\\session.json") is None and app.media_file(f"{key}-check.png\n") is None
    for name in ("x.yaml\n", "a/b.yaml", "a\\b.yaml", ".hidden.yaml", "C:x.yaml"):
        assert not EXPORT_NAME.match(name), name


def test_ids_from_requests_are_checked_before_any_path(server: StudioServer, app: StudioApp) -> None:
    request(server, "POST", "/api/load", {"text": TINY})
    for session_id in ("../x", "20260101-000000-abcd\n", "٢٠٢٦٠١٠١-000000-abcd", "20260101-000000-ABCD", "..\\20260101-000000-abcd"):
        status, _, body = request(server, "POST", "/api/open", {"session": session_id})
        assert status == 400 and b"not a studio session id" in body, session_id
    for batch, letter in (("../b0001", "a"), ("b0001\n", "a"), ("b٠٠٠١", "a"), ("b0001", "../a"), ("b0001", "e")):
        status, _, _ = request(server, "POST", "/api/variations/keep", {"batch": batch, "letter": letter})
        assert status in (400, 404), (batch, letter)
        status, _, _ = request(server, "POST", "/api/render", {"variation": f"{batch}/{letter}"})
        assert status in (400, 404), (batch, letter)
    for note in ("n1\n", "../n1", "n0"):
        assert request(server, "POST", "/api/notes/update", {"id": note, "text": "x"})[0] == 400, note
    for key in ("../x", "0" * 20 + "%0A", "0" * 19, "..%2F..%2Fsession"):  # a query is decoded: %0A is a newline there
        assert request(server, "GET", f"/api/facts?key={key}")[0] in (400, 404), key


def test_save_to_project_refuses_unsafe_and_windows_device_names(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    for name in ("..", "../x", "a/b", "a\\b", "C:x", "c:", "\\\\srv\\x", "//srv/x", "x\ny", "My Theme", ".x", "x.yaml", "", "a" * 65):
        with pytest.raises(VidgenError, match="not a piece name"):
            save_to_project(project, name, TINY)
    for name in ("con", "nul", "aux", "prn", "com1", "lpt9", "com0"):
        with pytest.raises(VidgenError, match="Windows keeps for a device"):
            save_to_project(project, name, TINY)
    assert save_to_project(project, "console", TINY)["saved"]  # a name that only starts like one is fine
    assert not any(p.name.startswith(".") for p in (project / "assets" / "music").iterdir())  # no temporary file left


def test_save_to_project_never_follows_a_link_out(tmp_path: Path) -> None:
    project, outside = tmp_path / "proj", tmp_path / "outside"
    (project / "assets").mkdir(parents=True)
    outside.mkdir()
    try:
        (project / "assets" / "music").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("this system does not let us make a link")
    with pytest.raises(VidgenError, match="outside the project"):
        save_to_project(project, "theme", TINY)
    assert list(outside.iterdir()) == []


# ----- hostile score text ------------------------------------------------------------------------


def test_alias_bombs_deep_nesting_and_python_tags_are_problems_not_hangs() -> None:
    laughs = "a: &a [x, x, x, x, x, x, x, x, x]\n"
    prev = "a"
    for k in "bcdefghi":
        laughs += f"{k}: &{k} [" + ", ".join([f"*{prev}"] * 9) + "]\n"
        prev = k
    began = time.perf_counter()
    _, score, problems = check_text(laughs + "title: *i\nkey: A minor\ntempo: 120\nsections: [{name: a, bars: 1}]\ntracks: {}\n")
    assert score is None and str(MAX_YAML_NODES) in problems[0]["message"] and time.perf_counter() - began < 5  # took 30 s before
    _, score, problems = check_text("a: " + "[" * 20000 + "]" * 20000 + "\n")
    assert score is None and "nested too deeply" in problems[0]["message"]
    _, score, problems = check_text("!!python/object/apply:os.system ['echo hi']\n")
    assert score is None and "not valid YAML" in problems[0]["message"]
    # a few anchors, used sensibly, are fine
    _, score, problems = check_text(TINY.replace('kick: {instrument: kick, steps: "x... x... x... x..."}',
                                                 'kick: &k {instrument: kick, steps: "x... x... x... x..."}\n  kick2: *k'))
    assert score is not None, problems


def test_bad_values_are_problems_not_crashes() -> None:
    _, score, problems = check_text(TINY.replace('steps: "x... x... x... x..."', "steps: [[x..., x...]]"))
    assert score is None and "write the steps as a string" in problems[0]["message"]  # was a TypeError (a 500)
    _, score, problems = check_text(TINY.replace("{name: a, bars: 1}", '{name: "a\\n", bars: 1}'))
    assert score is None and "a section needs a name" in problems[0]["message"]  # it names files: no newline


def test_typed_and_pasted_text_keeps_unix_line_ends(app: StudioApp) -> None:
    app.load(text=TINY.replace("\n", "\r\n"))
    session = app.session
    assert session is not None and b"\r" not in session.version_path(1).read_bytes()
    assert app.text(None, TINY.replace("\n", "\r\n"))["unchanged"]  # the same text, other line ends
    app.text(None, TINY.replace("tempo: 120", "tempo: 121").replace("\n", "\r\n"))
    assert b"\r" not in session.version_path(2).read_bytes() and session.text(2) == TINY.replace("tempo: 120", "tempo: 121")


# ----- agents: the MCP side and the paid provider ------------------------------------------------------


def test_mcp_tools_do_not_follow_a_session_link_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDGEN_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "root"
    real = StudioSession.create(tmp_path / "elsewhere", None, "x")
    real.add_version(TINY, "text", "x", None)
    sessions = studio_dir(root) / "sessions"
    sessions.mkdir(parents=True)
    try:
        (sessions / real.id).symlink_to(real.folder, target_is_directory=True)
    except OSError:
        pytest.skip("this system does not let us make a link")
    with pytest.raises(VidgenError, match="link out of"):
        find_session(root, real.id)
    with pytest.raises(VidgenError, match="link out of"):
        agent_propose(root, TINY.replace("120", "121"), session_id=real.id)
    assert not (real.folder / "inbox").exists()
    for bad in ("../x", "20260101-000000-abcd\n"):
        with pytest.raises(VidgenError, match="not a studio session id"):
            find_session(root, bad)


def test_the_paid_provider_needs_the_persons_confirmation(server: StudioServer, monkeypatch: pytest.MonkeyPatch) -> None:
    from vidgen import httpapi

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-a-key")
    monkeypatch.setattr(httpapi, "post_with_retries", lambda *a, **kw: pytest.fail("no network in tests"))
    request(server, "POST", "/api/load", {"text": TINY})
    request(server, "POST", "/api/ask", {})
    for body in ({"model": "x/y"}, {"model": "x/y", "confirm": "yes"}, {"model": "x/y", "confirm": 1}):
        status, _, reply = request(server, "POST", "/api/proposal/send", body)
        assert status == 400 and b"confirm" in reply, body
    for path in ("/api/info", "/api/session", "/api/ask"):
        assert b"sk-or" not in request(server, "GET", path)[2], path  # the key is never given to the page


# ----- cleaning while a studio runs ----------------------------------------------------------------------


def test_clean_leaves_the_session_a_running_studio_has_open(tmp_path: Path) -> None:
    studio = studio_dir(tmp_path)
    open_session = StudioSession.create(studio, None, "open")
    other = StudioSession.create(studio, None, "other")
    for session in (open_session, other):
        session.add_version(TINY, "text", "v1", None)
        session.add_version(TINY.replace("120", "121"), "edit", "v2", 1)
        session.set_current(2)
        session.add_version(TINY.replace("120", "122"), "edit", "v3", 2, current=False)
        session.renders.mkdir()
        from vidgen.studio_app.app import render_key

        for k in (120, 121, 122):
            (session.renders / f"{render_key(yaml.safe_load(TINY.replace('120', str(k))))}.wav").write_bytes(b"\0" * 10)
    (studio / OPEN_FILE).write_text(json.dumps({"url": "http://127.0.0.1:1/", "session": open_session.id, "pid": 1}), encoding="utf-8")
    said: list[str] = []
    clean_studio_folder(tmp_path, said.append)
    assert len(list(open_session.renders.iterdir())) == 3 and "left as it is" in said[0]
    assert len(list(other.renders.iterdir())) == 2  # v3 is neither current, first nor starred


# ----- the studio's quick FFT lengths (§94.19) -----------------------------------------------------------


def test_fft_lengths() -> None:
    assert not fx.slow_fft_length(2 ** 12 * 5 ** 4) and not fx.slow_fft_length(2559744)  # 2⁸·3²·11·101: numpy is quick enough
    assert fx.slow_fft_length(2468352) and fx.slow_fft_length(2 * 601) and not fx.slow_fft_length(499 * 64)
    for n in (1, 2, 7, 97, 1000, 4937, 4937 * 2, 1 << 20, (1 << 20) + 1):
        m = fx.fast_fft_length(n)
        assert m >= n and not fx.slow_fft_length(m)
        rest = m
        for p in (2, 3, 5):
            while rest % p == 0:
                rest //= p
        assert rest == 1, (n, m)
        assert all(not (k >= n and k < m and _smooth(k)) for k in range(n, min(m, n + 5000))), (n, m)
    assert not fx.CircularFFT(2468352).folded and fx.CircularFFT(2468352, fast=True).folded  # only when asked
    assert not fx.CircularFFT(2400000, fast=True).folded and not fx.CircularFFT(1201, fast=True).folded  # quick, or short


def _smooth(k: int) -> bool:
    for p in (2, 3, 5):
        while k % p == 0:
            k //= p
    return k == 1


def _slow_length(at_least: int) -> int:
    n = at_least
    while not fx.slow_fft_length(n):
        n += 1
    return n


#: How close the quick lengths' filters are to the exact ones here, against the loudest sample:
#: white noise at the shortest folded length is the worst case (what the filters do near 24 kHz
#: reaches furthest); a real piece of 50 s differed by 5e-15 (DESIGN.md §94.19).
QUICK_TOLERANCE = 1e-9


def test_quick_lengths_filter_as_the_exact_ones() -> None:
    n = _slow_length(fx.FAST_FFT_MIN + 1000)
    rng = np.random.default_rng(7)
    x = rng.standard_normal((n, 2))
    cutoff = np.geomspace(500, 5000, n)
    for kind in ("lowpass", "highpass"):
        exact, quick = fx.swept_filter(x, cutoff, kind), fx.swept_filter(x, cutoff, kind, fast=True)
        assert float(np.abs(exact - quick).max()) <= QUICK_TOLERANCE * float(np.abs(exact).max()), kind
    flat = np.full(n, 900.0)
    assert np.abs(fx.swept_filter(x, flat, "lowpass") - fx.swept_filter(x, flat, "lowpass", True)).max() <= QUICK_TOLERANCE * np.abs(x).max()
    for wrap in (True, False):
        rv = fx.Reverb(size=0.8, mix=0.3, tone=5000.0, predelay=0.02)
        exact, quick = fx.reverb(x, rv, wrap, "seed"), fx.reverb(x, rv, wrap, "seed", fast=True)
        assert float(np.abs(exact - quick).max()) <= QUICK_TOLERANCE * float(np.abs(exact).max()), wrap
    score = parse_music_score(yaml.safe_load(TINY))
    exact, quick = _master_filter(x, score, 1), _master_filter(x, score, 2, fast_fft=True)
    assert float(np.abs(exact - quick).max()) <= QUICK_TOLERANCE * float(np.abs(exact).max())
    assert np.array_equal(_master_filter(x, score, 2), exact)  # threads alone: the same to the bit


def _slow_score() -> str:
    """A loop whose length has a large prime factor, with filter sweeps, reverb and echo."""
    for tempo in range(97, 200):
        text = (TINY.replace("tempo: 120", f"tempo: {tempo}").replace("bars: 1}", "bars: 2}")
                + '  arp: {instrument: pluck, steps: "1358 5313", reverb: {size: 1.0, mix: 0.3}, lowpass: 900,'
                  ' sections: {b: {lowpass: {from: 900, to: 3000}}}}\n'
                + '  pad: {instrument: pad, play: chords, highpass: {from: 200, to: 600}, echo: {delay: 0.75, feedback: 0.3, repeats: 2}}\n')
        score = parse_music_score(yaml.safe_load(text))
        if fx.slow_fft_length(score.samples):
            return text
    raise AssertionError("no tempo gives a slow length")


def test_the_studio_plays_the_same_16_bit_audio_as_a_video_on_slow_lengths(app: StudioApp) -> None:
    text = _slow_score()
    app.load(text=text)
    played = app.render()
    score = parse_music_score(yaml.safe_load(text))
    assert fx.CircularFFT(score.samples, fast=True).folded
    # the studio's audition WAV, as it writes it (float32 samples times its gain), from the video's samples
    expected = wav_bytes(np.clip(render_music_score(score) * 10 ** (played["audition_gain_db"] / 20), -1.0, 1.0))
    assert (app.session.renders / f"{played['key']}.wav").read_bytes() == expected
    stems = [render_track_stem(score, t.name, fast_fft=True) for t in score.tracks]
    quick, _ = mix_track_stems(score, stems, fast_fft=True)
    assert float(np.abs(quick.astype(np.float64) - render_music_score(score)).max()) <= 1e-9  # the remix tolerance of Step 196


def _slow_templates() -> list[str]:
    from vidgen.music import BUILTIN_BEDS

    return [n for n in BUILTIN_BEDS if fx.slow_fft_length(parse_music_score(yaml.safe_load(music_template_text(n))).samples)]


@pytest.mark.slow
@pytest.mark.parametrize("name", _slow_templates())
def test_templates_of_slow_lengths_play_as_their_renders(name: str) -> None:
    """The built-in templates whose length is slow (ascent, breakthrough): the studio's quick
    stems mixed are their render within Step 196's remix tolerance, the same audition WAV."""
    score = parse_music_score(yaml.safe_load(music_template_text(name)))
    exact = render_music_score(score)
    quick, _ = mix_track_stems(score, (render_track_stem(score, t.name, fast_fft=True) for t in score.tracks), threads=2, fast_fft=True)
    assert float(np.abs(quick.astype(np.float64) - exact).max()) <= 1e-9
    level = 10 ** (12 / 20)
    assert wav_bytes(np.clip(quick * level, -1.0, 1.0)) == wav_bytes(np.clip(exact * level, -1.0, 1.0))


# ----- long pieces: stems streamed; exports block by block -------------------------------------------------


def test_stems_that_do_not_fit_are_streamed_with_the_same_audio(app: StudioApp, tmp_path: Path) -> None:
    text = TINY + '  arp: {instrument: pluck, steps: "1358 5313", lowpass: {from: 900, to: 3000}}\n  pad: {instrument: pad, play: chords}\n'
    app.load(text=text)
    whole = app.render()
    small = StudioApp(None, studio=tmp_path / "small")
    small.stems = StemCache(budget=1)  # nothing fits: every stem streamed
    try:
        small.load(text=text)
        streamed = small.render()
        assert set(streamed["timing"]["tracks"]) == {"kick", "arp", "pad"}
        assert (small.session.renders / f"{streamed['key']}.wav").read_bytes() == (app.session.renders / f"{whole['key']}.wav").read_bytes()
        assert streamed["meters"] == whole["meters"] and streamed["mix_gain"] == whole["mix_gain"]
        muted = small.render(mute=["kick"])
        assert (small.session.renders / muted["url"].rsplit("/", 1)[1]).is_file()
        check = small.check(None, wait=60)
        assert check["status"] == "done" and check["verdict"] == app.check(None, wait=60)["verdict"]
    finally:
        small.close()


def _export_before(score: Any, length: str, count: float | None, level: str) -> np.ndarray:
    """Studio exports as Step 197 made them (the whole piece in memory at once)."""
    from vidgen import loudness

    audio = np.asarray(render_music_score(score), dtype=np.float64)
    if length == "loops":
        audio = np.tile(audio, (int(count), 1))
    elif length == "seconds":
        n = int(round(count * RATE))
        cut = score.loop or n < len(audio)
        audio = np.tile(audio, (n // len(audio) + 1, 1))[:n] if score.loop else np.concatenate([audio, np.zeros((max(0, n - len(audio)), 2))])[:n]
        fade = min(int(2.0 * RATE), n // 4)
        if cut and fade > 0:
            audio[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
    gain = 10 ** ((-16.0 + 28.0) / 20) if level == "listening" else 1.0
    if level == "listening":
        peak = float(loudness.peak_envelope(audio).max()) * gain
        if peak > 10 ** (-1 / 20):
            gain *= 10 ** (-1 / 20) / peak
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32)


def test_exports_made_block_by_block_are_the_same_files_and_bounded() -> None:
    peaky = parse_music_score(yaml.safe_load(
        "key: A minor\ntempo: 97\nprogression: i\nsections: [{name: a, bars: 2}]\ntracks:\n  boom: {instrument: boom, steps: \"x... .... .... ....\"}\n"
        "  bass: {instrument: sub, steps: \"1--- ---- ---- ----\", octave: 1}\n"))
    once = parse_music_score({**yaml.safe_load(TINY), "loop": False})
    for score, length, count, level in ((peaky, "seconds", 23.5, "listening"), (peaky, "loops", 3, "listening"), (once, "seconds", 12, "video"),
                                        (once, "once", None, "listening")):
        audio, facts = export_audio(score, length, count, level)
        assert np.array_equal(audio, _export_before(score, length, count, level)), (length, level)
    assert export_audio(peaky, "once", None, "listening")[1]["true_peak"] <= -0.99  # the peak limit was used
    with pytest.raises(VidgenError, match="from 1 to 600"):
        export_audio(peaky, "seconds", 601, "video")
    with pytest.raises(VidgenError, match="from 1 to 600"):
        export_audio(peaky, "seconds", math.nan, "video")
    minute = parse_music_score({**yaml.safe_load(TINY), "sections": [{"name": "a", "bars": 16}, {"name": "b", "bars": 16}]})
    with pytest.raises(VidgenError, match="longer than 10 minutes"):
        export_audio(minute, "loops", 10, "video")  # 64 loops of a 5 s piece fit; ten of a minute-long one do not
