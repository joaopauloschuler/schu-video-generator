"""Command-line interface (DESIGN.md §8)."""

from __future__ import annotations

import argparse
import difflib
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
from vidgen.render.jobs import AUTO as AUTO_JOBS, PER_JOB_BYTES, JobsChoice, choose_jobs
from vidgen.sheets import DEFAULT_WIDTH as DEFAULT_SHEET_WIDTH
from vidgen.theme import Theme

TEMPLATES_DIR = Path(__file__).parent / "templates"
#: Template files copied as ``.<name>`` by ``vidgen init``.
TEMPLATE_DOTFILES: tuple[str, ...] = ("gitignore",)
#: Subcommands that accept ``--json``.
JSON_COMMANDS: tuple[str, ...] = (
    "validate", "list-scenes", "list-themes", "list-icons", "list-sfx", "list-music", "list-pronunciation", "render", "schema", "storyboard", "lint",
    "thumbnail", "export", "translate-template", "slides", "readback", "guide", "gallery", "plan",
    "init", "tts", "imagegen", "character-sheet", "direct", "screenplay", "cast", "animatic", "music",
)

#: What a command function returns: an exit code, or (with ``--json``) the JSON document.
CommandResult = int | dict[str, Any]

#: ``validate_project`` messages start with the param they are about: ``"path: file not found"``.
_PARAM_MESSAGE = re.compile(r"^([A-Za-z_][\w.\[\]]*): (.*)$", re.DOTALL)


def _format_seconds(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}:{secs:02d}"


def cmd_init(args: argparse.Namespace) -> CommandResult:
    """Scaffold a new project from a template."""
    target = Path(args.dir)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise VidgenError(f"{target} already exists and is not an empty directory")
    scaffold_project(target, args.example)
    if args.json:
        return jsonout.init_document(target, args.example)
    print(f"created project in {target}")
    print("next: edit video.yaml, then `vidgen validate`, `vidgen storyboard` (look at the PNGs), `vidgen lint`; "
          "when it reads well, `vidgen tts` and `vidgen render`")
    print("guide: `vidgen guide` (how to make a good video: workflow, pacing, scene types; for AI agents too)")
    return 0


def scaffold_project(target: Path, example: str = "minimal") -> None:
    """Copy the ``example`` template into ``target`` (created if needed): its files with dot files
    restored, ``assets/`` and ``extensions/``, the title derived from the folder name."""
    template = TEMPLATES_DIR / example
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


def cmd_plan(args: argparse.Namespace) -> CommandResult:
    """Write a draft project from a Markdown outline or a plain-text script (DESIGN.md §61)."""
    from vidgen.languages import normalize_language
    from vidgen.outline import parse_outline
    from vidgen.plan import PlanOptions, make_plan
    from vidgen.plan_yaml import write_plan
    from vidgen.presets import BUILTIN_PRESETS

    source = Path(args.input)
    if not source.is_file():
        raise VidgenError(f"{source}: no such file (give a Markdown outline or a plain-text script)")
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise VidgenError(f"{source}: cannot read it as UTF-8 text: {exc}") from None
    try:
        language = normalize_language(args.language) if args.language else None
    except ValueError as exc:
        raise VidgenError(f"--language: {exc}") from None
    if args.preset not in BUILTIN_PRESETS:
        close = difflib.get_close_matches(args.preset, list(BUILTIN_PRESETS), n=1)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        raise VidgenError(f"unknown theme preset '{args.preset}'{hint} (presets: {', '.join(BUILTIN_PRESETS)})")
    blocks = parse_outline(text, plain=source.suffix.lower() in (".txt", ".text"))
    if not blocks:
        raise VidgenError(f"{source}: no text to plan from")
    options = PlanOptions(
        title=args.title,
        default_title=source.stem.replace("_", " ").replace("-", " ").strip().capitalize() or "Untitled",
        language=language,
        base=source.resolve().parent,
    )
    plan = make_plan(blocks, options)
    output = Path(args.output) if args.output else Path(source.stem)
    result = write_plan(plan, output, fmt=args.format, preset=args.preset, source=source.name, force=args.force)
    project = Project.load(result.config)
    problems, _ = validate_all(project, keep_going=True)
    if args.json:
        return jsonout.plan_document(project, plan, result, problems, args.format)
    beats = sum(len(s.beats) for s in plan.scenes)
    print(
        f"planned {len(plan.scenes)} scenes ({beats} beats), about {_format_seconds(project.estimated_duration())}; "
        f"{plan.todo_count} TODOs to review (# TODO: in the config)"
    )
    id_width = max((len(s.id) for s in plan.scenes), default=0)
    type_width = max((len(s.type) for s in plan.scenes), default=0)
    for scene in plan.scenes:
        count = f"{len(scene.beats)} beat{'s' if len(scene.beats) != 1 else ''}" if scene.beats else f"{scene.duration:g} s"
        print(f"  {scene.id:<{id_width}}  {scene.type:<{type_width}}  {count:<8}  {scene.reason}")
    created = "created project in" if result.created else "wrote"
    print(f"{created} {result.root if result.created else result.config}")
    for rel in result.assets:
        print(f"  copied {rel}")
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    print("next: refine the draft (read its # plan: and # TODO: comments), then `vidgen validate`, `vidgen storyboard`, `vidgen lint`")
    return 1 if problems else 0


def cmd_screenplay(args: argparse.Namespace) -> CommandResult:
    """Write a stage project from a screenplay (DESIGN.md §69.25)."""
    from vidgen.plan_yaml import commented_yaml, write_project
    from vidgen.random_cast import parse_species
    from vidgen.screenplay import parse_screenplay, screenplay_project

    source = Path(args.input)
    if not source.is_file():
        raise VidgenError(f"{source}: no such file (give a screenplay, e.g. story.md)")
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise VidgenError(f"{source}: cannot read it as UTF-8 text: {exc}") from None
    try:
        play = parse_screenplay(text)
    except VidgenError as exc:
        raise VidgenError(f"{source}: {exc}") from None
    output = Path(args.out) if args.out else Path(source.stem)
    cast, include = None, None
    if args.cast:
        from vidgen.includes import project_relative, read_include_file

        cast_file = Path(args.cast)
        if not cast_file.is_file():
            raise VidgenError(f"--cast {cast_file}: no such file (give an include file with characters, voices and sets)")
        cast = read_include_file(cast_file)
        folder = output.parent if output.suffix.lower() in (".yaml", ".yml") else output
        include = project_relative(cast_file.resolve(), folder.resolve())
    draft = screenplay_project(
        play, source.stem.replace("_", " ").replace("-", " ").strip().capitalize() or "Untitled", cast, include,
        species=parse_species(args.species), seed=args.seed,
    )
    header = [
        f"# Written by `vidgen screenplay` from {source.name}: the screenplay's scenes as stage scenes, one",
        "# beat per line. Characters without a declaration got a generated look and a voice; auto_direct adds",
        "# the looks, reactions, gestures and close-ups. Check the # TODO: lines, then: vidgen validate,",
        "# vidgen storyboard, vidgen lint (`vidgen guide cartoons`).",
    ]
    scene_notes = [list(todos) for todos in draft.scene_todos]
    key_notes = {"characters": [f"generated: {', '.join(draft.generated)} (look and colours to adjust; `vidgen character-sheet --all`)"]} if draft.generated else {}
    if draft.notes:
        key_notes["voices" if "voices" in draft.config else "voice"] = [f"TODO: {n}" for n in draft.notes]
    yaml_text = commented_yaml(draft.config, header, key_notes, scene_notes, draft.beat_todos)
    result = write_project(yaml_text, output, force=args.force)
    project = Project.load(result.config)
    problems, _ = validate_all(project, keep_going=True)
    if args.json:
        return jsonout.screenplay_document(project, draft, result, problems)
    beats = sum(len(s.get("beats", [])) for s in draft.config["scenes"])   # a silent card has none
    print(
        f"wrote {len(draft.config['scenes'])} scenes ({beats} beats), {len(project.config.characters)} characters, "
        f"about {_format_seconds(project.estimated_duration())}; {draft.todo_count} TODOs to review (# TODO: in the config)"
    )
    print(f"{'created project in' if result.created else 'wrote'} {result.root if result.created else result.config}")
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    print("next: `vidgen character-sheet --all`, `vidgen direct`, `vidgen storyboard`, `vidgen lint`; then `vidgen tts`")
    return 1 if problems else 0


