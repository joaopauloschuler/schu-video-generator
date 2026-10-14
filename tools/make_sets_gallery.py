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


def project_for(sets: list[str]) -> dict:
    """A project with one stage scene per set, two generated characters on the set's clear marks."""
    characters = [
        {"name": "nib", "look": {"body": "round", "hair": "curly"}, "colors": {"clothes": "primary"}},
        {"name": "olla", "look": {"body": "bean", "ears": "floppy", "accessories": ["hat"]}, "colors": {"clothes": "tertiary"}},
    ]
    scenes = [
        {"id": name, "type": "stage", "set": name,
         "params": {"idle": False, "characters": [{"name": "nib", "at": "stand_left"}, {"name": "olla", "at": "stand_right"}]},
         "beats": [{"text": "A ready-made set."}]}
        for name in sets
    ]
    return {"title": "Sets gallery", "preview": {"width": 854, "height": 480, "fps": 15}, "characters": characters, "scenes": scenes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sets", nargs="+", help="set names, in gallery order")
    parser.add_argument("--work", type=Path, required=True, help="a scratch folder for the project and its renders")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    (args.work / "video.yaml").write_text(yaml.safe_dump(project_for(args.sets), sort_keys=False), encoding="utf-8")
    done = subprocess.run([sys.executable, "-m", "vidgen", "storyboard", str(args.work), "--jobs", "1", "--json"],
                          check=True, capture_output=True, text=True, encoding="utf-8")
    first = {sheet["scene"]: sheet["frames"][0]["path"] for sheet in json.loads(done.stdout)["sheets"]}
    rows = -(-len(args.sets) // COLUMNS)
    cell_w, cell_h = THUMB[0] + GAP, THUMB[1] + LABEL + GAP
    sheet = Image.new("RGB", (COLUMNS * cell_w + GAP, rows * cell_h + GAP), PAPER)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONT), 16)
    for k, name in enumerate(args.sets):
        row, column = divmod(k, COLUMNS)
        left, top = GAP + column * cell_w, GAP + row * cell_h
        with Image.open(first[name]) as still:
            sheet.paste(still.convert("RGB").resize(THUMB, Image.Resampling.LANCZOS), (left, top))
        draw.text((left + THUMB[0] / 2, top + THUMB[1] + LABEL / 2), name, fill=INK, font=font, anchor="mm")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.quantize(colors=64).save(args.out, optimize=True)
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
