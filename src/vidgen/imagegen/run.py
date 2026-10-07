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

from vidgen.errors import VidgenError
from vidgen.fileio import write_bytes_atomic, write_text_atomic
from vidgen.imagegen import GENERATED_DIR, ImageProvider, ImageRequest, SceneImage, get_image_provider, orphaned_images, scene_images
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

    @property
    def cost(self) -> tuple[float, int]:
        """Estimated US dollars of ``todo`` and how many requests have no known price."""
        prices = [r.estimated_cost for r in self.todo]
        return sum(p for p in prices if p is not None), sum(1 for p in prices if p is None)


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


def _describe(request: ImageRequest) -> str:
    quality = f" {request.quality}" if request.quality else ""
    cost = request.estimated_cost
    return f"{request.size}, {request.model}{quality}" + (f", ~{_money(cost)}" if cost is not None else ", cost unknown")


def sidecar_document(request: ImageRequest, revised_prompt: str | None, scenes: list[str]) -> dict[str, object]:
    """The ``<key>.json`` next to a generated picture: how it was made."""
    return {
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


def run_imagegen(
    project: Project,
    *,
    scene_ids: Sequence[str] = (),
    force: bool = False,
    dry_run: bool = False,
    provider: ImageProvider | None = None,
    out: Callable[[str], None] = print,
) -> ImagegenPlan:
    """Generate the missing pictures of ``project`` (``force``: all selected ones again);
    ``dry_run`` only lists them with an estimated cost (no API key needed). ``provider``
    replaces the configured one (tests)."""
    plan = plan_imagegen(project, scene_ids, force)
    where = GENERATED_DIR.as_posix()
    if plan.orphans:
        out(f"pictures in {where}/ no scene uses (not deleted): {', '.join(p.name for p in plan.orphans)}")
    total, unknown = plan.cost
    estimate = f"estimated {_money(total)}" + (f" + {unknown} of unknown price" if unknown else "") + f" ({PRICE_NOTE})"
    if dry_run:
        for request in plan.todo:
            out(f"would generate {request.key}.png for {', '.join(plan.scenes[request.key])} ({_describe(request)})")
            out(f"    prompt: {request.text}")
        out(f"dry run: {len(plan.todo)} picture(s) to generate, {estimate}; {len(plan.up_to_date)} up to date")
        return plan
    if not plan.todo:
        out(f"nothing to do: {len(plan.up_to_date)} picture(s) up to date in {where}/")
        return plan

    provider = get_image_provider(project) if provider is None else provider
    provider.check_credentials()  # fail before the first request if the key is missing
    for n, request in enumerate(plan.todo, start=1):
        scenes = plan.scenes[request.key]
        started = time.monotonic()
        try:
            picture = provider.generate(request)
            write_bytes_atomic(request.path, picture.data)
            doc = sidecar_document(request, picture.revised_prompt, scenes)
            write_text_atomic(request.sidecar, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        except (VidgenError, OSError) as exc:
            done = f"{n - 1} of {len(plan.todo)} done before the error; run again to continue"
            raise VidgenError(f"picture for scene '{scenes[0]}': {exc}\n({done})") from None
        out(f"[{n}/{len(plan.todo)}] generated {request.key}.png for {', '.join(scenes)} ({time.monotonic() - started:.1f} s)")
    out(f"done: {len(plan.todo)} picture(s) generated ({estimate}), {len(plan.up_to_date)} up to date, in {where}/")
    return plan
