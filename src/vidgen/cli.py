"""Command-line interface (DESIGN.md §8)."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from vidgen import __version__
from vidgen.config import validation_error_lines
from vidgen.errors import VidgenError
from vidgen.project import CONFIG_NAMES, Project

TEMPLATES_DIR = Path(__file__).parent / "templates"


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
    config_file = target / "video.yaml"
    title = json.dumps(target.resolve().name.replace("_", " ").replace("-", " ").title())
    config_file.write_text(
        config_file.read_text(encoding="utf-8").replace("__TITLE__", title), encoding="utf-8"
    )
    print(f"created project in {target}")
    print("next: edit video.yaml, then run `vidgen validate`, `vidgen tts` and `vidgen render`")
    return 0


def check_project(project: Project) -> list[str]:
    """Checks beyond config structure; returns problems found (empty if none).

    Loads built-ins and the project's extensions in isolation (nothing leaks into the caller's
    registry), checks that every scene ``type`` is registered and validates each scene's
    ``params`` against the type's ``Params`` model.
    """
    from vidgen import extensions, registry

    problems: list[str] = []
    try:
        with extensions.project_session(project):
            for i, scene in enumerate(project.config.scenes):
                entry = registry.find(scene.type)
                if entry is None:
                    problems.append(f"scenes[{i}].type: {registry.unknown_type_message(scene.type)}")
                    continue
                try:
                    entry.cls.validate_params(scene.params)
                except ValidationError as exc:
                    problems.extend(validation_error_lines(exc, ("scenes", i, "params")))
    except VidgenError as exc:
        problems.append(str(exc))
    return problems


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


def _type_name(annotation: Any) -> str:
    if isinstance(annotation, type) and not getattr(annotation, "__args__", None):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def describe_params(model: type[BaseModel] | None) -> list[str]:
    """``name: type [= default]`` for each field of a ``Params`` model (empty for plain dicts)."""
    if model is None:
        return []
    lines = []
    for name, field in model.model_fields.items():
        line = f"{name}: {_type_name(field.annotation)}"
        if not field.is_required():
            default = field.get_default(call_default_factory=True)
            line += f" = {default!r}"
        lines.append(line)
    return lines


def _print_scene_types() -> None:
    from vidgen import registry

    entries = registry.all()
    width = max((len(e.name) for e in entries), default=0)
    for entry in entries:
        marker = "  (overrides builtin)" if entry.overrides is not None else ""
        print(f"{entry.name:<{width}}  {entry.origin}{marker}")
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


def _not_implemented(step: int) -> Callable[[argparse.Namespace], int]:
    def run(args: argparse.Namespace) -> int:
        raise VidgenError(f"'vidgen {args.command}' is not implemented yet (step {step})")

    return run


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
    p.set_defaults(func=_not_implemented(4))
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
    args = build_parser().parse_args(argv)
    try:
        with _cli_logging():
            return args.func(args)
    except VidgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
