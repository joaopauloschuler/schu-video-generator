"""``vidgen gallery``: every scene type rendered from one canonical sample, at
16:9 and 9:16, written as Markdown pages with stills and short GIF clips.

**Samples.** A built-in type's sample is its snippet in the author guide's ``scenes`` topic
(``data/guide/scenes.md``, ``vidgen guide scenes``; the first one of the type, preferring one without a generated picture), so the
guide and the gallery show the same YAML. Files the snippets name under ``assets/`` are the
small pictures and clip shipped in ``data/gallery/``, and the page the ``web`` snippet names is
``data/gallery/web/<name>`` (:func:`sample_asset`). A project's own
types (run in a project) take the first scene of that type in its ``video.yaml``. Names that
are another name of the same class (``flowchart`` / ``diagram``) are rendered once.

**Rendering.** The samples become one work project in ``<project or .>/build/gallery`` (16:9 at
:data:`FORMATS` sizes, 9:16 as its ``portrait`` variant), rendered with one still per beat like
``vidgen storyboard`` (current stills are reused, by the render fingerprint). A type's still is
its last beat's end; its clip is the scene's render as a palette GIF.

**Output** (default ``docs/gallery``): ``README.md`` (the index: every registered type by group,
with its stills), ``<type>.md`` (what it is for, stills, clips, the YAML, params, targets,
beats) and ``media/<type>-16x9.png|gif``, ``media/<type>-9x16.png|gif``. Nothing in them depends
on the time or the machine, so regenerating with the same schu-video-generator gives the same files.

**Two galleries**: the entries of types drawn by a web page in headless
Chromium (``NarratedScene.drawn_in_browser``: ``web``, ``3d``, ``space``) and the showcases using
one go to ``web/`` (its own ``README.md``, pages and ``media/``); the indexes link each other and
the YouTube section ends the main one.
"""

from __future__ import annotations

