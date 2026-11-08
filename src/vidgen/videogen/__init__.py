"""Generated video shots (DESIGN.md §113): requests, their canonical form and cache key, jobs.

A :class:`VideoRequest` is one clip asked of a video model (OpenRouter's asynchronous video API:
submit, poll, download). A request asks for the model's own sound only when its
``generate_audio`` is true (a shot's resolved ``sound: model``, DESIGN.md §113.11); by default it
is sent with ``generate_audio: false`` and vidgen's mix is the film's sound. Requests are cached
by :func:`request_hash`, the SHA-256 of :func:`canonical_request` (input files by their contents'
hashes, ``generate_audio`` as sent), so the same request is never paid for twice and a request
with sound is never served the clip of one without.

Modules: :mod:`.models` (the public video model list, checks, cost estimates),
:mod:`.openrouter` (the provider), :mod:`.mock` (a fake OpenRouter for tests and dry demos),
:mod:`.ledger` (the spending ledger and budget cap), :mod:`.pictures` (smaller copies of the
pictures sent inline), :mod:`.run` (cache, budget, pay or dry run).
"""

from __future__ import annotations

import difflib
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from vidgen.errors import VidgenError

#: Bumped when the canonical form changes (old cache entries then miss).
CACHE_VERSION = 1
#: Where generated clips are stored in a project, ``<hash>.mp4`` with a ``<hash>.json`` sidecar.
CLIPS_DIR = Path("assets") / "generated_video"
#: The project's spending ledger (append-only JSON lines, DESIGN.md §113).
LEDGER_NAME = "videogen-ledger.jsonl"
#: Job statuses OpenRouter reports while a job runs, and the terminal ones.
RUNNING_STATUSES = frozenset({"pending", "in_progress"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "expired"})

MediaKind = Literal["image", "audio", "video"]
FrameType = Literal["first_frame", "last_frame"]


def did_you_mean(word: str, options: Sequence[str]) -> str:
    """`` (did you mean X?)`` for the closest of ``options``, else ``""``."""
    lowered = {o.lower(): o for o in options}
    close = difflib.get_close_matches(word.lower(), list(lowered), n=1, cutoff=0.6)
    return f" (did you mean {lowered[close[0]]}?)" if close else ""


@dataclass(frozen=True)
class MediaInput:
    """An input picture, sound or clip: a local ``path`` (sent inline or uploaded) or a hosted
    ``url``. ``frame_type`` marks a frame image (``first_frame`` / ``last_frame``); without it
    the input is a reference."""

    kind: MediaKind
    path: Path | None = None
    url: str | None = None
    frame_type: FrameType | None = None

    def __post_init__(self) -> None:
        if (self.path is None) == (self.url is None):
            raise VidgenError(f"a {self.kind} input needs a path or a url (one of them)")
        if self.frame_type is not None and self.kind != "image":
            raise VidgenError(f"only pictures can be frame images, not a {self.kind} ({self.frame_type})")

    def canonical(self) -> dict[str, Any]:
        """The input in the cache key: a file by its contents' SHA-256 and size (its name does
        not matter), a url as written."""
        out: dict[str, Any] = {"kind": self.kind, "frame_type": self.frame_type}
        if self.url is not None:
            out["url"] = self.url
            return out
        assert self.path is not None
        try:
            data = self.path.read_bytes()
        except OSError as exc:
            raise VidgenError(f"cannot read the {self.kind} input {self.path}: {exc.strerror or exc}") from None
        out["sha256"] = hashlib.sha256(data).hexdigest()
        out["bytes"] = len(data)
        return out


@dataclass(frozen=True)
class VideoRequest:
    """One clip asked of a video model. ``provider_options`` maps an upstream provider's slug
    to its passthrough parameters (``provider.options.<slug>.parameters``)."""

    model: str
    prompt: str = ""
    duration: int | None = None
    resolution: str | None = None
    size: str | None = None
    aspect_ratio: str | None = None
    frame_images: tuple[MediaInput, ...] = ()
    references: tuple[MediaInput, ...] = ()
    seed: int | None = None
    previous_job_id: str | None = None
    provider_options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    generate_audio: bool = False

    def __post_init__(self) -> None:
        if "/" not in self.model.strip("/"):
            raise VidgenError(f"OpenRouter model ids look like author/name (e.g. bytedance/seedance-2.0-fast), not {self.model!r}")
        if self.duration is not None and self.duration <= 0:
            raise VidgenError(f"duration must be a whole number of seconds above 0, not {self.duration}")
        if self.size is not None and self.resolution is not None:
            raise VidgenError("give size (WIDTHxHEIGHT) or resolution, not both")
        if any(f.frame_type is None for f in self.frame_images):
            raise VidgenError("each frame image needs frame_type first_frame or last_frame")
        if any(r.frame_type is not None for r in self.references):
            raise VidgenError("references take no frame_type (put frame images in frame_images)")

    @property
    def images(self) -> int:
        """Number of input pictures (frame images and picture references)."""
        return len(self.frame_images) + sum(1 for r in self.references if r.kind == "image")


def canonical_request(request: VideoRequest) -> dict[str, Any]:
    """Everything that decides the clip, as plain JSON (input files by content hash; local
    pictures by their source, with the size limit of the copies sent, :mod:`.pictures`)."""
    from vidgen.videogen.pictures import JPEG_QUALITY, PICTURE_MAX_SIDE

    return {
        "cache_version": CACHE_VERSION,
        "model": request.model,
        "prompt": request.prompt,
        "duration": request.duration,
        "resolution": request.resolution,
        "size": request.size,
        "aspect_ratio": request.aspect_ratio,
        "generate_audio": request.generate_audio,
        "frame_images": [f.canonical() for f in request.frame_images],
        "references": [r.canonical() for r in request.references],
        "pictures_sent": {"max_side": PICTURE_MAX_SIDE, "jpeg_quality": JPEG_QUALITY},
        "seed": request.seed,
        "previous_job_id": request.previous_job_id,
        "provider_options": {k: dict(v) for k, v in sorted(request.provider_options.items())},
    }


def request_hash(request: VideoRequest) -> str:
    """The cache key of ``request``: 24 hex digits of the SHA-256 of its canonical JSON."""
    text = json.dumps(canonical_request(request), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


#: The ``videogen.provider`` that sends nothing and shares nothing (a fake API).
MOCK_PROVIDER = "mock"


@dataclass(frozen=True)
class JobState:
    """A video job as OpenRouter reports it: ``status`` (pending, in_progress, completed,
    failed, cancelled, expired), the reported ``cost`` (US dollars, ``usage.cost``) once known,
    and the ``error`` text of a failed job."""

    id: str
    status: str
    polling_url: str | None = None
    cost: float | None = None
    is_byok: bool | None = None
    error: str | None = None

    @property
    def done(self) -> bool:
        """Whether the job has finished (successfully or not)."""
        return self.status in TERMINAL_STATUSES


__all__ = [
    "CACHE_VERSION", "CLIPS_DIR", "LEDGER_NAME", "RUNNING_STATUSES", "TERMINAL_STATUSES",
    "JobState", "MediaInput", "VideoRequest", "canonical_request", "did_you_mean", "request_hash",
]
