"""Fast re-render (DESIGN.md §94.14, Step 196): every track's stem is kept in memory under a key
of exactly what its sound depends on, so an edit re-renders only the tracks it changed and
remixes; mute / solo remix the kept stems at the whole piece's gain; level meters are each
stem's loudness per 50 ms.

What a track's sound depends on (:func:`vidgen.studio.render.render_track_stem`): the score's
shared data (every top-level key but ``title``, ``description``, ``master`` and ``tracks``), its
own spec and name, and — when it ducks under another track — when that track hits (its steps,
accent, play and the sections it plays in), plus the renderer. The master filter and the level
(−28 LUFS) are the mix's, applied after the stems are summed. A change of only a track's volume
(one number for the whole track) scales its kept stem instead of rendering it.

Stems are float64 (a minute of stereo is 46 MB): kept in memory only, least recently used out
past :data:`STEM_CACHE_BYTES`. A restarted studio renders them again on its first render.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen import __version__

#: Bump when a stem of the same track would sound different (the stem keys include it).
STEM_RENDER_VERSION = 1
#: Memory kept for stems (least recently used out first; the stems of the mix being made stay):
#: about two versions of a 50-second piece of nine tracks (41 MB a stem).
STEM_CACHE_BYTES = 768 << 20
#: Threads for the mix's master filter (one per channel) and loudness: the same samples as on
#: one, in about half the time on two cores. Tracks render one at a time (memory).
THREADS = 2
#: Filters and reverb on quick FFT lengths when a piece's length is a slow one (Step 201,
#: DESIGN.md §94.19): within about 1e-14 of the exact samples, the same 16-bit audio, 2–3 times
#: faster and a third less memory on such pieces (exports render exactly, as videos do).
FAST_FFT = True
#: A meter frame (s): the level of each stem per frame.
METER_SECONDS = 0.05
#: The quietest level a meter reports (dBFS as heard); quieter is this.
METER_FLOOR_DB = -60.0
#: Top-level keys of a score no track's sound depends on (the master filter is the mix's).
NOT_TRACK_INPUTS = ("title", "description", "master", "tracks")
#: What of a track another track's duck depends on (when it hits, and how hard).
HIT_KEYS = ("steps", "accent", "play", "rest", "only")
HIT_PART_KEYS = ("steps", "accent")


def _digest(doc: Any) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


def hit_inputs(spec: Any) -> Any:
    """The part of a track's spec that decides when it hits (what a duck under it follows)."""
    if not isinstance(spec, Mapping):
        return spec
    out: dict[str, Any] = {k: spec[k] for k in HIT_KEYS if k in spec}
    sections = spec.get("sections")
    if isinstance(sections, Mapping):
        out["sections"] = {str(s): ({k: v[k] for k in HIT_PART_KEYS if k in v} if isinstance(v, Mapping) else v) for s, v in sections.items()}
    elif sections is not None:
        out["sections"] = sections
    return out


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def plain_volume(spec: Any) -> float | None:
    """The track's volume (dB) when it is one number for the whole track — written or 0, no
    section changing it — so the track's sound is its sound at 0 dB times one gain; else ``None``.
    (Every note is scaled by the volume, and all the effects after are linear: echo, reverb,
    filters, gate, duck, volume curves of other keys, width.)"""
    if not isinstance(spec, Mapping):
        return None
    volume = spec.get("volume", 0)
    sections = spec.get("sections")
    if not _is_number(volume) or (sections is not None and not isinstance(sections, Mapping)):
        return None
    if isinstance(sections, Mapping) and any(not isinstance(v, Mapping) or "volume" in v for v in sections.values()):
        return None
    return float(volume)


@dataclass(frozen=True)
class TrackKey:
    """A track's stem key and, when its volume is one number (:func:`plain_volume`), the key
    of the same track without it (``level_key``) and that volume — so a volume change scales a
    kept stem instead of rendering it again."""

    key: str
    level_key: str | None
    volume: float | None


