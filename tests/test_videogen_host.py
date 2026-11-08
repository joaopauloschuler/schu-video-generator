"""Hosting audio / video inputs through a Cloudflare quick tunnel (DESIGN.md §115). No network:
the share server is real (127.0.0.1), cloudflared is a fake Python script that prints a
trycloudflare address and starts a child process, and "the public address" is mapped back to
the local server."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import time
from pathlib import Path

import pytest

from vidgen import cli
from vidgen.errors import VidgenError
from vidgen.videogen import host as host_module
from vidgen.videogen.host import (
    HostSettings,
    QuickTunnelHost,
    ShareServer,
    copy_into_share,
    find_cloudflared,
    host_self_test,
    tunnel_command,
)
from vidgen.videogen.ledger import Ledger
from vidgen.videogen.openrouter import Response

FAKE_HOST = "fake-words.trycloudflare.com"
FAKE_CLOUDFLARED = '''
import os, subprocess, sys, time
from pathlib import Path
Path(os.environ["FAKE_CF_ARGS"]).write_text("\\n".join(sys.argv[1:]), encoding="utf-8")
mode = os.environ.get("FAKE_CF_MODE", "ok")
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
Path(os.environ["FAKE_CF_CHILD"]).write_text(str(child.pid), encoding="utf-8")
if mode == "exit":
    print("ERR failed to request quick Tunnel: 403 Forbidden", flush=True)
    child.kill()
    sys.exit(1)
if mode == "ok":
    print("INF Requesting new quick Tunnel on trycloudflare.com...", flush=True)
    print("INF |  https://fake-words.trycloudflare.com                                  |", flush=True)
    print("INF Registered tunnel connection connIndex=0 protocol=http2", flush=True)
time.sleep(60)
'''

SETTINGS = HostSettings(url_timeout=10, verify_timeout=1.0, verify_interval=0.05, grace_seconds=0.2)


@pytest.fixture
def fake_cloudflared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    script = tmp_path / "fake_cloudflared.py"
    script.write_text(FAKE_CLOUDFLARED, encoding="utf-8")
    monkeypatch.setenv("FAKE_CF_ARGS", str(tmp_path / "cf_args.txt"))
    monkeypatch.setenv("FAKE_CF_CHILD", str(tmp_path / "cf_child.txt"))
    return [sys.executable, str(script)]


def raw(port: int, method: str, path: str) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path)
        answer = conn.getresponse()
        return answer.status, {k.lower(): v for k, v in answer.getheaders()}, answer.read()
    finally:
        conn.close()


def local_fetch(tmp_path: Path):
    """The fake tunnel: https://fake-words.trycloudflare.com/... goes to the port cloudflared was given."""
    def fetch(method: str, url: str, timeout: float) -> Response:
        args = (tmp_path / "cf_args.txt").read_text(encoding="utf-8").splitlines()
        port = int(args[args.index("--url") + 1].rsplit(":", 1)[1])
        path = url.removeprefix(f"https://{FAKE_HOST}") or "/"
        status, headers, body = raw(port, method, path)
        return Response(status, body, headers)
    return fetch


def pid_alive(pid: int) -> bool:
    if os.name == "nt":   # pragma: no cover
        import subprocess
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:   # a zombie (ended, not yet reaped by its parent) counts as gone
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2] != "Z"
    except OSError:
        return True


def wait_dead(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


def sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    (project / "build" / "videogen" / "shot1").mkdir(parents=True)
    audio = project / "build" / "videogen" / "shot1" / "audio.mp3"
    audio.write_bytes(b"ID3" + bytes(range(256)) * 300)
    guide = project / "build" / "videogen" / "shot1" / "guide.MP4"
    guide.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 1000)
    (project / "secret.txt").write_text("do not share", encoding="utf-8")
    return project, audio, guide


def test_copies_get_random_names_and_hashes(tmp_path: Path) -> None:
    project, audio, guide = sources(tmp_path)
    folder = tmp_path / "share"
    folder.mkdir()
    shared = copy_into_share([audio, guide], folder, project)
    assert [s.label for s in shared] == ["build/videogen/shot1/audio.mp3", "build/videogen/shot1/guide.MP4"]
    assert shared[0].name.endswith(".mp3") and shared[1].name.endswith(".mp4") and len(shared[0].name) == 16 + 4
    assert shared[0].name != "audio.mp3" and sorted(p.name for p in folder.iterdir()) == sorted(s.name for s in shared)
    assert shared[0].size == audio.stat().st_size and shared[0].path.read_bytes() == audio.read_bytes()
    assert shared[0].sha256 == hashlib.sha256(audio.read_bytes()).hexdigest()
    assert shared[0].content_type == "audio/mpeg" and shared[1].content_type == "video/mp4"
    assert copy_into_share([audio], folder)[0].label == "audio.mp3"   # without a project: the file name


