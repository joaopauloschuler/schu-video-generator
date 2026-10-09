"""Generated images: the provider seam of ``generate:`` params and ``vidgen imagegen`` (DESIGN.md §58).

- :class:`GenerateImage` is the ``generate:`` param (prompt, negative, style, aspect, seed) a
  scene type uses in place of an image ``path`` (the built-in ``image`` scene does).
- :func:`image_request` resolves it against the project's ``imagegen:`` section into an
  :class:`ImageRequest`: the prompt sent (style and negative added), provider, model, size,
  quality, seed and the cache key, a hash of all of them. The picture is stored as
  ``assets/generated/<key>.png`` with a sidecar ``<key>.json`` (prompt, provider, model, date,
  revised prompt); both are meant to be committed, like narration audio (they cost money).
  ``format: svg`` asks for a vector picture, stored as ``<key>.svg`` (OpenRouter's SVG models;
  drawn as shapes by :mod:`vidgen.vector_mobject`, DESIGN.md §65).
- Rendering and validating never call a provider: :func:`generated_image` gives the stored
  picture, or a placeholder card showing the prompt (:mod:`vidgen.imagegen.placeholder`) when
  ``vidgen imagegen`` has not made it yet.
- :func:`get_image_provider` returns the provider: OpenAI Images (:mod:`vidgen.imagegen.openai`,
  the default) or OpenRouter (:mod:`vidgen.imagegen.openrouter`).

No manim import.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vidgen.errors import VidgenError

if TYPE_CHECKING:
    from vidgen.project import Project
    from vidgen.theme import Theme

#: Providers ``imagegen.provider`` accepts.
IMAGEGEN_PROVIDERS: tuple[str, ...] = ("openai", "openrouter")
#: Where generated pictures are stored, relative to the project.
GENERATED_DIR = Path("assets") / "generated"
#: Version of the cache key's inputs (bumped if they change: every picture would be "missing").
KEY_VERSION = 1

#: ``style:`` presets: a name stands for these words added to the prompt.
STYLE_PRESETS: dict[str, str] = {
    "photo": "photorealistic photograph, natural light, sharp focus",
    "illustration": "clean digital illustration, soft shading, limited colour palette",
    "flat": "flat vector illustration, simple geometric shapes, solid colours, no outlines",
    "isometric": "isometric 3D illustration, clean edges, soft shadows, plain background",
    "watercolor": "watercolour painting, soft washes, visible paper texture",
    "line_art": "minimal line art, thin even strokes, mostly empty background",
    "render_3d": "3D render, soft studio lighting, smooth materials, plain background",
    "cinematic": "cinematic film still, dramatic lighting, wide angle, subtle film grain",
}
#: A ``style:`` value meaning "no style words" (also drops the project's ``imagegen.style``).
NO_STYLE = "none"

Aspect = Literal["landscape", "portrait", "square"]
#: Sizes per model family and aspect (what the OpenAI Images API accepts).
MODEL_SIZES: dict[str, dict[str, str]] = {
    "gpt-image": {"landscape": "1536x1024", "portrait": "1024x1536", "square": "1024x1024"},
    "dall-e-3": {"landscape": "1792x1024", "portrait": "1024x1792", "square": "1024x1024"},
    "dall-e-2": {"landscape": "1024x1024", "portrait": "1024x1024", "square": "1024x1024"},
}
#: Quality sent when ``imagegen.quality`` is not set, per model family.
DEFAULT_QUALITY: dict[str, str | None] = {"gpt-image": "medium", "dall-e-3": "standard", "dall-e-2": None}
#: Price in US dollars of one picture by (model, quality, square or not), from OpenAI's price
#: list when this was written (2025); an estimate for ``--dry-run`` only.
PRICES: dict[tuple[str, str | None, bool], float] = {
    ("gpt-image-1", "low", True): 0.011, ("gpt-image-1", "low", False): 0.016,
    ("gpt-image-1", "medium", True): 0.042, ("gpt-image-1", "medium", False): 0.063,
    ("gpt-image-1", "high", True): 0.167, ("gpt-image-1", "high", False): 0.25,
    ("dall-e-3", "standard", True): 0.04, ("dall-e-3", "standard", False): 0.08,
    ("dall-e-3", "hd", True): 0.08, ("dall-e-3", "hd", False): 0.12,
    ("dall-e-2", None, True): 0.02,
}
#: Aspect ratios OpenRouter's image API accepts (``aspect_ratio``; a provider clamps to the ones
#: its model has). ``auto`` sizes send the one nearest the video's format.
OPENROUTER_ASPECTS: tuple[str, ...] = (
    "1:1", "1:2", "1:4", "1:8", "2:1", "2:3", "2.35:1", "3:2", "3:4", "4:1", "4:3", "4:5", "5:2", "5:4",
    "5:7", "7:5", "8:1", "9:16", "16:9", "9:19.5", "19.5:9", "9:20", "20:9", "9:21", "21:9",
)
#: Long side in pixels of each OpenRouter ``resolution`` tier (nominal: the provider decides the
#: exact pixels); without a tier, 1K (what most models make by default).
RESOLUTION_PIXELS: dict[str, int] = {"512": 512, "768": 768, "1K": 1024, "1.5K": 1536, "2K": 2048, "4K": 4096}
#: OpenRouter image models that turn a text prompt into an SVG, with their price per picture in
#: US dollars, from OpenRouter's public model list of 2026-10-08 (all Recraft, none with a Zero
#: Data Retention endpoint). Only for hints: `vidgen imagegen --dry-run` reads the live records.
SVG_MODELS: dict[str, float] = {
    "recraft/recraft-v4.1-vector": 0.08,
    "recraft/recraft-v4-vector": 0.08,
    "recraft/recraft-v4.1-pro-vector": 0.30,
    "recraft/recraft-v4-pro-vector": 0.30,
}
SVG_MODELS_DATE = "2026-10-08"


def svg_models_hint() -> str:
    """``recraft/recraft-v4.1-vector ($0.08), ...`` (the snapshot :data:`SVG_MODELS`)."""
    return ", ".join(f"{m} (${p:.2f})" for m, p in SVG_MODELS.items())


class GenerateImage(BaseModel):
    """``generate:``: a picture made by the image-generation provider (``vidgen imagegen``) in
    place of a file. A plain string is the prompt."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
    #: Other input types this model is built from (shown by ``vidgen list-scenes``).
    also_accepts: ClassVar[tuple[type, ...]] = (str,)

    prompt: str = Field(min_length=1)
    """What the picture shows, e.g. "a lighthouse on a cliff at dawn" (keep words out of it: generators draw text poorly)."""
    negative: str = ""
    """What the picture should not show (added to the prompt as "Avoid: ..."), e.g. "people, text"."""
    style: str | None = None
    """Style words added to the prompt: a preset (photo, illustration, flat, isometric, watercolor, line_art, render_3d, cinematic), your own words, or none; default imagegen.style."""
    aspect: Literal["auto", "landscape", "portrait", "square"] = "auto"
    """Shape of the picture: auto (the video's: landscape for 16:9, portrait for 9:16, square), landscape, portrait or square."""
    seed: int | None = Field(default=None, ge=0)
    """Another number asks for another picture of the same prompt (part of the cache key; OpenAI takes no seed, so it does not make a picture reproducible)."""
    format: Literal["png", "svg"] = "png"
    """png: a raster picture; svg: a vector picture drawn as shapes (provider openrouter with an SVG model, e.g. imagegen.svg_model: recraft/recraft-v4.1-vector; good for flat illustrations, not photos)."""

    @model_validator(mode="before")
    @classmethod
    def _prompt_only(cls, data: Any) -> Any:
        return {"prompt": data} if isinstance(data, str) else data


