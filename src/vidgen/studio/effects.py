"""Track effects and movement of score files (DESIGN.md §93.7): values that move along a section
(curves), filter sweeps, side-chain ducking, gates, echo, reverb and stereo width.

A curve is a number (constant), ``{from: a, to: b}`` (a straight ramp over the section) or a list
of ``[bar, value]`` points (bars counted from the section's start, fractions allowed), straight
between the points (frequencies in octaves), held before the first and after the last.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from vidgen.music import _circular_add
from vidgen.sfx import RATE, _highpass, _lowpass
from vidgen.studio.patterns import Pattern, parse_steps

#: Values that switch an effect off in a section's changes (``duck: none``).
OFF = (None, False, "none", "off")
#: Seconds over which a curve's jumps (between sections) are smoothed, so nothing clicks.
SMOOTH_SECONDS = 0.02
#: The side-chain dip's attack and the gate's attack / release, seconds (as the beds' ``_pump`` / ``_gate``).
DUCK_ATTACK, GATE_ATTACK, GATE_RELEASE = 0.008, 0.003, 0.018
#: A gate step written soft (``o``, ``x?``) opens this far.
GATE_SOFT = 0.4


@dataclass(frozen=True)
class Field:
    """A field of an effect: its default (``None``: required), range (numbers) and what it does."""

    default: Any
    words: str
    low: float | None = None
    high: float | None = None


@dataclass(frozen=True)
class Effect:
    """A track key of the effects catalogue: what it does, how to write it and its fields."""

    name: str
    words: str
    example: str
    fields: Mapping[str, Field]


@dataclass(frozen=True)
class Curve:
    """A value along a section: ``points`` ``(bar, value)``; ``ramp``: the two points are the
    section's start and end."""

    points: tuple[tuple[float, float], ...]
    ramp: bool = False

    def samples(self, n: int, bar: int, octaves: bool = False) -> np.ndarray:
        """The value at each of the section's ``n`` samples (``octaves``: interpolate the log)."""
        if len(self.points) == 1:
            return np.full(n, self.points[0][1])
        xs = np.array([0.0, n]) if self.ramp else np.array([p[0] * bar for p in self.points])
        ys = np.array([p[1] for p in self.points])
        t = np.arange(n, dtype=float)
        if octaves:
            return np.exp(np.interp(t, xs, np.log(ys)))
        return np.interp(t, xs, ys)

    @property
    def constant(self) -> float | None:
        return self.points[0][1] if len(self.points) == 1 else None


@dataclass(frozen=True)
class Duck:
    """Side-chain ducking: the sound dips by ``depth`` at every hit of track ``to`` (or every
    beat, ``to: beat``) and recovers over ``release`` seconds."""

    to: str
    depth: float
    release: float


@dataclass(frozen=True)
class Gate:
    """A rhythmic gate: the sound passes on the pattern's hits (``duty`` of each step), and is
    held down to ``floor`` between them."""

    steps: Pattern
    duty: float
    floor: float


@dataclass(frozen=True)
class Echo:
    """Echoes ``delay`` beats apart, each ``feedback`` quieter; ``pingpong``: alternating sides."""

    delay: float
    feedback: float
    repeats: int
    pingpong: bool


@dataclass(frozen=True)
class Reverb:
    """A room: a decaying noise tail of ``size`` seconds (to -60 dB) at ``mix``, low-passed at
    ``tone``, after ``predelay``; a different tail per side (wide)."""

    size: float
    mix: float
    tone: float
    predelay: float


_CURVE_WORDS = "a number, {from: a, to: b} (a ramp over the section) or [[bar, value], ...] points (bars from the section's start)"