def track_keys(data: Mapping[str, Any], score: Any) -> dict[str, TrackKey]:
    """Each track's stem key (24 hex digits) for the score's ``data`` (as read from YAML) and the
    checked ``score``: the same key, the same samples."""
    shared = {k: v for k, v in data.items() if k not in NOT_TRACK_INPUTS}
    raw = data.get("tracks") or {}
    out: dict[str, TrackKey] = {}
    for track in score.tracks:
        ducks = sorted({p.duck.to for p in track.parts.values() if p.duck is not None and p.duck.to != "beat"})
        spec = raw.get(track.name)
        doc = {
            "song": shared,
            "name": track.name,
            "track": spec,
            "duck_to": {to: hit_inputs(raw.get(to)) for to in ducks},
            "stems": STEM_RENDER_VERSION,
            "vidgen": __version__,
        }
        volume = plain_volume(spec)
        level_key = _digest({**doc, "track": {k: v for k, v in spec.items() if k != "volume"}}) if volume is not None else None
        out[track.name] = TrackKey(_digest(doc), level_key, volume)
    return out


@dataclass(frozen=True)
class CachedStem:
    """A track's stem and its power per meter frame (mean square over both channels, from the
    piece's start, the one-shot's tail included)."""

    stem: Any  # vidgen.studio.render.TrackStem
    power: np.ndarray
    seconds: float  # how long it took to render
    level_key: str | None = None
    volume: float | None = None
    scaled: bool = False  # made from another volume's stem

    @property
    def nbytes(self) -> int:
        return int(self.stem.data.nbytes + self.power.nbytes)

    def at_volume(self, volume: float, key: TrackKey) -> CachedStem:
        """This stem at another volume (dB): every sample times the gain between them."""
        from vidgen.studio.render import TrackStem

        assert self.volume is not None
        began = time.perf_counter()
        gain = 10 ** ((volume - self.volume) / 20)
        data = self.stem.data * gain
        data.setflags(write=False)
        stem = TrackStem(self.stem.name, data, self.stem.before, self.stem.skipped)
        return CachedStem(stem, self.power * gain**2, time.perf_counter() - began, key.level_key, volume, True)


def frame_power(piece: np.ndarray) -> np.ndarray:
    """Mean square of a stereo signal per :data:`METER_SECONDS` frame (the last frame partial)."""
    from vidgen.sfx import RATE

    hop = int(METER_SECONDS * RATE)
    n = len(piece)
    whole = n // hop
    power = np.empty(whole + (1 if n % hop else 0))
    if whole:
        power[:whole] = np.mean(np.square(piece[: whole * hop]).reshape(whole, hop * 2), axis=1)
    if n % hop:
        power[whole] = float(np.mean(np.square(piece[whole * hop :])))
    return power


def meter_levels(power: np.ndarray, frames: int, gain: float) -> list[float]:
    """A stem's level per frame as heard (dBFS, its RMS times ``gain``: the mix's level and the
    audition gain; before the master filter), ``frames`` long, at least :data:`METER_FLOOR_DB`."""
    p = np.zeros(frames)
    p[: min(frames, len(power))] = power[:frames]
    with np.errstate(divide="ignore"):
        db = 10 * np.log10(p) + 20 * math.log10(gain) if gain > 0 else np.full(frames, -np.inf)
    return [round(float(v), 1) for v in np.maximum(db, METER_FLOOR_DB)]


