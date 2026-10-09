"""OpenRouter image provider (``POST /api/v1/images``), standard library only (DESIGN.md §64).

One key, many image models (``imagegen: {provider: openrouter, model: author/name}``). The API key
is read from the environment variable ``OPENROUTER_API_KEY`` when a request is made; it is never
stored, logged, written to a file or included in an error message: it is only sent as the
``Authorization: Bearer`` header to openrouter.ai.

Free lookups (no key) use the public per-model records ``GET
/api/v1/images/models/{author}/{slug}/endpoints``: each endpoint's supported parameters and
pricing lines (``{billable, unit: image | megapixel | token | request, cost_usd, variant}``).
``vidgen imagegen --dry-run`` prices pictures with them; a real run checks the options against
them before the first paid request.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
import urllib.error
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from vidgen import DIST_NAME, httpapi
from vidgen.errors import VidgenError
from vidgen.imagegen import GeneratedPicture, ImageRequest, PriceQuote
from vidgen.imagegen.openai import as_png

API_BASE = "https://openrouter.ai/api/v1"
API_URL = f"{API_BASE}/images"
API_KEY_ENV = "OPENROUTER_API_KEY"
SERVICE = "OpenRouter"
#: Optional app identification OpenRouter documents (``HTTP-Referer`` = the app's URL,
#: ``X-OpenRouter-Title`` = its name; ``X-Title`` is the older alias). Sent with every request.
APP_URL = "https://github.com/joaopauloschuler/schu-video-generator"
APP_HEADERS: dict[str, str] = {"HTTP-Referer": APP_URL, "X-OpenRouter-Title": DIST_NAME}
#: Seconds a free lookup (price list) may take before the dry run says "price unknown".
LOOKUP_TIMEOUT = 5.0
#: HTTP statuses retried: rate limit, server errors, edge timeout (524), provider overloaded (529).
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504, 524, 529})
#: Media types of vector pictures (not supported yet: the pictures are stored as PNG).
VECTOR_TYPES = frozenset({"image/svg+xml"})


def missing_key_message() -> str:
    """How to set the API key, for the error shown when it is missing."""
    return (
        f"the environment variable {API_KEY_ENV} is not set. Set it to your OpenRouter API key "
        "(https://openrouter.ai/keys):\n"
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
    return status in TRANSIENT_STATUS


# ----- the public model records ------------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    """An image model's endpoints (one per upstream provider) as OpenRouter lists them."""

    model: str
    endpoints: tuple[dict[str, Any], ...]

    def parameters(self) -> dict[str, dict[str, Any]]:
        """Supported parameters over all endpoints (enum values merged): OpenRouter routes a
        request to any endpoint that takes it."""
        merged: dict[str, dict[str, Any]] = {}
        for endpoint in self.endpoints:
            params = endpoint.get("supported_parameters")
            for name, spec in (params.items() if isinstance(params, dict) else ()):
                spec = spec if isinstance(spec, dict) else {}
                have = merged.setdefault(name, dict(spec))
                if "values" in have or "values" in spec:
                    values = list(have.get("values") or [])
                    values += [v for v in spec.get("values") or [] if v not in values]
                    have["values"] = values
        return merged

    def values(self, name: str) -> list[str] | None:
        """The listed values of an enum parameter, ``None`` when it has none (or is absent)."""
        spec = self.parameters().get(name)
        values = spec.get("values") if spec else None
        return [str(v) for v in values] if isinstance(values, list) else None


@dataclass(frozen=True)
class LookupFailure:
    """Why a model's record is not available: ``missing`` (OpenRouter has no such image model)
    or not reachable (offline, timeout: prices unknown, nothing is refused)."""

    reason: str
    missing: bool = False


Lookup = ModelInfo | LookupFailure


def endpoints_url(model: str) -> str:
    """``.../images/models/{author}/{slug}/endpoints`` of ``model`` (``author/slug``)."""
    author, _, slug = model.strip("/").partition("/")
    quote = urllib.parse.quote
    return f"{API_BASE}/images/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"


