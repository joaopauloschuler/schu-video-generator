"""OpenAI Images provider (``POST /v1/images/generations``), standard library only (DESIGN.md §58).

The API key is read from the environment variable ``OPENAI_API_KEY`` when a request is made. It
is never stored, logged, written to a file or included in an error message: it is only sent as
the ``Authorization: Bearer`` header to api.openai.com.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import time
from collections.abc import Callable
from typing import Any

from vidgen import httpapi
from vidgen.errors import VidgenError
from vidgen.imagegen import GeneratedPicture, ImageRequest, model_family

API_URL = "https://api.openai.com/v1/images/generations"
API_KEY_ENV = "OPENAI_API_KEY"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def missing_key_message() -> str:
    """How to set the API key, for the error shown when it is missing."""
    return (
        f"the environment variable {API_KEY_ENV} is not set. Set it to your OpenAI API key:\n"
        f"  Windows:      setx {API_KEY_ENV} your_key   (then open a new terminal)\n"
        f"  Linux/macOS:  export {API_KEY_ENV}=your_key\n"
        "vidgen never stores the key; `vidgen imagegen --dry-run` works without it."
    )


def read_api_key() -> str:
    """The API key from the environment (stripped). Raises :class:`VidgenError` if unset."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise VidgenError(missing_key_message())
    return key


def _transient(status: int, body: str) -> bool:
    """429 (rate limit) and 5xx are retried, but not a 429 for an exhausted quota or billing
    limit: waiting does not help."""
    if status == 429:
        return "insufficient_quota" not in body and "billing_hard_limit" not in body
    return status in httpapi.TRANSIENT_STATUS


def as_png(data: bytes) -> bytes:
    """``data`` as PNG bytes (converted with Pillow when the API returned another format).
    Raises :class:`VidgenError` if it is not a picture."""
    if data.startswith(PNG_SIGNATURE):
        return data
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as im:
            out = io.BytesIO()
            im.convert("RGBA" if "A" in im.getbands() else "RGB").save(out, format="PNG")
    except (UnidentifiedImageError, OSError):
        raise VidgenError("OpenAI returned data that is not a picture") from None
    return out.getvalue()


def parse_response(body: bytes) -> GeneratedPicture:
    """The picture and revised prompt of an Images API response ``{data: [{b64_json,
    revised_prompt}]}``. Raises :class:`VidgenError` if it holds no picture."""
    try:
        doc = json.loads(body.decode("utf-8"))
        item = doc["data"][0]
        data = base64.b64decode(item["b64_json"], validate=True)
    except (ValueError, KeyError, IndexError, TypeError, binascii.Error):
        raise VidgenError("OpenAI returned an unreadable response (no data[0].b64_json)") from None
    if not data:
        raise VidgenError("OpenAI returned an empty picture")
    revised = item.get("revised_prompt")
    return GeneratedPicture(as_png(data), revised if isinstance(revised, str) and revised.strip() else None)


class OpenAIImageProvider:
    """Generate pictures with the OpenAI Images API (gpt-image-1, dall-e-3, dall-e-2).

    ``retries`` transient failures (HTTP 429 / 5xx, timeouts, dropped connections) are retried
    with exponential backoff (``backoff * 2**attempt`` seconds, or the server's ``Retry-After``,
    capped at ``max_wait``). ``sleep`` is injectable for tests.
    """

    name = "openai"

    def __init__(
        self,
        *,
        timeout: float = 240.0,
        retries: int = 3,
        backoff: float = 4.0,
        max_wait: float = 60.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_wait = max_wait
        self._sleep = sleep if sleep is not None else time.sleep

    def check_credentials(self) -> None:
        """Raise :class:`VidgenError` with setup instructions if ``OPENAI_API_KEY`` is unset."""
        read_api_key()

    @staticmethod
    def request_body(request: ImageRequest) -> dict[str, Any]:
        """JSON body for ``request``: model, prompt, one picture, size, quality; DALL·E models
        are asked for base64 (gpt-image models always return it)."""
        body: dict[str, Any] = {"model": request.model, "prompt": request.text, "n": 1, "size": request.size}
        if request.quality is not None:
            body["quality"] = request.quality
        if model_family(request.model) != "gpt-image":
            body["response_format"] = "b64_json"
        return body

    def generate(self, request: ImageRequest) -> GeneratedPicture:
        """The picture of ``request``. Raises :class:`VidgenError` on any failure."""
        key = read_api_key()
        data = json.dumps(self.request_body(request)).encode("utf-8")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
        body = httpapi.post_with_retries(
            API_URL, data, headers=headers, service="OpenAI", secret=key, timeout=self.timeout, retries=self.retries,
            backoff=self.backoff, max_wait=self.max_wait, sleep=self._sleep, transient=_transient,
        )
        return parse_response(body)