@dataclass(frozen=True)
class ImageRequest:
    """One picture to generate: what is sent (``text`` = prompt + style + negative, ``size``,
    ``quality``) and where it is stored (``path``, ``sidecar``), keyed by ``key``.

    OpenRouter requests (§64) also carry ``aspect_ratio`` and ``resolution``: with
    ``explicit_size`` false they are sent instead of ``size``, which is then only the nominal
    pixel size (placeholder shape, per-megapixel price estimate)."""

    provider: str
    model: str
    size: str
    quality: str | None
    seed: int | None
    prompt: str
    negative: str
    style: str
    text: str
    key: str
    path: Path
    sidecar: Path
    aspect_ratio: str | None = None
    resolution: str | None = None
    explicit_size: bool = True
    #: ``png`` (raster, stored as PNG) or ``svg`` (vector, stored as SVG; §65).
    format: str = "png"

    @property
    def exists(self) -> bool:
        """Whether the picture has been generated (its PNG / SVG is stored)."""
        return self.path.is_file()

    @property
    def pixels(self) -> tuple[int, int]:
        """``size`` as ``(width, height)``."""
        w, h = self.size.split("x")
        return int(w), int(h)

    @property
    def shape(self) -> str:
        """What sets the picture's size, for messages: ``1536x1024``, ``16:9, 2K`` or ``16:9, SVG``."""
        if self.explicit_size:
            return self.size
        return ", ".join(p for p in (self.aspect_ratio, self.resolution, "SVG" if self.format == "svg" else None) if p)

    @property
    def estimated_cost(self) -> float | None:
        """US dollars one generation costs by OpenAI's :data:`PRICES`, ``None`` if unknown (always
        for other providers: their prices are looked up by ``vidgen imagegen --dry-run``)."""
        if self.provider != "openai":
            return None
        w, h = self.pixels
        return PRICES.get((self.model, self.quality, w == h))


