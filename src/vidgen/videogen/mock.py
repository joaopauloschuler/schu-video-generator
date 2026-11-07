"""A fake OpenRouter video API for tests and free dry demos (DESIGN.md §113).

:class:`MockOpenRouter` is a transport that answers like ``/api/v1/videos``: a submit makes a
job (202), each poll moves it one step through ``states`` (default pending, in_progress,
completed), a completed job reports ``usage.cost``, and its content is ``video`` bytes. It
records every request (method, url, headers, JSON body) so tests can check what would have been
sent. ``submit_error`` / ``poll_error`` (``(status, message)``) and a ``states`` list ending in
``failed`` / ``expired`` script the failures. :class:`MockVideoProvider` is the OpenRouter
provider on it (``videogen: {provider: mock}``): no key, no network, nothing charged.

The content of a completed job is ``video`` when given, else a real, playable MP4 made by FFmpeg
(:func:`synthetic_clip`: a moving test pattern of the submitted length, in the submitted aspect
ratio at the submitted resolution's short side, no sound), so placing, QA and contact sheets work
on mock takes. :func:`synthetic_clip` also makes the bad clips QA tests need (black, frozen,
flickering, an abrupt cut).
"""

from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vidgen.videogen.openrouter import VIDEOS_URL, OpenRouterVideoProvider, Response

#: Placeholder bytes for tests that only move files around (not a playable video).
MOCK_VIDEO = b"\x00\x00\x00\x18ftypmp42vidgen-mock-video"
#: Patterns :func:`synthetic_clip` draws.
Pattern = Literal["testsrc", "bars", "black", "frozen", "flicker", "cut"]
#: Short side of a mock clip when the request names no resolution.
MOCK_SHORT_SIDE = 360


def synthetic_clip(
    path: Path, width: int, height: int, seconds: float, *, fps: int = 24, pattern: Pattern = "testsrc", audio: bool = False,
) -> Path:
    """Write an H.264 MP4 of ``seconds`` at ``width`` x ``height`` (rounded to even) and ``fps``:
    ``testsrc`` (a moving test pattern), ``bars`` (still colour bars), ``black``, ``frozen`` (1 s of
    movement, then its last frame held), ``flicker`` (brightness jumping every frame) or ``cut``
    (the moving pattern turning solid red half-way). ``audio``: with a sine tone (a model's own
    sound, which vidgen drops)."""
    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    w, h = 2 * max(1, round(width / 2)), 2 * max(1, round(height / 2))
    size = f"{w}x{h}"
    source = {
        "bars": f"smptebars=size={size}:rate={fps}",
        "black": f"color=c=black:size={size}:rate={fps}",
    }.get(pattern, f"testsrc2=size={size}:rate={fps}")
    filters = {
        "frozen": [f"trim=end={min(1.0, seconds / 2):.3f}", f"tpad=stop_mode=clone:stop_duration={seconds:.3f}"],
        "flicker": ["eq=brightness=0.3*(2*mod(n\\,2)-1):eval=frame"],
        "cut": [f"drawbox=x=0:y=0:w=iw:h=ih:color=red@1:t=fill:enable='gte(t,{seconds / 2:.3f})'"],
    }.get(pattern, [])
    args = ["-f", "lavfi", "-i", source]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    args += ["-t", f"{seconds:.3f}", "-vf", ",".join([*filters, "format=yuv420p"]), "-c:v", "libx264", "-preset", "ultrafast", "-r", str(fps)]
    args += ["-c:a", "aac", "-shortest"] if audio else ["-an"]
    path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(find_ffmpeg(), [*args, str(path)], f"making a {pattern} test clip")
    return path


def clip_size(aspect_ratio: str | None, resolution: str | None, size: str | None = None) -> tuple[int, int]:
    """The picture size a request asks for: ``size`` (WxH) as is, else the resolution tier's short
    side (``MOCK_SHORT_SIDE`` without one) in the aspect ratio (16:9 without one)."""
    from vidgen.videogen.models import TIER_SHORT_SIDE

    if size and "x" in size:
        w, _, h = size.partition("x")
        return int(w), int(h)
    short = TIER_SHORT_SIDE.get((resolution or "").lower(), MOCK_SHORT_SIDE)
    a, _, b = (aspect_ratio or "16:9").partition(":")
    ratio = float(a) / float(b)
    return (round(short * ratio), short) if ratio >= 1 else (short, round(short / ratio))


