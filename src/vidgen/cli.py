"""Command-line interface (DESIGN.md §8)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from vidgen import __version__
from vidgen.errors import VidgenError
from vidgen.project import Project

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

    Step 1 validates structure only (done by ``Project.load``). The registry step adds here:
    load extensions, check that every scene ``type`` is registered, validate ``params``.
    """
    return []


def cmd_validate(args: argparse.Namespace) -> int:
    """Load the project (and every variant) and print a short summary."""
    project = Project.load(args.project)
    problems = check_project(project)
    for name in project.config.variants:
        problems.extend(check_project(Project.load(args.project, variant=name)))
    if problems:
        raise VidgenError("\n".join([f"{project.config_file.name}: invalid project", *problems]))

    config = project.config
    n_beats = sum(1 for _ in project.beats())
    print(f"title:     {config.title}")
    print(f"scenes:    {len(config.scenes)}")
    print(f"beats:     {n_beats}")
    print(f"duration:  ~{_format_seconds(project.estimated_duration())} (estimated from word count)")
    if config.variants:
        print(f"variants:  {', '.join(config.variants)}")
    print("ok")
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
    p.set_defaults(func=_not_implemented(2))

    p = sub.add_parser("tts", help="generate narration audio")
    project_arg(p)
    p.add_argument("--force", action="store_true", help="regenerate even if up to date")
    p.add_argument("--dry-run", action="store_true", help="only list what would be generated")
    p.add_argument("--beat", action="append", default=[], metavar="ID", help="only this beat (repeatable)")
    p.set_defaults(func=_not_implemented(3))

    p = sub.add_parser("render", help="render the video")
    project_arg(p)
    p.add_argument("--preview", action="store_true", help="fast low-resolution render")
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--no-audio", action="store_true", help="render without narration audio")
    p.add_argument("--keep-going", action="store_true", help="continue after a scene fails")
    p.set_defaults(func=_not_implemented(4))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except VidgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
