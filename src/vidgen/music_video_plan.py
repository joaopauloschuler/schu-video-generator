"""A storyboard from the music (DESIGN.md §121.2): ``vidgen music plan SCORE`` reads a score file
and proposes the scenes of a music video, cut on its bar lines, without playing it.

The score's events (:func:`vidgen.studio.events.score_events`) are counted per bar: which tracks
sound, how many notes and hits start, the chord. From them:

- **sections and roles**: every section of the score gets a role (``intro``, ``verse``,
  ``build``, ``drop``, ``climax``, ``breakdown``, ``outro``) from its name when the name says it
  (``dawn``, ``coda``, ``riser``...), else from its energy (how many tracks play, how busy they
  are) against the piece's and its neighbours';
- **cuts**: a scene per section, a long section split on a phrase line (every 4 bars from its
  start) where the material changes most (tracks come in or leave, the progression starts again,
  a breath before it), a section shorter than ``min_seconds`` joined to the one before;
- **moments**: drops (a bar much busier than the two before), breaths (a bar with almost no new
  notes between busy ones), silent bars, risers;
- **a colour script**: a colour per role (cool and sparse at the start, warm and saturated at the
  peak, calm at the end), more saturated with more energy, tinted by the key's mode;
- **reactions**: the tracks each scene's page follows, by what they are: low drums pulse the
  light, accents (snares, claps, cymbals) send rings, melodies leave glints, pads and held notes
  set the glow.

:func:`write_music_video` writes the plan as a draft project: ``video.yaml`` with ``music:`` on
the score, a ``web_cut`` scene (the ``web`` scene without its fade-out) per cut with
``music_data``, and a starter page per scene from ``data/web/starters/`` (one per look, built on
``vidgen/three-kit`` and ``vidgen/music-time``).
"""

from __future__ import annotations

import colorsys
import json
import math
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

from vidgen.errors import VidgenError
from vidgen.sfx import RATE
from vidgen.studio.events import ScoreEvent, score_events
from vidgen.studio.score_file import MusicScore, load_music_score

#: The roles a section can play, in the order of the colour script.
ROLES = ("intro", "verse", "build", "drop", "climax", "breakdown", "outro")
#: Words in a section's name that give its role (matched as whole words or name parts).
ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "intro": ("intro", "introduction", "opening", "prelude", "dawn", "overture"),
    "outro": ("outro", "coda", "end", "ending", "close", "closing", "epilogue", "postlude"),
    "build": ("build", "buildup", "rise", "riser", "pre", "prechorus", "ramp"),
    "drop": ("drop", "chorus"),
    "climax": ("climax", "peak", "summit", "apex"),
    "breakdown": ("break", "breakdown", "bridge", "interlude"),
    "verse": ("verse", "groove"),
}
#: The colour of a role (hue in degrees, saturation, lightness), before energy and mode tint it.
ROLE_COLOURS: dict[str, tuple[float, float, float]] = {
    "intro": (205.0, 0.55, 0.55),
    "verse": (185.0, 0.65, 0.50),
    "build": (280.0, 0.70, 0.55),
    "drop": (325.0, 0.85, 0.55),
    "climax": (32.0, 0.95, 0.55),
    "breakdown": (250.0, 0.50, 0.50),
    "outro": (220.0, 0.35, 0.65),
}
#: The grade of a role (three-finish's ``grade``: temperature, saturation): cool at the edges, warm at the peak.
ROLE_GRADES: dict[str, tuple[float, float]] = {
    "intro": (-0.15, 0.9), "verse": (-0.05, 1.0), "build": (0.0, 1.05), "drop": (0.05, 1.15),
    "climax": (0.15, 1.2), "breakdown": (-0.1, 0.9), "outro": (-0.12, 0.85),
}
#: The starter page each role gets (``data/web/starters/<look>.js``).
ROLE_LOOKS: dict[str, str] = {
    "intro": "drift", "verse": "orbit", "build": "tunnel", "drop": "swarm",
    "climax": "rings", "breakdown": "dust", "outro": "ribbon",
}
LOOK_WORDS: dict[str, str] = {
    "drift": "a slow flight through a nebula and stars",
    "orbit": "a tesseract the camera circles, in a shell of stars",
    "tunnel": "a flight down a tunnel of rings on the beat, faster as it builds",
    "swarm": "a swarm of crystals around a flare, rings from the accents",
    "rings": "great rings, a crystal field and the spectrum as rays around a flare",
    "dust": "one crystal in drifting dust, the camera close and slow",
    "ribbon": "the melody as a ribbon of light, the camera drawing back",
}
#: What a track's sound makes the picture do.
REACTIONS = ("pulse", "ring", "glint", "glow")
REACTION_WORDS = {"pulse": "brightness pulse", "ring": "rings of light", "glint": "glints", "glow": "glow level"}
LOW_DRUMS = frozenset({"kick", "boom", "taiko", "bass_drum", "frame_drum", "pulsar", "timpani", "toms"})
ACCENTS = frozenset({"clap", "gated_snare", "snare_drum", "cymbal", "tam_tam", "open_hat", "snap"})
#: Drums that only mark time or texture (too dense or unpitched noise to follow).
TEXTURE = frozenset({"hat", "tick", "static", "riser"})
PADS = frozenset({"pad", "supersaw", "saw_pad", "glass", "organ", "choir"})
MINOR_MODES = frozenset({"minor", "dorian", "phrygian"})
DEFAULT_MAX_SECONDS = 16.0
DEFAULT_MIN_SECONDS = 5.0
#: Seconds the last scene holds after the last bar of a one-pass score, for the last chord's ring.
TAIL_SECONDS = 3.0
PHRASE_BARS = 4
DEFAULT_FPS = 30
WEB_CUT = '''"""``web_cut``: the ``web`` scene without its 0.5 s fade-out, so the scenes cut straight into each
other on the bar line while the music goes on (written by ``vidgen music plan``; docs/EXTENDING.md,
"A variant of the ``web`` type"). Its scenes take the ``web`` params and are cached like ``web`` scenes."""

from vidgen.api import scene
from vidgen.scenes.web import Web


@scene("web_cut")
class WebCut(Web):
    outro = 0.0
'''


