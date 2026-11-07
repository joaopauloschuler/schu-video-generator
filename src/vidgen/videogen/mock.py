"""A fake OpenRouter video API for tests and free dry demos (DESIGN.md §113).

:class:`MockOpenRouter` is a transport that answers like ``/api/v1/videos``: a submit makes a
job (202), each poll moves it one step through ``states`` (default pending, in_progress,
completed), a completed job reports ``usage.cost``, and its content is ``video`` bytes. It
records every request (method, url, headers, JSON body) so tests can check what would have been
sent. ``submit_error`` / ``poll_error`` (``(status, message)``) and a ``states`` list ending in
``failed`` / ``expired`` script the failures. :class:`MockVideoProvider` is the OpenRouter
provider on it (``videogen: {provider: mock}``): no key, no network, nothing charged.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidgen.videogen.openrouter import VIDEOS_URL, OpenRouterVideoProvider, Response

#: The bytes of a mock clip (not a playable video).
MOCK_VIDEO = b"\x00\x00\x00\x18ftypmp42vidgen-mock-video"


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
    video: bytes = MOCK_VIDEO
    error: str | None = None
    submit_error: tuple[int, str] | None = None
    poll_error: tuple[int, str] | None = None
    poll_errors: int = 1
    requests: list[SentRequest] = field(default_factory=list)
    jobs: dict[str, int] = field(default_factory=dict)

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> Response:
        self.requests.append(SentRequest(method, url, dict(headers), json.loads(body) if body else None))
        if method == "POST" and url == VIDEOS_URL:
            if self.submit_error is not None:
                return _error(*self.submit_error)
            job_id = f"mock-job-{len(self.jobs) + 1}"
            self.jobs[job_id] = 0
            return _json(202, {"id": job_id, "polling_url": f"{VIDEOS_URL}/{job_id}", "status": "pending"})
        path = url[len(VIDEOS_URL) + 1:] if url.startswith(VIDEOS_URL + "/") else ""
        job_id, _, rest = path.partition("/")
        if method != "GET" or job_id not in self.jobs:
            return _error(404, f"no video job {job_id or url}")
        if rest.startswith("content"):
            if self.states[min(self.jobs[job_id], len(self.states) - 1)] != "completed":
                return _error(409, "the video is not ready")
            return Response(200, self.video, {"content-type": "video/mp4"})
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
    ``Authorization`` header), no waiting."""

    name = "mock"

    def __init__(self, api: MockOpenRouter | None = None, **kwargs: Any) -> None:
        self.api = api if api is not None else MockOpenRouter()
        kwargs.setdefault("sleep", lambda seconds: None)
        super().__init__(key_via_proxy=True, transport=self.api, **kwargs)
