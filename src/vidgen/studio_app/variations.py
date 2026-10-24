"""Variations (DESIGN.md §94.17): four siblings of a version, each a different, musically sensible
kind of change, made by fixed edits of its score text — the same text and shuffle counter always
give the same four (no random numbers).

The operators are pure functions of the parsed score (``data`` as read from YAML and the checked
``score``) returning value edits (:mod:`vidgen.studio_app.edits`: the comments and layout stay)
and a short label in words ("darker mix: pad tone 1800 → 1260, hat −2 dB"). They come in four
kinds, and a batch takes one of each kind that changes something for the piece (more of the
others when a kind has nothing to offer):

- **harmony**: the chords re-voiced (each chord's lowest note an octave up, or the top one down),
  one chord substituted by a relative in the same key, one chord in first inversion, another seed
  (the pads' phases and the reverbs' tails);
- **pattern**: the busiest figure (ostinato, arpeggio) turned by a step, its degrees swapped, its
  accents regrouped (3+3+2 ↔ 4+4+2+3+3), ghost notes on the hat or its soft hits taken out;
- **mix**: darker or brighter (the master low-pass, the pads' tone, the hats' level), the lead
  forward or back against the pads;
- **energy**: a sparser intro (the drums rest in the first section), a stronger lift (its drums
  louder or the pads opening there), the drums building in, the pad breathing over the loop.

Tempo is never changed (a tempo whose piece length has a large prime factor makes every FFT of
the renderer several times slower, §94.14), nor the key.

The studio renders and checks each candidate in the background (:class:`VariationBatches`):
``variations/<batch>/batch.json`` and ``<letter>.yaml``. Keeping one makes it the next version
(``origin: variation``, its parent the version varied); the others never become versions.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidgen.errors import VidgenError
from vidgen.fileio import write_text_atomic
from vidgen.studio.patterns import _TOKEN, accent_steps
from vidgen.studio_app.edits import apply_edits

#: ``batch.json``'s ``format``.
BATCH_FORMAT = 1
#: The kinds of change, in the order a batch shows them.
KINDS = ("harmony", "pattern", "mix", "energy")
#: Candidates per batch and their letters.
LETTERS = ("a", "b", "c", "d")
#: A batch id: ``b0001``.
BATCH_ID = re.compile(r"^b[0-9]{4}\Z")
#: The most shuffles a page may ask for (a counter, not a seed).
MAX_SHUFFLE = 999

#: Drums that make the groove (not effects such as a riser, a boom or static).
FX_DRUMS = ("riser", "boom", "static")
HAT_DRUMS = ("hat", "open_hat", "tick")
BASS_INSTRUMENTS = ("synth_bass", "sub", "analog_bass")
#: Section names that mean the piece's peak.
PEAK_NAMES = ("lift", "drop", "release", "chorus", "peak", "climax")

#: Chord substitutes in the same key (a numeral → a chord sharing two of its tones).
SUBSTITUTES = {
    "minor": {"VI": "iv", "iv": "VI", "VII": "v", "v": "VII", "III": "v", "i": "VI"},
    "major": {"IV": "ii", "ii": "IV", "V": "iii", "iii": "V", "vi": "IV", "I": "vi"},
}
#: Degree swaps tried on a figure, in order.
DEGREE_SWAPS = (({"3": "5", "5": "3"}, "3rds and 5ths swapped"), ({"5": "8", "8": "5"}, "5ths and octaves swapped"),
                ({"v2": "v3", "v3": "v2"}, "voicing notes 2 and 3 swapped"), ({"1": "8", "8": "1"}, "roots and octaves swapped"))
#: Accent groupings offered, in order (each must fill the figure's bars).
ACCENTS = ("3+3+2", "4+4+2+3+3", "3+3+3+3+4", "2+2+3+3+2+2+2", "4")

_ROMAN = re.compile(r"^([b#]?)(VII|VI|V|IV|III|II|I|vii|vi|v|iv|iii|ii|i)(.*)$")
_CHORD_TOKEN = re.compile(r"[^\s|,]+")
_NOTE = re.compile(r"^([A-G][#b]?)(\d)$")


@dataclass(frozen=True)
class Variation:
    """One candidate: its ``kind`` (:data:`KINDS`), the operator's ``name``, a ``label`` in
    words and the value edits that make it from the base text."""

    kind: str
    name: str
    label: str
    ops: tuple[dict[str, Any], ...]


@dataclass
class Piece:
    """The score being varied: its text, data (from YAML) and the checked score."""

    text: str
    data: dict[str, Any]
    score: Any
    tracks: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.tracks = {t.name: t for t in self.score.tracks}

    def spec(self, name: str) -> dict[str, Any]:
        raw = (self.data.get("tracks") or {}).get(name)
        return raw if isinstance(raw, dict) else {}

    @property
    def minor(self) -> bool:
        return self.score.key.mode in ("minor", "dorian", "phrygian")


# ----- small helpers --------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _db(delta: float) -> str:
    text = f"{delta:+.1f}".rstrip("0").rstrip(".")
    return text.replace("-", "−") + " dB"


def _round_hz(value: float) -> float:
    step = 10 if value < 1000 else 50
    return float(round(value / step) * step)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _num_text(value: float) -> str:
    return f"{value:g}"


def _names(names: Sequence[str]) -> str:
    return ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")


def _where_words(piece: Piece, path: str) -> str:
    """``sections[2].progression[1]`` → "the lift's chords"; ``progression`` → "the progression"."""
    m = re.match(r"sections\[(\d+)\]", path)
    if m is None:
        return "the progression"
    return f"the {piece.score.sections[int(m[1])].name}'s chords"


def _octave(note: str, by: int) -> str | None:
    """A note name an octave ``by`` up or down, its spelling kept (``G2`` → ``G3``)."""
    m = _NOTE.match(note)
    if m is None or not 0 <= int(m[2]) + by <= 8:
        return None
    return f"{m[1]}{int(m[2]) + by}"


def _midi(note: str) -> int:
    from vidgen.studio.theory import note_number

    return note_number(note)


def _plays(piece: Piece, track: str, section: str) -> bool:
    return section in piece.tracks[track].parts


def _beat_drums(piece: Piece) -> list[str]:
    return [t.name for t in piece.score.tracks if t.instrument.kind == "drum" and t.instrument.name not in FX_DRUMS]


def _is_bass(track: Any) -> bool:
    """A bass line: named so, a sub, or a bass instrument kept in octave 2 or lower (an
    ostinato on a synth bass in octave 3 is a figure, not the bass)."""
    if "bass" in track.name or track.instrument.name == "sub":
        return True
    octaves = [p.octave for p in track.parts.values()]
    return track.instrument.name in BASS_INSTRUMENTS and all(o is not None and o <= 2 for o in octaves)


def _verb(names: Sequence[str], one: str, many: str) -> str:
    return one if len(names) == 1 else many


def _pads(piece: Piece) -> list[Any]:
    return [t for t in piece.score.tracks if t.instrument.kind == "pad" and t.play_chords]


def _plain(spec: Mapping[str, Any]) -> float | None:
    from vidgen.studio_app.stems import plain_volume

    return plain_volume(spec)


# ----- step patterns ----------------------------------------------------------------------------


def step_cells(text: str) -> list[list[tuple[int, int]]]:
    """The steps text's cells as ``(start, end)`` spans, bar by bar (a ``+`` stack is one cell),
    read with the score's own tokens."""
    bars: list[list[tuple[int, int]]] = [[]]
    pos, joining = 0, False
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise VidgenError(f"variations: cannot read the steps {text!r}")
        pos = m.end()
        if m["space"]:
            continue
        if m["bar"]:
            bars.append([])
        elif m["plus"]:
            joining = True
        elif joining and bars[-1]:
            bars[-1][-1] = (bars[-1][-1][0], m.end())
            joining = False
        else:
            bars[-1].append((m.start(), m.end()))
    return bars


