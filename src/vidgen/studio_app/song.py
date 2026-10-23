"""What the studio's song strip, timeline and track list show and change (DESIGN.md §94.12): the
facts of a score for the page (chords as Roman numerals with their names, each section's own
progression, each track's steps as levels for the meters) and the edits that change more than
one value (add or delete a track, add, remove or rename a section), as lists of
:mod:`vidgen.studio_app.edits` ops.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from vidgen.errors import VidgenError

#: A track's or section's name in a score (as :mod:`vidgen.studio.score_file` checks it).
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII")
_PITCH = re.compile(r"^[A-G][#b]?")
_SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
#: The volume a new track starts at (dB), below the parts already there.
NEW_TRACK_VOLUME = -6


# ----- chords ---------------------------------------------------------------------------------


def roman_numeral(chord: Any, key: Any) -> str:
    """``chord`` (a :class:`vidgen.studio.theory.Chord`) as a Roman numeral of ``key``: the
    degree of its root (``b`` / ``#`` when outside the scale), lower case when minor, then the
    chord's suffix as written (``Gm(add9)`` in G minor is ``i(add9)``, ``Ebmaj7`` ``VImaj7``,
    ``C/E`` in C major ``I/E``). It reads back as the same notes."""
    from vidgen.studio.theory import MODES

    steps = MODES[key.mode]
    rel = (chord.root - key.tonic) % 12
    if rel in steps:
        degree, accidental = steps.index(rel), ""
    elif (rel + 1) % 12 in steps:
        degree, accidental = steps.index((rel + 1) % 12), "b"
    else:
        degree, accidental = steps.index((rel - 1) % 12), "#"
    tones = set(chord.intervals)
    minor = 3 in tones and 4 not in tones
    body = chord.name.split("/")[0] if "/" in chord.name and not chord.name.endswith("6/9") else chord.name
    match = _PITCH.match(body)
    suffix = body[match.end() :] if match else ""
    if suffix.startswith("min"):  # written minor (a minor seventh sus chord has no third)
        suffix, minor = suffix[3:], True
    elif suffix.startswith("m") and not suffix.startswith("maj"):
        suffix, minor = suffix[1:], True
    numeral = _ROMAN[degree].lower() if minor else _ROMAN[degree]
    text = accidental + numeral + suffix
    if chord.bass != chord.root:
        written = chord.symbol.rsplit("/", 1)[-1] if "/" in chord.symbol and not chord.symbol.endswith("6/9") else ""
        text += "/" + (written if _PITCH.fullmatch(written) else (_FLAT_NAMES if key.flats else _SHARP_NAMES)[chord.bass])
    return text


def _progression_items(raw: Any) -> list[str] | None:
    """The chords of a progression as written: ``"i VI | III VII"`` or a list of names or
    ``{chord, notes, bass}`` voicings, as the chord symbols."""
    if isinstance(raw, str):
        return raw.replace("|", " ").replace(",", " ").split()
    if isinstance(raw, list):
        return [str(item.get("chord", "")) if isinstance(item, Mapping) else str(item) for item in raw]
    return None


def analyse_progression(raw: Any, key: Any) -> dict[str, Any] | None:
    """A progression as written (``raw``) read in ``key``: ``{text, written, chords: [{numeral,
    name}]}`` — ``text`` the numerals to edit (the string itself when written as one),
    ``written`` ``"text"``, ``"names"`` or ``"voicings"`` (``{chord, notes}`` items, which typing
    replaces); ``None`` when there is none or it does not read."""
    from vidgen.studio.theory import parse_chord

    items = _progression_items(raw)
    if not items:
        return None
    chords = []
    try:
        for symbol in items:
            chord = parse_chord(symbol, key)
            chords.append({"symbol": symbol, "numeral": roman_numeral(chord, key), "name": chord.name})
    except VidgenError:
        return None
    if isinstance(raw, str):
        written, text = "text", raw
    else:
        written = "voicings" if any(isinstance(item, Mapping) for item in raw) else "names"
        text = " ".join(c["numeral"] for c in chords)
    return {"text": text, "written": written, "chords": chords}


# ----- the page's facts -----------------------------------------------------------------------


def steps_text(spec: Any) -> str:
    """A track's ``steps`` as one line (a list of strings joined by ``|``, which reads the same)."""
    steps = spec.get("steps") if isinstance(spec, Mapping) else None
    if isinstance(steps, list):
        return " | ".join(str(s) for s in steps)
    return "" if steps is None else str(steps)


