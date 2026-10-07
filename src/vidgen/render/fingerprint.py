"""Scene fingerprints: has anything that a scene's render depends on changed since it was made?

The worker records :func:`scene_fingerprint` in the scene's timings (``render.fingerprint``);
``vidgen storyboard`` reuses a scene's stills only while the fingerprint still matches.

What counts: the scene's config (type, params, beats; not ``lint_ignore``), every other config
section except ``scenes``, ``variants`` and ``lint`` (theme, narration, format...) but including
``lint.rules.min_font.min_size`` (``vidgen.regions.readable_size`` lays text out by it), the narration MP3s of the scene's
beats (size and modification time), the source of vidgen itself (with its bundled fonts and
icons) and of
the project's extension folders (file contents), and the files under ``<project>/assets`` (size and modification time).
With overlays, also what the planned timeline reads from every scene (``vidgen.videoplan``).
Files a scene reads from elsewhere are not tracked (``--force`` renders again).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from vidgen import __version__
from vidgen.project import Project

#: Bumped when the fingerprint's inputs change (old renders then count as stale).
FINGERPRINT_VERSION = 1

_PACKAGE_DIR = Path(__file__).resolve().parent.parent

#: vidgen modules that cannot change a scene's pixels or timing (commands, output documents,
#: contact sheets, TTS); every other module, including new ones, is part of the fingerprint.
NOT_RENDER_INPUTS: frozenset[str] = frozenset(
    {
        "__main__.py", "cli.py", "describe.py", "iconlist.py", "jsonout.py", "lint", "schema.py", "sheets.py", "storyboard.py",
        "render/fingerprint.py", "render/pipeline.py", "render/ffmpeg.py", "subtitles.py", "themelist.py", "tts",
    }
)


def _files(folder: Path, suffix: str | None = None) -> Iterator[Path]:
    """Regular files under ``folder`` (sorted; ``__pycache__`` skipped), optionally by suffix."""
    if not folder.is_dir():
        return
    for path in sorted(folder.rglob("*")):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        if suffix is None or path.suffix == suffix:
            yield path


def _contents_digest(paths: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _render_input(path: Path) -> bool:
    rel = path.relative_to(_PACKAGE_DIR).as_posix()
    return rel not in NOT_RENDER_INPUTS and rel.split("/", 1)[0] not in NOT_RENDER_INPUTS


@lru_cache(maxsize=1)
def vidgen_source_digest() -> str:
    """Digest of vidgen's own Python source that renders depend on (built-in scenes, helpers,
    the scene base, the worker...; not :data:`NOT_RENDER_INPUTS`), of its bundled fonts and of
    its vendored icons (SVGs and manifest)."""
    paths = [p for p in _files(_PACKAGE_DIR, ".py") if _render_input(p)]
    paths += [p for p in _files(_PACKAGE_DIR / "data" / "fonts") if p.suffix in (".ttf", ".otf")]
    paths += [p for p in _files(_PACKAGE_DIR / "data" / "icons") if p.suffix in (".svg", ".json")]
    return _contents_digest(paths, _PACKAGE_DIR)


def _stat(path: Path) -> list[int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def _overlay_inputs(project: Project) -> Any:
    """What overlays read from the other scenes (their planned timeline: types, durations, beat
    texts and MP3s, chapter titles; DESIGN.md §41); ``None`` without overlays."""
    cfg = project.config
    if not cfg.overlays and not any(isinstance(s.overlays, dict) for s in cfg.scenes):
        return None
    return [
        {
            "id": s.id,
            "type": s.type,
            "duration": s.duration,
            "title": s.params.get("title") if s.type == "chapter" else None,
            "overlays": s.overlays,
            "beats": [[b.id, b.text, _stat(project.audio_dir / f"{b.id}.mp3")] for b in s.beats],
        }
        for s in cfg.scenes
    ]


def scene_fingerprint(project: Project, scene_id: str) -> str:
    """A hex digest of everything (that vidgen knows of) the render of ``scene_id`` depends on."""
    spec = project.scene(scene_id)
    # Lint settings cannot change pixels or timing (except the readable text size scenes use):
    # editing them must not make renders stale.
    config = project.config.model_dump(mode="json", exclude={"scenes", "variants", "lint"})
    assets = project.root / "assets"
    data: dict[str, Any] = {
        "fingerprint": FINGERPRINT_VERSION,
        "vidgen": __version__,
        "vidgen_source": vidgen_source_digest(),
        "config": config,
        "readable": project.config.lint.rules.min_font.min_size,
        "scene": spec.model_dump(mode="json", exclude={"lint_ignore"}),
        "audio": {beat.id: _stat(project.audio_dir / f"{beat.id}.mp3") for beat in spec.beats},
        "extensions": [_contents_digest(_files(folder, ".py"), folder) for folder in project.extension_dirs],
        "assets": {path.relative_to(assets).as_posix(): _stat(path) for path in _files(assets)},
        "overlays": _overlay_inputs(project),
    }
    text = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
