"""Voice effects: a voice that sounds through a hall, a robot, a radio or from another world
(DESIGN.md §100.2). No manim, no ffmpeg run here: this module turns a voice's ``effect:`` into
an ffmpeg audio filter chain; :mod:`vidgen.tts.effects` applies it to each beat's audio after
synthesis, for every provider.

Each effect is a named preset; several combine in a fixed order (pitch first, then the robot,
the radio band, the chorus, the echo and the hall; with the robot the pitch comes right after
it, moving its buzz), so ``[deep, hall]`` and ``[hall, deep]`` sound and hash the same. ``amount`` (0-1, default 0.5) sets how strong the wet effects (echo,
hall, chorus, robot) are; ``pitch`` (semitones) replaces the pitch of ``deep`` / ``high``.
The length is kept, except that an echo, a hall or a chorus adds a short tail of silence for its
reflections to ring out in (:data:`TAILS`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

#: The presets, in the order they are applied.
VOICE_EFFECTS: tuple[str, ...] = ("deep", "high", "robot", "radio", "chorus", "echo", "hall", "otherworldly")
#: What each preset does (docs, ``vidgen validate`` messages).
EFFECT_DESCRIPTIONS: dict[str, str] = {
    "deep": "4 semitones lower (a larger, darker voice)",
    "high": "4 semitones higher (a smaller, brighter voice)",
    "robot": "a flat, metallic monotone (the pitch replaced by a steady buzz)",
    "radio": "a narrow band like a radio or a phone",
    "chorus": "several slightly detuned copies (a voice of many)",
    "echo": "a short echo, as from a loudspeaker in a room",
    "hall": "a large hall's reverberation",
    "otherworldly": "deep (3 semitones lower), a chorus and a hall together: a resonant voice not of this world",
}
#: Presets that are other presets together.
COMBINED: dict[str, tuple[str, ...]] = {"otherworldly": ("deep", "chorus", "hall")}
#: Semitones of the pitch presets (``otherworldly``'s deep is :data:`OTHERWORLDLY_PITCH`).
PRESET_PITCH: dict[str, float] = {"deep": -4.0, "high": 4.0}
OTHERWORLDLY_PITCH = -3.0
#: The rate the effects work at (every provider's audio is resampled to it first).
EFFECT_RATE = 48000
#: Seconds a preset makes the audio longer, for the reflections to ring out after the speech.
TAILS: dict[str, float] = {"chorus": 0.1, "echo": 0.35, "hall": 0.9}
#: Seconds each preset's filter adds by itself at the end (ffmpeg's ``aecho`` and ``chorus``
#: play out their longest delay); the rest of the tail is silence padded before them.
DELAYS: dict[str, float] = {"robot": 0.011, "chorus": 0.075, "echo": 0.23, "hall": 0.347}
#: The default strength of the wet presets.
DEFAULT_AMOUNT = 0.5
#: dB a preset adds back so the voice stays about as loud (measured on Kokoro lines: the robot
#: loses about 13 dB, the radio band 5.5); a rough first step: the effect's audio is then
#: level-matched to the dry voice (:data:`MATCH_LIMIT`, :mod:`vidgen.tts.effects`).
GAINS: dict[str, float] = {"robot": 12.5, "radio": 5.5}
#: Largest correction (dB, either way) of the level match that brings each effect's audio to
#: the dry voice's integrated loudness.
MATCH_LIMIT = 15.0


@dataclass(frozen=True)
class VoiceEffect:
    """A voice's effect: the presets (each once, in :data:`VOICE_EFFECTS` order, combined ones
    expanded), the pitch shift in semitones (0: none) and the strength of the wet presets."""

    names: tuple[str, ...]
    pitch: float = 0.0
    amount: float = DEFAULT_AMOUNT

    def spec(self) -> dict[str, Any]:
        """What the audio depends on (part of each beat's hash; ``level``: the effect's audio is
        level-matched to the dry voice)."""
        return {"effects": list(self.names), "pitch": self.pitch, "amount": self.amount, "level": "matched"}

    @property
    def tail(self) -> float:
        """Seconds added after the speech (the longest tail of its presets)."""
        return max((TAILS.get(name, 0.0) for name in self.names), default=0.0)


def voice_effect(setting: Any) -> VoiceEffect | None:
    """The :class:`VoiceEffect` of an ``effect:`` setting: a preset's name, a list of names, or a
    mapping (``VoiceEffectConfig`` or a dict) with ``use``, ``pitch`` and ``amount``. ``None``
    for no effect. Raises ``ValueError`` for an unknown name."""
    if setting is None:
        return None
    pitch: float | None = None
    amount = DEFAULT_AMOUNT
    if isinstance(setting, str):
        given: Sequence[str] = [setting]
    elif isinstance(setting, (list, tuple)):
        given = list(setting)
    else:
        data = setting if isinstance(setting, dict) else setting.model_dump()
        use = data.get("use")
        given = [use] if isinstance(use, str) else list(use or [])
        pitch = data.get("pitch")
        amount = DEFAULT_AMOUNT if data.get("amount") is None else float(data["amount"])
    unknown = [name for name in given if name not in VOICE_EFFECTS]
    if unknown:
        raise ValueError(f"unknown voice effect {unknown[0]!r}; effects: {', '.join(VOICE_EFFECTS)}")
    expanded = {part for name in given for part in COMBINED.get(name, (name,))}
    if not expanded and pitch in (None, 0):
        return None
    names = tuple(name for name in VOICE_EFFECTS if name in expanded)
    if pitch is None:
        if "otherworldly" in given and not ({"deep", "high"} & set(given)):
            pitch = OTHERWORLDLY_PITCH
        else:
            pitch = sum(PRESET_PITCH.get(name, 0.0) for name in names)
    return VoiceEffect(names=tuple(n for n in names if n not in PRESET_PITCH), pitch=float(pitch), amount=amount)


def _pitch(semitones: float) -> list[str]:
    if semitones == 0.0:
        return []
    shifted = int(round(EFFECT_RATE * 2.0 ** (semitones / 12.0)))
    return [f"asetrate={shifted}", f"aresample={EFFECT_RATE}", f"atempo={EFFECT_RATE / shifted:.6f}"]


def _taps(delays: Sequence[int], first: float, last: float, amount: float) -> str:
    """``aecho`` delays and decays: from ``first`` to ``last`` (scaled by ``amount`` / 0.5)."""
    scale = amount / DEFAULT_AMOUNT
    n = max(len(delays) - 1, 1)
    decays = [min(0.95, (first + (last - first) * k / n) * scale) for k in range(len(delays))]
    return f"{'|'.join(str(d) for d in delays)}:{'|'.join(f'{d:.3f}' for d in decays)}"


def effect_filter(effect: VoiceEffect) -> str:
    """The ffmpeg audio filter chain of ``effect`` (mono, any rate in; :data:`EFFECT_RATE` out),
    ending in a limiter so the peaks stay below full scale."""
    parts = [f"aresample={EFFECT_RATE}", "aformat=channel_layouts=mono"]
    pad = effect.tail - sum(DELAYS.get(name, 0.0) for name in effect.names)
    if pad > 0:
        parts.append(f"apad=pad_dur={pad:.3f}")
    robot = "robot" in effect.names
    if not robot:
        parts += _pitch(effect.pitch)
    a = effect.amount
    s = a / DEFAULT_AMOUNT
    for name in effect.names:
        if name == "robot":
            # The phase of every frequency set to zero: the voice's own pitch is replaced by the
            # frame rate (48000 / 256 = 187.5 Hz), a flat buzz; then a short metallic comb. A
            # pitch shift comes after it, moving the buzz (-6: about 133 Hz).
            parts.append("afftfilt=real='hypot(re,im)':imag='0':win_size=1024:overlap=0.75")
            parts.append(f"aecho=1:0.8:{_taps([6, 11], 0.3, 0.24, a)}")
            parts.append(f"volume={GAINS['robot']}dB")
            parts += _pitch(effect.pitch)
        elif name == "radio":
            parts += ["highpass=f=320", "lowpass=f=3200", "acompressor=threshold=0.1:ratio=4:attack=5:release=60", f"volume={GAINS['radio']}dB"]
        elif name == "chorus":
            # in gain : out gain : delays (ms) : decays : speeds (Hz) : depths (ms)
            decays = "|".join(f"{min(0.95, d * s):.3f}" for d in (0.5, 0.4, 0.3))
            parts.append(f"chorus=0.7:0.9:45|60|75:{decays}:0.25|0.4|0.3:2|2.3|1.3")
        elif name == "echo":
            parts.append(f"aecho=1:0.85:{_taps([110, 230], 0.3, 0.15, a)}")
        elif name == "hall":
            parts.append(f"aecho=1:0.8:{_taps([37, 59, 83, 113, 149, 197, 263, 347], 0.42, 0.12, a)}")
    parts.append("alimiter=limit=0.89:level=false")
    return ",".join(parts)


__all__ = [
    "COMBINED",
    "DEFAULT_AMOUNT",
    "DELAYS",
    "EFFECT_DESCRIPTIONS",
    "VOICE_EFFECTS",
    "EFFECT_RATE",
    "MATCH_LIMIT",
    "OTHERWORLDLY_PITCH",
    "PRESET_PITCH",
    "TAILS",
    "VoiceEffect",
    "effect_filter",
    "voice_effect",
]
