"""A line's feeling (``emotion:``) as changes to how it is spoken (DESIGN.md §72). No manim, no
PyTorch.

``emotion: excited`` on a beat (or as a voice's default) names a row of :data:`EMOTIONS`: a
:class:`Prosody` of four numbers that the Kokoro provider applies to that beat's speech
(:mod:`vidgen.tts.kokoro`): a factor on the voice's speed, a pitch shift in semitones, a gain in
dB and a factor on the pauses at punctuation inside the beat. ``emotion: {like: sad, pitch: -2}``
changes some numbers of a row. ``neutral`` (or numbers that change nothing) changes nothing,
also not the beat's audio hash. :data:`EMOTION_WORDS` maps a screenplay's manner words
(``PIP (cross): ...``) to the rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Prosody:
    """How an emotion changes a line: ``speed`` (factor on the voice's speed), ``pitch``
    (semitones, the length kept), ``gain`` (dB; a boost is soft-limited below full scale) and
    ``pauses`` (factor on the pauses at commas and full stops inside the line)."""

    name: str = "neutral"
    speed: float = 1.0
    pitch: float = 0.0
    gain: float = 0.0
    pauses: float = 1.0

    @property
    def is_neutral(self) -> bool:
        """True when the numbers change nothing (whatever the name)."""
        return (self.speed, self.pitch, self.gain, self.pauses) == (1.0, 0.0, 0.0, 1.0)

    def spec(self) -> dict[str, Any]:
        """The name and the numbers, as they go into the audio hash."""
        return {"name": self.name, "speed": self.speed, "pitch": self.pitch, "gain": self.gain, "pauses": self.pauses}


#: The built-in emotions (the documented table, DESIGN.md §72).
EMOTIONS: dict[str, Prosody] = {
    p.name: p
    for p in (
        Prosody("neutral"),
        Prosody("happy", 1.05, 1.0, 1.5, 0.9),
        Prosody("excited", 1.12, 2.0, 3.0, 0.7),
        Prosody("sad", 0.86, -1.5, -3.0, 1.5),
        Prosody("angry", 1.06, -0.5, 3.0, 0.8),
        Prosody("worried", 1.04, 0.7, -1.5, 1.3),
        Prosody("scared", 1.1, 1.5, -1.0, 1.2),
        Prosody("surprised", 1.04, 2.5, 2.0, 1.0),
        Prosody("calm", 0.93, -0.5, -1.5, 1.2),
        Prosody("doubtful", 0.92, -0.3, -1.0, 1.4),
        Prosody("sleepy", 0.8, -2.0, -4.0, 1.6),
        Prosody("whisper", 0.92, -1.0, -9.0, 1.2),
        Prosody("shout", 1.06, 2.5, 5.0, 0.8),
    )
}
EMOTION_NAMES: tuple[str, ...] = tuple(EMOTIONS)
#: Allowed ranges of the numbers (``emotion: {like, speed, pitch, gain, pauses}``).
SPEED_RANGE = (0.5, 2.0)
PITCH_RANGE = (-3.0, 3.0)
GAIN_RANGE = (-12.0, 6.0)
PAUSES_RANGE = (0.25, 3.0)

#: A screenplay's manner words (and the names themselves) -> emotion.
EMOTION_WORDS: dict[str, str] = {
    **{name: name for name in EMOTION_NAMES},
    **{w: "happy" for w in (
        "glad", "cheerful", "pleased", "proud", "smiling", "beaming", "warm", "amused", "laughing", "laughs", "chuckling",
        "giggling", "playful", "cheeky", "teasing",
    )},
    **{w: "excited" for w in ("delighted", "thrilled", "eager", "enthusiastic", "overjoyed", "ecstatic")},
    **{w: "sad" for w in (
        "unhappy", "upset", "glum", "gloomy", "disappointed", "crying", "sobbing", "weeping", "in tears", "tearful", "cries",
    )},
    **{w: "angry" for w in ("cross", "annoyed", "furious", "mad", "grumpy", "irritated")},
    **{w: "worried" for w in ("nervous", "anxious", "uneasy", "embarrassed", "shy", "bashful", "flustered")},
    **{w: "scared" for w in ("frightened", "afraid", "terrified", "panicked", "petrified", "fearful")},
    **{w: "surprised" for w in ("shocked", "amazed", "astonished", "startled", "stunned")},
    **{w: "calm" for w in ("gentle", "soothing", "relaxed", "deadpan", "flat")},
    **{w: "doubtful" for w in ("puzzled", "unsure", "sceptical", "skeptical", "pondering", "thinking")},
    **{w: "sleepy" for w in ("tired", "drowsy", "yawning", "weary")},
    **{w: "whisper" for w in ("whispers", "whispering", "quietly", "softly", "hushed", "under breath", "under his breath",
                              "under her breath", "under their breath")},
    **{w: "shout" for w in ("shouts", "shouting", "yelling", "yells", "loudly", "calling out")},
}


class EmotionFields(Protocol):
    """``emotion: {like, speed, pitch, gain, pauses}`` as the config reads it."""

    like: str
    speed: float | None
    pitch: float | None
    gain: float | None
    pauses: float | None


def prosody(setting: str | EmotionFields | None) -> Prosody | None:
    """The prosody of an ``emotion:`` value (a name, or a mapping read by the config); ``None``
    when it is not set or changes nothing."""
    if setting is None:
        return None
    if isinstance(setting, str):
        found = EMOTIONS[setting]
    else:
        base = EMOTIONS[setting.like]
        changes = {k: float(v) for k in ("speed", "pitch", "gain", "pauses") if (v := getattr(setting, k)) is not None}
        found = Prosody(base.name, **{**{k: getattr(base, k) for k in ("speed", "pitch", "gain", "pauses")}, **changes})
    return None if found.is_neutral else found


def manner_emotion(manner: str) -> tuple[str | None, list[str]]:
    """The emotion a line's manner names (``(cross, arms crossed)`` -> ``angry``; the first
    one) and the manner's parts that name none."""
    found: str | None = None
    others: list[str] = []
    for part in (p.strip().lower() for p in re.split(r",|;|\band\b", manner) if p.strip()):
        emotion = EMOTION_WORDS.get(part)
        if emotion is None:
            others.append(part)
        elif found is None:
            found = emotion
    return found, others
