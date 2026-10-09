"""Live check of the OpenRouter image and text-to-speech providers (Steps 61, 61b, 62) against the real API.

Not shipped with vidgen and never run by the tests; a maintainer tool for a person with an
OpenRouter key. It

1. fetches OpenRouter's public image-model list (free, no key) and prints the cheapest models
   that take a text prompt, with their prices as vidgen estimates them (``--svg``: models that
   return SVG; ``--zdr``: only models with a Zero Data Retention endpoint, for accounts that
   require ZDR);
2. without ``--yes``: prints the dry run of one picture with the cheapest model and stops (free);
3. with ``--yes``: generates ONE small picture through vidgen's own code path
   (``vidgen.imagegen.run.run_imagegen`` with the ``openrouter`` provider) in a new temporary
   project folder, then prints where the PNG (``--svg``: SVG, with what vidgen's sanitiser makes
   of it) and its sidecar are and the cost OpenRouter reported.

``--tts`` checks narration instead (Step 62): it prices the text-to-speech models whose cost
per character is listed (``--zdr``: only those with a ZDR endpoint), prints ``vidgen tts
--dry-run`` of ONE short beat with the cheapest, and with ``--yes`` voices it through vidgen's own
code path (``vidgen.tts.run.run_tts``) in a temporary project, then prints the MP3's path and
duration and the cost OpenRouter reported.

The key is read only from the environment variable ``OPENROUTER_API_KEY`` (by vidgen, at the
moment of the request); this script never prints or stores it. Run from the repository root::

    python tools/live_check_openrouter.py            # free: model list + dry run
    python tools/live_check_openrouter.py --yes      # one paid picture (a few cents at most)
    python tools/live_check_openrouter.py --yes --model black-forest-labs/flux.2-klein-4b
    python tools/live_check_openrouter.py --zdr --yes           # only models with a ZDR endpoint
    python tools/live_check_openrouter.py --svg [--zdr] [--yes] # one vector (SVG) picture (~$0.08)
    python tools/live_check_openrouter.py --tts [--zdr] [--yes] [--model ID] [--voice NAME]
                                                                # one short beat of narration (< $0.01)
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
SVG_PROMPT = "a flat illustration of a red paper boat on a blue wave, simple shapes, few colours"
#: Resolution tiers from the smallest (the first one a model lists is used).
TIERS = ("512", "768", "1K", "1.5K", "2K", "4K")


def image_models() -> list[dict[str, Any]]:
    """``GET /api/v1/images/models`` (public)."""
    headers = {"Accept": "application/json", **orr.APP_HEADERS}
    body = httpapi.get(f"{orr.API_BASE}/images/models", headers=headers, service="OpenRouter", timeout=20)
    return [m for m in json.loads(body.decode("utf-8"))["data"] if isinstance(m, dict)]


def text_to_image(model: dict[str, Any], svg: bool = False) -> bool:
    """Takes a text prompt alone and makes raster pictures (``svg``: SVG pictures)."""
    arch = model.get("architecture") or {}
    params = model.get("supported_parameters") or {}
    refs = params.get("input_references") or {}
    formats = (params.get("output_format") or {}).get("values") or []
    makes = "svg" in formats if svg else formats != ["svg"]
    return "text" in (arch.get("input_modalities") or []) and not (refs.get("min") or 0) and makes


def smallest_tier(info: orr.ModelInfo) -> str | None:
    """The model's smallest listed resolution tier, if it lists any."""
    listed = info.values("resolution") or []
    return next((t for t in TIERS if t in listed), None)


