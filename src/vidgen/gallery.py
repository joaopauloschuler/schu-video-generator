"""``vidgen gallery`` (DESIGN.md §60): every scene type rendered from one canonical sample, at
16:9 and 9:16, written as Markdown pages with stills and short GIF clips.

**Samples.** A built-in type's sample is its snippet in the author guide's ``scenes`` topic
(``AGENTS.md``; the first one of the type, preferring one without a generated picture), so the
guide and the gallery show the same YAML. Files the snippets name under ``assets/`` are the
small pictures and clip shipped in ``data/gallery/`` (:func:`sample_asset`). A project's own
types (run in a project) take the first scene of that type in its ``video.yaml``. Names that
are another name of the same class (``flowchart`` / ``diagram``) are rendered once.

**Rendering.** The samples become one work project in ``<project or .>/build/gallery`` (16:9 at
:data:`FORMATS` sizes, 9:16 as its ``portrait`` variant), rendered with one still per beat like
``vidgen storyboard`` (current stills are reused, by the render fingerprint). A type's still is
its last beat's end; its clip is the scene's render as a palette GIF.

**Output** (default ``docs/gallery``): ``README.md`` (the index: every registered type by group,
with its stills), ``<type>.md`` (what it is for, stills, clips, the YAML, params, targets,
beats) and ``media/<type>-16x9.png|gif``, ``media/<type>-9x16.png|gif``. Nothing in them depends
on the time or the machine, so regenerating with the same vidgen gives the same files.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from vidgen.errors import VidgenError
from vidgen.fileio import remove_file, replace_file, write_bytes_atomic, write_text_atomic
from vidgen.project import Project

#: Pictures and the clip the guide's snippets use (package data).
SAMPLE_ASSETS_DIR = Path(__file__).resolve().parent / "data" / "gallery"
#: The two formats: name -> (width, height) of the render, and the file-name tag.
FORMATS: dict[str, tuple[int, int]] = {"16:9": (640, 360), "9:16": (360, 640)}
FORMAT_TAGS: dict[str, str] = {"16:9": "16x9", "9:16": "9x16"}
#: Render frame rate (also the clips' upper limit).
FPS = 12
#: GIF clips: width per format, frame rate, palette size (flat pictures, no dithering) and how
#: long the last beat's end is held before the loop starts again. The clip ends at the last
#: beat's end (the scene's fade-out, every pixel changing, would cost the most bytes).
CLIP_WIDTHS: dict[str, int] = {"16:9": 320, "9:16": 180}
CLIP_FPS = 6
CLIP_COLORS = 32
CLIP_HOLD = 1.5
#: The work project's variant rendering 9:16.
PORTRAIT_VARIANT = "portrait"
#: Index group of a project's own types.
PROJECT_GROUP = "project types"

_FENCE = re.compile(r"```(\w*)\n(.*?)```", re.S)
_TICKED = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class Sample:
    """The canonical example of a scene type: its scene ``config`` (a ``scenes:`` entry), the
    ``yaml`` as written in its source, the index ``group`` and where it came from (``guide`` or
    the project's config file name)."""

    type: str
    config: dict[str, Any]
    yaml: str
    group: str
    origin: str


@dataclass
class GalleryType:
    """One scene type of the gallery: ``name``; ``alias_of`` (the name it is rendered under) or
    ``None``; the ``sample`` (``None``: none found, not rendered); the written ``page`` and
    ``stills`` / ``clips`` by format."""

    name: str
    alias_of: str | None
    sample: Sample | None
    page: Path | None = None
    stills: dict[str, Path] = field(default_factory=dict)
    clips: dict[str, Path] = field(default_factory=dict)


@dataclass
class GalleryResult:
    """What :func:`make_gallery` did: the folder and its index, the work project, the formats,
    every type (index order), the samples rendered / reused as ``"<type> (<format>)"``, the
    gallery's own ``warnings`` (types without a sample) and the render workers' warnings
    ``(sample, message)`` (already printed while rendering)."""

    output: Path
    index: Path
    work: Path
    formats: list[str]
    types: list[GalleryType]
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    render_warnings: list[tuple[str, str]] = field(default_factory=list)

    @property
    def bytes(self) -> int:
        """Total size of the files in the output folder."""
        return sum(p.stat().st_size for p in self.output.rglob("*") if p.is_file())


# ----- samples ---------------------------------------------------------------------------------


def _snippet_items(body: str) -> tuple[str, list[str]]:
    """A YAML block of the guide as ``(group, [the text of each list item])``: the group is the
    block's first comment line (``# data``)."""
    group = ""
    items: list[list[str]] = []
    for line in body.splitlines():
        if not items and line.startswith("#"):
            group = group or line.lstrip("# ").strip()
            continue
        if line.startswith("- "):
            items.append([])
        if items:
            items[-1].append(line)
    return group, ["\n".join(item).rstrip() + "\n" for item in items]


def guide_samples() -> dict[str, Sample]:
    """Type name -> sample from the guide's ``scenes`` topic (its first snippet of the type; a
    later one replaces a snippet that uses ``generate:``, which only renders a placeholder)."""
    from vidgen.guide import find_topic

    samples: dict[str, Sample] = {}
    for lang, body in _FENCE.findall(find_topic("scenes").text):
        if lang != "yaml":
            continue
        group, items = _snippet_items(body)
        for text in items:
            scene = yaml.safe_load(text)[0]
            name = scene["type"]
            known = samples.get(name)
            if known is None or "generate" in known.config.get("params", {}):
                samples[name] = Sample(name, scene, text, group, "guide")
    return samples


def chooser_uses() -> dict[str, str]:
    """Type name -> "what you want to show" from the guide's chooser table."""
    from vidgen.guide import find_topic

    uses: dict[str, str] = {}
    for line in find_topic("scenes").text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) >= 3:
            for name in _TICKED.findall(cells[1]):
                uses.setdefault(name, cells[0])
    return uses


