"""Command-line interface (DESIGN.md §8)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import traceback
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from vidgen import __version__
from vidgen.config import validation_error_lines
from vidgen.errors import VidgenError
from vidgen.project import CONFIG_NAMES, Project

TEMPLATES_DIR = Path(__file__).parent / "templates"
#: Template files copied as ``.<name>`` by ``vidgen init``.
TEMPLATE_DOTFILES: tuple[str, ...] = ("gitignore",)


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
    return 0


def check_project(project: Project) -> list[str]:
    """Checks beyond config structure; returns problems found (empty if none).

    Loads built-ins and the project's extensions in isolation (nothing leaks into the caller's
    registry), checks that every scene ``type`` is registered, validates each scene's
    ``params`` against the type's ``Params`` model (theme tokens against the project's theme)
    and runs the type's ``validate_project`` (e.g. missing asset files).
    """
    from vidgen import extensions, registry

    problems: list[str] = []
    try:
        with extensions.project_session(project) as theme:
            for i, scene in enumerate(project.config.scenes):
                entry = registry.find(scene.type)
                if entry is None:
                    problems.append(f"scenes[{i}].type: {registry.unknown_type_message(scene.type)}")
                    continue
                beat_problem = entry.cls.check_beat_count(len(scene.beats))
                if beat_problem is not None:
                    problems.append(f"scenes[{i}].beats: type '{scene.type}' {beat_problem}")
                try:
                    params = entry.cls.validate_params(scene.params, theme)
                except ValidationError as exc:
                    problems.extend(validation_error_lines(exc, ("scenes", i, "params")))
                    continue
                try:
                    problems.extend(f"scenes[{i}].params.{p}" for p in _project_checks(entry, params, project))
                except VidgenError as exc:
                    problems.append(f"scenes[{i}]: {exc}")
    except VidgenError as exc:
        problems.append(str(exc))
    return problems


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


def cmd_validate(args: argparse.Namespace) -> int:
    """Load the project (and every variant), check it and print a short summary."""
    project = Project.load(args.project)
    base = check_project(project)
    problems = list(base)
    for name in project.config.variants:
        problems.extend(
            f"[variant {name}] {p}" for p in check_project(Project.load(args.project, variant=name)) if p not in base
        )
    if problems:
        lines = [f"{project.config_file.name}: invalid project"]
        for problem in problems:
            lines.extend(f"  {line}" for line in problem.splitlines())
        raise VidgenError("\n".join(lines))

    config = project.config
    n_beats = sum(1 for _ in project.beats())
    print(f"title:     {config.title}")
    print(f"scenes:    {len(config.scenes)}")
    print(f"beats:     {n_beats}")
    print(f"duration:  ~{_format_seconds(project.estimated_duration())} (estimated from word count)")
    if config.variants:
        print(f"variants:  {', '.join(config.variants)}")
    for line in audio_summary_lines(project):
        print(line)
    print("ok")
    return 0


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


def cmd_tts(args: argparse.Namespace) -> int:
    """Generate narration audio for beats whose MP3 is missing or stale."""
    from vidgen import extensions
    from vidgen.tts.run import run_tts

    project = Project.load(args.project, variant=args.variant)
    with extensions.project_session(project):
        run_tts(project, beat_ids=args.beat, force=args.force, dry_run=args.dry_run)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Render every scene (or only ``--scene`` ones), join them and write the MP4 and SRT."""
    from vidgen.render.pipeline import render_project

    if args.jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    project = Project.load(args.project, variant=args.variant)
    result = render_project(
        project,
        preview=args.preview,
        scenes=args.scene or None,
        no_audio=args.no_audio,
        keep_going=args.keep_going,
        jobs=args.jobs,
    )
    reused = f", {len(result.reused)} reused" if result.reused else ""
    print(f"rendered {len(result.rendered)} scene(s){reused}")
    print(f"video:     {result.output}")
    print(f"subtitles: {result.srt}")
    print(f"duration:  {_format_seconds(result.duration)} ({result.duration:.2f} s)")
    return 0


