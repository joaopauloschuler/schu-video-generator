"""Non-speech voice sounds in a beat's text: ``[gasp]``, ``[hmm]``, ``[laugh]``, ``[sigh]``,
``[giggle]``, ``[groan]`` (DESIGN.md §69.33) and a robot's ``[beep]`` (§69.58).

- :func:`take_out_sounds` finds the markers (a trailing ``s`` is allowed: ``[laughs]``) and
  returns the text without them plus each :class:`VoiceSound` with the number of words before
  it. :class:`~vidgen.config.BeatConfig` calls it, so ``beat.text`` (captions, SRT, bubbles,
  slides, readback's written text) never shows a marker. Other ``[...]`` stay in the text.
- :func:`sound_voicing` says how a beat's voice makes a sound: words the TTS says (Kokoro, most
  ElevenLabs models and OpenRouter say ``Hmm.``, ``Ha ha ha!``), an ElevenLabs v3 audio tag
  (``[laughs]``), or ``None``: a built-in generated sound (:data:`VoiceSoundKind.sfx`) mixed into
  the silence before or after the line. :func:`voiced_spoken` puts the said forms into a
  :class:`~vidgen.pronunciation.Spoken` text (the audio hash covers them, so a beat without
  markers keeps its hash).
- :func:`sound_spans` times the sounds of a beat from its word times; the narration records the
  generated ones as sound effects, lip sync opens the mouth for them and a stage's speaker gets
  the sound's expression.

No manim import (``vidgen.config`` uses it).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from vidgen.config import BeatConfig, VoiceConfig
    from vidgen.project import Project
    from vidgen.pronunciation import Spoken
    from vidgen.speech import WordTime


@dataclass(frozen=True)
class VoiceSoundKind:
    """A voice sound: ``said`` (what a TTS says for it), ``tag`` (ElevenLabs v3's audio tag;
    ``None``: ``said``), ``sfx`` (the built-in sound played instead at a line's start or end;
    ``None``: always said), ``expression`` (the speaker's face on a stage), ``viseme`` (the
    mouth during a generated sound) and ``heard`` (words a transcript may show for it)."""

    name: str
    said: str
    expression: str
    heard: frozenset[str]
    tag: str | None = None
    sfx: str | None = None
    viseme: str = "O"


#: The voice sounds, by marker name.
VOICE_SOUNDS: dict[str, VoiceSoundKind] = {
    k.name: k
    for k in (
        VoiceSoundKind("gasp", "Hah!", "surprised", frozenset({"hah", "ha", "huh", "ah", "oh", "gasp", "gasps"}), "[gasps]", "gasp", "O"),
        VoiceSoundKind("hmm", "Hmm.", "thinking", frozenset({"hmm", "hm", "hmmm", "mm", "mmm", "mhm", "um", "uh"})),
        VoiceSoundKind("laugh", "Ha ha ha!", "happy", frozenset({"ha", "haha", "hahaha", "hah", "heh", "laugh", "laughs", "laughing"}), "[laughs]"),
        VoiceSoundKind("sigh", "Haah.", "sad", frozenset({"haah", "hah", "ha", "ah", "ahh", "oh", "sigh", "sighs"}), "[sighs]", "sigh", "A"),
        VoiceSoundKind("giggle", "Hee hee!", "happy", frozenset({"hee", "heehee", "hehe", "hihi", "he", "giggle", "giggles"}), "[giggles]"),
        VoiceSoundKind("groan", "Ugh.", "worried", frozenset({"ugh", "uh", "argh", "groan", "groans"}), "[groans]"),
        VoiceSoundKind("beep", "Beep boop!", "happy", frozenset({"beep", "boop", "bleep", "bip", "beeps"}), None, "beep", "E"),
    )
}

#: A marker in a beat's text: ``[laugh]`` or ``[laughs]`` (any case), with the spaces before it.
SOUND_MARKER = re.compile(r"\s*\[(" + "|".join(VOICE_SOUNDS) + r")s?\]", re.IGNORECASE)
#: Seconds between a generated sound and the speech it precedes or follows.
SOUND_GAP = 0.05
#: Gain (dB) of a generated voice sound: built-in sounds sit under the narration (sfx
#: ``LOUDNESS_TARGET``); a breath is part of the voice, so it plays louder.
SOUND_GAIN_DB = 6.0


class VoiceSound(NamedTuple):
    """A voice sound of a beat: its ``kind`` (a :data:`VOICE_SOUNDS` name) and ``word``, how many
    words of the beat's text come before it."""

    kind: str
    word: int


class SoundSpan(NamedTuple):
    """When a beat's sound is heard, in seconds from the beat's start (``start`` may be negative:
    a generated sound before the line); ``generated``: a built-in sound, not the TTS."""

    kind: str
    word: int
    start: float
    end: float
    generated: bool


