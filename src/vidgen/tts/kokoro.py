"""Kokoro-82M text to speech on this computer: free, offline after the first download
(DESIGN.md §68).

``voice: {provider: kokoro, voice: af_heart, speed: 1.0, lang: a, device: cpu}`` voices every
beat with hexgrad's Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M, Apache-2.0) through
its ``kokoro`` package (the optional extra ``schu-video-generator[kokoro]``: PyTorch, misaki's
grapheme-to-phoneme, a bundled espeak-ng). Nothing here imports ``kokoro`` or PyTorch until a
beat is voiced, so ``vidgen validate`` / ``render`` and the other commands work without them.

The model (``kokoro-v1_0.pth``, 327 MB) and each voice (~0.5 MB) are downloaded from the Hugging
Face Hub on first use into its cache (``~/.cache/huggingface/hub``; ``HF_HOME`` /
``HF_HUB_CACHE`` move it). They are loaded once per ``vidgen tts`` run (:class:`KokoroEngine`,
one pipeline per language sharing one model) and run on the CPU unless ``voice.device`` says
otherwise. Kokoro returns 24 kHz float samples; they are encoded to MP3 with ffmpeg. For English
(``lang`` a / b) the pipeline also says when each word is spoken: stored as the beat's
character alignment (as ElevenLabs' timings) for exact karaoke captions.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import sys
import warnings
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from vidgen import DIST_NAME, kokoro_voices
from vidgen.config import VoiceConfig
from vidgen.errors import VidgenError

#: The model repository and weights file (v1.0, SHA256 496dba11...); both are in each beat's hash.
REPO_ID = "hexgrad/Kokoro-82M"
WEIGHTS = "kokoro-v1_0.pth"
#: Sample rate of Kokoro's audio (mono float samples).
SAMPLE_RATE = 24000
INSTALL_COMMAND = f'pip install "{DIST_NAME}[kokoro]"'
#: The newest Python the kokoro package (0.9.4) declares support for.
NEWEST_PYTHON = (3, 12)
#: Installs kokoro on a newer Python anyway (worked on 3.13 on 2026-10-09; the spaCy pins stop
#: pip from backtracking to a spaCy 4 pre-release that does not build).
FORCED_INSTALL = (
    'pip install --ignore-requires-python "kokoro>=0.9.4" "misaki[en]>=0.9.4" "spacy>=3.8,<4" '
    '"spacy-curated-transformers<0.4"'
)
#: Languages read through espeak-ng (English uses it only for words missing from its dictionary).
ESPEAK_LANGS = frozenset({"e", "f", "h", "i", "p"})
#: Languages needing one more misaki extra: lang -> (a module of it, the install command).
LANG_EXTRAS: dict[str, tuple[str, str]] = {"j": ("pyopenjtalk", 'pip install "misaki[ja]"'), "z": ("jieba", 'pip install "misaki[zh]"')}
#: Share of a beat's words the word timings must cover to be stored (else: estimated).
MIN_TIMED_SHARE = 0.8
#: Words in an exception that mean the model or a voice could not be downloaded (seen: httpx
#: ``ProxyError: 403``, Xet ``CAS Client Error``, ``LocalEntryNotFoundError`` offline).
DOWNLOAD_WORDS: tuple[str, ...] = (
    "huggingface", "hf_hub", "hf.co", "xet", "cas client", "connection", "proxy", "resolve", "offline", "localentrynotfound",
    "timed out", "name or service",
)


# ----- installation and the model download --------------------------------------------------------


def module_available(name: str) -> bool:
    """True if ``name`` can be imported (not imported here)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def install_message() -> str:
    """How to install the extra (and what to do on a Python the kokoro package does not support)."""
    text = (
        f"voice.provider kokoro needs the optional extra: {INSTALL_COMMAND} "
        "(PyTorch and Kokoro's packages; the model itself is downloaded on the first run)"
    )
    if sys.version_info[:2] > NEWEST_PYTHON:
        text += (
            f". The kokoro package (0.9.4) supports Python 3.10-3.12 and this is Python {sys.version_info[0]}.{sys.version_info[1]}, "
            f"so the extra installs nothing here: use a Python 3.12 virtual environment, or install it anyway: {FORCED_INSTALL}"
        )
    return text