def sample_asset(scene_type: str, rel: str) -> Path:
    """The shipped file standing in for a snippet's ``assets/...`` path: the landscape picture
    for ``image``, the app screenshot for other pictures, the screen recording for videos."""
    suffix = Path(rel).suffix.lower()
    if suffix in (".mp4", ".webm", ".mov", ".mkv"):
        return SAMPLE_ASSETS_DIR / "clip.webm"
    if suffix in (".png", ".jpg", ".jpeg", ".webp"):
        return SAMPLE_ASSETS_DIR / ("picture.png" if scene_type == "image" else "app.png")
    raise VidgenError(f"the gallery has no sample file for {rel} (a {scene_type} snippet)")


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def project_samples(project: Project) -> dict[str, Sample]:
    """Type name -> the first scene of that type in ``project``'s config."""
    samples: dict[str, Sample] = {}
    for scene in project.config.scenes:
        if scene.type in samples:
            continue
        data = scene.model_dump(mode="json", by_alias=True, exclude_defaults=True)
        data = {"id": scene.id, "type": scene.type, **{k: v for k, v in data.items() if k not in ("id", "type")}}
        text = yaml.safe_dump([data], sort_keys=False, allow_unicode=True, width=100)
        samples[scene.type] = Sample(scene.type, data, text, PROJECT_GROUP, project.config_file.name)
    return samples


# ----- the types -------------------------------------------------------------------------------


