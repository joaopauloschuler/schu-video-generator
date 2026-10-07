"""Speech-to-text: the provider seam of ``vidgen readback`` (DESIGN.md §57).

- :func:`get_stt_provider` returns the provider for a project's ``stt:`` section:
  ``faster_whisper`` (local, free; the optional extra ``vidgen[stt]``) or ``elevenlabs``
  (ElevenLabs Speech to Text, the ``ELEVENLABS_API_KEY`` of ``vidgen tts``).
- :func:`stt_settings` gives what a transcript depends on (provider, model, language), without
  importing a provider library: the transcript cache (:mod:`vidgen.readback`) and the
  ``readback`` lint rule key on it.
- A provider returns a :class:`Transcript`: the text heard and its words with times.

No manim import.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from vidgen.errors import VidgenError
from vidgen.languages import primary_language

if TYPE_CHECKING:
    from vidgen.config import SttConfig
    from vidgen.project import Project

#: Providers ``stt.provider`` accepts.
STT_PROVIDERS: tuple[str, ...] = ("faster_whisper", "elevenlabs")
#: The model of each provider when ``stt.model`` is not set (faster-whisper: ``small.en`` for
#: English, see :func:`stt_settings`).
DEFAULT_MODELS: dict[str, str] = {"faster_whisper": "small", "elevenlabs": "scribe_v1"}


@dataclass(frozen=True)
class TranscriptWord:
    """A word heard and when (seconds from the start of the audio)."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Transcript:
    """What a speech-to-text provider heard in one audio file: the ``text``, its ``words`` with
    times (may be empty: then the text's words are compared without times) and the ``language``
    it heard (``None`` if the provider does not say)."""

    text: str
    words: tuple[TranscriptWord, ...] = ()
    language: str | None = None

    def word_texts(self) -> list[str]:
        """The words heard, in order (the text split at spaces when there are no timed words)."""
        if self.words:
            return [w for word in self.words for w in word.text.split()]
        return self.text.split()

    def word_times(self) -> list[tuple[float, float] | None]:
        """For each of :meth:`word_texts`, its ``(start, end)``, or ``None`` without times."""
        if not self.words:
            return [None] * len(self.text.split())
        return [(word.start, word.end) for word in self.words for _ in word.text.split()]

    def to_json(self) -> dict[str, Any]:
        """``{text, language, words: [[text, start, end], ...]}``."""
        return {
            "text": self.text,
            "language": self.language,
            "words": [[w.text, round(w.start, 3), round(w.end, 3)] for w in self.words],
        }

    @classmethod
    def from_json(cls, doc: dict[str, Any]) -> Transcript:
        """The transcript of :meth:`to_json`; ``ValueError`` / ``KeyError`` / ``TypeError`` if
        it is malformed."""
        words = tuple(TranscriptWord(str(t), float(s), float(e)) for t, s, e in doc["words"])
        language = doc.get("language")
        return cls(str(doc["text"]), words, None if language is None else str(language))


class STTProvider(Protocol):
    """What ``vidgen readback`` needs from a speech-to-text provider. Constructing one never
    loads a model or needs a key."""

    name: str

    def check_available(self) -> None:
        """Raise ``VidgenError`` (saying how to fix it) if the provider cannot run: a missing
        optional package, a missing API key."""

    def transcribe(self, path: Path) -> Transcript:
        """What is said in the audio file ``path``. Raises ``VidgenError``."""


def stt_settings(project: Project) -> dict[str, Any]:
    """What a transcript of the project's audio depends on: ``{provider, model, language}``
    from ``stt:`` with the defaults resolved (``language``: ``stt.language``, else the video's
    language subtag, ``en`` without one; ``None`` for ``auto``: the provider detects it;
    ``model``: ``stt.model``, else the provider's default — faster-whisper ``small.en`` for
    English, ``small`` otherwise; ElevenLabs ``scribe_v1``)."""
    stt = project.config.stt
    if stt.language == "auto":
        language = None
    else:
        language = primary_language(stt.language if stt.language is not None else project.config.language)
    model = stt.model
    if model is None:
        model = DEFAULT_MODELS[stt.provider]
        if stt.provider == "faster_whisper" and language == "en":
            model += ".en"
    return {"provider": stt.provider, "model": model, "language": language}


def get_stt_provider(project: Project) -> STTProvider:
    """The provider of the project's ``stt:`` section (with :func:`stt_settings`)."""
    settings = stt_settings(project)
    config: SttConfig = project.config.stt
    if settings["provider"] == "faster_whisper":
        from vidgen.stt.faster_whisper import FasterWhisperProvider

        return FasterWhisperProvider(settings["model"], settings["language"], device=config.device)
    if settings["provider"] == "elevenlabs":
        from vidgen.stt.elevenlabs import ElevenLabsSTTProvider

        return ElevenLabsSTTProvider(settings["model"], settings["language"])
    raise VidgenError(f"unknown stt provider {settings['provider']!r}; available: {', '.join(STT_PROVIDERS)}")


__all__ = [
    "DEFAULT_MODELS",
    "STTProvider",
    "STT_PROVIDERS",
    "Transcript",
    "TranscriptWord",
    "get_stt_provider",
    "stt_settings",
]
