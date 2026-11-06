"""Stereo staging and room acoustics of the voices (DESIGN.md §111.4).

Opt-in, applied in the mix to each beat's voice after its overlap shape, never to the MP3s (the
TTS hashes do not change): ``pan:`` on a voice of ``voice:`` / ``voices:`` or on a beat (a
number from -1, left, to 1, right, a named position of :data:`POSITIONS`, or a beat's ``{from,
to}``: an eased move across its line); ``audio.follow_stage``: on a stage scene each voice sounds
where its speaking character stands; ``room:`` per scene (default ``audio.room``): one of
:data:`ROOM_PRESETS`, the narrator (the base voice) dry unless ``narrator: true``.

A voice is panned with the effects' equal-power law (:func:`vidgen.sfx.stereo`: at the centre
both channels carry it at full level, so a centred voice is unchanged). A room is generated, never
downloaded: its *early reflections* (a few delayed copies of the voice, a corridor's flutter echo,
a car's tight boxy ones) are added to the dry voice and panned with it; its *reverberation* is a
pair of impulse responses made from seeded noise (one seed per channel, so the tail is wide and
decorrelated), split at :data:`CROSSOVER` into a low and a high band that decay with their own
RT60 (the highs die first, as in a real room), band-limited, normalised to unit energy and set
:attr:`RoomPreset.wet_db` under the voice. The voice is convolved with both (FFT). ``phone``
replaces the voice by its 300-3400 Hz band, a little saturated, at the same RMS. The output is
longer than the voice by the reverberation's tail, so a line's room rings out under the next one
(a scene in another room starts dry of it: rooms change as smoothly as the tails overlap). Every
step is deterministic numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import numpy as np

from vidgen.sfx import RATE

if TYPE_CHECKING:
    from vidgen.config import BeatConfig, SceneConfig, VideoConfig

#: Named stereo positions (the stage's marks far_left 0.1, left 0.25 ... far_right 0.9 of its
#: width, as pans).
POSITIONS: dict[str, float] = {"far_left": -0.8, "left": -0.5, "centre": 0.0, "center": 0.0, "right": 0.5, "far_right": 0.8}
#: Hz where a room's reverberation splits into the band that decays with ``rt60`` and the higher
#: band that decays with ``rt60_high``.
CROSSOVER = 2000.0
#: Seconds over which the reverberation builds up after its pre-delay.
ONSET = 0.008
#: The phone's band (Hz) and its saturation drive.
PHONE_BAND = (300.0, 3400.0)
PHONE_DRIVE = 2.0
#: Seconds over which a tail that would outlast its scene fades out (video renders).
TAIL_FADE = 0.25


@dataclass(frozen=True)
class RoomPreset:
    """A room: its reverberation (``rt60`` seconds below :data:`CROSSOVER`, ``rt60_high`` above,
    after ``predelay`` seconds, ``wet_db`` under the voice, band-limited to ``band`` Hz; 0: none)
    and its early reflections (``early``: (milliseconds, gain) taps added to the dry voice)."""

    name: str
    description: str
    rt60: float = 0.0
    rt60_high: float = 0.0
    predelay: float = 0.0
    wet_db: float = -60.0
    band: tuple[float, float] = (100.0, 8000.0)
    early: tuple[tuple[float, float], ...] = ()
    phone: bool = False


def _flutter(first: float, step: float, gain: float, decay: float, count: int) -> tuple[tuple[float, float], ...]:
    """A flutter echo between two parallel walls: taps every ``step`` ms from ``first``."""
    return tuple((first + step * k, gain * decay**k) for k in range(count))


#: The rooms of ``room:`` (``none``: dry). Their numbers are rough measures of such spaces: an
#: office of ~30 m² with soft furniture, a long hard corridor (walls ~1.9 m apart: an 11 ms
#: flutter), a concert-sized hall, open air with a building ~15 m away, a car's cabin.
ROOM_PRESETS: dict[str, RoomPreset] = {
    "none": RoomPreset("none", "dry: the voice as recorded"),
    "small_office": RoomPreset(
        "small_office", "a small furnished room: short, soft reverberation (RT60 0.4 s), close reflections",
        rt60=0.4, rt60_high=0.25, predelay=0.004, wet_db=-12.0, band=(150.0, 7000.0), early=((4.0, 0.22), (7.5, 0.17), (11.0, 0.13), (17.0, 0.09)),
    ),
    "corridor": RoomPreset(
        "corridor", "a long hard corridor: a metallic flutter echo and a 1.1 s tail",
        rt60=1.1, rt60_high=0.6, predelay=0.010, wet_db=-11.0, band=(200.0, 6000.0), early=_flutter(11.0, 11.0, 0.26, 0.8, 10),
    ),
    "hall": RoomPreset(
        "hall", "a large hall: a long, smooth reverberation (RT60 2.2 s) after a 25 ms pre-delay",
        rt60=2.2, rt60_high=1.2, predelay=0.025, wet_db=-9.0, band=(100.0, 7000.0), early=((19.0, 0.16), (31.0, 0.13), (43.0, 0.11), (57.0, 0.08)),
    ),
    "outdoors": RoomPreset(
        "outdoors", "open air: almost dry, a faint slap from a building far off",
        rt60=0.3, rt60_high=0.15, predelay=0.040, wet_db=-27.0, band=(250.0, 5000.0), early=((88.0, 0.10), (161.0, 0.05)),
    ),
    "car": RoomPreset(
        "car", "a car's cabin: very short, boxy reflections (RT60 0.12 s)",
        rt60=0.12, rt60_high=0.06, predelay=0.001, wet_db=-13.0, band=(90.0, 3500.0), early=((1.6, 0.30), (2.9, 0.24), (4.3, 0.17)),
    ),
    "phone": RoomPreset("phone", "a telephone line: 300-3400 Hz, a little saturated, no room", phone=True),
}
#: The room names in order (``config.RoomName``; a test keeps them equal).
ROOMS: tuple[str, ...] = tuple(ROOM_PRESETS)


@dataclass(frozen=True)
class VoiceStaging:
    """Where a beat's voice sounds: ``pan`` (-1 to 1) as the line starts, ``pan_to`` as it ends
    (``None``: it stays), in ``room`` with ``amount`` of it."""

    pan: float = 0.0
    pan_to: float | None = None
    room: str = "none"
    amount: float = 1.0

    @property
    def plain(self) -> bool:
        """Whether the voice plays as it is (centred, dry)."""
        return self.pan == 0.0 and self.pan_to is None and (self.room == "none" or (self.amount == 0.0 and not ROOM_PRESETS[self.room].phone))

    def to_json(self) -> dict[str, Any]:
        """``{pan, pan_to, room, amount}`` (fingerprints, timings)."""
        return {"pan": self.pan, "pan_to": self.pan_to, "room": self.room, "amount": self.amount}


# ----- settings ------------------------------------------------------------------------------------


def pan_value(setting: Any) -> float:
    """The pan (-1 to 1) of a ``pan:`` number or named position (``None``: 0)."""
    if setting is None:
        return 0.0
    if isinstance(setting, str):
        return POSITIONS[setting]
    return float(min(1.0, max(-1.0, setting)))


def room_of(setting: Any) -> tuple[str, float, bool]:
    """``(name, amount, narrator)`` of a ``room:`` setting (a name or ``RoomConfig``; ``None``: dry)."""
    if setting is None:
        return "none", 1.0, False
    if isinstance(setting, str):
        return setting, 1.0, False
    return setting.use, float(setting.amount), bool(setting.narrator)


def stage_pan(x: float) -> float:
    """The pan of a place ``x`` from 0 (the frame's left edge) to 1 (its right edge)."""
    return float(min(1.0, max(-1.0, 2.0 * x - 1.0)))


def params_stage_pan(config: VideoConfig, scene: SceneConfig, beat: BeatConfig) -> float | None:
    """With ``audio.follow_stage``, a stage scene's pan for ``beat``: where its speaking
    characters stand in the scene's ``characters:`` params (their marks or x, averaged; the
    audio-only render's view: a video render takes where they stand as the line starts);
    ``None`` otherwise or when no character on the stage has the beat's voice."""
    from vidgen.cartoon.cast import beat_voice, speaking_characters
    from vidgen.cartoon.stage import mark_x

    if not config.audio.follow_stage or scene.type != "stage":
        return None
    places: dict[str, Any] = {}
    for item in scene.params.get("characters") or []:
        if isinstance(item, str):
            places[item] = "centre"
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            places[item["name"]] = item.get("at", "centre")
    names = speaking_characters(config, beat_voice(scene, beat), places)
    xs = []
    for name in names:
        try:
            xs.append(mark_x(places[name], scene.params.get("marks")))
        except (KeyError, TypeError, ValueError):
            continue
    return stage_pan(sum(xs) / len(xs)) if xs else None


def beat_staging(config: VideoConfig, scene: SceneConfig, beat: BeatConfig, stage: float | None = None) -> VoiceStaging:
    """Where ``beat`` of ``scene`` sounds: its own ``pan`` (a move with ``{from, to}``), else
    ``stage`` (the pan of its character's place, :attr:`AudioConfig.follow_stage`), else its
    voice's ``pan``; in the scene's ``room`` (else ``audio.room``), which leaves the base voice
    dry unless ``narrator: true``."""
    from vidgen.config import PanMove
    from vidgen.voices import DEFAULT_VOICE

    name = beat.voice or scene.voice or DEFAULT_VOICE
    entry = config.voice if name == DEFAULT_VOICE else config.voices.get(name)
    pan_to = None
    if isinstance(beat.pan, PanMove):
        pan, pan_to = pan_value(beat.pan.from_), pan_value(beat.pan.to)
    elif beat.pan is not None:
        pan = pan_value(beat.pan)
    elif stage is not None:
        pan = stage
    else:
        pan = pan_value(entry.pan if entry is not None else None)
    room, amount, narrator = room_of(scene.room if scene.room is not None else config.audio.room)
    if name == DEFAULT_VOICE and not narrator:
        room = "none"
    return VoiceStaging(pan, pan_to, room, amount if room != "none" else 1.0)


def uses_staging(config: VideoConfig) -> bool:
    """Whether anything in ``config`` places voices or widens the music (the render then reports
    the file's mono compatibility)."""
    audio = config.audio
    if audio.room is not None or audio.follow_stage or audio.music_width != 1.0 or audio.ambience_width != 1.0:
        return True
    if config.voice.pan is not None or any(v.pan is not None for v in config.voices.values()):
        return True
    return any(s.room is not None or any(b.pan is not None for b in s.beats) for s in config.scenes)


# ----- signal --------------------------------------------------------------------------------------


def pan_gains(pan: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
    """Left and right gains of the equal-power law (:func:`vidgen.sfx.stereo`: 1 and 1 at 0)."""
    angle = (np.asarray(pan, dtype=np.float64) + 1) * math.pi / 4
    return math.sqrt(2) * np.cos(angle), math.sqrt(2) * np.sin(angle)


def _band_gain(freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """A second-order (Butterworth-like) band-pass magnitude between ``lo`` and ``hi`` Hz."""
    f = np.maximum(freqs, 1e-3)
    return 1 / np.sqrt(1 + (lo / f) ** 4) / np.sqrt(1 + (f / hi) ** 4)


@lru_cache(maxsize=16)
def reverb_ir(name: str, channel: int) -> np.ndarray:
    """The reverberation impulse response of room ``name`` for ``channel`` (0 left, 1 right;
    float64 at :data:`~vidgen.sfx.RATE`, energy ``10 ** (wet_db / 10)``; empty for a room
    without one). Always the same samples."""
    room = ROOM_PRESETS[name]
    if room.rt60 <= 0:
        return np.zeros(0)
    n = round((room.predelay + room.rt60 * 1.3) * RATE)
    rng = np.random.default_rng(1110 + 7 * ROOMS.index(name) + channel)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    shaped = spectrum * _band_gain(freqs, *room.band)
    low_weight = 1 / np.sqrt(1 + (freqs / CROSSOVER) ** 4)
    low = np.fft.irfft(shaped * low_weight, n)
    high = np.fft.irfft(shaped * np.sqrt(1 - low_weight**2), n)
    t = np.arange(n) / RATE - room.predelay
    live = np.clip(t, 0.0, None)
    ir = low * np.exp(-6.91 * live / room.rt60) + high * np.exp(-6.91 * live / room.rt60_high)
    ir *= np.clip(t / ONSET, 0.0, 1.0)
    return ir * (10 ** (room.wet_db / 20) / float(np.sqrt(np.sum(ir**2))))


def _convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    size = 1 << (len(x) + len(ir) - 2).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x) + len(ir) - 1]


def _phone(x: np.ndarray) -> np.ndarray:
    """``x`` through a telephone line: its :data:`PHONE_BAND`, a soft saturation, the band again
    (the saturation's overtones cut), at the same RMS."""
    if not len(x):
        return x
    gain = _band_gain(np.fft.rfftfreq(2 * len(x), 1 / RATE), *PHONE_BAND) ** 2

    def band(y: np.ndarray) -> np.ndarray:
        return np.fft.irfft(np.fft.rfft(y, 2 * len(y)) * gain, 2 * len(y))[: len(y)]

    narrow = band(x)
    rms = float(np.sqrt(np.mean(narrow**2)))
    if rms <= 0:
        return narrow
    driven = band(np.tanh(PHONE_DRIVE * narrow / (rms * 4)) * (rms * 4) / PHONE_DRIVE)
    return driven * (float(np.sqrt(np.mean(x**2))) / float(np.sqrt(np.mean(driven**2))))


def stage_voice(samples: np.ndarray, staging: VoiceStaging, limit: int | None = None) -> np.ndarray:
    """A beat's voice (``(n, channels)`` at :data:`~vidgen.sfx.RATE`) as ``staging`` places it:
    ``(m, 2)`` float32, ``m`` past ``n`` by the room's tail. ``limit``: the samples it may last
    (a video's scene ends there; a tail beyond it fades out over :data:`TAIL_FADE`)."""
    x = samples.reshape(len(samples), -1).astype(np.float64)
    mono = x.mean(axis=1)
    n = len(mono)
    room = ROOM_PRESETS[staging.room]
    a = staging.amount
    if room.phone:
        mono = _phone(mono)
    taps = [(round(ms * RATE / 1000), gain * a) for ms, gain in room.early if gain * a > 0]
    irs = [reverb_ir(room.name, c) for c in (0, 1)] if room.rt60 > 0 and a > 0 else []
    length = n + max([d for d, _ in taps] + [len(irs[0]) - 1 if irs else 0])
    dry = np.zeros(length)
    dry[:n] = mono
    for delay, gain in taps:
        dry[delay : delay + n] += gain * mono
    if staging.pan_to is None:
        left, right = pan_gains(staging.pan)
    else:  # eased from the first to the last sample above -40 dB of the peak (the speech)
        heard = np.nonzero(np.abs(mono) > 0.01 * float(np.max(np.abs(mono), initial=0.0)))[0]
        first, last = (int(heard[0]), int(heard[-1])) if heard.size else (0, n - 1)
        u = np.clip((np.arange(length) - first) / max(last - first, 1), 0.0, 1.0)
        left, right = pan_gains(staging.pan + (staging.pan_to - staging.pan) * (0.5 - 0.5 * np.cos(np.pi * u)))
    out = np.stack([dry * left, dry * right], axis=1)
    for c, ir in enumerate(irs):
        wet = _convolve(mono, ir) * a
        out[: len(wet), c] += wet
    if limit is not None and length > limit:
        out = out[: max(limit, 0)]
        fade = min(round(TAIL_FADE * RATE), max(limit - n, 0))
        if fade > 0:
            out[limit - fade :] *= (0.5 + 0.5 * np.cos(np.pi * np.arange(1, fade + 1) / fade))[:, None]
    return out.astype(np.float32)


def widen(x: np.ndarray, width: float) -> np.ndarray:
    """Stereo ``x`` (``(n, 2)``) with its side (L - R) scaled by ``width`` (0: mono, 1: as it is)."""
    if width == 1.0:
        return x
    mid = (x[:, 0] + x[:, 1]) / 2
    side = (x[:, 0] - x[:, 1]) / 2 * width
    return np.stack([mid + side, mid - side], axis=1)


__all__ = [
    "POSITIONS",
    "ROOMS",
    "ROOM_PRESETS",
    "RoomPreset",
    "VoiceStaging",
    "beat_staging",
    "pan_gains",
    "pan_value",
    "params_stage_pan",
    "reverb_ir",
    "room_of",
    "stage_pan",
    "stage_voice",
    "uses_staging",
    "widen",
]