def _step_levels(part: Any) -> list[list[float]] | None:
    """A part's steps as levels, bar by bar: its gain on a hit (accents included), 0 on a rest,
    -1 on a hold (the meters of the track list, rough until Step 196)."""
    from vidgen.studio.patterns import ACCENT_GAIN, accent_steps

    if part.steps is None:
        return None
    out = []
    for bar in part.steps:
        accents = accent_steps(part.accent, len(bar)) if part.accent else None
        levels = []
        for k, step in enumerate(bar):
            if step.kind == "hold":
                levels.append(-1.0)
            elif step.kind == "rest":
                levels.append(0.0)
            else:
                levels.append(round(ACCENT_GAIN if accents is not None and k in accents and not step.marked else step.gain, 2))
        out.append(levels)
    return out


def describe_score(score: Any, data: Mapping[str, Any]) -> dict[str, Any]:
    """The facts the page shows: :func:`vidgen.studio.score_outline` plus the progression (score
    and each section's own, as numerals and names), whether the sections are written as a list,
    each section's first bar, and per track its steps text, volume, pan, settings as written and
    its steps as levels per section (for the meters)."""
    from vidgen.sfx import RATE
    from vidgen.studio import score_outline

    outline = score_outline(score)
    raw_tracks = data.get("tracks") or {}
    by_name = {t.name: t for t in score.tracks}
    for track in outline["tracks"]:
        spec = raw_tracks.get(track["name"], {})
        volume = spec.get("volume", 0)
        track["steps"] = "chords" if track["plays"] == "chords" else steps_text(spec)
        track["volume"] = volume if isinstance(volume, (int, float)) and not isinstance(volume, bool) else None
        track["pan"] = spec.get("pan", 0)
        track["settings"] = dict(spec.get("settings") or {})
        track["kind"] = by_name[track["name"]].instrument.kind
        track["levels"] = {name: _step_levels(part) for name, part in by_name[track["name"]].parts.items()}
    raw_sections = data.get("sections") if isinstance(data.get("sections"), list) else None
    for k, section in enumerate(outline["sections"]):
        found = score.sections[k]
        section["first_bar"] = found.first_bar + 1
        item = raw_sections[k] if raw_sections is not None else {}
        own = isinstance(item, Mapping) and "progression" in item
        section["own_progression"] = own
        section["progression"] = analyse_progression(item["progression"] if own else data.get("progression"), found.key)
        section["chord_seconds"] = [round(c.length / RATE, 3) for c in found.chords]
    outline["sections_written"] = raw_sections is not None
    outline["progression"] = analyse_progression(data.get("progression"), score.key)
    outline["description"] = score.description
    outline["bar_seconds"] = round(score.bar / RATE, 6)
    outline["steps_per_bar"] = steps_per_bar(score.time)
    return outline


# ----- new tracks -----------------------------------------------------------------------------


def steps_per_bar(time: tuple[int, int]) -> int:
    """The steps of a bar in sixteenths (``4/4`` 16, ``3/4`` 12, ``6/8`` 12)."""
    return time[0] * 16 // time[1]


