"""The ``elevenlabs`` speech-to-text provider (DESIGN.md §57): ElevenLabs Speech to Text
(``POST /v1/speech-to-text``, model ``scribe_v1``), with the ``ELEVENLABS_API_KEY`` that
``vidgen tts`` uses. Standard library only; paid per audio hour.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.stt import Transcript, TranscriptWord
from vidgen.tts.elevenlabs import post_with_retries, read_api_key

STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


def multipart_body(fields: dict[str, str], file_field: str, filename: str, data: bytes, content_type: str) -> tuple[bytes, str]:
    """A ``multipart/form-data`` body with text ``fields`` and one file; ``(body, content type
    with the boundary)``."""
    boundary = f"vidgen-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class ElevenLabsSTTProvider:
    """Transcribe with ElevenLabs ``model`` (``scribe_v1``) in ``language`` (ISO 639-1 / 639-3;
    ``None``: detected). Retries as the TTS provider does (``sleep`` injectable for tests)."""

    name = "elevenlabs"

    def __init__(
        self,
        model: str,
        language: str | None,
        *,
        timeout: float = 300.0,
        retries: int = 3,
        backoff: float = 2.0,
        max_wait: float = 30.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.model = model
        self.language = language
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_wait = max_wait
        self._sleep = sleep if sleep is not None else time.sleep

    def check_available(self) -> None:
        """Raise :class:`VidgenError` with setup instructions if ``ELEVENLABS_API_KEY`` is unset."""
        read_api_key()

    def form_fields(self) -> dict[str, str]:
        """The text fields of a request: model, word timestamps, no audio-event tags, and the
        language when it is known."""
        fields = {"model_id": self.model, "timestamps_granularity": "word", "tag_audio_events": "false"}
        if self.language is not None:
            fields["language_code"] = self.language
        return fields

    def transcribe(self, path: Path) -> Transcript:
        """What is said in ``path`` (an MP3)."""
        try:
            audio = path.read_bytes()
        except OSError as exc:
            raise VidgenError(f"cannot read audio file {path}: {exc}") from None
        body, content_type = multipart_body(self.form_fields(), "file", path.name, audio, "audio/mpeg")
        reply = post_with_retries(
            STT_URL, body, content_type=content_type, accept="application/json", timeout=self.timeout,
            retries=self.retries, backoff=self.backoff, max_wait=self.max_wait, sleep=self._sleep,
        )
        return parse_response(reply)


def parse_response(body: bytes) -> Transcript:
    """The transcript of an ElevenLabs Speech to Text response: ``{language_code, text, words:
    [{text, start, end, type}]}`` (only ``type: word`` entries are words; spacing and audio
    events are left out)."""
    try:
        doc: Any = json.loads(body.decode("utf-8"))
        text = str(doc["text"])
        words = tuple(
            TranscriptWord(str(w["text"]).strip(), float(w.get("start") or 0.0), float(w.get("end") or 0.0))
            for w in doc.get("words") or ()
            if w.get("type", "word") == "word" and str(w.get("text", "")).strip()
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        raise VidgenError("ElevenLabs returned an unreadable speech-to-text response (no text)") from None
    language = doc.get("language_code")
    return Transcript(text.strip(), words, str(language) if language else None)