import html
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
#: Files of a ``web`` snippet (its ``page`` or ``script``) shipped in ``data/gallery/web``.
WEB_SUFFIXES = (".html", ".htm", ".js", ".mjs")
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
#: (a busy cartoon: rain, camera moves), then with CLIP_FALLBACK_COLORS colours at the lowest
#: rates (a star field under a camera move: every frame differs everywhere), so every GIF stays light.
CLIP_MAX_BYTES = 150_000
CLIP_FALLBACK_FPS = (5, 4)
CLIP_FALLBACK_COLORS = ((4, 16), (3, 16), (2, 16), (2, 8))
#: ...and a clip that needs fewer colours is noise more than picture: it is held to this, so its entry
#: (two clips, two stills, a page) stays within its share of the gallery.
CLIP_NOISY_MAX_BYTES = 95_000
#: Stills are saved with a palette of this many colours (flat pictures: no visible loss).
STILL_COLORS = 256
#: A still heavier than this is saved again with the next palette of STILL_FALLBACK_COLORS (star fields, skies at dusk).
STILL_MAX_BYTES = 80_000
STILL_FALLBACK_COLORS = (128, 64, 32, 16)
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
    "particle physics": (
        "A whole particle-physics explainer, the Standard Model, gluon fusion through a top loop, the decay modes, a diphoton "
        "event, the invariant mass worked out, a simulated spectrum with its bump and fit and what five sigma means: "
        "[How the Higgs boson was found](../../examples/higgs-discovery/README.md) (`examples/higgs-discovery`). Natural units, "
        "simulated data, sources, significance and pacing: [the particle-physics cookbook](../COOKBOOK-PARTICLES.md)."
    ),
}
#: The web gallery's section notes (links relative to ``docs/gallery/web``), as SECTION_NOTES for the main one.
WEB_SECTION_NOTES: dict[str, str] = {
    "pictures and media": (
        "Whole films of `web` scenes: [Escapement](../../../examples/escapement/README.md) (`examples/escapement`), a 3:11 "
        "clockwork music film in three.js whose watch movement ticks on the score's beat, "
        "[Parallel Space](../../../examples/parallel-space/README.md) (`examples/parallel-space`), a 3:05 trance and "
        "choir film of a flight through parallel realities, and "
        "[Signal Fire](../../../examples/signal-fire/README.md) (`examples/signal-fire`), a 27 s orchestral cue with its picture. "
        "Seven portrait orchestral music videos of about 35 s, sharing one scene module: "
        "[Orchestral shorts](../../../examples/orchestral-shorts/README.md) (`examples/orchestral-shorts`). "
        "A film of `space` scenes written in YAML alone: [Outbound](../../../examples/outbound/README.md) (`examples/outbound`), "
        "58 s from a sunrise over a world, past a ringed giant, to a black hole, with an orchestral score. "
        "How to make them: [the 3D cookbook](../../COOKBOOK-3D.md), [the space cookbook](../../COOKBOOK-SPACE.md) and [the air cookbook](../../COOKBOOK-AIR.md)."
    ),
}
#: The web gallery's folder under the gallery's output: the entries of types drawn
#: in headless Chromium (``NarratedScene.drawn_in_browser``: ``web``, ``3d``, ``space``) and the
#: showcases using one, with an index of their own.
WEB_FOLDER = "web"
#: The last line of a showcase's page, by section: where to read more.
SECTION_FOOTERS: dict[str, str] = {
    "cell biology": "`vidgen guide scenes` · [the cell-biology cookbook](../COOKBOOK-CELL-BIOLOGY.md)",
    "genetics": "`vidgen guide genetics` · [the genetics cookbook](../COOKBOOK-GENETICS.md)",
    "orbital mechanics": "`vidgen guide orbits` · [the orbits cookbook](../COOKBOOK-ORBITS.md)",
    "particle physics": "`vidgen guide particle-physics` · [the particle-physics cookbook](../COOKBOOK-PARTICLES.md)",
    "pictures and media": "`vidgen guide space-scenes` · [the space cookbook](../COOKBOOK-SPACE.md) · [the air cookbook](../COOKBOOK-AIR.md)",
}
#: Videos made with schu-video-generator and published on YouTube, listed at the end of the index.
YOUTUBE_VIDEOS: list[dict[str, str]] = [
    {
        "title": "How to create this AI music video in the video description",
        "url": "https://youtu.be/J8gljBhqtTo",
    },
    {
        "title": "How to create long cartoon videos with AI? I will teach you!",
        "url": "https://youtu.be/tjqrvbYNbGE",
    },
]
#: YouTube Shorts made with schu-video-generator, shown as a row of thumbnails under the videos.
YOUTUBE_SHORTS: list[dict[str, str]] = [
    {"title": "eclipse", "url": "https://www.youtube.com/shorts/gLsKCVGfdz4"},
    {"title": "Ascension", "url": "https://www.youtube.com/shorts/cEob9Rqooqo"},
    {"title": "Choir of the Void", "url": "https://www.youtube.com/shorts/8EZThIyJKOQ"},
    {"title": "Gate of Stars", "url": "https://www.youtube.com/shorts/nSDKRQBD6V4"},
    {"title": "The Signal", "url": "https://www.youtube.com/shorts/VIaxZaXD56Y"},
    {"title": "First Light", "url": "https://www.youtube.com/shorts/y1zxGYL9OOE"},
    {"title": "YouTube Short 7", "url": "https://www.youtube.com/shorts/TSMGYvusLXA"},
    {"title": "YouTube Short 8", "url": "https://www.youtube.com/shorts/CrLAV33RlIU"},
    {"title": "Moon of Fire", "url": "https://www.youtube.com/shorts/78nKM7xIsRE"},
    {"title": "Orchestra", "url": "https://www.youtube.com/shorts/rHDSSkKPzPw"},
]


_YOUTUBE_ID = re.compile(
    r"https://(?:youtu\.be/|(?:www\.)?youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/))([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])"
)


def youtube_id(url: str) -> str:
    """The video id of a ``https://youtu.be/<id>``, ``https://www.youtube.com/watch?v=<id>`` or
    ``https://www.youtube.com/shorts/<id>`` link."""
    match = _YOUTUBE_ID.match(url)
    if match is None:
        raise VidgenError(
            f"not a YouTube video link: {url!r} (expected https://youtu.be/<id>, https://www.youtube.com/watch?v=<id>"
            " or https://www.youtube.com/shorts/<id>)"
        )
    return match.group(1)