def hf_cache_dir() -> Path:
    """Where the Hugging Face Hub keeps downloads: ``HF_HUB_CACHE``, else ``HF_HOME/hub``, else
    ``~/.cache/huggingface/hub`` (also on Windows: ``%USERPROFILE%\\.cache\\huggingface\\hub``)."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    base = Path(os.environ["XDG_CACHE_HOME"]) if os.environ.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return base / "huggingface" / "hub"


def model_downloaded() -> bool:
    """True if the weights are in the Hugging Face cache already."""
    snapshots = hf_cache_dir() / f"models--{REPO_ID.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.glob(f"*/{WEIGHTS}"))


def download_note() -> str:
    """What the first run downloads, and where."""
    size = round(kokoro_voices.catalog()["weights_bytes"] / 1e6)
    return (
        f"the first run downloads Kokoro-82M from Hugging Face ({WEIGHTS}, {size} MB, and ~0.5 MB per voice) into "
        f"{hf_cache_dir()} (HF_HOME moves it); English voices also install spaCy's en_core_web_sm (~13 MB) with pip"
    )


def run_notes(voices: Iterable[VoiceConfig]) -> list[str]:
    """Notes for a dry run / a run with Kokoro beats: free and local, the download still to come,
    the extra or a language package not installed."""
    voices = list(voices)
    devices = sorted({v.device for v in voices})
    notes = [f"Kokoro-82M runs on this computer ({', '.join(devices)}): free, no API key"]
    if not model_downloaded():
        notes.append(download_note())
    if not module_available("kokoro"):
        notes.append(f"not installed yet: {install_message()}")
    for lang in sorted({str(v.lang) for v in voices}):
        if lang in LANG_EXTRAS and not module_available(LANG_EXTRAS[lang][0]):
            notes.append(f"lang {lang} ({kokoro_voices.lang_name(lang)}) also needs: {LANG_EXTRAS[lang][1]}")
    return notes


def check_installed(lang: str | None) -> None:
    """Raise :class:`VidgenError` naming what to install when the extra, a language's misaki
    extra or espeak-ng (bundled by ``espeakng-loader``) is missing."""
    if not module_available("kokoro"):
        raise VidgenError(install_message())
    if lang in LANG_EXTRAS and not module_available(LANG_EXTRAS[lang][0]):
        raise VidgenError(f"Kokoro's lang {lang} ({kokoro_voices.lang_name(lang)}) needs more packages: {LANG_EXTRAS[lang][1]}")
    if lang in ESPEAK_LANGS and not module_available("espeakng_loader"):
        raise VidgenError(espeak_message(lang, "the espeakng-loader package is not installed"))


def espeak_message(lang: str | None, detail: str) -> str:
    """What to do when espeak-ng cannot be loaded."""
    use = f"lang {lang} ({kokoro_voices.lang_name(lang)})" if lang in ESPEAK_LANGS else "English words missing from its dictionary"
    return (
        f"espeak-ng could not be loaded ({detail}); Kokoro reads {use} with it. It normally comes with the "
        "espeakng-loader package that the kokoro extra installs: pip install --force-reinstall espeakng-loader. "
        "Or install espeak-ng itself: Linux `sudo apt install espeak-ng`; Windows the espeak-ng .msi from "
        "https://github.com/espeak-ng/espeak-ng/releases"
    )


def explain(exc: BaseException, lang: str | None, device: str) -> str:
    """A :class:`VidgenError` message for an exception of the kokoro package."""
    detail = f"{type(exc).__name__}: {exc}".strip()
    text = detail.lower()
    if isinstance(exc, ImportError):
        missing = getattr(exc, "name", None) or ""
        if lang in LANG_EXTRAS:
            return f"Kokoro's lang {lang} ({kokoro_voices.lang_name(lang)}) needs more packages: {LANG_EXTRAS[lang][1]} ({detail})"
        if "espeak" in missing or "phonemizer" in missing:
            return espeak_message(lang, detail)
        return f"{install_message()} ({detail})"
    if "espeak" in text:
        return espeak_message(lang, detail)
    if "cuda" in text and device != "cpu":
        return f"voice.device {device}: PyTorch cannot use a CUDA GPU here ({detail}); set voice.device: cpu"
    if any(word in text for word in DOWNLOAD_WORDS):
        hint = " (if only the Xet storage is blocked, HF_HUB_DISABLE_XET=1 downloads over plain HTTPS)" if "xet" in text or "cas " in text else ""
        return (
            f"cannot download Kokoro-82M from Hugging Face ({detail[:300]}){hint}; the first run needs the internet "
            f"(huggingface.co and its file CDN), later runs use {hf_cache_dir()}"
        )
    return f"Kokoro could not voice the text: {detail}"


# ----- the model, loaded once per run -------------------------------------------------------------


@contextlib.contextmanager
def quiet_stdout() -> Iterator[None]:
    """Send whatever is written to standard output (also by child processes: misaki installs
    spaCy's English model with pip on first use) to standard error meanwhile, so ``vidgen tts
    --json`` keeps a clean JSON document on stdout; PyTorch's load-time warnings are hidden."""
    sys.stdout.flush()
    try:
        saved = os.dup(1)
    except OSError:  # no real stdout (embedded): nothing to protect
        saved = None
    try:
        if saved is not None:
            os.dup2(2, 1)
        with contextlib.redirect_stdout(sys.stderr), warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            warnings.simplefilter("ignore", FutureWarning)
            yield
    finally:
        sys.stderr.flush()
        if saved is not None:
            os.dup2(saved, 1)
            os.close(saved)


def load_pipeline(lang: str, device: str, model: Any = None) -> Any:
    """A ``kokoro.KPipeline`` for ``lang`` on ``device`` (``auto``: a GPU if PyTorch sees one),
    reusing ``model`` (a ``KModel``) when given; the model is downloaded on first use."""
    import kokoro

    return kokoro.KPipeline(
        lang_code=lang, repo_id=REPO_ID, model=True if model is None else model, device=None if device == "auto" else device
    )


class KokoroEngine:
    """Kokoro's model and one pipeline per language on one device, created on first use; every
    voice of a run shares it (:func:`shared_engine`). ``factory(lang, device, model)`` makes a
    pipeline (default :func:`load_pipeline`; tests pass a fake)."""

    def __init__(self, device: str, factory: Callable[[str, str, Any], Any] | None = None) -> None:
        self.device = device
        self._factory = factory
        self._pipelines: dict[str, Any] = {}
        self._model: Any = None

    def pipeline(self, lang: str) -> Any:
        """The pipeline of ``lang`` (loads the model on the first call)."""
        if lang not in self._pipelines:
            factory = self._factory or load_pipeline
            made = factory(lang, self.device, self._model)
            self._model = self._model if self._model is not None else getattr(made, "model", None)
            self._pipelines[lang] = made
        return self._pipelines[lang]

    @property
    def loaded(self) -> list[str]:
        """The languages with a pipeline so far."""
        return list(self._pipelines)


_ENGINES: dict[str, KokoroEngine] = {}


def shared_engine(device: str) -> KokoroEngine:
    """The engine of ``device`` for this process (one model per run)."""
    if device not in _ENGINES:
        _ENGINES[device] = KokoroEngine(device)
    return _ENGINES[device]


# ----- audio and timings --------------------------------------------------------------------------


def pcm16(audio: Any) -> bytes:
    """Float samples (a PyTorch tensor or an array, -1..1) as 16-bit little-endian PCM."""
    import numpy as np

    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    samples = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
    return (samples * 32767.0).round().astype("<i2").tobytes()


def pcm_to_mp3(pcm: bytes, ffmpeg: str | None = None) -> bytes:
    """24 kHz mono 16-bit PCM as MP3 (ffmpeg, 128 kb/s)."""
    from vidgen.tts.openrouter import convert_to_mp3

    return convert_to_mp3(pcm, ["-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1"], ffmpeg, source="Kokoro's audio")


def alignment_from_tokens(text: str, timed: Sequence[tuple[str, float, float]]) -> dict[str, list[Any]] | None:
    """A character alignment of ``text`` (``{characters, character_start_times_seconds,
    character_end_times_seconds}``, as ElevenLabs gives it) from Kokoro's timed tokens
    ``(token text, start, end)`` in order: each token found in the text spreads its time over its
    characters; characters between tokens (spaces, a token not found) take the previous end.
    ``None`` when fewer than :data:`MIN_TIMED_SHARE` of the words get a time."""
    starts: list[float | None] = [None] * len(text)
    ends: list[float | None] = [None] * len(text)
    cursor = 0
    for word, start, end in timed:
        word = word.strip()
        at = text.find(word, cursor) if word else -1
        if at < 0:
            continue
        end = max(end, start)
        for k in range(len(word)):
            starts[at + k] = start + (end - start) * k / len(word)
            ends[at + k] = start + (end - start) * (k + 1) / len(word)
        cursor = at + len(word)
    words = [m.span() for m in re.finditer(r"\S+", text)]
    covered = sum(1 for a, b in words if any(starts[k] is not None for k in range(a, b)))
    if not words or covered < MIN_TIMED_SHARE * len(words):
        return None
    out_starts: list[float] = []
    out_ends: list[float] = []
    last = 0.0
    for s, e in zip(starts, ends):
        if s is None or e is None:
            s = e = last
        last = max(last, e)
        out_starts.append(round(s, 4))
        out_ends.append(round(e, 4))
    return {
        "characters": list(text),
        "character_start_times_seconds": out_starts,
        "character_end_times_seconds": out_ends,
    }


# ----- the provider -------------------------------------------------------------------------------


class KokoroProvider:
    """Synthesise speech with one Kokoro voice (voice name or blend, language, speed) on this
    computer. Constructing it loads nothing; the first beat loads the shared engine of
    ``voice.device`` (``engine`` replaces it, ``ffmpeg`` the ffmpeg used for MP3: tests).
    Neighbouring beats are not used (each beat is voiced on its own)."""

    name = "kokoro"
    #: ``vidgen tts`` asks for the timings with every beat: they cost nothing (English only).
    timings_included = True

    def __init__(self, voice: VoiceConfig, *, engine: KokoroEngine | None = None, ffmpeg: str | None = None) -> None:
        if voice.provider != "kokoro":
            raise VidgenError("the Kokoro provider needs voice.provider: kokoro")
        name, lang = kokoro_voices.resolve(voice.voice, voice.lang, None)
        self.voice = voice
        self.voice_name = str(name)
        self.lang = str(lang)
        self.speed = 1.0 if voice.speed is None else float(voice.speed)
        self._engine = engine
        self._ffmpeg = ffmpeg

    # ----- cache keys ------------------------------------------------------------------------

    def spec(self) -> dict[str, Any]:
        """What the audio depends on besides the text: provider, model and weights, voice, lang,
        speed (not the device)."""
        return {"provider": self.name, "model": REPO_ID, "weights": WEIGHTS, "voice": self.voice_name, "lang": self.lang, "speed": self.speed}

    def cache_key(self, text: str) -> str:
        """sha1 of ``json(spec, sorted keys) | text`` (DESIGN.md §68)."""
        head = json.dumps(self.spec(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(f"{head}|{text}".encode("utf-8")).hexdigest()

    def matches(self, text: str, stored: str) -> bool:
        """True if a stored hash says the audio for ``text`` is up to date."""
        return stored.strip() == self.cache_key(text)

    # ----- synthesis -------------------------------------------------------------------------

    def check_credentials(self) -> None:
        """No key: raise :class:`VidgenError` naming what to install when the extra (or this
        language's packages) is missing."""
        if self._engine is None:
            check_installed(self.lang)

    def engine(self) -> KokoroEngine:
        """The engine this provider voices with."""
        return self._engine if self._engine is not None else shared_engine(self.voice.device)

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        """MP3 bytes for ``text``. Raises :class:`VidgenError` on any failure."""
        return self.synthesize_timed(text, previous_text, next_text)[0]

    def synthesize_timed(
        self, text: str, previous_text: str | None = None, next_text: str | None = None
    ) -> tuple[bytes, dict[str, list[Any]] | None]:
        """MP3 bytes for ``text`` and, for English, when each character is spoken (``None`` for
        other languages or when the timings cover too little of the text)."""
        engine = self.engine()
        chunks: list[bytes] = []
        timed: list[tuple[str, float, float]] = []
        offset = 0.0
        try:
            with quiet_stdout():
                pipeline = engine.pipeline(self.lang)
                results = list(pipeline(text, voice=self.voice_name, speed=self.speed, split_pattern=None))
            for result in results:
                audio = getattr(result, "audio", None)
                if audio is None:
                    continue
                pcm = pcm16(audio)
                for token in getattr(result, "tokens", None) or ():
                    start, end = getattr(token, "start_ts", None), getattr(token, "end_ts", None)
                    if start is not None and end is not None:
                        timed.append((str(token.text), offset + float(start), offset + float(end)))
                offset += len(pcm) / 2 / SAMPLE_RATE
                chunks.append(pcm)
        except VidgenError:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure of the library, the download or PyTorch
            raise VidgenError(explain(exc, self.lang, engine.device)) from None
        if not chunks:
            raise VidgenError("Kokoro produced no audio for this text (nothing it could pronounce)")
        mp3 = pcm_to_mp3(b"".join(chunks), self._ffmpeg)
        alignment = alignment_from_tokens(text, timed) if self.lang in kokoro_voices.TIMED_LANGS else None
        return mp3, alignment


# ----- vidgen validate ----------------------------------------------------------------------------


def voice_warnings(voice: VoiceConfig, where: str, language: str | None) -> list[str]:
    """What ``vidgen validate`` says about a resolved Kokoro voice (no network, nothing loaded)."""
    if voice.provider != "kokoro":
        return []
    return kokoro_voices.voice_warnings(voice.voice, voice.lang, language, voice.timestamps, where)


def install_warnings(voices: Iterable[VoiceConfig]) -> list[str]:
    """``vidgen validate``'s warnings when Kokoro beats cannot be voiced here yet (the extra or a
    language's packages missing; ``vidgen tts`` would refuse)."""
    voices = [v for v in voices if v.provider == "kokoro"]
    if not voices:
        return []
    if not module_available("kokoro"):
        return [f"voice.provider: {install_message()}"]
    out = []
    for lang in sorted({str(v.lang) for v in voices}):
        if lang in LANG_EXTRAS and not module_available(LANG_EXTRAS[lang][0]):
            out.append(f"voice.lang: {lang} ({kokoro_voices.lang_name(lang)}) needs {LANG_EXTRAS[lang][1]}")
    return out
