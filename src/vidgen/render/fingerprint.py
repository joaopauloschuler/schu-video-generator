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
With transitions, the one into the next scene (it changes how the scene ends, DESIGN.md §49).
With ``carry`` (DESIGN.md §50): what the next scene carries out of the scene (kept on screen at
its end), and for a scene that carries objects in, the fingerprint of the scene before.
Not the music and the final mix (``music``, ``audio``, a scene's ``music``): they are applied when
the video is joined; nor ``chapters``, ``metadata`` and ``thumbnail`` (outputs made after it).
Files a scene reads from elsewhere are not tracked (``--force`` renders again).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from vidgen import __version__, carry
from vidgen.project import Project

#: Bumped when the fingerprint's inputs change (old renders then count as stale).
FINGERPRINT_VERSION = 1

_PACKAGE_DIR = Path(__file__).resolve().parent.parent

#: vidgen modules that cannot change a scene's pixels or timing (commands, output documents,
#: contact sheets, TTS, sound synthesis); every other module, including new ones, is part of the
#: fingerprint.
NOT_RENDER_INPUTS: frozenset[str] = frozenset(
    {
        "__main__.py", "cli.py", "describe.py", "iconlist.py", "jsonout.py", "lint", "schema.py", "sheets.py", "storyboard.py",
        "render/fingerprint.py", "render/pipeline.py", "render/ffmpeg.py", "sfx.py", "subtitles.py", "themelist.py", "tts",
        "loudness.py", "mix.py", "music.py", "thumbnail.py", "export.py", "translation.py", "deck.py", "slides.py",
        "slides_pdf.py",
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
    texts and MP3s, chapters; DESIGN.md §41-42), the beats' stored alignments (captions, §43),
    their voices, the named voices and the subtitles settings (captions' speakers, §46);
    ``None`` without overlays."""
    cfg = project.config
    if not cfg.overlays and not any(isinstance(s.overlays, dict) for s in cfg.scenes):
        return None
    say = project.pronunciation.say  # captions time the written words by their spoken form (§45)
    speakers = project.voice_names()  # captions name / colour speakers (§46)
    scenes = [
        {
            "id": s.id,
            "type": s.type,
            "duration": s.duration,
            "title": s.params.get("title") if s.type == "chapter" else None,
            "number": s.params.get("number") if s.type == "chapter" else None,
            "chapter": s.model_dump(mode="json")["chapter"],
            "overlays": s.overlays,
            "transition": s.model_dump(mode="json")["transition"],  # crossfades move later scenes (§49)
            "beats": [
                [
                    b.id, b.text, say(b.text), speakers[b.id],
                    _stat(project.audio_dir / f"{b.id}.mp3"), _stat(project.audio_dir / f"{b.id}.align.json"),
                ]
                for b in s.beats
            ],
        }
        for s in cfg.scenes
    ]
    return {"scenes": scenes, "voices": cfg.model_dump(mode="json", include={"voices", "subtitles"})}


def _next_transition(project: Project, scene_id: str) -> Any:
    """The transition into the scene after ``scene_id`` with what limits its length (that
    scene's duration, beats and MP3s); a cut alone, and ``None`` for the last scene."""
    from vidgen.transitions import effective

    config = project.config
    ids = [s.id for s in config.scenes]
    i = ids.index(scene_id)
    if i + 1 >= len(ids):
        return None
    t = effective(config, i + 1)
    if t.type == "cut":
        return "cut"
    after = config.scenes[i + 1]
    # a crossfade's or fade's length is limited by the next scene's own length (its beats)
    return [t.model_dump(mode="json"), after.duration, [[b.id, _stat(project.audio_dir / f"{b.id}.mp3"), b.text] for b in after.beats]]


def scene_fingerprint(project: Project, scene_id: str) -> str:
    """A hex digest of everything (that vidgen knows of) the render of ``scene_id`` depends on."""
    spec = project.scene(scene_id)
    # Lint settings cannot change pixels or timing (except the readable text size scenes use):
    # editing them must not make renders stale.
    # The pronunciation changes only the audio (tracked below) and, with overlays, the captions'
    # word times (the spoken texts are in "overlays"); editing it must not re-render every scene.
    # Named voices and subtitle settings change only audio and, with overlays, captions (§46).
    # Music and the final mix (§48) are added when the video is joined: no pixels, no timing.
    # So are the MP4's chapters and tags and the YouTube chapter list (§52), and the thumbnail (§53).
    # A translation file's texts are already in the config (§54); its path changes nothing.
    excluded = {
        "scenes", "variants", "lint", "pronunciation", "pronunciation_file", "voices", "subtitles", "music", "audio",
        "chapters", "metadata", "thumbnail", "translations",
    }
    config = project.config.model_dump(mode="json", exclude=excluded)
    assets = project.root / "assets"
    data: dict[str, Any] = {
        "fingerprint": FINGERPRINT_VERSION,
        "vidgen": __version__,
        "vidgen_source": vidgen_source_digest(),
        "config": config,
        "readable": project.config.lint.rules.min_font.min_size,
        # A scene's `chapter:` only matters to overlays (in "overlays" below when there are any).
        "scene": spec.model_dump(mode="json", exclude={"lint_ignore", "chapter", "music", "carry"}),
        "audio": {beat.id: _stat(project.audio_dir / f"{beat.id}.mp3") for beat in spec.beats},
        "extensions": [_contents_digest(_files(folder, ".py"), folder) for folder in project.extension_dirs],
        "assets": {path.relative_to(assets).as_posix(): _stat(path) for path in _files(assets)},
        "overlays": _overlay_inputs(project),
        # the transition out of the scene changes its end: held instead of faded, faded to a
        # colour, or held longer (DESIGN.md §49)
        "next_transition": _next_transition(project, scene_id),
    }
    # continuity (DESIGN.md §50): what the next scene carries changes how this one fades out;
    # what this scene carries in is the end of the scene before (its render's inputs)
    carried_out = carry.carried_out(project.config, scene_id)
    if carried_out:
        data["next_carry"] = [str(e) for e in carried_out]
    before = carry.carried_from(project.config).get(scene_id)
    if before is not None:
        data["carry"] = [str(e) for e in spec.carry]
        data["carry_from"] = scene_fingerprint(project, before)
    text = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