def write_project(folder: Path, model: str, resolution: str | None, svg: bool = False) -> Project:
    """A one-scene project asking for one picture with ``model`` (``svg``: a vector picture)."""
    imagegen: dict[str, Any] = {"provider": "openrouter", "model": model}
    if resolution is not None and not svg:
        imagegen["resolution"] = resolution
    generate: dict[str, Any] = {"prompt": SVG_PROMPT if svg else PROMPT, "aspect": "square"}
    params: dict[str, Any] = {"generate": generate}
    if svg:
        generate["format"] = "svg"
        imagegen["svg_model"] = model
        params["draw"] = True
    config = {
        "title": "OpenRouter live check",
        "imagegen": imagegen,
        "scenes": [{"id": "pic", "type": "image", "params": params, "beats": [{"text": "A picture."}]}],
    }
    (folder / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return Project.load(folder)


def price_at_smallest(model: str, tmp: Path, svg: bool = False) -> tuple[float | None, str, str | None, orr.Lookup]:
    """vidgen's estimate of one square picture at the model's smallest tier."""
    lookup = orr.fetch_model_info(model, timeout=10)
    tier = smallest_tier(lookup) if isinstance(lookup, orr.ModelInfo) and not svg else None
    folder = tmp / model.replace("/", "__")
    folder.mkdir(parents=True, exist_ok=True)
    generate = GenerateImage(prompt=SVG_PROMPT if svg else PROMPT, aspect="square", format="svg" if svg else "png")
    request = image_request(write_project(folder, model, tier, svg), generate)
    quote = orr.quote(request, lookup)
    return quote.cost, quote.basis, tier, lookup


def report_svg(path: Path) -> None:
    """What vidgen's sanitiser makes of a generated SVG."""
    from vidgen.svgclean import sanitize_svg

    data = path.read_bytes()
    clean = sanitize_svg(data, where=path.name)
    print(f"SVG: {len(data)} bytes, {clean.shapes} shapes, {clean.segments} curve segments after sanitising")
    for warning in clean.warnings:
        print(f"  sanitiser: {warning}")


#: The one beat ``--tts`` voices (12 words).
TTS_TEXT = "This is a short live check of OpenRouter narration in vidgen."


def pick_voice(voices: tuple[str, ...] | None) -> str | None:
    """An English-looking voice of the model's list (else its first; ``None`` without a list)."""
    if not voices:
        return None
    english = [v for v in voices if v.lower().startswith(("en", "af_", "am_")) or "-en" in v.lower() or "english" in v.lower()]
    neutral = [v for v in english if "neutral" in v.lower()]
    return (neutral or english or list(voices))[0]


def write_tts_project(folder: Path, model: str, voice: str | None) -> Project:
    """A one-beat project voiced by ``model`` (``voice`` when given)."""
    spec: dict[str, Any] = {"provider": "openrouter", "model": model}
    if voice is not None:
        spec["voice"] = voice
    config = {
        "title": "OpenRouter TTS live check",
        "voice": spec,
        "scenes": [{"id": "check", "type": "text_card", "params": {"text": "Live check"}, "beats": [{"id": "check", "text": TTS_TEXT}]}],
    }
    (folder / "video.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return Project.load(folder)


def tts_check(args: argparse.Namespace) -> int:
    """``--tts``: price the TTS models, dry-run one beat with the cheapest, voice it with --yes."""
    from vidgen.tts import openrouter as ortts
    from vidgen.tts.run import run_tts

    listed = ortts.fetch_speech_models(timeout=20)
    if isinstance(listed, orr.LookupFailure):
        print(listed.reason)
        return 1
    models = sorted(listed)
    if args.zdr:
        allowed = ortts.zdr_tts_models(timeout=20)
        if allowed is None:
            print("OpenRouter's list of ZDR endpoints could not be reached")
            return 1
        models = [m for m in models if m in allowed]
    kind = "text-to-speech models" + (" with a ZDR endpoint" if args.zdr else "")
    print(f"{len(models)} {kind} on OpenRouter; pricing each (free lookups)...")
    found = ortts.lookup_speech_models(models, timeout=20)
    priced: list[tuple[float, str, str]] = []
    for model, lookup in found.items():
        quote = ortts.character_rate(lookup)
        if quote.cost is not None and quote.cost > 0:  # unknown (audio billed) and $0 listings skipped
            priced.append((quote.cost, model, quote.basis))
    priced.sort()
    print(f"cheapest {args.show} per character ({len(TTS_TEXT)} characters to voice):")
    for cost, model, basis in priced[: args.show]:
        print(f"  ${cost * len(TTS_TEXT):.6f}  {model}  {basis}")
    if not priced and not args.model:
        print("no TTS model with a known price per character found")
        return 1
    model = args.model or priced[0][1]
    lookup = found.get(model) or ortts.lookup_speech_models([model], timeout=20)[model]
    voice = args.voice or pick_voice(lookup.voices if isinstance(lookup, ortts.SpeechModel) else None)
    folder = Path(tempfile.mkdtemp(prefix="vidgen-or-tts-"))
    project = write_tts_project(folder, model, voice)
    print(f"\nproject: {folder}")
    print(f"model: {model}, voice: {voice or '(model default)'}")
    run_tts(project, dry_run=True)
    if not args.yes:
        print("\ndry run only: add --yes to voice this one beat (it costs the price above)")
        return 0
    try:
        plan = run_tts(project)
    except VidgenError as exc:
        print(f"error: {exc}")
        return 1
    from vidgen.scene import audio_duration

    mp3 = project.audio_dir / "check.mp3"
    print(f"\nsaved: {mp3}")
    print(f"duration: {audio_duration(mp3):.2f} s, {mp3.stat().st_size} bytes")
    print(f"cost reported by OpenRouter: {plan.charged if plan.charged is not None else 'not reported'}")
    print(f"listen to it, or check it: vidgen readback {folder}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="really generate one picture / one beat (costs money)")
    parser.add_argument("--model", help="model id to use instead of the cheapest found")
    parser.add_argument("--show", type=int, default=3, help="how many cheap models to list (default 3)")
    parser.add_argument("--svg", action="store_true", help="a vector (SVG) picture with a model that returns SVG")
    parser.add_argument("--tts", action="store_true", help="text to speech: one short beat with the cheapest TTS model")
    parser.add_argument("--voice", help="--tts: the model's voice to use (default: an English one of its list)")
    parser.add_argument("--zdr", action="store_true", help="only models with a Zero Data Retention endpoint (accounts requiring ZDR)")
    args = parser.parse_args()

    print("key:", "OPENROUTER_API_KEY is set" if os.environ.get(orr.API_KEY_ENV, "").strip() else "OPENROUTER_API_KEY is NOT set")
    if args.tts:
        return tts_check(args)
    scratch = Path(tempfile.mkdtemp(prefix="vidgen-or-prices-"))
    kind = "text-to-SVG" if args.svg else "text-to-image"
    models = [m["id"] for m in image_models() if text_to_image(m, args.svg)]
    if args.zdr:
        allowed = orr.zdr_image_models(timeout=20, svg=args.svg)
        if allowed is None:
            print("OpenRouter's list of ZDR endpoints could not be reached")
            return 1
        models = [m for m in models if m in allowed]
        kind += " models with a ZDR endpoint"
    print(f"{len(models)} {kind} on OpenRouter; pricing each (free lookups)...")
    priced: list[tuple[float, str, str, str | None]] = []
    for model in models:
        cost, basis, tier, _ = price_at_smallest(model, scratch, args.svg)
        if cost is not None and cost > 0:   # unknown (per token) and $0 listings are skipped
            priced.append((cost, model, basis, tier))
    priced.sort()
    print(f"cheapest {args.show} (square picture at the smallest tier):")
    for cost, model, basis, tier in priced[: args.show]:
        print(f"  ${cost:.4f}  {model}  [{tier or 'default size'}]  {basis}")
    if not priced and not args.model:
        print("no model with a known price found" + (" (no SVG model has a ZDR endpoint: drop --zdr if your account allows it)" if args.svg and args.zdr else ""))
        return 1

    model = args.model or priced[0][1]
    _, _, tier, lookup = price_at_smallest(model, scratch, args.svg)
    folder = Path(tempfile.mkdtemp(prefix="vidgen-or-live-"))
    project = write_project(folder, model, tier, args.svg)
    print(f"\nproject: {folder}")
    print(f"model: {model}, resolution: {tier or '(model default)'}, aspect: 1:1, format: {'svg' if args.svg else 'png'}")
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
        if request.format == "svg":
            report_svg(request.path)
            print(f"see it drawn: vidgen storyboard {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