def test_refuses_links_folders_and_missing_files(tmp_path: Path) -> None:
    project, audio, _ = sources(tmp_path)
    folder = tmp_path / "share"
    folder.mkdir()
    with pytest.raises(VidgenError, match="not a file"):
        copy_into_share([project / "build"], folder)
    with pytest.raises(VidgenError, match="not a file"):
        copy_into_share([project / "missing.mp3"], folder)
    with pytest.raises(VidgenError, match="given twice"):
        copy_into_share([audio, audio], folder)
    link = project / "link.mp3"
    try:
        link.symlink_to(project / "secret.txt")
    except OSError:   # pragma: no cover - Windows without the symlink privilege
        pytest.skip("cannot create symlinks here")
    with pytest.raises(VidgenError, match="symbolic link"):
        copy_into_share([link], folder)


def test_server_answers_only_the_exact_paths(tmp_path: Path) -> None:
    project, audio, guide = sources(tmp_path)
    folder = tmp_path / "share"
    folder.mkdir()
    shared = copy_into_share([audio, guide], folder, project)
    server = ShareServer(shared, "s3cr3t-token")
    server.start()
    try:
        port = server.port
        assert server.server_address[0] == "127.0.0.1"
        status, headers, body = raw(port, "GET", f"/s3cr3t-token/{shared[0].name}")
        assert status == 200 and body == audio.read_bytes()
        assert headers["content-type"] == "audio/mpeg" and headers["content-length"] == str(audio.stat().st_size)
        assert "server" not in headers
        status, headers, body = raw(port, "HEAD", f"/s3cr3t-token/{shared[1].name}")
        assert status == 200 and body == b"" and headers["content-length"] == str(guide.stat().st_size)
        for path in ("/", "/s3cr3t-token/", "/s3cr3t-token", f"/wrong/{shared[0].name}", f"/{shared[0].name}",
                     f"/s3cr3t-token/{shared[0].name}?x=1", "/s3cr3t-token/../secret.txt", "/s3cr3t-token/audio.mp3",
                     f"/s3cr3t-token/{shared[0].name}/"):
            status, headers, _ = raw(port, "GET", path)
            assert status == 404, path
            assert "server" not in headers
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PROPFIND"):
            assert raw(port, method, f"/s3cr3t-token/{shared[0].name}")[0] == 404, method
    finally:
        server.stop()
    kept = server.requests
    assert [r.status for r in kept[:2]] == [200, 200] and kept[0].bytes == audio.stat().st_size and kept[1].bytes == 0
    assert all("s3cr3t-token" not in r.path for r in kept) and all("127.0.0.1" not in repr(r) for r in kept)
    assert kept[0].file == "build/videogen/shot1/audio.mp3"


def test_tunnel_command_and_install_hints(tmp_path: Path) -> None:
    assert tunnel_command(["cloudflared"], 8123) == ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8123", "--no-autoupdate", "--protocol", "http2"]
    assert tunnel_command(["cf"], 1, "auto") == ["cf", "tunnel", "--url", "http://127.0.0.1:1", "--no-autoupdate"]
    with pytest.raises(VidgenError, match="http2, quic, auto"):
        tunnel_command(["cf"], 1, "tcp")
    with pytest.raises(VidgenError) as info:
        find_cloudflared(None, which=lambda name: None, environ={})
    assert "winget install Cloudflare.cloudflared" in str(info.value) and "brew install cloudflared" in str(info.value)
    assert "videogen: {cloudflared:" in str(info.value)
    with pytest.raises(VidgenError, match="videogen.cloudflared: nowhere/cloudflared not found"):
        find_cloudflared("nowhere/cloudflared", which=lambda name: None)
    exe = tmp_path / "Cloudflared" / "cloudflared" / "cloudflared.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert find_cloudflared(None, which=lambda name: None, environ={"ProgramFiles(x86)": str(tmp_path / "Cloudflared")}) == str(exe)
    assert find_cloudflared(str(exe), which=lambda name: None) == str(exe)
    assert find_cloudflared(None, which=lambda name: "/usr/bin/cloudflared") == "/usr/bin/cloudflared"


