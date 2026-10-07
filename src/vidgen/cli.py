"""Command-line interface (DESIGN.md §8)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
import traceback
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from vidgen import __version__, jsonout
from vidgen.config import validation_problems
from vidgen.describe import describe_params
from vidgen.errors import Problem, VidgenError
from vidgen.project import CONFIG_NAMES, Project, find_config_file
from vidgen.sheets import DEFAULT_WIDTH as DEFAULT_SHEET_WIDTH
from vidgen.theme import Theme

TEMPLATES_DIR = Path(__file__).parent / "templates"
#: Template files copied as ``.<name>`` by ``vidgen init``.
TEMPLATE_DOTFILES: tuple[str, ...] = ("gitignore",)
#: Subcommands that accept ``--json``.
JSON_COMMANDS: tuple[str, ...] = (
    "validate", "list-scenes", "list-themes", "list-icons", "list-sfx", "list-music", "render", "schema", "storyboard", "lint",
    "thumbnail", "export", "translate-template", "slides", "readback", "guide",
)

#: What a command function returns: an exit code, or (with ``--json``) the JSON document.
CommandResult = int | dict[str, Any]

#: ``validate_project`` messages start with the param they are about: ``"path: file not found"``.
_PARAM_MESSAGE = re.compile(r"^([A-Za-z_][\w.\[\]]*): (.*)$", re.DOTALL)


def _format_seconds(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a new project from a template."""
    target = Path(args.dir)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise VidgenError(f"{target} already exists and is not an empty directory")
    template = TEMPLATES_DIR / args.example
    shutil.copytree(template, target, dirs_exist_ok=True)
    # Dot files are not packaged in the wheel, so the template stores them without the dot.
    for name in TEMPLATE_DOTFILES:
        if (target / name).is_file():
            (target / name).replace(target / f".{name}")
    for folder in ("assets", "extensions"):
        (target / folder).mkdir(exist_ok=True)
    config_file = target / "video.yaml"
    title = json.dumps(target.resolve().name.replace("_", " ").replace("-", " ").title(), ensure_ascii=False)
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace("__TITLE__", title), encoding="utf-8"
    )
    print(f"created project in {target}")
    print("next: edit video.yaml, then run `vidgen validate`, `vidgen tts` and `vidgen render`")
    print("guide: `vidgen guide` (how to make a good video: workflow, pacing, scene types; for AI agents too)")
    return 0


def project_problems(project: Project) -> list[Problem]:
    """Checks beyond config structure; returns the problems found (empty if none).

    Loads built-ins and the project's extensions in isolation (nothing leaks into the caller's
    registry), checks that every scene ``type`` is registered, validates each scene's
    ``params`` against the type's ``Params`` model (theme tokens against the project's theme)
    and runs the type's ``validate_project`` (e.g. missing asset files); checks the beats'
    ``actions`` (action names, options, targets of the scene) and the ``overlays`` (types,
    options, scene references; DESIGN.md §41); also checks the project's ``assets/icons``,
    the sounds of the scenes' ``sfx:`` lists (§47), the ``music:`` sources (§48) and a designed
    ``thumbnail:``'s icon, image, preset and background (§53).
    """
    from vidgen import extensions, registry
    from vidgen.actions import scene_actions
    from vidgen.carry import carry_problems
    from vidgen.icons import PROJECT_ICONS_DIR, project_icons
    from vidgen.music import config_problems as music_problems
    from vidgen.overlays import overlay_problems
    from vidgen.sfx import config_problems as sfx_problems
    from vidgen.thumbnail import thumbnail_problems
    from vidgen.transitions import color_problems as transition_color_problems
    from vidgen.voices import voice_color_problems

    problems: list[Problem] = []
    try:
        with extensions.project_session(project) as theme:
            try:
                theme.preset_chain()
            except VidgenError as exc:  # every theme lookup would fail; nothing else to check
                return [Problem("theme.preset", str(exc))]
            try:
                project_icons(project.root)
            except VidgenError as exc:
                problems.append(Problem(PROJECT_ICONS_DIR.as_posix(), str(exc)))
            for i, scene in enumerate(project.config.scenes):
                entry = registry.find(scene.type)
                if entry is None:
                    problems.append(Problem(f"scenes[{i}].type", registry.unknown_type_message(scene.type)))
                    continue
                beat_problem = entry.cls.check_beat_count(len(scene.beats))
                if beat_problem is not None:
                    problems.append(Problem(f"scenes[{i}].beats", f"type '{scene.type}' {beat_problem}"))
                try:
                    params = entry.cls.validate_params(scene.params, theme)
                except ValidationError as exc:
                    problems.extend(validation_problems(exc, ("scenes", i, "params"), entry.cls.params_model()))
                    params = None
                _, action_problems = scene_actions(scene.type, entry.cls, scene, params, theme)
                problems.extend(Problem(f"scenes[{i}].{loc}", message) for loc, message in action_problems)
                if params is None:
                    continue
                try:
                    problems.extend(_param_problem(i, p) for p in _project_checks(entry, params, project))
                except VidgenError as exc:
                    problems.append(Problem(f"scenes[{i}]", str(exc)))
            problems.extend(overlay_problems(project, theme))
            problems.extend(voice_color_problems(project.config, theme))
            problems.extend(transition_color_problems(project.config, theme))
            problems.extend(carry_problems(project.config))
            problems.extend(Problem(loc, message) for loc, message in sfx_problems(project.config, project.root))
            problems.extend(Problem(loc, message) for loc, message in music_problems(project.config, project.root))
            problems.extend(thumbnail_problems(project, theme))
    except VidgenError as exc:
        problems.extend(exc.problems or [Problem("", str(exc))])
    return problems


def check_project(project: Project) -> list[str]:
    """:func:`project_problems` as the lines ``vidgen validate`` prints."""
    return [str(p) for p in project_problems(project)]


def _param_problem(index: int, message: str) -> Problem:
    """A ``validate_project`` message (``"<param>: <text>"`` by convention) as a Problem."""
    match = _PARAM_MESSAGE.match(message)
    if match is None:
        return Problem(f"scenes[{index}].params", message)
    return Problem(f"scenes[{index}].params.{match[1]}", match[2])


def _project_checks(entry: Any, params: Any, project: Project) -> list[str]:
    """``entry.cls.validate_project(params, project)``; a scene type whose check raises or does
    not return a list of strings becomes a :class:`VidgenError` naming the type and its file."""
    where = f"validate_project of scene type '{entry.name}' ({entry.origin})"
    try:
        result = entry.cls.validate_project(params, project)
    except VidgenError as exc:
        raise VidgenError(f"{where} failed: {exc}") from None
    except Exception as exc:
        tb = exc.__traceback__.tb_next if exc.__traceback__ is not None else None
        details = "".join(traceback.format_exception(type(exc), exc, tb)).rstrip()
        raise VidgenError(f"{where} failed: {type(exc).__name__}: {exc}\n{details}") from None
    if not isinstance(result, list) or not all(isinstance(p, str) for p in result):
        raise VidgenError(f"{where} must return a list of strings, got {result!r}")
    return result