@dataclass(frozen=True)
class BarFacts:
    """One bar: ``index`` (0-based), ``start`` (s), the tracks that sound in it, how many events
    start in it (``onsets``, per track in ``starts``), its chord, its ``energy`` (0..1 of the piece's busiest bar)."""

    index: int
    start: float
    section: str
    sounding: frozenset[str]
    starts: Mapping[str, int]
    chord: str
    energy: float

    @property
    def onsets(self) -> int:
        return sum(self.starts.values())


@dataclass(frozen=True)
class Moment:
    """A bar worth a picture's attention: ``kind`` ``drop``, ``breath``, ``silent`` or ``riser``."""

    kind: str
    bar: int
    time: float
    note: str


@dataclass(frozen=True)
class SectionPlan:
    name: str
    role: str
    first_bar: int
    bars: int
    energy: float
    why: str


@dataclass(frozen=True)
class SceneCut:
    """A proposed scene: bars ``first_bar`` .. ``first_bar + bars - 1`` (0-based), from ``start`` to
    ``end`` song seconds (``end`` with the tail on the last scene), ``frames`` at the plan's fps."""

    id: str
    section: str
    role: str
    look: str
    first_bar: int
    bars: int
    start: float
    end: float
    frames: int
    energy: float
    colours: Mapping[str, str]
    react: Mapping[str, tuple[str, ...]]
    enters: tuple[str, ...]
    leaves: tuple[str, ...]
    why: str
    moments: tuple[Moment, ...] = ()

    @property
    def tracks(self) -> list[str]:
        """Every track the scene's page reads, each once (``music_data.tracks``)."""
        return list(dict.fromkeys(t for kind in REACTIONS for t in self.react.get(kind, ())))


@dataclass(frozen=True)
class MusicPlan:
    path: Path
    title: str
    key: str
    mode: str
    tempo: float
    time: tuple[int, int]
    bar_seconds: float
    bars: int
    loop: bool
    seconds: float
    tail: float
    fps: int
    sections: tuple[SectionPlan, ...]
    scenes: tuple[SceneCut, ...]
    moments: tuple[Moment, ...]
    track_reactions: Mapping[str, str | None] = field(default_factory=dict)


# ----- reading the score per bar ---------------------------------------------------------------