class StemCache:
    """Stems by key, in memory, least recently used out past ``budget`` bytes. Thread-safe."""

    def __init__(self, budget: int = STEM_CACHE_BYTES) -> None:
        self.budget = budget
        self._items: OrderedDict[str, CachedStem] = OrderedDict()
        self._levels: dict[str, str] = {}  # level key → the key of a stem rendered (not scaled)
        self._lock = threading.Lock()

    def get(self, key: str) -> CachedStem | None:
        with self._lock:
            found = self._items.get(key)
            if found is not None:
                self._items.move_to_end(key)
            return found

    def at_level(self, level_key: str) -> CachedStem | None:
        """A rendered stem of the same track at another volume, or ``None``."""
        with self._lock:
            key = self._levels.get(level_key)
            return self._items.get(key) if key is not None else None

    def put(self, key: str, item: CachedStem, keep: Sequence[str] = ()) -> None:
        """Keep ``item``; drop the least recently used stems (never those in ``keep``) while
        the total is over the budget."""
        with self._lock:
            self._items[key] = item
            self._items.move_to_end(key)
            if item.level_key is not None and not item.scaled:
                self._levels[item.level_key] = key
            self._trim(self.budget, [*keep, key])

    def make_room(self, nbytes: int, keep: Sequence[str] = ()) -> None:
        """Drop the least recently used stems (not those in ``keep``) so that ``nbytes`` more
        fit in the budget — before rendering, so stems and renders never hold more together."""
        with self._lock:
            self._trim(max(self.budget - nbytes, 0), keep)

    def _trim(self, limit: int, keep: Sequence[str]) -> None:
        total = sum(i.nbytes for i in self._items.values())
        for old in list(self._items):
            if total <= limit:
                break
            if old in keep:
                continue
            gone = self._items.pop(old)
            total -= gone.nbytes
            if gone.level_key is not None and self._levels.get(gone.level_key) == old:
                del self._levels[gone.level_key]

    @property
    def nbytes(self) -> int:
        with self._lock:
            return sum(i.nbytes for i in self._items.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def stem_bytes(score: Any) -> int:
    """The memory one stem of ``score`` takes (float64 stereo on the piece's canvas)."""
    from vidgen.sfx import RATE
    from vidgen.studio.render import BEFORE_SECONDS, TAIL_SECONDS

    samples = score.samples if score.loop else int(BEFORE_SECONDS * RATE) + score.samples + int(TAIL_SECONDS * RATE)
    return samples * 2 * 8


@dataclass
class StemSet:
    """The stems of one score: by track name, the keys, and which were rendered now (seconds).
    ``streamed`` (Step 201): the score's stems do not fit the cache together (a long piece: a
    5-minute stem is 235 MB) — then ``stems`` is empty and :meth:`get` gives each when asked
    (kept, or rendered then and kept while it fits), so a mix holds one stem besides its sum
    instead of all of them; ``rendered`` / ``scaled`` fill in as they are asked for."""

    stems: dict[str, CachedStem]
    keys: dict[str, TrackKey]
    rendered: dict[str, float]  # tracks rendered now: seconds
    scaled: dict[str, float]  # tracks whose kept stem was set to a new volume: seconds
    seconds: float
    streamed: bool = False
    fetch: Callable[[str], CachedStem] | None = None

    def get(self, name: str) -> CachedStem:
        """Track ``name``'s stem (rendered now when it is streamed and not kept)."""
        if name in self.stems:
            return self.stems[name]
        assert self.fetch is not None, name
        return self.fetch(name)


def score_stems(cache: StemCache, data: Mapping[str, Any], score: Any) -> StemSet:
    """Every track's stem of ``score``: from ``cache`` when its key is there; a kept stem of the
    track at another volume scaled when only its (plain) volume changed; else rendered and kept.
    The stems dict is in the score's track order. When they cannot all be kept at once
    (:attr:`StemSet.streamed`), nothing is rendered here: :meth:`StemSet.get` does it."""
    from vidgen.studio.render import render_track_stem

    began = time.perf_counter()
    keys = track_keys(data, score)
    streamed = len(keys) * stem_bytes(score) > cache.budget
    keep = [] if streamed else [k.key for k in keys.values()]
    rendered: dict[str, float] = {}
    scaled: dict[str, float] = {}

    def kept(name: str) -> CachedStem | None:
        key = keys[name]
        found = cache.get(key.key)
        if found is None and key.level_key is not None and key.volume is not None:
            other = cache.at_level(key.level_key)
            if other is not None:
                found = other.at_volume(key.volume, key)
                cache.put(key.key, found, keep)
                scaled[name] = round(found.seconds, 3)
        return found

    def render(name: str) -> CachedStem:
        t0 = time.perf_counter()
        stem = render_track_stem(score, name, fast_fft=FAST_FFT)
        item = CachedStem(stem, frame_power(stem.piece), time.perf_counter() - t0, keys[name].level_key, keys[name].volume)
        cache.put(keys[name].key, item, keep)
        rendered[name] = round(item.seconds, 3)
        return item

    if streamed:
        def fetch(name: str) -> CachedStem:
            found = kept(name)
            if found is None:
                cache.make_room(stem_bytes(score))  # room for this one before it renders
                found = render(name)
            return found

        return StemSet({}, keys, rendered, scaled, time.perf_counter() - began, True, fetch)
    stems = {name: found for name in keys if (found := kept(name)) is not None}
    missing = [name for name in keys if name not in stems]
    if missing:
        cache.make_room(len(missing) * stem_bytes(score), keep)
    for name in missing:  # one at a time: a heavy track's render takes hundreds of MB while it runs
        stems[name] = render(name)
    ordered = {name: stems[name] for name in keys}
    return StemSet(ordered, keys, rendered, scaled, time.perf_counter() - began)
