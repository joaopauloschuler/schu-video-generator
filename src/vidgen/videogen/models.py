"""OpenRouter's public video model list: fetch (no key), cache, checks and cost estimates
(DESIGN.md §113).

``GET https://openrouter.ai/api/v1/videos/models`` lists each model's supported durations,
resolutions, aspect ratios, sizes, frame types, ``generate_audio`` / ``seed`` capability,
passthrough parameters and ``pricing_skus`` (name -> price string). The list is cached in
vidgen's cache folder (``openrouter/video_models.json``) and read from there offline.

Prices: SKU names say what they bill. ``cents_per_...`` values are US cents, the others US
dollars; ``...second...`` SKUs are per second of output (a ``_480p`` / ``_4k`` ... suffix is a
resolution tier, ``with_audio`` / ``without_audio``, ``text_to_video`` / ``image_to_video``,
``reference_`` and ``video_continuation`` say when they apply); ``video_tokens`` SKUs are per
token, estimated as ``width x height x 24 fps x seconds / 1024`` (ByteDance's Seedance token
formula); ``image_input`` / ``reference_images`` SKUs are per input picture; ``minimum_...`` is
a floor per generation. Where several SKUs could apply, the estimate takes the highest (a
conservative budget).
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen import httpapi
from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.videogen import VideoRequest, did_you_mean

API_BASE = "https://openrouter.ai/api/v1"
MODELS_URL = f"{API_BASE}/videos/models"
SERVICE = "OpenRouter"
#: Seconds the free model-list lookup may take.
LOOKUP_TIMEOUT = 10.0
#: A cached list younger than this is used without asking OpenRouter again.
CACHE_MAX_AGE = 24 * 3600.0
#: Frames per second assumed for token-priced models (Seedance renders 24 fps).
TOKEN_FPS = 24
#: The short side in pixels of each resolution tier (``2K`` = 1440p, ``4K`` = 2160p).
TIER_SHORT_SIDE: dict[str, int] = {"360p": 360, "480p": 480, "720p": 720, "768p": 768, "1080p": 1080, "2k": 1440, "4k": 2160}
_TIER = re.compile(r"(?:^|_)(360p|480p|720p|768p|1080p|2k|4k)(?:_|$)")


# ----- the records -------------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoModel:
    """One video model as the list describes it (``None``: the list says nothing)."""

    id: str
    name: str = ""
    description: str = ""
    durations: tuple[int, ...] | None = None
    resolutions: tuple[str, ...] | None = None
    aspect_ratios: tuple[str, ...] | None = None
    sizes: tuple[str, ...] | None = None
    frame_types: tuple[str, ...] | None = None
    generate_audio: bool | None = None
    seed: bool | None = None
    passthrough: tuple[str, ...] = ()
    pricing: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> VideoModel:
        """A record of ``GET /videos/models`` (unknown keys ignored)."""

        def strings(key: str) -> tuple[str, ...] | None:
            value = record.get(key)
            return tuple(str(v) for v in value) if isinstance(value, list) else None

        durations = record.get("supported_durations")
        flag = lambda key: record[key] if isinstance(record.get(key), bool) else None  # noqa: E731
        pricing = record.get("pricing_skus")
        return cls(
            id=str(record["id"]),
            name=str(record.get("name") or ""),
            description=str(record.get("description") or ""),
            durations=tuple(sorted(int(d) for d in durations if isinstance(d, (int, float)))) if isinstance(durations, list) else None,
            resolutions=strings("supported_resolutions"),
            aspect_ratios=strings("supported_aspect_ratios"),
            sizes=strings("supported_sizes"),
            frame_types=strings("supported_frame_images"),
            generate_audio=flag("generate_audio"),
            seed=flag("seed"),
            passthrough=strings("allowed_passthrough_parameters") or (),
            pricing={str(k): str(v) for k, v in pricing.items()} if isinstance(pricing, dict) else {},
        )

    def to_json(self) -> dict[str, Any]:
        """The record as ``vidgen generate models --json`` lists it."""
        return {
            "id": self.id, "name": self.name, "durations": list(self.durations) if self.durations is not None else None,
            "resolutions": _listed(self.resolutions), "aspect_ratios": _listed(self.aspect_ratios), "sizes": _listed(self.sizes),
            "frame_images": _listed(self.frame_types), "generate_audio": self.generate_audio, "seed": self.seed,
            "passthrough": list(self.passthrough), "pricing_skus": dict(self.pricing), "prices": price_lines(self),
        }


def _listed(values: tuple[str, ...] | None) -> list[str] | None:
    return list(values) if values is not None else None


def parse_models(doc: Any) -> list[VideoModel]:
    """The models of a ``{data: [...]}`` document. Raises :class:`VidgenError` if unreadable."""
    try:
        return [VideoModel.from_record(r) for r in doc["data"] if isinstance(r, dict) and r.get("id")]
    except (KeyError, TypeError, ValueError):
        raise VidgenError("OpenRouter's video model list is unreadable (no data: [...])") from None


@dataclass(frozen=True)
class Catalog:
    """The video model list with when it was fetched (UNIX time) and where it came from
    (``live`` or ``cache``; ``note`` says why a stale cache is used)."""

    models: tuple[VideoModel, ...]
    fetched_at: float
    source: str
    note: str | None = None

    def find(self, model: str) -> VideoModel:
        """The model ``model``. Raises :class:`VidgenError` with a did-you-mean if absent."""
        for m in self.models:
            if m.id == model:
                return m
        ids = [m.id for m in self.models]
        raise VidgenError(f"OpenRouter lists no video model {model!r}{did_you_mean(model, ids)}; `vidgen generate models` lists them")


def default_cache_path() -> Path:
    """``openrouter/video_models.json`` in vidgen's cache folder."""
    from vidgen.soundfont import cache_dir

    return cache_dir() / "openrouter" / "video_models.json"