def cmd_cast(args: argparse.Namespace) -> CommandResult:
    """Write a random, well-contrasted cast as an include file (DESIGN.md §69.49)."""
    from vidgen.cartoon.contrast import MIN_CONTRAST
    from vidgen.config import CharacterEntry
    from vidgen.languages import normalize_language
    from vidgen.random_cast import cast_yaml, parse_species, random_cast

    species = parse_species(args.species)
    try:
        language = normalize_language(args.language) if args.language else None
    except ValueError as exc:
        raise VidgenError(f"--language: {exc}") from None
    out = Path(args.out)
    if out.suffix.lower() not in (".yaml", ".yml"):
        raise VidgenError(f"--out {out}: give a .yaml file (the cast is an include file)")
    if out.exists() and not args.force:
        raise VidgenError(f"{out} already exists (use --force to replace it)")
    voice = {"provider": args.provider, **({"voice": args.narrator} if args.narrator else {}), **({"model": args.model} if args.model else {})}
    if args.provider == "kokoro" and not args.narrator:
        voice["voice"] = "bf_emma"   # vidgen screenplay's narrator
    cast = random_cast(args.random, args.seed, species=species, voice=voice, language=language)
    for entry in cast.characters:   # what vidgen wrote must load (a bug otherwise, never the user's fault)
        CharacterEntry.model_validate(entry)
    command = f"vidgen cast --random {args.random} --seed {args.seed}" + (f" --species {' '.join(species)}" if species != ["human"] else "")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cast_yaml(cast, command), encoding="utf-8")
    if args.json:
        return jsonout.cast_document(out, cast, args.seed, species, voice["provider"], MIN_CONTRAST)
    print(f"wrote {len(cast.characters)} characters to {out} (lowest contrast between two: {cast.lowest_contrast:.2f}; lint look_alike warns below {MIN_CONTRAST:g})")
    for entry in cast.characters:
        look = entry["look"]
        said = cast.voices[entry["voice"]].get("voice", "set by hand")
        print(f"  {entry['name']:<6} {cast.kinds[entry['name']]:<9} voice {said:<12} {look.get('species', 'human')}, body {look['body']}, "
              f"hair {look.get('hair', 'none')}, clothes {entry['colors']['clothes']}")
    for note in cast.notes:
        print(f"TODO: {note}", file=sys.stderr)
    print(f"next: `include: [{out.name}]` in video.yaml or `vidgen screenplay STORY.md --cast {out}`; `vidgen character-sheet --all`")
    return 0


def project_problems(project: Project) -> list[Problem]:
    """Checks beyond config structure; returns the problems found (empty if none).

    Loads built-ins and the project's extensions in isolation (nothing leaks into the caller's
    registry), checks that every scene ``type`` is registered, validates each scene's
    ``params`` against the type's ``Params`` model (theme tokens against the project's theme)
    and runs the type's ``validate_project`` (e.g. missing asset files); checks the beats'
    ``actions`` (action names, options, targets of the scene) and the ``overlays`` (types,
    options, scene references; DESIGN.md §41); also checks the project's ``assets/icons``,
    the sounds of the scenes' ``sfx:`` lists (§47), the ``music:`` sources (§48), the
    ``soundfont:`` file (§81), a designed
    ``thumbnail:``'s icon, image, preset and background (§53) and the ``characters:`` colours,
    SVG files (§69) and the shapes of their own poses (§69.3), and the host's floor colour and a
    scene's own ``host:`` on a type that draws none (§71). Each problem points where its
    value is written: an ``include:`` file, a set (§69.35).
    """
    from vidgen import extensions, registry
    from vidgen.actions import scene_actions
    from vidgen.carry import carry_problems
    from vidgen.cartoon.cast import character_color_problems, character_look_problems, character_pose_problems
    from vidgen.cartoon.host import host_color_problems
    from vidgen.icons import PROJECT_ICONS_DIR, project_icons
    from vidgen.imagegen import imagegen_problems
    from vidgen.music import config_problems as music_problems
    from vidgen.overlays import overlay_problems
    from vidgen.sfx import config_problems as sfx_problems
    from vidgen.soundfont import soundfont_problems
    from vidgen.thumbnail import thumbnail_problems
    from vidgen.terms import term_color_problems
    from vidgen.transitions import color_problems as transition_color_problems
    from vidgen.transitions import iris_problems
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
                if scene.host not in (None, False) and not entry.cls.takes_host:
                    problems.append(Problem(f"scenes[{i}].host", f"type '{scene.type}' draws no host (remove host: here; the video's host: skips it)"))
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
            problems.extend(character_color_problems(project.config, theme))
            problems.extend(host_color_problems(project.config, theme))
            problems.extend(character_look_problems(project.config, project.root))
            problems.extend(character_pose_problems(project.config, project.root))
            problems.extend(transition_color_problems(project.config, theme))
            problems.extend(Problem(loc, message) for loc, message in term_color_problems(project.config, theme))
            problems.extend(iris_problems(project.config))
            problems.extend(carry_problems(project.config))
            problems.extend(Problem(loc, message) for loc, message in sfx_problems(project.config, project.root))
            problems.extend(Problem(loc, message) for loc, message in music_problems(project.config, project.root))
            problems.extend(Problem(loc, message) for loc, message in soundfont_problems(project.config.soundfont, project.root))
            problems.extend(thumbnail_problems(project, theme))
            problems.extend(Problem(loc, message) for loc, message in imagegen_problems(project))
    except VidgenError as exc:
        problems.extend(exc.problems or [Problem("", str(exc))])
    return project.attributed(problems)


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
    """``pronunciation:`` entries that match no beat, never apply or collide (DESIGN.md §45);
    built-in entries are not reported (§88)."""
    from vidgen.pronunciation import pronunciation_warnings as check

    return check(project.pronunciation, ((beat.id, beat.text) for _, beat in project.beats()), project.beat_pronunciation)