def _rewrite(text: str, spans: Sequence[tuple[int, int]], new: Sequence[str]) -> str:
    out, at = [], 0
    for (start, end), value in sorted(zip(spans, new)):
        out.append(text[at:start])
        out.append(value)
        at = end
    return "".join(out) + text[at:]


def rotate_steps(text: str, by: int) -> str:
    """Each bar's cells turned ``by`` steps to the left (what played on step 2 plays on step 1);
    spacing, ``|`` and the cells' places stay."""
    spans, new = [], []
    for bar in step_cells(text):
        cells = [text[a:b] for a, b in bar]
        k = by % len(cells) if cells else 0
        spans += bar
        new += cells[k:] + cells[:k]
    return _rewrite(text, spans, new)


def map_tokens(text: str, mapping: Mapping[str, str]) -> str:
    """Degrees (``3``) and voicing notes (``v2``) replaced by ``mapping``, their octave marks
    and accents kept."""
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise VidgenError(f"variations: cannot read the steps {text!r}")
        piece = m.group(0)
        if m["degree"] and m["degree"] in mapping:
            piece = mapping[m["degree"]] + piece[1:]
        elif m["voice"] and f"v{m['voice']}" in mapping:
            piece = mapping[f"v{m['voice']}"] + piece[2:]
        out.append(piece)
        pos = m.end()
    return "".join(out)


def _sounding(text: str) -> tuple[int, int]:
    """(sounding cells, bars) of a steps text."""
    bars = step_cells(text)
    return sum(1 for bar in bars for a, b in bar if text[a:b] not in (".", "-")), len(bars)


def _steps_strings(spec: Mapping[str, Any]) -> list[str] | None:
    steps = spec.get("steps")
    if isinstance(steps, str):
        return [steps]
    if isinstance(steps, list) and steps and all(isinstance(s, str) for s in steps):
        return list(steps)
    return None


def _steps_ops(track: str, spec: Mapping[str, Any], change: Callable[[str], str]) -> tuple[list[dict[str, Any]], str, str] | None:
    """Edits writing ``change`` of each of the track's steps strings (one edit per list item, so a
    block list keeps its layout); the first bar before and after, for the label."""
    strings = _steps_strings(spec)
    if strings is None:
        return None
    ops = []
    for k, s in enumerate(strings):
        new = change(s)
        if new != s:
            path = f"tracks.{track}.steps" if isinstance(spec.get("steps"), str) else f"tracks.{track}.steps[{k}]"
            ops.append({"op": "set", "path": path, "value": new})
    if not ops:
        return None
    return ops, _first_bar(strings[0]), _first_bar(change(strings[0]))


def _first_bar(text: str) -> str:
    bar = step_cells(text)[0]
    cells = [text[a:b] for a, b in bar]
    joined = " ".join(cells[:8])
    return joined + (" …" if len(cells) > 8 else "")