def validate_all(
    project: Project, keep_going: bool = False
) -> tuple[list[Problem], dict[str, Project | None]]:
    """Check ``project`` and every variant; returns the problems and the loaded variants.

    Problems of a variant that equal the base config's are not repeated. A variant whose
    config does not load raises its :class:`VidgenError`, or with ``keep_going`` adds its
    problems and maps the variant to ``None``.
    """
    base = project_problems(project)
    problems = list(base)
    variants: dict[str, Project | None] = {}
    for name in project.config.variants:
        try:
            variant = Project.load(project.config_file, variant=name)
        except VidgenError as exc:
            if not keep_going:
                raise
            variants[name] = None
            problems.extend(exc.problems or [Problem("", str(exc), name)])
            continue
        variants[name] = variant
        problems.extend(p.in_variant(name) for p in project_problems(variant) if p not in base)
    return problems, variants


def theme_warnings(project: Project) -> list[str]:
    """The project theme's colour pairs below WCAG AA (``theme_contrast``), as messages; empty
    when the theme cannot be resolved (an unknown preset is a problem, reported elsewhere)."""
    from vidgen import extensions
    from vidgen.lint.color import theme_contrast

    try:
        with extensions.project_session(project) as theme:
            checks = theme_contrast(theme)
    except VidgenError:
        return []
    return [f"theme contrast: {check}" for check in checks if not check.ok]


def pronunciation_warnings(project: Project) -> list[str]:
    """``pronunciation:`` entries that match no beat, never apply or collide (DESIGN.md §45)."""
    from vidgen.pronunciation import pronunciation_warnings as check

    return check(project.pronunciation, ((beat.id, beat.text) for _, beat in project.beats()))


def validate_warnings(project: Project) -> list[str]:
    """What ``vidgen validate`` warns about (not problems): :func:`theme_warnings`,
    :func:`pronunciation_warnings`, named voices no beat uses and transitions that hold the
    scene before them longer (DESIGN.md §49), carries through a transition that moves them
    (§50), a YouTube chapter list YouTube would ignore (§52), texts a translation file leaves in
    the source language and base pronunciations kept in another language (§54), generated
    pictures not made yet and prompts asking for words in a picture (§58)."""
    from vidgen.carry import carry_warnings
    from vidgen.chapter_export import chapter_warnings
    from vidgen.imagegen import imagegen_warnings
    from vidgen.transitions import transition_warnings
    from vidgen.translation import language_warnings, translation_warnings
    from vidgen.voices import voice_warnings

    return (
        theme_warnings(project)
        + pronunciation_warnings(project)
        + voice_warnings(project.config)
        + transition_warnings(project)
        + carry_warnings(project.config)
        + chapter_warnings(project)
        + translation_warnings(project)
        + language_warnings(project)
        + imagegen_warnings(project)
    )


def log_validate_warnings(project: Project, variants: dict[str, Project | None]) -> None:
    """Log :func:`validate_warnings` of ``project`` and of every loaded variant (a variant's
    warning that equals the base config's is not repeated)."""
    log = logging.getLogger("vidgen")
    base = validate_warnings(project)
    for message in base:
        log.warning(message)
    for name, variant in variants.items():
        if variant is not None:
            for message in validate_warnings(variant):
                if message not in base:
                    log.warning("[%s] %s", name, message)


def _invalid_project(project: Project, problems: list[Problem]) -> VidgenError:
    lines = [f"{project.config_file.name}: invalid project"]
    for problem in problems:
        lines.extend(f"  {line}" for line in str(problem).splitlines())
    return VidgenError("\n".join(lines), problems=problems)


def cmd_validate(args: argparse.Namespace) -> CommandResult:
    """Load the project (and every variant), check it and print a short summary."""
    if args.json:
        return _validate_json(args.project)
    project = Project.load(args.project)
    problems, variants = validate_all(project)
    log_validate_warnings(project, variants)
    if problems:
        raise _invalid_project(project, problems)

    config = project.config
    n_beats = sum(1 for _ in project.beats())
    print(f"title:     {config.title}")
    print(f"scenes:    {len(config.scenes)}")
    print(f"beats:     {n_beats}")
    print(f"duration:  ~{_format_seconds(project.estimated_duration())} (estimated from word count)")
    if config.variants:
        print(f"variants:  {', '.join(config.variants)}")
    if config.voices:
        counts = Counter(name or "default" for name in project.voice_names().values())
        print(f"voices:    {', '.join(f'{name} ({n} beats)' for name, n in counts.items())}")
    for line in language_summary_lines(project, variants):
        print(line)
    for line in audio_summary_lines(project):
        print(line)
    for line in images_summary_lines(project, variants):
        print(line)
    print("ok")
    return 0


def _validate_json(path: str) -> dict[str, Any]:
    """``vidgen validate --json``: like the human command, but every problem is reported in the
    document (a variant that does not load is a problem, not the end of the command)."""
    try:
        project = Project.load(path)
    except VidgenError as exc:
        return jsonout.validate_document(None, exc.problems or [Problem("", str(exc))], {}, exc)
    problems, variants = validate_all(project, keep_going=True)
    log_validate_warnings(project, variants)
    error = _invalid_project(project, problems) if problems else None
    return jsonout.validate_document(project, problems, variants, error)


def language_summary_lines(project: Project, variants: dict[str, Project | None]) -> list[str]:
    """``language: pt-BR (translations/pt.yaml: 40 translated, 2 stale)`` for the base config
    and each variant with a language or a translation file (DESIGN.md §54)."""
    lines = []
    for p in [project, *(v for v in variants.values() if v is not None)]:
        report = p.translation
        if p.config.language is None and report is None:
            continue
        if p.variant is not None and p.config.language == project.config.language and report is None:
            continue
        what = p.config.language or "not set"
        if report is not None:
            what += f" ({report.file}: {len(report.applied)} translated" + (f", {len(report.stale)} stale" if report.stale else "") + ")"
        label = "language:" if p.variant is None else f"language [{p.variant}]:"
        lines.append(f"{label:<10} {what}" if p.variant is None else f"{label} {what}")
    return lines


def audio_summary_lines(project: Project) -> list[str]:
    """``audio: 18 ok, 2 stale, 1 missing`` for the base config and for each variant that has
    its own audio folder (no API key needed)."""
    from vidgen import tts

    lines = []
    projects = [project] + [Project.load(project.config_file, variant=name) for name in project.config.variants]
    for p in projects:
        if p.variant is not None and not p.has_own_audio:
            continue
        label = "audio:" if p.variant is None else f"audio [{p.variant}]:"
        summary = tts.format_audio_summary(tts.audio_status(p))
        orphans = tts.orphaned_audio(p)
        if orphans:
            summary += f" ({len(orphans)} orphaned mp3)"
        lines.append(f"{label:<10} {summary}" if p.variant is None else f"{label} {summary}")
    return lines


