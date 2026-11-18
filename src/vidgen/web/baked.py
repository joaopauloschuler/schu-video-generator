"""The cache of baked maps: pictures a page bakes once (a planet's surface, a sky's cube map),
kept between pages in vidgen's cache folder (DESIGN.md §123.2).

The page side is the module ``vidgen/baked`` (``data/web/modules/baked.js``): it asks
:class:`~vidgen.web.page.WebPage` under ``__vidgen__/baked/`` whether an entry exists
(:func:`bake_key` names it), uploads a stored entry's bytes instead of baking, or bakes and hands
the bytes over. :class:`BakedStore` keeps the entries: one folder per key under
``<cache folder>/baked/``, each part (one face of a render target) a raw deflate stream (zlib level
1; the bytes of a half float or float split into planes first, which packs them a third smaller;
the page inflates and joins them), written whole into a staging folder and renamed into place (two pages or
two render jobs baking the same map at once: the second rename loses and its copy is dropped),
checked against their SHA-256 before use (a damaged entry is removed and baked again), evicted
least recently used first above :func:`limit_bytes`. Nothing here changes a scene's cache key: a
page draws the same pixels with or without an entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError

#: Environment variable: the most the baked maps may take, in MB; ``0`` switches the cache off.
LIMIT_ENV = "VIDGEN_BAKED_CACHE_MB"
#: The default limit (MB), counted on disk: about forty planets of `size: 2048` (50 MB each as stored) or ninety 1024 skies.
DEFAULT_LIMIT_MB = 2000
#: The folder under vidgen's cache folder.
FOLDER = "baked"
#: Bumped when the layout of an entry on disk or the key's recipe changes (old entries are then never found).
STORE_VERSION = 1
#: Bytes of one part (one face of a target) at most: a cube face of 4096 texels in float.
MAX_PART_BYTES = 4096 * 4096 * 16
#: Free space kept on the disk: an entry is not stored when it would leave less.
KEEP_FREE_BYTES = 500 * 1024 * 1024
#: A staged copy older than this (seconds) was left by a page that stopped: eviction removes it.
STALE_STAGING_S = 3600.0
#: Bytes per value of each type a part can have (``vidgen/baked``'s names); a part's bytes are split into that many planes before deflate.
TYPE_WIDTHS: dict[str, int] = {"u8": 1, "f16": 2, "f32": 4}
#: zlib's level for the stored parts: the fastest (a 2048 planet's 201 MB in about 1 s, a quarter of it on disk).
DEFLATE_LEVEL = 1
_STAGING = ".staging"
_META = "meta.json"
_DATA = Path(__file__).resolve().parent.parent / "data"


def limit_bytes(environ: dict[str, str] | None = None) -> int:
    """The cache's limit in bytes from :data:`LIMIT_ENV` (default :data:`DEFAULT_LIMIT_MB`); 0: off."""
    value = (os.environ if environ is None else environ).get(LIMIT_ENV, "").strip()
    if not value:
        return DEFAULT_LIMIT_MB * 1_000_000
    try:
        megabytes = float(value)
    except ValueError:
        raise VidgenError(f"{LIMIT_ENV}={value!r}: give the most the baked maps may take in MB (e.g. 2000), or 0 to switch the cache off") from None
    if megabytes < 0 or megabytes != megabytes:
        raise VidgenError(f"{LIMIT_ENV}={value!r}: give a size in MB of 0 or more (0 switches the cache off)")
    return int(megabytes * 1_000_000)


def baked_dir() -> Path:
    """Where the baked maps are kept: ``baked/`` in vidgen's cache folder (``VIDGEN_CACHE_DIR``...); only returns the path."""
    from vidgen.soundfont import cache_dir

    return cache_dir() / FOLDER