def _figure(piece: Piece) -> str | None:
    """The busiest pitched figure with its own steps (an ostinato or arpeggio): degrees or
    voicing notes before note names, then the most notes per bar (at least four)."""
    best: tuple[tuple[int, float], str] | None = None
    for t in piece.score.tracks:
        if t.instrument.kind == "drum" or t.play_chords or _is_bass(t):
            continue
        strings = _steps_strings(piece.spec(t.name))
        if strings is None:
            continue
        sounding = [_sounding(s) for s in strings]
        per_bar = sum(n for n, _ in sounding) / max(1, sum(b for _, b in sounding))
        relative = any(re.search(r"(?<![A-G#b])[1-9]|v[1-9]", s) for s in strings)
        if per_bar < 4:
            continue
        rank = (int(relative), per_bar)
        if best is None or rank > best[0]:
            best = (rank, t.name)
    return best[1] if best else None


# ----- harmony ----------------------------------------------------------------------------------


def _progressions(piece: Piece) -> list[tuple[str, Any]]:
    """Every progression of the score as ``(path, value)``: the score's, then each section's."""
    out = []
    if "progression" in piece.data:
        out.append(("progression", piece.data["progression"]))
    for k, s in enumerate(piece.data.get("sections") or []):
        if isinstance(s, Mapping) and "progression" in s:
            out.append((f"sections[{k}].progression", s["progression"]))
    return out


def revoice(piece: Piece, v: int) -> Variation | None:
    """The written voicings (``{chord, notes}``) re-voiced: each chord's lowest note an octave up
    (``v`` 0) or its top note an octave down (``v`` 1)."""
    if v > 1:
        return None
    ops, example = [], None
    for path, value in _progressions(piece):
        if not isinstance(value, list):
            continue
        for k, item in enumerate(value):
            if not isinstance(item, Mapping) or not isinstance(item.get("notes"), list) or len(item["notes"]) < 3:
                continue
            notes = [str(n) for n in item["notes"]]
            try:
                order = sorted(notes, key=_midi)
            except VidgenError:
                continue
            moved = order[0] if v == 0 else order[-1]
            to = _octave(moved, 1 if v == 0 else -1)
            if to is None:
                continue
            new = sorted([n for n in notes if n is not moved] + [to], key=_midi)
            if len({_midi(n) for n in new}) < len(new):  # the moved note doubles another: leave the chord
                continue
            ops.append({"op": "set", "path": f"{path}[{k}].notes", "value": new})
            example = example or f"{item.get('chord')}: {moved} → {to}"
    if not ops:
        return None
    words = "each chord's lowest note an octave up" if v == 0 else "each chord's top note an octave down"
    return Variation("harmony", "revoice", f"chords re-voiced: {words} ({example})", tuple(ops))


def _numeral_spots(piece: Piece) -> list[tuple[str, Any, int, re.Match[str], re.Match[str]]]:
    """Every Roman numeral of the progressions written as text (or as plain items of a list):
    ``(path, value, index in the string list, token match, numeral match)``."""
    out = []
    for path, value in _progressions(piece):
        strings = [(path, value, -1)] if isinstance(value, str) else [(f"{path}[{k}]", s, k) for k, s in enumerate(value) if isinstance(s, str)] if isinstance(value, list) else []
        for where, text, k in strings:
            for m in _CHORD_TOKEN.finditer(text):
                roman = _ROMAN.match(m.group(0))
                if roman is not None:
                    out.append((where, text, k, m, roman))
    return out


def _chord_name(symbol: str, piece: Piece) -> str:
    from vidgen.studio.theory import parse_chord

    try:
        return parse_chord(symbol, piece.score.key).name
    except VidgenError:
        return symbol


def _replace_token(where: str, text: str, m: re.Match[str], new: str) -> dict[str, Any]:
    return {"op": "set", "path": where, "value": text[: m.start()] + new + text[m.end() :]}


def substitute(piece: Piece, v: int) -> Variation | None:
    """One chord of a progression written in numerals replaced by a relative in the same key
    (``VII`` → ``v``: two tones shared), not the first chord; ``v`` picks which (from the last)."""
    table = SUBSTITUTES["minor" if piece.minor else "major"]
    spots = [s for s in _numeral_spots(piece) if s[3].start() > 0 or s[2] > 0]
    spots = [s for s in spots if not s[4][1] and s[4][2] in table and "/" not in s[4][3]]
    if v >= len(spots):
        return None
    where, text, _, m, roman = spots[::-1][v]
    new = table[roman[2]]
    old_name, new_name = _chord_name(m.group(0), piece), _chord_name(new, piece)
    return Variation("harmony", "substitute", f"a chord substituted: {m.group(0)} → {new} ({old_name} → {new_name}) in {_where_words(piece, where)}",
                     (_replace_token(where, text, m, new),))


def invert(piece: Piece, v: int) -> Variation | None:
    """One chord of a numeral progression in first inversion (``VI`` → ``VI/3``: its third in
    the bass, a smoother bass line), not the first chord; ``v`` picks which (from the last)."""
    from vidgen.studio.theory import parse_chord

    spots = []
    for s in _numeral_spots(piece):
        if (s[3].start() == 0 and s[2] <= 0) or "/" in s[3].group(0):
            continue
        try:
            chord = parse_chord(s[3].group(0), piece.score.key)
            parse_chord(s[3].group(0) + "/3", piece.score.key)
        except VidgenError:
            continue
        if 3 in chord.intervals or 4 in chord.intervals:  # a real third (not a sus chord's 2nd or 4th)
            spots.append(s)
    if v >= len(spots):
        return None
    where, text, _, m, _ = spots[::-1][v]
    new = m.group(0) + "/3"
    return Variation("harmony", "invert", f"a chord inverted: {m.group(0)} → {new} ({_chord_name(new, piece)}) in {_where_words(piece, where)}, its third in the bass",
                     (_replace_token(where, text, m, new),))


