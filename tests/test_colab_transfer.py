"""File transfers through quick tunnels (vidgen.colab_transfer, colab_vm fetch/serve) with a fake
cloudflared: the tunnel servers run for real on 127.0.0.1, the VM is a folder."""
from __future__ import annotations

import io
import json
import shutil
import sys
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from vidgen import colab_transfer, colab_vm
from vidgen.colab import Colab, ColabError, CommandResult
from vidgen.colab_transfer import LocalTunnel, TransferError, Transfers, http_get

FAKE_CLOUDFLARED = '''import sys, time
print("INF |  https://fake-words.trycloudflare.com  |", flush=True)
print("INF Registered tunnel connection", flush=True)
time.sleep(120)
'''


@pytest.fixture()
def fake_cloudflared(tmp_path: Path) -> str:
    path = tmp_path / "cloudflared"
    path.write_text(f"#!{sys.executable}\n{FAKE_CLOUDFLARED}", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


class LoopbackTunnel(LocalTunnel):
    """A local tunnel whose address is its server on 127.0.0.1 (the fake cloudflared reaches nothing)."""

    def wait_url(self, timeout: float = 20.0, sleep=None) -> str:  # type: ignore[override]
        super().wait_url(timeout)
        return f"http://127.0.0.1:{self.state()['port']}"


def _status(url: str, method: str = "GET") -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=5) as answer:
            return answer.status
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.mark.slow
def test_tunnel_serves_only_its_files_under_the_secret(tmp_path: Path, fake_cloudflared: str) -> None:
    (tmp_path / "a.bin").write_bytes(b"A" * 1000)
    tunnel = LoopbackTunnel(fake_cloudflared)
    try:
        base = tunnel.wait_url()
        assert LocalTunnel.wait_url(tunnel, 5) == "https://fake-words.trycloudflare.com"
        assert len(tunnel.secret) >= 43
        name = tunnel.add(tmp_path / "a.bin")
        (tunnel.folder / "files" / ".hidden").write_bytes(b"h")
        (tunnel.folder / "outside").write_bytes(b"o")
        assert http_get(f"{base}/{tunnel.secret}/{name}", tmp_path / "b.bin", colab_transfer.sha256_file(tmp_path / "a.bin")) == 1000
        for path in ("/", f"/{tunnel.secret}/", f"/{tunnel.secret}", f"/x{tunnel.secret}/{name}", f"/{tunnel.secret}/.hidden",
                     f"/{tunnel.secret}/../outside", f"/{tunnel.secret}/%2e%2e/outside", f"/{tunnel.secret}/{name}/x", "/%C3%A9/x"):
            assert _status(base + path) == 404, path
        assert _status(f"{base}/{tunnel.secret}/{name}", "POST") == 404
        with pytest.raises(TransferError, match="SHA-256 differs"):
            http_get(f"{base}/{tunnel.secret}/{name}", tmp_path / "c.bin", "0" * 64)
        assert not (tmp_path / "c.bin").exists()
    finally:
        tunnel.close()
    assert tunnel.process.returncode is not None and not tunnel.folder.exists()


class VMRunner:
    """`colab exec` of colab_vm.py run here; paths stay real (the VM folders are monkeypatched)."""

    def __init__(self) -> None:
        self.actions: list[dict[str, str]] = []

    def __call__(self, args: list[str], timeout_seconds: float) -> CommandResult:
        assert args[1] == "exec" and Path(args[-1]).name == "colab_vm.py"
        env = dict(a.split("=", 1) for a in args if a.startswith("VIDGEN_"))
        self.actions.append(env)
        out = io.StringIO()
        with redirect_stdout(out):
            colab_vm.main(env)
        return CommandResult(0, out.getvalue())


@pytest.fixture()
def vm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_cloudflared: str) -> Path:
    root = tmp_path / "vm"
    monkeypatch.setattr(colab_vm, "FETCH_DIR", root / ".vidgen-fetch")
    monkeypatch.setattr(colab_vm, "TUNNEL_DIR", root / ".vidgen-tunnel")
    monkeypatch.setattr(colab_vm, "CLOUDFLARED", Path(fake_cloudflared))
    return root


def _loopback_getter(url: str, dest: Path, sha256: str) -> int:
    port = json.loads((colab_vm.TUNNEL_DIR / "state.json").read_text(encoding="utf-8"))["port"]
    return http_get(url.replace("https://fake-words.trycloudflare.com", f"http://127.0.0.1:{port}"), dest, sha256)


