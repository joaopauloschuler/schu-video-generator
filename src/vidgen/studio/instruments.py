"""The instrument library of score files (DESIGN.md §93.4): drums, pitched voices and pads made
from the built-in beds' building blocks (:mod:`vidgen.music`), each with settings that have a
default, a range and a sentence saying what they change (``vidgen music patches``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from vidgen.music import (
    _AIRY,
    _SAW,
    _SOFT_SAW,
    _WARM,
    _analog_bass,
    _bell,
    _clap,
    _clock,
    _fm_pluck,
    _gated_snare,
    _hat,
    _kick,
    _music_box,
    _partials,
    _piano,
    _pizzicato,
    _pluck,
    _pulsar_pulse,
    _riser,
    _shape,
    _square_pluck,
    _static,
    _synth_bass,
    _woodblock,
)
from vidgen.sfx import RATE, _band, _filtered, _lowpass, _tone

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
    by default (the chord's root in that octave; C4 is middle C); ``group``: its family in the
    catalogue (``vidgen music patches``)."""

    name: str
    kind: str
    words: str
    level: float
    octave: int | None
    settings: Mapping[str, Setting] = field(default_factory=dict)
    #: drum: ``(settings, held seconds) -> mono (n,) or stereo (n, 2)``; note: ``(Hz, samples, settings) -> mono``.
    make: Callable[..., np.ndarray] | None = None
    #: pad: harmonic amplitudes (spread by the ``detune`` setting).
    harmonics: tuple[float, ...] = ()
    group: str = ""


_DECAY = "seconds for the sound to fall to about a third"
_TONE = "low-pass in Hz: lower is darker"
_RING = "seconds the note sounds on after its held steps"


# ----- drums and noises ---------------------------------------------------------------------------


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


@lru_cache(maxsize=8)
def _snare(gate: float, body: float) -> np.ndarray:
    return _gated_snare(seed=91, gate=gate, body=body)


def _snare_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _snare(s["gate"], s["body"])


@lru_cache(maxsize=8)
def _snap(tone: float, decay: float) -> np.ndarray:
    """A soft snare-like snap (80 ms): a noise burst band-passed around ``tone`` Hz, nothing much
    above 1.8 times it (the ``cartoon`` bed's tick, ``lab``'s snap); peak 1."""
    n = int(0.08 * RATE)
    t = np.arange(n) / RATE
    burst = np.random.default_rng(31).standard_normal(n) * np.exp(-t / decay) * (1 - np.exp(-t / 0.0008))
    snap = _filtered(burst, lambda f: _band(f, tone, 0.6) * _lowpass(f, 1.8 * tone, 4))
    fade = int(0.01 * RATE)
    snap[-fade:] *= np.linspace(1, 0, fade)
    snap = snap / np.abs(snap).max()
    snap.setflags(write=False)
    return snap


def _snap_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _snap(s["tone"], s["decay"])


def _tick_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _clock(s["tone"])


def _pulsar_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _pulsar_pulse(s["high"], s["low"], s["sweep"], s["noise"], 61, s["tone"])


def _riser_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    return _riser(max(held, 0.1), s["low"], s["high"])


def _static_sound(s: Mapping[str, float], held: float) -> np.ndarray:
    """Radio static for its held steps: a sine fade-in and, after them, a cosine fade-out of
    ``fade`` seconds, so back-to-back hits join at constant power; stereo."""
    body, fade = max(int(held * RATE), 1), max(int(s["fade"] * RATE), 1)
    total = body + fade
    t = np.arange(total)
    rise = np.sin(0.5 * np.pi * np.clip((t + 0.5) / fade, 0.0, 1.0))
    fall = np.cos(0.5 * np.pi * np.clip((t - body) / fade, 0.0, 1.0))
    return _static(total, s["low"], s["high"], 77, s["wander"]) * (rise * fall)[:, None]


# ----- notes --------------------------------------------------------------------------------------


def _bass_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _synth_bass(freq, n, s["decay"], s["tone"])


def _analog_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _analog_bass(freq, n, s["decay"], s["tone"], s["closed"], s["snap"], s["detune"])


def _sub_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    partials = ((1.0, 1.0, 1.0), (2.0, s["second"], 0.6)) + (((3.0, s["third"], 0.4),) if s["third"] > 0 else ())
    return _partials(freq, n, s["decay"], 0.012, partials, s["tone"])


def _pluck_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _pluck(freq, n, s["decay"], s["bright"], s["tone"])


def _fm_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _fm_pluck(freq, n, s["decay"], s["index"], s["tone"])


