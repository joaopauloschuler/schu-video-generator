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
#: long the last beat's end is held; the held end opens the GIF, so a page shows the finished
#: picture before it plays (and between loops). The clip ends at the last beat's end (the
#: scene's fade-out, every pixel changing, would cost the most bytes).
CLIP_WIDTHS: dict[str, int] = {"16:9": 320, "9:16": 180}
CLIP_FPS = 6
CLIP_COLORS = 32
CLIP_HOLD = 2.0
#: The clip skips the scene's empty opening: it starts at the first frame whose difference from
#: the first frame (mean grey) is this share of the largest one, at most CLIP_START_MAX s in.
CLIP_START_SHARE = 0.75
CLIP_START_MAX = 1.0
#: A clip larger than this is made again at the next lower frame rate of CLIP_FALLBACK_FPS
#: (a busy cartoon: rain, camera moves), so every GIF stays light.
CLIP_MAX_BYTES = 150_000
CLIP_FALLBACK_FPS = (5, 4)
#: Stills are saved with a palette of this many colours (flat pictures: no visible loss).
STILL_COLORS = 256
#: The work project's variant rendering 9:16.
PORTRAIT_VARIANT = "portrait"
#: Index group of a project's own types.
PROJECT_GROUP = "project types"
#: The index heading of a group when it is not the group's own name.
GROUP_TITLES: dict[str, str] = {"cartoons": "2D cartoons"}
#: Guide groups shown in the index section of another (the cell-biology types in one section).
GROUP_SECTIONS: dict[str, str] = {
    "signalling pathways": "cell biology",
    "cell cycle and division": "cell biology",
    "energy metabolism": "cell biology",
}
#: The showcases' scenes (package data): ``<name>.yaml``, each a whole config of one scene.
SHOWCASES_DIR = SAMPLE_ASSETS_DIR / "showcases"
#: Showcase sections that are not a guide group, and the line under their heading.
SECTION_NOTES: dict[str, str] = {
    "isometric cartoons": (
        "A whole isometric story, a village by a stream, a room, rain and a lamp at night: "
        "[Hazel and the Lamp by the Bridge](../../examples/iso-story/video.yaml) (`examples/iso-story`)."
    ),
    "cell biology": (
        "A whole lecture-style video, a protein's route from its gene to the blood through every scene type here: "
        "[From gene to secreted protein](../../examples/gene-to-secreted-protein/README.md) (`examples/gene-to-secreted-protein`). "
        "How to make them accurate and well paced: [the cell-biology cookbook](../COOKBOOK-CELL-BIOLOGY.md)."
    ),
    "genetics": (
        "A whole medical-genetics video, one inherited disease from a family's pedigree to the variant, a carrier test and "
        "the population: [Cystic fibrosis: from a family to a diagnosis](../../examples/cystic-fibrosis/README.md) "
        "(`examples/cystic-fibrosis`). Notation, exact numbers and counselling tone: "
        "[the genetics cookbook](../COOKBOOK-GENETICS.md)."
    ),
    "science charts": (
        "A whole physics explainer with plots and calculations, simulated nuclei, counts with a fit, the half-life worked out "
        "and carbon-14 dating: [Half-life: how radioactive decay keeps time](../../examples/radioactive-decay/README.md) "
        "(`examples/radioactive-decay`). Honest axes, error bars, fits, units and significant figures: "
        "[the science-charts cookbook](../COOKBOOK-SCIENCE-CHARTS.md)."
    ),
    "orbital mechanics": (
        "A whole orbital-mechanics explainer, why a rocket cannot fly straight to Mars, the Hohmann transfer, the transfer "
        "time and the departure burn worked out, the planets on a real date: [How to get to Mars](../../examples/mars-transfer/README.md) "
        "(`examples/mars-transfer`). Scale honesty, units, approximations to state and pacing: "
        "[the orbits cookbook](../COOKBOOK-ORBITS.md)."
    ),
}
#: The last line of a showcase's page, by section: where to read more.
SECTION_FOOTERS: dict[str, str] = {
    "cell biology": "`vidgen guide scenes` · [the cell-biology cookbook](../COOKBOOK-CELL-BIOLOGY.md)",
    "genetics": "`vidgen guide genetics` · [the genetics cookbook](../COOKBOOK-GENETICS.md)",
    "orbital mechanics": "`vidgen guide orbits` · [the orbits cookbook](../COOKBOOK-ORBITS.md)",
}
DEFAULT_FOOTER = "`vidgen guide cartoons` · `vidgen guide iso` · `vidgen guide platform`"

