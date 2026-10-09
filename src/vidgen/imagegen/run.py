"""``vidgen imagegen``: generate the pictures of ``generate:`` params that are missing (DESIGN.md §58).

Each distinct request (same prompt, style, size, model...) is generated once and stored as
``assets/generated/<key>.png`` + ``<key>.json``; pictures that exist are skipped unless ``force``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic, write_text_atomic
from vidgen.imagegen import (
    GENERATED_DIR,
    ImageProvider,
    ImageRequest,
    PriceQuote,
    SceneImage,
    get_image_provider,
    orphaned_images,
    scene_images,
)
from vidgen.project import Project

#: Where the prices in :data:`vidgen.imagegen.PRICES` come from (shown with estimates).
PRICE_NOTE = "OpenAI list prices of 2025; check current pricing"


@dataclass
class ImagegenPlan:
    """What ``vidgen imagegen`` will do: ``todo`` (distinct requests to generate, in video
    order), ``scenes`` (key -> the scenes using it), ``up_to_date`` (keys already stored) and
    ``orphans`` (stored pictures no config of the project uses; never deleted)."""

    todo: list[ImageRequest] = field(default_factory=list)
    scenes: dict[str, list[str]] = field(default_factory=dict)
    up_to_date: list[str] = field(default_factory=list)
    orphans: list[Path] = field(default_factory=list)
    #: Prices looked up by :func:`price_plan` (key -> quote); else OpenAI's :data:`PRICES`.
    quotes: dict[str, PriceQuote] = field(default_factory=dict)
    #: Per key: options the model ignores or changes (OpenRouter), and what a real run refuses.
    notes: dict[str, list[str]] = field(default_factory=dict)
    problems: dict[str, list[str]] = field(default_factory=dict)
    #: What the prices are based on (shown with the total).
    price_notes: list[str] = field(default_factory=list)
    #: US dollars the provider reported charging in a real run (``None``: it did not say).
    charged: float | None = None

    def quote(self, request: ImageRequest) -> PriceQuote:
        """The price of ``request``: looked up, or OpenAI's list price."""
        if request.key in self.quotes:
            return self.quotes[request.key]
        cost = request.estimated_cost
        return PriceQuote(cost, PRICE_NOTE if cost is not None else f"no list price for {request.model}")

    @property
    def cost(self) -> tuple[float, int]:
        """Estimated US dollars of ``todo`` and how many requests have no known price."""
        prices = [self.quote(r).cost for r in self.todo]
        return sum(p for p in prices if p is not None), sum(1 for p in prices if p is None)

    @property
    def price_note(self) -> str:
        """What the estimate is based on: OpenAI's 2025 list, OpenRouter's prices of today..."""
        return "; ".join(self.price_notes) if self.price_notes else PRICE_NOTE


def price_plan(plan: ImagegenPlan, *, lookup: Callable[[list[str]], dict[str, Any]] | None = None) -> ImagegenPlan:
    """Fill ``plan``'s quotes, notes, problems and price notes. OpenRouter requests are priced
    from OpenRouter's public model records (a free lookup with a short timeout; offline: "price
    unknown"); OpenAI requests from :data:`PRICES`. ``lookup`` replaces the OpenRouter lookup."""
    from vidgen.imagegen import openrouter

    routed = [r for r in plan.todo if r.provider == "openrouter"]
    notes: list[str] = []
    if any(r.provider == "openai" for r in plan.todo):
        notes.append(PRICE_NOTE)
    if routed:
        found = (lookup or openrouter.lookup_models)(list(dict.fromkeys(r.model for r in routed)))
        for request in routed:
            result = found[request.model]
            plan.quotes[request.key] = openrouter.quote(request, result)
            if isinstance(result, openrouter.ModelInfo):
                check = openrouter.check_request(request, result)
                plan.notes[request.key], plan.problems[request.key] = check.notes, check.problems
            elif result.missing:
                plan.problems[request.key] = [result.reason]
        reached = any(isinstance(v, openrouter.ModelInfo) or v.missing for v in found.values())
        today = datetime.now(timezone.utc).date().isoformat()
        notes.append(f"OpenRouter prices of {today}" if reached else "OpenRouter prices unknown (its model list could not be reached)")
    plan.price_notes = notes
    return plan


def used_keys(project: Project) -> set[str]:
    """Keys of the pictures the base config and every variant use (variants that do not load
    are skipped: `vidgen validate` reports them)."""
    base = project if project.variant is None else Project.load(project.config_file)
    keys = {i.request.key for i in scene_images(base)}
    for name in base.config.variants:
        try:
            variant = Project.load(project.config_file, variant=name)
        except VidgenError:
            continue
        keys |= {i.request.key for i in scene_images(variant)}
    return keys


def plan_imagegen(project: Project, scene_ids: Sequence[str] = (), force: bool = False, images: list[SceneImage] | None = None) -> ImagegenPlan:
    """Decide which pictures to generate. ``scene_ids`` restricts it to those scenes (an unknown
    id or a scene without ``generate:`` is an error)."""
    images = scene_images(project) if images is None else images
    known = [s.id for s in project.config.scenes]
    unknown = [s for s in scene_ids if s not in known]
    if unknown:
        raise VidgenError(f"unknown scene(s): {', '.join(unknown)}; scenes: {', '.join(known)}")
    with_images = list(dict.fromkeys(i.scene_id for i in images))
    without = [s for s in scene_ids if s not in with_images]
    if without:
        raise VidgenError(f"scene(s) without a generate: param: {', '.join(without)}; scenes with one: {', '.join(with_images) or 'none'}")
    plan = ImagegenPlan()
    seen: set[str] = set()
    for image in images:
        if scene_ids and image.scene_id not in scene_ids:
            continue
        request = image.request
        plan.scenes.setdefault(request.key, []).append(image.scene_id)
        if request.key in seen:
            continue
        seen.add(request.key)
        if request.exists and not force:
            plan.up_to_date.append(request.key)
        else:
            plan.todo.append(request)
    plan.orphans = orphaned_images(project, used_keys(project))
    return plan