#: The effects and movement a track (and its ``sections:`` changes) can have, in catalogue order.
EFFECTS: dict[str, Effect] = {
    e.name: e
    for e in (
        Effect("volume", "the track's level in dB (0 = the instrument's normal level); a curve fades or swells it",
               "volume: {from: -18, to: 0}", {"value": Field(0.0, "dB: a number or a curve", -60.0, 24.0)}),
        Effect("pan", "where the track sits, -1 left .. 1 right", "pan: -0.3", {"value": Field(0.0, "a number", -1.0, 1.0)}),
        Effect("spread", "steps alternate sides: even steps this far left of pan, odd steps as far right (hats, ostinatos)",
               "spread: 0.25", {"value": Field(0.0, "a number", 0.0, 1.0)}),
        Effect("width", "stereo width of the track's sound: 0 mono, 1 as it is, 2 extra wide (mid/side); a curve opens it up",
               "width: 1.4", {"value": Field(1.0, "a number or a curve", 0.0, 2.0)}),
        Effect("lowpass", "a low-pass filter on the track (12 dB per octave); a curve is a filter sweep (the trance build: dark to bright)",
               "lowpass: [[0, 800], [8, 3200]]", {"value": Field(None, "Hz: a number or a curve", 40.0, 16000.0)}),
        Effect("highpass", "a high-pass filter on the track (12 dB per octave): thins it out; a curve sweeps it",
               "highpass: {from: 600, to: 40}", {"value": Field(None, "Hz: a number or a curve", 20.0, 8000.0)}),
        Effect("duck", "side-chain ducking: the track dips at every hit of another track and swells back (the pumping pad)",
               "duck: {to: kick, depth: 0.5, release: 0.15}   (or duck: kick)",
               {"to": Field("kick", "the track whose hits it ducks under, or beat (every beat)"),
                "depth": Field(0.45, "how far it dips: 0 not at all, 1 to silence", 0.0, 1.0),
                "release": Field(0.15, "seconds to swell back", 0.03, 1.0)}),
        Effect("gate", "a rhythmic gate (trance gate): the sound passes on the pattern's hits and is held down between them",
               "gate: {steps: \"X.xX .xX. X.xX .x-x\", duty: 0.55}   (or gate: \"x.x.x.x.\")",
               {"steps": Field(None, "a drum pattern: x or X opens fully, o or x? opens to 0.4, - keeps it open a step longer, . closed"),
                "duty": Field(0.55, "share of each step it stays open", 0.1, 1.0),
                "floor": Field(0.08, "level between the hits (0 silent)", 0.0, 1.0)}),
        Effect("echo", "echoes (delay) of every note, each quieter; ping-pong between the sides",
               "echo: {delay: 0.75, feedback: 0.35, repeats: 2}",
               {"delay": Field(0.75, "beats between echoes (0.75 = a dotted eighth)", 0.05, 4.0),
                "feedback": Field(0.35, "each echo's level against the one before", 0.0, 0.9),
                "repeats": Field(2, "how many echoes", 1, 12),
                "pingpong": Field(True, "true: the echoes alternate sides; false: they stay where the note is")}),
        Effect("reverb", "a room or hall around the track: a soft decaying tail, wider than the sound",
               "reverb: {size: 2.5, mix: 0.3}",
               {"size": Field(1.8, "seconds the tail takes to die away (-60 dB)", 0.2, 8.0),
                "mix": Field(0.2, "level of the tail against the dry sound", 0.0, 1.0),
                "tone": Field(4000.0, "low-pass of the tail in Hz: lower is darker", 500.0, 12000.0),
                "predelay": Field(0.02, "seconds before the tail starts", 0.0, 0.2)}),
    )
}
#: The effects that are processed on the track's own buffer (not per note).
BUS_EFFECTS = ("width", "lowpass", "highpass", "duck", "gate", "echo", "reverb")


# ----- reading -----------------------------------------------------------------------------------


def is_off(value: Any) -> bool:
    return any(value is v or (isinstance(v, str) and value == v) for v in OFF)