def images_summary_lines(project: Project, variants: dict[str, Project | None]) -> list[str]:
    """``images: 3 generated, 1 missing`` for the base config and each variant whose pictures
    differ (none without ``generate:`` params)."""
    from vidgen.imagegen import images_summary, scene_images

    lines = []
    base_keys: set[str] | None = None
    for p in [project, *(v for v in variants.values() if v is not None)]:
        try:
            images = scene_images(p)
        except VidgenError:  # extensions that do not load are a problem reported above
            images = []
        keys = {i.request.key for i in images}
        if base_keys is None:
            base_keys = keys
        elif keys == base_keys:
            continue
        if images:
            label = "images:" if p.variant is None else f"images [{p.variant}]:"
            lines.append(f"{label:<10} {images_summary(images)}" if p.variant is None else f"{label} {images_summary(images)}")
    return lines


def cmd_imagegen(args: argparse.Namespace) -> int:
    """Generate the pictures of ``generate:`` params that are missing (DESIGN.md §58)."""
    from vidgen.imagegen.run import run_imagegen

    project = Project.load(args.project, variant=args.variant)
    run_imagegen(project, scene_ids=args.scene, force=args.force, dry_run=args.dry_run)
    return 0


def cmd_tts(args: argparse.Namespace) -> int:
    """Generate narration audio for beats whose MP3 is missing or stale."""
    from vidgen import extensions
    from vidgen.tts.run import run_tts

    project = Project.load(args.project, variant=args.variant)
    with extensions.project_session(project):
        run_tts(project, beat_ids=args.beat, force=args.force, dry_run=args.dry_run, voices=args.voice)
    return 0


def cmd_readback(args: argparse.Namespace) -> CommandResult:
    """Transcribe the beats' MP3s (speech to text, cached) and compare them with their texts:
    word error rate, differing words and suggested fixes per beat (DESIGN.md §57)."""
    from vidgen.readback import report_lines, run_readback

    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    result = run_readback(project, beat_ids=args.beat, force=args.force, max_wer=args.max_wer)
    if args.json:
        return jsonout.readback_document(project, result, time.monotonic() - started)
    for line in report_lines(result):
        print(line)
    return 0


def cmd_translate_template(args: argparse.Namespace) -> CommandResult:
    """Write (or update) a variant's translation file: every translatable text with its source,
    keeping the translations it already holds (DESIGN.md §54)."""
    from vidgen.translation import write_template

    project = Project.load(args.project, variant=args.variant)
    output = Path(args.output).resolve() if args.output else None
    result = write_template(project, language=args.lang, output=output)
    if args.json:
        return jsonout.translate_template_document(project, result)
    s = result.stats
    print(f"translations: {result.path}")
    print(f"language:     {result.language or 'not set (give --lang, e.g. --lang pt-BR)'}")
    parts = [f"{s.translated} translated", f"{len(s.untranslated)} to translate"]
    for name, keys in (("stale", s.stale), ("moved", s.moved), ("obsolete", s.obsolete), ("dropped", s.dropped)):
        if keys:
            parts.append(f"{len(keys)} {name}")
    print(f"texts:        {result.total} ({', '.join(parts)}); {result.references} references")
    if not result.linked:
        where = f"variant '{project.variant}'" if project.variant else "config"
        print(f"next: add `translations: {result.rel}` to the {where}, fill in the texts, then `vidgen validate`")
    if result.language is not None and project.config.language != result.language:
        print(f"note: set `language: {result.language}` in the {'variant' if project.variant else 'config'} too")
    return 0


def cmd_render(args: argparse.Namespace) -> CommandResult:
    """Render every scene (or only ``--scene`` ones), join them and write the MP4 and SRT."""
    from vidgen.render.pipeline import render_project

    if args.jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    if args.frames_per_beat is not None and args.frames_per_beat < 1:
        raise VidgenError("--frames-per-beat must be at least 1")
    frames = args.frames_per_beat or (1 if args.frames else 0)
    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    result = render_project(
        project,
        preview=args.preview,
        scenes=args.scene or None,
        no_audio=args.no_audio,
        keep_going=args.keep_going,
        jobs=args.jobs,
        frames=frames,
    )
    if args.json:
        return jsonout.render_document(project, result, args.preview, time.monotonic() - started)
    reused = f", {len(result.reused)} reused" if result.reused else ""
    print(f"rendered {len(result.rendered)} scene(s){reused}")
    print(f"video:     {result.output}")
    print(f"subtitles: {result.srt}")
    if result.chapters is not None:
        print(f"chapters:  {result.chapters}")
    if result.frames_index is not None:
        print(f"frames:    {result.frames_index}")
    if result.thumbnail is not None:
        print(f"thumbnail: {result.thumbnail.path}")
    print(f"duration:  {_format_seconds(result.duration)} ({result.duration:.2f} s)")
    mix = result.timings.get("mix")
    if mix is not None:
        print(f"loudness:  {_loudness_line(mix)}")
    return 0


def _loudness_line(mix: dict[str, Any]) -> str:
    """``-16.0 LUFS integrated, true peak -1.6 dBTP (normalised to -16, +4.2 dB; music: calm)``."""
    level = "silent" if mix["integrated_lufs"] is None else f"{mix['integrated_lufs']:.1f} LUFS integrated"
    peak = "" if mix["true_peak_dbtp"] is None else f", true peak {mix['true_peak_dbtp']:.1f} dBTP"
    notes = []
    if mix["normalized"]:
        notes.append(f"normalised to {mix['target_lufs']:g}, {mix['gain_db']:+.1f} dB")
    if mix["music"]:
        notes.append("music: " + ", ".join(m["source"] for m in mix["music"]))
    return level + peak + (f" ({'; '.join(notes)})" if notes else "")


def cmd_storyboard(args: argparse.Namespace) -> CommandResult:
    """Render what is needed with frame stills and write contact sheets (PNG) of the video."""
    from vidgen.storyboard import make_storyboard

    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    result = make_storyboard(
        project,
        preview=not args.final,
        scenes=args.scene or None,
        per_beat=args.per_beat,
        width=args.width,
        jobs=args.jobs,
        force=args.force,
    )
    if args.json:
        return jsonout.storyboard_document(project, result, time.monotonic() - started)
    reused = f", {len(result.reused)} reused" if result.reused else ""
    print(f"rendered {len(result.rendered)} scene(s){reused}")
    print(f"storyboard: {result.folder}")
    for sheet in result.sheets:
        rel = sheet.path.relative_to(result.folder).as_posix()
        print(f"  {rel}  ({len(sheet.stills)} still{'s' if len(sheet.stills) != 1 else ''}, {sheet.width}x{sheet.height})")
    return 0


def _cli_thumbnail(project: Project, args: argparse.Namespace) -> Any:
    """The frame thumbnail of ``--scene`` / ``--beat`` / ``--at`` / ``--no-overlays`` (keeping the
    config's ``jpeg``); ``None`` without ``--scene``."""
    from vidgen.config import ThumbnailConfig

    if args.scene is None:
        if args.beat is not None or args.at is not None or args.no_overlays:
            raise VidgenError("--beat, --at and --no-overlays choose a frame of --scene ID; add --scene")
        return None
    beat: str | int | None = args.beat
    if beat is not None and beat.isdigit() and beat not in {b.id for b in project.scene(args.scene).beats}:
        beat = int(beat)  # a beat number, unless a beat is called that
    try:
        spec = ThumbnailConfig(
            scene=args.scene, beat=beat, at=args.at, overlays=False if args.no_overlays else None,
            jpeg=project.config.thumbnail.jpeg if project.config.thumbnail is not None else False,
        )
    except ValidationError as exc:
        raise VidgenError("; ".join(str(p) for p in validation_problems(exc, ("thumbnail",)))) from None
    problems = project.config.thumbnail_problems(spec)
    if problems:
        raise VidgenError("; ".join(problems))
    return spec