def test_open_verify_fetch_close_with_the_ledger(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, guide = sources(tmp_path)
    ledger = Ledger(project / "videogen-ledger.jsonl")
    fetch = local_fetch(tmp_path)
    lines: list[str] = []
    with QuickTunnelHost([audio, guide], root=project, settings=SETTINGS, ledger=ledger, executable=fake_cloudflared,
                         fetch=fetch, close_when_fetched=False, out=lines.append) as host:
        folder = host.folder
        assert folder is not None and not folder.resolve().is_relative_to(project.resolve())
        url = host.url_of(audio)
        assert url.startswith(f"https://{FAKE_HOST}/") and url.endswith(".mp3") and "audio" not in url
        assert set(host.urls()) == {audio, guide}
        assert fetch("GET", url, 5).body == audio.read_bytes()
        assert host.is_open
        child = int((tmp_path / "cf_child.txt").read_text(encoding="utf-8"))
        assert pid_alive(child)
    assert host.close_reason == "done" and not host.is_open
    assert not folder.exists()
    assert wait_dead(host.tunnel.process.pid) and wait_dead(child), "cloudflared's process tree is still running"
    args = (tmp_path / "cf_args.txt").read_text(encoding="utf-8").splitlines()
    assert args[:2] == ["tunnel", "--url"] and "--no-autoupdate" in args and args[-2:] == ["--protocol", "http2"]
    text = ledger.path.read_text(encoding="utf-8")
    secret = url.split("/")[3]
    assert secret not in text and url not in text
    events = ledger.events()
    assert [e["event"] for e in events][0] == "host_open" and events[-1]["event"] == "host_close"
    opened = events[0]
    assert opened["host"] == FAKE_HOST and opened["max_seconds"] == 900.0
    assert opened["files"][0] == {"name": "build/videogen/shot1/audio.mp3", "size": audio.stat().st_size,
                                  "sha256": copy_into_share([audio], tmp_path)[0].sha256}
    fetches = [e for e in events if e["event"] == "host_fetch"]
    assert {(e["file"], e["method"], e["status"]) for e in fetches} >= {("build/videogen/shot1/audio.mp3", "HEAD", 200),
                                                                       ("build/videogen/shot1/guide.MP4", "HEAD", 200),
                                                                       ("build/videogen/shot1/audio.mp3", "GET", 200)}
    assert events[-1]["reason"] == "done" and events[-1]["folder_deleted"] is True
    assert ledger.jobs() == []   # host events are not jobs
    assert any("at most 15 min" in line for line in lines) and any("closed (done)" in line for line in lines)
    assert all(secret not in line for line in lines)


def test_closes_after_every_file_was_fetched(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, guide = sources(tmp_path)
    fetch = local_fetch(tmp_path)
    with QuickTunnelHost([audio, guide], root=project, settings=SETTINGS, executable=fake_cloudflared, fetch=fetch) as host:
        fetch("GET", host.url_of(audio), 5)
        assert not host.wait_closed(0.5), "closed before every file was fetched"
        fetch("GET", host.url_of(guide), 5)
        assert host.wait_closed(3)
        assert host.close_reason == "all files fetched" and not host.folder.exists()
    assert host.close_reason == "all files fetched"


def test_hard_maximum_lifetime(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    settings = HostSettings(url_timeout=10, verify_timeout=1, verify_interval=0.05, max_seconds=1.0)
    with QuickTunnelHost([audio], root=project, settings=settings, executable=fake_cloudflared, fetch=local_fetch(tmp_path)) as host:
        assert host.wait_closed(5)
        assert host.close_reason == "max lifetime" and not host.folder.exists()
        assert wait_dead(host.tunnel.process.pid)


def test_ctrl_c_inside_the_block_closes_everything(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    with pytest.raises(KeyboardInterrupt):
        with QuickTunnelHost([audio], root=project, settings=SETTINGS, ledger=ledger, executable=fake_cloudflared, fetch=local_fetch(tmp_path)) as host:
            raise KeyboardInterrupt
    child = int((tmp_path / "cf_child.txt").read_text(encoding="utf-8"))
    assert host.close_reason == "interrupted" and not host.folder.exists() and wait_dead(child)
    assert ledger.events()[-1]["reason"] == "interrupted"
    with pytest.raises(RuntimeError):
        with QuickTunnelHost([audio], root=project, settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path)) as host:
            raise RuntimeError("the job failed")
    assert host.close_reason == "error: RuntimeError" and not host.folder.exists()


def test_cloudflared_failures_close_everything(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    project, audio, _ = sources(tmp_path)
    monkeypatch.setenv("FAKE_CF_MODE", "exit")
    host = QuickTunnelHost([audio], root=project, settings=SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path))
    with pytest.raises(VidgenError, match=r"stopped \(exit code 1\)[\s\S]*403 Forbidden"):
        host.open()
    assert host.close_reason == "failed to open" and not host.folder.exists()
    monkeypatch.setenv("FAKE_CF_MODE", "silent")
    settings = HostSettings(url_timeout=0.5)
    host = QuickTunnelHost([audio], root=project, settings=settings, executable=fake_cloudflared)
    with pytest.raises(VidgenError, match="no quick tunnel address within 0.5 s"):
        host.open()
    child = int((tmp_path / "cf_child.txt").read_text(encoding="utf-8"))
    assert not host.folder.exists() and wait_dead(host.tunnel.process.pid) and wait_dead(child)
    with pytest.raises(VidgenError, match="cannot start cloudflared"):
        QuickTunnelHost([audio], settings=SETTINGS, executable=[str(tmp_path / "no-such-program")]).open()


def test_public_address_that_never_works_stops_before_anything_is_sent(tmp_path: Path, fake_cloudflared: list[str]) -> None:
    project, audio, _ = sources(tmp_path)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    calls: list[str] = []

    def unreachable(method: str, url: str, timeout: float) -> Response:
        calls.append(method)
        raise OSError("Name or service not known")

    host = QuickTunnelHost([audio], root=project, settings=SETTINGS, ledger=ledger, executable=fake_cloudflared, fetch=unreachable)
    with pytest.raises(VidgenError, match=r"never served build/videogen/shot1/audio.mp3 within 1 s .*Name or service not known.*host-test"):
        host.open()
    assert len(calls) > 1 and set(calls) == {"HEAD"}
    assert not host.folder.exists()
    assert [e["event"] for e in ledger.events()] == ["host_open", "host_close"]
    assert ledger.events()[-1]["reason"] == "failed to open"

    def wrong_length(method: str, url: str, timeout: float) -> Response:
        return Response(200, b"", {"content-length": "3"})

    with pytest.raises(VidgenError, match="length 3 instead of"):
        QuickTunnelHost([audio], settings=SETTINGS, executable=fake_cloudflared, fetch=wrong_length).open()


def test_self_test_and_the_cli(tmp_path: Path, fake_cloudflared: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    lines: list[str] = []
    result = host_self_test(SETTINGS, executable=fake_cloudflared, fetch=local_fetch(tmp_path), out=lines.append)
    assert result.ok and result.host == FAKE_HOST and result.close_reason == "done"
    assert [c[1] for c in result.checks] == [True, True, True, True]
    assert any("FAIL" not in line and "same bytes" in line for line in lines)

    def tampering(method: str, url: str, timeout: float) -> Response:
        answer = local_fetch(tmp_path)(method, url, timeout)
        return Response(200, b"changed", answer.headers) if method == "GET" else answer

    with pytest.raises(VidgenError, match="host test failed: GET through the tunnel returns the same bytes"):
        host_self_test(SETTINGS, executable=fake_cloudflared, fetch=tampering, out=lines.append)

    # the CLI, outside any project: default settings, cloudflared (one program) and the network replaced
    if os.name == "nt":   # pragma: no cover - a script with a #! line is a program only on POSIX
        return
    program = tmp_path / "cloudflared"
    program.write_text(f"#!{sys.executable}\n" + Path(fake_cloudflared[1]).read_text(encoding="utf-8"), encoding="utf-8")
    program.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(host_module, "find_cloudflared", lambda setting=None, **kw: str(program))
    monkeypatch.setattr(host_module, "urllib_fetch", local_fetch(tmp_path))
    assert cli.main(["generate", "host-test"]) == 0
    out = capsys.readouterr().out
    assert f"host test OK: {FAKE_HOST}" in out and "closed (done)" in out
    assert cli.main(["generate", "host-test", "--keep", "0.2", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] and doc["action"] == "host-test" and doc["host"] == FAKE_HOST and len(doc["checks"]) == 4
    assert cli.main(["generate", "host-test", "--pay"]) != 0


def test_config_keys() -> None:
    from vidgen.config import VideogenConfig

    settings = HostSettings.from_config(VideogenConfig(cloudflared="C:/tools/cloudflared.exe", tunnel_protocol="quic", host_max_minutes=5, host_grace_seconds=10))
    assert settings == HostSettings(cloudflared="C:/tools/cloudflared.exe", protocol="quic", max_seconds=300.0, grace_seconds=10.0)
    assert HostSettings.from_config(VideogenConfig()) == HostSettings()
    with pytest.raises(ValueError):
        VideogenConfig(host_max_minutes=0)
    with pytest.raises(ValueError):
        VideogenConfig(tunnel_protocol="tcp")
