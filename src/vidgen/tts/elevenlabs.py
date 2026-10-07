"""ElevenLabs text-to-speech provider (DESIGN.md §7). Standard library only.

The API key is read from the environment variable ``ELEVENLABS_API_KEY`` at the moment a request
is made. It is never stored on the provider, logged, written to a file or included in an error
message: it is only sent as the ``xi-api-key`` header to api.elevenlabs.io.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import time
import urllib.parse
from collections.abc import Callable
from typing import Any

from vidgen import httpapi
from vidgen.config import VoiceConfig
from vidgen.errors import VidgenError

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={output_format}"
#: The same speech as JSON with the audio in base64 and character timings (``alignment``).
TIMESTAMPS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format={output_format}"
API_KEY_ENV = "ELEVENLABS_API_KEY"

#: Values the kphi3 script used implicitly; its hash files are only valid for these.
LEGACY_OUTPUT_FORMAT = "mp3_44100_128"
LEGACY_SETTINGS: dict[str, Any] = {
    "stability": 0.55,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}

def missing_key_message() -> str:
    """How to set the API key, for the error shown when it is missing."""
    return (
        f"the environment variable {API_KEY_ENV} is not set. Set it to your ElevenLabs API key:\n"
        f"  Windows:      setx {API_KEY_ENV} your_key   (then open a new terminal)\n"
        f"  Linux/macOS:  export {API_KEY_ENV}=your_key\n"
        "vidgen never stores the key; `vidgen tts --dry-run` works without it."
    )


def read_api_key() -> str:
    """The API key from the environment (stripped). Raises :class:`VidgenError` if unset."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise VidgenError(missing_key_message())
    return key