def cmd_thumbnail(args: argparse.Namespace) -> CommandResult:
    """Write the video's thumbnail (the config's ``thumbnail:``, or a frame chosen with ``--scene``)."""
    from vidgen.thumbnail import make_thumbnail

    if args.jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    spec = _cli_thumbnail(project, args)
    result = make_thumbnail(project, preview=args.preview, spec=spec, jpeg=True if args.jpeg else None, jobs=args.jobs)
    if args.json:
        return jsonout.thumbnail_document(project, result, args.preview, time.monotonic() - started)
    source = result.source
    if result.kind == "frame":
        what = f"frame {source['frame']} of {source['scene']}" + (f" ({source['beat']})" if source["beat"] else "")
        what += f" @ {source['time']:.2f} s" + ("" if source["overlays"] else ", no overlays")
    else:
        what = f"designed, title {source['title_px']} px"
    print(f"thumbnail: {result.path}  ({result.width}x{result.height}, {what}, {result.bytes / 1e3:.0f} KB)")
    if result.jpeg is not None and result.jpeg_bytes is not None:
        print(f"jpeg:      {result.jpeg}  ({result.jpeg_bytes / 1e3:.0f} KB)")
    print(f"small:     {result.small}  (as YouTube shows it small; look at it)")
    if result.rendered:
        print(f"rendered {len(result.rendered)} scene(s) for it: {', '.join(result.rendered)}")
    for check in result.checks:
        print(str(check))
    return 0


def _slides_options(args: argparse.Namespace) -> None:
    """Options of one deck format given with the other are errors (before anything renders)."""
    if args.format == "pdf":
        wrong = [name for name, given in (("--audio", args.audio), ("--separate", args.separate)) if given]
        if wrong:
            raise VidgenError(f"{', '.join(wrong)}: only for the HTML deck (--format html)")
    else:
        wrong = [name for name, given in (("--notes", args.notes), ("--title-page", args.title_page), ("--paper", args.paper)) if given]
        if wrong:
            raise VidgenError(f"{', '.join(wrong)}: only for the PDF deck (--format pdf); the HTML deck always has the notes")


def cmd_slides_pdf(args: argparse.Namespace, project: Project, started: float) -> CommandResult:
    """``vidgen slides --format pdf``: the PDF deck."""
    from vidgen.slides_pdf import DEFAULT_PDF_QUALITY, make_slides_pdf

    result = make_slides_pdf(
        project,
        preview=not args.final,
        mode=args.mode,
        per_beat=args.per_beat,
        overlays=args.overlays,
        dedupe=not args.no_dedupe,
        notes=args.notes,
        title_page=args.title_page,
        paper=args.paper or "a4",
        image_format=args.image_format or "jpeg",
        quality=args.quality if args.quality is not None else DEFAULT_PDF_QUALITY,
        max_width=args.max_width,
        output=Path(args.output).resolve() if args.output else None,
        jobs=args.jobs,
        force=args.force,
    )
    if args.json:
        return jsonout.slides_pdf_document(project, result, time.monotonic() - started)
    deck = result.deck
    reused = f", {len(deck.reused)} reused" if deck.reused else ""
    print(f"rendered {len(deck.rendered)} scene(s){reused}")
    note = f", {deck.merged} alike merged" if deck.merged else ""
    print(f"slides: {result.path}  ({len(deck.slides)} slides from {deck.stills} stills{note}, {result.pages} pages, {result.bytes / 1e6:.1f} MB)")
    options = result.options
    quality = "" if options.image_format == "png" else f" q{options.quality}"
    layout = f"notes pages ({options.paper})" if options.notes else "a slide per page"
    title = ""
    if options.title_page:
        title = ", title page" + (f" with {result.thumbnail.name}" if result.thumbnail is not None else " (no thumbnail: `vidgen thumbnail` adds it)")
    print(f"pictures: {result.width}x{result.height} {options.image_format}{quality}; {layout}{title}; {result.bookmarks} bookmarks")
    return 0


def cmd_slides(args: argparse.Namespace) -> CommandResult:
    """Write a slide deck (HTML, or PDF with ``--format pdf``) of the video's key frames with the
    narration as speaker notes."""
    from vidgen.slides import DEFAULT_IMAGE_FORMAT, DEFAULT_QUALITY, make_slides

    started = time.monotonic()
    _slides_options(args)
    project = Project.load(args.project, variant=args.variant)
    if args.format == "pdf":
        return cmd_slides_pdf(args, project, started)
    result = make_slides(
        project,
        preview=not args.final,
        mode=args.mode,
        per_beat=args.per_beat,
        overlays=args.overlays,
        dedupe=not args.no_dedupe,
        image_format=args.image_format or DEFAULT_IMAGE_FORMAT,
        quality=args.quality if args.quality is not None else DEFAULT_QUALITY,
        max_width=args.max_width,
        audio=args.audio,
        separate=args.separate,
        output=Path(args.output).resolve() if args.output else None,
        jobs=args.jobs,
        force=args.force,
    )
    if args.json:
        return jsonout.slides_document(project, result, time.monotonic() - started)
    deck = result.deck
    reused = f", {len(deck.reused)} reused" if deck.reused else ""
    print(f"rendered {len(deck.rendered)} scene(s){reused}")
    note = f", {deck.merged} alike merged" if deck.merged else ""
    print(f"slides: {result.path}  ({len(deck.slides)} slides from {deck.stills} stills{note}, {result.bytes / 1e6:.1f} MB)")
    quality = "" if result.image_format == "png" else f" q{result.quality}"
    sound = f", {result.audio} narration MP3s" if result.audio else ""
    print(f"pictures: {result.width}x{result.height} {result.image_format}{quality}{sound}")
    if result.files_dir is not None:
        print(f"files: {result.files_dir}")
    return 0


