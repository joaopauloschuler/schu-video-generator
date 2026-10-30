"""The SoundFont that composed music is played with (DESIGN.md §81; no manim).

By default GeneralUser GS 2.0.3: downloaded on first use into vidgen's cache folder
(:func:`cache_dir`), checked against its size and SHA-256 before it is used, never shipped in the
package. A project's ``soundfont: PATH`` uses any SF2 / SF3 file instead (relative to the project).
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vidgen.errors import VidgenError
from vidgen.fileio import replace_file

NAME = "GeneralUser GS 2.0.3"
FILE_NAME = "GeneralUser-GS.sf2"
URL = "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/main/GeneralUser-GS.sf2"
SIZE_BYTES = 32_319_396
SHA256 = "9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe"
HOME_PAGE = "https://www.schristiancollins.com/generaluser"
LICENCE = (
    "GeneralUser GS License v2.0: free to use without restriction for your own music, private or "
    "commercial; no attribution required (a credit is welcome)"
)
AUTHOR = "S. Christian Collins"
CREDIT = f"Music rendered with the GeneralUser GS SoundFont by {AUTHOR} ({HOME_PAGE})."
#: Environment variable that moves vidgen's cache folder.
CACHE_ENV = "VIDGEN_CACHE_DIR"
#: Seconds the download may wait for data before it fails.
TIMEOUT_SECONDS = 60.0
SUFFIXES = (".sf2", ".sf3")

#: Files already checked in this process: path -> (size, mtime_ns) when checked.
_checked: dict[Path, tuple[int, int]] = {}


def cache_dir() -> Path:
    """vidgen's cache folder: ``VIDGEN_CACHE_DIR``, else ``%LOCALAPPDATA%\\vidgen`` on Windows,
    ``~/Library/Caches/vidgen`` on macOS, ``$XDG_CACHE_HOME/vidgen`` or ``~/.cache/vidgen``
    elsewhere. Only returns the path."""
    if os.environ.get(CACHE_ENV):
        return Path(os.environ[CACHE_ENV])
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "vidgen"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "vidgen"
    base = Path(os.environ["XDG_CACHE_HOME"]) if os.environ.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return base / "vidgen"


def default_path() -> Path:
    """Where the default SoundFont is (or will be) kept; only returns the path."""
    return cache_dir() / "soundfonts" / FILE_NAME


def file_sha256(path: Path) -> str:
    """The SHA-256 of ``path``'s bytes, in hex."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


#: SHA-256 of SoundFont files hashed in this process: path -> (size, mtime_ns, sha256).
_hashes: dict[Path, tuple[int, int, str]] = {}


def content_sha256(path: Path) -> str:
    """The SHA-256 of a SoundFont file (the default one: :data:`SHA256` once checked; others
    hashed once per process while their size and mtime stay the same)."""
    if path == default_path():
        _check_default(path)
        return SHA256
    stat = path.stat()
    known = _hashes.get(path)
    if known is not None and known[:2] == (stat.st_size, stat.st_mtime_ns):
        return known[2]
    digest = file_sha256(path)
    _hashes[path] = (stat.st_size, stat.st_mtime_ns, digest)
    return digest


def _override_hint() -> str:
    return (
        f"or download an SF2 / SF3 SoundFont yourself (GeneralUser GS: {HOME_PAGE}) and set "
        "`soundfont: PATH` in video.yaml (relative to the project)"
    )


def mismatch_message(what: str, size_bytes: int, sha256: str | None) -> str:
    """The error for a file that is not the expected GeneralUser GS 2.0.3."""
    got = f"{size_bytes:,} bytes" + (f", sha256 {sha256}" if sha256 else "")
    return (
        f"{what} is not the expected {NAME} ({got}; expected {SIZE_BYTES:,} bytes, sha256 {SHA256}); "
        f"it was not used. The file at {URL} may have changed upstream: update schu-video-generator, {_override_hint()}"
    )


def _check_default(path: Path) -> None:
    """Raise :class:`VidgenError` unless ``path`` has the default SoundFont's size and hash (a
    file checked earlier in this process and unchanged since is not hashed again)."""
    stat = path.stat()
    stamp = (stat.st_size, stat.st_mtime_ns)
    if _checked.get(path) == stamp:
        return
    what = f"the cached SoundFont {path}"
    if stat.st_size != SIZE_BYTES:
        raise VidgenError(mismatch_message(what, stat.st_size, None) + "; `vidgen soundfont fetch --force` downloads it again")
    digest = file_sha256(path)
    if digest != SHA256:
        raise VidgenError(mismatch_message(what, stat.st_size, digest) + "; `vidgen soundfont fetch --force` downloads it again")
    _checked[path] = stamp