def reseed(piece: Piece, v: int) -> Variation | None:
    """Another seed, when the score uses it (a pad's phases, a reverb's tail)."""
    uses = _pads(piece) or any(p.reverb is not None for t in piece.score.tracks for p in t.parts.values())
    if not uses or v > 2:
        return None
    seed = int(piece.score.seed)
    new = seed + 1 + v
    return Variation("harmony", "reseed", f"another seed: {seed} → {new} (the pads' phases and noises, the same notes)",
                     ({"op": "set", "path": "seed", "value": new},))


# ----- pattern ----------------------------------------------------------------------------------


def _figure_change(piece: Piece, name: str, label: str, change: Callable[[str], str]) -> Variation | None:
    track = _figure(piece)
    if track is None:
        return None
    found = _steps_ops(track, piece.spec(track), change)
    if found is None:
        return None
    ops, before, after = found
    return Variation("pattern", name, f"{track} {label}: {before} → {after}", tuple(ops))


def rotate(piece: Piece, v: int) -> Variation | None:
    """The figure turned by 1, 2 or 3 steps (``v``): the same notes, the accents on others."""
    if v > 2:
        return None
    by = v + 1
    return _figure_change(piece, "rotate", f"turned by {by} step{'s' if by > 1 else ''}", lambda s: rotate_steps(s, by))


def swap_degrees(piece: Piece, v: int) -> Variation | None:
    """The figure's chord degrees swapped (3rds ↔ 5ths, 5ths ↔ octaves...): the ``v``-th swap
    that changes it."""
    track = _figure(piece)
    if track is None:
        return None
    useful = []
    for mapping, words in DEGREE_SWAPS:
        found = _steps_ops(track, piece.spec(track), lambda s, m=mapping: map_tokens(s, m))  # type: ignore[misc]
        if found is not None:
            useful.append((found, words))
    if v >= len(useful):
        return None
    (ops, before, after), words = useful[v]
    return Variation("pattern", "degrees", f"{track}: {words}: {before} → {after}", tuple(ops))


def reaccent(piece: Piece, v: int) -> Variation | None:
    """The figure's accents regrouped (3+3+2 ↔ 4+4+2+3+3...): the ``v``-th grouping that fills
    its bars and differs from the one written."""
    from vidgen.studio.patterns import parse_accent

    track = _figure(piece)
    if track is None:
        return None
    part = next(iter(piece.tracks[track].parts.values()))
    if part.steps is None:
        return None
    lengths = {len(bar) for bar in part.steps}
    current = "+".join(map(str, part.accent)) if part.accent else None
    options = [a for a in ACCENTS if a != current and all(accent_steps(parse_accent(a, "accent"), n) is not None for n in lengths)]
    if v >= len(options):
        return None
    new = options[v]
    spec = piece.spec(track)
    if "sections" in spec and any(isinstance(c, Mapping) and "accent" in c for c in spec["sections"].values()):
        return None
    words = f"{current} → {new}" if current else f"accented {new}"
    return Variation("pattern", "accent", f"{track} re-accented: {words}", ({"op": "set", "path": f"tracks.{track}.accent", "value": new},))


def hat_touch(piece: Piece, v: int) -> Variation | None:
    """The hat with soft ghost notes on its free off-sixteenths (``v`` 0), or its soft hits taken
    out (``v`` 1)."""
    if v > 1:
        return None
    for t in piece.score.tracks:
        if t.instrument.name not in HAT_DRUMS:
            continue
        spec = piece.spec(t.name)

        def ghost(text: str) -> str:
            spans, new = [], []
            for bar in step_cells(text):
                if len(bar) < 8:
                    continue
                for k, (a, b) in enumerate(bar):
                    if k % 2 == 1 and text[a:b] == "." and (k + 1 >= len(bar) or text[slice(*bar[k + 1])] != "-"):
                        spans.append((a, b))
                        new.append("o")
            return _rewrite(text, spans, new)

        def thin(text: str) -> str:
            spans = [(a, b) for bar in step_cells(text) for a, b in bar if text[a:b] == "o"]
            out = _rewrite(text, spans, ["."] * len(spans))
            return out if _sounding(out)[0] > 0 else text

        found = _steps_ops(t.name, spec, ghost if v == 0 else thin)
        if found is not None:
            ops, before, after = found
            words = "ghost notes on the free off-sixteenths" if v == 0 else "its soft hits taken out"
            return Variation("pattern", "hat", f"{t.name}: {words}: {before} → {after}", tuple(ops))
    return None


# ----- mix ----------------------------------------------------------------------------------------