def _type_name(annotation: Any, metadata: Sequence[Any] = ()) -> str:
    """Readable type: ``color`` / ``size`` for theme tokens, ``a | b`` for unions and literals."""
    import types
    import typing

    from vidgen.scene import ThemeToken

    for meta in metadata:
        if isinstance(meta, ThemeToken):
            return meta.kind
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if origin is typing.Annotated:
        return _type_name(args[0], annotation.__metadata__)
    if origin in (typing.Union, types.UnionType):
        return " | ".join(_type_name(a) for a in args)
    if origin is typing.Literal:
        return " | ".join(repr(a) for a in args)
    if origin is not None and args:
        name = getattr(origin, "__name__", str(origin))
        return f"{name}[{', '.join(_type_name(a) for a in args)}]"
    if annotation is type(None):
        return "None"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _nested_models(annotation: Any) -> list[type[BaseModel]]:
    """Pydantic models used inside a field type (``Ring``, ``list[Ring]``, ``Ring | None``...)."""
    import typing

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for arg in typing.get_args(annotation):
        found += [m for m in _nested_models(arg) if m not in found]
    return found


def describe_params(model: type[BaseModel] | None, indent: str = "", _seen: tuple[type, ...] = ()) -> list[str]:
    """``name: type [= default]`` for each field of a ``Params`` model (empty for plain dicts);
    the fields of nested models follow their field, indented."""
    if model is None:
        return []
    lines = []
    for name, field in model.model_fields.items():
        line = f"{indent}{name}: {_type_name(field.annotation, field.metadata)}"
        if not field.is_required():
            default = field.get_default(call_default_factory=True)
            line += f" = {default!r}"
        lines.append(line)
        for nested in _nested_models(field.annotation):
            if nested not in _seen:
                lines += describe_params(nested, indent + "    ", (*_seen, model, nested))
    return lines


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


def cmd_list_scenes(args: argparse.Namespace) -> int:
    """Print every scene type (built-ins and the project's extensions) with its params."""
    from vidgen import extensions, registry

    if args.project == "." and not any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        # No project here: list the built-ins only.
        with registry.isolated():
            extensions.load_builtins()
            _print_scene_types()
        return 0
    project = Project.load(args.project)
    with extensions.project_session(project):
        _print_scene_types()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The argparse parser for all subcommands."""
    parser = argparse.ArgumentParser(
        prog="vidgen", description="Generate narrated, animated videos from a project folder."
    )
    parser.add_argument("--version", action="version", version=f"vidgen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def project_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("project", nargs="?", default=".", help="project dir or config file (default: .)")

    p = sub.add_parser("init", help="scaffold a new project")
    p.add_argument("dir", help="directory to create (must not exist or be empty)")
    examples = sorted(d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir())
    p.add_argument("--example", choices=examples, default="minimal", help="template (default: minimal)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="check the project config")
    project_arg(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("list-scenes", help="list available scene types")
    project_arg(p)
    p.set_defaults(func=cmd_list_scenes)

    p = sub.add_parser("tts", help="generate narration audio")
    project_arg(p)
    p.add_argument("--force", action="store_true", help="regenerate even if up to date")
    p.add_argument("--dry-run", action="store_true", help="only list what would be generated")
    p.add_argument("--beat", action="append", default=[], metavar="ID", help="only this beat (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant (may have its own voice)")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("render", help="render the video")
    project_arg(p)
    p.add_argument("--preview", action="store_true", help="fast low-resolution render")
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--no-audio", action="store_true", help="render without narration audio")
    p.add_argument("--keep-going", action="store_true", help="continue after a scene fails")
    p.add_argument("--jobs", "-j", type=int, default=1, metavar="N", help="render N scenes in parallel (default: 1)")
    p.set_defaults(func=cmd_render)
    return parser


class _LevelFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname.lower()}: {record.getMessage()}"


@contextmanager
def _cli_logging() -> Iterator[None]:
    """Print vidgen's log warnings as ``warning: <message>`` on stderr while a command runs."""
    logger = logging.getLogger("vidgen")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_LevelFormatter())
    saved = (logger.level, logger.propagate)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(saved[0])
        logger.propagate = saved[1]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the process exit code."""
    for stream in (sys.stdout, sys.stderr):
        # A Windows console redirected to a file/pipe uses a legacy code page (cp1252...):
        # never crash on a character it cannot show (titles, paths, tracebacks).
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    try:
        with _cli_logging():
            return args.func(args)
    except VidgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # output piped into e.g. `head` or `more`, which stopped reading
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - silence the flush at exit
        except OSError:
            pass
        return 1