def is_voice_sound(name: str) -> bool:
    """Whether ``name`` (a bracket's content, e.g. ``laughs``) is a voice sound marker."""
    return SOUND_MARKER.fullmatch(f"[{name.strip()}]") is not None


def take_out_sounds(text: str) -> tuple[str, tuple[VoiceSound, ...]]:
    """``text`` without its sound markers (and the spaces before them) and the sounds found, in
    order. ``"Oh no [gasp] it fell"`` gives ``"Oh no it fell"`` and ``gasp`` after 2 words."""
    sounds: list[VoiceSound] = []
    plain = ""
    pos = 0
    for match in [*SOUND_MARKER.finditer(text), None]:
        piece = text[pos : match.start() if match is not None else len(text)]
        if not plain:
            piece = piece.lstrip()
        elif pos and piece[:1].isalnum():
            piece = " " + piece   # "[laugh]so" -> " so"
        plain += piece
        if match is None:
            break
        sounds.append(VoiceSound(match.group(1).lower(), len(plain.split())))
        pos = match.end()
    return (plain, tuple(sounds)) if sounds else (text, ())


def is_tagged_voice(voice: VoiceConfig) -> bool:
    """Whether ``voice`` reads ElevenLabs v3 audio tags (``[laughs]``)."""
    return voice.provider == "elevenlabs" and voice.model_id.startswith("eleven_v3")


def sound_voicing(voice: VoiceConfig, sound: VoiceSound, words: int) -> str | None:
    """What the TTS of ``voice`` gets for ``sound`` in a text of ``words`` words: an ElevenLabs v3
    audio tag, else the said form; ``None`` for a sound with a built-in ``sfx`` at the start or
    end of the line (generated in the silence there: a TTS says a breath as a word)."""
    kind = VOICE_SOUNDS[sound.kind]
    if is_tagged_voice(voice):
        return kind.tag or kind.said
    if kind.sfx is not None and sound.word in (0, words):
        return None
    return kind.said


def voiced_spoken(spoken: Spoken, sounds: Sequence[VoiceSound], voice: VoiceConfig) -> Spoken:
    """``spoken`` (the beat's text with pronunciation applied) with what ``voice`` says for each
    sound inserted after its word: what the TTS gets (:func:`sound_voicing`)."""
    ends = [m.end() for m in re.finditer(r"\S+", spoken.text)]
    inserts: list[tuple[int, str, str]] = []
    for sound in sounds:
        said = sound_voicing(voice, sound, len(ends))
        if said is None:
            continue
        if sound.word == 0:
            inserts.append((0, f"{said} ", f"[{sound.kind}]"))
        else:
            inserts.append((ends[sound.word - 1], f" {said}", f"[{sound.kind}]"))
    return spoken.inserted(inserts) if inserts else spoken


def sound_spans(sounds: Sequence[VoiceSound], words: Sequence[WordTime], seconds: float, voice: VoiceConfig) -> list[SoundSpan]:
    """When each sound of a beat is heard (seconds from its start), from ``words`` (the written
    words' times, :func:`vidgen.speech.beat_word_times`) over its ``seconds``: a said sound fills
    the gap between its words; a generated one ends :data:`SOUND_GAP` before the first word or
    starts that long after the last."""
    from vidgen.sfx import BUILTIN_SOUNDS

    out: list[SoundSpan] = []
    n = len(words)
    for sound in sounds:
        k = min(sound.word, n)
        said = sound_voicing(voice, sound, n)
        if said is not None or not n:
            start = words[k - 1].end if k > 0 else 0.0
            end = words[k].start if k < n else seconds
            out.append(SoundSpan(sound.kind, sound.word, start, max(end, start), False))
            continue
        length = BUILTIN_SOUNDS[VOICE_SOUNDS[sound.kind].sfx or ""].duration
        if k == 0:
            end = words[0].start - SOUND_GAP
            out.append(SoundSpan(sound.kind, sound.word, end - length, end, True))
        else:
            start = words[-1].end + SOUND_GAP
            out.append(SoundSpan(sound.kind, sound.word, start, start + length, True))
    return out


def beat_sound_spans(project: Project, beat: BeatConfig, seconds: float) -> list[SoundSpan]:
    """:func:`sound_spans` of a beat of ``project`` whose narration lasts ``seconds``: its words
    timed like its captions (the stored alignment of what the TTS said, else estimated)."""
    from vidgen.speech import beat_word_times

    if not beat.voice_sounds:
        return []
    spoken = project.spoken(beat)
    words = beat_word_times(project.audio_dir, beat.id, beat.text, 0.0, seconds, spoken, project.config.language)
    return sound_spans(beat.voice_sounds, words, seconds, project.beat_voice(beat.id))


def heard_sound_words(sounds: Sequence[VoiceSound]) -> frozenset[str]:
    """The words a transcript may show for ``sounds`` (normalised, lower case)."""
    return frozenset(w for s in sounds for w in VOICE_SOUNDS[s.kind].heard)