def gallery_types(project: Project | None) -> list[GalleryType]:
    """Every registered scene type (built-ins and, with ``project``, its extensions; the current
    registry), in index order: the guide's groups, then the project's types, then others. A name
    that is another name of an earlier type's class is its ``alias_of``."""
    from vidgen import registry

    entries = registry.all()
    guide = guide_samples()
    own = project_samples(project) if project is not None else {}
    canonical: dict[type, str] = {}
    types: list[GalleryType] = []
    for entry in entries:
        if entry.cls in canonical:
            types.append(GalleryType(entry.name, canonical[entry.cls], None))
            continue
        canonical[entry.cls] = entry.name
        names = [e.name for e in entries if e.cls is entry.cls]
        # a built-in (or a project's override of one) shows the guide's snippet; a project's own
        # type, or a type the guide has no snippet for, its first scene in video.yaml
        sample = next((guide[n] for n in names if n in guide), None) if entry.builtin or entry.overrides is not None else None
        if sample is None:
            sample = next((own[n] for n in names if n in own), None)
        if sample is not None and sample.type != entry.name:  # the snippet of another name of it
            text = sample.yaml.replace(f"type: {sample.type}", f"type: {entry.name}")
            sample = Sample(entry.name, {**sample.config, "type": entry.name}, text, sample.group, sample.origin)
        types.append(GalleryType(entry.name, None, sample))
    groups = list(dict.fromkeys(s.group for s in guide.values()))
    order = {g: i for i, g in enumerate(groups)}
    guide_order = {name: i for i, name in enumerate(guide)}

    def key(t: GalleryType) -> tuple[int, int, str]:
        base = t if t.alias_of is None else next(x for x in types if x.name == t.alias_of)
        if base.sample is None:
            return (len(groups) + 1, 0, t.name)
        group = order.get(base.sample.group, len(groups))
        return (group, guide_order.get(base.sample.type, guide_order.get(t.name, 0)), t.name)

    return sorted(types, key=key)


def rendered_names(types: list[GalleryType], only: list[str] | None) -> list[str]:
    """The names to render: every type with a sample, or those of ``only`` (another name of a
    type renders it under its own name); an unknown name is a :class:`VidgenError`."""
    from vidgen import registry

    by_name = {t.name: t for t in types}
    unknown = [n for n in only or [] if n not in by_name]
    if unknown:
        raise VidgenError(registry.unknown_type_message(unknown[0]))
    wanted = {by_name[n].alias_of or n for n in only} if only else set(by_name)
    return [t.name for t in types if t.name in wanted and t.alias_of is None and t.sample is not None]


# ----- the work project ------------------------------------------------------------------------


def work_dir(project: Project | None) -> Path:
    """Where the samples are rendered: ``<project>/build/gallery`` or ``./build/gallery``."""
    return (project.root if project is not None else Path.cwd()) / "build" / "gallery"


def work_config(types: list[GalleryType], project: Project | None, preset: str | None) -> dict[str, Any]:
    """The work project's config: one scene per rendered type (id = type name), 16:9 preview,
    9:16 as the ``portrait`` variant; the project's theme and extensions."""
    (w, h), (pw, ph) = FORMATS["16:9"], FORMATS["9:16"]
    scenes = []
    for t in types:
        if t.alias_of is None and t.sample is not None:
            scenes.append({**t.sample.config, "id": t.name})
    config: dict[str, Any] = {
        "title": "vidgen gallery",
        "output": "gallery",
        "preview": {"width": w, "height": h, "fps": FPS},
        "variants": {PORTRAIT_VARIANT: {"preview": {"width": pw, "height": ph, "fps": FPS}}},
        "extensions": [],
        "scenes": scenes,
    }
    if project is not None:
        from vidgen.extensions import extension_dirs

        config["extensions"] = [str(d) for d in extension_dirs(project)]
        theme = project.config.theme.model_dump(mode="json", exclude_defaults=True)
        if theme:
            config["theme"] = theme
    if preset is not None:
        config["theme"] = {"preset": preset}
    return config


def _copy(source: Path, target: Path) -> None:
    """Copy with its modification time, unless ``target`` is the same already (render
    fingerprints see ``assets/`` files by size and time)."""
    if target.is_file() and target.read_bytes() == source.read_bytes():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_files(types: list[GalleryType], project: Project | None, work: Path) -> None:
    """Put the files the samples name into the work project: shipped stand-ins for the guide's
    ``assets/...`` paths, the project's own files (and its ``assets/icons``) for its samples."""
    for t in types:
        if t.sample is None or t.alias_of is not None:
            continue
        for value in _strings(t.sample.config.get("params", {})):
            source: Path | None = None
            if t.sample.origin == "guide" and value.startswith("assets/"):
                source = sample_asset(t.sample.type, value)
            elif project is not None and t.sample.origin != "guide" and not Path(value).is_absolute() and "/" in value:
                candidate = project.root / value
                source = candidate if candidate.is_file() else None
            if source is not None:
                _copy(source, work / value)
    if project is not None and (project.root / "assets" / "icons").is_dir():
        shutil.copytree(project.root / "assets" / "icons", work / "assets" / "icons", dirs_exist_ok=True)


