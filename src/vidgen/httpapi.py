"""POST requests to a paid web API with retries and scrubbed errors (standard library only).

Shared by the ElevenLabs text-to-speech / speech-to-text providers and the image-generation
providers (OpenAI, OpenRouter). The API key is passed in by the caller (read from an environment variable at the
moment of the request); it goes only into the request headers and is removed from every error
message.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from email.message import Message

from vidgen.errors import VidgenError

#: HTTP statuses retried by default (rate limit, server errors).
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})
#: Characters of an error response's body quoted in the error message.
MAX_BODY_IN_ERROR = 500


def scrub(text: str, secret: str) -> str:
    """``text`` with ``secret`` replaced by ``***`` (defensive: it should never be there)."""
    return text.replace(secret, "***") if secret else text


def retry_after(headers: Message | None) -> float | None:
    """The ``Retry-After`` header in seconds, or ``None`` (missing or not a number)."""
    value = headers.get("Retry-After") if headers is not None else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


def post_with_retries(
    url: str,
    data: bytes,
    *,
    headers: Mapping[str, str],
    service: str,
    secret: str,
    timeout: float,
    retries: int,
    backoff: float,
    max_wait: float,
    sleep: Callable[[float], None],
    transient: Callable[[int, str], bool] | None = None,
    response_headers: dict[str, str] | None = None,
) -> bytes:
    """POST ``data`` to ``url`` with ``headers``; the response body.

    Transient failures (by default HTTP 429 / 5xx; ``transient(status, body)`` decides instead
    when given), timeouts and dropped connections are retried ``retries`` times, waiting
    ``backoff * 2**attempt`` seconds or the server's ``Retry-After``, at most ``max_wait``. Every
    failure becomes a :class:`VidgenError` naming ``service`` without ``secret`` in it. A
    ``response_headers`` dict receives the successful response's headers (names lower case).
    """
    is_transient = transient if transient is not None else (lambda status, body: status in TRANSIENT_STATUS)
    attempt = 0
    while True:
        wait: float | None = None
        try:
            return _request(url, data, headers, timeout, service, response_headers)
        except urllib.error.HTTPError as exc:
            body = scrub(exc.read().decode("utf-8", errors="replace"), secret)
            if not is_transient(exc.code, body) or attempt >= retries:
                if len(body) > MAX_BODY_IN_ERROR:
                    body = body[:MAX_BODY_IN_ERROR] + "..."
                raise VidgenError(f"{service} returned HTTP {exc.code}: {body.strip() or '(empty body)'}") from None
            wait = retry_after(exc.headers)
        except (TimeoutError, ConnectionError, urllib.error.URLError) as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if not isinstance(reason, (TimeoutError, ConnectionError)) or attempt >= retries:
                what = f"{type(reason).__name__}: {reason}" if isinstance(reason, BaseException) else str(reason)
                raise VidgenError(f"cannot reach {service}: {scrub(what, secret)}") from None
        except VidgenError:
            raise
        except Exception as exc:  # e.g. http.client rejecting a malformed header value
            raise VidgenError(f"{service} request failed: {type(exc).__name__}: {scrub(str(exc), secret)}") from None
        delay = wait if wait is not None else backoff * 2**attempt
        sleep(min(delay, max_wait))
        attempt += 1


def get(url: str, *, headers: Mapping[str, str], service: str, timeout: float) -> bytes:
    """GET ``url`` once (no retries: for free lookups that may fail, such as a public price
    list). Raises ``urllib.error.HTTPError`` for an HTTP error status (the caller decides what
    a 404 means) and :class:`VidgenError` when ``service`` cannot be reached."""
    request = urllib.request.Request(url, method="GET", headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError:
        raise
    except (TimeoutError, ConnectionError, urllib.error.URLError, OSError, ValueError) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        what = f"{type(reason).__name__}: {reason}" if isinstance(reason, BaseException) else str(reason)
        raise VidgenError(f"cannot reach {service}: {what}") from None


def _request(
    url: str, data: bytes, headers: Mapping[str, str], timeout: float, service: str, got: dict[str, str] | None = None
) -> bytes:
    request = urllib.request.Request(url, data=data, method="POST", headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        received = getattr(response, "headers", None)
        if got is not None and received is not None:
            got.update({str(k).lower(): str(v) for k, v in received.items()})
    if not body:
        raise VidgenError(f"{service} returned an empty response")
    return body