def cmd_export(args: argparse.Namespace) -> CommandResult:
    """Export a part of the rendered video (a scene, or ``--from`` / ``--to``) as a GIF or an MP4 clip."""
    from vidgen.export import export_clip, export_gif

    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    output = Path(args.output).resolve() if args.output else None
    common = {"preview": args.preview, "scene": args.scene, "start": args.from_, "end": args.to, "width": args.width, "fps": args.fps, "output": output}
    if args.kind == "gif":
        if args.with_audio:
            raise VidgenError("--with-audio is for clips: a GIF has no sound")
        result = export_gif(project, max_mb=args.max_mb, **common)
    else:
        if args.max_mb is not None:
            raise VidgenError("--max-mb is for GIFs (a clip's size follows its length and resolution)")
        result = export_clip(project, audio=args.with_audio, **common)
    if args.json:
        return jsonout.export_document(project, result, args.preview, time.monotonic() - started)
    part = f"scene {result.scene}, " if result.scene else ""
    print(f"{result.kind}: {result.path}")
    print(f"part:  {part}{result.start:.2f}-{result.end:.2f} s of {result.source.name} ({result.end - result.start:.2f} s)")
    sound = ", with audio" if result.audio else ""
    print(f"size:  {result.width}x{result.height}, {result.fps:g} fps, {result.bytes / 1e6:.2f} MB ({result.method}{sound})")
    if len(result.attempts) > 1:
        tries = ", ".join(f"{a['width']} px {a['fps']:g} fps {a['bytes'] / 1e6:.2f} MB" for a in result.attempts)
        print(f"budget {result.max_mb:g} MB: {tries}")
    return 0


def cmd_lint(args: argparse.Namespace) -> CommandResult:
    """Check the layout of every beat-end still (rendering what is needed) and report problems."""
    from vidgen.lint import lint_project, report_lines

    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    if (not args.rule or "contrast" in args.rule) and project.config.lint.rules.contrast.severity != "off":
        for message in theme_warnings(project):  # the theme itself, as `vidgen validate` does
            logging.getLogger("vidgen").warning(message)
    result = lint_project(
        project,
        preview=not args.final,
        scenes=args.scene or None,
        rules=args.rule or None,
        fail_on=args.fail_on,
        jobs=args.jobs,
        force=args.force,
    )
    if args.json:
        return jsonout.lint_document(project, result, time.monotonic() - started)
    for line in report_lines(result, Path.cwd()):
        print(line)
    return 1 if result.failed else 0


def _print_scene_types() -> None:
    from vidgen import registry

    entries = registry.all()
    width = max((len(e.name) for e in entries), default=0)
    for entry in entries:
        marker = "  (overrides builtin)" if entry.overrides is not None else ""
        print(f"{entry.name:<{width}}  {entry.origin}{marker}")
        beats = entry.cls.beat_count_text()
        if beats is not None:
            print(f"    beats: {beats}")
        if entry.params_model is None:
            print("    params: free-form (no Params model)")
        for line in describe_params(entry.params_model):
            print(f"    {line}")
        if entry.cls.target_patterns:
            print(f"    targets: {', '.join(entry.cls.target_patterns)}")
    actions = registry.all_actions()
    if actions:
        print()
        print("actions (beat `actions:`, docs/CONFIG.md \"Beat actions\"):")
        width = max(len(a.name) for a in actions)
    for act in actions:
        marker = "  (overrides builtin)" if act.overrides is not None else ""
        undo = ", until" if act.cls.reversible else ""
        undo += ", undone by the beat's end" if act.cls.temporary else ""
        undo += ", undone when the next beat starts" if act.cls.until_next_beat else ""
        timing = f"run_time {act.cls.run_time:g} s{undo}" if act.cls.animates else "at its time, does not animate"
        print(f"{act.name:<{width}}  {act.origin}{marker}  ({timing})")
        for line in describe_params(act.cls.Options):
            print(f"    {line}")
    overlays = registry.all_overlays()
    if overlays:
        print()
        print("overlays (video `overlays:`, docs/CONFIG.md \"Overlays\"):")
        width = max(len(o.name) for o in overlays)
    for entry in overlays:
        marker = "  (overrides builtin)" if entry.overrides is not None else ""
        skip = f"  (lint skips: {', '.join(entry.cls.lint_skip)})" if entry.cls.lint_skip else ""
        print(f"{entry.name:<{width}}  {entry.origin}{marker}{skip}")
        for line in describe_params(entry.cls.Options):
            print(f"    {line}")


@contextmanager
def scene_types_session(path: str, lenient: bool = False) -> Iterator[tuple[Project | None, Theme]]:
    """Activate the scene types of the project at ``path`` (built-ins + its extensions) and yield
    ``(project, theme)``; with the default path and no config file in the current directory,
    only the built-ins (``project`` is ``None``, default theme). ``lenient`` loads a project
    whose config is invalid (see :func:`vidgen.schema.lenient_project`)."""
    from vidgen import extensions, registry
    from vidgen.schema import lenient_project

    if path == "." and not any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        with registry.isolated():
            extensions.load_builtins()
            yield None, Theme()
        return
    project = lenient_project(path) if lenient else Project.load(path)
    with extensions.project_session(project) as theme:
        yield project, theme


def cmd_list_scenes(args: argparse.Namespace) -> CommandResult:
    """Print every scene type (built-ins and the project's extensions) with its params."""
    with scene_types_session(args.project) as (project, _):
        if args.json:
            return jsonout.list_scenes_document(project)
        _print_scene_types()
    return 0


def cmd_list_themes(args: argparse.Namespace) -> CommandResult:
    """Print every theme preset (built-in and the project's) with its values and checks."""
    from vidgen import themelist

    with redirect_stdout(sys.stderr), scene_types_session(args.project) as (project, theme):
        entries = themelist.list_presets(theme)
        orientation = theme.orientation
        current = {"preset": theme.preset, "scale": theme.scale_setting, "scale_resolved": theme.scale}
    swatches = themelist.render_swatches(entries, Path(args.swatches)) if args.swatches else None
    if args.json:
        return jsonout.list_themes_document(project, orientation, current, entries, themelist.scales_json(), swatches)
    for line in themelist.summary_lines(entries, orientation):
        print(line)
    if swatches is not None:
        print(f"swatches: {swatches}")
    return 0


def sheet_theme(path: str, preset: str) -> Theme:
    """The theme an icon sheet is drawn in: the project's (``preset`` is ``project``; the
    default theme without a project) or the named preset (built-in or the project's)."""
    from vidgen.config import ThemeConfig

    with redirect_stdout(sys.stderr), scene_types_session(path) as (_, theme):
        if preset == "project":
            return theme
        if preset not in theme.presets:
            raise VidgenError(f"unknown theme preset '{preset}'; presets: {', '.join(theme.presets)} (or project)")
        return theme.derive(ThemeConfig(preset=preset))


def cmd_list_icons(args: argparse.Namespace) -> CommandResult:
    """Print the available icons (built-in and the project's), optionally filtered, and write a
    contact sheet of them."""
    from vidgen import iconlist
    from vidgen.icons import available_icons, search_icons

    root = None
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        root = find_config_file(args.project).resolve().parent
    icons = available_icons(root)
    iconlist.check_category(args.category, list(icons.values()))
    found = search_icons(icons, args.search, args.category)
    sheets: list[Path] = []
    if args.theme is not None and not args.sheet:
        raise VidgenError("--theme draws the --sheet in a theme's colours; add --sheet PNG")
    if args.sheet:
        filters = [f"search '{args.search}'" if args.search else "", f"category {args.category}" if args.category else ""]
        title = f"vidgen icons: {len(found)}" + "".join(f", {f}" for f in filters if f)
        theme = sheet_theme(args.project, args.theme) if args.theme is not None else None
        if theme is not None:
            title += f", theme {theme.preset or 'project'}"
        sheets = iconlist.render_sheets(found, Path(args.sheet), title, theme)
    if args.json:
        return jsonout.list_icons_document(
            root, args.search, args.category, found, iconlist.categories_json(list(icons.values())), sheets
        )
    for line in iconlist.summary_lines(found, len(icons)):
        print(line)
    for sheet in sheets:
        print(f"sheet: {sheet}")
    return 0