def validate_warnings(project: Project) -> list[str]:
    """What ``vidgen validate`` warns about (not problems): :func:`theme_warnings`,
    :func:`pronunciation_warnings`, named voices no beat uses and transitions that hold the
    scene before them longer (DESIGN.md §49), carries through a transition that moves them
    (§50), a YouTube chapter list YouTube would ignore (§52), texts a translation file leaves in
    the source language and base pronunciations kept in another language (§54), generated
    pictures not made yet and prompts asking for words in a picture (§58), OpenRouter TTS models
    and voices not in the bundled list and ``timestamps`` it cannot honour (§66), and SVG
    characters' unavailable actions and part warnings (§69.2), parts the characters' own
    poses name that they do not have (§69.3), characters sharing a voice and beat actions on a
    character that lacks the parts they need (§69.11), front views asked of SVG characters
    (§69.44), a host speaking only in its own voice without one (§71), lines that overlap a
    line of their own voice (§69.34), dubbed voices that lose their kind or merge (§80) and
    composed music without the ``music`` extra or the SoundFont (§85)."""
    from vidgen.carry import carry_warnings
    from vidgen.cartoon.cast import acting_warnings, character_look_warnings, character_pose_warnings, front_view_warnings, shared_voice_warnings
    from vidgen.cartoon.host import host_warnings
    from vidgen.chapter_export import chapter_warnings
    from vidgen.dubbing import dub_warnings
    from vidgen.imagegen import imagegen_warnings
    from vidgen.music import music_warnings
    from vidgen.overlap import overlap_warnings
    from vidgen.transitions import transition_warnings
    from vidgen.translation import language_warnings, translation_warnings
    from vidgen.tts import tts_warnings
    from vidgen.voices import voice_warnings

    return (
        theme_warnings(project)
        + pronunciation_warnings(project)
        + voice_warnings(project.config, project.origins)
        + tts_warnings(project)
        + transition_warnings(project)
        + carry_warnings(project.config)
        + chapter_warnings(project)
        + translation_warnings(project)
        + language_warnings(project)
        + imagegen_warnings(project)
        + character_look_warnings(project.config, project.root)
        + character_pose_warnings(project.config, project.root)
        + shared_voice_warnings(project.config)
        + acting_warnings(project)
        + front_view_warnings(project.config)
        + host_warnings(project.config)
        + overlap_warnings(project.config)
        + dub_warnings(project)
        + music_warnings(project.config)
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
    from vidgen.music import music_summary, music_summary_line

    if args.json:
        return _validate_json(args.project)
    project = Project.load(args.project)
    # A variant that does not load is reported with the others' problems, not the end of the check.
    problems, variants = validate_all(project, keep_going=True)
    log_validate_warnings(project, variants)
    if problems:
        raise _invalid_project(project, problems)

    config = project.config
    n_beats = sum(1 for _ in project.beats())
    print(f"title:     {config.title}")
    print(f"scenes:    {len(config.scenes)}")
    print(f"beats:     {n_beats}")
    print(f"duration:  ~{_format_seconds(project.estimated_duration())} (estimated from word count)")
    if project.included_files:
        print(f"included:  {', '.join(project.included_labels)}")
    if config.variants:
        print(f"variants:  {', '.join(config.variants)}")
    if config.voices:
        counts = Counter(name or "default" for name in project.voice_names().values())
        print(f"voices:    {', '.join(f'{name} ({n} beats)' for name, n in counts.items())}")
    for line in pronunciation_summary_lines(project):
        print(line)
    for line in language_summary_lines(project, variants):
        print(line)
    for line in audio_summary_lines(project):
        print(line)
    for line in images_summary_lines(project, variants):
        print(line)
    for entry in music_summary(config):
        print(f"music:     {music_summary_line(entry)}")
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
    from vidgen.music import music_summary

    images = [jsonout.images_json(p, found) for p, found in variant_images(project, variants)]
    return jsonout.validate_document(project, problems, variants, error, images=images, music=music_summary(project.config))


def pronunciation_summary_lines(project: Project) -> list[str]:
    """``pronounce: built-in kokoro-en-us changes 3 beat(s): epoch (2), README (1)`` when
    built-in pronunciation entries change beats' spoken text (DESIGN.md §88); else nothing."""
    changes = project.builtin_changes()
    if not changes:
        return []
    counts = Counter(term for terms in changes.values() for term in terms)
    lists = sorted({str(project.beat_pronunciation(beat_id).builtin_list) for beat_id in changes})
    terms = ", ".join(f"{term} ({n})" for term, n in counts.items())
    return [f"{'pronounce:':<10} built-in {', '.join(lists)} changes {len(changes)} beat(s): {terms} (vidgen list-pronunciation)"]


def language_summary_lines(project: Project, variants: dict[str, Project | None]) -> list[str]:
    """``language: pt-BR (translations/pt.yaml: 40 translated, 2 stale)`` for the base config
    and each variant with a language or a translation file (DESIGN.md §54), each followed by
    ``dub [pt]: default bf_emma -> pf_dora (auto), ...`` when its voices are dubbed (§80)."""
    from vidgen.dubbing import dub_summary

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
        dubbed = dub_summary(p)
        if dubbed is not None:
            label = "dub:" if p.variant is None else f"dub [{p.variant}]:"
            lines.append(f"{label:<10} {dubbed}" if p.variant is None else f"{label} {dubbed}")
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


def variant_images(project: Project, variants: dict[str, Project | None]) -> list[tuple[Project, list[Any]]]:
    """The ``generate:`` pictures (``SceneImage``) of the base config and of each loaded variant
    whose pictures differ from the base's; configs without any are left out."""
    from vidgen.imagegen import scene_images

    out: list[tuple[Project, list[Any]]] = []
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
            out.append((p, images))
    return out


def images_summary_lines(project: Project, variants: dict[str, Project | None]) -> list[str]:
    """``images: 3 generated, 1 missing`` for the base config and each variant whose pictures
    differ (none without ``generate:`` params)."""
    from vidgen.imagegen import images_summary

    lines = []
    for p, images in variant_images(project, variants):
        label = "images:" if p.variant is None else f"images [{p.variant}]:"
        lines.append(f"{label:<10} {images_summary(images)}" if p.variant is None else f"{label} {images_summary(images)}")
    return lines


def cmd_imagegen(args: argparse.Namespace) -> CommandResult:
    """Generate the pictures of ``generate:`` params that are missing (DESIGN.md §58)."""
    from vidgen.imagegen.run import run_imagegen

    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant)
    plan = run_imagegen(project, scene_ids=args.scene, force=args.force, dry_run=args.dry_run)
    if args.json:
        return jsonout.imagegen_document(project, plan, args.dry_run, args.force, time.monotonic() - started)
    return 0


def each_language(args: argparse.Namespace, command: str, run: Callable[[str | None], CommandResult]) -> CommandResult:
    """``run(variant)`` for ``--variant`` alone, or with ``--all-languages`` for the base config
    and every variant in another language (:func:`vidgen.dubbing.language_variants`, DESIGN.md
    §80) in turn: a heading line before each, the worst exit code, or with ``--json`` one document
    whose ``languages`` lists each one's."""
    if not getattr(args, "all_languages", False):
        return run(args.variant)
    from vidgen.dubbing import language_variants

    if args.variant:
        raise VidgenError("--all-languages makes the base config and every variant in another language: leave out --variant")
    base = Project.load(args.project)
    results: list[CommandResult] = []
    for variant, language in [(None, base.config.language), *language_variants(base)]:
        if not args.json:
            print(f"== {variant or 'base config'} ({language or 'no language'}) ==", flush=True)
        results.append(run(variant))
    if args.json:
        docs = [r for r in results if isinstance(r, dict)]
        return jsonout.envelope(command, all(d.get("ok", True) for d in docs), languages=docs)
    return max((r for r in results if isinstance(r, int)), default=0)


