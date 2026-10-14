"""Make a gallery still of built-in sets (``docs/gallery/media/sets_outdoors.png``,
``sets_indoors.png``): each set as a small thumbnail, two characters on its ``stand_left`` /
``stand_right`` marks, its name below.

Not shipped with vidgen; a maintainer tool. It writes a project with one stage scene per set into
``--work`` (a scratch folder), renders its storyboard stills at preview size with ``vidgen
storyboard --jobs 1`` (run it under the memory cap, CODING-AND-COMMUNICATION-GUIDE rule 7), and
tiles each scene's first still into one 64-colour PNG. Run from the repository root::

    python tools/make_sets_gallery.py --work /tmp/sets --out docs/gallery/media/sets_outdoors.png \\
        city_street park beach forest snowy_hills
    python tools/make_sets_gallery.py --work /tmp/rooms --out docs/gallery/media/sets_indoors.png \\
        classroom kitchen shop living_room bedroom

``--styles`` draws one set in each drawing style of :data:`STYLES` instead (``drawing:``, DESIGN.md
§79; ``docs/gallery/media/drawing_styles.png``), each thumbnail a quarter of the still around the
left character, so outlines and grain show::

    python tools/make_sets_gallery.py --work /tmp/styles --out docs/gallery/media/drawing_styles.png --styles --colors 48 park
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "src" / "vidgen" / "data" / "fonts" / "Inter" / "Inter-Regular.ttf"
#: Thumbnail size (px), columns, the label band under each thumbnail, the gap between cells.
THUMB = (320, 180)
COLUMNS = 3
LABEL = 26
GAP = 8
PAPER = (244, 246, 250)
INK = (43, 47, 58)
#: ``--styles``: (scene id, label, ``drawing:``) of each thumbnail.
STYLES: list[tuple[str, str, dict]] = [
    ("plain", "default (normal, flat, none)", {}),
    ("thin", "outline: thin", {"outline": "thin"}),
    ("bold", "outline: bold", {"outline": "bold"}),
    ("soft", "shading: soft", {"shading": "soft"}),
    ("paper", "texture: paper", {"texture": "paper"}),
    ("storybook", "bold + soft + storybook", {"outline": "bold", "shading": "soft", "texture": "storybook"}),
]


def project_for(sets: list[str], styles: list[tuple[str, str, dict]] | None = None) -> dict:
    """A project with one stage scene per set (with ``styles``: one per style, on the first set),
    two generated characters on the set's clear marks."""
    characters = [
        {"name": "nib", "look": {"body": "round", "hair": "curly"}, "colors": {"clothes": "primary"}},
        {"name": "olla", "look": {"body": "bean", "ears": "floppy", "accessories": ["hat"]}, "colors": {"clothes": "tertiary"}},
    ]
    cast = {"idle": False, "characters": [{"name": "nib", "at": "stand_left"}, {"name": "olla", "at": "stand_right"}]}
    shown = [(name, name, {}) for name in sets] if styles is None else [(sid, sets[0], drawing) for sid, _, drawing in styles]
    scenes = [
        {"id": sid, "type": "stage", "set": name, "params": {**cast, "drawing": drawing} if drawing else cast,
         "beats": [{"text": "A ready-made set."}]}
        for sid, name, drawing in shown
    ]
    return {"title": "Sets gallery", "preview": {"width": 854, "height": 480, "fps": 15}, "characters": characters, "scenes": scenes}


def thumbnail(still: Image.Image, crop: bool) -> Image.Image:
    """The still resized to :data:`THUMB`, or (``crop``) the quarter of it around the left
    character (its ``stand_left`` mark) resized to it."""
    if crop:
        left, top = round(still.width * 0.05), round(still.height * 0.31)
        still = still.crop((left, top, left + still.width // 2, top + still.height // 2))
    return still.resize(THUMB, Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sets", nargs="+", help="set names, in gallery order")
    parser.add_argument("--work", type=Path, required=True, help="a scratch folder for the project and its renders")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--styles", action="store_true", help="the first set in each drawing style instead")
    parser.add_argument("--colors", type=int, default=64, help="colours of the PNG (fewer: smaller)")
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    styles = STYLES if args.styles else None
    (args.work / "video.yaml").write_text(yaml.safe_dump(project_for(args.sets, styles), sort_keys=False), encoding="utf-8")
    done = subprocess.run([sys.executable, "-m", "vidgen", "storyboard", str(args.work), "--jobs", "1", "--json"],
                          check=True, capture_output=True, text=True, encoding="utf-8")
    first = {sheet["scene"]: sheet["frames"][0]["path"] for sheet in json.loads(done.stdout)["sheets"]}
    cells = [(name, name) for name in args.sets] if styles is None else [(sid, label) for sid, label, _ in styles]
    rows = -(-len(cells) // COLUMNS)
    cell_w, cell_h = THUMB[0] + GAP, THUMB[1] + LABEL + GAP
    sheet = Image.new("RGB", (COLUMNS * cell_w + GAP, rows * cell_h + GAP), PAPER)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONT), 16)
    for k, (scene_id, label) in enumerate(cells):
        row, column = divmod(k, COLUMNS)
        left, top = GAP + column * cell_w, GAP + row * cell_h
        with Image.open(first[scene_id]) as still:
            sheet.paste(thumbnail(still.convert("RGB"), crop=styles is not None), (left, top))
        draw.text((left + THUMB[0] / 2, top + THUMB[1] + LABEL / 2), label, fill=INK, font=font, anchor="mm")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.quantize(colors=args.colors).save(args.out, optimize=True)
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
