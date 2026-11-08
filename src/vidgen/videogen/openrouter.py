"""OpenRouter video provider: submit, poll, download (DESIGN.md §113), standard library only.

``POST /api/v1/videos`` (202 ``{id, polling_url, status: pending}``), ``GET
/api/v1/videos/{id}`` until ``completed`` (or ``failed | cancelled | expired``), then ``GET
/api/v1/videos/{id}/content?index=0`` (the MP4). A completed job reports ``usage: {cost,
is_byok}``.

The key: ``OPENROUTER_API_KEY`` from the environment, read when a request is made, sent only
as ``Authorization: Bearer`` to openrouter.ai and scrubbed from every error; never logged or
stored. Proxy mode (``videogen.key_via_proxy: true`` or ``VIDGEN_OPENROUTER_KEY_VIA_PROXY=1``):
the network proxy adds the header, vidgen sends none and needs no key.

Paid requests are never retried automatically: a submit that fails is reported (402, 429,
413, content policy, ...). Polls and the download are free and retried on 429 / 5xx.

Inputs (frame images, references): a hosted ``url`` is sent as is. A local picture is sent
inline as a ``data:`` URL (``frame_images``: "an https URL or a base64 data URL"); the caller
sends a smaller copy of it (:func:`vidgen.videogen.pictures.sendable_request`). A local sound or
clip needs an ``uploader`` (a callable ``Path -> url``) to host it, else the request stops with a
clear error: OpenRouter refuses inline audio / video (HTTP 400 "Only HTTPS URLs are allowed",
seen in Step 296).
"""

from __future__ import annotations

import base64
import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vidgen import DIST_NAME, httpapi
from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic
from vidgen.videogen import JobState, MediaInput, VideoRequest
from vidgen.videogen.pictures import sendable_request

log = logging.getLogger("vidgen.videogen")

API_BASE = "https://openrouter.ai/api/v1"
VIDEOS_URL = f"{API_BASE}/videos"
API_KEY_ENV = "OPENROUTER_API_KEY"
PROXY_ENV = "VIDGEN_OPENROUTER_KEY_VIA_PROXY"
SERVICE = "OpenRouter"
APP_HEADERS: dict[str, str] = {"HTTP-Referer": "https://github.com/joaopauloschuler/schu-video-generator", "X-OpenRouter-Title": DIST_NAME}
#: Largest inline (base64) payload of one request: larger inputs must be hosted (413 otherwise).
MAX_INLINE_BYTES = 20 * 1024 * 1024
#: Media types of inline inputs by file suffix.
MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
}
#: Words of an error that mean the provider refused the content.
POLICY_WORDS = ("content policy", "content_policy", "moderation", "safety", "policy violation", "flagged", "not allowed")
#: Statuses of free requests (polls, download) retried with backoff.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504, 524, 529})


@dataclass(frozen=True)
class Response:
    """An HTTP answer (error statuses included)."""

    status: int
    body: bytes
    headers: Mapping[str, str]