@dataclass(frozen=True)
class SceneImage:
    """A ``generate:`` of a scene: the scene, its index, the param holding it and its request."""

    scene_id: str
    index: int
    field: str
    generate: GenerateImage
    request: ImageRequest
    #: The scene's validated params (``simplify`` of a vector picture is read from them).
    params: Any = None

    @property
    def location(self) -> str:
        """``scenes[i].params.<field>`` (config path, for messages)."""
        return f"scenes[{self.index}].params.{self.field}"


@dataclass(frozen=True)
class GeneratedPicture:
    """What a provider returns: PNG bytes, the prompt it actually used and what it charged in
    US dollars, if it says."""

    data: bytes
    revised_prompt: str | None = None
    cost: float | None = None


@dataclass(frozen=True)
class PriceQuote:
    """The estimated price of one picture in US dollars (``None``: unknown) and what it is
    based on (``basis``, shown with the estimate)."""

    cost: float | None
    basis: str


class ImageProvider(Protocol):
    """What ``vidgen imagegen`` needs from an image-generation provider. Constructing one needs
    no key. A provider may also have ``check_requests(requests)``: called once before the first
    paid request, it raises ``VidgenError`` for options the model does not take."""

    name: str

    def check_credentials(self) -> None:
        """Raise ``VidgenError`` (saying how to set it) if the API key is missing."""

    def generate(self, request: ImageRequest) -> GeneratedPicture:
        """Make the picture of ``request``. Raises ``VidgenError``."""


# ----- resolving a request ----------------------------------------------------------------------


def model_family(model: str) -> str:
    """``dall-e-3``, ``dall-e-2`` or ``gpt-image`` (any other model name)."""
    for family in ("dall-e-3", "dall-e-2"):
        if model.startswith(family):
            return family
    return "gpt-image"


def video_aspect(project: Project) -> Aspect:
    """The final format's shape: ``landscape``, ``portrait`` or ``square``."""
    fmt = project.config.format
    return "landscape" if fmt.width > fmt.height else "portrait" if fmt.width < fmt.height else "square"


def style_words(value: str | None) -> str:
    """The words a ``style`` value adds: a preset's, the value itself, or nothing (``none``)."""
    if value is None or value.strip().lower() == NO_STYLE:
        return ""
    return STYLE_PRESETS.get(value.strip(), value.strip())


def _sentence(text: str) -> str:
    text = " ".join(text.split())
    return text if not text or text[-1] in ".!?" else text + "."


def compose_prompt(prompt: str, style: str = "", negative: str = "") -> str:
    """The prompt sent: ``prompt`` as a sentence, then ``Style: ...`` and ``Avoid: ...``."""
    parts = [_sentence(prompt)]
    if style:
        parts.append(_sentence(f"Style: {style.rstrip('.')}"))
    if negative:
        parts.append(_sentence(f"Avoid: {negative.rstrip('.')}"))
    return " ".join(parts)