def fetch(force: bool = False, url: str | None = None, progress: Callable[[int], None] | None = None) -> Path:
    """The default SoundFont's path, downloading it first (from ``url``, default :data:`URL`)
    when it is missing (or with ``force``).

    The download goes to a temporary file next to it, is checked (size, SHA-256) and only then
    moved into place; a mismatch or a failed download leaves nothing behind and raises
    :class:`VidgenError`. ``progress`` receives the bytes read so far.
    """
    path = default_path()
    if path.is_file() and not force:
        _check_default(path)
        return path
    url = URL if url is None else url
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{FILE_NAME}.", suffix=".part", dir=path.parent)
    tmp = Path(tmp_name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as handle:
            done = 0

            def write(chunk: bytes) -> None:
                nonlocal done
                handle.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done)

            try:
                size_bytes = _stream(url, write)
            except VidgenError as exc:
                raise VidgenError(
                    f"cannot download the {NAME} SoundFont ({exc}); connect to the internet and run "
                    f"`vidgen soundfont fetch`, {_override_hint()}"
                ) from None
        if size_bytes != SIZE_BYTES or digest.hexdigest() != SHA256:
            shown = digest.hexdigest() if size_bytes <= SIZE_BYTES else None
            raise VidgenError(mismatch_message(f"the file downloaded from {url}", size_bytes, shown))
        replace_file(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    _check_default(path)
    return path


def _stream(url: str, write: Callable[[bytes], None]) -> int:
    from vidgen.httpapi import stream_get

    return stream_get(url, write, service="GitHub (raw.githubusercontent.com)", timeout=TIMEOUT_SECONDS, max_bytes=SIZE_BYTES)


def is_soundfont_file(path: Path) -> bool:
    """True if ``path`` starts like an SF2 / SF3 file (a RIFF ``sfbk`` header); reads 12 bytes."""
    try:
        with path.open("rb") as handle:
            head = handle.read(12)
    except OSError:
        return False
    return head[:4] == b"RIFF" and head[8:12] == b"sfbk"


def override_problem(setting: str, root: Path) -> str | None:
    """Why ``soundfont: setting`` cannot be used (missing, not an SF2 / SF3 file), or ``None``."""
    path = root / setting
    if not path.is_file():
        return f"{setting!r} does not exist (a SoundFont file: .sf2 or .sf3, relative to the project)"
    if path.suffix.lower() not in SUFFIXES or not is_soundfont_file(path):
        return f"{setting!r} is not an SF2 / SF3 SoundFont file"
    return None


def soundfont_problems(setting: str | None, root: Path) -> list[tuple[str, str]]:
    """``vidgen validate`` problems of the ``soundfont:`` key, as (location, message)."""
    problem = override_problem(setting, root) if setting else None
    return [] if problem is None else [("soundfont", problem)]


def resolve(setting: str | None, root: Path, download: bool = True) -> Path:
    """The SoundFont to play composed music with: ``soundfont: setting`` (relative to ``root``,
    the project folder), else the default one, downloaded first when ``download`` and missing.
    Raises :class:`VidgenError` for a bad override, a mismatched or (without ``download``)
    missing default file."""
    if setting:
        problem = override_problem(setting, root)
        if problem is not None:
            raise VidgenError(f"soundfont: {problem}")
        return (root / setting).resolve()
    path = default_path()
    if path.is_file():
        _check_default(path)
        return path
    if not download:
        raise VidgenError(f"the {NAME} SoundFont is not downloaded yet: run `vidgen soundfont fetch`, {_override_hint()}")
    return fetch()


@dataclass(frozen=True)
class SoundFontInfo:
    """What ``vidgen soundfont info`` shows."""

    path: Path
    origin: str
    """``default`` (the cached GeneralUser GS) or ``project`` (``soundfont:``)."""
    exists: bool
    size_bytes: int | None
    sha256: str | None
    matches: bool | None
    """The default file: whether it has the expected size and hash; ``None`` for an override."""
    licence: str


def info(setting: str | None, root: Path | None) -> SoundFontInfo:
    """The SoundFont a project (or, with ``root`` ``None``, any project without ``soundfont:``)
    would use, hashed if present; downloads nothing."""
    if setting and root is not None:
        path = (root / setting).resolve()
        origin, licence = "project", "the licence of your file (soundfont: in video.yaml)"
    else:
        path, origin, licence = default_path(), "default", LICENCE
    if not path.is_file():
        return SoundFontInfo(path, origin, False, None, None, None, licence)
    size_bytes = path.stat().st_size
    digest = file_sha256(path)
    matches = (size_bytes == SIZE_BYTES and digest == SHA256) if origin == "default" else None
    return SoundFontInfo(path, origin, True, size_bytes, digest, matches, licence)