def parse_curve(r: Any, value: Any, where: str, low: float, high: float) -> Curve | None:
    """A curve from YAML (problems added to the reader ``r``)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = r.number(value, where, low, high)
        return Curve(((0.0, number),)) if number is not None else None
    if isinstance(value, Mapping):
        ramp = r.mapping(value, where, ("from", "to"), "a ramp over the section")
        if set(ramp) != {"from", "to"}:
            r.add(where, "a ramp needs from and to, e.g. {from: 800, to: 3200}")
            return None
        a, b = r.number(ramp["from"], f"{where}.from", low, high), r.number(ramp["to"], f"{where}.to", low, high)
        return Curve(((0.0, a), (1.0, b)), ramp=True) if a is not None and b is not None else None
    if isinstance(value, list) and value:
        points: list[tuple[float, float]] = []
        for k, item in enumerate(value):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                r.add(f"{where}[{k}]", f"a point is [bar, value], e.g. [4, 3200], got {item!r}")
                return None
            bar, v = r.number(item[0], f"{where}[{k}][0]", 0, 512), r.number(item[1], f"{where}[{k}][1]", low, high)
            if bar is None or v is None:
                return None
            if points and bar < points[-1][0]:
                r.add(f"{where}[{k}]", f"the points' bars must not go back ({bar:g} after {points[-1][0]:g})")
                return None
            points.append((bar, v))
        return Curve(tuple(points))
    r.add(where, f"expected {_CURVE_WORDS}, e.g. [[0, 800], [8, 3200]]; got {value!r}")
    return None


def _fields(r: Any, value: Any, where: str, effect: Effect, shorthand: str) -> dict[str, Any] | None:
    """An effect's fields with defaults; a plain value is the ``shorthand`` field."""
    given = {shorthand: value} if not isinstance(value, Mapping) else r.mapping(value, where, list(effect.fields), f"{effect.name} settings")
    out: dict[str, Any] = {}
    count = len(r.problems)
    for name, f in effect.fields.items():
        if name not in given:
            if f.default is None:
                r.add(where, f"{effect.name} needs {name} ({f.words}), e.g. {effect.example}")
            out[name] = f.default
        elif f.low is not None and f.high is not None:
            integer = isinstance(f.default, int) and not isinstance(f.default, bool)
            out[name] = r.number(given[name], f"{where}.{name}", f.low, f.high, integer=integer)
            out[name] = int(out[name]) if integer and out[name] is not None else out[name]
        else:
            out[name] = given[name]
    return out if len(r.problems) == count else None


def parse_duck(r: Any, value: Any, where: str) -> Duck | None:
    f = _fields(r, True if value is True else value, where, EFFECTS["duck"], "to")
    if f is None:
        return None
    to = "kick" if f["to"] is True else str(f["to"])
    return Duck(to, f["depth"], f["release"])


def parse_gate(r: Any, value: Any, where: str) -> Gate | None:
    f = _fields(r, value, where, EFFECTS["gate"], "steps")
    if f is None:
        return None
    here = f"{where}.steps" if isinstance(value, Mapping) else where
    steps = r.attempt(here, parse_steps, f["steps"], here)
    if steps is None:
        return None
    if any(s.pitched for bar in steps for s in bar):
        r.add(here, "a gate pattern has no pitch: use x, X, o, '.' and '-'")
        return None
    return Gate(steps, f["duty"], f["floor"])


def parse_echo(r: Any, value: Any, where: str) -> Echo | None:
    f = _fields(r, {} if value is True else value, where, EFFECTS["echo"], "delay")
    if f is None:
        return None
    if not isinstance(f["pingpong"], bool):
        r.add(f"{where}.pingpong", f"expected true or false, got {f['pingpong']!r}")
        return None
    return Echo(f["delay"], f["feedback"], f["repeats"], f["pingpong"])


def parse_reverb(r: Any, value: Any, where: str) -> Reverb | None:
    f = _fields(r, {} if value is True else value, where, EFFECTS["reverb"], "mix")
    return Reverb(f["size"], f["mix"], f["tone"], f["predelay"]) if f is not None else None


# ----- processing ---------------------------------------------------------------------------------


def smooth(x: np.ndarray, seconds: float, wrap: bool) -> np.ndarray:
    """``x`` averaged over a centred window of ``seconds`` (around the loop when ``wrap``)."""
    width = int(seconds * RATE)
    if width < 2:
        return x
    pad = width // 2
    if wrap:
        ext = np.concatenate([x[len(x) - pad :], x, x[: width - pad]])
    else:
        ext = np.concatenate([np.full(pad, x[0]), x, np.full(width - pad, x[-1])])
    total = np.concatenate([[0.0], np.cumsum(ext)])
    return (total[width : width + len(x)] - total[: len(x)]) / width