def tone(piece: Piece, v: int) -> Variation | None:
    """A darker (``v`` even) or brighter (odd) mix: the master low-pass, the pads' tone and the
    hats' level; the other way when one has no room."""
    from vidgen.studio.score_file import DEFAULT_LOWPASS

    if v > 1:
        return None
    for darker in ((v == 0, v != 0)):
        ops, words = [], []
        master = piece.data.get("master") if isinstance(piece.data.get("master"), Mapping) else {}
        low = _number(master.get("lowpass")) or DEFAULT_LOWPASS
        new_low = _round_hz(min(low * 0.72, 6000) if darker else low * 1.4)
        new_low = _clamp(new_low, 1000, 16000)
        if (darker and new_low < low - 1) or (not darker and low < 12000 and new_low > low + 1):
            ops.append({"op": "set", "path": "master.lowpass", "value": new_low})
            words.append(f"master low-pass {_num_text(low)} → {_num_text(new_low)}")
        for pad in _pads(piece):
            setting = pad.instrument.settings.get("tone")
            if setting is None:
                continue
            spec = piece.spec(pad.name)
            given = spec.get("settings", {}).get("tone") if isinstance(spec.get("settings"), Mapping) else None
            now = _number(given) if given is not None else setting.default
            if now is None:
                continue
            new = _clamp(_round_hz(now * (0.7 if darker else 1.4)), setting.low, setting.high)
            if abs(new - now) >= 1:
                ops.append({"op": "set", "path": f"tracks.{pad.name}.settings.tone", "value": new})
                words.append(f"{pad.name} tone {_num_text(now)} → {_num_text(new)}")
        for t in piece.score.tracks:
            if t.instrument.name in HAT_DRUMS:
                volume = _plain(piece.spec(t.name))
                if volume is not None:
                    delta = -2.0 if darker else 1.5
                    ops.append({"op": "set", "path": f"tracks.{t.name}.volume", "value": round(volume + delta, 2)})
                    words.append(f"{t.name} {_db(delta)}")
                    break
        if ops and (len(ops) > 1 or not ops[0]["path"].endswith("volume")):
            name = "darker" if darker else "brighter"
            return Variation("mix", name, f"{name} mix: {', '.join(words)}", tuple(ops))
    return None


def _lead(piece: Piece) -> Any | None:
    """The top voice: a pitched track that is no pad or bass, with its own plain volume, playing
    the highest notes by its octave (a written-out tune ranks first)."""
    best = None
    for t in piece.score.tracks:
        if t.instrument.kind != "note" or _is_bass(t) or _plain(piece.spec(t.name)) is None:
            continue
        octave = max((p.octave or 0) for p in t.parts.values()) if t.parts else 0
        strings = _steps_strings(piece.spec(t.name)) or []
        notes = [int(n) for s in strings for n in re.findall(r"[A-G][#b]?(\d)", s)]
        rank = (max(notes) if notes else octave, len(t.parts))
        if best is None or rank > best[0]:
            best = (rank, t)
    return best[1] if best else None


def balance(piece: Piece, v: int) -> Variation | None:
    """The lead forward and the pads back (``v`` 0), or the other way (``v`` 1)."""
    if v > 1:
        return None
    lead = _lead(piece)
    pads = [p for p in _pads(piece) if _plain(piece.spec(p.name)) is not None]
    if lead is None or not pads:
        return None
    up, down = (2.5, -2.0) if v == 0 else (-2.5, 1.5)
    ops = [{"op": "set", "path": f"tracks.{lead.name}.volume", "value": round(_plain(piece.spec(lead.name)) + up, 2)}]  # type: ignore[operator]
    for p in pads:
        ops.append({"op": "set", "path": f"tracks.{p.name}.volume", "value": round(_plain(piece.spec(p.name)) + down, 2)})  # type: ignore[operator]
    words = f"{lead.name} forward" if v == 0 else f"{lead.name} back"
    return Variation("mix", "balance", f"{words}: {lead.name} {_db(up)}, {_names([p.name for p in pads])} {_db(down)}", tuple(ops))


# ----- energy -------------------------------------------------------------------------------------


