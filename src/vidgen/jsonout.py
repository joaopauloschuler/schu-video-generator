"""``--json`` output of the CLI: stable documents for programs (and AI agents) driving vidgen.

Every document is one JSON object written to stdout, with the envelope

``{"version": SCHEMA_VERSION, "vidgen": "<package version>", "command": "<name>", "ok": bool,
"warnings": [{"scene", "message"}], ...command fields..., "error": {...}}``

``error`` is present only when ``ok`` is false: ``{"kind", "message", "problems", "details"}``.
The shapes are documented in docs/CONFIG.md ("JSON output"); a change that removes or renames
a key, or changes a value's type, bumps :data:`SCHEMA_VERSION` (new keys do not).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from vidgen import __version__
from vidgen.errors import Problem, VidgenError
from vidgen.project import Project

if TYPE_CHECKING:
    from vidgen.export import ExportResult
    from vidgen.icons import IconInfo
    from vidgen.deck import Deck
    from vidgen.slides import SlidesResult
    from vidgen.slides_pdf import PdfResult
    from vidgen.thumbnail import ThumbnailResult
    from vidgen.translation import TemplateResult
    from vidgen.render.pipeline import RenderResult
    from vidgen.lint import LintResult
    from vidgen.storyboard import StoryboardResult

#: Version of the JSON document shapes (not of vidgen).
SCHEMA_VERSION = 1

ErrorKind = Literal["usage", "error", "internal"]


def dumps(doc: Mapping[str, Any]) -> str:
    """Serialise a document: indented, ASCII-only (valid whatever the console's code page)."""
    return json.dumps(doc, indent=2, ensure_ascii=True)


def envelope(command: str | None, ok: bool, warnings: Iterable[Mapping[str, Any]] = (), **fields: Any) -> dict[str, Any]:
    """The common top of every document followed by ``fields``."""
    return {
        "version": SCHEMA_VERSION,
        "vidgen": __version__,
        "command": command,
        "ok": ok,
        "warnings": [dict(w) for w in warnings],
        **fields,
    }


def error_json(
    kind: ErrorKind, message: str, problems: Iterable[Problem] = (), details: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """``{"kind", "message", "problems", "details"}``.

    ``kind``: ``usage`` (bad command line, exit 2), ``error`` (a problem the user can fix: config,
    files, a failed scene..., exit 1) or ``internal`` (an unexpected exception, exit 1; ``details``
    has the ``traceback``).
    """
    return {
        "kind": kind,
        "message": message,
        "problems": [p.to_json() for p in problems],
        "details": dict(details or {}),
    }


def error_document(command: str | None, exc: VidgenError, warnings: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The document for a command that failed with ``exc``."""
    return envelope(command, False, warnings, error=error_json("error", str(exc), exc.problems, exc.details))


def warning(message: str, scene: str | None = None) -> dict[str, Any]:
    """A ``warnings`` entry: ``{"scene": id or null, "message"}``."""
    return {"scene": scene, "message": message}


def _path(path: Path) -> str:
    return str(path.resolve())


# ----- validate ----------------------------------------------------------------------------------


def audio_json(project: Project) -> dict[str, Any]:
    """Narration audio of one audio folder: counts, orphaned MP3s and each beat's state."""
    from vidgen import tts

    statuses = tts.audio_status(project)
    counts = {state: sum(1 for s in statuses if s.state == state) for state in ("ok", "stale", "missing")}
    return {
        "variant": project.variant,
        "dir": _path(project.audio_dir),
        **counts,
        "orphaned": [_path(p) for p in tts.orphaned_audio(project)],
        "beats": [{"scene": s.scene_id, "beat": s.beat_id, "state": s.state} for s in statuses],
    }


def validate_document(
    project: Project | None,
    problems: list[Problem],
    variants: Mapping[str, Project | None],
    error: VidgenError | None,
    warnings: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The ``vidgen validate --json`` document.

    ``project`` is ``None`` when the base config could not be loaded (then the summary fields
    are ``null``); ``variants`` maps every variant name to its loaded project (``None`` if it
    could not be loaded). ``error`` is the error to report when there are problems.
    """
    ok = not problems and error is None
    summary: dict[str, Any] = {
        "project": None,
        "config_file": None,
        "title": None,
        "language": None,
        "translations": None,
        "scenes": None,
        "beats": None,
        "estimated_duration": None,
        "variants": [],
        "audio": [],
    }
    if project is not None:
        summary.update(
            project=_path(project.root),
            config_file=_path(project.config_file),
            title=project.config.title,
            language=project.config.language,
            translations=translation_json(project),
            scenes=len(project.config.scenes),
            beats=sum(1 for _ in project.beats()),
            estimated_duration=round(project.estimated_duration(), 2),
            variants=[
                {
                    "name": name,
                    "loaded": variant is not None,
                    "estimated_duration": None if variant is None else round(variant.estimated_duration(), 2),
                    "problems": sum(1 for p in problems if p.variant == name),
                    "language": None if variant is None else variant.config.language,
                    "translations": None if variant is None else translation_json(variant),
                }
                for name, variant in variants.items()
            ],
            audio=[
                audio_json(p)
                for p in [project, *variants.values()]
                if p is not None and (p.variant is None or p.has_own_audio)
            ],
        )
    doc = envelope("validate", ok, warnings, **summary, problems=[p.to_json() for p in problems])
    if error is not None:
        doc["error"] = error_json("error", str(error), problems, error.details)
    return doc


# ----- list-scenes -------------------------------------------------------------------------------


def list_scenes_document(project: Project | None, warnings: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The ``vidgen list-scenes --json`` document (call with the project's scene types active)."""
    from vidgen import registry
    from vidgen.describe import action_type_json, overlay_type_json, scene_type_json

    return envelope(
        "list-scenes",
        True,
        warnings,
        project=None if project is None else _path(project.root),
        scene_types=[scene_type_json(entry) for entry in registry.all()],
        actions=[action_type_json(entry) for entry in registry.all_actions()],
        overlays=[overlay_type_json(entry) for entry in registry.all_overlays()],
    )


# ----- list-themes -------------------------------------------------------------------------------


def list_themes_document(
    project: Project | None,
    orientation: str,
    current: Mapping[str, Any],
    presets: list[dict[str, Any]],
    scales: Mapping[str, Any],
    swatches: Path | None,
    warnings: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The ``vidgen list-themes --json`` document: the project's theme choice, every preset
    (``vidgen.themelist.preset_entry``) and the type scales."""
    return envelope(
        "list-themes",
        True,
        warnings,
        project=None if project is None else _path(project.root),
        orientation=orientation,
        current=dict(current),
        presets=presets,
        type_scales=dict(scales),
        swatches=None if swatches is None else _path(swatches),
    )


# ----- list-icons --------------------------------------------------------------------------------


def list_icons_document(
    root: Path | None,
    search: str | None,
    category: str | None,
    icons: Iterable[IconInfo],
    categories: list[dict[str, Any]],
    sheets: Iterable[Path],
    warnings: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The ``vidgen list-icons --json`` document: the filter, the built-in sources, every
    category with its icon count, the matching icons (``IconInfo.to_json``) and sheet paths."""
    from vidgen.icons import builtin_sources

    icons = list(icons)
    return envelope(
        "list-icons",
        True,
        warnings,
        project=None if root is None else _path(root),
        search=search,
        category=category,
        sources=builtin_sources(),
        categories=categories,
        count=len(icons),
        icons=[icon.to_json() for icon in icons],
        sheets=[_path(p) for p in sheets],
    )


def list_sfx_document(
    root: Path | None, sounds: Iterable[Mapping[str, Any]], previews: Path | None, warnings: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The ``vidgen list-sfx --json`` document: the level every sound is set to, the params of
    built-in sounds, every sound (``vidgen.sfx.sound_entries``) and the previews folder."""
    from vidgen import sfx
    from vidgen.config import SfxParams
    from vidgen.describe import params_json

    entries = [{**s, "preview": None if s["preview"] is None else _path(s["preview"])} for s in sounds]
    return envelope(
        "list-sfx",
        True,
        warnings,
        project=None if root is None else _path(root),
        rate=sfx.RATE,
        loudness_target=sfx.LOUDNESS_TARGET,
        peak_ceiling=sfx.PEAK_CEILING,
        params=params_json(SfxParams),
        count=len(entries),
        sounds=entries,
        previews=None if previews is None else _path(previews),
    )


def list_music_document(
    root: Path | None, entries: Iterable[Mapping[str, Any]], previews: Path | None, warnings: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The ``vidgen list-music --json`` document: the music level, the default ducking, every bed
    and project file (``vidgen.music.music_entries``) and the previews folder."""
    from vidgen import music
    from vidgen.config import DuckConfig

    items = [{**e, "preview": None if e["preview"] is None else _path(e["preview"])} for e in entries]
    return envelope(
        "list-music",
        True,
        warnings,
        project=None if root is None else _path(root),
        rate=music.RATE,
        level=music.MUSIC_LEVEL,
        duck=DuckConfig().model_dump(),
        count=len(items),
        music=items,
        previews=None if previews is None else _path(previews),
    )


# ----- render ------------------------------------------------------------------------------------


def render_document(
    project: Project,
    result: RenderResult,
    preview: bool,
    elapsed: float,
    warnings: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The ``vidgen render --json`` document."""
    timings = result.timings
    worker_warnings = [warning(message, scene) for scene, message in result.warnings]
    scenes = [
        {
            "id": scene["id"],
            "type": scene["type"],
            "status": "rendered" if scene["id"] in result.rendered else "reused",
            "start": scene["start"],
            "duration": scene["duration"],
            "render_seconds": result.render_seconds.get(scene["id"]),
            "beats": [{"id": b["id"], "start": b["start"], "end": b["end"]} for b in scene["beats"]],
        }
        for scene in timings["scenes"]
    ]
    return envelope(
        "render",
        True,
        [*warnings, *worker_warnings],
        project=_path(project.root),
        variant=project.variant,
        preview=preview,
        audio=timings["audio"],
        format=timings["format"],
        outputs={
            "video": _path(result.output),
            "subtitles": _path(result.srt),
            "timings": _path(result.timings_file),
            "frames": None if result.frames_index is None else _path(result.frames_index),
            "chapters": None if result.chapters is None else _path(result.chapters),
            "thumbnail": None if result.thumbnail is None else _path(result.thumbnail.path),
        },
        duration=result.duration,
        elapsed=round(elapsed, 3),
        mix=timings.get("mix"),
        chapters=timings.get("chapters", []),
        scenes=scenes,
    )


# ----- thumbnail / export ------------------------------------------------------------------------


def thumbnail_document(
    project: Project, result: ThumbnailResult, preview: bool, elapsed: float, warnings: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The ``vidgen thumbnail --json`` document: the files, what the picture shows (``source``)
    and the legibility ``checks`` (``{rule, severity, message}``)."""
    return envelope(
        "thumbnail",
        True,
        warnings,
        project=_path(project.root),
        variant=project.variant,
        preview=preview,
        kind=result.kind,
        path=_path(result.path),
        width=result.width,
        height=result.height,
        bytes=result.bytes,
        jpeg=None if result.jpeg is None else _path(result.jpeg),
        jpeg_bytes=result.jpeg_bytes,
        small=_path(result.small),
        source=result.source,
        checks=[c.to_json() for c in result.checks],
        rendered=result.rendered,
        elapsed=round(elapsed, 3),
    )


def translate_template_document(project: Project, result: TemplateResult, warnings: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The ``vidgen translate-template --json`` document: the file, its language, how many
    texts it lists and what the merge with the existing file did (lists of keys)."""
    s = result.stats
    return envelope(
        "translate-template",
        True,
        warnings,
        project=_path(project.root),
        variant=project.variant,
        path=_path(result.path),
        rel=result.rel,
        language=result.language,
        linked=result.linked,
        texts=result.total,
        translated=s.translated,
        untranslated=s.untranslated,
        stale=s.stale,
        moved=s.moved,
        obsolete=s.obsolete,
        dropped=s.dropped,
        references=result.references,
    )


def translation_json(project: Project) -> dict[str, Any] | None:
    """``{file, language, applied, stale, unknown, untranslated}`` of the project's translation
    file (key lists except ``applied``, a count), or ``None`` without one (DESIGN.md §54)."""
    report = project.translation
    if report is None:
        return None
    return {
        "file": report.file,
        "language": report.language,
        "applied": len(report.applied),
        "stale": list(report.stale),
        "unknown": list(report.unknown),
        "untranslated": list(report.untranslated),
    }


def export_document(
    project: Project, result: ExportResult, preview: bool, elapsed: float, warnings: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The ``vidgen export --json`` document: the file, the part of the video and how it was made."""
    return envelope(
        "export",
        True,
        warnings,
        project=_path(project.root),
        variant=project.variant,
        preview=preview,
        kind=result.kind,
        path=_path(result.path),
        source=_path(result.source),
        scene=result.scene,
        start=result.start,
        end=result.end,
        duration=round(result.end - result.start, 6),
        width=result.width,
        height=result.height,
        fps=result.fps,
        bytes=result.bytes,
        method=result.method,
        audio=result.audio,
        max_mb=result.max_mb,
        within_budget=result.within_budget,
        attempts=result.attempts,
        elapsed=round(elapsed, 3),
    )


def _deck_slides(deck: Deck) -> list[dict[str, Any]]:
    """The slides of a ``vidgen slides`` document (HTML and PDF)."""
    return [
        {
            "index": s.index,
            "scene": s.scene,
            "type": s.scene_type,
            "chapter": None if s.chapter is None else s.chapter.title,
            "beats": [b.id for b in s.beats],
            "notes": s.notes,
            "k": s.k,
            "n": s.n,
            "merged": s.merged,
            "time": s.time,
            "scene_time": s.scene_time,
            "at": s.at,
            "until": s.until,
            "still": _path(s.still),
        }
        for s in deck.slides
    ]


def slides_document(project: Project, result: SlidesResult, elapsed: float, warnings: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The ``vidgen slides --json`` document: the page, how its slides were chosen and each slide."""
    deck = result.deck
    worker_warnings = [warning(message, scene) for scene, message in deck.warnings]
    fmt = deck.format
    return envelope(
        "slides",
        True,
        [*warnings, *worker_warnings],
        project=_path(project.root),
        variant=project.variant,
        language=project.config.language,
        output_format="html",
        preview=deck.preview,
        mode=deck.mode,
        per_beat=deck.per_beat,
        overlays=deck.overlays,
        dedupe=deck.dedupe,
        format={"width": fmt.width, "height": fmt.height, "fps": fmt.fps},
        path=_path(result.path),
        bytes=result.bytes,
        files_dir=None if result.files_dir is None else _path(result.files_dir),
        image_format=result.image_format,
        quality=result.quality,
        width=result.width,
        height=result.height,
        audio=result.audio,
        duration=deck.duration,
        stills=deck.stills,
        merged=deck.merged,
        rendered=deck.rendered,
        reused=deck.reused,
        elapsed=round(elapsed, 3),
        slides=_deck_slides(deck),
    )


def slides_pdf_document(project: Project, result: PdfResult, elapsed: float, warnings: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The ``vidgen slides --format pdf --json`` document: the PDF, its layout and each slide."""
    deck = result.deck
    worker_warnings = [warning(message, scene) for scene, message in deck.warnings]
    fmt = deck.format
    options = result.options
    return envelope(
        "slides",
        True,
        [*warnings, *worker_warnings],
        project=_path(project.root),
        variant=project.variant,
        language=project.config.language,
        output_format="pdf",
        preview=deck.preview,
        mode=deck.mode,
        per_beat=deck.per_beat,
        overlays=deck.overlays,
        dedupe=deck.dedupe,
        format={"width": fmt.width, "height": fmt.height, "fps": fmt.fps},
        path=_path(result.path),
        bytes=result.bytes,
        pages=result.pages,
        notes=options.notes,
        title_page=options.title_page,
        thumbnail=None if result.thumbnail is None else _path(result.thumbnail),
        paper=options.paper,
        bookmarks=result.bookmarks,
        image_format=options.image_format,
        quality=options.quality,
        width=result.width,
        height=result.height,
        duration=deck.duration,
        stills=deck.stills,
        merged=deck.merged,
        rendered=deck.rendered,
        reused=deck.reused,
        elapsed=round(elapsed, 3),
        slides=_deck_slides(deck),
    )


# ----- schema ------------------------------------------------------------------------------------


def schema_document(project: Project | None, schema: Mapping[str, Any], warnings: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The ``vidgen schema --json`` document: the JSON Schema under ``schema``."""
    return envelope("schema", True, warnings, project=None if project is None else _path(project.root), schema=dict(schema))


# ----- storyboard --------------------------------------------------------------------------------


def storyboard_document(
    project: Project, result: StoryboardResult, elapsed: float, warnings: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The ``vidgen storyboard --json`` document: every sheet page with the stills it shows."""
    worker_warnings = [warning(message, scene) for scene, message in result.warnings]
    sheets = [
        {
            "kind": sheet.kind,
            "scene": sheet.scene,
            "page": sheet.page,
            "pages": sheet.pages,
            "path": _path(sheet.path),
            "width": sheet.width,
            "height": sheet.height,
            "frames": [
                {
                    "scene": still.scene_id,
                    "beat": still.beat_id,
                    "k": still.k,
                    "n": still.n,
                    "time": still.time,
                    "scene_time": still.scene_time,
                    "path": _path(still.path),
                }
                for still in sheet.stills
            ],
        }
        for sheet in result.sheets
    ]
    fmt = result.format
    return envelope(
        "storyboard",
        True,
        [*warnings, *worker_warnings],
        project=_path(project.root),
        variant=project.variant,
        preview=result.preview,
        per_beat=result.per_beat,
        format={"width": fmt.width, "height": fmt.height, "fps": fmt.fps},
        folder=_path(result.folder),
        rendered=result.rendered,
        reused=result.reused,
        elapsed=round(elapsed, 3),
        sheets=sheets,
    )


# ----- lint --------------------------------------------------------------------------------------


def lint_document(
    project: Project, result: LintResult, elapsed: float, warnings: Iterable[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The ``vidgen lint --json`` document: every finding; ``ok`` is false (exit code 1) when a
    finding is at least as severe as ``fail_on``."""
    worker_warnings = [warning(message, scene) for scene, message in result.warnings]
    fmt = result.format
    counts = result.counts()
    doc = envelope(
        "lint",
        not result.failed,
        [*warnings, *worker_warnings],
        project=_path(project.root),
        variant=project.variant,
        preview=result.preview,
        format={"width": fmt.width, "height": fmt.height, "fps": fmt.fps},
        fail_on=result.fail_on,
        rules=result.rules,
        scenes=result.scenes,
        stills=result.stills,
        rendered=result.rendered,
        reused=result.reused,
        elapsed=round(elapsed, 3),
        counts=counts,
        ignored=result.ignored,
        findings=[f.to_json() for f in result.findings],
    )
    if result.failed:
        summary = ", ".join(f"{n} {sev}" for sev, n in counts.items())
        message = f"lint found {summary} (fails on {result.fail_on} or worse)"
        doc["error"] = error_json("error", message, details={"fail_on": result.fail_on, "counts": counts})
    return doc