def _bar_facts(score: MusicScore, events: Mapping[str, Sequence[ScoreEvent]]) -> list[BarFacts]:
    bar = score.bar / RATE
    count = score.bars
    sounding: list[set[str]] = [set() for _ in range(count)]
    starts: list[dict[str, int]] = [{} for _ in range(count)]
    for track, evs in events.items():
        for e in evs:
            first = math.floor(e.time / bar + 1e-6)
            if 0 <= first < count:
                starts[first][track] = starts[first].get(track, 0) + 1
            last = math.ceil((e.time + max(e.duration, 1e-3)) / bar - 1e-6) - 1
            for b in range(max(first, 0), min(last, count - 1) + 1):
                sounding[b].add(track)
    chords: list[str] = [""] * count
    names: list[str] = [""] * count
    for section in score.sections:
        for b in range(section.first_bar, section.first_bar + section.bars):
            names[b] = section.name
            at = b * score.bar
            slot = next((c for c in section.chords if c.start <= at < c.start + c.length), None)
            chords[b] = slot.chord.name if slot is not None else ""
    raw = [0.5 * len(sounding[b]) + 0.5 * sum(min(n, 8) / 8 for n in starts[b].values()) for b in range(count)]
    top = max(raw) or 1.0
    return [BarFacts(b, b * bar, names[b], frozenset(sounding[b]), starts[b], chords[b], raw[b] / top) for b in range(count)]


def _moments(bars: Sequence[BarFacts], events: Mapping[str, Sequence[ScoreEvent]], score: MusicScore) -> list[Moment]:
    out: list[Moment] = []
    for b, facts in enumerate(bars):
        before = [bars[k].energy for k in (b - 2, b - 1) if k >= 0]
        if not facts.sounding:
            out.append(Moment("silent", b, facts.start, "nothing sounds"))
        elif (b and before and facts.energy - sum(before) / len(before) >= 0.25 and facts.energy >= 0.55
              and not any(m.kind == "drop" and m.bar >= b - 2 for m in out)):
            out.append(Moment("drop", b, facts.start, f"energy {sum(before) / len(before):.2f} -> {facts.energy:.2f}"))
        neighbours = [bars[k].onsets for k in (b - 1, b + 1) if 0 <= k < len(bars)]
        if facts.sounding and neighbours and min(neighbours) >= 4 and facts.onsets <= 0.25 * sum(neighbours) / len(neighbours):
            out.append(Moment("breath", b, facts.start, f"{facts.onsets} new notes between {' and '.join(str(n) for n in neighbours)}"))
    riser_tracks = [t.name for t in score.tracks if t.instrument.name == "riser"]
    bar = score.bar / RATE
    for name in riser_tracks:
        for e in events.get(name, ()):
            out.append(Moment("riser", int(e.time / bar + 1e-6), e.time, f"{name} for {e.duration:.1f} s"))
    return sorted(out, key=lambda m: (m.bar, m.kind))


# ----- roles ------------------------------------------------------------------------------------


def _name_role(name: str) -> str | None:
    """The role a section's name gives (``coda`` -> outro, ``heart2`` -> verse), else ``None``."""
    parts = [p for p in re.split(r"[_\d]+", name.lower()) if p]
    for role, words in ROLE_WORDS.items():
        if name.lower() in words or any(p in words for p in parts):
            return role
    return None


