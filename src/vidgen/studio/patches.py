"""The catalogue of score-file instruments and effects in words (``vidgen music patches``,
DESIGN.md §93.4 / §93.7): what each one sounds like, its settings with default and range, and
how each effect is written."""

from __future__ import annotations

from typing import Any

from vidgen.studio.effects import EFFECTS, Field
from vidgen.studio.instruments import GROUPS, INSTRUMENTS

_KIND_WORDS = {
    "drum": "a drum or noise: steps of x X o . - (no pitch)",
    "note": "notes: steps of degrees, notes, x (the bass note) or * (the chord)",
    "pad": "a pad: play: chords holds the progression, or notes and chords in steps",
}


def _number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


def _field(f: Field) -> dict[str, Any]:
    return {"default": f.default, "low": f.low, "high": f.high, "words": f.words}


def patch_catalog() -> dict[str, Any]:
    """Every instrument (name, family, kind, description, level, default octave, settings) and
    every effect (description, example, fields), as data."""
    return {
        "instruments": [
            {
                "name": i.name,
                "group": i.group,
                "kind": i.kind,
                "plays": _KIND_WORDS[i.kind],
                "words": i.words,
                "level": i.level,
                "octave": i.octave,
                "settings": {k: {"default": _number(s.default), "low": _number(s.low), "high": _number(s.high), "words": s.words} for k, s in i.settings.items()},
            }
            for group in GROUPS
            for i in INSTRUMENTS.values()
            if i.group == group
        ],
        "effects": [{"name": e.name, "words": e.words, "example": e.example, "fields": {k: _field(f) for k, f in e.fields.items()}} for e in EFFECTS.values()],
    }


def _range(f: dict[str, Any]) -> str:
    if f["low"] is None:
        if f["default"] is None:
            return "required"
        return f"default {str(f['default']).lower() if isinstance(f['default'], bool) else f['default']}"
    default = "none" if f["default"] is None else f"{_number(f['default'])}"
    return f"default {default}, {_number(f['low'])} to {_number(f['high'])}"


def patch_text() -> str:
    """The catalogue as text for people and agents."""
    catalog = patch_catalog()
    lines = ["Instruments of score files (tracks: {name: {instrument: NAME, settings: {...}}}):"]
    group = None
    for i in catalog["instruments"]:
        if i["group"] != group:
            group = i["group"]
            lines += ["", f"{group.upper()}"]
        octave = f"; octave {i['octave']}" if i["octave"] is not None else ""
        lines.append(f"  {i['name']} ({i['kind']}{octave}): {i['words']}")
        for name, s in i["settings"].items():
            lines.append(f"      {name:<8} {s['default']:>7}  ({s['low']} to {s['high']})  {s['words']}")
    lines += ["", "Effects and movement (on a track, or in its sections: {name: {...}} changes; none / off switches one off there):"]
    for e in catalog["effects"]:
        lines += ["", f"  {e['name']}: {e['words']}", f"      e.g. {e['example']}"]
        for name, f in e["fields"].items():
            if name != "value":
                lines.append(f"      {name:<9} {f['words']} ({_range(f)})")
            else:
                lines.append(f"      value: {f['words']} ({_range(f)})")
    lines += [
        "",
        "Curves (volume, width, lowpass, highpass): a number; {from: a, to: b} ramps over the section; [[bar, value], ...]",
        "points (bars from the section's start, fractions allowed) are joined by straight lines (frequencies in octaves).",
    ]
    return "\n".join(lines)