def fetch_model_info(model: str, *, timeout: float = LOOKUP_TIMEOUT) -> Lookup:
    """The public record of ``model`` (no key needed), or why it is not available."""
    headers = {"Accept": "application/json", **APP_HEADERS}
    try:
        body = httpapi.get(endpoints_url(model), headers=headers, service=SERVICE, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return LookupFailure(f"OpenRouter has no image model {model!r} (see https://openrouter.ai/models?output_modalities=image)", missing=True)
        return LookupFailure(f"OpenRouter's model list answered HTTP {exc.code}")
    except VidgenError as exc:
        return LookupFailure(f"OpenRouter's model list could not be reached ({exc})")
    try:
        doc = json.loads(body.decode("utf-8"))
        endpoints = tuple(e for e in doc["endpoints"] if isinstance(e, dict))
    except (ValueError, KeyError, TypeError):
        return LookupFailure("OpenRouter's model list sent an unreadable answer")
    if not endpoints:
        return LookupFailure(f"no provider on OpenRouter serves {model!r} now", missing=True)
    return ModelInfo(model, endpoints)


def lookup_models(models: Iterable[str], *, timeout: float = LOOKUP_TIMEOUT, fetch: Callable[..., Lookup] | None = None) -> dict[str, Lookup]:
    """:func:`fetch_model_info` of each distinct model; once OpenRouter cannot be reached the
    others are not tried (offline: one short wait, not one per model)."""
    fetch = fetch_model_info if fetch is None else fetch
    out: dict[str, Lookup] = {}
    offline: LookupFailure | None = None
    for model in dict.fromkeys(models):
        if offline is not None:
            out[model] = offline
            continue
        result = fetch(model, timeout=timeout)
        out[model] = result
        if isinstance(result, LookupFailure) and not result.missing:
            offline = result
    return out


# ----- prices ------------------------------------------------------------------------------------


def _money(value: float) -> str:
    text = f"{value:.8f}" if value < 0.01 else f"{value:.3f}"
    return "$" + (text.rstrip("0").rstrip(".") or "0")


def _endpoint_price(endpoint: dict[str, Any], request: ImageRequest) -> tuple[float | None, str]:
    """One endpoint's price of ``request``'s output picture and its basis."""
    lines = [p for p in endpoint.get("pricing") or [] if isinstance(p, dict) and p.get("billable") == "output_image"]
    if not lines:
        return None, "no output-picture price listed"
    tier = (request.resolution or "").lower()
    if any(p.get("variant") for p in lines):
        matching = [p for p in lines if str(p.get("variant") or "").lower() == tier]
        plain = [p for p in lines if not p.get("variant")]
        lines = matching or plain or lines
    known: list[tuple[float, str]] = []
    unknown: list[str] = []
    for line in lines:
        try:
            cost = float(line.get("cost_usd"))
        except (TypeError, ValueError):
            unknown.append("an unreadable price")
            continue
        unit = str(line.get("unit") or "")
        variant = f" ({line['variant']})" if line.get("variant") else ""
        if cost == 0:
            known.append((0.0, f"free (listed at $0 per {unit or 'unit'}){variant}"))
        elif unit in ("image", "request"):
            known.append((cost, f"{_money(cost)} per {unit}{variant}"))
        elif unit == "megapixel":
            w, h = request.pixels
            mp = w * h / 1e6
            size = request.size if request.explicit_size else f"nominal {request.size}"
            known.append((cost * mp, f"{_money(cost)} per megapixel x {mp:.2f} MP ({size}){variant}"))
        else:
            unknown.append(f"{_money(cost)} per output {unit or 'unit'}{variant}")
    if known:
        cost, basis = max(known)
        return cost, basis
    return None, f"{unknown[0]}; the {('tokens' if 'token' in unknown[0] else 'units')} per picture are not listed"


def quote(request: ImageRequest, lookup: Lookup) -> PriceQuote:
    """The price of one picture of ``request`` from its model's record: per image, per
    megapixel (of the requested or nominal size) or unknown (per token, not listed, offline).
    With several endpoints, the highest (OpenRouter may route to any)."""
    if isinstance(lookup, LookupFailure):
        return PriceQuote(None, f"price unknown: {lookup.reason}")
    prices = [_endpoint_price(e, request) for e in lookup.endpoints]
    known = [p for p in prices if p[0] is not None]
    if not known:
        return PriceQuote(None, f"price unknown: OpenRouter lists {prices[0][1]}")
    cost, basis = max(known, key=lambda p: p[0] or 0.0)
    if len({round(p[0] or 0.0, 6) for p in known}) > 1 or len(known) < len(prices):
        basis += f"; the highest of {len(prices)} providers"
    return PriceQuote(cost, f"OpenRouter: {basis}")


# ----- checking and building a request -----------------------------------------------------------


@dataclass
class RequestCheck:
    """What a model makes of ``request``: ``problems`` (a real run refuses before paying) and
    ``notes`` (options it ignores or changes)."""

    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_request(request: ImageRequest, info: ModelInfo) -> RequestCheck:
    """``request``'s options against ``info``'s supported parameters."""
    check = RequestCheck()
    params = info.parameters()
    model = info.model
    for name, value, where in (("quality", request.quality, "imagegen.quality"), ("resolution", request.resolution, "imagegen.resolution")):
        if value is None:
            continue
        values = info.values(name)
        if name not in params:
            check.problems.append(f"{model} has no {name} setting: remove {where} ({value})")
        elif values is not None and value not in values:
            check.problems.append(f"{model} takes {name} {', '.join(values)}, not {value} ({where})")
    formats = info.values("output_format")
    if formats is not None and formats and all(f == "svg" for f in formats):
        check.problems.append(f"{model} makes vector (SVG) pictures, which vidgen cannot store yet: choose a model that makes PNG/JPEG/WebP pictures")
    refs = params.get("input_references")
    if isinstance(refs, dict) and isinstance(refs.get("min"), int) and refs["min"] >= 1:
        check.problems.append(f"{model} edits an input picture (needs {refs['min']}+): choose a text-to-image model")
    if request.aspect_ratio is not None:
        ratios = info.values("aspect_ratio")
        if "aspect_ratio" not in params:
            check.notes.append(f"{model} takes no aspect ratio: its pictures may not be {request.aspect_ratio} (the scene's fit crops or pads them)")
        elif ratios is not None and request.aspect_ratio not in ratios:
            listed = ", ".join(r for r in ratios if r != "auto")
            check.notes.append(f"{model} has no {request.aspect_ratio} ratio ({listed}): the provider picks its nearest")
    if request.seed is not None and "seed" not in params:
        check.notes.append(f"{model} takes no seed: the seed only names another picture (not sent)")
    return check


def request_body(request: ImageRequest, info: ModelInfo | None = None) -> dict[str, Any]:
    """JSON body of ``POST /images``: model, prompt, one picture, then either ``size`` (an
    explicit WIDTHxHEIGHT) or ``aspect_ratio`` (+ ``resolution``), ``quality``, ``seed`` (unless
    the model is known to take none) and ``output_format: png`` when the model lists it."""
    body: dict[str, Any] = {"model": request.model, "prompt": request.text, "n": 1}
    if request.explicit_size:
        body["size"] = request.size
    else:
        if request.aspect_ratio is not None:
            body["aspect_ratio"] = request.aspect_ratio
        if request.resolution is not None:
            body["resolution"] = request.resolution
    if request.quality is not None:
        body["quality"] = request.quality
    params = info.parameters() if info is not None else None
    if request.seed is not None and (params is None or "seed" in params):
        body["seed"] = request.seed
    formats = info.values("output_format") if info is not None else None
    if formats and "png" in formats:
        body["output_format"] = "png"
    return body


# ----- the response ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RawPicture:
    """A response's picture as sent: bytes, media type (may be ``None``), cost, revised prompt."""

    data: bytes
    media_type: str | None
    cost: float | None
    revised_prompt: str | None


def decode_response(body: bytes) -> RawPicture:
    """``{data: [{b64_json, media_type}], usage: {cost}}`` decoded. Raises
    :class:`VidgenError` if it holds no picture."""
    try:
        doc = json.loads(body.decode("utf-8"))
        item = doc["data"][0]
        data = base64.b64decode(item["b64_json"], validate=True)
    except (ValueError, KeyError, IndexError, TypeError, binascii.Error):
        raise VidgenError("OpenRouter returned an unreadable response (no data[0].b64_json)") from None
    if not data:
        raise VidgenError("OpenRouter returned an empty picture")
    usage = doc.get("usage") if isinstance(doc, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    media = item.get("media_type")
    revised = item.get("revised_prompt")
    return RawPicture(
        data,
        media if isinstance(media, str) and media else None,
        float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
        revised if isinstance(revised, str) and revised.strip() else None,
    )


def _is_vector(raw: RawPicture) -> bool:
    head = raw.data[:256].lstrip().lower()
    return raw.media_type in VECTOR_TYPES or head.startswith((b"<svg", b"<?xml"))


def parse_response(body: bytes) -> GeneratedPicture:
    """The picture of a response as PNG (JPEG / WebP converted), with its cost."""
    raw = decode_response(body)
    if _is_vector(raw):
        raise VidgenError("OpenRouter returned a vector (SVG) picture, which vidgen cannot store yet: choose a model that makes PNG/JPEG/WebP pictures")
    return GeneratedPicture(as_png(raw.data, SERVICE), raw.revised_prompt, raw.cost)


# ----- the provider ------------------------------------------------------------------------------


class OpenRouterImageProvider:
    """Generate pictures with OpenRouter's image API (any of its image models).

    ``retries`` transient failures (HTTP 429 / 5xx / 524 / 529, timeouts, dropped connections)
    are retried with exponential backoff (``backoff * 2**attempt`` seconds, or the server's
    ``Retry-After``, capped at ``max_wait``). ``sleep`` and ``fetch`` (the model-record lookup)
    are injectable for tests.
    """

    name = "openrouter"

    def __init__(
        self,
        *,
        timeout: float = 240.0,
        retries: int = 3,
        backoff: float = 4.0,
        max_wait: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        fetch: Callable[..., Lookup] | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_wait = max_wait
        self._sleep = sleep if sleep is not None else time.sleep
        self._fetch = fetch
        self._info: dict[str, Lookup] = {}

    def check_credentials(self) -> None:
        """Raise :class:`VidgenError` with setup instructions if ``OPENROUTER_API_KEY`` is unset."""
        read_api_key()

    def model_info(self, model: str) -> Lookup:
        """The model's public record (fetched once per provider)."""
        if model not in self._info:
            self._info.update(lookup_models([model], fetch=self._fetch))
        return self._info[model]

    def check_requests(self, requests: Sequence[ImageRequest]) -> None:
        """Refuse, before any paid request, a model OpenRouter does not have and options the
        model does not take. When the records cannot be reached nothing is refused (the
        generation itself reports what goes wrong)."""
        problems: list[str] = []
        for request in requests:
            lookup = self.model_info(request.model)
            if isinstance(lookup, LookupFailure):
                if lookup.missing:
                    problems.append(lookup.reason)
                continue
            problems += check_request(request, lookup).problems
        if problems:
            raise VidgenError("cannot generate with these settings:\n  " + "\n  ".join(dict.fromkeys(problems)))

    def generate(self, request: ImageRequest) -> GeneratedPicture:
        """The picture of ``request``. Raises :class:`VidgenError` on any failure."""
        key = read_api_key()
        lookup = self.model_info(request.model)
        info = lookup if isinstance(lookup, ModelInfo) else None
        data = json.dumps(request_body(request, info)).encode("utf-8")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json", **APP_HEADERS}
        body = httpapi.post_with_retries(
            API_URL, data, headers=headers, service=SERVICE, secret=key, timeout=self.timeout, retries=self.retries,
            backoff=self.backoff, max_wait=self.max_wait, sleep=self._sleep, transient=_transient,
        )
        return parse_response(body)