def fetch_models_doc(timeout: float = LOOKUP_TIMEOUT) -> Any:
    """``GET /videos/models`` (public; no key is sent). Raises :class:`VidgenError`."""
    headers = {"Accept": "application/json"}
    try:
        body = httpapi.get(MODELS_URL, headers=headers, service=SERVICE, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise VidgenError(f"OpenRouter's video model list answered HTTP {exc.code}") from None
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        raise VidgenError("OpenRouter's video model list sent an unreadable answer") from None


def load_catalog(
    *, refresh: bool = False, cache_path: Path | None = None, fetch: Callable[[], Any] | None = None,
    now: Callable[[], float] | None = None, max_age: float = CACHE_MAX_AGE,
) -> Catalog:
    """The video model list: the cache when younger than ``max_age`` (unless ``refresh``),
    else fetched and cached; offline, the cache whatever its age (with a note). Raises
    :class:`VidgenError` when neither is available."""
    path = cache_path if cache_path is not None else default_cache_path()
    clock = now if now is not None else time.time
    cached = _read_cache(path)
    if cached is not None and not refresh and clock() - cached[0] <= max_age:
        return Catalog(tuple(parse_models(cached[1])), cached[0], "cache")
    try:
        doc = (fetch or fetch_models_doc)()
        models = parse_models(doc)
    except VidgenError as exc:
        if cached is None:
            raise VidgenError(f"{exc}, and no copy is cached yet ({path}): connect once to fetch the list") from None
        return Catalog(tuple(parse_models(cached[1])), cached[0], "cache", note=f"{exc}: using the cached list")
    stamp = clock()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps({"fetched_at": stamp, "doc": doc}, indent=1, ensure_ascii=True))
    return Catalog(tuple(models), stamp, "live")


