"""Exports from the studio (DESIGN.md §94.15): a version as its score file (YAML), as audio (WAV or
MP3: the piece once, N loops or N seconds, at a video's level or a listening level) for the
browser to download, or saved into the project's ``assets/music/<name>.yaml`` as a project piece
(``music: <name>``) with the Step 188 name rule.

Files are written only into the session's ``exports/`` folder (served from there by name, the
browser saves the download where the person chooses) and, when asked, into the project's
``assets/music/``. Audio is rendered by :func:`vidgen.studio.render_music_score` itself, the
samples a video plays.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.fileio import replace_file, write_bytes_atomic, write_text_atomic

#: Formats a version exports as.
FORMATS = ("yaml", "wav", "mp3")
#: How long the audio is: the piece once (a loop's one pass, a one-pass piece with its ending),
#: N times round the loop, or N seconds (looped as a video loops it, faded out at the end).
LENGTHS = ("once", "loops", "seconds")
MAX_LOOPS = 64
#: The longest export (s; N loops too): a score is at most 10 minutes, and a 30-minute export
#: took more than 3 GB before Step 201 (a video loops its music by itself anyway).
MAX_SECONDS = 600
#: The fade-out at the end of an N-seconds export (s; shorter for a short one).
FADE_OUT_SECONDS = 2.0
#: Levels: name -> (LUFS, words). A video's music level (schu-video-generator plays it at volume 0), or the
#: studio's listening level (the Listen page's -16 LUFS), its true peak kept at most -1 dBTP.
LEVELS: dict[str, tuple[float, str]] = {
    "video": (-28.0, "video level: −28 LUFS, as schu-video-generator plays music at volume 0 (for a video or another editor)"),
    "listening": (-16.0, "listening level: −16 LUFS, as the studio plays it (peaks kept under −1 dBTP)"),
}
LISTENING_PEAK_DBTP = -1.0
#: A file the server sends from the session's exports: a name, then the format's suffix.
EXPORT_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}\.(yaml|wav|mp3)\Z")
#: A project piece's name (``assets/music/<name>.yaml``, ``music: <name>``).
PIECE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\Z")
#: Names Windows keeps for devices (``con.yaml`` would be the console, not a file).
WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])\Z")


def slug(text: str) -> str:
    """A file-name-safe form of a title (``Momentum (template)`` → ``momentum-template``)."""
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    return out or "piece"


def export_audio(score: Any, length: str, count: float | None, level: str) -> tuple[np.ndarray, dict[str, Any]]:
    """The audio of ``score`` to export (float32 ``(n, 2)``) and its facts: ``length`` once,
    ``count`` loops or ``count`` seconds; at ``level`` (:data:`LEVELS`)."""
    from vidgen import loudness
    from vidgen.sfx import RATE
    from vidgen.studio import render_music_score

    if length not in LENGTHS:
        raise VidgenError(f"export: length is one of {', '.join(LENGTHS)}, got {length!r}")
    if level not in LEVELS:
        raise VidgenError(f"export: level is one of {', '.join(LEVELS)}, got {level!r}")
    if length == "loops":
        if not score.loop:
            raise VidgenError("export: this piece plays once (loop: false), so it has no loops: export it once or as N seconds")
        if not isinstance(count, (int, float)) or isinstance(count, bool) or int(count) != count or not 1 <= count <= MAX_LOOPS:
            raise VidgenError(f"export: loops is a whole number from 1 to {MAX_LOOPS}")
        if count * score.samples > MAX_SECONDS * RATE:
            raise VidgenError(f"export: {int(count)} loops of {score.samples / RATE:.0f} s is longer than {MAX_SECONDS // 60} minutes; export fewer loops")
    elif length == "seconds":
        if not isinstance(count, (int, float)) or isinstance(count, bool) or not math.isfinite(count) or not 1 <= count <= MAX_SECONDS:
            raise VidgenError(f"export: seconds is a number from 1 to {MAX_SECONDS}")
    warnings: list[str] = []
    piece = np.asarray(render_music_score(score, warnings), dtype=np.float64)
    once = len(piece)
    # the export is made and measured block by block (a long one never holds more than one
    # float32 copy): the same samples as tiling the whole piece, fading and scaling it at once
    fade = 0
    if length == "loops":
        n = int(count) * once
    elif length == "seconds":
        n = int(round(count * RATE))
        cut = score.loop or n < once  # the music goes on past the end: fade it out
        fade = min(int(FADE_OUT_SECONDS * RATE), n // 4) if cut else 0
    else:
        n = once
    ramp = np.linspace(1.0, 0.0, fade) if fade > 0 else None

    def read(a: int, b: int) -> np.ndarray:
        """Samples ``a .. b`` of the export before its gain."""
        at = np.arange(a, b)
        if score.loop:
            part = piece[at % once]
        else:
            part = np.zeros((b - a, 2))
            inside = at < once
            part[inside] = piece[at[inside]]
        if ramp is not None and b > n - fade:
            first = max(a, n - fade)
            part[first - a :] *= ramp[first - (n - fade) : b - (n - fade)][:, None]
        return part

    target, words = LEVELS[level]
    gain = 10 ** ((target - (-28.0)) / 20)
    if level == "listening":
        peak = 0.0
        for lo, hi, ext in loudness.blocks(n, read):
            peak = max(peak, float(loudness.peak_envelope(ext)[loudness.MARGIN : loudness.MARGIN + hi - lo].max()))
        peak *= gain
        limit = 10 ** (LISTENING_PEAK_DBTP / 20)
        if peak > limit:
            gain *= limit / peak
    audio = np.empty((n, 2), dtype=np.float32)
    for lo in range(0, n, loudness.BLOCK):
        hi = min(n, lo + loudness.BLOCK)
        audio[lo:hi] = np.clip(read(lo, hi) * gain, -1.0, 1.0)
    meter = loudness.measure(len(audio), lambda a, b: audio[a:b])
    facts = {
        "seconds": round(len(audio) / RATE, 3),
        "length": length,
        "count": count,
        "level": level,
        "level_words": words,
        "loudness": round(meter.integrated, 2),
        "true_peak": round(meter.true_peak, 2),
        "warnings": warnings,
    }
    return audio, facts


def file_name(title: str, version: int, fmt: str, length: str = "once", count: float | None = None, level: str = "video") -> str:
    """The exported file's name: ``<title>-v<N>[-<length>-<level>].<fmt>``."""
    base = f"{slug(title)}-v{version}"
    if fmt == "yaml":
        return f"{base}.yaml"
    what = "once" if length == "once" else (f"{int(count or 0)}loops" if length == "loops" else f"{count:g}s".replace(".", "_"))
    return f"{base}-{what}-{level}.{fmt}"