_FENCE = re.compile(r"```(\w*)\n(.*?)```", re.S)
_TICKED = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class Sample:
    """The canonical example of a scene type: its scene ``config`` (a ``scenes:`` entry), the
    ``yaml`` as written in its source, the index ``group``, where it came from (``guide`` or
    the project's config file name) and the ``characters:`` entries its snippet declares (a
    ``stage`` needs them; DESIGN.md §69.6)."""

    type: str
    config: dict[str, Any]
    yaml: str
    group: str
    origin: str
    characters: tuple[dict[str, Any], ...] = ()


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


@dataclass(frozen=True)
class Showcase:
    """A small scene written for the gallery to show what a scene type can do, beyond its sample
    (DESIGN.md §60.1): ``name`` (its scene's id, its page and media names), the index
    ``section`` it ends (a guide group, or a section of its own after them), its ``title`` and
    ``use`` (the "use it for" line). Its YAML is ``data/gallery/showcases/<name>.yaml``: a whole
    config with one scene."""

    name: str
    section: str
    title: str
    use: str

    @property
    def path(self) -> Path:
        return SHOWCASES_DIR / f"{self.name}.yaml"

    def text(self) -> str:
        """The YAML as written (the page shows it)."""
        return self.path.read_text(encoding="utf-8")

    def config(self) -> dict[str, Any]:
        """The config, checked to hold one scene with the showcase's name as its id."""
        data = yaml.safe_load(self.text())
        scenes = data.get("scenes") if isinstance(data, dict) else None
        if not scenes or len(scenes) != 1 or scenes[0].get("id") != self.name:
            raise VidgenError(f"showcase {self.path.name}: a config with one scene, id '{self.name}'")
        return data


#: The showcases, in index order within their sections.
SHOWCASES: tuple[Showcase, ...] = (
    Showcase("talk_in_a_room", "cartoons", "A talk in the living room", "a dialogue on a furnished set, with a close-up on the punchline"),
    Showcase("walk_in_depth", "cartoons", "Passing in the park", "characters walking towards and away from the camera, passing in front of each other"),
    Showcase("rainy_evening", "cartoons", "Rain at nightfall", "weather and evening light outdoors: rain and puddles, the sun going down, a street lamp, an umbrella"),
    Showcase("star_jump", "cartoons", "A jump for a star", "a platform level: run to the edge, jump the gap, catch a star"),
    Showcase("iso_village", "isometric cartoons", "Morning in the village", "a sunny isometric village where two characters walk to meet"),
    Showcase("iso_room", "isometric cartoons", "A cut-away room", "an isometric room seen like a dollhouse: furniture, a thing to pick up"),
    Showcase("iso_lamp", "isometric cartoons", "Lighting the lamp", "night on an isometric place: a lamp lit, a speaker's name tag"),
    Showcase("iso_snow", "isometric cartoons", "First snow", "snow settling on an isometric village: the ground, roofs and trees turn white"),
    Showcase("plant_cell", "cell biology", "Inside a plant cell", "a plant cell's wall, vacuole and chloroplasts, then a zoom into one chloroplast's grana"),
    Showcase("sodium_pump", "cell biology", "The sodium pump", "a membrane pump's cycle: 3 Na⁺ out and 2 K⁺ in per ATP, against their gradients"),
    Showcase("mek_inhibitor", "cell biology", "Blocking MEK", "a signal running down the MAPK cascade, then a drug that blocks MEK and its effects downstream"),
    Showcase("mitosis", "cell biology", "Mitosis", "a dividing cell: condensation, the metaphase plate, sister chromatids parting, two daughter cells"),
    Showcase("respiratory_chain", "cell biology", "The respiratory chain", "electrons down complexes I–IV with protons pumped, then ATP synthase turning"),
    Showcase("mars_hohmann", "orbital mechanics", "The Hohmann transfer to Mars",
             "a transfer between two planets: the phase angle at the launch window, two burns on words, the Δv and the time computed"),
    Showcase("jupiter_trojans", "orbital mechanics", "Trojans in the rotating frame",
             "a three-body system in the frame turning with Jupiter: the five Lagrange points standing still, a Trojan's tadpole "
             "inside its zero-velocity curve"),
)


@dataclass
class GalleryShowcase:
    """A showcase in a gallery run: the ``showcase``, its written ``page`` and ``stills`` /
    ``clips`` by format."""

    showcase: Showcase
    page: Path | None = None
    stills: dict[str, Path] = field(default_factory=dict)
    clips: dict[str, Path] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.showcase.name