def request_key(
    provider: str, model: str, size: str, quality: str | None, seed: int | None, text: str, extra: dict[str, Any] | None = None
) -> str:
    """16 hex digits of sha1 over everything that changes the picture. ``extra`` holds a
    provider's own inputs (OpenRouter: aspect ratio, resolution); without it the key is the one
    OpenAI pictures have always had."""
    data = {"v": KEY_VERSION, "provider": provider, "model": model, "size": size, "quality": quality, "seed": seed, "prompt": text}
    data.update(extra or {})
    return hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:16]


def _ratio(value: str) -> float:
    a, b = value.split(":")
    return float(a) / float(b)


def openrouter_aspect(project: Project, aspect: str) -> str:
    """The ``aspect_ratio`` sent to OpenRouter: the listed ratio nearest the video's format when
    the picture has the video's shape (``auto``), else 16:9, 9:16 or 1:1."""
    if aspect == "auto" or aspect == video_aspect(project):
        fmt = project.config.format
        target = fmt.width / fmt.height
        shape = video_aspect(project)
        same = [r for r in OPENROUTER_ASPECTS if (_ratio(r) > 1, _ratio(r) < 1) == (shape == "landscape", shape == "portrait")]
        return min(same, key=lambda r: abs(_ratio(r) - target))
    return {"landscape": "16:9", "portrait": "9:16"}.get(aspect, "1:1")


def nominal_size(aspect_ratio: str, resolution: str | None) -> str:
    """``WxH`` of ``aspect_ratio`` at the long side of ``resolution`` (1K without one)."""
    long_side = RESOLUTION_PIXELS[resolution or "1K"]
    r = _ratio(aspect_ratio)
    w, h = (long_side, round(long_side / r)) if r >= 1 else (round(long_side * r), long_side)
    return f"{w}x{h}"


def image_request(project: Project, generate: GenerateImage) -> ImageRequest:
    """``generate`` resolved with the project's ``imagegen:`` settings."""
    cfg = project.config.imagegen
    style = style_words(generate.style if generate.style is not None else cfg.style)
    negatives = [n.strip() for n in (generate.negative, cfg.negative or "") if n and n.strip()]
    negative = "; ".join(dict.fromkeys(negatives))
    text = compose_prompt(generate.prompt, style, negative)
    extra: dict[str, Any] | None = None
    aspect_ratio: str | None = None
    explicit = cfg.size != "auto"
    model, resolution = cfg.model, cfg.resolution
    if generate.format == "svg":  # vectors: the SVG model, an aspect ratio, no quality / resolution (§65)
        model = cfg.svg_model or cfg.model
        quality, resolution, explicit = None, None, False
        aspect_ratio = openrouter_aspect(project, generate.aspect)
        size = nominal_size(aspect_ratio, None)
        extra = {"aspect_ratio": aspect_ratio, "resolution": None, "format": "svg"}
    elif cfg.provider == "openrouter":
        quality = cfg.quality
        aspect_ratio = None if explicit else openrouter_aspect(project, generate.aspect)
        size = cfg.size if explicit else nominal_size(aspect_ratio or "1:1", cfg.resolution)
        extra = {"aspect_ratio": aspect_ratio, "resolution": cfg.resolution}
    else:
        family = model_family(cfg.model)
        if explicit:
            size = cfg.size
        else:
            aspect = video_aspect(project) if generate.aspect == "auto" else generate.aspect
            size = MODEL_SIZES[family][aspect]
        quality = cfg.quality if cfg.quality is not None else DEFAULT_QUALITY[family]
    key = request_key(cfg.provider, model, size, quality, generate.seed, text, extra)
    folder = project.root / GENERATED_DIR
    return ImageRequest(
        provider=cfg.provider, model=model, size=size, quality=quality, seed=generate.seed,
        prompt=" ".join(generate.prompt.split()), negative=negative, style=style, text=text, key=key,
        path=folder / f"{key}.{generate.format}", sidecar=folder / f"{key}.json",
        aspect_ratio=aspect_ratio, resolution=resolution,
        explicit_size=explicit or (cfg.provider != "openrouter" and generate.format != "svg"), format=generate.format,
    )


