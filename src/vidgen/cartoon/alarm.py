"""An alarm on a stage and the shutters of an iso room (DESIGN.md §100.7): the maths, no manim.

While an alarm runs (the ``alarm`` action: ``start`` .. ``stop``) the stage's light is a dark room
lit by a red light that rises and falls (:func:`alarm_grade`): between pulses the set is dark
(:data:`ALARM_DARK`), at each pulse's top it glows in the alarm's colour, a beacon sweeping by;
it fades in over :data:`ALARM_RISE` and back to the stage's own light over :data:`ALARM_FALL`.
What the light never grades (a portal, a hologram, a lit screen) keeps shining over it.

Shutters close over an iso room's windows (``shutters: close``) in :data:`SHUTTER_CLOSE_SECONDS`
(a slam) and roll up again (``shutters: open``) in :data:`SHUTTER_OPEN_SECONDS`
(:func:`shutter_level`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from vidgen.cartoon.lighting import LightGrade, blend_grades, tint_grade
from vidgen.lint.color import hex_rgb

#: The alarm's colour, the seconds of one pulse (dark, red, dark), and its fades (s).
ALARM_COLOR = "#FF2A1F"
ALARM_PERIOD = 1.6
ALARM_RISE = 0.4
ALARM_FALL = 0.8
#: The dark between the pulses: a tint and its strength (the set barely seen).
ALARM_DARK = ("#2B1B26", 0.82)
#: The light at a pulse's top: the strength of the alarm colour's tint and the glow it adds
#: (a share of the colour), so red reads as a light, not as paint.
ALARM_STRENGTH = 0.82
ALARM_GLOW = 0.06
#: How bright the pulse's top is (a factor on its multiply: the room stays dim, lit red).
ALARM_BRIGHTNESS = 0.72
#: How sharp the pulse is (an exponent on a raised cosine: above 1 it is short and bright, like a
#: rotating beacon passing).
ALARM_SHARPNESS = 2.0


@dataclass(frozen=True)
class AlarmSpan:
    """An alarm from scene time ``start`` to ``end`` (``None``: to the scene's end), pulsing in
    ``color`` (#hex) every ``period`` seconds."""

    start: float
    end: float | None
    color: str = ALARM_COLOR
    period: float = ALARM_PERIOD

    def over_at(self) -> float:
        """When it has faded out completely (``inf`` while it runs to the scene's end)."""
        return math.inf if self.end is None else self.end + ALARM_FALL


def alarm_spans(changes: Sequence[tuple[float, bool, str, float]]) -> list[AlarmSpan]:
    """The alarm's spans from its changes ``(scene time, on, color, period)`` (an ``alarm``
    action each): a ``start`` while it runs ends that span and starts one in its own colour and
    period (the two cross-fade); a ``stop`` while it is off does nothing."""
    spans: list[AlarmSpan] = []
    running: tuple[float, str, float] | None = None
    for time, on, color, period in sorted(changes, key=lambda c: c[0]):
        if running is not None:
            spans.append(AlarmSpan(running[0], float(time), running[1], running[2]))
            running = None
        if on:
            running = (float(time), color, float(period))
    if running is not None:
        spans.append(AlarmSpan(running[0], None, running[1], running[2]))
    return [s for s in spans if s.end is None or s.end > s.start]


def alarm_envelope(span: AlarmSpan, now: float) -> float:
    """How strongly ``span`` shows at scene time ``now`` (0..1): rising over :data:`ALARM_RISE`
    from its start, falling over :data:`ALARM_FALL` after its end."""
    if now < span.start:
        return 0.0
    rise = min((now - span.start) / ALARM_RISE, 1.0)
    fall = 1.0 if span.end is None or now <= span.end else max(1.0 - (now - span.end) / ALARM_FALL, 0.0)
    return _smooth(min(rise, fall))


def alarm_pulse(span: AlarmSpan, now: float) -> float:
    """The red light's level at scene time ``now`` (0 dark .. 1 the pulse's top): a raised cosine
    of ``period`` starting dark, sharpened by :data:`ALARM_SHARPNESS`."""
    phase = (now - span.start) / max(span.period, 1e-6)
    return (0.5 - 0.5 * math.cos(2.0 * math.pi * phase)) ** ALARM_SHARPNESS


def _smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def alarm_light(color: str, pulse: float) -> LightGrade:
    """The alarm's own light at ``pulse`` (0..1): from the dark (:data:`ALARM_DARK`) to the
    colour's tint with its glow."""
    r, g, b = hex_rgb(color)
    tint = tint_grade(color, ALARM_STRENGTH)
    peak = LightGrade(tuple(m * ALARM_BRIGHTNESS for m in tint.multiply), (ALARM_GLOW * r, ALARM_GLOW * g, ALARM_GLOW * b))  # type: ignore[arg-type]
    return blend_grades(tint_grade(*ALARM_DARK), peak, pulse)


def alarm_grade(base: LightGrade, spans: Sequence[AlarmSpan], now: float) -> LightGrade:
    """``base`` (the stage's light now) under the alarms ``spans`` at scene time ``now``: the
    strongest span's light (:func:`alarm_light` at its pulse), as far as its envelope; ``base``
    while none runs. The stars and shadows of ``base`` fade with it."""
    best = max(((alarm_envelope(s, now), s) for s in spans), key=lambda e: e[0], default=(0.0, None))
    level, span = best
    if span is None or level <= 0.0:
        return base
    light = alarm_light(span.color, alarm_pulse(span, now))
    light = LightGrade(light.multiply, light.glow, base.stars * (1.0 - level), base.shadow)
    return blend_grades(base, light, level)


def alarm_changing(spans: Sequence[AlarmSpan], start: float, end: float) -> bool:
    """Whether an alarm shows anything between scene times ``start`` and ``end`` (its light
    pulses on every frame)."""
    return any(s.start < end and s.over_at() > start for s in spans)


def alarm_settled(spans: Sequence[AlarmSpan], now: float) -> bool:
    """Whether every alarm has faded out by scene time ``now``."""
    return all(s.over_at() <= now for s in spans)


#: Shutters: seconds to slam down and to roll up.
SHUTTER_CLOSE_SECONDS = 0.5
SHUTTER_OPEN_SECONDS = 1.4


def shutter_level(closed_at_start: bool, moves: Sequence[tuple[float, bool]], now: float) -> float:
    """How far the shutters are down at scene time ``now`` (0 open .. 1 closed): each move
    ``(scene time, close)`` goes from where they are, down in :data:`SHUTTER_CLOSE_SECONDS`
    (accelerating, as they drop) or up in :data:`SHUTTER_OPEN_SECONDS` (eased)."""
    level = 1.0 if closed_at_start else 0.0
    ordered = sorted(moves, key=lambda m: m[0])
    for k, (time, close) in enumerate(ordered):
        if now < time:
            break
        until = min(now, ordered[k + 1][0]) if k + 1 < len(ordered) else now
        seconds = SHUTTER_CLOSE_SECONDS if close else SHUTTER_OPEN_SECONDS
        share = min(max((until - time) / seconds, 0.0), 1.0)
        if close:
            level = level + (1.0 - level) * share * share
        else:
            level = level * (1.0 - _smooth(share))
    return min(max(level, 0.0), 1.0)


def shutters_changing(moves: Sequence[tuple[float, bool]], start: float, end: float) -> bool:
    """Whether the shutters move between scene times ``start`` and ``end``."""
    return any(time < end and time + (SHUTTER_CLOSE_SECONDS if close else SHUTTER_OPEN_SECONDS) > start for time, close in moves)


__all__ = [
    "ALARM_COLOR",
    "ALARM_DARK",
    "ALARM_FALL",
    "ALARM_PERIOD",
    "ALARM_RISE",
    "SHUTTER_CLOSE_SECONDS",
    "SHUTTER_OPEN_SECONDS",
    "AlarmSpan",
    "alarm_changing",
    "alarm_envelope",
    "alarm_grade",
    "alarm_light",
    "alarm_pulse",
    "alarm_settled",
    "alarm_spans",
    "shutter_level",
    "shutters_changing",
]
