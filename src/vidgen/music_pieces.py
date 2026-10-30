"""Project pieces: score files (DESIGN.md §93) under the project's ``assets/music`` played as
background music like the built-in beds (§93.10).

``music: my_theme`` plays ``assets/music/my_theme.yaml`` (or ``.yml``; a piece in a sub-folder is
``themes/my_theme``); ``source: assets/music/my_theme.yaml`` (any ``.yaml`` / ``.yml`` path under
the project) names the file itself. A name that is both a built-in bed and a project piece is a
problem (rename the piece, or use the path form). The piece is rendered by :mod:`vidgen.studio`
when the video's audio is mixed and the render is kept in ``build/music`` under a key of the
file's bytes, :data:`PIECE_RENDER_VERSION`, schu-video-generator's version and the sample rate, so it is made
once. A ``loop: true`` piece loops seamlessly (like a bed); a ``loop: false`` piece plays once,
with its ending, and the cue's fades apply.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.errors import VidgenError
from vidgen.music import BUILTIN_BEDS, MUSIC_LEVEL, PROJECT_MUSIC_DIR, RATE

if TYPE_CHECKING:
    from vidgen.config import MusicCue, VideoConfig
    from vidgen.studio import MusicScore

log = logging.getLogger("vidgen.music")

#: File suffixes of score files.
SCORE_SUFFIXES = (".yaml", ".yml")
#: Bumped when the studio's rendering changes, so cached renders of project pieces are made again.
PIECE_RENDER_VERSION = 1


def is_score_source(source: str, root: Path | None = None) -> bool:
    """Whether a cue's ``source`` names a score file: a ``.yaml`` / ``.yml`` path, or a name
    without a suffix that is not a built-in bed (and, with ``root``, not a file there: such a
    file stays a music file, as before)."""
    suffix = PurePosixPath(source).suffix.lower()
    if suffix in SCORE_SUFFIXES:
        return True
    if suffix or source in BUILTIN_BEDS:
        return False
    return root is None or not (root / source).is_file()


def project_pieces(root: Path | None) -> dict[str, Path]:
    """The project's pieces: name (the path under ``assets/music`` without its suffix, ``/``
    between folders) -> file, sorted by name (``.yaml`` before ``.yml`` of the same name)."""
    folder = None if root is None else root / PROJECT_MUSIC_DIR
    if folder is None or not folder.is_dir():
        return {}
    found: dict[str, Path] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in SCORE_SUFFIXES:
            found.setdefault(path.relative_to(folder).with_suffix("").as_posix(), path)
    return dict(sorted(found.items()))


def _suggest(source: str, root: Path | None) -> str:
    known = [*BUILTIN_BEDS, *project_pieces(root)]
    close = difflib.get_close_matches(source.lower(), known, n=1, cutoff=0.7)
    return f"; did you mean '{close[0]}'?" if close else ""


def piece_path(source: str, root: Path) -> Path:
    """The score file a ``source`` names (:func:`is_score_source`); :class:`VidgenError` when
    there is none (with did-you-mean across the beds and the project's pieces)."""
    if PurePosixPath(source).suffix.lower() in SCORE_SUFFIXES:
        path = root / source
        if not path.is_file():
            raise VidgenError(f"score file not found: {source} (looked for {path})")
        return path
    if ".." in PurePosixPath(source).parts:
        raise VidgenError(f"a piece's name may not contain '..': {source}")
    for suffix in SCORE_SUFFIXES:
        path = root / PROJECT_MUSIC_DIR / f"{source}{suffix}"
        if path.is_file():
            return path
    pieces = ", ".join(project_pieces(root)) or "none"
    raise VidgenError(
        f"neither a built-in bed nor a project piece: {source} (looked for {(PROJECT_MUSIC_DIR / source).as_posix()}.yaml)"
        f"{_suggest(source, root)}; built-in beds: {', '.join(BUILTIN_BEDS)}; project pieces: {pieces}; "
        "or a file, or compose: {mood: ...} (vidgen list-music)"
    )


def bed_conflict(source: str, root: Path | None) -> str | None:
    """The problem when ``source`` is a built-in bed's name and the project has a piece of that
    name too (which one plays would be a guess), else ``None``."""
    if root is None or source not in BUILTIN_BEDS:
        return None
    path = project_pieces(root).get(source)
    if path is None:
        return None
    rel = path.relative_to(root).as_posix()
    return (
        f"'{source}' is a built-in bed and also the project piece {rel}: rename the piece (e.g. {source}_mine) or write "
        f"source: {rel} to play the piece (source: {source} plays the bed)"
    )


def music_source(name: str, root: Path) -> tuple[str, Path | None]:
    """What ``vidgen music render`` / ``check`` play for ``name`` (a path or a name):
    ``("file", path)`` an existing file (a score file or audio); ``("score bed", path)`` the
    score file of a bed written as one (``tidewater``, ``skyline``, ``time_of_flight``);``("bed", None)`` another
    built-in bed (its own code: the audio); ``("piece", path)`` a project piece under ``root``
    (``assets/music/<name>.yaml``). :class:`VidgenError` with did-you-mean otherwise, or when the
    name is both a bed and a project piece."""
    from vidgen.studio.templates import TEMPLATE_DIR

    path = Path(name)
    if path.is_file():
        return "file", path
    if name in BUILTIN_BEDS:
        piece = project_pieces(root).get(name)
        if piece is not None:
            rel = piece.relative_to(root).as_posix()
            raise VidgenError(f"'{name}' is a built-in bed and also the project piece {rel}: give the path ({rel}) for the piece, or rename it "
                              f"(e.g. {name}_mine)")
        return ("score bed", TEMPLATE_DIR / f"{name}.yaml") if BUILTIN_BEDS[name].score else ("bed", None)
    if path.suffix:
        raise VidgenError(f"file not found: {name} (looked for {path.resolve()})")
    return "piece", piece_path(name, root)


def cue_score(cue: MusicCue, root: Path) -> Path | None:
    """The score file a cue plays: its project piece, or a score bed's own file (``tidewater``,
    ``skyline``, ``time_of_flight``); ``None`` for other beds, audio files and composed music (or a missing piece)."""
    from vidgen.music import source_kind
    from vidgen.studio.templates import TEMPLATE_DIR

    if cue.source is None:
        return None
    kind = source_kind(cue, root)
    if kind == "bed":
        return TEMPLATE_DIR / f"{cue.source}.yaml" if BUILTIN_BEDS[cue.source].score else None
    if kind != "score":
        return None
    try:
        return piece_path(cue.source, root)
    except VidgenError:
        return None


def section_start(cue: MusicCue, root: Path) -> float:
    """Seconds into the piece where the cue's ``section`` starts (0 without one);
    :class:`VidgenError` when the cue cannot start at a section or the piece has no such section."""
    if cue.section is None:
        return 0.0
    problem = section_problem(cue, root)
    if problem is not None:
        raise VidgenError(f"music.section: {problem}")
    from vidgen.studio import load_music_score

    path = cue_score(cue, root)
    assert path is not None
    score = load_music_score(path)
    section = next(s for s in score.sections if s.name == cue.section)
    return score.section_start(section) / RATE


def section_problem(cue: MusicCue, root: Path) -> str | None:
    """What is wrong with the cue's ``section`` (``None``: nothing, or no section): only a score
    (a project piece or a score bed) has sections, and the piece must have that one."""
    from vidgen.studio import load_music_score

    if cue.section is None:
        return None
    path = cue_score(cue, root)
    if path is None:
        score_beds = ", ".join(n for n, b in BUILTIN_BEDS.items() if b.score)
        return (f"'{cue.section}': only a score file has sections — a project piece (assets/music/*.yaml) or a score bed ({score_beds}); "
                f"{cue.label} has none (use start: seconds)")
    try:
        score = load_music_score(path)
    except VidgenError:
        return None  # the piece's own problems are reported on its source
    names = [s.name for s in score.sections]
    if cue.section not in names:
        close = difflib.get_close_matches(cue.section, names, n=1, cutoff=0.6)
        guess = f"; did you mean '{close[0]}'?" if close else ""
        return f"{cue.label} has no section '{cue.section}'{guess} (sections: {', '.join(names)})"
    return None


def score_problems(path: Path) -> list[str]:
    """The problems of the score file at ``path`` as ``where: what`` lines (empty if it reads)."""
    from vidgen.studio import load_music_score

    try:
        load_music_score(path)
    except VidgenError as exc:
        return _problem_lines(exc)
    return []


def _problem_lines(exc: VidgenError) -> list[str]:
    """A score file's error as its ``where: what`` lines (the whole message when it has none)."""
    lines = str(exc).splitlines()
    return [line.strip()[2:] for line in lines[1:] if line.strip().startswith("- ")] or lines


def played_pieces(config: VideoConfig, root: Path) -> list[tuple[int, Path]]:
    """``(cue index, score file)`` of the ``music:`` cues that play a project piece (cues whose
    piece is missing are left out: :func:`vidgen.music.config_problems` reports them)."""
    from vidgen.music import source_kind

    out = []
    for k, cue in enumerate(config.music_cues):
        if cue.source is not None and source_kind(cue, root) == "score":
            try:
                out.append((k, piece_path(cue.source, root)))
            except VidgenError:
                continue
    return out


def piece_warnings(config: VideoConfig, root: Path) -> list[str]:
    """``vidgen validate`` warnings: the project's pieces the video does not play whose score
    file has problems (the played ones are problems of their cue)."""
    played = {path.resolve() for _, path in played_pieces(config, root)}
    out = []
    for path in project_pieces(root).values():
        if path.resolve() in played:
            continue
        problems = score_problems(path)
        if problems:
            more = f" (+{len(problems) - 1} more: vidgen music render {path.relative_to(root).as_posix()} lists them)" if len(problems) > 1 else ""
            out.append(f"music: {path.relative_to(root).as_posix()} (a project piece this video does not play): {problems[0]}{more}")
    return out


def piece_key(path: Path) -> str:
    """The cache key (SHA-256 hex) of a piece's render: the file's bytes,
    :data:`PIECE_RENDER_VERSION`, schu-video-generator's version and the sample rate."""
    from vidgen import __version__

    data = {
        "score": hashlib.sha256(path.read_bytes()).hexdigest(),
        "renderer": PIECE_RENDER_VERSION,
        "vidgen": __version__,
        "rate": RATE,
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def _write_atomic(path: Path, write: Any) -> None:
    from vidgen.fileio import replace_file

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".piece-", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        write(tmp)
        replace_file(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@lru_cache(maxsize=4)
def _rendered(path: Path, key: str, cache_dir: Path | None) -> np.ndarray:
    from vidgen.studio import load_music_score, render_music_score

    cached = None if cache_dir is None else cache_dir / f"piece-{key}.npy"
    if cached is not None and cached.is_file():
        try:
            data = np.load(cached, allow_pickle=False)
            if data.ndim == 2 and data.shape[1] == 2 and data.dtype == np.float32:
                data.setflags(write=False)
                return data
        except (OSError, ValueError):
            pass  # a damaged cache file: render again
    notes: list[str] = []
    data = render_music_score(load_music_score(path), notes)
    for note in notes:
        log.warning("music: %s: %s", path.name, note)
    if cached is not None:
        _write_atomic(cached, lambda tmp: np.save(tmp, data, allow_pickle=False))
    return data


def piece_audio(path: Path, cache_dir: Path | None = None) -> tuple[np.ndarray, MusicScore]:
    """The piece at ``path`` rendered (float32 stereo ``(n, 2)`` at :data:`RATE`, at the music
    level, read-only; a loop exactly its bars, a one-shot with its ending) and its score. With
    ``cache_dir`` the render is kept there as ``piece-<key>.npy`` and reused."""
    from vidgen.studio import load_music_score

    score = load_music_score(path)
    return _rendered(path.resolve(), piece_key(path), cache_dir), score


def piece_entry(name: str, path: Path, root: Path) -> dict[str, Any]:
    """A project piece described for ``vidgen list-music`` (the score is read, not rendered: a
    piece always plays at the music level)."""
    from vidgen.studio import load_music_score, score_outline

    rel = path.relative_to(root).as_posix()
    base = {"name": name, "origin": "score", "path": rel, "use": None, "duration": None, "channels": 2, "preview": None}
    try:
        score = load_music_score(path)
    except VidgenError as exc:
        return {**base, "title": None, "description": None, "tempo": None, "key": None, "time": None, "bars": None, "chords": None,
                "loop": None, "loop_seconds": None, "sections": [], "loudness": None, "problems": _problem_lines(exc)}
    outline = score_outline(score)
    chords = list(dict.fromkeys(c for s in outline["sections"] for c in s["chords"]))
    seconds = round(score.seconds, 3)
    return {
        **base,
        "title": score.title or None,
        "description": score.description or None,
        "tempo": score.tempo,
        "key": score.key.name,
        "time": outline["time"],
        "bars": score.bars,
        "chords": chords,
        "loop": score.loop,
        "loop_seconds": seconds if score.loop else None,
        "duration": None if score.loop else seconds,
        "sections": [s["name"] for s in outline["sections"]],
        "loudness": MUSIC_LEVEL,
        "problems": [],
    }


def piece_check(path: Path, cache_dir: Path | None = None) -> dict[str, Any]:
    """``vidgen music check``'s report of the piece (:func:`vidgen.studio.check.check_dict`, no
    demo, no picture), kept in ``cache_dir`` as ``piece-<key>-check<N>.json`` (``N``:
    :data:`vidgen.studio.check.CHECK_VERSION`, so a changed check is made again) and reused."""
    from vidgen.studio import check, load_music_score

    cached = None if cache_dir is None else cache_dir / f"piece-{piece_key(path)}-check{check.CHECK_VERSION}.json"
    if cached is not None and cached.is_file():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    report = check.check_dict(check.check_music_score(load_music_score(path)))
    if cached is not None:
        text = json.dumps(report, indent=1)
        _write_atomic(cached, lambda tmp: tmp.write_text(text, encoding="utf-8"))
    return report
