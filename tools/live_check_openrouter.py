"""Live check of the OpenRouter image provider (Step 61) against the real API.

Not shipped with vidgen and never run by the tests; a maintainer tool for a person with an
OpenRouter key. It

1. fetches OpenRouter's public image-model list (free, no key) and prints the cheapest models
   that take a text prompt, with their prices as vidgen estimates them;
2. without ``--yes``: prints the dry run of one picture with the cheapest model and stops (free);
3. with ``--yes``: generates ONE small picture through vidgen's own code path
   (``vidgen.imagegen.run.run_imagegen`` with the ``openrouter`` provider) in a new temporary
   project folder, then prints where the PNG and its sidecar are and the cost OpenRouter reported.

The key is read only from the environment variable ``OPENROUTER_API_KEY`` (by vidgen, at the
moment of the request); this script never prints or stores it. Run from the repository root::

    python tools/live_check_openrouter.py            # free: model list + dry run
    python tools/live_check_openrouter.py --yes      # one paid picture (a few cents at most)
    python tools/live_check_openrouter.py --yes --model black-forest-labs/flux.2-klein-4b
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from vidgen import httpapi
from vidgen.errors import VidgenError
from vidgen.imagegen import GenerateImage, image_request
from vidgen.imagegen import openrouter as orr
from vidgen.imagegen.run import run_imagegen
from vidgen.project import Project

PROMPT = "a small red paper boat on calm blue water, seen from above"
#: Resolution tiers from the smallest (the first one a model lists is used).
TIERS = ("512", "768", "1K", "1.5K", "2K", "4K")


def image_models() -> list[dict[str, Any]]:
    """``GET /api/v1/images/models`` (public)."""
    headers = {"Accept": "application/json", **orr.APP_HEADERS}
    body = httpapi.get(f"{orr.API_BASE}/images/models", headers=headers, service="OpenRouter", timeout=20)
    return [m for m in json.loads(body.decode("utf-8"))["data"] if isinstance(m, dict)]


def text_to_image(model: dict[str, Any]) -> bool:
    """Takes a text prompt alone and makes raster pictures."""
    arch = model.get("architecture") or {}
    params = model.get("supported_parameters") or {}
    refs = params.get("input_references") or {}
    formats = (params.get("output_format") or {}).get("values") or []
    return "text" in (arch.get("input_modalities") or []) and not (refs.get("min") or 0) and formats != ["svg"]


def smallest_tier(info: orr.ModelInfo) -> str | None:
    """The model's smallest listed resolution tier, if it lists any."""
    listed = info.values("resolution") or []
    return next((t for t in TIERS if t in listed), None)


def write_project(folder: Path, model: str, resolution: str | None) -> Project:
    """A one-scene project asking for one picture with ``model``."""
    imagegen: dict[str, Any] = {"provider": "openrouter", "model": model}
    if resolution is not None:
        imagegen["resolution"] = resolution
    config = {
        "title": "OpenRouter live check",
        "imagegen": imagegen,
        "scenes": [{"id": "pic", "type": "image", "params": {"generate": {"prompt": PROMPT, "aspect": "square"}}, "beats": [{"text": "A picture."}]}],
    }
    (folder / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return Project.load(folder)


def price_at_smallest(model: str, tmp: Path) -> tuple[float | None, str, str | None, orr.Lookup]:
    """vidgen's estimate of one square picture at the model's smallest tier."""
    lookup = orr.fetch_model_info(model, timeout=10)
    tier = smallest_tier(lookup) if isinstance(lookup, orr.ModelInfo) else None
    folder = tmp / model.replace("/", "__")
    folder.mkdir(parents=True, exist_ok=True)
    request = image_request(write_project(folder, model, tier), GenerateImage(prompt=PROMPT, aspect="square"))
    quote = orr.quote(request, lookup)
    return quote.cost, quote.basis, tier, lookup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="really generate one picture (costs money)")
    parser.add_argument("--model", help="model id to use instead of the cheapest found")
    parser.add_argument("--show", type=int, default=3, help="how many cheap models to list (default 3)")
    args = parser.parse_args()

    print("key:", "OPENROUTER_API_KEY is set" if os.environ.get(orr.API_KEY_ENV, "").strip() else "OPENROUTER_API_KEY is NOT set")
    scratch = Path(tempfile.mkdtemp(prefix="vidgen-or-prices-"))
    models = [m["id"] for m in image_models() if text_to_image(m)]
    print(f"{len(models)} text-to-image models on OpenRouter; pricing each (free lookups)...")
    priced: list[tuple[float, str, str, str | None]] = []
    for model in models:
        cost, basis, tier, _ = price_at_smallest(model, scratch)
        if cost is not None and cost > 0:   # unknown (per token) and $0 listings are skipped
            priced.append((cost, model, basis, tier))
    priced.sort()
    print(f"cheapest {args.show} (square picture at the smallest tier):")
    for cost, model, basis, tier in priced[: args.show]:
        print(f"  ${cost:.4f}  {model}  [{tier or 'default size'}]  {basis}")
    if not priced and not args.model:
        print("no model with a known price found")
        return 1

    model = args.model or priced[0][1]
    _, _, tier, lookup = price_at_smallest(model, scratch)
    folder = Path(tempfile.mkdtemp(prefix="vidgen-or-live-"))
    project = write_project(folder, model, tier)
    print(f"\nproject: {folder}")
    print(f"model: {model}, resolution: {tier or '(model default)'}, aspect: 1:1")
    run_imagegen(project, dry_run=True)
    if not args.yes:
        print("\ndry run only: add --yes to generate this one picture (it costs the price above)")
        return 0
    if isinstance(lookup, orr.LookupFailure) and lookup.missing:
        print(lookup.reason)
        return 1
    try:
        plan = run_imagegen(project)
    except VidgenError as exc:
        print(f"error: {exc}")
        return 1
    for request in plan.todo:
        print(f"\nsaved: {request.path}")
        print(f"sidecar: {request.sidecar}")
        doc = json.loads(request.sidecar.read_text(encoding="utf-8"))
        print(f"cost reported by OpenRouter: {doc.get('cost_usd', 'not reported')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