def default_steps(instrument: str, kind: str, time: tuple[int, int]) -> str | None:
    """A sensible first pattern for a new track of ``instrument`` (``None``: a pad holds the
    chords): one bar of sixteenths in groups of a beat."""
    beats, per = time[0], max(16 // time[1], 1)  # steps per beat: 4 in x/4, 2 in x/8

    def beat_cells(make: Any) -> str:
        return " ".join(make(b) for b in range(beats))

    def arpeggio(b: int) -> str:  # the plucks: a broken chord in eighths, 1 3 5 8
        if per < 2:
            return "1358"[b % 4]
        half = per // 2
        return "1358"[(2 * b) % 4] + "." * (half - 1) + "1358"[(2 * b + 1) % 4] + "." * (per - half - 1)

    if kind == "pad":
        return None
    rest = "." * (per - 1)
    hold = "-" * (per - 1)
    patterns = {
        "kick": lambda b: "x" + rest,
        "clap": lambda b: ("x" if b % 2 else ".") + rest,
        "gated_snare": lambda b: ("x" if b % 2 else ".") + rest,
        "snap": lambda b: ("x" if b % 2 else ".") + rest,
        "hat": lambda b: (".." + "x" + "." * (per - 3)) if per >= 4 else "x" + rest,
        "open_hat": lambda b: (".." + ("x" if b % 2 else ".") + "." * (per - 3)) if per >= 4 else "x" + rest,
        "tick": lambda b: ("o." * (per // 2)) or "o",
        "boom": lambda b: ("x" if b == 0 else ".") + rest,
        "pulsar": lambda b: ("x" if b == 0 else ".") + rest,
        "static": lambda b: ("o" if b == 0 else ".") + rest,
        "riser": lambda b: ("x" if b == 0 else "-") + hold,
        "sub": lambda b: ("1" if b == 0 else "-") + hold,
        "synth_bass": lambda b: ("1" if b % 2 == 0 else ".") + rest,
        "analog_bass": lambda b: ("1" if b % 2 == 0 else ".") + rest,
        "piano": lambda b: ("*" if b % 2 == 0 else "-") + hold,
        "soft_lead": lambda b: ("531-"[b % 4] if b < beats - 1 else "-") + hold,
        "music_box": lambda b: "5385"[b % 4] + rest,
        "bell": lambda b: ("5" if b == 0 else ".") + rest,
        "woodblock": lambda b: "1" + rest,
    }
    return beat_cells(patterns.get(instrument, arpeggio))


def free_name(base: str, taken: set[str]) -> str:
    """``base``, or ``base_2``, ``base_3``... the first not in ``taken``."""
    if base not in taken:
        return base
    k = 2
    while f"{base}_{k}" in taken:
        k += 1
    return f"{base}_{k}"


def add_track(data: Mapping[str, Any], score: Any, instrument: str, name: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """The edits that add a track of ``instrument`` at the end of the tracks, with a default
    pattern (a pad holds the chords; a riser plays only in the last section), and its label."""
    from vidgen.studio import INSTRUMENTS

    found = INSTRUMENTS.get(instrument)
    if found is None:
        import difflib

        close = difflib.get_close_matches(instrument, list(INSTRUMENTS), n=1, cutoff=0.6)
        hint = f"; did you mean '{close[0]}'?" if close else ""
        raise VidgenError(f"add track: unknown instrument '{instrument}'{hint} (instruments: {', '.join(INSTRUMENTS)})")
    taken = set((data.get("tracks") or {}).keys())
    if name is not None and (not NAME.match(name) or name in taken):
        raise VidgenError(f"add track: {name!r} is taken or not a name (lower-case letters, digits and _)")
    name = name or free_name(instrument, taken)
    spec: dict[str, Any] = {"instrument": instrument}
    steps = default_steps(instrument, found.kind, score.time)
    if steps is None:
        spec["play"] = "chords"
    else:
        spec["steps"] = steps
    if instrument == "riser" and len(score.sections) > 1:
        spec["only"] = [score.sections[-1].name]
    spec["volume"] = NEW_TRACK_VOLUME
    return [{"op": "set", "path": f"tracks.{name}", "value": spec}], f"+ track {name} ({instrument})"


def delete_track(data: Mapping[str, Any], name: str) -> tuple[list[dict[str, Any]], str]:
    tracks = data.get("tracks") or {}
    if name not in tracks:
        raise VidgenError(f"delete track: no track '{name}'")
    if len(tracks) == 1:
        raise VidgenError("delete track: a score needs at least one track")
    return [{"op": "delete", "path": f"tracks.{name}"}], f"− track {name}"


# ----- sections -------------------------------------------------------------------------------


def _section_list(data: Mapping[str, Any], what: str) -> list[Any]:
    sections = data.get("sections")
    if not isinstance(sections, list):
        raise VidgenError(f"{what}: this score gives its length as bars, not a list of sections; write sections: [...] in the score file first")
    return sections


def _section_index(sections: list[Any], name: str, what: str) -> int:
    for k, item in enumerate(sections):
        if isinstance(item, Mapping) and item.get("name") == name:
            return k
    raise VidgenError(f"{what}: no section '{name}'")


def _names(value: Any) -> list[str] | None:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else None


def add_section(data: Mapping[str, Any], after: int | None, name: str | None = None, bars: int = 4) -> tuple[list[dict[str, Any]], str]:
    """The edits that add a section of ``bars`` bars after section ``after`` (``None``: at the
    end). Without a score progression it takes the chords of the section before it."""
    sections = _section_list(data, "add section")
    taken = {str(s.get("name")) for s in sections if isinstance(s, Mapping)}
    if name is not None and (not NAME.match(name) or name in taken):
        raise VidgenError(f"add section: {name!r} is taken or not a name (lower-case letters, digits and _)")
    name = name or free_name("part", taken)
    index = len(sections) if after is None else max(0, min(after + 1, len(sections)))
    item: dict[str, Any] = {"name": name, "bars": int(bars)}
    before = sections[index - 1] if index > 0 else sections[0]
    if "progression" not in data and isinstance(before, Mapping) and "progression" in before:
        item["progression"] = before["progression"]
        if "chord_bars" in before:
            item["chord_bars"] = before["chord_bars"]
    ops: list[dict[str, Any]] = [{"op": "insert", "path": "sections", "index": index, "value": item}]
    for track, spec in (data.get("tracks") or {}).items():
        # a track whose steps are all written per section has none for the new one: it rests there
        if isinstance(spec, Mapping) and "only" not in spec and "steps" not in spec and spec.get("play") != "chords":
            listed = _names(spec.get("rest")) or []
            ops.append({"op": "set", "path": f"tracks.{track}.rest", "value": [*listed, name]})
    return ops, f"+ section {name} ({bars} bars)"


def remove_section(data: Mapping[str, Any], name: str) -> tuple[list[dict[str, Any]], str]:
    """The edits that remove section ``name`` and every mention of it in the tracks (``rest``,
    ``only``, per-section changes); a track that plays only there goes with it (the label says
    so; the version before keeps it). Refused when it is the only section, or when every track
    plays only there."""
    sections = _section_list(data, "remove section")
    index = _section_index(sections, name, "remove section")
    if len(sections) == 1:
        raise VidgenError("remove section: a score needs at least one section")
    tracks = data.get("tracks") or {}
    gone = [t for t, spec in tracks.items() if isinstance(spec, Mapping) and _names(spec.get("only")) == [name]]
    if len(gone) == len(tracks):
        raise VidgenError(f"remove section: every track plays only in '{name}'")
    ops: list[dict[str, Any]] = [{"op": "delete", "path": f"sections[{index}]"}]
    ops += [{"op": "delete", "path": f"tracks.{t}"} for t in gone]
    for track, spec in tracks.items():
        if not isinstance(spec, Mapping) or track in gone:
            continue
        for field in ("only", "rest"):
            listed = _names(spec.get(field))
            if listed is None or name not in listed:
                continue
            left = [n for n in listed if n != name]
            path = f"tracks.{track}.{field}"
            ops.append({"op": "delete", "path": path} if not left else {"op": "set", "path": path, "value": left})
        changes = spec.get("sections")
        if isinstance(changes, Mapping) and name in changes:
            path = f"tracks.{track}.sections"
            ops.append({"op": "delete", "path": f"{path}.{name}"} if len(changes) > 1 else {"op": "delete", "path": path})
    also = f" (and track{'s' if len(gone) > 1 else ''} {', '.join(gone)}, which played only there)" if gone else ""
    return ops, f"− section {name}{also}"


def rename_section(data: Mapping[str, Any], name: str, to: str) -> tuple[list[dict[str, Any]], str]:
    """The edits that rename section ``name`` to ``to`` everywhere it is named."""
    sections = _section_list(data, "rename section")
    index = _section_index(sections, name, "rename section")
    if not isinstance(to, str) or not NAME.match(to):
        raise VidgenError(f"rename section: {to!r} is not a name: lower-case letters, digits and _ (e.g. intro, lift_2)")
    if to == name:
        return [], ""
    if any(isinstance(s, Mapping) and s.get("name") == to for s in sections):
        raise VidgenError(f"rename section: there is already a section '{to}'")
    ops: list[dict[str, Any]] = [{"op": "set", "path": f"sections[{index}].name", "value": to}]
    for track, spec in (data.get("tracks") or {}).items():
        if not isinstance(spec, Mapping):
            continue
        for field in ("only", "rest"):
            value = spec.get(field)
            listed = _names(value)
            if listed is not None and name in listed:
                renamed = [to if n == name else n for n in listed]
                ops.append({"op": "set", "path": f"tracks.{track}.{field}", "value": renamed[0] if isinstance(value, str) else renamed})
        changes = spec.get("sections")
        if isinstance(changes, Mapping) and name in changes:
            ops.append({"op": "rename", "path": f"tracks.{track}.sections.{name}", "to": to})
    return ops, f"section {name} → {to}"