def _rest_ops(piece: Piece, tracks: Sequence[str], section: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Edits making ``tracks`` rest in ``section`` one by one, each kept only when the score stays
    valid (a hold into the next section needs the note before it)."""
    from vidgen.studio_app.app import check_text
    from vidgen.studio_app.inspector import set_section_plays

    text, data = piece.text, piece.data
    ops: list[dict[str, Any]] = []
    done = []
    for name in tracks:
        try:
            more, _, _ = set_section_plays(data, name, section, False)
        except VidgenError:
            continue
        if not more:
            continue
        try:
            new_text = apply_edits(text, more)
        except VidgenError:
            continue
        new_data, score, _ = check_text(new_text)
        if score is None:
            continue
        text, data = new_text, new_data
        ops += more
        done.append(name)
    return ops, done


def sparser_intro(piece: Piece, v: int) -> Variation | None:
    """The drums (``v`` 0; and the bass, ``v`` 1) rest in the first section, when it is at most
    half the piece and something pitched still plays there."""
    if v > 1 or len(piece.score.sections) < 2:
        return None
    first = piece.score.sections[0]
    if first.bars * 2 > piece.score.bars:
        return None
    playing = [t for t in piece.score.tracks if first.name in t.parts]
    drums = [t.name for t in playing if t.name in _beat_drums(piece)]
    basses = [t.name for t in playing if t.instrument.kind != "drum" and _is_bass(t)]
    chosen = drums + (basses if v == 1 else [])
    if not chosen or (v == 1 and not basses) or not [t for t in playing if t.name not in chosen and t.instrument.kind != "drum"]:
        return None
    ops, done = _rest_ops(piece, chosen, first.name)
    if not ops:
        return None
    return Variation("energy", "intro", f"sparser {first.name}: {_names(done)} {_verb(done, 'rests', 'rest')} there", tuple(ops))


def _peak(piece: Piece) -> Any | None:
    """The piece's peak: a section named like one (lift, drop...), else the one where the most
    tracks play (the later one on a tie), never the first of several."""
    sections = piece.score.sections
    if len(sections) < 2:
        return None
    named = [s for s in sections if s.name in PEAK_NAMES or s.name.rstrip("0123456789_") in PEAK_NAMES]
    if named:
        return named[0]
    count = {s.name: sum(1 for t in piece.score.tracks if s.name in t.parts) for s in sections[1:]}
    return max(sections[1:], key=lambda s: (count[s.name], s.first_bar))


def stronger_lift(piece: Piece, v: int) -> Variation | None:
    """The peak section stronger: its drums +2 dB there (``v`` 0), or the pads opening there (tone
    ×1.5, ``v`` 1)."""
    peak = _peak(piece)
    if peak is None or v > 1:
        return None
    ops, names = [], []
    if v == 0:
        drums = [n for n in _beat_drums(piece) if _plays(piece, n, peak.name)]
        drums = [n for n in drums if piece.tracks[n].instrument.name not in HAT_DRUMS] or drums
        for name in drums:
            spec = piece.spec(name)
            own = spec.get("sections", {}).get(peak.name) if isinstance(spec.get("sections"), Mapping) else None
            now = _number(own.get("volume")) if isinstance(own, Mapping) and "volume" in own else (_number(spec.get("volume", 0)))
            if now is None or (isinstance(own, Mapping) and "volume" in own and _number(own["volume"]) is None):
                continue
            ops.append({"op": "set", "path": f"tracks.{name}.sections.{peak.name}.volume", "value": round(now + 2.0, 2)})
            names.append(name)
        if not ops:
            return None
        return Variation("energy", "lift", f"stronger {peak.name}: {_names(names)} +2 dB there", tuple(ops))
    for pad in _pads(piece):
        setting = pad.instrument.settings.get("tone")
        part = pad.parts.get(peak.name)
        if setting is None or part is None:
            continue
        now = part.settings["tone"]
        new = _clamp(_round_hz(now * 1.5), setting.low, setting.high)
        if new - now >= 1:
            ops.append({"op": "set", "path": f"tracks.{pad.name}.sections.{peak.name}.settings.tone", "value": new})
            names.append(f"{pad.name} tone {_num_text(now)} → {_num_text(new)}")
    if not ops:
        return None
    return Variation("energy", "lift", f"the {peak.name} opens up: {', '.join(names)} there", tuple(ops))


def _one_section(piece: Piece) -> int | None:
    """The bars of a score written with ``bars:`` (one section), else ``None``."""
    return int(piece.score.bars) if "sections" not in piece.data and len(piece.score.sections) == 1 else None


def build_in(piece: Piece, v: int) -> Variation | None:
    """In a one-section piece, the drums build in over its first half (a volume curve from 18 dB
    under to their level); ``v`` 1: the bass too."""
    bars = _one_section(piece)
    if bars is None or bars < 8 or v > 1:
        return None
    half = bars // 2
    chosen = [n for n in _beat_drums(piece) if _plain(piece.spec(n)) is not None]
    if v == 1:
        chosen += [t.name for t in piece.score.tracks if t.instrument.kind == "note" and _is_bass(t) and _plain(piece.spec(t.name)) is not None]
    if not chosen or len(chosen) == len(piece.score.tracks):
        return None
    ops = []
    for name in chosen:
        level = _plain(piece.spec(name))
        assert level is not None
        ops.append({"op": "set", "path": f"tracks.{name}.volume", "value": [[0, round(level - 18, 2)], [half, level]]})
    return Variation("energy", "build", f"{_names(chosen)} {_verb(chosen, 'builds', 'build')} in over bars 1–{half} (from 18 dB under)", tuple(ops))


def breathe(piece: Piece, v: int) -> Variation | None:
    """In a one-section piece, the pads dip 5 dB to the middle of the loop and come back."""
    bars = _one_section(piece)
    if bars is None or bars < 4 or v > 0:
        return None
    pads = [p for p in _pads(piece) if _plain(piece.spec(p.name)) is not None]
    if not pads:
        return None
    ops = []
    for p in pads:
        level = _plain(piece.spec(p.name))
        assert level is not None
        ops.append({"op": "set", "path": f"tracks.{p.name}.volume", "value": [[0, level], [bars // 2, round(level - 5, 2)], [bars, level]]})
    names = [p.name for p in pads]
    return Variation("energy", "breathe", f"{_names(names)} {_verb(names, 'breathes', 'breathe')}: −5 dB at bar {bars // 2 + 1} and back", tuple(ops))


#: The operators of each kind, in the order a batch tries them.
OPERATORS: dict[str, tuple[Callable[[Piece, int], Variation | None], ...]] = {
    "harmony": (revoice, substitute, invert, reseed),
    "pattern": (rotate, reaccent, swap_degrees, hat_touch),
    "mix": (tone, balance),
    "energy": (sparser_intro, stronger_lift, build_in, breathe),
}


# ----- choosing four ------------------------------------------------------------------------------


def _piece(text: str) -> Piece:
    from vidgen.studio_app.app import check_text

    data, score, problems = check_text(text)
    if score is None:
        p = problems[0]
        raise VidgenError(f"variations: the score has problems to fix first ({p['where']}: {p['message']})")
    return Piece(text, data, score)


#: Variants each operator may offer (``v`` 0, 1, 2).
VARIANTS = 3


def _candidates(piece: Piece, kind: str, shuffle: int) -> list[tuple[Variation, str]]:
    """Every valid candidate of ``kind`` with its text — each operator's first variant, then
    their second ones... — turned by ``shuffle``, so each shuffle starts from another one."""
    from vidgen.studio_app.app import check_text, render_key

    base_key = render_key(piece.data)
    out: list[tuple[Variation, str]] = []
    for v in range(VARIANTS):
        for op in OPERATORS[kind]:
            try:
                found = op(piece, v)
            except VidgenError:
                found = None
            if found is None:
                continue
            try:
                text = apply_edits(piece.text, found.ops)
            except VidgenError:
                continue
            data, score, _ = check_text(text)
            if score is None or render_key(data) == base_key or any(t == text for _, t in out):
                continue
            out.append((found, text))
    k = shuffle % len(out) if out else 0
    return out[k:] + out[:k]


def make_variations(text: str, shuffle: int = 0, first: str | None = None, count: int = 4) -> list[tuple[Variation, str]]:
    """Four (``count``) variations of score ``text`` with their texts: one of each kind that
    changes something (``first``: that kind first, for "more like this"), the others' next ones
    when a kind has none. The same text and ``shuffle`` always give the same ones."""
    if not 0 <= shuffle <= MAX_SHUFFLE:
        raise VidgenError(f"variations: shuffle is a counter from 0 to {MAX_SHUFFLE}")
    piece = _piece(text)
    kinds = list(KINDS)
    if first in kinds:
        kinds.remove(first)
        kinds.insert(0, first)
    pools = {k: _candidates(piece, k, shuffle) for k in kinds}
    chosen: list[tuple[Variation, str]] = []
    seen = {text}
    for round_ in range(max(len(p) for p in pools.values()) if pools else 0):
        for k in kinds:
            if len(chosen) < count and round_ < len(pools[k]) and pools[k][round_][1] not in seen:
                chosen.append(pools[k][round_])
                seen.add(pools[k][round_][1])
    return chosen


# ----- batches on disk and their background work ---------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class VariationBatches:
    """The session's variation batches (``variations/<batch>/``) and the one worker that renders
    and checks them. ``render(session, text)`` renders a candidate (its facts and timing) and
    ``check(session, text)`` checks it (the kept check's document); both are the studio's."""

    def __init__(self, render: Callable[[Any, str], dict[str, Any]], check: Callable[[Any, str, Callable[[], bool]], dict[str, Any] | None]) -> None:
        self._render = render
        self._check = check
        self._lock = threading.Lock()
        self._docs: dict[str, dict[str, Any]] = {}  # folder → batch doc (the running one is the truth)
        self._running: str | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    @staticmethod
    def folder(session: Any, batch: str) -> Path:
        if not BATCH_ID.match(batch):
            raise VidgenError(f"variations: not a batch id: {batch!r}")
        return session.folder / "variations" / batch

    def read(self, session: Any, batch: str) -> dict[str, Any]:
        """A batch's document (as the worker last wrote it)."""
        folder = self.folder(session, batch)
        with self._lock:
            doc = self._docs.get(str(folder))
            if doc is not None:
                return json.loads(json.dumps(doc))
        try:
            doc = json.loads((folder / "batch.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise VidgenError(f"variations: no batch {batch} in this session") from None
        if doc.get("state") == "running":  # written by a studio that stopped before it finished
            doc.update(state="stopped", progress="stopped (the studio was closed); a candidate plays once rendered")
        return doc

    def batches(self, session: Any) -> list[dict[str, Any]]:
        """The session's batches, newest first: id, when, what they vary, state and, per
        candidate, its letter, kind, label and the version it was kept as (if it was)."""
        top = session.folder / "variations"
        if not top.is_dir():
            return []
        out = []
        for path in sorted((p for p in top.iterdir() if BATCH_ID.match(p.name)), key=lambda p: p.name, reverse=True):
            try:
                doc = self.read(session, path.name)
            except VidgenError:
                continue
            out.append({k: doc.get(k) for k in ("id", "created", "root", "base", "shuffle", "chain", "state")}
                       | {"items": [{k: i.get(k) for k in ("letter", "kind", "label", "kept", "status")} for i in doc.get("items", [])]})
        return out

    def text(self, session: Any, batch: str, letter: str) -> str:
        if letter not in LETTERS:
            raise VidgenError(f"variations: no candidate {letter!r} (a to d)")
        path = self.folder(session, batch) / f"{letter}.yaml"
        if not path.is_file():
            raise VidgenError(f"variations: no candidate {letter} in batch {batch}")
        return path.read_text(encoding="utf-8")

    def item(self, session: Any, batch: str, letter: str) -> dict[str, Any]:
        doc = self.read(session, batch)
        found = next((i for i in doc["items"] if i["letter"] == letter), None)
        if found is None:
            raise VidgenError(f"variations: no candidate {letter} in batch {batch}")
        return {**found, "root": doc["root"], "chain": doc.get("chain", [])}

    def start(self, session: Any, text: str, root: int, base: dict[str, Any], shuffle: int = 0, first: str | None = None,
              chain: Sequence[str] = ()) -> dict[str, Any]:
        """Make a batch of variations of ``text`` (the version ``root``, or a candidate of an
        earlier batch: ``base``), write it, and render and check it in the background (a running
        batch stops at its next step)."""
        began = time.perf_counter()
        found = make_variations(text, shuffle, first)
        if not found:
            raise VidgenError("variations: nothing to vary in this score (no chords, figures, pads or sections to change)")
        made = round(time.perf_counter() - began, 3)
        top = session.folder / "variations"
        number = 1 + max((int(p.name[1:]) for p in top.iterdir() if BATCH_ID.match(p.name)), default=0) if top.is_dir() else 1
        batch = f"b{number:04d}"
        folder = self.folder(session, batch)
        for letter, (variation, new_text) in zip(LETTERS, found):
            write_text_atomic(folder / f"{letter}.yaml", new_text)
        doc = {
            "format": BATCH_FORMAT, "id": batch, "created": _now(), "root": root, "base": base, "shuffle": shuffle,
            "first": first, "chain": list(chain), "state": "running", "progress": "waiting to render",
            "items": [{"letter": letter, "kind": v.kind, "name": v.name, "label": v.label, "status": "waiting", "key": None,
                       "render": None, "check": None, "kept": None, "error": None} for letter, (v, _) in zip(LETTERS, found)],
            "timing": {"made": made},
        }
        with self._lock:
            self._running = str(folder)
            self._docs = {str(folder): doc}
        self._save(folder, doc)
        thread = threading.Thread(target=self._work, args=(session, folder), name=f"vidgen-studio-variations-{batch}", daemon=True)
        self._thread = thread
        thread.start()
        return self.read(session, batch)

    def close(self) -> None:
        self._closed = True
        with self._lock:
            self._running = None

    def wait(self, seconds: float) -> None:
        """Wait for the worker (tests)."""
        if self._thread is not None:
            self._thread.join(seconds)

    def mark_kept(self, session: Any, batch: str, letter: str, version: int) -> None:
        folder = self.folder(session, batch)
        with self._lock:
            doc = self._docs.get(str(folder))
        if doc is None:
            doc = self.read(session, batch)
        for item in doc["items"]:
            if item["letter"] == letter:
                item["kept"] = version
        self._save(folder, doc)

    # -- the worker --

    def _wanted(self, folder: Path) -> bool:
        return not self._closed and self._running == str(folder)

    def _save(self, folder: Path, doc: dict[str, Any]) -> None:
        with self._lock:
            write_text_atomic(folder / "batch.json", json.dumps(doc, indent=1, ensure_ascii=False) + "\n")

    def _work(self, session: Any, folder: Path) -> None:
        doc = self._docs.get(str(folder))
        if doc is None:
            return
        began = time.perf_counter()
        items = doc["items"]
        try:
            for k, item in enumerate(items):  # render all first: the four play as soon as possible
                if not self._wanted(folder):
                    break
                item["status"] = "rendering"
                doc["progress"] = f"rendering {item['letter']} ({k + 1}/{len(items)})"
                self._save(folder, doc)
                try:
                    r = self._render(session, (folder / f"{item['letter']}.yaml").read_text(encoding="utf-8"))
                except VidgenError as exc:
                    item.update(status="failed", error=str(exc))
                    continue
                item.update(status="rendered", key=r["key"], render=r)
            doc["timing"]["render"] = round(time.perf_counter() - began, 2)
            checking = time.perf_counter()
            for k, item in enumerate(items):
                if not self._wanted(folder):
                    break
                if item["status"] != "rendered":
                    continue
                item["status"] = "checking"
                doc["progress"] = f"checking {item['letter']} ({k + 1}/{len(items)})"
                self._save(folder, doc)
                one = time.perf_counter()
                try:
                    found = self._check(session, (folder / f"{item['letter']}.yaml").read_text(encoding="utf-8"), lambda: self._wanted(folder))
                except VidgenError as exc:
                    item.update(status="failed", error=str(exc))
                    continue
                if found is None:
                    item["status"] = "rendered"
                    break
                item.update(status="done", check={**found, "seconds": round(time.perf_counter() - one, 2)})
            doc["timing"]["check"] = round(time.perf_counter() - checking, 2)
        finally:
            doc["timing"]["total"] = round(time.perf_counter() - began + doc["timing"].get("made", 0), 2)
            stopped = not self._wanted(folder)
            doc["state"] = "stopped" if stopped else "done"
            doc["progress"] = "stopped (a newer batch was asked for)" if stopped else "done"
            self._save(folder, doc)


def check_brief(doc: Mapping[str, Any]) -> dict[str, Any]:
    """What a variation's card shows of its check: verdict, level, headline numbers, the
    spectrogram's address and size, how many findings to fix or note."""
    return {
        "key": doc["key"],
        "verdict": doc["verdict"],
        "level": doc["level"],
        "headline": doc["headline"],
        "image": doc["image"],
        "fix": sum(1 for f in doc["findings"] if f["level"] == "fix"),
        "note": sum(1 for f in doc["findings"] if f["level"] == "note"),
    }


def agent_variations(root: Path, session_id: str | None = None, version: int | None = None, shuffle: int = 0) -> dict[str, Any]:
    """For an MCP agent: four variations of a studio session's version (default: the current one)
    as whole score texts with their labels — starting points to listen to through the studio or
    to propose (``studio_propose``); nothing is written."""
    from vidgen.studio_app.agent import find_session

    session = find_session(root, session_id)
    number = version if version is not None else session.current
    assert number is not None
    found = make_variations(session.text(number), shuffle)
    return {
        "session": session.id,
        "version": number,
        "shuffle": shuffle,
        "variations": [{"letter": letter, "kind": v.kind, "label": v.label, "score": text} for letter, (v, text) in zip(LETTERS, found)],
        "next": "listen in the studio (Variations), or change one further and studio_propose it with one line per note; "
                f"shuffle={shuffle + 1} gives four others",
    }