def _square_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _square_pluck(freq, n, s["decay"], s["tone"])


def _pizzicato_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _pizzicato(freq, n, s["decay"], s["tone"])


def _music_box_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _music_box(freq, n, s["decay"], s["tone"])


def _woodblock_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _woodblock(freq, s["tone"])


def _bell_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _bell(freq, n, s["decay"], s["tone"])


def _piano_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    return _piano(freq, n, s["decay"], s["tone"])


def _lead_note(freq: float, n: int, s: Mapping[str, float]) -> np.ndarray:
    """A soft lead: a mellow saw-like tone (harmonics at 1/h^1.5 shaped by the beds' filter at
    ``tone``) with a vibrato of ``vibrato`` cents at 5 Hz fading in over 0.35 s, an ``attack``
    and, over its last ``ring`` seconds, a cosine release."""
    t = np.arange(n) / RATE
    wobble = s["vibrato"] / 1200 * np.sin(2 * np.pi * 5.0 * t) * np.clip(t / 0.35, 0.0, 1.0)
    phase = _tone(freq * 2**wobble, n)
    y = np.zeros(n)
    for h in range(1, 17):
        if freq * h > 2 * s["tone"]:
            break
        y += _shape(freq * h, s["tone"]) / h**1.5 * np.sin(h * phase)
    release = max(int(s["ring"] * RATE), 1)
    fall = np.cos(0.5 * np.pi * np.clip((np.arange(n) - (n - release)) / release, 0.0, 1.0))
    return y * (1 - np.exp(-t / s["attack"])) * fall / 1.6


def _settings(**items: tuple[float, float, float, str]) -> dict[str, Setting]:
    return {name: Setting(*values) for name, values in items.items()}


def _pad_settings(tone: float, air: float, detune: float, fade: float) -> dict[str, Setting]:
    return _settings(
        tone=(tone, 300.0, 6000.0, _TONE),
        air=(air, 0.0, 1.0, "level of a soft airy layer an octave up (0 off)"),
        swell=(0.0, 0.0, 512.0, "bars over which the airy layer swells from silence to `air` and back, counted from the piece's start "
               "(0: steady; a whole number of swells per piece keeps a loop seamless)"),
        sub=(0.0, 0.0, 1.0, "level of a sine-like sub bass on the chord's bass note (the written bass, else octave 2; 0 off)"),
        sub_width=(0.0, 0.0, 1.0, "0: the sub is the same wave on both sides (centred, solid in mono); 1: its own phases on each side "
                   "(wider, thinner in mono; how scores rendered before Step 186)"),
        attack=(0.08, 0.005, 2.0, "seconds to fade in a note played in steps (play: chords cross-fades instead, see fade)"),
        release=(0.4, 0.02, 3.0, "seconds to fade out after a note played in steps"),
        detune=(detune, 2.0, 80.0, "spread of each harmonic in cents: more is wider, more chorused"),
        fade=(fade, 0.05, 4.0, "play: chords: seconds of the cross-fade from one chord to the next"),
    )


def _drum(name: str, words: str, level: float, settings: dict[str, Setting], make: Callable[..., np.ndarray], group: str) -> Instrument:
    return Instrument(name, "drum", words, level, None, settings, make, group=group)


def _voice(name: str, words: str, level: float, octave: int, settings: dict[str, Setting], make: Callable[..., np.ndarray], group: str) -> Instrument:
    return Instrument(name, "note", words, level, octave, settings, make, group=group)


def _pad(name: str, words: str, level: float, octave: int, harmonics: tuple[float, ...], settings: dict[str, Setting]) -> Instrument:
    return Instrument(name, "pad", words, level, octave, settings, harmonics=harmonics, group="pads")


