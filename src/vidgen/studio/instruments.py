"""The instrument library of score files: drums, pitched voices and pads made
from the built-in beds' building blocks (:mod:`vidgen.music`), each with settings that have a
default, a range and a sentence saying what they change (``vidgen music patches``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

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
from vidgen.studio.additive import Phrase, phrase_pitch, phrase_tone
from vidgen.studio.brass import horn_note, low_brass_note, trumpet_note
from vidgen.studio.choir import MORPHS, VOICES, VOWELS
from vidgen.studio.singing import SYLLABLES, choir_note, read_yes_no
from vidgen.studio.organ import REGISTRATION_NAMES, REGISTRATIONS, organ_note, read_drawbars
from vidgen.studio.percussion import (
    bass_drum_sound,
    cymbal_sound,
    frame_drum_sound,
    snare_drum_sound,
    taiko_sound,
    tam_tam_sound,
    timpani_note,
    toms_note,
)
from vidgen.studio.strings import STROKES, basses_note, cellos_note, violas_note, violins_note

#: Instrument kinds: ``drum`` (no pitch: hits), ``note`` (one sound per note, a chord is its
#: notes together), ``pad`` (sustained chords, cross-faded; can also play held notes).
KINDS = ("drum", "note", "pad")


@dataclass(frozen=True)
class Setting:
    """An instrument setting: its default, allowed range and what it changes. A setting is a
    number in the score; two kinds may be written another way. ``choices``: names for the whole
    numbers from 0 (``registration: flute``; the number is accepted too). ``read``: a function
    ``(value, where) -> number`` for a value with its own notation (the organ's ``drawbars``),
    raising :class:`~vidgen.errors.VidgenError` for one it cannot read."""

    default: float
    low: float
    high: float
    words: str
    choices: tuple[str, ...] = ()
    read: Callable[[Any, str], float] | None = None


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
    #: drum: ``(settings, held seconds) -> mono (n,) or stereo (n, 2)``; note: ``(Hz, samples,
    #: settings) -> mono or stereo``, with ``seeded`` ``(Hz, samples, settings, seed text)``.
    make: Callable[..., np.ndarray] | None = None
    #: pad: harmonic amplitudes (spread by the ``detune`` setting).
    harmonics: tuple[float, ...] = ()
    group: str = ""
    #: note: ``make`` takes a seed (the score's seed and the track's name), so two tracks in
    #: unison are two players, not one twice as loud.
    seeded: bool = False
    #: The lowest and highest note it is meant for (``("E3", "C6")``); notes outside are played
    #: (and reported: :func:`vidgen.studio.render.range_warnings`).
    range: tuple[str, str] | None = None
    #: Its response to dynamics: ``(settings, dB) -> settings`` as it plays a
    #: note ``dB`` louder than an unmarked one (brighter, harder; the level is the renderer's).
    #: ``None``: a dynamic changes its level only.
    respond: Callable[[Mapping[str, float], float], Mapping[str, float]] | None = None
    #: note: ``(settings) -> bool``, whether it can slur with these settings; its ``make`` then
    #: takes ``phrase=`` (:data:`vidgen.studio.additive.Phrase`). ``None``: it cannot slur.
    slurs: Callable[[Mapping[str, float]], bool] | None = None


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


def _lead_note(freq: float, n: int, s: Mapping[str, float], phrase: Phrase = ()) -> np.ndarray:
    """A soft lead: a mellow saw-like tone (harmonics at 1/h^1.5 shaped by the beds' filter at
    ``tone``) with a vibrato of ``vibrato`` cents at ``vibrato_speed`` Hz fading in over 0.35 s
    from ``vibrato_delay`` on, an ``attack`` and, over its last ``ring`` seconds, a cosine
    release. ``phrase``: the notes slurred to it (one tone gliding from pitch to pitch)."""
    t = np.arange(n) / RATE
    wobble = s["vibrato"] / 1200 * np.sin(2 * np.pi * s["vibrato_speed"] * t) * np.clip((t - s["vibrato_delay"]) / 0.35, 0.0, 1.0)
    phase = _tone(freq * 2**wobble if not phrase else freq * 2 ** (wobble + phrase_pitch(n, phrase) / 12), n)

    def voiced(semitones: float, first: int, last: int) -> np.ndarray:
        hz = freq * 2 ** (semitones / 12) if semitones else freq
        y = np.zeros(last - first)
        for h in range(1, 17):
            if hz * h > 2 * s["tone"]:
                break
            y += _shape(hz * h, s["tone"]) / h**1.5 * np.sin(h * phase[first:last])
        return y

    y = voiced(0.0, 0, n) if not phrase else phrase_tone(n, phrase, 0, voiced)
    release = max(int(s["ring"] * RATE), 1)
    fall = np.cos(0.5 * np.pi * np.clip((np.arange(n) - (n - release)) / release, 0.0, 1.0))
    return y * (1 - np.exp(-t / s["attack"])) * fall / 1.6


def _settings(**items: tuple[Any, ...]) -> dict[str, Setting]:
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


def _struck_drum(name: str, words: str, level: float, settings: dict[str, Setting], make: Callable[..., np.ndarray]) -> Instrument:
    """An orchestral drum or metal: a ``drum`` whose blow is harder the louder it is played."""
    return Instrument(name, "drum", words, level, None, {**settings, **_settings(touch=_TOUCH)}, make, group="percussion", respond=_struck_respond)


def _voice(name: str, words: str, level: float, octave: int, settings: dict[str, Setting], make: Callable[..., np.ndarray], group: str) -> Instrument:
    return Instrument(name, "note", words, level, octave, settings, make, group=group)


def _orchestral(name: str, words: str, level: float, octave: int, low: str, high: str, settings: dict[str, Setting],
                make: Callable[..., np.ndarray], group: str, respond: Callable[..., Mapping[str, float]] | None = None,
                slurs: Callable[[Mapping[str, float]], bool] | None = None) -> Instrument:
    return Instrument(name, "note", words, level, octave, settings, make, group=group, seeded=True, range=(low, high), respond=respond, slurs=slurs)


# ----- expression ----------------------------------------------------------------

_TOUCH = (0.0, 0.0, 1.0, "how much an accent or a soft note (X, o, !, ?, the accent: groups) changes the tone as well as the level: 0 the level only, "
          "1 as a dynamic mark of the same level ([f], [p]) would")
_GLIDE = "seconds a slurred note \"(A4 - C5 -)\" takes to reach its pitch: 0.03-0.08 a clean legato, 0.15-0.4 a portamento (it begins before the note's step)"


def _vibrato(speed: float, delay: float) -> dict[str, tuple[Any, ...]]:
    return {
        "vibrato_speed": (speed, 2.0, 10.0, "vibrato speed in Hz (4.5 slow and wide, 5-6 usual, 7 nervous)"),
        "vibrato_delay": (delay, 0.0, 3.0, "seconds a note sounds before its vibrato begins (0: from the start; 0.5-1: only long notes get any)"),
    }


def _always(settings: Mapping[str, float]) -> bool:
    return True


def _bowed(settings: Mapping[str, float]) -> bool:
    """Strings slur while the bow stays on the string: sustained and tremolo notes."""
    return STROKES[int(settings["stroke"])] in ("sustain", "tremolo")


def _moved(settings: Mapping[str, float], **to: float) -> Mapping[str, float]:
    return {**settings, **to}


def _brass_respond(s: Mapping[str, float], db: float) -> Mapping[str, float]:
    """Blown harder, brass is brighter: 0.03 of ``brightness`` per dB (pp: -0.45, ff: +0.2)."""
    return _moved(s, brightness=float(np.clip(s["brightness"] + 0.03 * db, 0.0, 1.15)))


def _string_respond(s: Mapping[str, float], db: float) -> Mapping[str, float]:
    """More bow: brighter, and a harder bite at the start of the stroke."""
    return _moved(s, brightness=float(np.clip(s["brightness"] + 0.016 * db, 0.0, 1.0)), accent=float(np.clip(s["accent"] + 0.07 * db, 0.0, 2.0)))


def _choir_respond(s: Mapping[str, float], db: float) -> Mapping[str, float]:
    """Sung louder, the voices have more upper harmonics (full voice against a covered one)."""
    return _moved(s, brightness=float(np.clip(s["brightness"] + 0.035 * db, 0.0, 1.0)))


def _struck_respond(s: Mapping[str, float], db: float) -> Mapping[str, float]:
    """Struck harder: a harder blow (``mallet``), and the head stretched further where it has a ``drop``."""
    moved = _moved(s, mallet=float(np.clip(s["mallet"] + 0.025 * db, 0.0, 1.0)))
    return _moved(moved, drop=float(np.clip(s["drop"] * 10 ** (db / 40), 0.0, 4.0))) if "drop" in s else moved


def _brass_settings(attack: float, brightness: float, vibrato: float, ring: float, **more: tuple[Any, ...]) -> dict[str, Setting]:
    return _settings(
        attack=(attack, 0.01, 4.0, "seconds to reach full level: 0.02-0.06 tongued (hard, with a short accent), 0.15-0.4 soft, 1 and more a swell "
                "that opens as it grows"),
        brightness=(brightness, 0.0, 1.0, "how hard it is blown: 0 round and dark (pianissimo), 1 blaring (fortissimo); the level stays, the "
                    "harmonics change"),
        vibrato=(vibrato, 0.0, 40.0, "vibrato depth in cents; it begins `vibrato_delay` s into a note, so short notes have none"),
        **_vibrato(5.3, 0.28),
        breath=(1.0, 0.0, 4.0, "level of the breath noise (1 natural, 0 none)"),
        ring=(ring, 0.03, 2.0, "seconds of the release after its held steps"),
        glide=(0.06, 0.01, 1.0, _GLIDE),
        touch=_TOUCH,
        **more,
    )


_MUTE = (0.0, 0.0, 1.0, "a straight mute: 0 open, 1 muted (thin, nasal, a little quieter)")
_PLAYERS = "players in unison: 1 a solo (mono), more a section spread from left to right"
_SECTION_DETUNE = "cents the players of a section are apart"


def _string_settings(players: float) -> dict[str, Setting]:
    return _settings(
        stroke=(0.0, 0.0, float(len(STROKES) - 1), "how it is played: sustain: bowed for as long as its steps hold it; spiccato: one short bounced stroke per "
                "note, the same every time (for ostinatos; `length` 0.15 is a staccato); tremolo: a held note of fast bow strokes (`speed`); pizzicato: "
                "plucked, ringing until its steps end", STROKES),
        players=(players, 1.0, 12.0, "players in unison: 1 a solo (mono), more a section spread from left to right (each with its own instrument, "
                 "tuning, vibrato and timing; as loud as one player)"),
        attack=(0.1, 0.02, 4.0, "sustain, tremolo: seconds to reach full level: 0.03-0.06 a firm stroke with a bite, 0.1-0.3 smooth, 0.5 and more a swell"),
        brightness=(0.5, 0.0, 1.0, "where the bow is: 0 over the fingerboard (sul tasto: dark, flute-like), 0.5 ordinary, 1 at the bridge (sul ponticello: "
                    "glassy, thin); the level stays"),
        vibrato=(12.0, 0.0, 50.0, "sustain: vibrato depth in cents; it begins `vibrato_delay` s into a note and takes 0.35 s to grow, so short notes have none"),
        **_vibrato(5.8, 0.16),
        accent=(1.0, 0.0, 2.0, "the bite at the start of a stroke (0 none, 1 natural, 2 hard): scratch, a short overshoot, more highs; tremolo: how deep each "
                "stroke dips; pizzicato: how hard it is plucked"),
        length=(0.07, 0.03, 0.4, "spiccato: seconds the bow stays on the string (0.05 light and bounced, 0.07 spiccato, 0.15-0.25 staccato to marcato)"),
        speed=(13.0, 6.0, 20.0, "tremolo: bow strokes per second (the players of a section each a little off, so a section shimmers)"),
        decay=(1.0, 0.3, 3.0, "spiccato, pizzicato: how long the string rings on, times its natural time (low notes ring longer)"),
        bow=(1.0, 0.0, 4.0, "level of the bow's rosin noise and scratch (1 natural, 0 none)"),
        mute=(0.0, 0.0, 1.0, "a mute on the bridge (con sordino): 0 open, 1 muted (veiled, the highs and the nasal peak gone)"),
        detune=(8.0, 0.0, 30.0, _SECTION_DETUNE),
        ring=(0.25, 0.03, 3.0, "seconds of the release after its held steps (the string rings on as it darkens; notes that follow without a rest overlap "
              "into a legato)"),
        glide=(0.06, 0.01, 1.0, _GLIDE),
        touch=_TOUCH,
    )


def _strings(name: str, words: str, level: float, octave: int, low: str, high: str, players: float, make: Callable[..., np.ndarray]) -> Instrument:
    return _orchestral(name, words, level, octave, low, high, _string_settings(players), make, "strings", _string_respond, _bowed)


_MALLET = "what strikes it, 0 to 1: the harder, the brighter the blow and the more of its own knock (the level stays)"
_DRUM_DECAY = "how long it rings, times its natural time (lower drums ring longer)"
_DRUM_PLAYERS = "drums struck together: 1 one drum (mono), more an ensemble spread from left to right, each drum tuned a little apart (as loud as one)"
_APART = "seconds the players of an ensemble are apart at most (0: exactly together)"
_HIT_ROLL = ("hit", "roll")
_HIT_SWELL = ("hit", "swell")


def _roll(speed: float, low: float, high: float) -> dict[str, tuple[Any, ...]]:
    return {
        "stroke": (0.0, 0.0, 1.0, "hit: one blow; roll: fast blows of both hands for as long as its steps hold it (\"x - - -\"), at a steady level: shape a "
                   "crescendo with a volume curve", _HIT_ROLL),
        "speed": (speed, low, high, "roll: blows per second"),
    }


def _swell(speed: float) -> dict[str, tuple[Any, ...]]:
    return {
        "stroke": (0.0, 0.0, 1.0, "hit: one blow, ringing out; swell: a roll with soft mallets that grows from nearly nothing until its held steps end "
                   "(\"x | - | - | -\"), then rings out: end it on the bar where the hit falls", _HIT_SWELL),
        "speed": (speed, 5.0, 24.0, "swell: blows per second"),
    }


def _pad(name: str, words: str, level: float, octave: int, harmonics: tuple[float, ...], settings: dict[str, Setting]) -> Instrument:
    return Instrument(name, "pad", words, level, octave, settings, harmonics=harmonics, group="pads")


#: The instrument library by name, in catalogue order (drums, noises, basses, plucks and keys, leads, brass, organ, strings, percussion, choir, pads).
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
        replace(_voice("soft_lead", "a soft, mellow lead for melodies: a saw-like tone with a gentle vibrato; it sustains while held", 0.15, 5,
               _settings(attack=(0.03, 0.003, 1.0, "seconds to fade in"), vibrato=(12.0, 0.0, 50.0, "vibrato depth in cents"), **_vibrato(5.0, 0.0),
                         tone=(2400.0, 600.0, 6000.0, _TONE), ring=(0.25, 0.02, 3.0, "seconds of the release after its held steps"),
                         glide=(0.05, 0.01, 1.0, _GLIDE)), _lead_note, "leads"), slurs=_always),
        _orchestral("trumpet", "a solo trumpet: bright and singing; the tone opens as each note speaks, vibrato comes in on held notes", 0.1, 4, "E3", "C6",
                    _brass_settings(0.05, 0.6, 9.0, 0.12, mute=_MUTE, players=(1.0, 1.0, 6.0, _PLAYERS), detune=(6.0, 0.0, 25.0, _SECTION_DETUNE)),
                    trumpet_note, "brass", _brass_respond, _always),
        _orchestral("horn", "a horn (French horn): round, warm and distant, darker than the trumpet; `players: 4` is the film-score horn section", 0.113, 3,
                    "B1", "F5",
                    _brass_settings(0.09, 0.4, 0.0, 0.18, mute=_MUTE, players=(1.0, 1.0, 8.0, _PLAYERS), detune=(6.0, 0.0, 25.0, _SECTION_DETUNE)),
                    horn_note, "brass", _brass_respond, _always),
        _orchestral("low_brass", "a low brass section (trombones, with `tuba` a tuba an octave under them): sustained chords, and with a long "
                    "`attack` the low swell (\"braam\") of film scores", 0.12, 2, "E1", "F4",
                    _brass_settings(0.07, 0.55, 0.0, 0.25, players=(4.0, 1.0, 8.0, _PLAYERS), detune=(7.0, 0.0, 25.0, _SECTION_DETUNE),
                                    tuba=(0.0, 0.0, 1.5, "level of a tuba doubling each note an octave lower (0 none)")),
                    low_brass_note, "brass", _brass_respond, _always),
        _orchestral("organ", "a drawbar organ: nine ranks at the organ footages; `registration` picks a named one (" + ", ".join(REGISTRATION_NAMES)
                    + "), `drawbars` sets the nine bars yourself; hold chords with \"* | - | - | -\" and give it a long reverb", 0.14, 3, "C1", "C7",
                    _settings(
                        registration=(0.0, 0.0, float(len(REGISTRATIONS) - 1),
                                      "the stops drawn: " + "; ".join(f"{r.name}: {r.words}" for r in REGISTRATIONS), REGISTRATION_NAMES),
                        drawbars=(0.0, 0.0, 888888888.0, "the nine drawbars 16' 5 1/3' 8' 4' 2 2/3' 2' 1 3/5' 1 1/3' 1', each 0 (off) to 8 (full; a step "
                                  "down halves the power), in quotes: \"00 8400 000\"; they replace the registration's bars, the pipes stay its kind (0: the "
                                  "registration's own)", (), read_drawbars),
                        tone=(7000.0, 500.0, 12000.0, _TONE),
                        detune=(0.0, 0.0, 15.0, "cents the ranks are out of tune with each other (about a third of it): a chord shimmers slowly, a held note's tone "
                                "drifts (0: every rank in tune, the tone stands still); with `chorus` its pipes are a further 1-2 times this apart (then at least 3)"),
                        chorus=(0.0, 0.0, 1.0, "level of a second, detuned pipe on every rank: a slow beating like a celeste stop (0 none: a steady tone)"),
                        chiff=(1.0, 0.0, 3.0, "strength of the pipes' speech noise, times the registration's own (0 none; drawbar and full have none)"),
                        attack=(1.0, 0.2, 5.0, "how slowly the pipes speak, times the registration's own (low pipes speak later than high ones)"),
                        click=(0.0, 0.0, 1.0, "level of a key click when a key goes down and up (0 none)"),
                        ring=(0.09, 0.02, 2.0, "seconds of the release after its held steps"),
                    ), organ_note, "organ"),
        _strings("violins", "a violin section (`players: 1`: a solo violin): bowed, with the body of the instrument in the tone; `stroke` picks "
                 "sustain, spiccato, tremolo or pizzicato", 0.115, 4, "G3", "C7", 6.0, violins_note),
        _strings("violas", "a viola section: the darker, slightly nasal middle voice of the strings; strokes as for the violins", 0.115, 3, "C3", "E6", 5.0, violas_note),
        _strings("cellos", "a cello section: warm tenor and bass lines, low ostinatos (`stroke: spiccato`); strokes as for the violins", 0.115, 2, "C2", "A5", 4.0,
                 cellos_note),
        _strings("double_basses", "a double bass section: the floor of the strings; bowed, or `stroke: pizzicato` for a plucked bass line", 0.115, 1, "C1", "G4",
                 3.0, basses_note),
        _orchestral("timpani", "timpani (kettledrums), played by note name (\"D2 . . A2\"): a drum with a pitch, its overtones a fifth, an octave and a "
                    "tenth above the note; `stroke: roll` for a roll", 0.22, 2, "D2", "A3",
                    _settings(**_roll(11.0, 5.0, 22.0),
                              mallet=(0.4, 0.0, 1.0, _MALLET + ": 0.15 soft felt (round, for rolls), 0.4 medium, 0.8 wood (clear, hard)"),
                              decay=(1.0, 0.2, 2.5, _DRUM_DECAY),
                              ring=(3.0, 0.05, 8.0, "seconds it rings on after its held steps before a hand damps it: 3 lets it ring out, 0.1-0.3 is a damped (secco) note"),
                              touch=_TOUCH),
                    timpani_note, "percussion", _struck_respond),
        _orchestral("toms", "concert toms from high to floor, played by note name (a fill: \"C4 A3 F3 . D3 A2 F2 .\"): the pitch falls as the head "
                    "settles, the shell rings under it", 0.24, 2, "G1", "C5",
                    _settings(**_roll(14.0, 5.0, 26.0),
                              mallet=(0.75, 0.0, 1.0, _MALLET + ": 0.2 a felt mallet (round, like small timpani), 0.75 a stick"),
                              drop=(1.0, 0.0, 4.0, "semitones the pitch starts sharp before it falls to the note (0 none, 2-3 a slack, growling head)"),
                              decay=(1.0, 0.2, 3.0, _DRUM_DECAY),
                              shell=(1.0, 0.0, 3.0, "level of the shell's own ring (0: the head alone)"),
                              ring=(1.5, 0.05, 6.0, "seconds it rings on after its held steps before it is damped"),
                              touch=_TOUCH),
                    toms_note, "percussion", _struck_respond),
        _struck_drum("taiko", "a taiko, the big drum of film-score hits: a hard stick on a thick head over a barrel, a crack and a long low tail; `players` "
              "makes it an ensemble", 0.3,
              _settings(pitch=(62.0, 36.0, 130.0, "the head's lowest note in Hz (45 huge, 62 big, 100 a smaller drum answering)"),
                        mallet=(0.7, 0.0, 1.0, _MALLET), decay=(1.0, 0.2, 2.5, _DRUM_DECAY),
                        drop=(1.5, 0.0, 4.0, "semitones the pitch starts sharp before it falls"),
                        players=(1.0, 1.0, 8.0, _DRUM_PLAYERS), apart=(0.022, 0.0, 0.08, _APART)), taiko_sound),
        _struck_drum("bass_drum", "a concert bass drum (gran cassa): a soft beater on a wide head, a deep bloom without a click and a long tail", 0.3,
              _settings(pitch=(40.0, 26.0, 75.0, "the head's lowest note in Hz"), mallet=(0.25, 0.0, 1.0, _MALLET), decay=(1.0, 0.2, 2.5, _DRUM_DECAY),
                        players=(1.0, 1.0, 4.0, _DRUM_PLAYERS), apart=(0.03, 0.0, 0.08, _APART)), bass_drum_sound),
        _struck_drum("frame_drum", "a frame drum played by hand: one head on a hoop; `edge` moves the stroke from the deep middle to the bright rim", 0.2,
              _settings(pitch=(110.0, 55.0, 280.0, "the head's lowest note in Hz"),
                        mallet=(0.4, 0.0, 1.0, _MALLET + ": 0.2 the flat hand, 0.4 fingers, 0.9 a stick"),
                        edge=(0.0, 0.0, 1.0, "where it is struck: 0 the middle (deep, open), 1 at the rim (short and bright); change it per section, or use "
                              "two tracks for a pattern of both"),
                        decay=(1.0, 0.2, 2.5, _DRUM_DECAY), players=(1.0, 1.0, 8.0, _DRUM_PLAYERS), apart=(0.015, 0.0, 0.08, _APART)),
              frame_drum_sound),
        _struck_drum("snare_drum", "an orchestral snare drum: a short head and the rattle of the snare wires; `stroke: roll` for a roll, `players` for a line "
              "of field drums", 0.22,
              _settings(**_roll(26.0, 10.0, 40.0),
                        pitch=(185.0, 130.0, 280.0, "the head's lowest note in Hz"), mallet=(0.7, 0.0, 1.0, _MALLET),
                        snares=(1.0, 0.0, 2.0, "level of the snare wires (0: snares off, a dry tom-like drum)"),
                        decay=(1.0, 0.4, 2.5, "how long head and wires ring, times their natural time"),
                        players=(1.0, 1.0, 8.0, _DRUM_PLAYERS), apart=(0.012, 0.0, 0.08, _APART)), snare_drum_sound),
        _struck_drum("cymbal", "a suspended cymbal: a blow that rings for seconds (a crash with a soft start), or `stroke: swell`, the mallet roll that "
              "grows into a hit (stereo)", 0.065,
              _settings(**_swell(14.0),
                        pitch=(1.0, 0.6, 1.6, "the size: under 1 a larger, lower cymbal, over 1 a smaller, higher one"),
                        mallet=(0.5, 0.0, 1.0, _MALLET + ": 0.2 soft yarn (a wash), 0.5 a medium mallet, 1 a stick (a ping)"),
                        decay=(1.0, 0.2, 2.0, "how long it rings, times its natural time")), cymbal_sound),
        _struck_drum("tam_tam", "a tam-tam (a large flat gong): a dark blow whose highs arrive a second later and a very long tail; `stroke: swell` grows "
              "into one (stereo)", 0.1,
              _settings(**_swell(9.0),
                        pitch=(1.0, 0.6, 1.8, "the size: under 1 a larger, lower gong, over 1 a smaller one"),
                        mallet=(0.3, 0.0, 1.0, _MALLET),
                        bloom=(1.0, 0.0, 2.0, "how much the highs grow in after the blow (0: none, a dull gong; 2: a roaring one)"),
                        decay=(1.0, 0.2, 2.0, "how long it rings, times its natural time")), tam_tam_sound),
        _orchestral("choir", "a choir holding a vowel or singing syllables (no words): `vowel` picks " + ", ".join(VOWELS) + "; `syllable` a consonant "
                    "into a vowel or two vowels (la, na, ma, da, mm-ah, ah-oh ...; also per note: [la]); `voices` who sings (" + ", ".join(VOICES)
                    + "); `soloist: true` one solo voice; `whisper` breath instead of tone; hold chords with \"* | - | - | -\" in a hall", 0.125, 3, "E2", "C6",
                    _settings(
                        vowel=(0.0, 0.0, float(len(VOWELS) - 1), "the vowel held: ooh (dark, round), aah (open, full), eeh (brighter, as in \"bed\"), mm (a hum, "
                               "the mouth closed), oh, ee (thin and bright)", VOWELS),
                        voices=(0.0, 0.0, float(len(VOICES) - 1), "who sings: mixed (every note by the kinds of voice that reach it: basses lowest, then tenors, "
                                "altos, sopranos), men (basses and tenors), women (altos and sopranos), or one kind for every note", VOICES),
                        singers=(8.0, 1.0, 16.0, "singers on each note: each with its own throat, tuning, vibrato and entry (as loud as one; 1 is a single, "
                                 "plainly synthetic voice, mono)"),
                        attack=(0.25, 0.03, 4.0, "seconds to reach full level (each singer a little sooner or later): 0.08 firm, 0.25 sung, 1 and more a swell"),
                        brightness=(0.5, 0.0, 1.0, "how the voices sing: 0 soft and covered, 1 full voice (more upper harmonics; the level stays)"),
                        vibrato=(16.0, 0.0, 50.0, "vibrato depth in cents; every singer has its own speed, depth and delay around `vibrato_speed` and "
                                 "`vibrato_delay`; 0 is a straight, early-music tone"),
                        **_vibrato(5.5, 0.3),
                        breath=(1.0, 0.0, 4.0, "level of the breath in the voices (1 natural, 0 none, 3 airy)"),
                        detune=(10.0, 0.0, 30.0, "cents the singers of a section are apart"),
                        morph=(0.0, 0.0, float(len(MORPHS) - 1), "the vowel a held note turns into over its middle (none: it keeps its vowel): `vowel: mm, "
                               "morph: aah` opens from a hum; with `syllable: vowel` only (a syllable sings its own vowels: "
                               "`syllable: mm-ah` for a hum that opens)", MORPHS),
                        ring=(0.4, 0.05, 3.0, "seconds of the release after its held steps (notes that follow without a rest overlap)"),
                        glide=(0.08, 0.01, 1.0, _GLIDE),
                        touch=_TOUCH,
                        syllable=(0.0, 0.0, float(len(SYLLABLES) - 1), "what each note sings: vowel (the `vowel` setting held, no consonant), a soft "
                                  "consonant l, n, m or d into a vowel (la lo loo le lee, na ..., ma ..., da ...: a = aah, o = oh, oo = ooh, e = eeh, "
                                  "ee = ee), or two vowels, the second from `turn` on (mm-ah mm-oh mm-oo ah-oh oo-ah oh-ah ah-ee); a consonant starts "
                                  "the note at once (`attack` then shapes nothing); inside a slur only where a mark writes one", SYLLABLES),
                        turn=(0.5, 0.1, 0.9, "two-vowel syllables: where in the note the second vowel takes over, as a share of the note (it glides "
                              "over 0.15 s)"),
                        soloist=(0.0, 0.0, 1.0, "true: one solo voice instead of the section (mono; `singers` ignored): brighter, with the singer's "
                                 "formant near 3 kHz, a wider vibrato that comes later, a scoop up into each note and more breath; a track of its own "
                                 "over a choir track", (), read_yes_no),
                        whisper=(0.0, 0.0, 1.0, "breath instead of tone: 0 sung, 0.3-0.6 breathy, 1 an unvoiced whisper (noise through the vowel's "
                                 "formants, about as loud as the voice)"),
                    ), choir_note, "choir", _choir_respond, _always),
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
GROUPS = ("drums", "noises", "basses", "plucks and keys", "leads", "brass", "organ", "strings", "percussion", "choir", "pads")
