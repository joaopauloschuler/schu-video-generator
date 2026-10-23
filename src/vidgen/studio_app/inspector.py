"""What the studio's inspector changes beyond one value (DESIGN.md §94.13): the patch catalogue with
units and slider scales, an instrument change that keeps the settings the new instrument has and
says what changes, the play mode of a pad (chords or steps) and whether a track plays in a section
(``rest`` / ``only``). Each is a list of :mod:`vidgen.studio_app.edits` ops, a label for the
version and plain-language notes on what changes.
"""

from __future__ import annotations

import copy
import difflib
import re
from collections.abc import Mapping
from typing import Any

from vidgen.errors import VidgenError
from vidgen.studio_app.song import default_steps

_UNITS = (  # in this order: "vibrato depth in cents (5 Hz)" is in cents
    (re.compile(r"\bcents\b"), "cents"),
    (re.compile(r"\bHz\b"), "Hz"),
    (re.compile(r"\bseconds?\b"), "s"),
    (re.compile(r"\bbars\b"), "bars"),
    (re.compile(r"\bbeats\b"), "beats"),
    (re.compile(r"\bdB\b"), "dB"),
)


def unit_of(words: str) -> str:
    """The unit a setting's words name (``"centre in Hz"`` → ``Hz``), or ``""``."""
    for pattern, unit in _UNITS:
        if pattern.search(words):
            return unit
    return ""


def _slider(field: dict[str, Any], integer: bool) -> None:
    """Add ``unit``, ``scale`` (``log`` for a frequency spanning two octaves or more) and
    ``integer`` (whole numbers only) to a catalogue field with a range."""
    field["unit"] = unit_of(str(field.get("words", "")))
    low, high = field.get("low"), field.get("high")
    log = field["unit"] == "Hz" and isinstance(low, (int, float)) and low > 0 and high / low >= 4
    field["scale"] = "log" if log else "linear"
    field["integer"] = integer


def studio_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    """:func:`vidgen.studio.patch_catalog` for the page: every setting and effect field with a
    range gets its ``unit``, ``scale`` and ``integer`` (``music patches --json`` is unchanged).
    Instrument settings are real numbers (the catalogue writes 2600.0 as 2600); an effect field
    is whole when its default is (echo ``repeats``), as the score checks it."""
    out = copy.deepcopy(dict(catalog))
    for instrument in out["instruments"]:
        for setting in instrument["settings"].values():
            _slider(setting, False)
    for effect in out["effects"]:
        for field in effect["fields"].values():
            if field.get("low") is not None:
                default = field.get("default")
                _slider(field, isinstance(default, int) and not isinstance(default, bool))
    return out


# ----- helpers --------------------------------------------------------------------------------


def _track_spec(data: Mapping[str, Any], track: str, what: str) -> Mapping[str, Any]:
    spec = (data.get("tracks") or {}).get(track)
    if not isinstance(spec, Mapping):
        raise VidgenError(f"{what}: no track '{track}'")
    return spec