#: The instrument library by name, in catalogue order (drums, noises, basses, plucks and keys, leads, pads).
INSTRUMENTS: dict[str, Instrument] = {
    i.name: i
    for i in (
        _drum("kick", "a soft electronic kick: a sine gliding from `high` to `low` Hz, a faint click", 0.75,
              _settings(high=(92.0, 60.0, 160.0, "start pitch in Hz"), low=(47.0, 35.0, 70.0, "end pitch in Hz"),
                        decay=(0.16, 0.05, 0.6, _DECAY), click=(0.06, 0.0, 0.3, "level of the click")), _kick_sound, "drums"),
        _drum("clap", "a soft clap: noise around `tone` Hz with a short low body", 0.13,
              _settings(tone=(1300.0, 600.0, 3000.0, "centre of the noise in Hz")), _clap_sound, "drums"),
        _drum("hat", "a soft closed hi-hat: a short noise burst, 4.5-9 kHz", 0.06,
              _settings(decay=(0.022, 0.008, 0.08, _DECAY), tone=(6500.0, 4500.0, 9000.0, "centre in Hz")), _hat_sound, "drums"),
        _drum("open_hat", "an open hi-hat: a longer noise burst, 4.5-9 kHz", 0.07,
              _settings(decay=(0.05, 0.02, 0.2, _DECAY), tone=(7000.0, 4500.0, 9000.0, "centre in Hz")), _open_hat_sound, "drums"),
        _drum("gated_snare", "an 80s gated-reverb snare: a crack, a falling body tone and a wide noise room cut off after `gate` s (stereo)", 0.12,
              _settings(gate=(0.24, 0.08, 0.6, "seconds the room is held before it is cut"), body=(190.0, 120.0, 320.0, "pitch of the body in Hz")),
              _snare_sound, "drums"),
        _drum("snap", "a soft snare-like snap: a short noise burst around `tone` Hz", 0.08,
              _settings(tone=(1800.0, 800.0, 4000.0, "centre of the noise in Hz"), decay=(0.012, 0.004, 0.05, _DECAY)), _snap_sound, "drums"),
        _drum("tick", "a clock tick: a 4 ms click with a little ring at `tone` Hz", 0.04,
              _settings(tone=(3600.0, 1500.0, 6000.0, "pitch of the ring in Hz")), _tick_sound, "drums"),
        _drum("boom", "a deep low boom (2.4 s) to mark a lift", 0.5,
              _settings(low=(38.0, 30.0, 60.0, "pitch in Hz"), decay=(0.8, 0.2, 2.0, _DECAY)), _boom_sound, "drums"),
        _drum("riser", "a noise riser: noise sweeping from `low` to `high` Hz and swelling until its held steps end", 0.07,
              _settings(low=(300.0, 100.0, 2000.0, "start in Hz"), high=(2500.0, 800.0, 6000.0, "end in Hz")), _riser_sound, "noises"),
        _drum("pulsar", "a pulsar tick: a radio pulsar's pulse as sound, a short chirp falling from `high` to `low` Hz with a burst of static", 0.15,
              _settings(high=(1400.0, 300.0, 3000.0, "start of the chirp in Hz"), low=(160.0, 60.0, 600.0, "end of the chirp in Hz"),
                        sweep=(0.035, 0.01, 0.15, "seconds of the chirp"), noise=(0.6, 0.0, 1.5, "level of the static burst"),
                        tone=(1800.0, 800.0, 5000.0, _TONE)), _pulsar_sound, "noises"),
        _drum("static", "soft stereo radio static for its held steps (hold it: \"x | - | - | -\"), its level wandering slowly", 0.008,
              _settings(low=(1800.0, 200.0, 4000.0, "lowest frequency in Hz"), high=(4200.0, 1000.0, 9000.0, "highest frequency in Hz"),
                        wander=(1.5, 0.2, 6.0, "seconds over which the level wanders"), fade=(0.3, 0.02, 3.0, "seconds of fade in and out")),
              _static_sound, "noises"),
        _voice("synth_bass", "a warm saw-like synth bass whose upper harmonics die first", 0.45, 2,
               _settings(decay=(0.1, 0.03, 1.0, _DECAY), tone=(600.0, 200.0, 2000.0, _TONE), ring=(0.05, 0.0, 2.0, _RING)), _bass_note, "basses"),
        _voice("analog_bass", "an analog-style bass: two detuned saws through a low-pass closing from `tone` to `closed` Hz", 0.32, 2,
               _settings(decay=(0.12, 0.03, 1.0, _DECAY), tone=(1400.0, 300.0, 4000.0, "filter cutoff at the attack in Hz"),
                         closed=(260.0, 80.0, 1500.0, "filter cutoff it closes to in Hz"), snap=(0.05, 0.01, 0.5, "seconds the filter takes to close"),
                         detune=(7.0, 0.0, 30.0, "cents between the two saws"), ring=(0.05, 0.0, 2.0, _RING)), _analog_note, "basses"),
        _voice("sub", "a deep sine-like sub bass with a little second harmonic", 0.5, 1,
               _settings(decay=(0.3, 0.05, 2.0, _DECAY), tone=(600.0, 200.0, 1500.0, _TONE), second=(0.18, 0.0, 1.0, "level of the second harmonic"),
                         third=(0.0, 0.0, 1.0, "level of the third harmonic"), ring=(0.1, 0.0, 2.0, _RING)), _sub_note, "basses"),
        _voice("pluck", "a soft plucked synth note: a sine with a little second and third harmonic", 0.35, 4,
               _settings(decay=(0.22, 0.05, 1.5, _DECAY), bright=(0.5, 0.0, 1.0, "level of the upper harmonics"),
                         tone=(3000.0, 800.0, 6000.0, _TONE), ring=(0.8, 0.0, 4.0, _RING)), _pluck_note, "plucks and keys"),
        _voice("fm_pluck", "a bright electronic FM pluck that settles into a sine", 0.2, 4,
               _settings(decay=(0.16, 0.05, 1.0, _DECAY), index=(1.6, 0.0, 5.0, "brightness of the blip"),
                         tone=(2600.0, 800.0, 6000.0, _TONE), ring=(0.4, 0.0, 3.0, _RING)), _fm_note, "plucks and keys"),
        _voice("square_pluck", "a retro square-ish pluck: odd harmonics, the upper ones dying first", 0.09, 5,
               _settings(decay=(0.09, 0.03, 1.0, _DECAY), tone=(2200.0, 800.0, 6000.0, _TONE), ring=(0.2, 0.0, 2.0, _RING)), _square_note, "plucks and keys"),
        _voice("pizzicato", "a plucked string (pizzicato): a woody body of five harmonics", 0.3, 4,
               _settings(decay=(0.25, 0.05, 1.5, _DECAY), tone=(2400.0, 800.0, 6000.0, _TONE), ring=(0.5, 0.0, 3.0, _RING)), _pizzicato_note, "plucks and keys"),
        _voice("music_box", "a music-box tine with a slow shimmer and a faint high ping", 0.18, 5,
               _settings(decay=(0.6, 0.1, 3.0, _DECAY), tone=(4000.0, 1000.0, 8000.0, _TONE), ring=(1.5, 0.0, 6.0, _RING)), _music_box_note, "plucks and keys"),
        _voice("woodblock", "a small woodblock tock (60 ms) at the note's pitch", 0.15, 5,
               _settings(tone=(3000.0, 800.0, 6000.0, _TONE)), _woodblock_note, "plucks and keys"),
        _voice("bell", "a soft glockenspiel-like bell", 0.22, 5,
               _settings(decay=(0.5, 0.1, 3.0, _DECAY), tone=(3000.0, 1000.0, 6000.0, _TONE), ring=(1.6, 0.0, 6.0, _RING)), _bell_note, "plucks and keys"),
        _voice("piano", "a soft piano-like note with slightly stretched harmonics", 0.26, 4,
               _settings(decay=(0.7, 0.1, 3.0, _DECAY), tone=(2400.0, 800.0, 6000.0, _TONE), ring=(2.2, 0.0, 6.0, _RING)), _piano_note, "plucks and keys"),
        _voice("soft_lead", "a soft, mellow lead for melodies: a saw-like tone with a gentle vibrato; it sustains while held", 0.15, 5,
               _settings(attack=(0.03, 0.003, 1.0, "seconds to fade in"), vibrato=(12.0, 0.0, 50.0, "vibrato depth in cents (5 Hz)"),
                         tone=(2400.0, 600.0, 6000.0, _TONE), ring=(0.25, 0.02, 3.0, "seconds of the release after its held steps")), _lead_note, "leads"),
        _pad("pad", "a warm, wide synthesizer-string pad (PADsynth), with an optional airy layer and sub", 0.3, 3, _WARM,
             _pad_settings(2600.0, 0.25, 18.0, 1.6)),
        _pad("supersaw", "supersaw-like chords: a cloud of detuned saws, wide (sweep it with lowpass, gate it, duck it)", 0.2, 3, _SAW,
             _pad_settings(2400.0, 0.0, 28.0, 1.6)),
        _pad("saw_pad", "a softer saw pad: warm, slightly hollow synthwave strings", 0.24, 3, _SOFT_SAW, _pad_settings(1700.0, 0.0, 24.0, 0.5)),
        _pad("glass", "a glassy shimmer: chords as near-sines spread wide, high and quiet", 0.06, 5, (1.0, 0.25, 0.08), _pad_settings(4200.0, 0.0, 45.0, 0.8)),
    )
}

#: The airy layer of the pads (an octave up, wider).
AIRY_HARMONICS, AIRY_WIDTH_CENTS = _AIRY, 30.0
#: The catalogue's families in order.
GROUPS = ("drums", "noises", "basses", "plucks and keys", "leads", "pads")
