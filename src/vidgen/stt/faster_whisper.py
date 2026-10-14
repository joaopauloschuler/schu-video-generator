"""The ``faster_whisper`` speech-to-text provider (DESIGN.md §57): OpenAI's Whisper run locally
with CTranslate2, free, no API key. The optional extra ``schu-video-generator[stt]`` installs it.

The model (``stt.model``: a size such as ``small`` / ``small.en``, or a folder holding a
converted model) is loaded on the first :meth:`FasterWhisperProvider.transcribe`; a size is
downloaded from the Hugging Face Hub once and cached there.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from vidgen import DIST_NAME
from vidgen.errors import VidgenError
from vidgen.stt import Transcript, TranscriptWord

INSTALL_HINT = f'the faster_whisper speech-to-text provider needs the optional extra: pip install "{DIST_NAME}[stt]"'

#: The sample rate Whisper models take.
SAMPLE_RATE = 16000


def load_audio(path: Path) -> np.ndarray:
    """``path`` decoded by the ffmpeg executable to the 1-D float32 16 kHz mono samples Whisper
    takes.

    Decoding here instead of handing faster-whisper the path keeps readback working with every
    PyAV version (faster-whisper's own decoder passes an argument PyAV 19 removed)."""
    from vidgen.render.ffmpeg import decode_mono

    return decode_mono(path, SAMPLE_RATE)


def _probability(word: Any) -> float | None:
    probability = getattr(word, "probability", None)
    return None if probability is None else float(probability)


def _module() -> Any:
    try:
        import faster_whisper
    except ImportError:
        raise VidgenError(INSTALL_HINT) from None
    return faster_whisper


class FasterWhisperProvider:
    """Transcribe with a Whisper ``model`` in ``language`` (ISO 639-1; ``None``: detected) on
    ``device`` (``auto``, ``cpu``, ``cuda``)."""

    name = "faster_whisper"

    def __init__(self, model: str, language: str | None, device: str = "auto") -> None:
        self.model = model
        self.language = language
        self.device = device
        self._whisper: Any = None

    def check_available(self) -> None:
        """Raise :class:`VidgenError` with the install command if faster-whisper is missing."""
        _module()

    def _load(self) -> Any:
        if self._whisper is None:
            module = _module()
            # its per-clip INFO lines would show between vidgen's progress lines wherever Manim
            # has set up logging (vidgen lint --readback)
            logging.getLogger("faster_whisper").setLevel(logging.WARNING)
            try:
                self._whisper = module.WhisperModel(self.model, device=self.device)
            except Exception as exc:  # noqa: BLE001 - download / file / runtime errors of the library
                raise VidgenError(
                    f"cannot load the Whisper model {self.model!r}: {type(exc).__name__}: {exc} "
                    "(a model size is downloaded from the Hugging Face Hub on first use; stt.model may "
                    "also name a folder holding a converted model)"
                ) from None
        return self._whisper

    def transcribe(self, path: Path) -> Transcript:
        """What is said in ``path``: word timestamps (and probabilities) on, no conditioning on earlier text (each
        beat is heard on its own, so a mistake cannot carry over), beam search of 5."""
        model = self._load()
        audio = load_audio(path)
        try:
            segments, info = model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                word_timestamps=True,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            segments = list(segments)  # the generator runs the model
        except Exception as exc:  # noqa: BLE001
            raise VidgenError(f"faster-whisper could not transcribe {path.name}: {type(exc).__name__}: {exc}") from None
        words = tuple(
            TranscriptWord(word.word.strip(), float(word.start), float(word.end), _probability(word))
            for segment in segments
            for word in (segment.words or ())
            if word.word.strip()
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return Transcript(text, words, getattr(info, "language", None))
