"""The starter instruments of score files (DESIGN.md §93): drums, pitched voices and pads made
from the built-in beds' building blocks (:mod:`vidgen.music`), each with a few settings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np

from vidgen.music import _AIRY, _SAW, _WARM, _bell, _clap, _fm_pluck, _hat, _kick, _partials, _piano, _pluck, _riser, _synth_bass

#: Instrument kinds: ``drum`` (no pitch: hits), ``note`` (one sound per note, a chord is its
#: notes together), ``pad`` (sustained chords, cross-faded; can also play held notes).
KINDS = ("drum", "note", "pad")


@dataclass(frozen=True)
class Setting:
    """An instrument setting: its default, allowed range and what it changes."""

    default: float
    low: float
    high: float
    words: str


@dataclass(frozen=True)
class Instrument:
    """A score instrument. ``level``: the amplitude of a normal hit at ``volume: 0`` before the
    piece is set to -28 LUFS (the balance between instruments); ``octave``: where its notes sit
    by default (the chord's root in that octave; C4 is middle C)."""

    name: str
    kind: str
    words: str
    level: float
    octave: int | None
    settings: Mapping[str, Setting] = field(default_factory=dict)
    #: drum: ``(settings, held seconds) -> mono``; note: ``(Hz, samples, settings) -> mono``.
    make: Callable[..., np.ndarray] | None = None
    #: pad: harmonic amplitudes and their spread in cents.
    harmonics: tuple[float, ...] = ()
    width_cents: float = 0.0


_DECAY = "seconds for the sound to fall to about a third"
_TONE = "low-pass in Hz: lower is darker"
_RING = "seconds the note sounds on after its held steps"


def _kick_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _kick(f_hi=s["high"], f_lo=s["low"], tau=s["decay"], click=s["click"])


def _boom_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _kick(f_hi=70.0, f_lo=s["low"], tau=s["decay"], click=0.02, seconds=2.4)


def _clap_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _clap(center=s["tone"])


def _hat_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _hat(seed=3, tau=s["decay"], center=s["tone"])


def _open_hat_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _hat(seed=5, tau=s["decay"], center=s["tone"])


def _riser_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _riser(max(held, 0.1), s["low"], s["high"])


def _bass_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _synth_bass(freq, n, s["decay"], s["tone"])


def _sub_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _partials(freq, n, s["decay"], 0.012, ((1.0, 1.0, 1.0), (2.0, 0.18, 0.6)), s["tone"])


def _pluck_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _pluck(freq, n, s["decay"], s["bright"], s["tone"])


def _fm_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _fm_pluck(freq, n, s["decay"], s["index"], s["tone"])


def _bell_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _bell(freq, n, s["decay"], s["tone"])


def _piano_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _piano(freq, n, s["decay"], s["tone"])


def _settings(**items: tuple[float, float, float, str]) -> dict[str, Setting]:
    return {name: Setting(*values) for name, values in items.items()}


_PAD_SETTINGS = dict(
    tone=(2600.0, 300.0, 6000.0, _TONE),
    air=(0.25, 0.0, 1.0, "level of a soft airy layer an octave up (0 off)"),
    sub=(0.0, 0.0, 1.0, "level of a sine-like sub bass on the chord's bass note in octave 2 (0 off)"),
    attack=(0.08, 0.005, 2.0, "seconds to fade in a held note (play: chords cross-fades chords over 1.6 s)"),
    release=(0.4, 0.02, 3.0, "seconds to fade out after a held note"),
)

#: The starter instruments by name.
INSTRUMENTS: dict[str, Instrument] = {
    i.name: i
    for i in (
        Instrument(
            "kick", "drum", "a soft electronic kick: a sine gliding from `high` to `low` Hz, a faint click", 0.75, None,
            _settings(high=(92.0, 60.0, 160.0, "start pitch in Hz"), low=(47.0, 35.0, 70.0, "end pitch in Hz"),
                      decay=(0.16, 0.05, 0.6, _DECAY), click=(0.06, 0.0, 0.3, "level of the click")),
            _kick_sound,
        ),
        Instrument("clap", "drum", "a soft clap: noise around `tone` Hz with a short low body", 0.13, None,
                   _settings(tone=(1300.0, 600.0, 3000.0, "centre of the noise in Hz")), _clap_sound),
        Instrument("hat", "drum", "a soft closed hi-hat: a short noise burst, 4.5-9 kHz", 0.06, None,
                   _settings(decay=(0.022, 0.008, 0.08, _DECAY), tone=(6500.0, 4500.0, 9000.0, "centre in Hz")), _hat_sound),
        Instrument("open_hat", "drum", "an open hi-hat: a longer noise burst, 4.5-9 kHz", 0.07, None,
                   _settings(decay=(0.05, 0.02, 0.2, _DECAY), tone=(7000.0, 4500.0, 9000.0, "centre in Hz")), _open_hat_sound),
        Instrument("riser", "drum", "a noise riser: noise sweeping from `low` to `high` Hz and swelling until its held steps end", 0.07, None,
                   _settings(low=(300.0, 100.0, 2000.0, "start in Hz"), high=(2500.0, 800.0, 6000.0, "end in Hz")), _riser_sound),
        Instrument("boom", "drum", "a deep low boom (2.4 s) to mark a lift", 0.5, None,
                   _settings(low=(38.0, 30.0, 60.0, "pitch in Hz"), decay=(0.8, 0.2, 2.0, _DECAY)), _boom_sound),
        Instrument(
            "synth_bass", "note", "a warm saw-like synth bass whose upper harmonics die first", 0.45, 2,
            _settings(decay=(0.1, 0.03, 1.0, _DECAY), tone=(600.0, 200.0, 2000.0, _TONE), ring=(0.05, 0.0, 2.0, _RING)),
            _bass_note,
        ),
        Instrument(
            "sub", "note", "a deep sine-like sub bass with a little second harmonic", 0.5, 1,
            _settings(decay=(0.3, 0.05, 2.0, _DECAY), tone=(600.0, 200.0, 1500.0, _TONE), ring=(0.1, 0.0, 2.0, _RING)),
            _sub_note,
        ),
        Instrument(
            "pluck", "note", "a soft plucked synth note: a sine with a little second and third harmonic", 0.35, 4,
            _settings(decay=(0.22, 0.05, 1.5, _DECAY), bright=(0.5, 0.0, 1.0, "level of the upper harmonics"),
                      tone=(3000.0, 800.0, 6000.0, _TONE), ring=(0.8, 0.0, 4.0, _RING)),
            _pluck_note,
        ),
        Instrument(
            "fm_pluck", "note", "a bright electronic FM pluck that settles into a sine", 0.2, 4,
            _settings(decay=(0.16, 0.05, 1.0, _DECAY), index=(1.6, 0.0, 5.0, "brightness of the blip"),
                      tone=(2600.0, 800.0, 6000.0, _TONE), ring=(0.4, 0.0, 3.0, _RING)),
            _fm_note,
        ),
        Instrument(
            "bell", "note", "a soft glockenspiel-like bell", 0.22, 5,
            _settings(decay=(0.5, 0.1, 3.0, _DECAY), tone=(3000.0, 1000.0, 6000.0, _TONE), ring=(1.6, 0.0, 6.0, _RING)),
            _bell_note,
        ),
        Instrument(
            "piano", "note", "a soft piano-like note with slightly stretched harmonics", 0.26, 4,
            _settings(decay=(0.7, 0.1, 3.0, _DECAY), tone=(2400.0, 800.0, 6000.0, _TONE), ring=(2.2, 0.0, 6.0, _RING)),
            _piano_note,
        ),
        Instrument("pad", "pad", "a warm, wide synthesizer-string pad (PADsynth), with an optional airy layer and sub", 0.3, 3,
                   _settings(**_PAD_SETTINGS), harmonics=_WARM, width_cents=18.0),
        Instrument("supersaw", "pad", "supersaw-like chords: a cloud of detuned saws, wide", 0.2, 3,
                   _settings(**{**_PAD_SETTINGS, "tone": (2400.0, 300.0, 6000.0, _TONE), "air": (0.0, 0.0, 1.0, _PAD_SETTINGS["air"][3])}),
                   harmonics=_SAW, width_cents=28.0),
    )
}

#: The airy layer of the pads (an octave up, wider).
AIRY_HARMONICS, AIRY_WIDTH_CENTS = _AIRY, 30.0