def _overrides(spec: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    changes = spec.get("sections")
    return {str(k): v for k, v in changes.items() if isinstance(v, Mapping)} if isinstance(changes, Mapping) else {}


def _pitched(steps: Any) -> bool:
    """Whether a steps value names pitches (degrees, notes, chords): a drum cannot play it."""
    from vidgen.studio.patterns import parse_steps

    try:
        pattern = parse_steps(steps, "steps", True)
    except VidgenError:
        return False
    return any(s.pitched for bar in pattern for s in bar)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fmt(value: float) -> str:
    return f"{value:g}"


# ----- the instrument ---------------------------------------------------------------------------


def change_instrument(data: Mapping[str, Any], score: Any, track: str, name: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    """The edits that make ``track`` play ``name``: the settings the new instrument also has are
    kept (moved into its range when outside it), the others dropped; a drum loses its octave,
    transpose and pitched steps (a default pattern instead); a pad's ``play: chords`` becomes steps
    on an instrument that cannot hold chords. Returns the ops, a label and notes on what changes."""
    from vidgen.studio import INSTRUMENTS

    spec = _track_spec(data, track, "change instrument")
    new = INSTRUMENTS.get(name)
    if new is None:
        close = difflib.get_close_matches(name, list(INSTRUMENTS), n=1, cutoff=0.6)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        raise VidgenError(f"change instrument: unknown instrument '{name}'{hint} (instruments: {', '.join(INSTRUMENTS)})")
    old = INSTRUMENTS.get(str(spec.get("instrument")))
    if old is None or old.name == new.name:
        return [], "", []
    base = f"tracks.{track}"
    ops: list[dict[str, Any]] = [{"op": "set", "path": f"{base}.instrument", "value": new.name}]
    notes: list[str] = []
    kept: list[str] = []
    dropped: list[str] = []
    places = [(base, spec)] + [(f"{base}.sections.{s}", change) for s, change in _overrides(spec).items()]
    for where, part in places:
        settings = part.get("settings")
        if not isinstance(settings, Mapping):
            continue
        for key, value in settings.items():
            setting = new.settings.get(str(key))
            if setting is None:
                dropped.append(str(key))
                ops.append({"op": "unset", "path": f"{where}.settings.{key}"})
            elif _number(value) and not setting.low <= value <= setting.high:
                inside = min(max(value, setting.low), setting.high)
                ops.append({"op": "set", "path": f"{where}.settings.{key}", "value": inside})
                notes.append(f"{key} {_fmt(value)} → {_fmt(inside)} ({new.name}'s range is {_fmt(setting.low)} to {_fmt(setting.high)})")
            else:
                kept.append(str(key))
    if kept:
        notes.insert(0, f"keeps {', '.join(dict.fromkeys(kept))}")
    if dropped:
        notes.append(f"drops {', '.join(dict.fromkeys(dropped))} ({new.name} has no such setting)")
    if new.kind == "drum":
        for where, part in places:
            for key in ("octave", "transpose"):
                if key in part:
                    ops.append({"op": "unset", "path": f"{where}.{key}"})
                    notes.append(f"drops {key} ({new.name} has no pitch)")
    elif old.kind == "drum":
        notes.append(f"x hits play the chord's bass note; plays in octave {new.octave} unless octave is set")
    elif "octave" not in spec and old.octave != new.octave:
        notes.append(f"plays in octave {new.octave} ({new.name}'s own; {old.name} played in {old.octave})")
    play_chords = spec.get("play") == "chords"
    if play_chords and new.kind != "pad":
        steps = default_steps(new.name, new.kind, score.time) or "*"
        ops += [{"op": "unset", "path": f"{base}.play"}, {"op": "set", "path": f"{base}.steps", "value": steps}]
        notes.append(f"{new.name} cannot hold chords: plays a first pattern instead (\"{steps}\")")
    elif new.kind == "drum" and "steps" in spec and _pitched(spec["steps"]):
        steps = default_steps(new.name, new.kind, score.time) or "x"
        ops.append({"op": "set", "path": f"{base}.steps", "value": steps})
        ops += [{"op": "unset", "path": f"{base}.accent"}] if "accent" in spec else []
        notes.append(f"the steps had notes and {new.name} has no pitch: a first {new.name} pattern instead (\"{steps}\")")
    if new.kind == "drum":
        for section, change in _overrides(spec).items():
            if "steps" in change and _pitched(change["steps"]):
                ops.append({"op": "unset", "path": f"{base}.sections.{section}.steps"})
                notes.append(f"drops the notes {section} played (no pitch)")
    return ops, f"{track}: {old.name} → {new.name}", list(dict.fromkeys(notes))


# ----- play mode --------------------------------------------------------------------------------


def set_play_mode(data: Mapping[str, Any], score: Any, track: str, mode: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    """The edits that make a pad hold the chords (``mode`` ``chords``) or play steps (``steps``:
    the chord on each bar's first beat, held)."""
    from vidgen.studio import INSTRUMENTS

    spec = _track_spec(data, track, "play mode")
    instrument = INSTRUMENTS.get(str(spec.get("instrument")))
    base = f"tracks.{track}"
    if mode not in ("chords", "steps"):
        raise VidgenError(f"play mode: 'chords' or 'steps', got {mode!r}")
    chords_now = spec.get("play") == "chords"
    if (mode == "chords") == chords_now:
        return [], "", []
    if mode == "chords":
        if instrument is None or instrument.kind != "pad":
            pads = ", ".join(n for n, i in INSTRUMENTS.items() if i.kind == "pad")
            raise VidgenError(f"play mode: {spec.get('instrument')} cannot hold chords ({pads} can)")
        ops: list[dict[str, Any]] = [{"op": "unset", "path": f"{base}.{k}"} for k in ("steps", "accent") if k in spec]
        notes = ["holds the progression's chords, cross-faded (the steps are dropped; the version before keeps them)"] if "steps" in spec else []
        for section, change in _overrides(spec).items():
            if "steps" in change or "accent" in change:
                ops += [{"op": "unset", "path": f"{base}.sections.{section}.{k}"} for k in ("steps", "accent") if k in change]
                notes.append(f"drops the steps {section} played")
        ops.append({"op": "set", "path": f"{base}.play", "value": "chords"})
        return ops, f"{track}: holds the chords", notes
    steps = " ".join(["*"] + ["-"] * (score.time[0] - 1)) if score.time[1] == 4 else "*"
    ops = [{"op": "unset", "path": f"{base}.play"}, {"op": "set", "path": f"{base}.steps", "value": steps}]
    return ops, f"{track}: plays steps", [f"plays the chord on each bar's first beat, held (\"{steps}\"); edit the steps to change it"]


# ----- where a track plays ----------------------------------------------------------------------


def set_section_plays(data: Mapping[str, Any], track: str, section: str, plays: bool) -> tuple[list[dict[str, Any]], str, list[str]]:
    """The edits that make ``track`` play or rest in ``section``, written as the track already
    does (``only`` when it lists the sections it plays in, else ``rest``); resting drops the
    section's changes (they would never play)."""
    spec = _track_spec(data, track, "plays in")
    raw = data.get("sections")
    names = [str(s.get("name")) for s in raw if isinstance(s, Mapping)] if isinstance(raw, list) else ["main"]
    if section not in names:
        close = difflib.get_close_matches(section, names, n=1, cutoff=0.6)
        raise VidgenError(f"plays in: no section '{section}'{f'; did you mean {close[0]!r}?' if close else ''} (sections: {', '.join(names)})")

    def listed(value: Any) -> list[str]:
        return [value] if isinstance(value, str) else [str(v) for v in value] if isinstance(value, list) else []

    silent = set(listed(spec.get("rest")))
    if "only" in spec:
        silent = set(names) - set(listed(spec.get("only")))
    if (section not in silent) == plays:
        return [], "", []
    silent = silent - {section} if plays else silent | {section}
    if len(silent) == len(names):
        raise VidgenError(f"plays in: {track} would play nowhere; delete the track instead")
    base = f"tracks.{track}"
    notes: list[str] = []
    ops: list[dict[str, Any]] = []
    if "only" in spec:
        playing = [n for n in names if n not in silent]
        ops.append({"op": "unset", "path": f"{base}.only"} if len(playing) == len(names) else {"op": "set", "path": f"{base}.only", "value": playing})
    else:
        resting = [n for n in names if n in silent]
        ops.append({"op": "set", "path": f"{base}.rest", "value": resting} if resting else {"op": "unset", "path": f"{base}.rest"})
    if not plays and isinstance(spec.get("sections"), Mapping) and section in spec["sections"]:
        ops.append({"op": "unset", "path": f"{base}.sections.{section}"})
        notes.append(f"drops its changes for {section} (a rest plays nothing)")
    return ops, f"{track}: {'plays' if plays else 'rests'} in {section}", notes