#: ``transport(method, url, headers, body, timeout) -> Response``; raises :class:`VidgenError`
#: when the server cannot be reached.
Transport = Callable[[str, str, Mapping[str, str], bytes | None, float], Response]


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> Response:
    """The real network (urllib)."""
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return Response(answer.status, answer.read(), {k.lower(): v for k, v in answer.headers.items()})
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read(), {k.lower(): v for k, v in (exc.headers or {}).items()})
    except (TimeoutError, ConnectionError, urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        raise VidgenError(f"cannot reach {SERVICE}: {type(reason).__name__ if isinstance(reason, BaseException) else ''} {reason}".strip()) from None


def proxy_mode(setting: bool = False, environ: Mapping[str, str] | None = None) -> bool:
    """Whether the key is added by the network proxy (``setting`` or ``VIDGEN_OPENROUTER_KEY_VIA_PROXY``
    set to 1 / true / yes)."""
    env = os.environ if environ is None else environ
    return setting or env.get(PROXY_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def missing_key_message() -> str:
    """How to give vidgen the key (or say the proxy adds it)."""
    return (
        f"the environment variable {API_KEY_ENV} is not set. Set it to your OpenRouter API key (https://openrouter.ai/keys):\n"
        f"  Windows:      setx {API_KEY_ENV} your_key   (then open a new terminal)\n"
        f"  Linux/macOS:  export {API_KEY_ENV}=your_key\n"
        f"or, when a network proxy adds the key for openrouter.ai, set videogen: {{key_via_proxy: true}} (or {PROXY_ENV}=1).\n"
        "schu-video-generator never stores the key; without --pay nothing is sent."
    )


def read_key(environ: Mapping[str, str] | None = None) -> str:
    """The key from the environment (stripped). Raises :class:`VidgenError` if unset or garbled."""
    key = (os.environ if environ is None else environ).get(API_KEY_ENV, "").strip()
    if not key:
        raise VidgenError(missing_key_message())
    if not (key.isascii() and key.isprintable()) or any(c.isspace() for c in key):
        raise VidgenError(f"{API_KEY_ENV} contains spaces, control or non-ASCII characters; set it again to the key exactly as https://openrouter.ai/keys shows it")
    return key


def is_policy_error(text: str) -> bool:
    """Whether an error text says the content was refused."""
    lowered = text.lower()
    return any(word in lowered for word in POLICY_WORDS)


def _error_text(body: bytes) -> str:
    """``error.message`` of a JSON error body, else the body's start."""
    text = body.decode("utf-8", errors="replace")
    try:
        doc = json.loads(text)
        error = doc.get("error") if isinstance(doc, dict) else None
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
    except ValueError:
        pass
    return text.strip()[: httpapi.MAX_BODY_IN_ERROR] or "(empty body)"


def http_error(status: int, body: bytes, what: str, secret: str = "") -> VidgenError:
    """The :class:`VidgenError` of an HTTP error answer to ``what`` (``submit``, ``poll``, ``download``)."""
    detail = httpapi.scrub(_error_text(body), secret)
    if status == 402:
        return VidgenError(f"OpenRouter refused the {what}: not enough credits (HTTP 402: {detail}). Add credits at https://openrouter.ai/settings/credits; nothing was charged.")
    if status == 429:
        return VidgenError(f"OpenRouter refused the {what}: rate limited (HTTP 429: {detail}). Wait and run again; paid jobs are not retried automatically.")
    if status == 413:
        return VidgenError(
            f"OpenRouter refused the {what}: the request is too large (HTTP 413: {detail}). "
            "Inline inputs (data URLs) are too big: use smaller pictures / shorter audio, or host the inputs and pass their URLs."
        )
    if status in (401, 403):
        return VidgenError(f"OpenRouter refused the {what}: the key is missing or not allowed (HTTP {status}: {detail}). Check {API_KEY_ENV} or the proxy's key.")
    if is_policy_error(detail):
        return VidgenError(f"OpenRouter refused the {what} under the provider's content policy (HTTP {status}: {detail}). Change the prompt or inputs.")
    if status == 404 and what != "submit":
        return VidgenError(f"OpenRouter has no such video job (HTTP 404: {detail}); it may have expired")
    return VidgenError(f"OpenRouter returned HTTP {status} for the {what}: {detail}")


def job_failure(job: JobState) -> VidgenError:
    """The error of a job that ended without a video."""
    detail = job.error or "no reason given"
    if job.status == "expired":
        return VidgenError(
            f"video job {job.id} expired before its video was downloaded ({detail}); OpenRouter keeps outputs only a short time. "
            "Submitting it again is a new paid job."
        )
    if job.status == "cancelled":
        return VidgenError(f"video job {job.id} was cancelled ({detail})")
    if is_policy_error(detail):
        return VidgenError(f"video job {job.id} was refused under the provider's content policy: {detail}. Change the prompt or inputs.")
    return VidgenError(f"video job {job.id} failed: {detail}")


def parse_job(body: bytes, fallback_id: str | None = None) -> JobState:
    """A submit or poll answer. Raises :class:`VidgenError` if it is not one."""
    try:
        doc = json.loads(body.decode("utf-8"))
        job_id = str(doc.get("id") or fallback_id or "")
        status = str(doc["status"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise VidgenError("OpenRouter sent an unreadable video job answer (no id / status)") from None
    if not job_id:
        raise VidgenError("OpenRouter sent a video job answer without an id")
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else {}
    cost = usage.get("cost")
    error = doc.get("error")
    if isinstance(error, dict):
        error = error.get("message") or json.dumps(error)
    return JobState(
        id=job_id, status=status, polling_url=doc.get("polling_url") if isinstance(doc.get("polling_url"), str) else None,
        cost=float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        is_byok=usage.get("is_byok") if isinstance(usage.get("is_byok"), bool) else None,
        error=str(error) if error else None,
    )


class SubmitRefused(VidgenError):
    """OpenRouter answered a submit with an error that means no job was created (HTTP 4xx
    except 408). Any other failure of a submit leaves its outcome unknown."""


class OpenRouterVideoProvider:
    """OpenRouter's video API. ``transport`` (the network), ``sleep`` and ``clock`` are
    injectable for tests; ``environ`` is where the key is read (default ``os.environ``)."""

    name = "openrouter"

    def __init__(
        self,
        *,
        key_via_proxy: bool = False,
        uploader: Callable[[Path], str] | None = None,
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        environ: Mapping[str, str] | None = None,
        timeout: float = 120.0,
        poll_interval: float = 10.0,
        max_interval: float = 60.0,
        poll_timeout: float = 900.0,
        retries: int = 4,
    ) -> None:
        self.environ = environ
        self.proxy = proxy_mode(key_via_proxy, environ)
        self.uploader = uploader
        self._transport = transport if transport is not None else urllib_transport
        self._sleep = sleep if sleep is not None else time.sleep
        self._clock = clock if clock is not None else time.monotonic
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_interval = max_interval
        self.poll_timeout = poll_timeout
        self.retries = retries

    # ----- the key ---------------------------------------------------------------------------

    def check_credentials(self) -> None:
        """Raise :class:`VidgenError` with setup steps when no key is available (none needed in proxy mode)."""
        if not self.proxy:
            read_key(self.environ)

    def _headers(self, *, json_body: bool = False) -> tuple[dict[str, str], str]:
        headers = {"Accept": "application/json", **APP_HEADERS}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.proxy:
            return headers, ""
        key = read_key(self.environ)
        headers["Authorization"] = f"Bearer {key}"
        return headers, key

    def _send(self, method: str, url: str, body: bytes | None, what: str, *, retry: bool) -> Response:
        headers, secret = self._headers(json_body=body is not None)
        attempt = 0
        while True:
            try:
                answer = self._transport(method, url, headers, body, self.timeout)
            except VidgenError as exc:
                if not retry or attempt >= self.retries:
                    raise VidgenError(httpapi.scrub(str(exc), secret)) from None
                answer = None
            if answer is not None and answer.status < 400:
                return answer
            if answer is not None and (not retry or answer.status not in RETRY_STATUS or attempt >= self.retries):
                error = http_error(answer.status, answer.body, what, secret)
                raise SubmitRefused(str(error)) if what == "submit" and 400 <= answer.status < 500 and answer.status != 408 else error
            wait = httpapi.retry_after(_Headers(answer.headers)) if answer is not None else None  # type: ignore[arg-type]
            self._sleep(min(wait if wait is not None else self.poll_interval * 2**attempt, self.max_interval))
            attempt += 1

    # ----- inputs ----------------------------------------------------------------------------

    def media_url(self, media: MediaInput) -> str:
        """The URL sent for an input: hosted as is, a local file inline or uploaded (see the module docstring)."""
        if media.url is not None:
            return media.url
        assert media.path is not None
        if media.kind != "image":
            if self.uploader is not None:
                return self.uploader(media.path)
            raise VidgenError(
                f"the {media.kind} input {media.path} must be hosted: audio/video references must be https URLs; "
                "OpenRouter refuses inline audio/video (pictures may be sent inline). Give its url"
            )
        media_type = MEDIA_TYPES.get(media.path.suffix.lower())
        if media_type is None or not media_type.startswith(media.kind):
            raise VidgenError(f"{media.path}: not a {media.kind} file vidgen can send ({', '.join(s for s, t in MEDIA_TYPES.items() if t.startswith(media.kind))})")
        try:
            data = media.path.read_bytes()
        except OSError as exc:
            raise VidgenError(f"cannot read {media.path}: {exc.strerror or exc}") from None
        return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"

    def request_body(self, request: VideoRequest, drop: set[str] | frozenset[str] = frozenset()) -> dict[str, Any]:
        """The JSON body of ``POST /videos`` (``generate_audio`` always false; ``drop``: fields not sent)."""
        body: dict[str, Any] = {"model": request.model}
        if request.prompt:
            body["prompt"] = request.prompt
        for name in ("duration", "resolution", "size", "aspect_ratio", "seed", "previous_job_id"):
            value = getattr(request, name)
            if value is not None and name not in drop:
                body[name] = value
        body["generate_audio"] = False
        if request.frame_images:
            body["frame_images"] = [
                {"type": "image_url", "image_url": {"url": self.media_url(f)}, "frame_type": f.frame_type} for f in request.frame_images
            ]
        if request.references:
            body["input_references"] = [{"type": f"{r.kind}_url", f"{r.kind}_url": {"url": self.media_url(r)}} for r in request.references]
        if request.provider_options:
            body["provider"] = {"options": {slug: {"parameters": dict(p)} for slug, p in request.provider_options.items()}}
        return body

    # ----- the job ---------------------------------------------------------------------------

    def submit(
        self, request: VideoRequest, drop: set[str] | frozenset[str] = frozenset(), *, on_sending: Callable[[], None] | None = None,
    ) -> JobState:
        """Submit one paid job (never retried). ``on_sending`` runs once the request is ready, just
        before it is sent (nothing is sent if it raises). Raises :class:`VidgenError`
        (:class:`SubmitRefused` when the answer means no job exists)."""
        data = json.dumps(self.request_body(request, drop)).encode("utf-8")
        if len(data) > MAX_INLINE_BYTES:
            raise VidgenError(
                f"the request is {len(data) / 1e6:.1f} MB with its inline inputs, more than vidgen sends ({MAX_INLINE_BYTES / 1e6:.0f} MB): "
                "use smaller inputs or host them and pass their URLs"
            )
        if on_sending is not None:
            on_sending()
        answer = self._send("POST", VIDEOS_URL, data, "submit", retry=False)
        job = parse_job(answer.body)
        log.info("submitted video job %s (%s)", job.id, request.model)
        return job

    def status(self, job_id: str) -> JobState:
        """The job's current state (a free poll, retried on 429 / 5xx)."""
        answer = self._send("GET", f"{VIDEOS_URL}/{job_id}", None, "poll", retry=True)
        return parse_job(answer.body, job_id)

    def wait(self, job: JobState, *, on_status: Callable[[JobState], None] | None = None) -> JobState:
        """Poll until the job finishes: every ``poll_interval`` s, growing 1.5x up to
        ``max_interval``, for at most ``poll_timeout`` s. Raises :class:`VidgenError` on timeout
        (the job keeps running: a later run polls it again, it is not submitted twice)."""
        start = self._clock()
        interval = self.poll_interval
        while not job.done:
            if self._clock() - start > self.poll_timeout:
                raise VidgenError(
                    f"video job {job.id} is still {job.status} after {self.poll_timeout:.0f} s; it was paid for and keeps running: "
                    "run again later to poll it (it is not submitted twice)"
                )
            self._sleep(interval)
            interval = min(interval * 1.5, self.max_interval)
            job = self.status(job.id)
            if on_status is not None:
                on_status(job)
        return job

    def download(self, job_id: str, dest: Path) -> int:
        """Save the job's video (``/content?index=0``) to ``dest``; its size in bytes."""
        answer = self._send("GET", f"{VIDEOS_URL}/{job_id}/content?index=0", None, "download", retry=True)
        if not answer.body:
            raise VidgenError(f"OpenRouter sent an empty video for job {job_id}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(dest, answer.body)
        return len(answer.body)


def request_bytes(request: VideoRequest, root: Path) -> int:
    """Size of the JSON body vidgen would send for ``request``: local pictures inline as their
    smaller copies (made in ``root``'s build folder), local audio / video counted as hosted URLs."""
    provider = OpenRouterVideoProvider(environ={}, uploader=lambda path: f"https://hosted.invalid/{path.name}")
    return len(json.dumps(provider.request_body(sendable_request(request, root))).encode("utf-8"))


class _Headers:
    """A mapping seen as an ``email.message.Message`` for :func:`httpapi.retry_after`."""

    def __init__(self, headers: Mapping[str, str]) -> None:
        self._h = {k.lower(): v for k, v in headers.items()}

    def get(self, name: str, default: Any = None) -> Any:
        return self._h.get(name.lower(), default)