def cmd_tts(args: argparse.Namespace) -> CommandResult:
    """Generate narration audio for beats whose MP3 is missing or stale (``--all-languages``: for
    every language, :func:`each_language`)."""
    return each_language(args, "tts", lambda variant: _tts(args, variant))


def _tts(args: argparse.Namespace, variant: str | None) -> CommandResult:
    from vidgen import extensions
    from vidgen.tts.run import run_tts

    started = time.monotonic()
    project = Project.load(args.project, variant=variant)
    with extensions.project_session(project):
        plan = run_tts(project, beat_ids=args.beat, force=args.force, dry_run=args.dry_run, voices=args.voice)
    if args.json:
        return jsonout.tts_document(project, plan, args.dry_run, args.force, time.monotonic() - started)
    return 0


def cmd_readback(args: argparse.Namespace) -> CommandResult:
    """Transcribe the beats' MP3s (speech to text, cached) and compare them with their texts:
    word error rate, differing words, unclear words and suggested fixes per beat (DESIGN.md
    §57, §78)."""
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
    print(f"language:     {result.language or 'not set (give --language, e.g. --language pt-BR)'}")
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
    """Render what changed (every scene with ``--force``, or the ``--scene`` ones), join the
    scenes and write the MP4 and SRT (``--all-languages``: of every language, :func:`each_language`)."""
    if args.jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    if args.frames_per_beat is not None and args.frames_per_beat < 1:
        raise VidgenError("--frames-per-beat must be at least 1")
    return each_language(args, "render", lambda variant: _render(args, variant))


def _render(args: argparse.Namespace, variant: str | None) -> CommandResult:
    from vidgen.render.pipeline import render_project

    frames = args.frames_per_beat or (1 if args.frames else 0)
    started = time.monotonic()
    project = Project.load(args.project, variant=variant, output_dir=args.output_dir, draft=args.draft)
    result = render_project(
        project,
        preview=args.preview or args.draft,
        scenes=args.scene or None,
        no_audio=args.no_audio,
        keep_going=args.keep_going,
        jobs=args.jobs,
        frames=frames,
        force=args.force,
    )
    if args.json:
        return jsonout.render_document(project, result, args.preview or args.draft, time.monotonic() - started)
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


def cmd_animatic(args: argparse.Namespace) -> CommandResult:
    """The storyboard's stills timed to the narration, with its audio and captions, as an MP4."""
    from vidgen.animatic import make_animatic

    started = time.monotonic()
    project = Project.load(args.project, variant=args.variant, output_dir=args.output_dir)
    result = make_animatic(project, no_audio=args.no_audio, captions=args.captions, jobs=args.jobs)
    elapsed = time.monotonic() - started
    if args.json:
        return jsonout.animatic_document(project, result, elapsed)
    reused = f", {len(result.reused)} reused" if result.reused else ""
    print(f"rendered {len(result.rendered)} scene(s) for their stills{reused}")
    print(f"animatic:  {result.output}")
    print(f"stills:    {len(result.holds)} ({result.format.width}x{result.format.height}, captions {'on' if result.captions else 'off'})")
    print(f"duration:  {_format_seconds(result.duration)} ({result.duration:.2f} s), made in {elapsed:.1f} s")
    if result.mix is not None:
        print(f"loudness:  {_loudness_line(result.mix)}")
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
    project = Project.load(args.project, variant=args.variant, output_dir=args.output_dir)
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


def cmd_character(args: argparse.Namespace) -> int:
    """Print a declared character's look, colours, poses and expressions; with ``--png``, also write one still of it."""
    from vidgen import extensions
    from vidgen.cartoon.cast import character_lines, find_character, pose_lines

    project = Project.load(args.project, variant=args.variant)
    entry = find_character(project.config, args.name)
    with extensions.project_session(project) as theme:
        for line in [*character_lines(entry, theme, project.root), *pose_lines(entry)]:
            print(line)
        if args.png is not None:
            from vidgen.cartoon.still import write_character_png

            still = write_character_png(project, entry, theme, Path(args.png) if args.png else None, facing=args.facing)
            print(f"png: {still.path}  ({still.width}x{still.height}, facing {args.facing})")
    return 0


def cmd_character_sheet(args: argparse.Namespace) -> CommandResult:
    """Write a character sheet (every pose, expression and mouth shape on one PNG) of one declared
    character, or of each with no NAME / ``--all``."""
    from vidgen import extensions
    from vidgen.cartoon.cast import find_character
    from vidgen.cartoon.still import write_character_sheet

    started = time.monotonic()
    name, where = args.name, args.project
    if args.all:
        if name is not None and where != ".":
            raise VidgenError("--all takes no character name: vidgen character-sheet --all [PROJECT]")
        name, where = None, name or where
    project = Project.load(where, variant=args.variant)
    if name is not None and args.output:
        targets = [(find_character(project.config, name), Path(args.output))]
    elif args.output:
        raise VidgenError("--output needs a character NAME (each character gets its own sheet)")
    else:
        entries = [find_character(project.config, name)] if name is not None else list(project.config.characters)
        if not entries:
            raise VidgenError("the video declares no characters (characters: in video.yaml)")
        targets = [(entry, None) for entry in entries]
    with extensions.project_session(project) as theme:
        sheets = [write_character_sheet(project, entry, theme, path) for entry, path in targets]
    if args.json:
        return jsonout.character_sheet_document(project, sheets, time.monotonic() - started)
    for sheet in sheets:
        counts = ", ".join(f"{len(s.names)} {s.title}" for s in sheet.sections)
        print(f"character sheet: {sheet.path}  ({sheet.width}x{sheet.height}, {counts}, {sheet.bytes / 1e3:.0f} KB)")
    return 0


def cmd_direct(args: argparse.Namespace) -> CommandResult:
    """Show the actions automatic directing (``auto_direct``) adds to the beats of the stage
    scenes; with ``--print``, as YAML to paste into ``video.yaml`` (DESIGN.md §69.23)."""
    from vidgen import extensions
    from vidgen.cartoon.directing import auto_label, directions_yaml, project_directions

    project = Project.load(args.project, variant=args.variant)
    known = [s.id for s in project.config.scenes]
    unknown = [sid for sid in args.scene if sid not in known]
    if unknown:
        raise VidgenError(f"unknown scene(s): {', '.join(unknown)}; scenes: {', '.join(known)}")
    with extensions.project_session(project):
        directed = project_directions(project, args.scene or None)
    if args.json:
        return jsonout.direct_document(project, directed)
    if args.print:
        print(directions_yaml(directed), end="")
        return 0
    if not directed:
        print("auto_direct adds nothing: it is off (auto_direct: true turns it on), or no character speaks to another on a stage")
        return 0
    for scene_id, beats in directed.items():
        count = sum(len(b.actions) for b in beats)
        print(f"scene {scene_id}: {count} automatic action{'s' if count != 1 else ''}")
        for beat in beats:
            print(f"  {beat.beat}: {'  ·  '.join(auto_label(a) for a in beat.actions)}")
    print("vidgen direct --print writes them as YAML to paste into video.yaml and edit")
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
    project = Project.load(args.project, variant=args.variant, output_dir=args.output_dir)
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
    project = Project.load(args.project, variant=args.variant, output_dir=args.output_dir)
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
    """Check the layout of every beat-end still (rendering what is needed) and report problems
    (``--all-languages``: in every language, :func:`each_language`)."""
    return each_language(args, "lint", lambda variant: _lint(args, variant))