def _read_cache(path: Path) -> tuple[float, Any] | None:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return float(saved["fetched_at"]), saved["doc"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ----- checking a request ------------------------------------------------------------------------


@dataclass
class RequestCheck:
    """What a model makes of a request: ``problems`` (refused before any job), ``notes`` and
    ``drop`` (fields the model has no setting for: not sent)."""

    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    drop: set[str] = field(default_factory=set)


def snap_duration(seconds: float, durations: Sequence[int]) -> int:
    """The shortest allowed duration at least ``seconds`` long (the clip is trimmed later),
    else the longest allowed."""
    longer = [d for d in sorted(durations) if d >= seconds - 1e-9]
    return longer[0] if longer else max(durations)


def _ranges(values: Sequence[int]) -> str:
    """``4-15`` for a run of whole numbers, else ``4, 6, 8``."""
    values = sorted(values)
    if len(values) > 2 and values == list(range(values[0], values[-1] + 1)):
        return f"{values[0]}-{values[-1]}"
    return ", ".join(str(v) for v in values)


def _one_of(name: str, value: str, listed: tuple[str, ...] | None, model: VideoModel, check: RequestCheck) -> None:
    if listed is None:
        check.notes.append(f"{model.id} lists no {name} setting: {name} {value} is not sent")
        check.drop.add(name)
    elif value.lower() not in {v.lower() for v in listed}:
        check.problems.append(f"{model.id} takes {name} {', '.join(listed)}, not {value}{did_you_mean(value, listed)}")


def check_request(request: VideoRequest, model: VideoModel) -> RequestCheck:
    """``request`` against ``model``'s listed settings."""
    check = RequestCheck()
    if request.duration is not None:
        if model.durations is None:
            check.notes.append(f"{model.id} lists no durations (its length follows its inputs): duration {request.duration} is not sent")
            check.drop.add("duration")
        elif request.duration not in model.durations:
            snapped = snap_duration(request.duration, model.durations)
            check.problems.append(f"{model.id} makes clips of {_ranges(model.durations)} s, not {request.duration} (did you mean {snapped}?)")
    if request.resolution is not None:
        _one_of("resolution", request.resolution, model.resolutions, model, check)
    if request.size is not None:
        _one_of("size", request.size, model.sizes, model, check)
    if request.aspect_ratio is not None:
        _one_of("aspect_ratio", request.aspect_ratio, model.aspect_ratios, model, check)
    for frame in request.frame_images:
        if model.frame_types is None or frame.frame_type not in model.frame_types:
            listed = ", ".join(model.frame_types) if model.frame_types else "no frame images"
            check.problems.append(f"{model.id} takes {listed}, not a {frame.frame_type}")
    if request.seed is not None and model.seed is False:
        check.notes.append(f"{model.id} takes no seed: the seed is not sent")
        check.drop.add("seed")
    for slug, params in request.provider_options.items():
        for key in params:
            if key not in model.passthrough:
                allowed = ", ".join(model.passthrough) or "none"
                check.problems.append(f"{model.id} passes no option {key!r} through to {slug} (allowed: {allowed}){did_you_mean(key, model.passthrough)}")
    if any(r.kind in ("audio", "video") for r in request.references):
        check.notes.append("audio and video references are honoured only by providers that support them (e.g. Seedance 2.x); others ignore them")
    return check


# ----- prices ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Estimate:
    """A clip's estimated cost in US dollars (``None``: unknown) and how it was worked out."""

    cost: float | None
    basis: str


def money(value: float) -> str:
    """``$0.104`` (3 decimals; 4 below a cent)."""
    return f"${value:.4f}" if 0 < value < 0.01 else f"${value:.3f}"


def _usd(name: str, value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number / 100 if "cents" in name else number


def resolution_pixels(resolution: str | None, aspect_ratio: str | None, size: str | None) -> tuple[int, int] | None:
    """Width and height of a request (``size`` as given; a tier's short side by the aspect
    ratio, 16:9 when none is given); ``None`` without either."""
    if size:
        w, _, h = size.lower().partition("x")
        return (int(w), int(h)) if w.isdigit() and h.isdigit() else None
    short = TIER_SHORT_SIDE.get((resolution or "").lower())
    if short is None:
        return None
    a, _, b = (aspect_ratio or "16:9").partition(":")
    try:
        ratio = float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        ratio = 16 / 9
    long = 2 * math.ceil(short * max(ratio, 1 / ratio) / 2)
    return (long, short) if ratio >= 1 else (short, long)


def _tier_of(request: VideoRequest) -> str | None:
    if request.resolution:
        return request.resolution.lower()
    px = resolution_pixels(None, None, request.size)
    if px is None:
        return None
    short = min(px)
    return next((t for t, s in TIER_SHORT_SIDE.items() if s == short), None)


def _applicable(names: list[str], request: VideoRequest) -> list[str]:
    """The SKUs of one kind that apply to ``request`` (see the module docstring)."""
    out = [n for n in names if ("continuation" in n) == (request.previous_job_id is not None)] or names
    if not request.references:
        out = [n for n in out if not n.startswith("reference")] or out
    has_video_ref = any(r.kind == "video" for r in request.references)
    out = [n for n in out if ("with_video_input" in n) == has_video_ref] or out
    mode = "image_to_video" if request.frame_images else "text_to_video"
    if any(mode in n for n in out):
        out = [n for n in out if mode in n or ("text_to_video" not in n and "image_to_video" not in n)]
    tier = _tier_of(request)
    if tier is not None:
        matching = [n for n in out if (m := _TIER.search(n)) is not None and m.group(1) == tier]
        untagged = [n for n in out if not _TIER.search(n)]
        out = matching or untagged or out
    if any("without_audio" in n for n in out):
        out = [n for n in out if "without_audio" in n]  # generate_audio is always false
    return out


def estimate(request: VideoRequest, model: VideoModel, *, duration: float | None = None, minimum: bool = True) -> Estimate:
    """The estimated cost of ``request`` from ``model``'s ``pricing_skus`` (the highest SKU
    that could apply). ``duration`` (seconds) prices a model without a duration setting (its
    length follows its audio); otherwise the request's duration, else the longest allowed.
    ``minimum``: apply a per-generation minimum price."""
    seconds = float(duration if duration is not None else request.duration or 0) or (max(model.durations) if model.durations else 0.0)
    if not model.pricing:
        return Estimate(None, f"price unknown: {model.id} lists no prices")
    if seconds <= 0:
        return Estimate(None, f"price unknown: {model.id} is priced per second and the clip's length is not known")
    skus = {n: _usd(n, v) for n, v in model.pricing.items()}
    skus = {n: v for n, v in skus.items() if v is not None}
    per_second = [n for n in skus if "second" in n and "megapixel" not in n and not n.startswith("minimum")]
    tokens = [n for n in skus if "video_tokens" in n]
    images = [n for n in skus if n in ("cents_per_image_input", "reference_input_images", "reference_images") or n.endswith("image_input")]
    floor = [skus[n] for n in skus if n.startswith("minimum")]
    parts: list[str] = []
    cost: float | None = None
    if per_second:
        names = _applicable(per_second, request)
        rate = max(skus[n] for n in names)
        cost = rate * seconds
        chosen = max(names, key=lambda n: skus[n])
        parts.append(f"{money(rate)}/s x {seconds:g} s ({chosen})")
    elif tokens:
        px = resolution_pixels(request.resolution, request.aspect_ratio, request.size)
        if px is None and model.resolutions:
            px = resolution_pixels(max(model.resolutions, key=lambda r: TIER_SHORT_SIDE.get(r.lower(), 0)), request.aspect_ratio, None)
        if px is None:
            return Estimate(None, f"price unknown: {model.id} is priced per video token and the clip's size is not known")
        names = _applicable(tokens, request)
        rate = max(skus[n] for n in names)
        count = px[0] * px[1] * TOKEN_FPS * seconds / 1024
        cost = rate * count
        parts.append(f"~{count:,.0f} tokens ({px[0]}x{px[1]}, {TOKEN_FPS} fps, {seconds:g} s) x ${rate:g} ({max(names, key=lambda n: skus[n])})")
    if cost is None:
        return Estimate(None, f"price unknown: {model.id}'s prices ({', '.join(model.pricing)}) are not per second or per token")
    if images:
        n_images = request.images if any("input" in n for n in images) else sum(1 for r in request.references if r.kind == "image")
        if n_images:
            rate = max(skus[n] for n in images)
            cost += rate * n_images
            parts.append(f"+ {n_images} picture(s) x {money(rate)}")
    if floor and minimum and cost < max(floor):
        cost = max(floor)
        parts.append(f"(minimum {money(cost)} per generation)")
    return Estimate(cost, " ".join(parts))


def price_lines(model: VideoModel) -> list[str]:
    """``480p ~$0.104/s`` per listed resolution (the estimate of one second, 16:9, no
    inputs), or one line for a model without resolutions; ``price unknown`` when none works."""
    tiers: Iterable[str | None] = sorted(model.resolutions, key=lambda r: TIER_SHORT_SIDE.get(r.lower(), 0)) if model.resolutions else [None]
    lines = []
    for tier in tiers:
        probe = VideoRequest(model=model.id, duration=1, resolution=tier, aspect_ratio="16:9")
        est = estimate(probe, model, duration=1.0, minimum=False)
        if est.cost is not None:
            approx = "~" if any("video_tokens" in n for n in model.pricing) else ""
            lines.append(f"{tier + ' ' if tier else ''}{approx}{money(est.cost)}/s")
    floors = [v for n, s in model.pricing.items() if n.startswith("minimum") and (v := _usd(n, s)) is not None]
    if lines and floors:
        lines.append(f"at least {money(max(floors))} per clip")
    return lines or ["price unknown"]


def model_line(model: VideoModel) -> str:
    """One line per model for ``vidgen generate models``."""
    parts = [model.id]
    if model.durations:
        parts.append(f"{_ranges(model.durations)} s")
    else:
        parts.append("length from inputs")
    if model.resolutions:
        parts.append("/".join(model.resolutions))
    if model.aspect_ratios:
        parts.append(" ".join(model.aspect_ratios))
    frames = {"first_frame": "first", "last_frame": "last"}
    if model.frame_types:
        parts.append("frames: " + "+".join(frames.get(f, f) for f in model.frame_types))
    parts.append(", ".join(price_lines(model)))
    return " | ".join(parts)
