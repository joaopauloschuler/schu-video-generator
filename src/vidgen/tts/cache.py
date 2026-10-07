"""The narration audio cache: ``<audio_dir>/<beat_id>.mp3`` + ``<beat_id>.hash`` (DESIGN.md §7).

Nothing here needs an API key or the network.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic
from vidgen.project import Project

if TYPE_CHECKING:
    from vidgen.tts import TTSProvider

AudioState = Literal["ok", "stale", "missing"]
STATES: tuple[AudioState, ...] = ("ok", "stale", "missing")


@dataclass(frozen=True)
class BeatAudioStatus:
    """Audio cache state of one beat.

    ``state`` is ``"ok"`` (MP3 exists and its hash matches the current spoken text — the beat's
    text with the project's pronunciation applied — and voice),
    ``"stale"`` (MP3 exists but its hash is missing or outdated) or ``"missing"`` (no MP3).
    """

    scene_id: str
    beat_id: str
    text: str
    state: AudioState
    mp3: Path
    hash_file: Path


def mp3_path(audio_dir: Path, beat_id: str) -> Path:
    """``<audio_dir>/<beat_id>.mp3``."""
    return audio_dir / f"{beat_id}.mp3"


def hash_path(audio_dir: Path, beat_id: str) -> Path:
    """``<audio_dir>/<beat_id>.hash``."""
    return audio_dir / f"{beat_id}.hash"


def read_hash(path: Path) -> str | None:
    """The stored hash (stripped), or ``None`` if the file is missing or unreadable."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def is_up_to_date(provider: TTSProvider, audio_dir: Path, beat_id: str, text: str) -> bool:
    """True if ``audio_dir`` holds an MP3 for ``beat_id`` whose hash matches ``text`` (the
    spoken text, see :meth:`vidgen.project.Project.spoken_texts`)."""
    stored = read_hash(hash_path(audio_dir, beat_id))
    return mp3_path(audio_dir, beat_id).is_file() and stored is not None and provider.matches(text, stored)


def audio_status(project: Project, provider: TTSProvider | None = None) -> list[BeatAudioStatus]:
    """State of every beat's audio in ``project.audio_dir``, in video order. No API key needed."""
    if provider is None:
        from vidgen.tts import get_provider

        provider = get_provider(project.config.voice)
    audio_dir = project.audio_dir
    spoken = project.spoken_texts()  # the hash covers what the TTS says (pronunciation applied)
    result = []
    for scene, beat in project.beats():
        mp3 = mp3_path(audio_dir, beat.id)
        if not mp3.is_file():
            state: AudioState = "missing"
        elif is_up_to_date(provider, audio_dir, beat.id, spoken[beat.id]):
            state = "ok"
        else:
            state = "stale"
        result.append(BeatAudioStatus(scene.id, beat.id, beat.text, state, mp3, hash_path(audio_dir, beat.id)))
    return result


def format_audio_summary(statuses: Iterable[BeatAudioStatus]) -> str:
    """``"18 ok, 2 stale, 1 missing"``."""
    counts = Counter(s.state for s in statuses)
    return ", ".join(f"{counts[state]} {state}" for state in STATES)


def _beat_ids_using(audio_dir: Path, project: Project) -> set[str]:
    """Beat ids of the base config and of every variant whose audio lives in ``audio_dir``."""
    ids: set[str] = set()
    base = project if project.variant is None else Project.load(project.config_file)
    candidates = [base]
    for name in base.config.variants:
        try:
            candidates.append(Project.load(project.config_file, variant=name))
        except VidgenError:
            continue  # an invalid variant is reported by `vidgen validate`
    for candidate in candidates:
        if candidate.audio_dir == audio_dir:
            ids.update(beat.id for _, beat in candidate.beats())
    return ids


def orphaned_audio(project: Project) -> list[Path]:
    """MP3s in ``project.audio_dir`` whose beat id no config sharing that folder uses (sorted).

    They are only reported, never deleted.
    """
    audio_dir = project.audio_dir
    if not audio_dir.is_dir():
        return []
    known = {beat.id for _, beat in project.beats()} | _beat_ids_using(audio_dir, project)
    return sorted(p for p in audio_dir.glob("*.mp3") if p.is_file() and p.stem not in known)


def atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to a temporary file next to ``path``, then replace ``path`` with it.

    ``path`` is either left untouched or fully written (see :mod:`vidgen.fileio`).
    """
    write_bytes_atomic(path, data)