def _lint(args: argparse.Namespace, variant: str | None) -> CommandResult:
    from vidgen.lint import lint_project, report_lines

    started = time.monotonic()
    project = Project.load(args.project, variant=variant)
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
        readback=args.readback,
        log=lambda line: print(line, file=sys.stderr),
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


def cmd_list_pronunciation(args: argparse.Namespace) -> CommandResult:
    """Print vidgen's built-in pronunciation lists (DESIGN.md §88): every list, or in a project
    the lists its beats' voices use, with what the project replaces or removes and the beats
    each entry changes."""
    from vidgen.pronunciation import builtin_list_names, builtin_listing

    project = None
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        project = Project.load(args.project)
    if project is None:
        lists = [builtin_listing(name) for name in builtin_list_names()]
        users: dict[str, int] = {}
    else:
        names = {beat.id: project.beat_pronunciation(beat.id).builtin_list for _, beat in project.beats()}
        users = dict(Counter(name for name in names.values() if name is not None))
        changes = project.builtin_changes()
        lists = [builtin_listing(name, project.pronunciation_entries, changes) for name in users]
    if args.json:
        return jsonout.list_pronunciation_document(project, lists, users)
    if project is not None and not project.config.pronunciation_defaults:
        print("pronunciation_defaults: false: no built-in entries are used")
    elif project is not None and not lists:
        print("no built-in list for this project's voices (only the project's own entries are used)")
    for listing in lists:
        entries = listing["entries"]
        used = f"; {users[listing['name']]} beat(s) use it" if listing["name"] in users else ""
        print(f"{listing['name']}: {len(entries)} entries ({', '.join(listing['files'])}){used}")
        width = max((len(e["term"]) for e in entries), default=0)
        for e in entries:
            line = f"  {e['term']:<{width}}  -> {e['say']}"
            if not e["case_sensitive"]:
                line += "  (any case)"
            if e["state"] == "replaced":
                line += f'  replaced by the project: "{e["own"]}"'
            elif e["state"] == "removed":
                line += "  removed by the project (null)"
            elif e["beats"]:
                line += f"  changes {', '.join(e['beats'])}"
            print(line)
    if lists:
        print("a project entry with the same term replaces a built-in one, `term: null` removes it; `pronunciation_defaults: false` turns them off")
    return 0


def cmd_list_music(args: argparse.Namespace) -> CommandResult:
    """Print the built-in music beds (what they sound like) and the project's ``assets/music``
    files, and write previews."""
    from vidgen import music

    root = None
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        root = find_config_file(args.project).resolve().parent
    from vidgen import composer, synth

    preview_dir = Path(args.render_dir).resolve() if args.render_dir else None
    entries = music.music_entries(root, preview_dir)
    if args.json:
        return jsonout.list_music_document(root, entries, preview_dir, composer.mood_entries(), composer.instrument_entries())
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
    print()
    print(f"composed music (music: {{compose: {{mood: NAME, key, tempo, instruments, seed, bars}}}}; symusic: {synth.symusic_status()};")
    print("without the music extra the bed named below plays; `vidgen music preview --mood NAME` writes a WAV and a .mid):")
    for m in composer.mood_entries():
        print(f"{m['name']}  {m['family']}  {m['key']}, {m['tempo']:g} BPM, {m['meter']}, {m['bars']} bars ({m['loop_seconds']:.0f} s loop)  [bed: {m['fallback_bed']}]")
        print(f"    description: {m['description']}")
        print(f"    use: {m['use']}")
    print("instruments (instruments: {melody|chords|pad|bass|drums: NAME | none | {instrument, volume, pan, reverb}}):")
    for i in composer.instrument_entries():
        where = "drum kit" if i["drums"] else f"{i['low']}-{i['high']}"
        print(f"    {i['name']} (GM {i['program']}, {where}): {i['description']}")
    return 0


def cmd_music(args: argparse.Namespace) -> CommandResult:
    """``preview``: compose a piece (the project's first ``compose:`` cue, changed by the options)
    and write it as ``<mood>-seed<N>.wav`` (one pass and the reverb's tail) and ``.mid`` (§83);
    ``page``: write the Listen page (§92)."""
    import math

    from vidgen import composer, loudness, soundfont, synth
    from vidgen.score import write_midi
    from vidgen.sfx import RATE, write_wav

    if args.action == "page":
        return _music_page(args)
    if args.action == "render":
        return _music_render(args)
    if args.action == "patches":
        return _music_patches(args)
    settings: dict[str, Any] = {}
    setting, root = None, Path.cwd()
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        project = Project.load(args.project)
        setting, root = project.config.soundfont, project.root
        found = next((c.compose for c in project.config.music_cues if c.compose is not None), None)
        if found is not None and args.mood in (None, found.mood):
            settings = {"mood": found.mood, "key": found.key, "tempo": found.tempo, "instruments": found.instrument_settings(), "seed": found.seed, "bars": found.bars}
    for name in ("mood", "key", "tempo", "seed", "bars"):
        if getattr(args, name) is not None:
            settings[name] = getattr(args, name)
    if "mood" not in settings:
        raise VidgenError(f"music preview: give --mood NAME (moods: {', '.join(composer.MOODS)}) or a project with music: {{compose: ...}}")
    piece = composer.compose_piece(**settings)
    synth.require_symusic()
    audio = synth.render_score(piece.score, soundfont.resolve(setting, root))
    out = Path(args.out or ".").resolve()
    stem = f"{piece.mood.name}-seed{piece.seed}"
    wav, mid = out / f"{stem}.wav", out / f"{stem}.mid"
    write_wav(wav, audio)
    write_midi(piece.score, mid)
    peak = float(loudness.peak_envelope(audio.astype("float64")).max())
    if args.json:
        lufs = loudness.integrated_loudness(audio)
        return jsonout.music_preview_document(piece, wav, mid, len(audio) / RATE, lufs, 20 * math.log10(max(peak, 1e-9)))
    print(f"mood: {piece.mood.name} ({piece.mood.family}), seed {piece.seed}: {piece.key.name}, {piece.tempo:g} BPM, {piece.mood.meter}/4, "
          f"{piece.bars} bars = {piece.seconds:.1f} s (loops; the WAV adds {synth.TAIL_SECONDS:g} s of tail)")
    print("parts: " + ", ".join(f"{v.role} {v.instrument.name} ({v.volume:+g} dB)" for v in piece.voices))
    for k, phrase in enumerate(piece.phrases):
        print(f"    bars {4 * k + 1:>3}-{4 * k + 4:<3} {phrase:<11} " + " | ".join(" ".join(c) for c in piece.chords[4 * k : 4 * k + 4]))
    print(f"loudness: {loudness.integrated_loudness(audio):.1f} LUFS integrated, true peak {20 * math.log10(max(peak, 1e-9)):.1f} dBTP, {len(audio) / RATE:.1f} s")
    print(f"wrote: {wav}")
    print(f"wrote: {mid}")
    return 0