@contextmanager
def _quiet_audio_warning() -> Iterator[None]:
    """The samples have no narration audio by design: drop the render's "audio missing" warning."""

    def keep(record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("audio missing")

    logger = logging.getLogger("vidgen.render")
    logger.addFilter(keep)
    try:
        yield
    finally:
        logger.removeFilter(keep)


# ----- writing the media and pages -------------------------------------------------------------


def media_name(type_name: str, fmt: str, suffix: str) -> str:
    """``<type>-16x9.png`` and the like."""
    return f"{type_name}-{FORMAT_TAGS[fmt]}{suffix}"


def _save_still(source: Path, target: Path) -> None:
    from PIL import Image

    with Image.open(source) as image:
        picture = image.convert("RGB")
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG", optimize=True)
    write_bytes_atomic(target, buffer.getvalue())


def _render_format(
    types: list[GalleryType], ids: list[str], work: Path, fmt: str, output: Path, clips: bool, jobs: int, force: bool, result: GalleryResult
) -> None:
    """Render (or reuse) the samples ``ids`` in one format and write their stills and clips."""
    from vidgen import extensions
    from vidgen.export import write_gif
    from vidgen.render import ffmpeg as ff
    from vidgen.render.pipeline import render_scenes
    from vidgen.render.worker import scene_frames_dir, scene_video_path
    from vidgen.storyboard import stills_current

    project = Project.load(work, variant=None if fmt == "16:9" else PORTRAIT_VARIANT)
    with extensions.project_session(project):
        todo = [sid for sid in ids if force or not stills_current(project, True, sid, 1)]
    with _quiet_audio_warning():
        runs = render_scenes(project, True, todo, jobs=jobs, frames=1)
    result.rendered.extend(f"{sid} ({fmt})" for sid in runs.rendered)
    result.reused.extend(f"{sid} ({fmt})" for sid in ids if sid not in runs.rendered)
    result.render_warnings.extend((f"{sid} ({fmt})", message) for sid, message in runs.warnings)
    ffmpeg = ff.find_ffmpeg() if clips else ""
    media = output / "media"
    for t in types:
        if t.name not in ids:
            continue
        index_file = scene_frames_dir(project, True, t.name) / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.is_file() else {}
        if not index.get("frames"):
            raise VidgenError(f"scene type {t.name}: no still was rendered ({fmt})")
        still = scene_frames_dir(project, True, t.name) / index["frames"][-1]["path"]
        t.stills[fmt] = media / media_name(t.name, fmt, ".png")
        _save_still(still, t.stills[fmt])
        if clips:
            target = media / media_name(t.name, fmt, ".gif")
            tmp = target.with_name(f"{target.stem}.partial.gif")
            media.mkdir(parents=True, exist_ok=True)
            try:
                end = float(index["frames"][-1]["time"]) + 0.5 / FPS
                write_gif(
                    ffmpeg, scene_video_path(project, True, t.name), tmp, CLIP_WIDTHS[fmt], CLIP_FPS, 0.0, end,
                    colors=CLIP_COLORS, dither="none", hold=CLIP_HOLD,
                )
                replace_file(tmp, target)
            finally:
                remove_file(tmp)
            t.clips[fmt] = target


def _first_paragraph(text: str | None) -> str:
    """The first paragraph of a docstring on one line, its reST ````code```` as Markdown."""
    if not text:
        return ""
    return " ".join(text.strip().split("\n\n")[0].split()).replace("``", "`")


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _param_rows(model: Any, prefix: str = "", seen: tuple[type, ...] = ()) -> list[str]:
    from vidgen.describe import nested_models, other_names, type_name

    rows = []
    for name, info in model.model_fields.items():
        shown = f"{prefix}{info.alias or name}"
        if info.is_required():
            default = "required"
        else:
            value = info.get_default(call_default_factory=True)
            default = "" if value in (None, [], {}, "") else f"`{value!r}`"
        also = other_names(info)
        doc = _first_paragraph(info.description)
        if also:
            doc = (doc + " " if doc else "") + f"(also: {', '.join(also)})"
        rows.append(f"| `{shown}` | `{_cell(type_name(info.annotation, info.metadata))}` | {_cell(default)} | {_cell(doc)} |")
        for nested in nested_models(info.annotation):
            if nested not in seen and nested is not model:
                rows += _param_rows(nested, f"{shown}.", (*seen, model, nested))
    return rows


def _images(t: GalleryType, formats: list[str], height: int | None = 180, suffix: str = ".png") -> str:
    """The stills (or with ``suffix`` ``.gif`` the clips) of ``t`` side by side, ``height`` px
    high (HTML, so GitHub shows them small; ``None``: their own size)."""
    size = f' height="{height}"' if height is not None else ""
    return " ".join(f'<img src="media/{media_name(t.name, fmt, suffix)}"{size} alt="{t.name} at {fmt}">' for fmt in formats)


def write_page(t: GalleryType, output: Path, formats: list[str], uses: dict[str, str], aliases: list[str]) -> Path:
    """Write ``<output>/<type>.md``."""
    from vidgen import registry
    from vidgen.describe import scene_doc

    assert t.sample is not None
    entry = registry.get(t.name)
    lines = [f"# `{t.name}`", "", "<!-- Generated by `vidgen gallery`; edit the sample in AGENTS.md (or video.yaml), not this file. -->", ""]
    if t.name in uses:
        lines += [f"**Use it for:** {uses[t.name]}.", ""]
    doc = _first_paragraph(scene_doc(entry))
    if doc:
        lines += [doc, ""]
    if aliases:
        lines += [f"Also available as {', '.join(f'`{a}`' for a in aliases)} (the same type).", ""]
    origin = "the author guide (`vidgen guide scenes`)" if t.sample.origin == "guide" else f"`{t.sample.origin}`"
    shown = [f for f in formats if (output / "media" / media_name(t.name, f, ".png")).is_file()]
    if shown:
        lines += [f"Last beat, {' and '.join(shown)}:", "", _images(t, shown, 300), ""]
    clips = [f for f in formats if (output / "media" / media_name(t.name, f, ".gif")).is_file()]
    if clips:
        lines += ["The scene playing (GIF, up to its last beat):", "", _images(t, clips, None, ".gif"), ""]
    lines += ["## YAML", "", f"From {origin}:", "", "```yaml", t.sample.yaml.rstrip(), "```", ""]
    model = entry.params_model
    lines += ["## Params", ""]
    if model is None:
        lines += ["Free-form (a plain mapping).", ""]
    else:
        lines += ["| param | type | default | notes |", "|---|---|---|---|", *_param_rows(model), ""]
    targets = list(entry.cls.target_patterns)
    lines += ["## Targets", "", ", ".join(f"`{p}`" for p in targets) if targets else "None.", ""]
    lines += ["## Beats", "", entry.cls.beat_count_text() or "Any number.", ""]
    lines += ["[All scene types](README.md) · `vidgen list-scenes` · `vidgen schema --scene " + t.name + "`", ""]
    path = output / f"{t.name}.md"
    write_text_atomic(path, "\n".join(lines))
    return path


def _use_from_doc(type_name: str) -> str:
    """The first sentence of a type's description (a project's type has no chooser row)."""
    from vidgen import registry
    from vidgen.describe import scene_doc

    entry = registry.find(type_name)
    doc = _first_paragraph(scene_doc(entry)) if entry is not None else ""
    return doc.split(". ")[0].rstrip(".") if doc else ""


def write_index(types: list[GalleryType], output: Path, formats: list[str], uses: dict[str, str]) -> Path:
    """Write ``<output>/README.md``: every type by group with its stills."""
    lines = [
        "# Scene gallery",
        "",
        "<!-- Generated by `vidgen gallery`; do not edit. -->",
        "",
        "Every vidgen scene type, rendered from its sample in the author guide (`AGENTS.md`,",
        "`vidgen guide scenes`): the last beat at 16:9 and 9:16; each page has the YAML, the",
        "params, the action targets and a GIF of the whole scene. Regenerate with `vidgen gallery`.",
        "",
    ]
    group = None
    by_name = {t.name: t for t in types}
    for t in types:
        base = by_name.get(t.alias_of) if t.alias_of else t
        current = base.sample.group if base is not None and base.sample is not None else "other"
        if current != group:
            group = current
            lines += [f"## {group[:1].upper()}{group[1:]}", "", "| type | stills | use it for |", "|---|---|---|"]
        use = _cell(uses.get(t.name) or uses.get(t.alias_of or "") or _use_from_doc(t.name))
        if t.alias_of is not None:
            lines.append(f"| `{t.name}` | same type as [`{t.alias_of}`]({t.alias_of}.md) | {use} |")
        elif t.sample is None:
            lines.append(f"| `{t.name}` | no sample (use it in a scene of video.yaml) | {use} |")
        elif not (output / f"{t.name}.md").is_file():
            lines.append(f"| `{t.name}` | not rendered here yet (`vidgen gallery --types {t.name}`) | {use} |")
        else:
            images = _images(t, [f for f in formats if (output / "media" / media_name(t.name, f, ".png")).is_file()])
            lines.append(f"| [`{t.name}`]({t.name}.md) | <a href=\"{t.name}.md\">{images}</a> | {use} |")
    text = "\n".join(lines) + "\n"
    text = re.sub(r"\n(## )", r"\n\n\1", text).replace("\n\n\n", "\n\n")
    path = output / "README.md"
    write_text_atomic(path, text)
    return path


# ----- the command -----------------------------------------------------------------------------


def make_gallery(
    project: Project | None,
    *,
    output: Path,
    only: list[str] | None = None,
    formats: list[str] | None = None,
    preset: str | None = None,
    clips: bool = True,
    jobs: int = 1,
    force: bool = False,
) -> GalleryResult:
    """Render every scene type's sample (``only``: these types) in ``formats`` and write the
    gallery into ``output``. ``project``: also its own types, its theme and extensions;
    ``preset``: render in this theme preset instead."""
    from vidgen import extensions, registry

    formats = formats or list(FORMATS)
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise VidgenError(f"unknown format '{unknown[0]}'; formats: {', '.join(FORMATS)}")
    if jobs < 1:
        raise VidgenError("--jobs must be at least 1")
    if project is not None:
        with extensions.project_session(project):
            types = gallery_types(project)
            names = rendered_names(types, only)
    else:
        with registry.isolated():
            extensions.load_builtins()
            types = gallery_types(None)
            names = rendered_names(types, only)
    if not names:
        raise VidgenError("no scene type to render (none has a sample)")
    # The work project always holds every sample and file, so a run for a few --types keeps the
    # other renders current (their fingerprints see the whole config and assets/).
    work = work_dir(project)
    work.mkdir(parents=True, exist_ok=True)
    config = work_config(types, project, preset)
    write_text_atomic(work / "video.yaml", yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    _copy_files(types, project, work)
    output.mkdir(parents=True, exist_ok=True)
    result = GalleryResult(output, output / "README.md", work, list(formats), types)
    for t in types:
        if t.sample is None and t.alias_of is None:
            result.warnings.append(f"scene type {t.name} has no sample; use it in a scene of video.yaml to show it")
    for fmt in formats:
        _render_format(types, names, work, fmt, output, clips, jobs, force, result)
    uses = chooser_uses()
    with extensions.project_session(Project.load(work)):
        for t in types:
            if t.name in names:
                aliases = [a.name for a in types if a.alias_of == t.name]
                t.page = write_page(t, output, list(FORMATS), uses, aliases)
        write_index(types, output, list(FORMATS), uses)
    return result