def generated_image(project: Project, generate: GenerateImage, theme: Theme | None = None) -> Path:
    """The picture of ``generate``: ``assets/generated/<key>.png`` (``.svg`` for ``format: svg``)
    once ``vidgen imagegen`` made it, else a placeholder card (PNG) in the theme's colours showing
    the prompt (``build/imagegen/``; never calls the provider)."""
    request = image_request(project, generate)
    if request.exists:
        return request.path
    from vidgen.imagegen.placeholder import placeholder_path

    if theme is None:
        from vidgen.runtime import current_theme

        theme = current_theme()
    return placeholder_path(project, request, theme)


# ----- the project's requests ----------------------------------------------------------------------


def find_images(project: Project) -> list[SceneImage]:
    """Every ``generate:`` (a top-level param of type :class:`GenerateImage`) of the project's
    scenes, in order. Needs the registry of a project session; scenes whose type is unknown or
    whose params do not validate are skipped (``vidgen validate`` reports them)."""
    from vidgen import registry

    found: list[SceneImage] = []
    for i, spec in enumerate(project.config.scenes):
        entry = registry.find(spec.type)
        if entry is None:
            continue
        try:
            params = entry.cls.validate_params(spec.params)
        except Exception:  # invalid params are reported by `vidgen validate`
            continue
        if not isinstance(params, BaseModel):  # a scene type without a Params model
            continue
        for name in type(params).model_fields:
            value = getattr(params, name)
            if isinstance(value, GenerateImage):
                found.append(SceneImage(spec.id, i, name, value, image_request(project, value), params))
    return found


def scene_images(project: Project) -> list[SceneImage]:
    """:func:`find_images` inside the project's own extension session."""
    from vidgen import extensions

    with extensions.project_session(project):
        return find_images(project)


def orphaned_images(project: Project, used: set[str]) -> list[Path]:
    """PNGs and SVGs in ``assets/generated/`` whose key is not in ``used`` (sorted); reported,
    never deleted."""
    folder = project.root / GENERATED_DIR
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix in (".png", ".svg") and p.is_file() and p.stem not in used)


# ----- warnings ----------------------------------------------------------------------------------

_QUOTED = re.compile(r"[\"“”«»]([^\"“”«»]{1,80})[\"“”«»]")
_TEXT_WORDS = re.compile(
    r"\b(text|words?|letters?|lettering|typography|captions?|labels?|label(?:l)?ed|titled?|headlines?|logos?|slogans?|"
    r"says|saying|written|spelled|spelling|fonts?)\b",
    re.IGNORECASE,
)
_CHART_WORDS = re.compile(r"\b(charts?|graphs?|diagrams?|infographics?|tables?|plots?)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(no|without|not|zero|avoid)\s+(?:\w+\s+)?$", re.IGNORECASE)


def _unnegated(pattern: re.Pattern[str], text: str) -> str | None:
    for match in pattern.finditer(text):
        if not _NEGATION.search(text[: match.start()]):
            return match.group(0)
    return None


def text_in_prompt(prompt: str) -> str | None:
    """Why ``prompt`` seems to ask for written words or a chart in the picture (generators draw
    them poorly), or ``None``."""
    quoted = _QUOTED.search(prompt)
    if quoted:
        return f'it quotes text ("{quoted.group(1)}")'
    word = _unnegated(_TEXT_WORDS, prompt)
    if word:
        return f"it mentions {word!r}"
    word = _unnegated(_CHART_WORDS, prompt)
    if word:
        return f"it asks for a {word.lower().rstrip('s')} (made-up labels and numbers)"
    return None


def imagegen_warnings(project: Project, images: list[SceneImage] | None = None) -> list[str]:
    """``vidgen validate`` warnings: pictures not generated yet (a placeholder is shown) and
    prompts asking for words in the picture (none when the project's extensions do not load:
    that is a problem, reported elsewhere)."""
    if images is None:
        try:
            images = scene_images(project)
        except VidgenError:
            return []
    out: list[str] = []
    for image in images:
        reason = text_in_prompt(image.generate.prompt)
        if reason is not None:
            out.append(
                f"{image.location}.prompt: {reason}; image generators render text poorly - put words on screen "
                "with vidgen (a caption, title or callout) and charts with its chart scenes"
            )
    out += vector_warnings(images)
    missing = [i for i in images if not i.request.exists]
    if missing:
        names = ", ".join(f"{i.scene_id} ({i.request.path.name})" for i in missing[:6]) + (f" (+{len(missing) - 6} more)" if len(missing) > 6 else "")
        out.append(f"generated images not made yet for {names}: placeholders are shown; run `vidgen imagegen`")
    return out


