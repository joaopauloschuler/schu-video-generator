"""The catalogue of score-file instruments and effects in words (``vidgen music patches``): what each one sounds like, its settings with default and range, and
how each effect is written."""

from __future__ import annotations

from typing import Any

from vidgen.studio.effects import EFFECTS, Field
from vidgen.studio.instruments import GROUPS, INSTRUMENTS, Setting

_KIND_WORDS = {
    "drum": "a drum or noise: steps of x X o . - (no pitch)",
    "note": "notes: steps of degrees, notes, x (the bass note) or * (the chord)",
    "pad": "a pad: play: chords holds the progression, or notes and chords in steps",
}


def _number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


def _field(f: Field) -> dict[str, Any]:
    return {"default": f.default, "low": f.low, "high": f.high, "words": f.words}


def _setting(s: Setting) -> dict[str, Any]:
    """A setting as data; one with named values also has ``choices`` (the names of 0, 1, ...)."""
    out: dict[str, Any] = {"default": _number(s.default), "low": _number(s.low), "high": _number(s.high), "words": s.words}
    if s.choices:
        out["choices"] = list(s.choices)
    return out


def patch_catalog() -> dict[str, Any]:
    """Every instrument (name, family, kind, description, level, default octave, settings;
    ``range`` when it has a written one; ``dynamics: true`` when a dynamic mark changes its tone
    as well as its level, ``slurs: true`` when it can slur) and every effect
    (description, example, fields), as data."""
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
                "settings": {k: _setting(s) for k, s in i.settings.items()},
                **({"range": list(i.range)} if i.range else {}),
                **({"dynamics": True} if i.respond is not None else {}),
                **({"slurs": True} if i.slurs is not None else {}),
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
        made_for = f"; made for {i['range'][0]} to {i['range'][1]}" if "range" in i else ""
        marks = "; ".join(w for w, key in (("dynamics change its tone", "dynamics"), ("slurs", "slurs")) if key in i)
        lines.append(f"  {i['name']} ({i['kind']}{octave}{made_for}{'; ' + marks if marks else ''}): {i['words']}")
        for name, s in i["settings"].items():
            if "choices" in s:
                lines.append(f"      {name:<8} {s['choices'][s['default']]:>7}  ({', '.join(s['choices'])}; or its number from 0)  {s['words']}")
            else:
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
        "",
        "Marks in a track's steps, each in force until changed (vidgen guide music, \"Expression\"):",
        "  [pp] [p] [mp] [mf] [f] [ff], [-6] (dB)   a dynamic: the level and, on instruments marked above, the tone",
        "  [p <] ... [f]    a hairpin: the level moves from this step to the next dynamic ([f >] ... [p] falls); under a held note it shapes the note",
        "  [fp] [sfz]       a loud start falling to piano; a start 7 dB over the level in force",
        "  [stroke=pizzicato] [pitch=90] [roll]   a setting of the instrument from this step on (a named value may stand alone); [default] ends them",
        "  (A4 - C5 - E5 -)  a slur: one note gliding from pitch to pitch (the glide setting: seconds)",
    ]
    return "\n".join(lines)