def swept_filter(x: np.ndarray, cutoff: np.ndarray, kind: str) -> np.ndarray:
    """Stereo ``x`` through a gentle (second-order, zero-phase) low- or high-pass whose cutoff
    follows ``cutoff`` (Hz per sample): the sound filtered at cutoffs half an octave apart,
    cross-faded along the curve (circular FFT over the whole buffer)."""
    response = _lowpass if kind == "lowpass" else _highpass
    spectrum = np.fft.rfft(x, axis=0)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    lo, hi = float(cutoff.min()), float(cutoff.max())
    if hi / lo < 1.01:
        return np.fft.irfft(spectrum * response(freqs, lo, 2)[:, None], len(x), axis=0)
    count = math.ceil(2 * math.log2(hi / lo)) + 1
    position = np.log(cutoff / lo) / math.log(hi / lo) * (count - 1)
    out = np.zeros_like(x)
    for j, fc in enumerate(np.geomspace(lo, hi, count)):
        weight = np.clip(1 - np.abs(position - j), 0.0, 1.0)
        if weight.any():
            out += np.fft.irfft(spectrum * response(freqs, fc, 2)[:, None], len(x), axis=0) * weight[:, None]
    return out


def echo(x: np.ndarray, e: Echo, beat: int, wrap: bool) -> np.ndarray:
    """``x`` and its echoes (around the loop when ``wrap``; else cut at the buffer's end)."""
    out = x.copy()
    for k in range(1, e.repeats + 1):
        src = x[:, ::-1] if e.pingpong and k % 2 else x
        shift = round(k * e.delay * beat)
        gain = e.feedback**k
        if wrap:
            out += gain * np.roll(src, shift, axis=0)
        elif shift < len(x):
            out[shift:] += gain * src[: len(x) - shift]
    return out


def reverb(x: np.ndarray, rv: Reverb, wrap: bool, seed: str) -> np.ndarray:
    """``x`` plus a reverb tail: each side convolved with its own decaying noise (unit energy,
    so the tail's level is ``mix`` of the sound's), low-passed at ``tone`` and high-passed at
    120 Hz (no boom); circular around a loop, else the tail is cut at the buffer's end."""
    n = max(int(rv.size * RATE), 1)
    pre = int(rv.predelay * RATE)
    total = len(x) if wrap else len(x) + n + pre
    t = np.arange(n) / RATE
    envelope = np.exp(-6.91 * t / rv.size) * (1 - np.exp(-t / 0.005))
    freqs = np.fft.rfftfreq(total, 1 / RATE)
    shape = _lowpass(freqs, rv.tone, 2) * _highpass(freqs, 120.0, 2)
    rng = np.random.default_rng(zlib.crc32(seed.encode("utf-8")))
    out = x.copy()
    for c in range(2):
        tail = rng.standard_normal(n) * envelope
        tail /= math.sqrt(float(np.sum(tail**2)))
        response = np.zeros(total)
        _circular_add(response, pre, tail)
        wet = np.fft.irfft(np.fft.rfft(x[:, c], total) * np.fft.rfft(response) * shape, total)
        out[:, c] += rv.mix * wet[: len(x)]
    return out


def widen(x: np.ndarray, width: np.ndarray) -> np.ndarray:
    """Mid/side: the side signal times ``width`` (per sample)."""
    mid, side = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2 * width
    return np.stack([mid + side, mid - side], axis=1)


def duck_dip(depth: float, release: float, limit: int) -> np.ndarray:
    """One side-chain dip (as the beds' ``_pump``): ``depth`` reached in ~8 ms, recovering over
    ``release`` seconds; at most ``limit`` samples long."""
    n = min(limit, int(8 * release * RATE))
    t = np.arange(n) / RATE
    return depth * (1 - np.exp(-t / DUCK_ATTACK)) * np.exp(-t / release)


def gate_window(open_: int, level: float) -> np.ndarray:
    """The gate's opening on one hit: a 3 ms attack, open for ``open_`` samples, an 18 ms release."""
    n = open_ + int(6 * GATE_RELEASE * RATE)
    t = np.arange(n) / RATE
    hold = open_ / RATE
    return level * (1 - np.exp(-t / GATE_ATTACK)) * np.where(t < hold, 1.0, np.exp(-(t - hold) / GATE_RELEASE))