def _money(value: float) -> str:
    return f"${value:.2f}" if value >= 0.1 or value == 0 else f"${value:.3f}"


def _describe(request: ImageRequest, quote: PriceQuote) -> str:
    quality = f" {request.quality}" if request.quality else ""
    if request.provider == "openai":
        cost = quote.cost
        return f"{request.size}, {request.model}{quality}" + (f", ~{_money(cost)}" if cost is not None else ", cost unknown")
    price = f"~{_money(quote.cost)}" if quote.cost is not None else "price unknown"
    return f"{request.shape}, {request.provider} {request.model}{quality}, {price}"


def sidecar_document(
    request: ImageRequest, revised_prompt: str | None, scenes: list[str], cost: float | None = None
) -> dict[str, object]:
    """The ``<key>.json`` next to a generated picture: how it was made (OpenRouter pictures also
    record the aspect ratio and resolution asked for and the cost the provider reported)."""
    doc: dict[str, object] = {
        "vidgen_imagegen": 1,
        "key": request.key,
        "prompt": request.prompt,
        "negative": request.negative or None,
        "style": request.style or None,
        "sent_prompt": request.text,
        "revised_prompt": revised_prompt,
        "provider": request.provider,
        "model": request.model,
        "size": request.size,
        "quality": request.quality,
        "seed": request.seed,
        "created": datetime.now(timezone.utc).date().isoformat(),
        "scenes": scenes,
    }
    if request.provider != "openai":
        doc["size"] = request.size if request.explicit_size else None
        doc["aspect_ratio"] = request.aspect_ratio
        doc["resolution"] = request.resolution
    if cost is not None:
        doc["cost_usd"] = cost
    return doc


def run_imagegen(
    project: Project,
    *,
    scene_ids: Sequence[str] = (),
    force: bool = False,
    dry_run: bool = False,
    provider: ImageProvider | None = None,
    out: Callable[[str], None] = print,
    lookup: Callable[[list[str]], dict[str, Any]] | None = None,
) -> ImagegenPlan:
    """Generate the missing pictures of ``project`` (``force``: all selected ones again);
    ``dry_run`` only lists them with an estimated cost (no API key needed; OpenRouter prices are
    looked up online, see :func:`price_plan`). ``provider`` replaces the configured one (tests);
    ``lookup`` the OpenRouter price lookup (tests)."""
    plan = plan_imagegen(project, scene_ids, force)
    where = GENERATED_DIR.as_posix()
    if plan.orphans:
        out(f"pictures in {where}/ no scene uses (not deleted): {', '.join(p.name for p in plan.orphans)}")
    if dry_run:
        price_plan(plan, lookup=lookup)
        for request in plan.todo:
            quote = plan.quote(request)
            out(f"would generate {request.key}.png for {', '.join(plan.scenes[request.key])} ({_describe(request, quote)})")
            if request.provider != "openai":
                out(f"    price: {quote.basis}")
            for note in plan.notes.get(request.key, []):
                out(f"    note: {note}")
            for problem in plan.problems.get(request.key, []):
                out(f"    problem: {problem}")
            out(f"    prompt: {request.text}")
        refused = sum(1 for r in plan.todo if plan.problems.get(r.key))
        stop = f"; {refused} would be refused (see problem:)" if refused else ""
        out(f"dry run: {len(plan.todo)} picture(s) to generate, {_estimate(plan)}; {len(plan.up_to_date)} up to date{stop}")
        return plan
    if not plan.todo:
        out(f"nothing to do: {len(plan.up_to_date)} picture(s) up to date in {where}/")
        return plan

    provider = get_image_provider(project) if provider is None else provider
    provider.check_credentials()  # fail before the first request if the key is missing
    check_requests = getattr(provider, "check_requests", None)
    if callable(check_requests):
        check_requests(plan.todo)  # options the model does not take: refused before paying
    charged: list[float] = []
    for n, request in enumerate(plan.todo, start=1):
        scenes = plan.scenes[request.key]
        started = time.monotonic()
        try:
            picture = provider.generate(request)
            write_bytes_atomic(request.path, picture.data)
            doc = sidecar_document(request, picture.revised_prompt, scenes, picture.cost)
            write_text_atomic(request.sidecar, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        except (VidgenError, OSError) as exc:
            done = f"{n - 1} of {len(plan.todo)} done before the error; run again to continue"
            raise VidgenError(f"picture for scene '{scenes[0]}': {exc}\n({done})") from None
        if picture.cost is not None:
            charged.append(picture.cost)
        cost = f", {_money(picture.cost)}" if picture.cost is not None else ""
        out(f"[{n}/{len(plan.todo)}] generated {request.key}.png for {', '.join(scenes)} ({time.monotonic() - started:.1f} s{cost})")
    if charged:
        plan.charged = sum(charged)
        spent = f"{_money(plan.charged)} charged by {provider.name}" + (f" for {len(charged)} of them" if len(charged) < len(plan.todo) else "")
    elif any(r.provider != "openai" for r in plan.todo):
        spent = f"cost not reported by {provider.name}"
    else:
        spent = _estimate(plan)
    out(f"done: {len(plan.todo)} picture(s) generated ({spent}), {len(plan.up_to_date)} up to date, in {where}/")
    return plan


def _estimate(plan: ImagegenPlan) -> str:
    total, unknown = plan.cost
    return f"estimated {_money(total)}" + (f" + {unknown} of unknown price" if unknown else "") + f" ({plan.price_note})"