@pytest.mark.slow
def test_upload_and_download_check_hashes_and_close_both_tunnels(tmp_path: Path, vm: Path, fake_cloudflared: str) -> None:
    if shutil.which("curl") is None:
        pytest.skip("needs curl (the VM side's fetch)")
    runner = VMRunner()
    lines: list[str] = []
    colab = Colab("ltx", runner=runner, sleep=lambda s: None, say=lines.append, lock_dir=tmp_path / "locks",
                  transfer_factory=lambda c: Transfers(c, tunnel_factory=lambda: LoopbackTunnel(fake_cloudflared),
                                                       getter=_loopback_getter))
    (tmp_path / "one.txt").write_bytes(b"one")
    (tmp_path / "two words.bin").write_bytes(b"2" * 70_000)
    with colab:
        colab.upload_many([(tmp_path / "one.txt", str(vm / "in" / "one.txt")),
                           (tmp_path / "two words.bin", str(vm / "in" / "deep" / "two.bin"))])
        assert (vm / "in" / "one.txt").read_bytes() == b"one" and (vm / "in" / "deep" / "two.bin").read_bytes() == b"2" * 70_000
        assert not list((vm / "in").rglob("*.vidgen-part")) and not any(colab_vm.FETCH_DIR.iterdir())
        local_folder = colab.transfers.local.folder  # type: ignore[union-attr]
        (vm / "out.mp4").write_bytes(b"MP4" * 100)
        colab.download(str(vm / "out.mp4"), tmp_path / "back" / "out.mp4")
        assert (tmp_path / "back" / "out.mp4").read_bytes() == b"MP4" * 100
        secrets = list(colab.transfers.secrets)
    assert not local_folder.exists() and not colab_vm.TUNNEL_DIR.exists()      # both closed
    assert runner.actions[-1]["VIDGEN_ACTION"] == "unserve"
    assert all(secret not in line for secret in secrets for line in lines)


@pytest.mark.slow
def test_fetch_reports_a_bad_hash_and_masks_the_secret(tmp_path: Path, vm: Path, fake_cloudflared: str) -> None:
    if shutil.which("curl") is None:
        pytest.skip("needs curl (the VM side's fetch)")
    (tmp_path / "a.txt").write_bytes(b"a")
    tunnel = LoopbackTunnel(fake_cloudflared)
    try:
        name = tunnel.add(tmp_path / "a.txt")
        files = [{"name": name, "dest": str(vm / "a.txt"), "sha256": "0" * 64}]
        env = {"VIDGEN_URL": f"{tunnel.wait_url()}/{tunnel.secret}/", "VIDGEN_FILES": json.dumps(files), "VIDGEN_ATTEMPT": "1"}
        reply = colab_vm.fetch(env, wait_seconds=20)
        assert reply["done"] and not reply["ok"] and "SHA-256 differs" in reply["problem"] and not (vm / "a.txt").exists()
        files[0]["name"] = "missing"
        env.update(VIDGEN_FILES=json.dumps(files), VIDGEN_ATTEMPT="2")
        reply = colab_vm.fetch(env, wait_seconds=20)
        assert not reply["ok"] and tunnel.secret not in reply["problem"] and "404" in reply["problem"]
    finally:
        tunnel.close()


class FlakyVM:
    """`serve` / `unserve` answers for Transfers.download without any process."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def __call__(self, args: list[str], timeout_seconds: float) -> CommandResult:
        env = dict(a.split("=", 1) for a in args if a.startswith("VIDGEN_"))
        self.calls.append(env)
        reply = {"closed": True} if env["VIDGEN_ACTION"] == "unserve" else {
            "url": "https://w.trycloudflare.com", "files": {"/content/x.mp4": {"name": "n-x.mp4", "size": 1, "sha256": "s"}}}
        return CommandResult(0, colab_vm.PREFIX + json.dumps(reply))


def test_a_name_that_does_not_resolve_gets_a_new_vm_tunnel_then_a_clear_error(tmp_path: Path) -> None:
    vm = FlakyVM()
    urls: list[str] = []

    def getter(url: str, dest: Path, sha256: str) -> int:
        urls.append(url)
        raise TransferError(f"{url} does not resolve", resolve=True)

    lines: list[str] = []
    colab = Colab("ltx", runner=vm, sleep=lambda s: None, say=lines.append, lock_dir=tmp_path,
                  transfer_factory=lambda c: Transfers(c, getter=getter))
    with pytest.raises(ColabError, match="could not download /content/x.mp4 from ltx after 3 tries") as caught:
        colab.download("/content/x.mp4", tmp_path / "x.mp4")
    secrets = colab.transfers.secrets
    assert len(set(secrets)) == 3 and all(len(s) >= 43 for s in secrets)        # a new secret (tunnel) each try
    assert [c.get("VIDGEN_RESTART") for c in vm.calls] == ["", "1", "1"]
    assert all(s not in str(caught.value) and all(s not in line for line in lines) for s in secrets)
    colab.close()
    assert vm.calls[-1]["VIDGEN_ACTION"] == "unserve"