def youtube_lines() -> list[str]:
    """The index's "Videos on YouTube" section: one clickable thumbnail per video, its title as the alt text,
    then "Shorts": the Shorts' thumbnails side by side in one paragraph (180 px high, as the gallery's previews),
    each linking to its Shorts page.

    The thumbnail is YouTube's own (``img.youtube.com``), so no image is kept in the repository.
    """
    if not YOUTUBE_VIDEOS and not YOUTUBE_SHORTS:
        return []
    lines = ["## Videos on YouTube", "", "Videos made with schu-video-generator:", ""]
    for v in YOUTUBE_VIDEOS:
        vid = youtube_id(v["url"])
        lines += [f"[![{v['title']}](https://img.youtube.com/vi/{vid}/hqdefault.jpg)](https://youtu.be/{vid})", ""]
    if YOUTUBE_SHORTS:
        thumbs = [
            f'<a href="{html.escape(v["url"])}"><img src="https://img.youtube.com/vi/{youtube_id(v["url"])}/hqdefault.jpg"'
            f' height="180" alt="{html.escape(v["title"])}"></a>'
            for v in YOUTUBE_SHORTS
        ]
        lines += ["### Shorts", "", " ".join(thumbs), ""]
    return lines


DEFAULT_FOOTER = "`vidgen guide cartoons` · `vidgen guide iso` · `vidgen guide platform`"

_FENCE = re.compile(r"```(\w*)\n(.*?)```", re.S)
_TICKED = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class Sample:
    """The canonical example of a scene type: its scene ``config`` (a ``scenes:`` entry), the
    ``yaml`` as written in its source, the index ``group``, where it came from (``guide`` or
    the project's config file name) and the ``characters:`` entries its snippet declares (a
    ``stage`` needs them)."""

    type: str
    config: dict[str, Any]
    yaml: str
    group: str
    origin: str
    characters: tuple[dict[str, Any], ...] = ()