def _music_render(args: argparse.Namespace) -> CommandResult:
    """``vidgen music render SCORE.yaml [--out FILE.wav|FILE.mp3]``: play a score file (DESIGN.md §93)."""
    from vidgen import loudness
    from vidgen.sfx import RATE, write_wav
    from vidgen.studio import load_music_score, render_music_score, score_outline

    if args.project == ".":
        raise VidgenError("music render: give the score file, e.g. vidgen music render my_theme.yaml --out my_theme.wav")
    path = Path(args.project)
    out = Path(args.out) if args.out else Path(path.stem + ".wav")
    if out.suffix.lower() not in (".wav", ".mp3"):
        raise VidgenError(f"music render: --out must be a .wav or .mp3 file, got {out}")
    score = load_music_score(path)
    notes: list[str] = []
    audio = render_music_score(score, notes)
    if out.suffix.lower() == ".mp3":
        from vidgen.listen import write_mp3

        write_mp3(audio, out)
    else:
        write_wav(out, audio)
    meter = loudness.measure(len(audio), lambda a, b: audio[a:b])
    outline = score_outline(score)
    if args.json:
        warnings = [{"scene": None, "message": n} for n in notes]
        return jsonout.music_render_document(outline, out, len(audio) / RATE, meter.integrated, meter.true_peak, warnings)
    for note in notes:
        print(f"warning: {note}", file=sys.stderr)
    print(f"{outline['title'] or path.stem}: {score.key.name}, {score.tempo:g} BPM, {outline['time']}, {score.bars} bars = {score.seconds:.2f} s "
          f"({'a seamless loop' if score.loop else f'one pass, {len(audio) / RATE:.2f} s with its ending'})")
    for s in outline["sections"]:
        print(f"    {s['start']:7.2f} s  {s['name']:<10} {s['bars']:>3} bars  {s['key']:<10} {' '.join(s['chords'])}")
    print("tracks: " + ", ".join(f"{t['name']} ({t['instrument']}{': ' + ', '.join(t['effects']) if t['effects'] else ''})" for t in outline["tracks"]))
    print(f"loudness: {meter.integrated:.1f} LUFS integrated, true peak {meter.true_peak:.1f} dBTP")
    print(f"wrote: {out}")
    return 0


def _music_patches(args: argparse.Namespace) -> CommandResult:
    """``vidgen music patches``: every score-file instrument, setting and effect in words (§93.4, §93.7)."""
    from vidgen.studio import patch_catalog, patch_text

    if args.json:
        return jsonout.music_patches_document(patch_catalog())
    print(patch_text())
    return 0


def _music_page(args: argparse.Namespace) -> CommandResult:
    """``vidgen music page``: write the Listen page (DESIGN.md §92)."""
    from vidgen.listen import make_listen_page

    result = make_listen_page(Path(args.out or Path("docs") / "music"), composed=args.composed)
    if args.json:
        return jsonout.listen_page_document(result)
    print(f"listen page: {result.page} ({len(result.clips)} clips, {result.bytes / 1e6:.2f} MB in {result.output})")
    if not result.composed:
        print(f"no composed clips: {result.composed_note}")
    return 0


def cmd_soundfont(args: argparse.Namespace) -> int:
    """``fetch``: download the default SoundFont into vidgen's cache (checked) unless it is there;
    ``info``: show the SoundFont a project (or any project) uses (DESIGN.md §81)."""
    from vidgen import soundfont, synth

    setting, root = None, None
    if args.project != "." or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        project = Project.load(args.project)
        setting, root = project.config.soundfont, project.root
    if args.action == "fetch":
        if setting:
            print(f"note: this project plays composed music with soundfont: {setting}; fetching the default one anyway")
        present = soundfont.default_path().is_file() and not args.force
        if not present:
            print(f"downloading {soundfont.NAME} ({soundfont.SIZE_BYTES / 1e6:.1f} MB) from {soundfont.URL}", flush=True)
        path = soundfont.fetch(force=args.force)
        print(f"{'already there' if present else 'saved'}: {path} (sha256 checked)")
        return 0
    found = soundfont.info(setting, root)
    print(f"soundfont: {found.path} ({'soundfont: in video.yaml' if found.origin == 'project' else soundfont.NAME + ', the default'})")
    if not found.exists:
        what = "file not found" if found.origin == "project" else "not downloaded yet: `vidgen soundfont fetch` (or the first composed render) downloads it"
        print(f"    {what}")
    else:
        assert found.size_bytes is not None
        print(f"    size: {found.size_bytes:,} bytes ({found.size_bytes / 1e6:.1f} MB)")
        print(f"    sha256: {found.sha256}")
        if found.matches is not None:
            print(f"    check: {'ok, the expected file' if found.matches else 'MISMATCH, not used: `vidgen soundfont fetch --force`'}")
    print(f"    licence: {found.licence}")
    if found.origin == "default":
        print(f"    suggested credit: {soundfont.CREDIT}")
    print(f"symusic: {synth.symusic_status()}")
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


def cmd_mcp(args: argparse.Namespace) -> int:
    """Serve vidgen's commands as MCP tools on stdin / stdout until the client disconnects (DESIGN.md §62)."""
    from vidgen.mcp_server import serve

    serve(Path(args.root))
    return 0