def cmd_list_sfx(args: argparse.Namespace) -> CommandResult:
    """Print the sound effects (built-in and the project's ``assets/sfx``) with what they sound
    like, and write previews."""
    from vidgen import sfx

    root = None
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        root = find_config_file(args.project).resolve().parent
    preview_dir = Path(args.render_dir).resolve() if args.render_dir else None
    entries = sfx.sound_entries(sfx.SoundLibrary(root), preview_dir)
    if args.json:
        return jsonout.list_sfx_document(root, entries, preview_dir)
    width = max(len(e["name"]) for e in entries)
    for e in entries:
        span = f" ({e['duration_range'][0]:g}-{e['duration_range'][1]:g} s)" if e["duration_range"] else ""
        level = f"{e['loudness']} LUFS, peak {e['peak_db']} dBFS" if e["loudness"] is not None else "silent"
        marker = "  (overrides builtin)" if e["overrides_builtin"] else ""
        print(f"{e['name']:<{width}}  {e['origin']}{marker}  {e['duration']:.2f} s{span}  {level}")
        for key in ("description", "use"):
            if e[key]:
                print(f"    {key}: {e[key]}")
    print(
        f"params (built-in sounds): duration (s, in the sound's range), pitch (semitones {sfx.PITCH_RANGE[0]:g} to "
        f"{sfx.PITCH_RANGE[1]:g}, default 0), intensity (0-1, default 0.5)"
    )
    print(f"level at gain 0: {sfx.LOUDNESS_TARGET:g} LUFS (about 7 dB under narration), peaks at most {sfx.PEAK_CEILING:g} dBFS")
    if preview_dir is not None:
        print(f"previews: {preview_dir} ({len(entries)} WAV files)")
    return 0


def cmd_list_music(args: argparse.Namespace) -> CommandResult:
    """Print the built-in music beds (what they sound like) and the project's ``assets/music``
    files, and write previews."""
    from vidgen import music

    root = None
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        root = find_config_file(args.project).resolve().parent
    preview_dir = Path(args.render_dir).resolve() if args.render_dir else None
    entries = music.music_entries(root, preview_dir)
    if args.json:
        return jsonout.list_music_document(root, entries, preview_dir)
    for e in entries:
        if e["origin"] == "builtin":
            tempo = f"{e['tempo']} BPM" if e["tempo"] else "no beat"
            print(f"{e['name']}  builtin  {e['key']}, {tempo}, {e['loop_seconds']:g} s loop")
            print(f"    description: {e['description']}")
            print(f"    chords: {' - '.join(e['chords'])}")
            print(f"    use: {e['use']}")
        else:
            level = f"{e['loudness']} LUFS" if e["loudness"] is not None else "silent"
            print(f"{e['name']}  project file  {e['duration']:.1f} s, {level} (played at {music.MUSIC_LEVEL:g} LUFS)")
    print(
        f"level at volume 0: {music.MUSIC_LEVEL:g} LUFS integrated (about 6.5 dB under narration), ducked "
        "12 dB under speech by default; a file anywhere under the project works as a source too"
    )
    if preview_dir is not None:
        print(f"previews: {preview_dir} (one loop of each bed as WAV)")
    return 0


def cmd_schema(args: argparse.Namespace) -> CommandResult:
    """Print the JSON Schema of video.yaml (or of one scene type's params, or of a scene)."""
    from vidgen import registry, schema

    # Extension modules may print while importing; stdout must hold only the schema.
    with redirect_stdout(sys.stderr), scene_types_session(args.project, lenient=True) as (project, theme):
        themes = schema.project_themes(project, theme)
        if args.scene is not None:
            entry = registry.find(args.scene)
            if entry is None:
                raise VidgenError(registry.unknown_type_message(args.scene))
            doc = schema.params_schema(entry, themes)
        elif args.all:
            doc = schema.scene_schema(registry.all(), themes)
        else:
            doc = schema.config_schema(registry.all(), themes)
    if args.json:
        return jsonout.schema_document(project, doc)
    _print_json(doc)
    return 0


def cmd_guide(args: argparse.Namespace) -> CommandResult:
    """Print the author guide for AI agents, one topic of it, or the list of topics (DESIGN.md §59)."""
    from vidgen.guide import find_topic, guide_text, guide_topics, topic_lines

    if args.list and args.topic is not None:
        raise VidgenError("--list lists every topic; give either a TOPIC or --list")
    topics = guide_topics()
    topic = find_topic(args.topic) if args.topic is not None else None
    text = None if args.list else (topic.text if topic is not None else guide_text())
    if args.json:
        return jsonout.guide_document(topic, topics, text)
    if text is None:
        for line in topic_lines(topics):
            print(line)
    else:
        print(text, end="")
    return 0


class UsageError(Exception):
    """A command-line usage error (raised instead of argparse's print-and-exit)."""

    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        super().__init__(message)
        self.parser = parser
        self.message = message


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser whose errors raise :class:`UsageError`, so ``--json`` can report them."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(self, message)