@lru_cache(maxsize=1)
def code_digest() -> str:
    """Digest of the code a bake may run in the page: vidgen's modules for pages and the bundled three.js."""
    digest = hashlib.sha256()
    files = sorted((_DATA / "web" / "modules").glob("*.js")) + [_DATA / "three" / name for name in ("three.module.js", "three.core.js")]
    for path in files:
        digest.update(path.name.encode("utf-8") + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def bake_key(request: dict[str, Any], engine: str) -> str:
    """The key of a bake the page asks for (``{name, inputs, renderer, parts, module}``, as
    ``vidgen/baked`` sends it): those, :func:`code_digest`, ``engine`` (what draws the pages,
    :func:`vidgen.web.page.engine_id`) and :data:`STORE_VERSION`, as canonical JSON, hashed."""
    what = {"store": STORE_VERSION, "code": code_digest(), "engine": engine,
            **{k: request.get(k) for k in ("name", "inputs", "renderer", "parts", "module")}}
    text = json.dumps(what, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def part_sizes(request: dict[str, Any]) -> list[tuple[int, int]] | None:
    """The byte count and value width (:data:`TYPE_WIDTHS`) of each part a request describes, or
    ``None`` when it is not a valid list."""
    parts = request.get("parts")
    if not isinstance(parts, list) or not parts or not all(isinstance(p, dict) for p in parts):
        return None
    sizes = [(p.get("bytes"), TYPE_WIDTHS.get(str(p.get("type")), 0)) for p in parts]
    if not all(isinstance(n, int) and 0 < n <= MAX_PART_BYTES and width and n % width == 0 for n, width in sizes):
        return None
    return sizes  # type: ignore[return-value]


def _is_key(key: str) -> bool:
    return len(key) == 64 and all(c in "0123456789abcdef" for c in key)


def part_file(folder: Path, index: int) -> Path:
    """The file of part ``index`` in an entry's (or a staged) folder."""
    return folder / f"{index}.z"


def write_part(path: Path, chunks: Iterable[bytes], width: int = 1) -> int:
    """Write the bytes of ``chunks`` to ``path`` as one raw deflate stream, split into ``width``
    planes first (byte ``k`` of every value, then byte ``k + 1``...: :func:`planes`); their count."""
    packer, count = zlib.compressobj(DEFLATE_LEVEL, zlib.DEFLATED, -15), 0
    with path.open("wb") as out:
        if width > 1:
            data = b"".join(chunks)
            count = len(data)
            out.write(packer.compress(planes(data, width)))
        else:
            for chunk in chunks:
                count += len(chunk)
                out.write(packer.compress(chunk))
        out.write(packer.flush())
    return count


def planes(data: bytes, width: int) -> bytes:
    """``data`` (values of ``width`` bytes) as ``width`` planes: every value's byte 0, then every byte 1..."""
    import numpy as np

    return np.frombuffer(data, np.uint8).reshape(-1, width).T.tobytes()


@dataclass(frozen=True)
class Entry:
    """A stored bake: its folder, each part's byte count (as the page uses it), its file's size and
    SHA-256, and the page's ``meta``."""

    folder: Path
    sizes: tuple[int, ...]
    stored: tuple[int, ...]
    hashes: tuple[str, ...]
    meta: dict[str, Any]

    def part(self, index: int) -> Path:
        """The file of part ``index``."""
        return part_file(self.folder, index)

    @property
    def bytes(self) -> int:
        """Bytes on disk (what the limit counts)."""
        return sum(self.stored)


@dataclass(frozen=True)
class Usage:
    """What the cache holds: entries, bytes, its folder and limit."""

    folder: Path
    entries: int
    bytes: int
    limit: int


class BakedStore:
    """The entries under ``root`` (:func:`baked_dir` by default), at most ``limit`` bytes in all."""

    def __init__(self, root: Path, limit: int) -> None:
        self.root, self.limit = root, limit

    # ----- reading ----------------------------------------------------------------------------------

    def entry(self, key: str) -> Entry | None:
        """The entry of ``key`` when it is there whole (its files of the recorded sizes), else ``None``."""
        if not _is_key(key):
            return None
        folder = self.root / key
        try:
            meta = json.loads((folder / _META).read_text(encoding="utf-8"))
            sizes = tuple(int(n) for n in meta["sizes"])
            stored = tuple(int(n) for n in meta["stored"])
            hashes = tuple(str(h) for h in meta["sha256"])
            found = Entry(folder, sizes, stored, hashes, dict(meta.get("meta") or {}))
            if meta.get("store") != STORE_VERSION or not len(sizes) == len(stored) == len(hashes):
                return None
            if any(found.part(i).stat().st_size != n for i, n in enumerate(stored)):
                return None
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return found

    def checked(self, key: str, sizes: list[int]) -> Entry | None:
        """The entry of ``key`` with parts of ``sizes`` whose files match their SHA-256 (marked as
        just used); a damaged one is removed. ``None`` when there is none to use."""
        found = self.entry(key)
        if found is None:
            return None
        if list(found.sizes) != sizes or any(_file_sha(found.part(i)) != h for i, h in enumerate(found.hashes)):
            self.remove(key)
            return None
        try:
            os.utime(found.folder / _META)
        except OSError:
            pass
        return found

    def usage(self) -> Usage:
        """How many entries and bytes the cache holds now."""
        entries = list(self._entries())
        return Usage(self.root, len(entries), sum(e.bytes for e in entries), self.limit)

    def _entries(self) -> Iterable[Entry]:
        folders = [p for p in _children(self.root) if p.is_dir() and _is_key(p.name)]
        return [e for e in (self.entry(p.name) for p in folders) if e is not None]

    # ----- writing ----------------------------------------------------------------------------------

    def staging(self, key: str) -> Path:
        """A new empty folder to write ``key``'s parts into before :meth:`commit`."""
        folder = self.root / _STAGING / f"{key}.{os.getpid()}.{uuid.uuid4().hex[:12]}"
        folder.mkdir(parents=True)
        return folder

    def has_room(self, size: int) -> bool:
        """Whether an entry of ``size`` bytes (before compression) may be stored: under the limit, and
        the disk keeps :data:`KEEP_FREE_BYTES` free."""
        if size > self.limit:
            return False
        from vidgen.render.disk import free_bytes

        try:
            free = free_bytes(self.root)
        except OSError:
            return False
        return free - size >= KEEP_FREE_BYTES

    def commit(self, key: str, folder: Path, sizes: list[int], meta: dict[str, Any]) -> bool:
        """Put the staged ``folder`` (parts written by :func:`write_part` as :func:`part_file`; ``sizes``:
        their byte counts) in place as ``key``'s entry, with ``meta``; then evict down to the limit.
        False (and the staged copy removed) when another page stored the same key first, or the
        folder could not be renamed."""
        parts = [part_file(folder, i) for i in range(len(sizes))]
        record = {"store": STORE_VERSION, "sizes": sizes, "stored": [p.stat().st_size for p in parts], "sha256": [_file_sha(p) for p in parts], "meta": meta}
        (folder / _META).write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        target = self.root / key
        try:
            if target.exists():
                raise FileExistsError(target)
            os.rename(folder, target)
        except OSError:
            shutil.rmtree(folder, ignore_errors=True)
            return False
        self.evict(keep=key)
        return True

    def evict(self, keep: str | None = None) -> int:
        """Remove the least recently used entries until the cache is under its limit (never ``keep``),
        and staged copies left by stopped pages; the bytes of the entries removed."""
        now = time.time()
        for staged in _children(self.root / _STAGING):
            if now - _mtime(staged) > STALE_STAGING_S:
                shutil.rmtree(staged, ignore_errors=True)
        entries = sorted(self._entries(), key=lambda e: _mtime(e.folder / _META))
        total, removed = sum(e.bytes for e in entries), 0
        for found in entries:
            if total <= self.limit:
                break
            if found.folder.name == keep:
                continue
            self.remove(found.folder.name)
            total -= found.bytes
            removed += found.bytes
        return removed

    def remove(self, key: str) -> None:
        """Remove ``key``'s entry (a missing one is fine)."""
        if _is_key(key):
            shutil.rmtree(self.root / key, ignore_errors=True)

    def clear(self) -> Usage:
        """Remove every entry and every staged copy; what was there."""
        before = self.usage()
        for path in _children(self.root):
            if path.is_dir() and (_is_key(path.name) or path.name == _STAGING):
                shutil.rmtree(path, ignore_errors=True)
        return before


def default_store() -> BakedStore | None:
    """The store pages use: :func:`baked_dir` with :func:`limit_bytes`, or ``None`` when the cache is off."""
    limit = limit_bytes()
    return BakedStore(baked_dir(), limit) if limit > 0 else None


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _children(folder: Path) -> list[Path]:
    try:
        return list(folder.iterdir())
    except OSError:
        return []


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


__all__ = ["DEFAULT_LIMIT_MB", "DEFLATE_LEVEL", "FOLDER", "KEEP_FREE_BYTES", "LIMIT_ENV", "MAX_PART_BYTES", "STALE_STAGING_S", "STORE_VERSION", "TYPE_WIDTHS", "BakedStore", "Entry", "Usage",
           "bake_key", "baked_dir", "code_digest", "default_store", "limit_bytes", "part_file", "part_sizes", "planes", "write_part"]