def _section_roles(score: MusicScore, bars: Sequence[BarFacts], events: Mapping[str, Sequence[ScoreEvent]]) -> list[SectionPlan]:
    energies = []
    for s in score.sections:
        block = bars[s.first_bar:s.first_bar + s.bars]
        energies.append(sum(f.energy for f in block) / len(block))
    top = max(energies) or 1.0
    riser_bars = {int(e.time / (score.bar / RATE) + 1e-6) for t in score.tracks if t.instrument.name == "riser" for e in events.get(t.name, ())}
    out: list[SectionPlan] = []
    last = len(score.sections) - 1
    for k, s in enumerate(score.sections):
        e = energies[k] / top
        named = _name_role(s.name)
        block = bars[s.first_bar:s.first_bar + s.bars]
        half = max(1, len(block) // 2)
        rising = sum(f.energy for f in block[half:]) / max(1, len(block) - half) - sum(f.energy for f in block[:half]) / half
        nxt = energies[k + 1] / top if k < last else 0.0
        prev = energies[k - 1] / top if k else 0.0
        has_riser = any(s.first_bar <= b < s.first_bar + s.bars for b in riser_bars)
        if named is not None:
            role, why = named, f"its name ({s.name})"
        elif k == 0 and e < 0.6:
            role, why = "intro", "first and sparse"
        elif k == last and e < 0.75:
            role, why = "outro", "last and calmer"
        elif e >= 0.9:
            role, why = "climax", "the busiest"
        elif (rising >= 0.15 or has_riser) and nxt > e:
            role, why = "build", "rising into a fuller section"
        elif k and e - prev >= 0.2 and e >= 0.7:
            role, why = "drop", "much fuller than the one before"
        elif k and prev - e >= 0.25:
            role, why = "breakdown", "much sparser than the one before"
        else:
            role, why = "verse", "steady"
        out.append(SectionPlan(s.name, role, s.first_bar, s.bars, round(e, 3), why))
    return out


# ----- cuts -------------------------------------------------------------------------------------


def _change(bars: Sequence[BarFacts], at: int, lo: int, hi: int, section_first: int) -> float:
    """How much the music changes at bar line ``at`` (within bars ``lo`` .. ``hi`` - 1): tracks
    entering or leaving over a phrase on each side, the progression starting again, a breath before."""
    a = set().union(*(bars[b].sounding for b in range(max(lo, at - PHRASE_BARS), at)))
    b_ = set().union(*(bars[b].sounding for b in range(at, min(hi, at + PHRASE_BARS))))
    union = a | b_
    score = len(a ^ b_) / len(union) if union else 0.0
    n = min(PHRASE_BARS, hi - at)
    if at > section_first and n and [f.chord for f in bars[at:at + n]] == [f.chord for f in bars[section_first:section_first + n]]:
        score += 0.25
    ea = sum(bars[b].energy for b in range(max(lo, at - PHRASE_BARS), at)) / max(1, at - max(lo, at - PHRASE_BARS))
    eb = sum(bars[b].energy for b in range(at, min(hi, at + PHRASE_BARS))) / max(1, min(hi, at + PHRASE_BARS) - at)
    score += 0.5 * abs(eb - ea)
    if at and bars[at - 1].onsets <= 0.25 * max(1, bars[at].onsets):
        score += 0.2
    return score


def _split(bars: Sequence[BarFacts], first: int, count: int, section_first: int, bar_s: float, max_s: float, min_s: float) -> list[tuple[int, int, str]]:
    """``(first bar, bars, why)`` pieces of bars ``first`` .. ``first + count - 1``: split on a
    phrase line while longer than ``max_s``; a piece of 16 bars or more also where the material changes clearly
    (into pieces of 8 bars or more)."""
    candidates = [b for b in range(first + 1, first + count) if (b - section_first) % PHRASE_BARS == 0
                  and (b - first) * bar_s >= min_s - 1e-6 and (first + count - b) * bar_s >= min_s - 1e-6]
    too_long = count * bar_s > max_s + 1e-6
    if not too_long:   # a split for the material alone leaves two pieces of two phrases or more
        candidates = [b for b in candidates if b - first >= 2 * PHRASE_BARS and first + count - b >= 2 * PHRASE_BARS]
    if not candidates:
        return [(first, count, "")]
    mid = first + count / 2
    scored = [(_change(bars, b, first, first + count, section_first) + 0.3 * (1 - abs(b - mid) / (count / 2)), b) for b in candidates]
    _, at = max(scored)
    change = _change(bars, at, first, first + count, section_first)
    if not too_long and change < 0.45:
        return [(first, count, "")]
    why = f"longer than {max_s:g} s" if too_long else "the material changes"
    why += f": split at bar {at + 1} (change {change:.2f})"
    left = _split(bars, first, at - first, section_first, bar_s, max_s, min_s)
    right = _split(bars, at, first + count - at, section_first, bar_s, max_s, min_s)
    left[-1] = (left[-1][0], left[-1][1], left[-1][2] or why)
    right[0] = (right[0][0], right[0][1], right[0][2] or why)
    return left + right


# ----- colour and reactions ---------------------------------------------------------------------


def _toward(hue: float, target: float, degrees: float) -> float:
    d = (target - hue + 540.0) % 360.0 - 180.0
    return (hue + max(-degrees, min(degrees, d))) % 360.0


def _hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return "#{:02x}{:02x}{:02x}".format(*(round(v * 255) for v in (r, g, b)))


def role_colours(role: str, energy: float, mode: str) -> dict[str, str]:
    """A scene's colours (``base``, ``accent``, ``deep``; ``#rrggbb``) from its role, its
    ``energy`` (0..1: more saturated and brighter when fuller) and the key's ``mode`` (minor,
    dorian and phrygian tint the hue towards blue, the others towards gold, by 8 degrees)."""
    h, s, l = ROLE_COLOURS[role]
    if mode in MINOR_MODES:
        h = _toward(h, 230.0, 8.0)
    else:
        h = _toward(h, 45.0, 8.0)
    e = max(0.0, min(1.0, energy))
    s *= 0.75 + 0.25 * e
    l *= 0.88 + 0.12 * e
    return {"base": _hex(h, s, l), "accent": _hex(h + 160.0, min(1.0, s + 0.1), 0.66), "deep": _hex(h, s * 0.8, 0.045)}


def _track_reaction(instrument: str, kind: str, pitches: Sequence[int], durations: Sequence[float], per_bar: float, beat: float) -> str | None:
    if instrument in LOW_DRUMS:
        return "pulse"
    if instrument in ACCENTS:
        return "ring" if per_bar <= 4 else None
    if kind == "drum" or instrument in TEXTURE:
        return None
    held = bool(durations) and median(durations) >= 2 * beat
    if kind in ("pad", "chords") or held:
        return "glow"
    if pitches and median(pitches) >= 55 and per_bar <= 8:
        return "glint"
    return None


def _reactions(score: MusicScore, events: Mapping[str, Sequence[ScoreEvent]], start: float, end: float) -> tuple[dict[str, tuple[str, ...]], dict[str, str | None]]:
    """The tracks a scene from ``start`` to ``end`` s follows, by reaction (at most two pulses and
    glints, one ring and one glow), and every playing track's reaction."""
    bar = score.bar / RATE
    beat = score.beat / RATE
    bars = max(1e-6, (end - start) / bar)
    found: dict[str, list[tuple[float, str]]] = {k: [] for k in REACTIONS}
    kinds: dict[str, str | None] = {}
    by_name = {t.name: t for t in score.tracks}
    for name, evs in events.items():
        inside = [e for e in evs if start - 1e-6 <= e.time < end - 1e-6]
        if not inside:
            continue
        track = by_name[name]
        kind = "chords" if track.play_chords else track.instrument.kind
        instrument = max({e.instrument for e in inside}, key=lambda n: sum(e.instrument == n for e in inside))
        if instrument != track.instrument.name:
            kind = next((t.kind for t in (track.instrument_of(p) for p in track.parts.values()) if t.name == instrument), kind)
        pitches = [p for e in inside for p in e.pitches[:1]]
        reaction = _track_reaction(instrument, kind, pitches, [e.duration for e in inside], len(inside) / bars, beat)
        kinds[name] = reaction
        if reaction is None:
            continue
        if reaction == "glint":
            rank = median(pitches) + min(len(inside), 64) / 8
        elif reaction == "glow":   # the pads and voices before held bass notes
            rank = sum(min(e.duration, end - e.time) for e in inside) * (3 if kind in ("pad", "chords") or instrument in PADS else 1)
        elif reaction == "ring":
            rank = -abs(len(inside) / bars - 1.0)       # about one a bar reads best
        else:
            rank = len(inside) + (50 if instrument in ("kick", "taiko", "bass_drum") else 0)
        found[reaction].append((rank, name))
    limits = {"pulse": 2, "ring": 1, "glint": 2, "glow": 1}
    return {k: tuple(n for _, n in sorted(found[k], key=lambda x: (-x[0], x[1]))[:limits[k]]) for k in REACTIONS}, kinds


# ----- the plan -----------------------------------------------------------------------------------


def plan_music_video(path: Path, *, max_seconds: float = DEFAULT_MAX_SECONDS, min_seconds: float = DEFAULT_MIN_SECONDS, fps: int = DEFAULT_FPS) -> MusicPlan:
    """The proposed scenes of a music video on the score file at ``path`` (see the module doc)."""
    if not (0 < min_seconds <= max_seconds):
        raise VidgenError(f"music plan: --min-scene ({min_seconds:g} s) must be above 0 and at most --max-scene ({max_seconds:g} s)")
    score = load_music_score(path)
    return plan_from_score(score, path, max_seconds=max_seconds, min_seconds=min_seconds, fps=fps)


def plan_from_score(score: MusicScore, path: Path, *, max_seconds: float = DEFAULT_MAX_SECONDS, min_seconds: float = DEFAULT_MIN_SECONDS,
                    fps: int = DEFAULT_FPS) -> MusicPlan:
    """:func:`plan_music_video` of a score already read."""
    events = score_events(score)
    if not any(events.values()):
        raise VidgenError(f"music plan: {path} has no notes or hits to plan from")
    bar_s = score.bar / RATE
    bars = _bar_facts(score, events)
    moments = _moments(bars, events, score)
    sections = _section_roles(score, bars, events)
    pieces: list[tuple[SectionPlan, int, int, str]] = []
    for sec in sections:
        for first, count, why in _split(bars, sec.first_bar, sec.bars, sec.first_bar, bar_s, max_seconds, min_seconds):
            pieces.append((sec, first, count, why or ("the whole section" if count == sec.bars else "")))
    merged: list[list[Any]] = []
    for sec, first, count, why in pieces:
        if merged and count * bar_s < min_seconds - 1e-6:
            merged[-1][2] += count
            merged[-1][3] += f"; with {sec.name} ({count} bar{'s' if count != 1 else ''}, under {min_seconds:g} s)"
        elif merged and merged[-1][2] * bar_s < min_seconds - 1e-6 and len(merged) == 1:
            merged[-1][2] += count
            merged[-1][3] += f"; with {sec.name}"
        else:
            merged.append([sec, first, count, why])
    tail = 0.0 if score.loop else TAIL_SECONDS
    mode = score.key.mode
    scenes: list[SceneCut] = []
    used: dict[str, int] = {}
    previous: frozenset[str] = frozenset()
    all_kinds: dict[str, str | None] = {}
    for k, (sec, first, count, why) in enumerate(merged):
        start, end = first * bar_s, (first + count) * bar_s
        last = k == len(merged) - 1
        block = bars[first:first + count]
        energy = round(sum(f.energy for f in block) / len(block), 3)
        react, kinds = _reactions(score, events, start, end)
        for name, kind in kinds.items():
            all_kinds.setdefault(name, kind)
        now = frozenset().union(*(f.sounding for f in block[:PHRASE_BARS]))
        used[sec.name] = used.get(sec.name, 0) + 1
        ident = f"{k + 1:02d}_{sec.name}" + (f"_{used[sec.name]}" if used[sec.name] > 1 else "")
        end_s = end + (tail if last else 0.0)
        frames = round(end_s * fps) - round(start * fps)
        scenes.append(SceneCut(
            id=ident, section=sec.name, role=sec.role, look=ROLE_LOOKS[sec.role], first_bar=first, bars=count,
            start=round(start, 6), end=round(end_s, 6), frames=frames, energy=energy,
            colours=role_colours(sec.role, energy, mode), react=react,
            enters=tuple(sorted(now - previous)) if k else (), leaves=tuple(sorted(previous - now)) if k else (),
            why=why, moments=tuple(m for m in moments if first <= m.bar < first + count),
        ))
        previous = frozenset().union(*(f.sounding for f in block[-PHRASE_BARS:]))
    return MusicPlan(
        path=path, title=score.title or path.stem.replace("_", " ").replace("-", " ").title(), key=score.key.name, mode=mode,
        tempo=score.tempo, time=score.time, bar_seconds=bar_s, bars=score.bars, loop=score.loop, seconds=score.seconds,
        tail=tail, fps=fps, sections=tuple(sections), scenes=tuple(scenes), moments=tuple(moments), track_reactions=all_kinds,
    )


# ----- output -------------------------------------------------------------------------------------


def _bars_text(first: int, count: int) -> str:
    return f"bar {first + 1}" if count == 1 else f"bars {first + 1}-{first + count}"


def plan_dict(plan: MusicPlan) -> dict[str, Any]:
    """The plan as JSON-ready data (``vidgen music plan --json``)."""
    return {
        "score": str(plan.path), "title": plan.title, "key": plan.key, "mode": plan.mode, "tempo": plan.tempo,
        "time": f"{plan.time[0]}/{plan.time[1]}", "bar_seconds": round(plan.bar_seconds, 6), "bars": plan.bars,
        "loop": plan.loop, "seconds": round(plan.seconds, 3), "tail": plan.tail, "fps": plan.fps,
        "sections": [{"name": s.name, "role": s.role, "first_bar": s.first_bar + 1, "bars": s.bars, "energy": s.energy, "why": s.why} for s in plan.sections],
        "scenes": [{
            "id": c.id, "section": c.section, "role": c.role, "look": c.look, "first_bar": c.first_bar + 1, "bars": c.bars,
            "start": c.start, "end": c.end, "duration": round(c.frames / plan.fps, 7), "frames": c.frames, "energy": c.energy,
            "colours": dict(c.colours), "react": {k: list(v) for k, v in c.react.items()}, "enters": list(c.enters),
            "leaves": list(c.leaves), "why": c.why, "moments": [_moment_dict(m) for m in c.moments],
        } for c in plan.scenes],
        "moments": [_moment_dict(m) for m in plan.moments],
        "tracks": {name: kind for name, kind in plan.track_reactions.items()},
    }


def _moment_dict(m: Moment) -> dict[str, Any]:
    return {"kind": m.kind, "bar": m.bar + 1, "time": round(m.time, 3), "note": m.note}


def plan_text(plan: MusicPlan) -> str:
    """The plan in words (``vidgen music plan``)."""
    lines = [f"{plan.title}: {plan.key}, {plan.tempo:g} BPM, {plan.time[0]}/{plan.time[1]}, {plan.bars} bars of {plan.bar_seconds:.3f} s "
             f"= {plan.seconds:.2f} s" + (f" (+ {plan.tail:g} s for the last chord)" if plan.tail else " (a loop)")]
    lines.append("sections:")
    for s in plan.sections:
        lines.append(f"  {s.name:<12} {_bars_text(s.first_bar, s.bars):<12} {s.role:<9} energy {s.energy:.2f}  ({s.why})")
    lines.append(f"scenes ({len(plan.scenes)}, cut on bar lines; durations at {plan.fps} fps):")
    width = max(len(c.id) for c in plan.scenes)
    for c in plan.scenes:
        lines.append(f"  {c.id:<{width}}  {c.start:7.2f} s  {_bars_text(c.first_bar, c.bars):<12} {c.frames / plan.fps:6.2f} s  "
                     f"{c.role:<9} {c.look:<6} {c.colours['base']} / {c.colours['accent']}")
        react = "; ".join(f"{REACTION_WORDS[k]}: {', '.join(v)}" for k, v in c.react.items() if v) or "nothing to follow (the measured level)"
        lines.append(f"  {'':<{width}}    reacts to {react}")
        change = []
        if c.enters:
            change.append("in: " + ", ".join(c.enters))
        if c.leaves:
            change.append("out: " + ", ".join(c.leaves))
        if change:
            lines.append(f"  {'':<{width}}    {'; '.join(change)}")
        for m in c.moments:
            lines.append(f"  {'':<{width}}    {m.kind} at bar {m.bar + 1} ({m.time:.2f} s): {m.note}")
        if c.why:
            lines.append(f"  {'':<{width}}    why: {c.why}")
    return "\n".join(lines)


# ----- the draft project --------------------------------------------------------------------------


STARTERS = Path(__file__).resolve().parent / "data" / "web" / "starters"


def starter_page(look: str) -> Path:
    """The starter page of ``look`` shipped with vidgen (``data/web/starters/<look>.js``)."""
    path = STARTERS / f"{look}.js"
    if not path.is_file():
        raise VidgenError(f"music plan: no starter page '{look}' (looks: {', '.join(sorted(LOOK_WORDS))})")
    return path


_PLAIN = re.compile(r"^[a-z_][a-z0-9_]*\Z")
_RESERVED = frozenset({"y", "n", "yes", "no", "on", "off", "true", "false", "null"})


def _yaml(value: Any) -> str:
    """A string as a YAML scalar (a JSON string is one)."""
    return json.dumps(value, ensure_ascii=False)


def _flow(value: Any) -> str:
    """``value`` (dicts, lists, numbers, strings) as flow-style YAML, names left unquoted."""
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{k}: {_flow(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_flow(v) for v in value) + "]"
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, str):
        return value if _PLAIN.match(value) and value not in _RESERVED else _yaml(value)
    return repr(value) if isinstance(value, float) else str(value)


def _seed(text: str) -> int:
    return sum((i + 1) * ord(c) for i, c in enumerate(text)) % 9973 + 1


def plan_yaml(plan: MusicPlan, source: str) -> str:
    """The draft's ``video.yaml``: the score as ``music:``, a ``web_cut`` scene per cut with its
    page, ``music_data`` and its ``data`` (role, colours, the colour script, reactions, moments)."""
    script = [{"at": round(c.start, 6), "role": c.role, **c.colours} for c in plan.scenes]
    lines = [
        f"# {plan.title}: a music video drafted by `vidgen music plan` from {Path(source).name}.",
        f"# Music: {plan.key}, {plan.tempo:g} BPM, {plan.time[0]}/{plan.time[1]}; one bar = {plan.bar_seconds:.4f} s "
        f"({plan.bar_seconds * plan.fps:.2f} frames at {plan.fps} fps). Form: "
        + " | ".join(f"{s.name} {s.bars}" for s in plan.sections) + f" = {plan.bars} bars.",
        "# Every scene starts on a bar line (its duration is whole frames between two bar lines), so",
        "# ctx.music.t0 is its place in the song; web_cut (extensions/web_cut.py) is the web scene without its",
        "# fade-out, so the scenes cut straight into each other. Each page is a starter from vidgen's kit",
        "# (vidgen/three-kit, vidgen/music-time, vidgen/three-finish): edit it freely; data: carries its plan.",
        "# Look:   vidgen still . --scene " + plan.scenes[0].id + " --at 2 --size 640x360",
        "# Render: vidgen render . --draft   (then --preview, then the final render)",
        f"title: {_yaml(plan.title)}",
        f"output: {re.sub(r'[^a-z0-9_]+', '_', plan.title.lower()).strip('_') or 'music_video'}",
        f"format: {{width: 1280, height: 720, fps: {plan.fps}}}",
        f"preview: {{width: 640, height: 360, fps: {plan.fps}}}",
        "theme: {preset: bold_neon}",
        "transition: cut",
        f"music: {{source: {_yaml(source)}, volume: 0, start: 0, loop: false, fade_in: 0, fade_out: 1.5, duck: false}}",
        "audio: {normalize: true, target_lufs: -14, true_peak: -1.5}",
        "scenes:",
    ]
    for k, c in enumerate(plan.scenes):
        react = "; ".join(f"{kind} {', '.join(v)}" for kind, v in c.react.items() if v) or "the measured level"
        music = f"{{tracks: {_flow(c.tracks)}}}" if c.tracks else "true"
        lines += [
            f"  # {_bars_text(c.first_bar, c.bars)} ({c.start:.2f} s): {c.section}, {c.role}: {LOOK_WORDS[c.look]}; reacts to {react}",
            f"  - id: {c.id}",
            "    type: web_cut",
            f"    duration: {round(c.frames / plan.fps, 7)}",
            "    params:",
            f"      script: extensions/{c.id}.js",
            f"      music_data: {music}",
            "      data:",
            f"        role: {c.role}",
            f"        look: {c.look}",
            f"        seed: {_seed(c.id)}",
            f"        energy: {c.energy}",
            f"        bar: {round(plan.bar_seconds, 6)}",
            f"        start: {c.start}",
            f"        end: {round((c.first_bar + c.bars) * plan.bar_seconds, 6)}",
            f"        until: {c.end}",
            f"        colours: {_flow(dict(c.colours))}",
            f"        grade: {_flow(dict(zip(('temperature', 'saturation'), ROLE_GRADES[c.role])))}",
            f"        react: {_flow({kind: list(v) for kind, v in c.react.items()})}",
            f"        drops: {_flow([round(m.time, 6) for m in c.moments if m.kind == 'drop'])}",
        ]
        if k == 0:
            lines.append("        script: &script      # the colour script: every scene's colours from its first second")
            lines += [f"          - {_flow(stop)}" for stop in script]
        else:
            lines.append("        script: *script")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class DraftResult:
    root: Path
    config: Path
    files: tuple[str, ...]
    created: bool


def place_score(plan: MusicPlan, output: Path, *, force: bool = False) -> tuple[str, list[str], bool]:
    """Make the draft's folder ``output`` (an existing folder that is not empty only with ``force``) and put
    the score in it (under ``assets/music/`` unless it is in the folder already): ``(the score's path in the
    project, the files written, whether the folder was new or empty)``."""
    if output.exists() and not output.is_dir():
        raise VidgenError(f"music plan: --out {output} exists and is not a folder")
    created = not output.exists() or not any(output.iterdir())
    if not created and not force:
        raise VidgenError(f"music plan: {output} already exists and is not empty (use --force to write the draft into it)")
    output.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    score = plan.path.resolve()
    try:
        source = score.relative_to(output.resolve()).as_posix()
    except ValueError:
        source = f"assets/music/{score.name}"
        target = output / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(score, target)
        files.append(source)
    return source, files, created


def write_music_video(plan: MusicPlan, output: Path, *, force: bool = False) -> DraftResult:
    """Write ``plan`` as a draft project in the folder ``output`` (created; an existing folder
    that is not empty only with ``force``): ``video.yaml``, the score under ``assets/music/``
    (unless it is in the folder already), ``extensions/web_cut.py`` and a page per scene."""
    from vidgen.fileio import write_text_atomic

    source, files, created = place_score(plan, output, force=force)
    ext = output / "extensions"
    ext.mkdir(exist_ok=True)
    write_text_atomic(ext / "web_cut.py", WEB_CUT)
    files.append("extensions/web_cut.py")
    for c in plan.scenes:
        shutil.copyfile(starter_page(c.look), ext / f"{c.id}.js")
        files.append(f"extensions/{c.id}.js")
    config = output / "video.yaml"
    write_text_atomic(config, plan_yaml(plan, source))
    gitignore = output / ".gitignore"
    if not gitignore.exists():
        write_text_atomic(gitignore, "build/\nexports/\n*.mp4\n")
    return DraftResult(output, config, tuple(files), created)


__all__ = [
    "LOOK_WORDS", "REACTIONS", "ROLES", "DraftResult", "MusicPlan", "SceneCut", "SectionPlan", "plan_dict", "plan_from_score",
    "place_score", "plan_music_video", "plan_text", "plan_yaml", "role_colours", "starter_page", "write_music_video",
]
