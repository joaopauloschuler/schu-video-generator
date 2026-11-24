"""A ComfyUI server over HTTP: ``/upload/image``, ``/prompt``, ``/history``, ``/view`` (DESIGN.md §113.20).

Standard library only, no vidgen imports: the Colab transport copies this file next to a job on
the VM and runs ``python3 comfyui_client.py job.json`` there, detached, against 127.0.0.1:8188.
``job.json`` holds ``url``, ``graph`` (API format), ``uploads`` (name in ComfyUI's input folder ->
file next to ``job.json``), ``poll_seconds`` and ``timeout``; the run writes ``output.mp4`` and
prints one JSON line (:func:`job_outcome` and ``prompt_id``) on stdout, its progress on stderr.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: The file a job's clip is written to, next to ``job.json``.
OUTPUT_NAME = "output.mp4"
#: Output keys of ComfyUI's history that hold video files (VHS_VideoCombine: ``gifs``).
VIDEO_KEYS = ("gifs", "videos", "images")


class ComfyError(Exception):
    """ComfyUI refused a request or could not be reached."""


Opener = Callable[..., Any]


class ComfyClient:
    """One ComfyUI server at ``url`` (``opener``: ``urllib.request.urlopen`` or a test double)."""

    def __init__(self, url: str, *, timeout: float = 60.0, opener: Opener = urllib.request.urlopen) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.opener = opener

    def _call(self, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        request = urllib.request.Request(self.url + path, data=body, headers=headers or {}, method="POST" if body is not None else "GET")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")[:2000]
            raise ComfyError(f"ComfyUI at {self.url} answered HTTP {exc.code} to {path.split('?')[0]}: {text}") from None
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ComfyError(f"no ComfyUI at {self.url} ({reason})") from None

    def _json(self, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
        raw = self._call(path, body, headers)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ComfyError(f"ComfyUI at {self.url} sent an unreadable answer to {path}") from None

    def system_stats(self) -> dict[str, Any]:
        """``GET /system_stats`` (answers when the server is up)."""
        return self._json("/system_stats")

    def upload(self, path: Path, name: str) -> str:
        """Put ``path`` into ComfyUI's input folder as ``name`` (``/upload/image`` takes any file);
        returns the name ComfyUI stored."""
        boundary = uuid.uuid4().hex
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode(),
            path.read_bytes(), f"\r\n--{boundary}--\r\n".encode(),
        ]
        reply = self._json("/upload/image", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return str(reply.get("name") or name)

    def submit(self, graph: dict[str, Any]) -> str:
        """``POST /prompt``; returns the prompt id."""
        body = json.dumps({"prompt": graph, "client_id": "vidgen"}).encode("utf-8")
        reply = self._json("/prompt", body, {"Content-Type": "application/json"})
        if not reply.get("prompt_id"):
            raise ComfyError(f"ComfyUI refused the graph: {json.dumps(reply)[:2000]}")
        return str(reply["prompt_id"])

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        """The history entry of ``prompt_id`` (``None`` while it is queued or running)."""
        reply = self._json(f"/history/{urllib.parse.quote(prompt_id)}")
        entry = reply.get(prompt_id) if isinstance(reply, dict) else None
        return entry if isinstance(entry, dict) else None

    def view(self, file: dict[str, Any], dest: Path) -> int:
        """Download an output ``file`` (``filename``, ``subfolder``, ``type``) to ``dest``; returns its size."""
        query = urllib.parse.urlencode({k: file.get(k, "") for k in ("filename", "subfolder", "type")})
        data = self._call(f"/view?{query}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return len(data)


def job_outcome(entry: dict[str, Any] | None) -> dict[str, Any]:
    """A history entry as ``{status: running | completed | failed, seconds, error, output}``:
    ``seconds`` from ComfyUI's ``execution_start`` to its end, ``output`` the first video file."""
    if entry is None:
        return {"status": "running", "seconds": None, "error": None, "output": None}
    status = entry.get("status") or {}
    messages = status.get("messages") or []
    stamps = {name: info.get("timestamp") for name, info in messages if isinstance(info, dict)}
    start = stamps.get("execution_start")
    end = stamps.get("execution_success") or stamps.get("execution_error") or stamps.get("execution_interrupted")
    seconds = round((end - start) / 1000.0, 1) if isinstance(start, (int, float)) and isinstance(end, (int, float)) else None
    if status.get("status_str") == "success":
        output = next((f for node in (entry.get("outputs") or {}).values() for key in VIDEO_KEYS
                       for f in node.get(key, []) if isinstance(f, dict) and str(f.get("filename", "")).endswith(".mp4")
                       and f.get("type") == "output"), None)
        if output is None:
            return {"status": "failed", "seconds": seconds, "error": "the graph ran but made no .mp4 output", "output": None}
        return {"status": "completed", "seconds": seconds, "error": None, "output": output}
    if status.get("status_str") == "error" or status.get("completed") is False:
        error = next((f"{info.get('node_type', '?')}: {info.get('exception_message', '').strip()}" for name, info in messages
                      if name == "execution_error" and isinstance(info, dict)), "ComfyUI reported an error")
        return {"status": "failed", "seconds": seconds, "error": error, "output": None}
    return {"status": "running", "seconds": None, "error": None, "output": None}


def run_job(job_file: Path, *, client: ComfyClient | None = None, sleep: Callable[[float], None] = time.sleep,
            clock: Callable[[], float] = time.monotonic, say: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run the job of ``job_file`` to its end (see the module docstring); returns its outcome."""
    tell = say or (lambda line: print(line, file=sys.stderr, flush=True))
    job = json.loads(job_file.read_text(encoding="utf-8"))
    comfy = client or ComfyClient(job["url"])
    for name, rel in job.get("uploads", {}).items():
        comfy.upload(job_file.parent / rel, name)
        tell(f"uploaded {name}")
    prompt_id = comfy.submit(job["graph"])
    tell(f"queued prompt {prompt_id}")
    begin = clock()
    while True:
        outcome = job_outcome(comfy.history(prompt_id))
        if outcome["status"] != "running":
            break
        if clock() - begin > float(job.get("timeout", 3600)):
            outcome = {"status": "failed", "seconds": None, "error": f"still running after {job.get('timeout', 3600)} s", "output": None}
            break
        sleep(float(job.get("poll_seconds", 5)))
    if outcome["status"] == "completed":
        size = comfy.view(outcome["output"], job_file.parent / OUTPUT_NAME)
        tell(f"done in {outcome['seconds']} s: {outcome['output']['filename']} ({size / 1e6:.2f} MB)")
    else:
        tell(f"failed: {outcome['error']}")
    return {**outcome, "prompt_id": prompt_id}


def main(argv: list[str]) -> int:
    """``python3 comfyui_client.py job.json``: run the job, print its outcome as JSON."""
    try:
        outcome = run_job(Path(argv[0]))
    except ComfyError as exc:
        outcome = {"status": "failed", "seconds": None, "error": str(exc), "output": None, "prompt_id": None}
    print(json.dumps(outcome), flush=True)
    return 0 if outcome["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