def write_export(folder: Path, name: str, fmt: str, text: str | None = None, audio: np.ndarray | None = None) -> Path:
    """Write an export into ``folder`` (the session's ``exports/``) atomically."""
    from vidgen.sfx import wav_bytes

    if not EXPORT_NAME.match(name):
        raise VidgenError(f"export: not a file name the studio writes: {name!r}")
    target = folder / name
    if fmt == "yaml":
        assert text is not None
        write_text_atomic(target, text)
    elif fmt == "wav":
        assert audio is not None
        write_bytes_atomic(target, wav_bytes(audio))
    else:
        from vidgen.listen import write_mp3

        assert audio is not None
        partial = folder / f".partial-{name}"
        try:
            write_mp3(audio, partial)
            replace_file(partial, target)  # retried while the browser still holds the last download (Windows)
        finally:
            partial.unlink(missing_ok=True)
    return target


def _inside(folder: Path, root: Path) -> bool:
    """Whether ``folder`` (or, while it does not exist, its nearest existing parent) is inside
    ``root`` once links are followed."""
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe.resolve().is_relative_to(root.resolve())


def save_to_project(root: Path | None, name: str, text: str, overwrite: bool = False) -> dict[str, Any]:
    """Save score ``text`` as the project piece ``assets/music/<name>.yaml`` (played with
    ``music: <name>``). Refused: no project, a name that is not a plain name, a built-in bed's
    name (Step 188: ``music: <bed>`` would be ambiguous). An existing piece of that name is
    overwritten only with ``overwrite``; else ``{exists: true, path}`` and nothing is written."""
    from vidgen.music import BUILTIN_BEDS, PROJECT_MUSIC_DIR

    if root is None:
        raise VidgenError(
            "save to project: the studio was started without a project. Start it in the project's folder (the one with video.yaml), "
            "or give it: vidgen studio path/to/project — then pieces are saved to its assets/music/. Or export the YAML and put it there yourself."
        )
    name = name.strip()
    if not PIECE_NAME.match(name):
        raise VidgenError(f"save to project: '{name}' is not a piece name: use lower-case letters, digits, '_' or '-' (e.g. my_theme), up to 64")
    if WINDOWS_RESERVED.match(name):
        raise VidgenError(f"save to project: '{name}' is a name Windows keeps for a device; pick another, e.g. {name}_theme")
    if name in BUILTIN_BEDS:
        raise VidgenError(
            f"save to project: '{name}' is a built-in bed's name; a piece with it would make music: {name} ambiguous (schu-video-generator reports that as a "
            f"problem). Pick another name, e.g. {name}_mine"
        )
    folder = root / PROJECT_MUSIC_DIR
    existing = next((folder / f"{name}{suffix}" for suffix in (".yaml", ".yml") if (folder / f"{name}{suffix}").is_file()), None)
    target = existing or folder / f"{name}.yaml"
    if not _inside(target.parent, root):
        raise VidgenError(f"save to project: {PROJECT_MUSIC_DIR.as_posix()} is outside the project; not writing there")
    rel = target.relative_to(root).as_posix()
    if existing is not None and not overwrite:
        return {"saved": False, "exists": True, "path": rel, "name": name, "message": f"{rel} exists: overwrite it?"}
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(target, text)
    return {"saved": True, "exists": existing is not None, "path": rel, "file": str(target), "name": name, "snippet": f"music: {name}"}