def cmd_gallery(args: argparse.Namespace) -> CommandResult:
    """Render every scene type's sample at 16:9 and 9:16 and write the Markdown gallery (DESIGN.md §60)."""
    from vidgen.gallery import make_gallery

    started = time.monotonic()
    project = None
    if args.project is not None or any((Path.cwd() / name).is_file() for name in CONFIG_NAMES):
        project = Project.load(args.project or ".")
    types = [t.strip() for value in args.types for t in value.split(",") if t.strip()]
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    result = make_gallery(
        project,
        output=Path(args.output),
        only=types or None,
        formats=formats,
        preset=args.theme,
        clips=args.clips,
        jobs=args.jobs,
        force=args.force,
    )
    for message in result.warnings:
        logging.getLogger("vidgen.gallery").warning(message)
    if args.json:
        return jsonout.gallery_document(project, result, time.monotonic() - started)
    reused = f", {len(result.reused)} reused" if result.reused else ""
    print(f"rendered {len(result.rendered)} sample(s){reused}")
    print(f"gallery: {result.index} ({result.bytes / 1e6:.1f} MB in {result.output})")
    for t in result.types:
        if t.page is not None:
            print(f"  {t.name}: {t.page.name}, {len(t.stills)} still(s), {len(t.clips)} clip(s)")
    for s in result.showcases:
        if s.page is not None:
            print(f"  showcase {s.name}: {s.page.name}, {len(s.stills)} still(s), {len(s.clips)} clip(s)")
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

    def jobs_arg(p: argparse.ArgumentParser, what: str = "scenes", when: str = "") -> None:
        p.add_argument(
            "--jobs", "-j", type=_jobs_value, default=1, metavar="N|auto",
            help=f"render N {what} in parallel{when}; auto: as many as the available memory "
            f"({PER_JOB_BYTES / 1e9:.1f} GB each) and CPU cores allow (default: 1)",
        )

    def output_dir_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--output-dir", metavar="DIR",
            help="folder of the rendered MP4, SRT, chapter list and thumbnail (relative to the current directory; "
            "default: output_dir: in video.yaml, else <project>/output)",
        )

    def all_languages_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--all-languages", action="store_true",
            help="the base config and then every variant whose language: differs from it (a dubbed video per language), "
            "one after the other; not with --variant",
        )

    p = sub.add_parser("init", help="scaffold a new project")
    p.add_argument("dir", help="directory to create (must not exist or be empty)")
    examples = sorted(d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir())
    p.add_argument("--example", choices=examples, default="minimal", help="template (default: minimal)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="draft a project from a Markdown outline or a plain-text script (scenes, beats, TODOs; no AI)")
    p.add_argument("input", help="the outline (.md) or script (.txt)")
    p.add_argument("--output", "-o", metavar="DIR|FILE", help="project folder to create, or a .yaml file to write (default: a folder named after INPUT)")
    p.add_argument("--title", help="the video's title (default: the outline's top heading, else the file name)")
    p.add_argument("--format", choices=["16:9", "9:16"], default="16:9", help="frame: 16:9 (default) or 9:16 (vertical)")
    p.add_argument("--preset", default="dark_tech", metavar="NAME", help="theme preset (default: dark_tech; `vidgen list-themes`)")
    p.add_argument("--language", metavar="TAG", help="language of the text (BCP-47, e.g. pt-BR): sentence and phrase rules, written as language:")
    p.add_argument("--force", action="store_true", help="write into a folder that is not empty, or replace an existing config")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("screenplay", help="a cartoon project from a screenplay: # Scene: headings, NAME: lines, [stage directions] (no AI)")
    p.add_argument("input", help="the screenplay (.md or .txt)")
    p.add_argument("--out", "-o", metavar="DIR|FILE", help="project folder to create, or a .yaml file to write (default: a folder named after INPUT)")
    p.add_argument("--cast", metavar="FILE", help="reuse a cast: an include file (characters, voices, sets) the project includes; set: NAME lines use its sets")
    p.add_argument("--species", nargs="+", action="extend", metavar="NAME", help="species of the undeclared characters: human (default), cat, dog, bird, bear, rabbit, mouse, fox, owl, frog, turtle, penguin, snail, robot (several: a mix)")
    p.add_argument("--seed", type=int, default=0, help="seed of the random looks undeclared characters get once the built-in ones are used (default: 0)")
    p.add_argument("--force", action="store_true", help="write into a folder that is not empty, or replace an existing config")
    p.set_defaults(func=cmd_screenplay)

    p = sub.add_parser("cast", help="write a cast of characters that differ clearly (looks, colours, voices) as an include file (no AI)")
    p.add_argument("--random", type=int, required=True, metavar="N", help="how many characters (1-24)")
    p.add_argument("--seed", type=int, default=0, help="the same seed gives the same cast (default: 0)")
    p.add_argument("--species", nargs="+", action="extend", metavar="NAME", help="human (default), cat, dog, bird, bear, rabbit, mouse, fox, owl, frog, turtle, penguin, snail, robot (several: a mix)")
    p.add_argument("--out", "-o", default="cast.yaml", metavar="FILE", help="the include file to write (default: cast.yaml)")
    p.add_argument("--provider", choices=["kokoro", "openrouter", "elevenlabs"], default="kokoro", help="the video's voice provider (default: kokoro)")
    p.add_argument("--narrator", metavar="VOICE", help="the narrator's voice, left out of the cast's (default for kokoro: bf_emma)")
    p.add_argument("--model", metavar="NAME", help="openrouter: the TTS model whose voices to use")
    p.add_argument("--language", metavar="TAG", help="the video's language (BCP-47): Kokoro voices of that language")
    p.add_argument("--force", action="store_true", help="replace an existing file")
    p.set_defaults(func=cmd_cast)

    p = sub.add_parser("guide", help="the author guide for AI agents making videos (workflow, pacing, scene types, ...)")
    p.add_argument("topic", nargs="?", metavar="TOPIC", help="print only this topic (vidgen guide --list shows them)")
    p.add_argument("--list", action="store_true", help="list the topics")
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("mcp", help="run the MCP server (stdio) that gives AI agents vidgen's commands as tools (needs schu-video-generator[mcp])")
    p.add_argument("--root", metavar="DIR", default=".", help="the only folder the tools may read and write (default: the current folder)")
    p.set_defaults(func=cmd_mcp)

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

    p = sub.add_parser("list-pronunciation", help="list vidgen's built-in pronunciation entries (per TTS engine and language) and, in a project, what they change")
    project_arg(p)
    p.set_defaults(func=cmd_list_pronunciation)

    p = sub.add_parser("list-music", help="list background music beds (built-in and the project's assets/music) with descriptions")
    project_arg(p)
    p.add_argument("--render-dir", metavar="DIR", help="also write one loop of every bed as DIR/<name>.wav")
    p.set_defaults(func=cmd_list_music)

    p = sub.add_parser(
        "music",
        help="music tools: preview writes a composed piece in a mood as WAV and .mid (needs the music extra); render plays a score file; "
        "patches describes the score files' instruments and effects; page writes the Listen page",
    )
    p.add_argument(
        "action", choices=["preview", "render", "patches", "page"],
        help="preview: compose the project's compose: music (or --mood) and write it; render: play a score file (YAML) to a WAV or MP3; "
        "patches: every score-file instrument, setting and effect in words; "
        "page: write the Listen page (a clip and spectrogram of every bed, the sound effects, ambience and composed moods; default --out docs/music)",
    )
    p.add_argument("project", nargs="?", default=".", help="preview: project dir or config file (default: .); render: the score file")
    p.add_argument("--mood", metavar="NAME", help="the mood (calm, focused, curious, upbeat, playful, sleepy, tense, triumphant; vidgen list-music)")
    p.add_argument("--seed", type=int, metavar="N", help="another seed gives another piece in the mood")
    p.add_argument("--bars", type=int, metavar="N", help="length in bars, a multiple of 4 (default: the mood's)")
    p.add_argument("--key", metavar="KEY", help="e.g. E, 'Eb major', 'F# minor' (default: the mood's)")
    p.add_argument("--tempo", type=float, metavar="BPM", help="quarter notes per minute (default: the mood's)")
    p.add_argument(
        "--out", metavar="PATH",
        help="preview: folder for <mood>-seed<N>.wav and .mid (default: .); render: the .wav or .mp3 (default: <score>.wav here); "
        "page: the page's folder (default: docs/music)",
    )
    p.add_argument("--no-composed", dest="composed", action="store_false", help="page: leave out the composed moods' clips")
    p.set_defaults(func=cmd_music)

    p = sub.add_parser("soundfont", help="the SoundFont composed music is played with: fetch downloads GeneralUser GS into vidgen's cache, info shows it")
    p.add_argument("action", choices=["fetch", "info"], help="fetch: download it (once; checked against its SHA-256); info: path, size, hash, licence")
    project_arg(p)
    p.add_argument("--force", action="store_true", help="fetch: download it again even if the cached file is there")
    p.set_defaults(func=cmd_soundfont)

    p = sub.add_parser("tts", help="generate narration audio (ElevenLabs, or OpenRouter with voice.provider: openrouter)")
    project_arg(p)
    p.add_argument("--force", action="store_true", help="regenerate even if up to date")
    p.add_argument("--dry-run", action="store_true", help="only list what would be generated (OpenRouter: with its estimated cost)")
    p.add_argument("--beat", action="append", default=[], metavar="ID", help="only this beat (repeatable)")
    p.add_argument("--voice", action="append", default=[], metavar="NAME", help="only the beats of this voice (a voices: name or default; repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant (may have its own voice)")
    all_languages_arg(p)
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("readback", help="transcribe the narration (speech to text) and compare it with the beat texts: misheard, missing or extra words, unclear words and pauses")
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
    p.add_argument("--lang", "--language", dest="lang", metavar="TAG", help="language of the translation (BCP-47, e.g. pt-BR; default: the variant's language)")
    p.add_argument("--output", "-o", metavar="FILE", help="write here instead of the variant's translations: file")
    p.set_defaults(func=cmd_translate_template)

    p = sub.add_parser("render", help="render the video")
    project_arg(p)
    quality = p.add_mutually_exclusive_group()
    quality.add_argument("--preview", action="store_true", help="fast low-resolution render")
    quality.add_argument(
        "--draft", action="store_true",
        help="fastest check of timing and staging: ~8 fps, 240p, no idle / wind / shadows / particles / light grade (build/draft, ..._draft.mp4)",
    )
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--no-audio", action="store_true", help="render without narration audio")
    p.add_argument("--keep-going", action="store_true", help="continue after a scene fails")
    jobs_arg(p)
    p.add_argument("--frames", action="store_true", help="also save a PNG still at the end of each beat (build/.../frames/)")
    p.add_argument(
        "--frames-per-beat", type=int, metavar="N", help="save N evenly spaced stills per beat, the last at its end (implies --frames)"
    )
    p.add_argument("--force", action="store_true", help="render every scene again, even those whose render is current")
    output_dir_arg(p)
    all_languages_arg(p)
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
    jobs_arg(p)
    p.add_argument("--force", action="store_true", help="render the scenes again even if their stills are current")
    p.set_defaults(func=cmd_storyboard)

    p = sub.add_parser("animatic", help="the storyboard's stills timed to the narration, with audio and captions, as an MP4 (no Manim when the stills are current)")
    project_arg(p)
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--no-audio", action="store_true", help="a silent animatic (no narration, effects or music)")
    p.add_argument(
        "--captions", action=argparse.BooleanOptionalAction, default=None,
        help="draw the subtitles onto the stills (default: on, unless the video burns in a captions overlay)",
    )
    jobs_arg(p, when=" when stills are missing")
    output_dir_arg(p)
    p.set_defaults(func=cmd_animatic)

    p = sub.add_parser("thumbnail", help="write the video's thumbnail (<output>_thumbnail.png) from the thumbnail: config or a scene's frame")
    project_arg(p)
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--preview", action="store_true", help="take frames from the preview render (fast; ..._preview_thumbnail.png)")
    p.add_argument("--scene", metavar="ID", help="a frame of this scene instead of the configured thumbnail")
    p.add_argument("--beat", metavar="ID|N", help="with --scene: the beat (its id or number from 1; default: the last)")
    p.add_argument("--at", type=float, metavar="SECONDS", help="with --scene: seconds into the beat (or the scene); default: the beat's end")
    p.add_argument("--no-overlays", action="store_true", help="with --scene: the frame without captions, watermark... (renders the scene again)")
    p.add_argument("--jpeg", action="store_true", help="also write <output>_thumbnail.jpg under 2 MB")
    jobs_arg(p, when=" when scenes must be rendered")
    output_dir_arg(p)
    p.set_defaults(func=cmd_thumbnail)

    p = sub.add_parser("character", help="show a character of characters: (its look and colours); --png writes one still of it")
    p.add_argument("name", help="the character's name (from characters:)")
    project_arg(p)
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument(
        "--png", nargs="?", const="", metavar="FILE",
        help="write a still of the character to FILE (default: <project>/exports/character_<name>.png)",
    )
    p.add_argument("--facing", choices=["right", "left", "front"], default="right", help="which way the character faces in the still: right, left or front (its front view; default: right)")
    p.set_defaults(func=cmd_character)

    p = sub.add_parser(
        "character-sheet", help="one PNG per character with every pose, expression and mouth shape (exports/character_sheet_<name>.png)"
    )
    p.add_argument("name", nargs="?", help="the character's name (from characters:; default: every character)")
    project_arg(p)
    p.add_argument("--all", action="store_true", help="every character; the one positional is then the project (vidgen character-sheet --all PROJECT)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.add_argument("--output", metavar="FILE", help="with NAME: write the sheet to FILE (default: <project>/exports/character_sheet_<name>.png)")
    p.set_defaults(func=cmd_character_sheet)

    p = sub.add_parser("direct", help="show the looks and reactions auto_direct adds to the stage scenes' beats; --print writes them as YAML")
    project_arg(p)
    p.add_argument("--print", action="store_true", help="write the added actions as YAML to paste into video.yaml and edit")
    p.add_argument("--scene", action="append", default=[], metavar="ID", help="only this scene (repeatable)")
    p.add_argument("--variant", metavar="NAME", help="apply a named variant")
    p.set_defaults(func=cmd_direct)

    p = sub.add_parser("slides", help="an HTML (or PDF) slide deck of the video's key frames, narration as speaker notes (exports/)")
    project_arg(p)
    p.add_argument("--format", choices=["html", "pdf"], default="html", help="an HTML deck (default) or a PDF (needs schu-video-generator[pdf])")
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
    jobs_arg(p)
    p.add_argument("--force", action="store_true", help="render the scenes again even if their stills are current")
    output_dir_arg(p)
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
    output_dir_arg(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("gallery", help="render every scene type's sample (16:9 and 9:16) into a Markdown gallery with stills, GIFs and YAML")
    p.add_argument("project", nargs="?", default=None, help="also show this project's own scene types, in its theme (default: the project in . if any)")
    p.add_argument("--output", "-o", default=str(Path("docs") / "gallery"), metavar="DIR", help="gallery folder (default: docs/gallery)")
    p.add_argument("--types", action="append", default=[], metavar="T,T", help="only these scene types or showcases (comma-separated, repeatable)")
    p.add_argument("--formats", default="16:9,9:16", metavar="F,F", help="formats to render: 16:9, 9:16 (default: both)")
    p.add_argument("--theme", metavar="PRESET", help="render in this theme preset (default: the project's theme, or the default one)")
    p.add_argument("--clips", action=argparse.BooleanOptionalAction, default=True, help="also write a GIF of each scene (default: yes)")
    jobs_arg(p, what="samples")
    p.add_argument("--force", action="store_true", help="render the samples again even if their stills are current")
    p.set_defaults(func=cmd_gallery)

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
    jobs_arg(p)
    p.add_argument("--force", action="store_true", help="render the scenes again even if their stills are current")
    p.add_argument(
        "--readback", action="store_true",
        help="also run the unclear_speech rule: transcribe the narration (as `vidgen readback`, cached) and flag unclear words (slow)",
    )
    all_languages_arg(p)
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


def _jobs_value(text: str) -> int | str:
    """A ``--jobs`` value: a whole number (checked by the command) or ``auto``."""
    if text == AUTO_JOBS:
        return AUTO_JOBS
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid value: {text!r} (a whole number, or {AUTO_JOBS})") from None


def _resolve_auto_jobs(args: argparse.Namespace) -> JobsChoice | None:
    """Replace ``--jobs auto`` by the number :func:`choose_jobs` picks and print the choice and
    its reason; ``None`` when the command has no ``--jobs`` or was given a number."""
    if getattr(args, "jobs", None) != AUTO_JOBS:
        return None
    choice = choose_jobs()
    args.jobs = choice.jobs
    print(f"jobs: {choice.jobs} (auto: {choice.reason})", flush=True)
    return choice


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
    jobs: JobsChoice | None = None
    try:
        with _cli_logging(warnings), redirect_stdout(sys.stderr):
            jobs = _resolve_auto_jobs(args)
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
    if jobs is not None:
        doc["jobs"] = jobs.to_json()
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
                _resolve_auto_jobs(args)
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