@dataclass
class GalleryResult:
    """What :func:`make_gallery` did: the folder and its index, the work project, the formats,
    every type (index order) and showcase, the samples rendered / reused as ``"<name>
    (<format>)"``, the gallery's own ``warnings`` (types without a sample) and the render
    workers' warnings ``(sample, message)`` (already printed while rendering)."""

    output: Path
    index: Path
    work: Path
    formats: list[str]
    types: list[GalleryType]
    showcases: list[GalleryShowcase] = field(default_factory=list)
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


def _config_snippet(body: str) -> tuple[str, str, dict[str, Any]] | None:
    """A YAML block of the guide that is a config (``characters:`` and ``scenes:``, for types
    that need top-level entries) as ``(group, its text without the group comment, the
    mapping)``; ``None`` for a block that is a list of scenes."""
    data = yaml.safe_load(body)
    if not isinstance(data, dict):
        return None
    lines = body.splitlines()
    group = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else ""
    text = "\n".join(lines[1:] if group else lines).rstrip() + "\n"
    return group, text, data


def guide_samples() -> dict[str, Sample]:
    """Type name -> sample from the guide's ``scenes`` topic (its first snippet of the type; a
    later one replaces a snippet that uses ``generate:``, which only renders a placeholder). A
    block that is a config (``characters:`` + ``scenes:``) is one sample per scene, shown whole."""
    from vidgen.guide import find_topic

    samples: dict[str, Sample] = {}
    for lang, body in _FENCE.findall(find_topic("scenes").text):
        if lang != "yaml":
            continue
        config = _config_snippet(body)
        if config is not None:
            group, text, data = config
            found = [(scene, text, tuple(data.get("characters") or ())) for scene in data.get("scenes") or []]
        else:
            group, items = _snippet_items(body)
            found = [(yaml.safe_load(text)[0], text, ()) for text in items]
        group = GROUP_SECTIONS.get(group, group)
        for scene, text, characters in found:
            name = scene["type"]
            known = samples.get(name)
            if known is None or "generate" in known.config.get("params", {}):
                samples[name] = Sample(name, scene, text, group, "guide", characters)
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
            sample = Sample(entry.name, {**sample.config, "type": entry.name}, text, sample.group, sample.origin, sample.characters)
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
    type renders it under its own name; a showcase's name is left to :func:`rendered_showcases`);
    an unknown name is a :class:`VidgenError`."""
    from vidgen import registry

    by_name = {t.name: t for t in types}
    showcases = {s.name for s in SHOWCASES}
    unknown = [n for n in only or [] if n not in by_name and n not in showcases]
    if unknown:
        raise VidgenError(registry.unknown_type_message(unknown[0]))
    wanted = {by_name[n].alias_of or n for n in only if n in by_name} if only else set(by_name)
    return [t.name for t in types if t.name in wanted and t.alias_of is None and t.sample is not None]


def rendered_showcases(only: list[str] | None) -> list[Showcase]:
    """The showcases to render: all, or those named in ``only``."""
    return [s for s in SHOWCASES if only is None or s.name in only]


# ----- the work project ------------------------------------------------------------------------


def work_dir(project: Project | None) -> Path:
    """Where the samples are rendered: ``<project>/build/gallery`` or ``./build/gallery``."""
    return (project.root if project is not None else Path.cwd()) / "build" / "gallery"


def work_config(types: list[GalleryType], project: Project | None, preset: str | None) -> dict[str, Any]:
    """The work project's config: one scene per rendered type (id = type name), the characters
    the samples declare (the first entry of a name), 16:9 preview, 9:16 as the ``portrait``
    variant; the project's theme and extensions."""
    scenes = []
    characters: dict[str, dict[str, Any]] = {}
    for t in types:
        if t.alias_of is None and t.sample is not None:
            scenes.append({**t.sample.config, "id": t.name})
            for entry in t.sample.characters:
                characters.setdefault(entry["name"], entry)
    config: dict[str, Any] = {"title": "vidgen gallery", "output": "gallery", **_formats_keys(), "extensions": [], "scenes": scenes}
    if characters:
        config["characters"] = list(characters.values())
    if project is not None:
        from vidgen.extensions import extension_dirs

        config["extensions"] = [str(d) for d in extension_dirs(project)]
        theme = project.config.theme.model_dump(mode="json", exclude_defaults=True)
        if theme:
            config["theme"] = theme
    if preset is not None:
        config["theme"] = {"preset": preset}
    return config