def build_parser() -> argparse.ArgumentParser:
    """The argparse parser for all subcommands."""
    parser = _Parser(
        prog="vidgen", description="Generate narrated, animated videos from a project folder."
    )
    parser.add_argument("--version", action="version", version=f"vidgen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def project_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("project", nargs="?", default=".", help="project dir or config file (default: .)")

    def json_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="print one JSON document on stdout (see docs/CONFIG.md)")

    p = sub.add_parser("init", help="scaffold a new project")
    p.add_argument("dir", help="directory to create (must not exist or be empty)")
    examples = sorted(d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir())
    p.add_argument("--example", choices=examples, default="minimal", help="template (default: minimal)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("guide", help="the author guide for AI agents making videos (workflow, pacing, scene types, ...)")
    p.add_argument("topic", nargs="?", metavar="TOPIC", help="print only this topic (vidgen guide --list shows them)")
    p.add_argument("--list", action="store_true", help="list the topics")
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("validate", help="check the project config")
    project_arg(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("list-scenes", help="list available scene types")
    project_arg(p)
    p.set_defaults(func=cmd_list_scenes)

    p = sub.add_parser("list-themes", help="list theme presets (built-in and the project's) and type scales")
    project_arg(p)
    p.add_argument("--swatches", "--sheet", dest="swatches", metavar="PNG", help="also write a swatch sheet of every preset to this PNG file (--sheet: same, as in list-icons)")
    p.set_defaults(func=cmd_list_themes)

    p = sub.add_parser("list-icons", help="list icons (built-in and the project's assets/icons)")
    project_arg(p)
    p.add_argument("--search", metavar="TEXT", help="only icons whose name or tags contain every word of TEXT")
    p.add_argument("--category", metavar="NAME", help="only icons of this category (tech, data, science, ...)")
    p.add_argument("--sheet", metavar="PNG", help="also draw the listed icons, labelled, into this PNG file")
    p.add_argument("--theme", nargs="?", const="project", metavar="PRESET", help="draw the sheet in a theme's colours: the project's (no value) or a preset's")
    p.set_defaults(func=cmd_list_icons)

    p = sub.add_parser("list-sfx", help="list sound effects (built-in and the project's assets/sfx) with descriptions")
    project_arg(p)
    p.add_argument("--render-dir", metavar="DIR", help="also write every sound at its defaults as DIR/<name>.wav")
    p.set_defaults(func=cmd_list_sfx)

    p = sub.add_parser("list-music", help="list background music beds (built-in and the project's assets/music) with descriptions")
    project_arg(p)
    p.add_argument("--render-dir", metavar="DIR", help="also write one loop of every bed as DIR/<name>.wav")
    p.set_defaults(func=cmd_list_music)

    p = sub.add_parser("tts", help="generate narration audio")
    project_arg(p)
    p.add_argument("--force", action="store_true", help="regenerate even if up to date")
    p.add_argument("--dry-run", action="store_true", help="only list what would be generated")
    p.add_argument("--beat", action="append", default=[], metavar="ID", help="only this beat (repeatable)")
    p.add_argument("--voice", action="append", default=[], metavar="NAME", help="only the beats of this voice (a voices: name or default; repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant (may have its own voice)")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("readback", help="transcribe the narration (speech to text) and compare it with the beat texts: misheard, missing or extra words")
    project_arg(p)
    p.add_argument("--variant", metavar="NAME", help="apply a named variant (its audio folder and language)")
    p.add_argument("--beat", action="append", default=[], metavar="ID", help="only this beat (repeatable)")
    p.add_argument("--max-wer", type=float, metavar="RATE", help="flag beats whose word error rate is above this, 0-1 (default: lint.rules.readback.max_wer, 0.1)")
    p.add_argument("--force", action="store_true", help="transcribe again even when a cached transcript exists")
    p.set_defaults(func=cmd_readback)

    p = sub.add_parser("imagegen", help="generate the pictures of generate: params that are missing (assets/generated/)")
    project_arg(p)
    p.add_argument("--dry-run", action="store_true", help="only list what would be generated, with an estimated cost (no API key needed)")
    p.add_argument("--force", action="store_true", help="generate again even when the picture exists")
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene's pictures (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant (its format, prompts and imagegen settings)")
    p.set_defaults(func=cmd_imagegen)

    p = sub.add_parser("translate-template", help="write or update a variant's translation file (every text to translate)")
    project_arg(p)
    p.add_argument("--variant", metavar="NAME", help="the variant to translate (its translations: file, else translations/NAME.yaml)")
    p.add_argument("--lang", metavar="TAG", help="language of the translation (BCP-47, e.g. pt-BR; default: the variant's language)")
    p.add_argument("--output", "-o", metavar="FILE", help="write here instead of the variant's translations: file")
    p.set_defaults(func=cmd_translate_template)

    p = sub.add_parser("render", help="render the video")
    project_arg(p)
    p.add_argument("--preview", action="store_true", help="fast low-resolution render")
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--no-audio", action="store_true", help="render without narration audio")
    p.add_argument("--keep-going", action="store_true", help="continue after a scene fails")
    p.add_argument("--jobs", "-j", type=int, default=1, metavar="N", help="render N scenes in parallel (default: 1)")
    p.add_argument("--frames", action="store_true", help="also save a PNG still at the end of each beat (build/.../frames/)")
    p.add_argument(
        "--frames-per-beat", type=int, metavar="N", help="save N evenly spaced stills per beat, the last at its end (implies --frames)"
    )
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("storyboard", help="contact sheets (PNG) of the video's frames, for review")
    project_arg(p)
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene's sheet (repeatable)")
    p.add_argument("--per-beat", type=int, default=1, metavar="N", help="stills per beat, the last at its end (default: 1)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    quality = p.add_mutually_exclusive_group()
    quality.add_argument("--preview", action="store_true", help="use the preview format (the default)")
    quality.add_argument("--final", action="store_true", help="use the final format (slower)")
    p.add_argument("--width", type=int, default=DEFAULT_SHEET_WIDTH, metavar="PX", help=f"sheet width in pixels (default: {DEFAULT_SHEET_WIDTH})")
    p.add_argument("--jobs", "-j", type=int, default=1, metavar="N", help="render N scenes in parallel (default: 1)")
    p.add_argument("--force", action="store_true", help="render the scenes again even if their stills are current")
    p.set_defaults(func=cmd_storyboard)

    p = sub.add_parser("thumbnail", help="write the video's thumbnail (<output>_thumbnail.png) from the thumbnail: config or a scene's frame")
    project_arg(p)
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--preview", action="store_true", help="take frames from the preview render (fast; ..._preview_thumbnail.png)")
    p.add_argument("--scene", metavar="ID", help="a frame of this scene instead of the configured thumbnail")
    p.add_argument("--beat", metavar="ID|N", help="with --scene: the beat (its id or number from 1; default: the last)")
    p.add_argument("--at", type=float, metavar="SECONDS", help="with --scene: seconds into the beat (or the scene); default: the beat's end")
    p.add_argument("--no-overlays", action="store_true", help="with --scene: the frame without captions, watermark... (renders the scene again)")
    p.add_argument("--jpeg", action="store_true", help="also write <output>_thumbnail.jpg under 2 MB")
    p.add_argument("--jobs", "-j", type=int, default=1, metavar="N", help="render N scenes in parallel when scenes must be rendered (default: 1)")
    p.set_defaults(func=cmd_thumbnail)

    p = sub.add_parser("slides", help="an HTML (or PDF) slide deck of the video's key frames, narration as speaker notes (exports/)")
    project_arg(p)
    p.add_argument("--format", choices=["html", "pdf"], default="html", help="an HTML deck (default) or a PDF (needs vidgen[pdf])")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant (a language variant gives translated notes)")
    quality = p.add_mutually_exclusive_group()
    quality.add_argument("--preview", action="store_true", help="use the preview format (the default; fast)")
    quality.add_argument("--final", action="store_true", help="use the final format (sharp slides; renders at full size)")
    p.add_argument("--mode", choices=["beat", "scene"], default="beat", help="a slide per beat (default) or per scene (its last beat's end)")
    p.add_argument("--per-beat", type=int, default=1, metavar="N", help="with --mode beat: N slides per beat, the last at its end (default: 1)")
    p.add_argument("--overlays", action=argparse.BooleanOptionalAction, default=True, help="show the video's overlays (captions, watermark...) on the slides (default: yes)")
    p.add_argument("--no-dedupe", action="store_true", help="keep consecutive slides that look the same (default: merged, notes joined)")
    p.add_argument("--image-format", choices=["webp", "jpeg", "png"], help="picture format (default: webp for HTML, jpeg for PDF; a PDF takes jpeg or png)")
    p.add_argument("--quality", type=int, metavar="Q", help="webp / jpeg quality 1-100 (default: 80 for HTML, 85 for PDF)")
    p.add_argument("--max-width", type=int, metavar="PX", help="scale the pictures down to this width")
    p.add_argument("--audio", action="store_true", help="HTML: include the beats' MP3s: Play then narrates the deck")
    p.add_argument("--separate", action="store_true", help="HTML: write pictures and MP3s into <name>_files/ beside the page instead of embedding them")
    p.add_argument("--notes", action="store_true", help="PDF: a notes page per slide (picture, narration, page number) instead of full-page slides")
    p.add_argument("--title-page", action="store_true", help="PDF: start with a title page (the thumbnail if `vidgen thumbnail` made one, title, author, date)")
    p.add_argument("--paper", choices=["a4", "letter"], help="PDF: paper of the notes pages (default: a4)")
    p.add_argument(
        "--output", "-o", metavar="FILE",
        help="write here instead of exports/<output>[_<variant>][_preview]_slides.html (PDF: _slides.pdf, _notes.pdf with --notes)",
    )
    p.add_argument("--jobs", "-j", type=int, default=1, metavar="N", help="render N scenes in parallel (default: 1)")
    p.add_argument("--force", action="store_true", help="render the scenes again even if their stills are current")
    p.set_defaults(func=cmd_slides)

    p = sub.add_parser("export", help="export a scene or part of the rendered video as a GIF or MP4 clip (exports/)")
    p.add_argument("kind", choices=["gif", "clip"], help="gif (palette GIF) or clip (MP4)")
    project_arg(p)
    p.add_argument("--scene", metavar="ID", help="this scene; --from / --to then count from its start")
    p.add_argument("--from", dest="from_", type=float, metavar="SECONDS", help="start (default: the scene's start, or 0)")
    p.add_argument("--to", type=float, metavar="SECONDS", help="end (default: the scene's end, or the video's)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--preview", action="store_true", help="export from the preview render")
    p.add_argument("--width", type=int, metavar="PX", help="width in pixels (GIF default: 480, 270 for 9:16; clip: the video's)")
    p.add_argument("--fps", type=float, metavar="F", help="frame rate (GIF default: 12; clip: the video's)")
    p.add_argument("--max-mb", type=float, metavar="MB", help="GIF: lower the frame rate, then the width, until the file is at most this big")
    p.add_argument("--with-audio", action="store_true", help="clip: keep the sound")
    p.add_argument("--output", "-o", metavar="FILE", help="write here instead of exports/<output>_<scene>[_<from>-<to>s].gif|mp4")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("lint", help="check the layout of the video's stills (text off frame, too small, ...)")
    project_arg(p)
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene (repeatable)")
    p.add_argument("--rule", action="append", default=[], metavar="NAME", help="only this rule (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    quality = p.add_mutually_exclusive_group()
    quality.add_argument("--preview", action="store_true", help="use the preview format (the default)")
    quality.add_argument("--final", action="store_true", help="use the final format (slower)")
    p.add_argument(
        "--fail-on", choices=["error", "warning", "info", "never"], help="lowest severity that fails (default: lint.fail_on, error)"
    )
    p.add_argument("--jobs", "-j", type=int, default=1, metavar="N", help="render N scenes in parallel (default: 1)")
    p.add_argument("--force", action="store_true", help="render the scenes again even if their stills are current")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("schema", help="print the JSON Schema of video.yaml")
    project_arg(p)
    which = p.add_mutually_exclusive_group()
    which.add_argument("--scene", metavar="TYPE", help="only the params schema of this scene type")
    which.add_argument("--all", action="store_true", help="the schema of one scene, with every type's params")
    p.set_defaults(func=cmd_schema)

    for name in JSON_COMMANDS:
        json_arg(sub.choices[name])
    return parser


class _LevelFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname.lower()}: {record.getMessage()}"


class _CollectHandler(logging.Handler):
    """Collects log records as ``--json`` ``warnings`` entries."""

    def __init__(self, into: list[dict[str, Any]]) -> None:
        super().__init__(logging.WARNING)
        self.into = into

    def emit(self, record: logging.LogRecord) -> None:
        self.into.append(jsonout.warning(record.getMessage()))


@contextmanager
def _cli_logging(collect: list[dict[str, Any]] | None = None) -> Iterator[None]:
    """Print vidgen's log warnings as ``warning: <message>`` on stderr while a command runs
    (and, if ``collect`` is given, also append them to it as JSON ``warnings`` entries)."""
    logger = logging.getLogger("vidgen")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_LevelFormatter())
    handlers: list[logging.Handler] = [handler] if collect is None else [handler, _CollectHandler(collect)]
    saved = (logger.level, logger.propagate)
    for h in handlers:
        logger.addHandler(h)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        yield
    finally:
        for h in handlers:
            logger.removeHandler(h)
        logger.setLevel(saved[0])
        logger.propagate = saved[1]


def _print_json(doc: dict[str, Any]) -> None:
    print(jsonout.dumps(doc), flush=True)


def _usage_error(exc: UsageError, argv: Sequence[str], json_mode: bool) -> int:
    """Report a command-line error like argparse does, or as a JSON document; exit code 2."""
    if json_mode:
        command = next((a for a in argv if not a.startswith("-")), None)
        _print_json(jsonout.envelope(command, False, error=jsonout.error_json("usage", exc.message)))
    else:
        exc.parser.print_usage(sys.stderr)
        print(f"{exc.parser.prog}: error: {exc.message}", file=sys.stderr)
    return 2


def _run_json(func: Callable[[argparse.Namespace], CommandResult], args: argparse.Namespace) -> int:
    """Run a command with ``--json``: everything it prints goes to stderr, then its document (or
    the error document) is printed on stdout; exit code 0 if ``ok``, else 1."""
    warnings: list[dict[str, Any]] = []
    try:
        with _cli_logging(warnings), redirect_stdout(sys.stderr):
            doc = func(args)
    except VidgenError as exc:
        doc = jsonout.error_document(args.command, exc)
    except BrokenPipeError:
        raise
    except Exception as exc:  # noqa: BLE001 - an agent needs a JSON answer even for a bug
        details = {"traceback": traceback.format_exc()}
        error = jsonout.error_json("internal", f"{type(exc).__name__}: {exc}", details=details)
        doc = jsonout.envelope(args.command, False, error=error)
    assert isinstance(doc, dict)
    doc["warnings"] = warnings + doc["warnings"]
    _print_json(doc)
    return 0 if doc["ok"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the process exit code."""
    for stream in (sys.stdout, sys.stderr):
        # A Windows console redirected to a file/pipe uses a legacy code page (cp1252...):
        # never crash on a character it cannot show (titles, paths, tracebacks).
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        try:
            args = build_parser().parse_args(argv)
        except UsageError as exc:
            return _usage_error(exc, argv, "--json" in argv)
        if getattr(args, "json", False):
            return _run_json(args.func, args)
        try:
            with _cli_logging():
                result = args.func(args)
        except VidgenError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        assert isinstance(result, int)
        return result
    except BrokenPipeError:  # output piped into e.g. `head` or `more`, which stopped reading
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - silence the flush at exit
        except OSError:
            pass
        return 1