@dataclass
class GalleryType:
    """One scene type of the gallery: ``name``; ``alias_of`` (the name it is rendered under) or
    ``None``; the ``sample`` (``None``: none found, not rendered); ``web``: in the web gallery (its
    class is drawn in headless Chromium, :func:`is_web_type`); the written ``page`` and
    ``stills`` / ``clips`` by format."""

    name: str
    alias_of: str | None
    sample: Sample | None
    web: bool = False
    page: Path | None = None
    stills: dict[str, Path] = field(default_factory=dict)
    clips: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class Showcase:
    """A small scene written for the gallery to show what a scene type can do, beyond its sample:
    ``name`` (its scene's id, its page and media names), the index
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
    Showcase("iso_lab", "isometric cartoons", "The night shift",
             "a lab at night: a hologram materialises, screens and blinking racks, shutters, a rift with a starry sky inside"),
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
    Showcase("higgs_diphoton", "particle physics", "A Higgs boson in two photons",
             "a simulated H → γγ event: two ECAL showers and no tracks, the photons' p_T and η and their invariant mass, "
             "125 GeV/c²"),
    Showcase("sunset_skim", "pictures and media", "A skim at sunset", "a surface scene: a world's own air and sea, 14 m over the water towards a low sun"),
    Showcase("orbit_to_sea", "pictures and media", "From orbit to the sea", "a descent in one shot from 400 km through the air to the cloud decks and the sea"),
    Showcase("carrier_pass", "pictures and media", "Along a giant ship", "a pass along a dressed 3.2 km ship over the Earth, a 50 m craft beside it for size"),
)


@dataclass
class GalleryShowcase:
    """A showcase in a gallery run: the ``showcase``, ``web`` (in the web gallery: one of its scene
    types is, :func:`is_web_showcase`), its written ``page`` and ``stills`` / ``clips`` by format."""

    showcase: Showcase
    web: bool = False
    page: Path | None = None
    stills: dict[str, Path] = field(default_factory=dict)
    clips: dict[str, Path] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.showcase.name


@dataclass
class GalleryResult:
    """What :func:`make_gallery` did: the folder and its index, the work project, the formats,
    every type (index order) and showcase, the web gallery's index (``None``: no web entry), the
    samples rendered / reused as ``"<name> (<format>)"``, the gallery's own ``warnings`` (types
    without a sample) and the render workers' warnings ``(sample, message)`` (already printed while
    rendering)."""

    output: Path
    index: Path
    work: Path
    formats: list[str]
    types: list[GalleryType]
    showcases: list[GalleryShowcase] = field(default_factory=list)
    web_index: Path | None = None
    rendered: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    render_warnings: list[tuple[str, str]] = field(default_factory=list)

    @property
    def bytes(self) -> int:
        """Total size of the files in the output folder (the web gallery's included)."""
        return sum(p.stat().st_size for p in self.output.rglob("*") if p.is_file())


# ----- the two galleries -----------------------------------------------------------------------


def is_web_type(name: str) -> bool:
    """Whether scene type ``name`` (the current registry) is drawn by a web page in headless
    Chromium (``NarratedScene.drawn_in_browser``): its entry goes to the web gallery."""
    from vidgen import registry

    entry = registry.find(name)
    return entry is not None and bool(getattr(entry.cls, "drawn_in_browser", False))


def is_web_showcase(showcase: Showcase) -> bool:
    """Whether a showcase goes to the web gallery: one of its scenes is of a web type."""
    return any(is_web_type(scene["type"]) for scene in showcase.config()["scenes"])


def gallery_folder(output: Path, web: bool) -> Path:
    """The folder an entry's page and ``media/`` go in: ``output`` or, for a web entry,
    ``output/web`` (:data:`WEB_FOLDER`)."""
    return output / WEB_FOLDER if web else output


def page_link(name: str, web: bool, from_web: bool) -> str:
    """The relative link to entry ``name``'s page (in the web gallery if ``web``) from a page of
    the web gallery (``from_web``) or of the main one."""
    if web == from_web:
        return f"{name}.md"
    return f"{WEB_FOLDER}/{name}.md" if web else f"../{name}.md"


_UP_LINK = re.compile(r"\]\(\.\./")


def relink_for_web(text: str) -> str:
    """Markdown written for a page of the main gallery (links ``](../...)``) as it reads from the
    web gallery, one folder deeper."""
    return _UP_LINK.sub("](../../", text)


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
    for ``image``, the app screenshot for other pictures, the screen recording for videos; for a
    ``web`` snippet's page or script, the file of that name in ``data/gallery/web``."""
    suffix = Path(rel).suffix.lower()
    if suffix in WEB_SUFFIXES:
        page = SAMPLE_ASSETS_DIR / "web" / Path(rel).name
        if page.is_file():
            return page
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
        web = bool(getattr(entry.cls, "drawn_in_browser", False))   # as is_web_type, for this entry
        if entry.cls in canonical:
            types.append(GalleryType(entry.name, canonical[entry.cls], None, web))
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
        types.append(GalleryType(entry.name, None, sample, web))
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


def _is_web_entry(sample: Sample, value: str) -> bool:
    """``value`` is the page or script a ``web`` sample names."""
    params = sample.config.get("params") or {}
    return sample.type == "web" and value in (params.get("page"), params.get("script"))


def _copy_files(types: list[GalleryType], project: Project | None, work: Path) -> None:
    """Put the files the samples name into the work project: shipped stand-ins for the guide's
    ``assets/...`` paths and its ``web`` page, the project's own files (and its
    ``assets/icons``) for its samples."""
    for t in types:
        if t.sample is None or t.alias_of is not None:
            continue
        for value in _strings(t.sample.config.get("params", {})):
            source: Path | None = None
            if t.sample.origin == "guide" and (value.startswith("assets/") or _is_web_entry(t.sample, value)):
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
    # 40 % of the RGB one (the gallery's budget, HANDOFF Step 210); a picture of fine noise (a star
    # field) that is still heavy gets fewer colours
    for colors in (STILL_COLORS, *STILL_FALLBACK_COLORS):
        buffer = io.BytesIO()
        picture.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(buffer, format="PNG", optimize=True)
        if buffer.tell() <= STILL_MAX_BYTES:
            break
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
    :data:`CLIP_FPS` or, over :data:`CLIP_MAX_BYTES`, a lower rate of :data:`CLIP_FALLBACK_FPS`, then
    fewer colours (:data:`CLIP_FALLBACK_COLORS`, held to :data:`CLIP_NOISY_MAX_BYTES`)."""
    from vidgen.export import write_gif
    from vidgen.render.ffmpeg import decode_gray_frames

    start = clip_start(decode_gray_frames(video, 64, CLIP_FPS, end), CLIP_FPS)
    tmp = target.with_name(f"{target.stem}.partial.gif")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        steps = [(fps, CLIP_COLORS, CLIP_MAX_BYTES) for fps in (CLIP_FPS, *CLIP_FALLBACK_FPS)]
        steps += [(fps, colors, CLIP_NOISY_MAX_BYTES) for fps, colors in CLIP_FALLBACK_COLORS]
        for fps, colors, most in steps:
            size = write_gif(
                ffmpeg, video, tmp, CLIP_WIDTHS[fmt], fps, start, end,
                colors=colors, dither="none", hold=CLIP_HOLD, hold_first=True,
            )
            if size <= most:
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
    for entry in entries:
        if entry.name not in ids:
            continue
        media = gallery_folder(output, entry.web) / "media"
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
    """Write ``<output>/<type>.md`` (a web type's: ``<output>/web/<type>.md``)."""
    from vidgen import registry
    from vidgen.describe import scene_doc

    assert t.sample is not None
    entry = registry.get(t.name)
    lines = [f"# `{t.name}`", "", "<!-- Generated by `vidgen gallery`; edit the sample in `vidgen guide scenes` (src/vidgen/data/guide/scenes.md) or video.yaml, not this file. -->", ""]
    if t.name in uses:
        lines += [f"**Use it for:** {uses[t.name]}.", ""]
    doc = _first_paragraph(scene_doc(entry))
    if doc:
        lines += [doc, ""]
    if aliases:
        lines += [f"Also available as {', '.join(f'`{a}`' for a in aliases)} (the same type).", ""]
    origin = "the author guide (`vidgen guide scenes`)" if t.sample.origin == "guide" else f"`{t.sample.origin}`"
    output = gallery_folder(output, t.web)
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
    index = "[All web scenes](README.md) · [All scene types](../README.md)" if t.web else "[All scene types](README.md)"
    lines += [f"{index} · `vidgen list-scenes` · `vidgen schema --scene {t.name}`", ""]
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


def write_showcase_page(showcase: Showcase, output: Path, formats: list[str], web: bool = False) -> Path:
    """Write ``<output>/<showcase>.md`` (``web``: ``<output>/web/<showcase>.md``): what it is for,
    the scene playing, its stills, the YAML; the scene types it shows linked in either gallery."""
    used = list(dict.fromkeys(scene["type"] for scene in showcase.config()["scenes"]))
    links = ", ".join(f"[`{name}`]({page_link(name, is_web_type(name), web)})" for name in used)
    output = gallery_folder(output, web)
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
    footer = SECTION_FOOTERS.get(showcase.section, DEFAULT_FOOTER)
    if web:
        lines += [f"[All web scenes](README.md) · [All scene types](../README.md) · {relink_for_web(footer)}", ""]
    else:
        lines += [f"[All scene types and showcases](README.md) · {footer}", ""]
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
    types: list[GalleryType], output: Path, formats: list[str], uses: dict[str, str],
    showcases: list[Showcase] | tuple[Showcase, ...] = (), web_showcases: frozenset[str] | set[str] = frozenset(), web: bool = False,
) -> Path:
    """Write ``<output>/README.md`` (``web``: the web gallery's, ``<output>/web/README.md``): its
    types by group with their previews, each group's showcases after its types (a showcase section
    that is no group after the groups). A type is in the web gallery when ``GalleryType.web``, a
    showcase when its name is in ``web_showcases``; the two indexes link to each other (the main
    one only when the web gallery has an entry) and the main one ends with the YouTube section."""
    folder = gallery_folder(output, web)
    web_types = [t.name for t in types if t.web]
    has_web = bool(web_types) or any(s.name in web_showcases for s in showcases)
    types = [t for t in types if t.web == web]
    showcases = [s for s in showcases if (s.name in web_showcases) == web]
    sections: dict[str, list[str]] = {}
    by_name = {t.name: t for t in types}
    for t in types:
        base = by_name.get(t.alias_of) if t.alias_of else t
        group = base.sample.group if base is not None and base.sample is not None else "other"
        sections.setdefault(group, []).append(_type_row(t, folder, formats, uses))
    type_groups = set(sections)
    for showcase in showcases:
        sections.setdefault(showcase.section, []).append(_showcase_row(showcase, folder, formats))
    with_showcases = {s.section for s in showcases}
    if web:
        lines = [
            "# Web scene gallery",
            "",
            "<!-- Generated by `vidgen gallery`; do not edit. -->",
            "",
            "The scene types drawn by a web page in headless Chromium (HTML, CSS, JavaScript, three.js), rendered",
            "from their samples in the author guide (`vidgen guide scenes`) like every other type in",
            "the [scene gallery](../README.md). The previews are animated: each GIF plays the scene at 16:9 and",
            "9:16 and holds its last beat (viewers who ask for reduced motion see that still instead).",
            "Each page has the YAML, the params, the action targets and the stills.",
            "Regenerate with `vidgen gallery`.",
            "",
        ]
        notes = WEB_SECTION_NOTES
    else:
        lines = [
            "# Scene gallery",
            "",
            "<!-- Generated by `vidgen gallery`; do not edit. -->",
            "",
            "Every schu-video-generator scene type, rendered from its sample in the author guide",
            "(`vidgen guide scenes`). The previews are animated: each GIF plays the scene at 16:9 and",
            "9:16 and holds its last beat (viewers who ask for reduced motion see that still instead).",
            "Each page has the YAML, the params, the action targets and the stills. The cell-biology and",
            "cartoon sections end with showcases, small scenes written for the gallery, each a whole `video.yaml`.",
            "Regenerate with `vidgen gallery`.",
            "",
        ]
        if has_web:
            shown = f" ({', '.join(f'`{n}`' for n in web_types)})" if web_types else ""
            lines += [
                f"The types drawn by a web page in headless Chromium{shown} and the films made of them have a gallery",
                f"of their own: the [web scene gallery]({WEB_FOLDER}/README.md).",
                "",
            ]
        notes = SECTION_NOTES
    for group, rows in sections.items():
        title = GROUP_TITLES.get(group, group)
        lines += [f"## {title[:1].upper()}{title[1:]}", ""]
        if group in notes:
            lines += [notes[group], ""]
        first = {(True, False): "type", (True, True): "type or showcase", (False, True): "showcase"}[(group in type_groups, group in with_showcases)]
        lines += [f"| {first} | preview | use it for |", "|---|---|---|", *rows, ""]
    if not web:
        lines += youtube_lines()
    path = folder / "README.md"
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
    web_showcases: frozenset[str] = frozenset()
    if project is not None:
        with extensions.project_session(project):
            types = gallery_types(project)
            names = rendered_names(types, only)
    else:
        with registry.isolated():
            extensions.load_builtins()
            types = gallery_types(None)
            names = rendered_names(types, only)
            web_showcases = frozenset(s.name for s in SHOWCASES if is_web_showcase(s))
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
    result = GalleryResult(output, output / "README.md", work, list(formats), types,
                           [GalleryShowcase(s, s.name in web_showcases) for s in showcases])
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
                _remove_other_copy(t.name, output, t.web)
        for entry in result.showcases:
            entry.page = write_showcase_page(entry.showcase, output, list(FORMATS), entry.web)
            _remove_other_copy(entry.name, output, entry.web)
        listed = SHOWCASES if project is None else ()
        write_index(types, output, list(FORMATS), uses, listed, web_showcases)
        if any(t.web for t in types) or web_showcases:
            result.web_index = write_index(types, output, list(FORMATS), uses, listed, web_showcases, web=True)
    return result


def _remove_other_copy(name: str, output: Path, web: bool) -> None:
    """Remove entry ``name``'s page and media from the gallery it is not in (an entry written
    there before it moved), so it is in one gallery only."""
    other = gallery_folder(output, not web)
    for path in [other / f"{name}.md", *(other / "media" / media_name(name, f, x) for f in FORMATS for x in (".png", ".gif"))]:
        remove_file(path)