def _formats_keys() -> dict[str, Any]:
    """A work project's ``preview`` (16:9) and ``variants`` (9:16 as ``portrait``) keys."""
    (w, h), (pw, ph) = FORMATS["16:9"], FORMATS["9:16"]
    return {
        "preview": {"width": w, "height": h, "fps": FPS},
        "variants": {PORTRAIT_VARIANT: {"preview": {"width": pw, "height": ph, "fps": FPS}}},
    }


def showcase_work_config(showcase: Showcase, preset: str | None) -> dict[str, Any]:
    """A showcase's work project config: its own config at the gallery's sizes (``preset``: in
    this theme preset)."""
    config = {**showcase.config(), "output": showcase.name, **_formats_keys()}
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
    # a 256-colour palette, no dithering: flat pictures lose nothing visible and the PNG is about
    # 40 % of the RGB one (the gallery's budget, HANDOFF Step 210)
    picture = picture.quantize(colors=STILL_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG", optimize=True)
    write_bytes_atomic(target, buffer.getvalue())


def clip_start(frames: Any, fps: float) -> float:
    """Where a clip of ``frames`` (grey, ``(n, h, w)``, ``fps`` a second) starts: at the first
    frame whose difference from the first frame is :data:`CLIP_START_SHARE` of the largest one
    (the empty opening and most of a fade-in skipped), at most :data:`CLIP_START_MAX` s in; 0
    when the picture hardly changes."""
    import numpy as np

    pictures = np.asarray(frames, dtype=np.float32)
    moved = np.abs(pictures - pictures[0]).mean(axis=(1, 2))
    if float(moved.max()) < 1.0:
        return 0.0
    first = int(np.argmax(moved >= CLIP_START_SHARE * float(moved.max())))
    return min(first / fps, CLIP_START_MAX)


def _write_clip(ffmpeg: str, video: Path, target: Path, fmt: str, end: float) -> None:
    """The GIF of ``video`` up to ``end`` s: from :func:`clip_start`, the end held first, at
    :data:`CLIP_FPS` or, over :data:`CLIP_MAX_BYTES`, a lower rate of :data:`CLIP_FALLBACK_FPS`."""
    from vidgen.export import write_gif
    from vidgen.render.ffmpeg import decode_gray_frames

    start = clip_start(decode_gray_frames(video, 64, CLIP_FPS, end), CLIP_FPS)
    tmp = target.with_name(f"{target.stem}.partial.gif")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        for fps in (CLIP_FPS, *CLIP_FALLBACK_FPS):
            size = write_gif(
                ffmpeg, video, tmp, CLIP_WIDTHS[fmt], fps, start, end,
                colors=CLIP_COLORS, dither="none", hold=CLIP_HOLD, hold_first=True,
            )
            if size <= CLIP_MAX_BYTES:
                break
        replace_file(tmp, target)
    finally:
        remove_file(tmp)


def _render_format(
    entries: list[GalleryType] | list[GalleryShowcase], ids: list[str], work: Path, fmt: str, output: Path,
    clips: bool, jobs: int, force: bool, result: GalleryResult,
) -> None:
    """Render (or reuse) the scenes ``ids`` of the work project ``work`` (a type's sample or a
    showcase, by its name) in one format and write their stills and clips."""
    from vidgen import extensions
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
    for entry in entries:
        if entry.name not in ids:
            continue
        index_file = scene_frames_dir(project, True, entry.name) / "index.json"
        index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.is_file() else {}
        if not index.get("frames"):
            raise VidgenError(f"gallery scene {entry.name}: no still was rendered ({fmt})")
        still = scene_frames_dir(project, True, entry.name) / index["frames"][-1]["path"]
        entry.stills[fmt] = media / media_name(entry.name, fmt, ".png")
        _save_still(still, entry.stills[fmt])
        if clips:
            end = float(index["frames"][-1]["time"]) + 0.5 / FPS
            entry.clips[fmt] = media / media_name(entry.name, fmt, ".gif")
            _write_clip(ffmpeg, scene_video_path(project, True, entry.name), entry.clips[fmt], fmt, end)


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


def _images(name: str, formats: list[str], height: int | None = 180, suffix: str = ".png") -> str:
    """The stills (or with ``suffix`` ``.gif`` the clips) of ``name`` side by side, ``height`` px
    high (HTML, so GitHub shows them small; ``None``: their own size)."""
    size = f' height="{height}"' if height is not None else ""
    return " ".join(f'<img src="media/{media_name(name, fmt, suffix)}"{size} alt="{name} at {fmt}">' for fmt in formats)


def preview_html(name: str, fmt: str, media: str = "media", height: int | None = 180, link: str | None = None) -> str:
    """One format's animated preview of ``name``: its GIF in a ``<picture>`` whose source for
    viewers who ask for reduced motion is the still; ``link``: wrapped in a link to it. ``media``
    is the media folder as the page refers to it."""
    size = f' height="{height}"' if height is not None else ""
    png, gif = (f"{media}/{media_name(name, fmt, suffix)}" for suffix in (".png", ".gif"))
    picture = (
        f'<picture><source media="(prefers-reduced-motion: reduce)" srcset="{png}">'
        f'<img src="{gif}"{size} alt="{name} at {fmt}"></picture>'
    )
    return f'<a href="{link}">{picture}</a>' if link is not None else picture


def _previews(name: str, output: Path, formats: list[str]) -> str:
    """The index cell of ``name``: each format's preview linked to its page (the still alone
    for a format whose GIF is not in the folder)."""
    cells = []
    for fmt in formats:
        if (output / "media" / media_name(name, fmt, ".gif")).is_file():
            cells.append(preview_html(name, fmt, link=f"{name}.md"))
        elif (output / "media" / media_name(name, fmt, ".png")).is_file():
            cells.append(f'<a href="{name}.md">{_images(name, [fmt])}</a>')
    return " ".join(cells)


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
        lines += [f"Last beat, {' and '.join(shown)}:", "", _images(t.name, shown, 300), ""]
    clips = [f for f in formats if (output / "media" / media_name(t.name, f, ".gif")).is_file()]
    if clips:
        lines += ["The scene playing (GIF, up to its last beat):", "", _images(t.name, clips, None, ".gif"), ""]
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


def write_showcase_page(showcase: Showcase, output: Path, formats: list[str]) -> Path:
    """Write ``<output>/<showcase>.md``: what it is for, the scene playing, its stills, the YAML."""
    used = list(dict.fromkeys(scene["type"] for scene in showcase.config()["scenes"]))
    links = ", ".join(f"[`{name}`]({name}.md)" for name in used)
    lines = [
        f"# {showcase.title}",
        "",
        f"<!-- Generated by `vidgen gallery`; edit src/vidgen/data/gallery/showcases/{showcase.path.name}, not this file. -->",
        "",
        f"**Use it for:** {showcase.use}.",
        "",
        f"A showcase of {links}: a small scene written for the gallery, a whole `video.yaml`. Copy it into a",
        "project and run `vidgen render`; until `vidgen tts` voices it, its beats are timed by their word count.",
        "",
    ]
    clips = [f for f in formats if (output / "media" / media_name(showcase.name, f, ".gif")).is_file()]
    if clips:
        lines += [f"The scene playing, {' and '.join(clips)}:", "", " ".join(preview_html(showcase.name, f, height=None) for f in clips), ""]
    shown = [f for f in formats if (output / "media" / media_name(showcase.name, f, ".png")).is_file()]
    if shown:
        lines += ["Last beat:", "", _images(showcase.name, shown, 300), ""]
    lines += ["## YAML", "", "```yaml", showcase.text().rstrip(), "```", ""]
    lines += [f"[All scene types and showcases](README.md) · {SECTION_FOOTERS.get(showcase.section, DEFAULT_FOOTER)}", ""]
    path = output / f"{showcase.name}.md"
    write_text_atomic(path, "\n".join(lines))
    return path


def _type_row(t: GalleryType, output: Path, formats: list[str], uses: dict[str, str]) -> str:
    """The index row of a scene type."""
    use = _cell(uses.get(t.name) or uses.get(t.alias_of or "") or _use_from_doc(t.name))
    if t.alias_of is not None:
        return f"| `{t.name}` | same type as [`{t.alias_of}`]({t.alias_of}.md) | {use} |"
    if t.sample is None:
        return f"| `{t.name}` | no sample (use it in a scene of video.yaml) | {use} |"
    if not (output / f"{t.name}.md").is_file():
        return f"| `{t.name}` | not rendered here yet (`vidgen gallery --types {t.name}`) | {use} |"
    return f"| [`{t.name}`]({t.name}.md) | {_previews(t.name, output, formats)} | {use} |"


def _showcase_row(showcase: Showcase, output: Path, formats: list[str]) -> str:
    """The index row of a showcase."""
    if not (output / f"{showcase.name}.md").is_file():
        return f"| {showcase.title} | not rendered here yet (`vidgen gallery --types {showcase.name}`) | {_cell(showcase.use)} |"
    return f"| [{showcase.title}]({showcase.name}.md) | {_previews(showcase.name, output, formats)} | {_cell(showcase.use)} |"


def write_index(
    types: list[GalleryType], output: Path, formats: list[str], uses: dict[str, str], showcases: list[Showcase] | tuple[Showcase, ...] = ()
) -> Path:
    """Write ``<output>/README.md``: every type by group with its previews, each group's
    showcases after its types (a showcase section that is no group after the groups)."""
    sections: dict[str, list[str]] = {}
    by_name = {t.name: t for t in types}
    for t in types:
        base = by_name.get(t.alias_of) if t.alias_of else t
        group = base.sample.group if base is not None and base.sample is not None else "other"
        sections.setdefault(group, []).append(_type_row(t, output, formats, uses))
    type_groups = set(sections)
    for showcase in showcases:
        sections.setdefault(showcase.section, []).append(_showcase_row(showcase, output, formats))
    with_showcases = {s.section for s in showcases}
    lines = [
        "# Scene gallery",
        "",
        "<!-- Generated by `vidgen gallery`; do not edit. -->",
        "",
        "Every vidgen scene type, rendered from its sample in the author guide (`AGENTS.md`,",
        "`vidgen guide scenes`). The previews are animated: each GIF plays the scene at 16:9 and",
        "9:16 and holds its last beat (viewers who ask for reduced motion see that still instead).",
        "Each page has the YAML, the params, the action targets and the stills. The cell-biology and",
        "cartoon sections end with showcases, small scenes written for the gallery, each a whole `video.yaml`.",
        "Regenerate with `vidgen gallery`.",
        "",
    ]
    for group, rows in sections.items():
        title = GROUP_TITLES.get(group, group)
        lines += [f"## {title[:1].upper()}{title[1:]}", ""]
        if group in SECTION_NOTES:
            lines += [SECTION_NOTES[group], ""]
        first = {(True, False): "type", (True, True): "type or showcase", (False, True): "showcase"}[(group in type_groups, group in with_showcases)]
        lines += [f"| {first} | preview | use it for |", "|---|---|---|", *rows, ""]
    path = output / "README.md"
    write_text_atomic(path, "\n".join(lines))
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
    # the showcases belong to the built-in gallery, not to a project's
    showcases = [] if project is not None else rendered_showcases(only)
    if not names and not showcases:
        raise VidgenError("no scene type to render (none has a sample)")
    # The work project always holds every sample and file, so a run for a few --types keeps the
    # other renders current (their fingerprints see the whole config and assets/).
    work = work_dir(project)
    work.mkdir(parents=True, exist_ok=True)
    config = work_config(types, project, preset)
    write_text_atomic(work / "video.yaml", yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
    _copy_files(types, project, work)
    output.mkdir(parents=True, exist_ok=True)
    result = GalleryResult(output, output / "README.md", work, list(formats), types, [GalleryShowcase(s) for s in showcases])
    for t in types:
        if t.sample is None and t.alias_of is None:
            result.warnings.append(f"scene type {t.name} has no sample; use it in a scene of video.yaml to show it")
    for fmt in formats:
        if names:
            _render_format(types, names, work, fmt, output, clips, jobs, force, result)
        # each showcase is a project of its own (its characters, sets and voices)
        for entry in result.showcases:
            showcase_work = work / "showcases" / entry.name
            showcase_work.mkdir(parents=True, exist_ok=True)
            text = yaml.safe_dump(showcase_work_config(entry.showcase, preset), sort_keys=False, allow_unicode=True)
            write_text_atomic(showcase_work / "video.yaml", text)
            _render_format([entry], [entry.name], showcase_work, fmt, output, clips, jobs, force, result)
    uses = chooser_uses()
    with extensions.project_session(Project.load(work)):
        for t in types:
            if t.name in names:
                aliases = [a.name for a in types if a.alias_of == t.name]
                t.page = write_page(t, output, list(FORMATS), uses, aliases)
        for entry in result.showcases:
            entry.page = write_showcase_page(entry.showcase, output, list(FORMATS))
        write_index(types, output, list(FORMATS), uses, SHOWCASES if project is None else ())
    return result