@dataclass
class SentRequest:
    """A request the mock received."""

    method: str
    url: str
    headers: dict[str, str]
    body: Any


@dataclass
class MockOpenRouter:
    """The fake API (see the module docstring)."""

    states: Sequence[str] = ("pending", "in_progress", "completed")
    cost: float | None = 0.25
    video: bytes | None = None
    error: str | None = None
    submit_error: tuple[int, str] | None = None
    poll_error: tuple[int, str] | None = None
    poll_errors: int = 1
    pattern: Pattern = "testsrc"
    prefix: str = "mock-job"
    requests: list[SentRequest] = field(default_factory=list)
    jobs: dict[str, int] = field(default_factory=dict)
    bodies: dict[str, Any] = field(default_factory=dict)
    made: dict[str, bytes] = field(default_factory=dict)

    def content(self, job_id: str) -> bytes:
        """The MP4 of job ``job_id``: ``video``, else a synthetic clip shaped like its request."""
        if self.video is not None:
            return self.video
        if job_id not in self.made:
            body = self.bodies.get(job_id) or {}
            width, height = clip_size(body.get("aspect_ratio"), body.get("resolution"), body.get("size"))
            seconds = float(body.get("duration") or 5)
            with tempfile.TemporaryDirectory(prefix="vidgen_mock_") as folder:
                path = synthetic_clip(Path(folder) / "clip.mp4", width, height, seconds, pattern=self.pattern)
                self.made[job_id] = path.read_bytes()
        return self.made[job_id]

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> Response:
        self.requests.append(SentRequest(method, url, dict(headers), json.loads(body) if body else None))
        if method == "POST" and url == VIDEOS_URL:
            if self.submit_error is not None:
                return _error(*self.submit_error)
            job_id = f"{self.prefix}-{len(self.jobs) + 1}"
            self.jobs[job_id] = 0
            self.bodies[job_id] = self.requests[-1].body
            return _json(202, {"id": job_id, "polling_url": f"{VIDEOS_URL}/{job_id}", "status": "pending"})
        path = url[len(VIDEOS_URL) + 1:] if url.startswith(VIDEOS_URL + "/") else ""
        job_id, _, rest = path.partition("/")
        if method != "GET" or job_id not in self.jobs:
            return _error(404, f"no video job {job_id or url}")
        if rest.startswith("content"):
            if self.states[min(self.jobs[job_id], len(self.states) - 1)] != "completed":
                return _error(409, "the video is not ready")
            return Response(200, self.content(job_id), {"content-type": "video/mp4"})
        if self.poll_error is not None and self.poll_errors > 0:
            self.poll_errors -= 1
            return _error(*self.poll_error)
        self.jobs[job_id] = min(self.jobs[job_id] + 1, len(self.states) - 1)
        status = self.states[self.jobs[job_id]]
        doc: dict[str, Any] = {"id": job_id, "status": status}
        if status == "completed":
            doc["unsigned_urls"] = [f"https://mock.invalid/{job_id}.mp4"]
            doc["usage"] = {"cost": self.cost, "is_byok": False} if self.cost is not None else None
        elif status in ("failed", "cancelled", "expired"):
            doc["error"] = self.error or f"job {status}"
        return _json(200, doc)

    @property
    def submits(self) -> list[SentRequest]:
        """The submit requests received."""
        return [r for r in self.requests if r.method == "POST"]


def _json(status: int, doc: Any) -> Response:
    return Response(status, json.dumps(doc).encode("utf-8"), {"content-type": "application/json"})


def _error(status: int, message: str) -> Response:
    return _json(status, {"error": {"code": status, "message": message}})


class MockVideoProvider(OpenRouterVideoProvider):
    """The OpenRouter provider on :class:`MockOpenRouter`: proxy mode (no key, no
    ``Authorization`` header), no waiting. Without ``api`` (``videogen.provider: mock``) its job
    ids are unique across runs (``mock-<8 hex>-1``), so the mock ledger counts every job."""

    name = "mock"

    def __init__(self, api: MockOpenRouter | None = None, **kwargs: Any) -> None:
        self.api = api if api is not None else MockOpenRouter(prefix=f"mock-{uuid.uuid4().hex[:8]}")
        kwargs.setdefault("sleep", lambda seconds: None)
        super().__init__(key_via_proxy=True, transport=self.api, **kwargs)
