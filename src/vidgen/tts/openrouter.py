"""OpenRouter text-to-speech provider (``POST /api/v1/audio/speech``), standard library only
(DESIGN.md §66).

``voice: {provider: openrouter, model, voice, instructions, speed}`` voices every beat with one
of OpenRouter's TTS models through one key (``OPENROUTER_API_KEY``, read from the environment
when a request is made; never stored, logged, written or put in an error message: it is only
sent as the ``Authorization: Bearer`` header to openrouter.ai).

The endpoint answers with raw audio (``response_format`` ``mp3``, or ``pcm``: 16-bit mono, 24 kHz,
which some models such as Gemini TTS return only); anything that is not MP3 is converted with
ffmpeg so the ``audio/`` cache always holds MP3s. No neighbouring-beat context, no character
timings and no ``language_code`` exist on this API: the language follows the text, and
``instructions`` can name a language or accent.

Free lookups (no key): ``GET /api/v1/models?output_modalities=speech`` (every TTS model with its
voices and list price) and ``GET /api/v1/models/{author}/{slug}/endpoints`` (each provider's
price). Most models are priced per input character (``pricing.prompt``, completion 0); models
that also bill generated audio (``pricing.completion``: per second or per audio token) have no
estimate. A real run reads what each request cost from ``GET /api/v1/generation?id=`` (with
the key; the id comes in the ``X-Generation-Id`` header); OpenRouter writes those records
asynchronously, so a record not there yet is asked for again for up to 15 s.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from vidgen import httpapi
from vidgen.config import VoiceConfig
from vidgen.errors import VidgenError
from vidgen.imagegen import PriceQuote
from vidgen.imagegen.openrouter import (
    API_BASE,
    API_KEY_ENV,
    APP_HEADERS,
    LOOKUP_TIMEOUT,
    SERVICE,
    TRANSIENT_STATUS,
    ZDR_URL,
    LookupFailure,
    is_policy_error,
    policy_intro,
    read_api_key,
)

API_URL = f"{API_BASE}/audio/speech"
#: Every text-to-speech model with ``supported_voices`` and list ``pricing`` (public).
MODELS_URL = f"{API_BASE}/models?output_modalities=speech"
#: What one request cost (``data.total_cost``; needs the key).
GENERATION_URL = f"{API_BASE}/generation"
#: Seconds to wait before asking ``/generation`` again for records not written yet (OpenRouter
#: writes them asynchronously after the response): at most 15 s after a paid run.
COST_WAITS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0)
#: Where people see each request's cost when the lookup gives none.
ACTIVITY_PAGE = "https://openrouter.ai/activity"
#: Where people browse the TTS models.
MODELS_PAGE = "https://openrouter.ai/models?output_modalities=speech"
#: Model id prefixes that return only raw PCM (Gemini TTS answers 400 to ``mp3``).
PCM_ONLY_PREFIXES: tuple[str, ...] = ("google/",)
#: Sample rate of OpenRouter's ``pcm`` output (16-bit little-endian mono) unless the
#: ``Content-Type`` names another one.
PCM_RATE = 24000
#: Model id prefixes OpenRouter documents as using ``instructions`` / ``speed`` (others ignore
#: them, or refuse a speed other than 1).
INSTRUCTION_PREFIXES: tuple[str, ...] = ("openai/", "google/")
SPEED_PREFIXES: tuple[str, ...] = ("openai/",)
#: Bit rate of the MP3s converted from PCM / WAV (ElevenLabs' default is 128 kb/s too).
MP3_BITRATE = "128k"


# ----- the bundled snapshot (offline checks in `vidgen validate`) ---------------------------------


@lru_cache(maxsize=1)
def snapshot() -> dict[str, Any]:
    """OpenRouter's TTS model list as of the snapshot's ``date``: ``{date, models: {id: {voices,
    zdr, prompt, completion}}}`` (``vidgen validate`` checks model and voice names against it
    without the network; the dry run and a real run use the live list)."""
    text = resources.files("vidgen").joinpath("data/openrouter/tts_models.json").read_text(encoding="utf-8")
    return json.loads(text)


def known_voices(model: str) -> list[str] | None:
    """The voices the snapshot lists for ``model`` (``None``: unknown model or no list)."""
    entry = snapshot()["models"].get(model)
    voices = entry.get("voices") if isinstance(entry, dict) else None
    return list(voices) if isinstance(voices, list) else None


def voices_hint(voices: list[str], limit: int = 8) -> str:
    """``a, b, c ... (N in all)``."""
    shown = ", ".join(voices[:limit])
    return shown + (f" ... ({len(voices)} in all)" if len(voices) > limit else "")


def model_warnings(voice: VoiceConfig, where: str) -> list[str]:
    """What ``vidgen validate`` says about an OpenRouter voice without the network: a model not
    in the snapshot, a voice the model does not list, no voice for a model that lists some,
    and ``timestamps`` (this provider returns no timings)."""
    if voice.provider != "openrouter" or voice.model is None:
        return []
    out: list[str] = []
    date = snapshot()["date"]
    models = snapshot()["models"]
    if voice.model not in models:
        close = difflib.get_close_matches(voice.model, list(models), n=1, cutoff=0.6)
        hint = f"; did you mean {close[0]}?" if close else ""
        out.append(
            f"{where}.model: {voice.model} is not in OpenRouter's text-to-speech list of {date}{hint} "
            f"(`vidgen tts --dry-run` checks the current list; see {MODELS_PAGE})"
        )
    else:
        voices = known_voices(voice.model)
        if voices and voice.voice is None:
            out.append(f"{where}.voice: {voice.model} has voices ({voices_hint(voices)}); without one the request may be refused")
        elif voices and voice.voice not in voices:
            out.append(f"{where}.voice: '{voice.voice}' is not among the voices OpenRouter listed for {voice.model} on {date} ({voices_hint(voices)})")
    if voice.timestamps:
        out.append(f"{where}.timestamps: OpenRouter returns no word timings; captions use estimated timings")
    return out


# ----- live lookups (dry run, before a paid run) --------------------------------------------------


@dataclass(frozen=True)
class SpeechModel:
    """A TTS model as OpenRouter lists it now: its voices (``None``: no list) and the price lines
    of each provider serving it (``{prompt, completion}``: US dollars per input character and
    per generated unit)."""

    model: str
    voices: tuple[str, ...] | None
    prices: tuple[dict[str, Any], ...]


SpeechLookup = SpeechModel | LookupFailure


def _get_json(url: str, timeout: float) -> Any:
    headers = {"Accept": "application/json", **APP_HEADERS}
    return json.loads(httpapi.get(url, headers=headers, service=SERVICE, timeout=timeout).decode("utf-8"))


def endpoints_url(model: str) -> str:
    """``.../models/{author}/{slug}/endpoints`` of ``model``."""
    author, _, slug = model.strip("/").partition("/")
    quote = urllib.parse.quote
    return f"{API_BASE}/models/{quote(author, safe='')}/{quote(slug, safe=':')}/endpoints"


def fetch_speech_models(*, timeout: float = LOOKUP_TIMEOUT) -> dict[str, dict[str, Any]] | LookupFailure:
    """Model id -> record of every TTS model OpenRouter lists now (public, no key), or why not."""
    try:
        doc = _get_json(MODELS_URL, timeout)
        return {str(m["id"]): m for m in doc["data"] if isinstance(m, dict) and "id" in m}
    except urllib.error.HTTPError as exc:
        return LookupFailure(f"OpenRouter's model list answered HTTP {exc.code}")
    except VidgenError as exc:
        return LookupFailure(f"OpenRouter's model list could not be reached ({exc})")
    except (ValueError, KeyError, TypeError):
        return LookupFailure("OpenRouter's model list sent an unreadable answer")


def fetch_endpoint_prices(model: str, *, timeout: float = LOOKUP_TIMEOUT) -> list[dict[str, Any]] | None:
    """The ``pricing`` of each provider of ``model`` (public), ``None`` when not available."""
    try:
        doc = _get_json(endpoints_url(model), timeout)
        prices = [e["pricing"] for e in doc["data"]["endpoints"] if isinstance(e, dict) and isinstance(e.get("pricing"), dict)]
    except (urllib.error.HTTPError, VidgenError, ValueError, KeyError, TypeError):
        return None
    return prices or None


def lookup_speech_models(
    models: Iterable[str],
    *,
    timeout: float = LOOKUP_TIMEOUT,
    fetch_list: Callable[..., dict[str, dict[str, Any]] | LookupFailure] | None = None,
    fetch_prices: Callable[..., list[dict[str, Any]] | None] | None = None,
) -> dict[str, SpeechLookup]:
    """The live record of each model: voices and every provider's price (the list price when
    the per-provider records cannot be read), or why there is none (``missing``: OpenRouter has
    no such TTS model; else offline)."""
    listed = (fetch_list or fetch_speech_models)(timeout=timeout)
    out: dict[str, SpeechLookup] = {}
    for model in dict.fromkeys(models):
        if isinstance(listed, LookupFailure):
            out[model] = listed
            continue
        record = listed.get(model)
        if record is None:
            out[model] = LookupFailure(f"OpenRouter has no text-to-speech model {model!r} (see {MODELS_PAGE})", missing=True)
            continue
        voices = record.get("supported_voices")
        prices = (fetch_prices or fetch_endpoint_prices)(model, timeout=timeout)
        if prices is None:
            prices = [record["pricing"]] if isinstance(record.get("pricing"), dict) else []
        out[model] = SpeechModel(model, tuple(str(v) for v in voices) if isinstance(voices, list) else None, tuple(prices))
    return out


def _price(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money(value: float) -> str:
    """``$0.000016``, ``$0.0123``, ``$1.25``."""
    text = f"{value:.8f}" if value < 0.01 else f"{value:.4f}" if value < 1 else f"{value:.2f}"
    return "$" + (text.rstrip("0").rstrip(".") or "0")


def character_rate(lookup: SpeechLookup) -> PriceQuote:
    """US dollars per input character of the model (the highest of its providers: OpenRouter may
    route to any) and the basis, or ``None`` with the reason (generated audio billed, offline,
    unknown model)."""
    if isinstance(lookup, LookupFailure):
        return PriceQuote(None, f"price unknown: {lookup.reason}")
    rates: list[float] = []
    for line in lookup.prices:
        prompt, completion = _price(line.get("prompt")), _price(line.get("completion"))
        if completion:
            return PriceQuote(
                None,
                f"price unknown: {lookup.model} also bills the generated audio (${completion:g} per second or audio token), "
                "which is not known before it is made",
            )
        if prompt is not None:
            rates.append(prompt)
    if not rates:
        return PriceQuote(None, f"price unknown: OpenRouter lists no price for {lookup.model}")
    rate = max(rates)
    basis = "free (listed at $0)" if rate == 0 else f"{money(rate)} per character"
    if len(set(rates)) > 1:
        basis += f"; the highest of {len(rates)} providers"
    return PriceQuote(rate, f"OpenRouter: {basis}")


def voice_notes(voice: VoiceConfig, lookup: SpeechLookup) -> list[str]:
    """Notes on ``voice`` (none refuses a run: lists may be incomplete): a voice the live list
    does not have for the model, no voice for a model that lists some, ``instructions`` /
    ``speed`` on a model OpenRouter documents as ignoring them."""
    notes: list[str] = []
    model = str(voice.model)
    if isinstance(lookup, SpeechModel) and lookup.voices:
        voices = list(lookup.voices)
        if voice.voice is None:
            notes.append(f"{model} lists voices ({voices_hint(voices)}) but voice: is not set; the request may be refused")
        elif voice.voice not in voices:
            notes.append(f"voice '{voice.voice}' is not among the voices OpenRouter lists for {model} ({voices_hint(voices)})")
    if voice.instructions is not None and not model.startswith(INSTRUCTION_PREFIXES):
        notes.append(f"{model} may ignore instructions (OpenRouter documents them for OpenAI and Gemini TTS models)")
    if voice.speed is not None and not model.startswith(SPEED_PREFIXES):
        notes.append(f"{model} may ignore speed or refuse a value other than 1 (OpenRouter documents it for OpenAI TTS)")
    return notes


# ----- the data-policy error ----------------------------------------------------------------------


def zdr_tts_models(*, timeout: float = LOOKUP_TIMEOUT) -> list[str] | None:
    """TTS models with a Zero Data Retention endpoint (sorted): the public ZDR endpoint list
    intersected with the TTS model list; ``None`` when OpenRouter cannot be reached."""
    try:
        zdr = _get_json(ZDR_URL, timeout)
        with_zdr = {str(e.get("model_id")) for e in zdr["data"] if isinstance(e, dict)}
    except (VidgenError, urllib.error.HTTPError, ValueError, KeyError, TypeError):
        return None
    listed = fetch_speech_models(timeout=timeout)
    if isinstance(listed, LookupFailure):
        return None
    return sorted(m for m in listed if m in with_zdr)


def policy_message(model: str, zdr: Callable[..., list[str] | None] | None = None) -> str:
    """What to do when the account's data policy (e.g. Zero Data Retention) excludes every
    provider of ``model``: the settings page and the TTS models that have a ZDR endpoint now."""
    found = (zdr or zdr_tts_models)()
    lines = [policy_intro(model)]
    if found is None:
        lines.append("(OpenRouter's list of ZDR endpoints could not be reached to suggest models.)")
    elif found:
        lines.append(f"Text-to-speech models with a ZDR endpoint now: {', '.join(found)}")
    else:
        lines.append("No text-to-speech model has a ZDR endpoint now.")
    return "\n".join(lines)


# ----- audio --------------------------------------------------------------------------------------


def audio_kind(data: bytes, content_type: str | None, requested: str) -> str:
    """``mp3``, ``wav``, ``pcm`` or ``unknown`` for a response body (its first bytes, then its
    ``Content-Type``, then the format asked for)."""
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    kind = (content_type or "").lower()
    if data.lstrip()[:1] in (b"{", b"<"):
        return "unknown"
    if "pcm" in kind or "l16" in kind:
        return "pcm"
    if "mpeg" in kind or "mp3" in kind:
        return "mp3"
    return "pcm" if requested == "pcm" and not kind.startswith(("text/", "application/")) else "unknown"


def pcm_rate(content_type: str | None) -> int:
    """The sample rate a ``Content-Type`` names (``audio/pcm;rate=24000``), else :data:`PCM_RATE`."""
    found = re.search(r"rate=(\d+)", content_type or "")
    return int(found.group(1)) if found else PCM_RATE


def convert_to_mp3(data: bytes, input_args: list[str], ffmpeg: str | None = None) -> bytes:
    """``data`` (read with ffmpeg's ``input_args``) encoded as MP3."""
    from vidgen.render.ffmpeg import find_ffmpeg, run_ffmpeg

    exe = ffmpeg or find_ffmpeg()
    with tempfile.TemporaryDirectory(prefix="vidgen-tts-") as folder:
        source, target = Path(folder) / "in.audio", Path(folder) / "out.mp3"
        source.write_bytes(data)
        try:
            run_ffmpeg(exe, [*input_args, "-i", str(source), "-codec:a", "libmp3lame", "-b:a", MP3_BITRATE, str(target)], "converting OpenRouter's audio to MP3")
        except (OSError, subprocess.SubprocessError) as exc:
            raise VidgenError(f"cannot convert OpenRouter's audio to MP3: {exc}") from None
        return target.read_bytes()


def as_mp3(data: bytes, content_type: str | None, requested: str, ffmpeg: str | None = None) -> bytes:
    """The response audio as MP3: MP3 kept as sent, WAV and raw PCM (16-bit mono) converted."""
    kind = audio_kind(data, content_type, requested)
    if kind == "mp3":
        return data
    if kind == "wav":
        return convert_to_mp3(data, [], ffmpeg)
    if kind == "pcm":
        if len(data) < 2:
            raise VidgenError("OpenRouter returned an empty audio stream")
        return convert_to_mp3(data, ["-f", "s16le", "-ar", str(pcm_rate(content_type)), "-ac", "1"], ffmpeg)
    preview = data[:200].decode("utf-8", errors="replace").strip()
    raise VidgenError(f"OpenRouter returned no audio vidgen can read ({content_type or 'no content type'}): {preview}")


def _pcm_only_error(message: str) -> bool:
    text = message.lower()
    return "http 400" in text and "response_format" in text and "pcm" in text


# ----- the provider -------------------------------------------------------------------------------


class OpenRouterTTSProvider:
    """Synthesise speech with one OpenRouter TTS voice configuration (model, voice, instructions,
    speed). Neighbouring beats are not sent (the API has no context fields) and no character
    timings come back.

    ``retries`` transient failures (HTTP 429 / 5xx / 524 / 529, timeouts, dropped connections)
    are retried with exponential backoff (``backoff * 2**attempt`` seconds, or ``Retry-After``,
    capped at ``max_wait``). ``sleep``, ``zdr`` (TTS models with a ZDR endpoint, for the
    data-policy message) and ``ffmpeg`` are injectable for tests. ``generations`` collects the
    ``X-Generation-Id`` of each request (for :meth:`reported_cost`; ``sleep`` also paces its
    waits).
    """

    name = "openrouter"

    def __init__(
        self,
        voice: VoiceConfig,
        *,
        timeout: float = 120.0,
        retries: int = 3,
        backoff: float = 4.0,
        max_wait: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        zdr: Callable[..., list[str] | None] | None = None,
        ffmpeg: str | None = None,
    ) -> None:
        if voice.provider != "openrouter" or voice.model is None:
            raise VidgenError("the OpenRouter TTS provider needs voice.provider: openrouter and a model")
        self.voice = voice
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_wait = max_wait
        self._sleep = sleep if sleep is not None else time.sleep
        self._zdr = zdr
        self._ffmpeg = ffmpeg
        self._pcm = voice.model.startswith(PCM_ONLY_PREFIXES)
        self.generations: list[str] = []
        #: Audio responses received (a response without ``X-Generation-Id`` has no cost record).
        self.requests = 0
        #: Why :meth:`reported_cost` left a request out (``None``: all reported).
        self.cost_problem: str | None = None

    @property
    def model(self) -> str:
        """The OpenRouter model id."""
        return str(self.voice.model)

    # ----- cache keys ------------------------------------------------------------------------

    def spec(self) -> dict[str, Any]:
        """What the audio depends on besides the text: provider, model, voice, instructions, speed."""
        v = self.voice
        return {"provider": self.name, "model": v.model, "voice": v.voice, "instructions": v.instructions, "speed": v.speed}

    def cache_key(self, text: str) -> str:
        """sha1 of ``json(spec, sorted keys) | text`` (DESIGN.md §66)."""
        head = json.dumps(self.spec(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(f"{head}|{text}".encode("utf-8")).hexdigest()

    def matches(self, text: str, stored: str) -> bool:
        """True if a stored hash says the audio for ``text`` is up to date."""
        return stored.strip() == self.cache_key(text)

    # ----- synthesis -------------------------------------------------------------------------

    @property
    def response_format(self) -> str:
        """``mp3``, or ``pcm`` for a model that returns only that."""
        return "pcm" if self._pcm else "mp3"

    def request_body(self, text: str) -> dict[str, Any]:
        """JSON body of ``POST /audio/speech``: model, input, response format, then voice,
        instructions and speed when set."""
        body: dict[str, Any] = {"model": self.model, "input": text, "response_format": self.response_format}
        v = self.voice
        if v.voice is not None:
            body["voice"] = v.voice
        if v.instructions is not None:
            body["instructions"] = v.instructions
        if v.speed is not None:
            body["speed"] = v.speed
        return body

    def check_credentials(self) -> None:
        """Raise :class:`VidgenError` with setup instructions if ``OPENROUTER_API_KEY`` is unset."""
        read_api_key("tts")

    def synthesize(self, text: str, previous_text: str | None = None, next_text: str | None = None) -> bytes:
        """MP3 bytes for ``text`` (neighbours are not sent: the API has no context fields).
        Raises :class:`VidgenError` on any failure."""
        try:
            data, headers = self._send(text)
        except VidgenError as exc:
            if is_policy_error(str(exc)):
                raise VidgenError(policy_message(self.model, self._zdr)) from None
            if self.response_format == "mp3" and _pcm_only_error(str(exc)):
                self._pcm = True  # this model returns raw PCM only: ask for it and convert
                data, headers = self._send(text)
            else:
                raise
        self.requests += 1
        generation = headers.get("x-generation-id")
        if generation:
            self.generations.append(generation.strip())
        return as_mp3(data, headers.get("content-type"), self.response_format, self._ffmpeg)

    def _send(self, text: str) -> tuple[bytes, dict[str, str]]:
        key = read_api_key("tts")
        headers = {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "audio/mpeg, audio/*", **APP_HEADERS,
        }
        got: dict[str, str] = {}
        data = httpapi.post_with_retries(
            API_URL, json.dumps(self.request_body(text)).encode("utf-8"), headers=headers, service=SERVICE, secret=key,
            timeout=self.timeout, retries=self.retries, backoff=self.backoff, max_wait=self.max_wait, sleep=self._sleep,
            transient=lambda status, body: status in TRANSIENT_STATUS, response_headers=got,
        )
        return data, got

    def reported_cost(self, *, timeout: float = 10.0, waits: Sequence[float] = COST_WAITS) -> tuple[float, int]:
        """US dollars OpenRouter reports for this provider's requests (``GET /generation``, with
        the key) and how many of them it reported. OpenRouter writes a generation's record
        asynchronously, a few seconds after the audio came back, so records not there yet (HTTP
        404, a record without ``total_cost``, a transient error) are asked again after each of
        ``waits`` seconds (all requests together: at most ``sum(waits)`` in all); what is still
        missing then is left out and :attr:`cost_problem` says why. Never raises."""
        self.cost_problem = None
        try:
            key = read_api_key("tts")
        except VidgenError:
            self.cost_problem = f"{API_KEY_ENV} is not set or not usable"
            return 0.0, 0
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json", **APP_HEADERS}
        total, found = 0.0, 0
        pending = list(dict.fromkeys(self.generations))
        asked, last = len(pending), ""
        deadline = time.monotonic() + sum(waits) + 2 * timeout   # slow answers do not stretch the wait much
        for wait in (*waits, None):
            if time.monotonic() > deadline:
                break
            retry: list[str] = []
            for n, generation in enumerate(pending):
                if time.monotonic() > deadline:
                    retry.extend(pending[n:])
                    break
                cost, problem, again = self._generation_cost(generation, headers, key, timeout)
                if cost is not None:
                    total, found = total + cost, found + 1
                    continue
                last = problem
                if again:
                    retry.append(generation)
            pending = retry
            if not pending or wait is None:
                break
            self._sleep(wait)
        if pending:
            self.cost_problem = f"{last or 'no answer from GET /generation'} (still missing after waiting {sum(waits):g} s)"
        elif found < asked:
            self.cost_problem = last
        elif self.requests > asked:
            self.cost_problem = f"{self.requests - asked} audio response(s) came without an X-Generation-Id header"
        return total, found

    @staticmethod
    def _generation_cost(generation: str, headers: dict[str, str], key: str, timeout: float) -> tuple[float | None, str, bool]:
        """``(cost, problem, ask again)`` for one ``GET /generation?id=`` request."""
        url = f"{GENERATION_URL}?id={urllib.parse.quote(generation, safe='')}"
        try:
            doc = json.loads(httpapi.get(url, headers=headers, service=SERVICE, timeout=timeout, secret=key).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            again = exc.code == 404 or exc.code in TRANSIENT_STATUS
            try:
                said = httpapi.scrub(exc.read().decode("utf-8", errors="replace"), key).strip()
            except Exception:  # noqa: BLE001 - the body only explains the status
                said = ""
            said = f": {said[:160]}" if said else ""
            return None, f"GET /generation answered HTTP {exc.code} for {generation}{said}", again
        except VidgenError as exc:
            return None, str(exc), True
        except ValueError:
            return None, f"GET /generation sent an unreadable answer for {generation}", False
        data = doc.get("data") if isinstance(doc, dict) else None
        cost = data.get("total_cost") if isinstance(data, dict) else None
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            return float(cost), "", False
        return None, f"the generation record of {generation} has no total_cost yet", True