class ElevenLabsProvider:
    """Synthesise speech with one ElevenLabs voice configuration.

    ``retries`` transient failures (HTTP 429/5xx, timeouts, dropped connections) are retried
    with exponential backoff (``backoff * 2**attempt`` seconds, or the server's ``Retry-After``,
    capped at ``max_wait``). ``sleep`` is injectable for tests.
    """

    name = "elevenlabs"

    def __init__(
        self,
        voice: VoiceConfig,
        *,
        timeout: float = 120.0,
        retries: int = 3,
        backoff: float = 2.0,
        max_wait: float = 30.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.voice = voice
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_wait = max_wait
        self._sleep = sleep if sleep is not None else time.sleep

    # ----- cache keys ------------------------------------------------------------------------

    @property
    def settings(self) -> dict[str, Any]:
        """``voice_settings`` as sent to the API."""
        return self.voice.settings.model_dump()

    @property
    def language_code(self) -> str | None:
        """The ``language_code`` sent with every request (``voice.language_code`` when it is a
        code; resolved from the video's language by :func:`vidgen.voices.resolve_voice`)."""
        code = self.voice.language_code
        return code if isinstance(code, str) else None

    def cache_key(self, text: str) -> str:
        """sha1 of ``voice_id|model_id|output_format|json(settings, sort_keys)|text``; with a
        language code sent, ``language_code=<code>`` comes before the text (DESIGN.md §54)."""
        v = self.voice
        parts = [v.voice_id, v.model_id, v.output_format, json.dumps(self.settings, sort_keys=True), text]
        if self.language_code is not None:
            parts.insert(4, f"language_code={self.language_code}")
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()

    def legacy_cache_key(self, text: str) -> str | None:
        """The kphi3 hash ``sha1(voice_id + model_id + text)``, or ``None`` when the output format
        or settings differ from the values kphi3 used (its hash files say nothing about them)."""
        v = self.voice
        if v.output_format != LEGACY_OUTPUT_FORMAT or self.settings != LEGACY_SETTINGS or self.language_code is not None:
            return None
        return hashlib.sha1((v.voice_id + v.model_id + text).encode("utf-8")).hexdigest()

    def matches(self, text: str, stored: str) -> bool:
        """True if a stored hash says the audio for ``text`` is up to date (current or kphi3 format)."""
        stored = stored.strip()
        return stored == self.cache_key(text) or (stored != "" and stored == self.legacy_cache_key(text))

    # ----- synthesis -------------------------------------------------------------------------

    def request_body(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> dict[str, Any]:
        """JSON body for one request; neighbours are sent only when ``voice.context`` is on."""
        body: dict[str, Any] = {"text": text, "model_id": self.voice.model_id, "voice_settings": self.settings}
        if self.language_code is not None:
            body["language_code"] = self.language_code
        if self.voice.context:
            if previous_text is not None:
                body["previous_text"] = previous_text
            if next_text is not None:
                body["next_text"] = next_text
        return body

    def url(self, timestamps: bool = False) -> str:
        """The endpoint for this voice and output format (``timestamps``: the with-timestamps one)."""
        return (TIMESTAMPS_URL if timestamps else API_URL).format(
            voice_id=urllib.parse.quote(self.voice.voice_id, safe=""),
            output_format=urllib.parse.quote(self.voice.output_format, safe=""),
        )

    def check_credentials(self) -> None:
        """Raise :class:`VidgenError` with setup instructions if ``ELEVENLABS_API_KEY`` is unset."""
        read_api_key()

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        """Return the audio bytes for ``text``. Raises :class:`VidgenError` on any failure."""
        return self._send(self.url(), self.request_body(text, previous_text, next_text), "audio/mpeg")

    def synthesize_timed(
        self, text: str, previous_text: str | None = None, next_text: str | None = None
    ) -> tuple[bytes, dict[str, Any] | None]:
        """The audio bytes for ``text`` and when each character is spoken (the with-timestamps
        endpoint): ``(audio, {characters, character_start_times_seconds,
        character_end_times_seconds})``, the timings ``None`` if the response has none. Raises
        :class:`VidgenError` on any failure."""
        body = self._send(self.url(timestamps=True), self.request_body(text, previous_text, next_text), "application/json")
        try:
            doc = json.loads(body.decode("utf-8"))
            audio = base64.b64decode(doc["audio_base64"], validate=True)
        except (ValueError, KeyError, TypeError, binascii.Error):
            raise VidgenError("ElevenLabs returned an unreadable with-timestamps response (no audio_base64)") from None
        if not audio:
            raise VidgenError("ElevenLabs returned an empty response")
        alignment = doc.get("alignment")
        keys = ("characters", "character_start_times_seconds", "character_end_times_seconds")
        if not isinstance(alignment, dict) or not all(isinstance(alignment.get(k), list) for k in keys):
            alignment = None
        elif not len(alignment["characters"]) == len(alignment[keys[1]]) == len(alignment[keys[2]]):
            alignment = None
        return audio, alignment

    def _send(self, url: str, payload: dict[str, Any], accept: str) -> bytes:
        """POST ``payload`` to ``url`` with retries; the response body."""
        data = json.dumps(payload).encode("utf-8")
        return post_with_retries(
            url, data, content_type="application/json", accept=accept, timeout=self.timeout,
            retries=self.retries, backoff=self.backoff, max_wait=self.max_wait, sleep=self._sleep,
        )


def post_with_retries(
    url: str,
    data: bytes,
    *,
    content_type: str,
    accept: str,
    timeout: float,
    retries: int,
    backoff: float,
    max_wait: float,
    sleep: Callable[[float], None],
) -> bytes:
    """POST ``data`` to an ElevenLabs ``url`` with the API key from the environment; the
    response body. Transient failures are retried ``retries`` times (``backoff * 2**attempt``
    seconds or ``Retry-After``, at most ``max_wait``); every failure becomes a
    :class:`VidgenError` without the key in it (shared by text to speech and speech to text;
    the loop itself is :func:`vidgen.httpapi.post_with_retries`)."""
    key = read_api_key()
    return httpapi.post_with_retries(
        url, data, headers={"xi-api-key": key, "Content-Type": content_type, "Accept": accept}, service="ElevenLabs",
        secret=key, timeout=timeout, retries=retries, backoff=backoff, max_wait=max_wait, sleep=sleep,
    )