def imagegen_problems(project: Project) -> list[tuple[str, str]]:
    """Config errors of the project's ``generate:`` params as ``(location, message)`` for
    ``vidgen validate`` (inside the project's session): ``format: svg`` needs the
    ``openrouter`` provider (OpenAI makes no SVG pictures)."""
    provider = project.config.imagegen.provider
    if provider == "openrouter":
        return []
    return [
        (
            f"{image.location}.format",
            f"svg needs imagegen.provider: openrouter and an SVG model, e.g. svg_model: recraft/recraft-v4.1-vector "
            f"({provider} makes no SVG pictures)",
        )
        for image in find_images(project)
        if image.generate.format == "svg"
    ]


def vector_warnings(images: list[SceneImage]) -> list[str]:
    """Warnings about vector pictures: a ``format: svg`` model not known to make SVG (or an
    SVG-only model asked for PNG), and what loading a stored SVG will remove or cut (§65)."""
    out: list[str] = []
    seen: set[tuple[str, str]] = set()
    for image in images:
        request = image.request
        if request.provider != "openrouter":
            continue
        if request.format == "svg" and request.model not in SVG_MODELS and "vector" not in request.model:
            out.append(
                f"{image.location}.format: svg with {request.model}, which is not known to make SVG pictures "
                f"(OpenRouter's SVG models on {SVG_MODELS_DATE}: {svg_models_hint()}); set imagegen.svg_model "
                "(`vidgen imagegen --dry-run` checks the model)"
            )
        elif request.format == "png" and request.model in SVG_MODELS:
            out.append(
                f"{image.location}: {request.model} makes only SVG pictures: add format: svg to the generate:, or set "
                "imagegen.model to a raster model and imagegen.svg_model to this one"
            )
        if request.format == "svg" and request.exists:
            from vidgen.svgclean import sanitize_svg

            simplify = getattr(image.params, "simplify", False)
            if (request.key, repr(simplify)) in seen:
                continue
            seen.add((request.key, repr(simplify)))
            try:
                report = sanitize_svg(request.path.read_bytes(), where=f"{image.scene_id} ({request.path.name})", simplify=simplify)
            except (VidgenError, OSError) as exc:
                out.append(f"{image.location}: the stored SVG cannot be shown: {exc}")
                continue
            out += list(report.warnings)
    return out


def images_summary(images: list[SceneImage]) -> str:
    """``"3 generated, 1 missing"`` (pictures, each distinct request once)."""
    by_key = {i.request.key: i.request for i in images}
    made = sum(1 for r in by_key.values() if r.exists)
    return f"{made} generated, {len(by_key) - made} missing"


# ----- the provider ------------------------------------------------------------------------------


def get_image_provider(project: Project) -> ImageProvider:
    """The provider of the project's ``imagegen:`` section."""
    cfg = project.config.imagegen
    if cfg.provider == "openai":
        from vidgen.imagegen.openai import OpenAIImageProvider

        return OpenAIImageProvider()
    if cfg.provider == "openrouter":
        from vidgen.imagegen.openrouter import OpenRouterImageProvider

        return OpenRouterImageProvider()
    raise VidgenError(f"unknown imagegen provider {cfg.provider!r}; available: {', '.join(IMAGEGEN_PROVIDERS)}")


__all__ = [
    "GENERATED_DIR",
    "IMAGEGEN_PROVIDERS",
    "OPENROUTER_ASPECTS",
    "STYLE_PRESETS",
    "SVG_MODELS",
    "GenerateImage",
    "GeneratedPicture",
    "ImageProvider",
    "ImageRequest",
    "PriceQuote",
    "SceneImage",
    "compose_prompt",
    "find_images",
    "generated_image",
    "get_image_provider",
    "image_request",
    "imagegen_problems",
    "imagegen_warnings",
    "images_summary",
    "nominal_size",
    "openrouter_aspect",
    "orphaned_images",
    "request_key",
    "scene_images",
    "style_words",
    "svg_models_hint",
    "text_in_prompt",
    "vector_warnings",
]
