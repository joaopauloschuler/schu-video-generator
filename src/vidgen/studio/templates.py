"""Templates of the built-in beds (DESIGN.md §93.8, §93.12): each of vidgen's 16 music beds written
as an editable score file to start a new piece from — for the 14 beds made in Python a close
re-creation (not bit-identical); for ``tidewater`` and ``skyline`` the very score the bed is
rendered from. They ship as package data in ``studio/beds/<bed>.yaml``; ``vidgen music template
<bed>`` copies one out.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.music import BUILTIN_BEDS
from vidgen.studio.score_file import load_music_score

#: Where the templates live (package data).
TEMPLATE_DIR = Path(__file__).parent / "beds"


def template_names() -> list[str]:
    """The beds that have a template, in the beds' listing order."""
    return [name for name in BUILTIN_BEDS if (TEMPLATE_DIR / f"{name}.yaml").is_file()]


def template_path(bed: str) -> Path:
    """The template file of ``bed`` (:class:`VidgenError` with did-you-mean for an unknown one)."""
    names = template_names()
    if bed not in names:
        close = difflib.get_close_matches(bed, names, n=1, cutoff=0.6)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        raise VidgenError(f"no template for '{bed}'{hint} (templates: {', '.join(names)})")
    return TEMPLATE_DIR / f"{bed}.yaml"


def music_template_text(bed: str) -> str:
    """The template of ``bed`` as YAML text (with its comments)."""
    return template_path(bed).read_text(encoding="utf-8")


def music_template_catalog() -> list[dict[str, Any]]:
    """Every template's facts: bed name, title, key, tempo, time, bars, seconds, sections,
    tracks and description."""
    out = []
    for name in template_names():
        score = load_music_score(template_path(name))
        out.append(
            {
                "name": name,
                "title": score.title,
                "key": score.key.name,
                "tempo": score.tempo,
                "time": f"{score.time[0]}/{score.time[1]}",
                "bars": score.bars,
                "seconds": round(score.seconds, 3),
                "sections": [s.name for s in score.sections],
                "tracks": [t.name for t in score.tracks],
                "description": score.description,
            }
        )
    return out
